"""
Fleet Scanner for Tailscale & Podman Agent Discovery.
Discovers Tailscale nodes and identifies Podman/Docker containers running Hermes or OpenClaw agents.
"""

import os
import json
import socket
import subprocess
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def load_config() -> Dict[str, Any]:
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

    # Environment variable overrides
    if os.environ.get("A2A_PROBE_PORTS"):
        try:
            cfg.setdefault("tailscale", {})["probe_ports"] = [
                int(p.strip()) for p in os.environ["A2A_PROBE_PORTS"].split(",")
            ]
        except Exception:
            pass

    return cfg


class FleetScanner:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or load_config()
        self.probe_ports = self.config.get("tailscale", {}).get(
            "probe_ports", [8080, 18789, 18880, 18812, 18813, 8642, 8644]
        )

    def get_tailscale_nodes(self) -> List[Dict[str, Any]]:
        """Query Tailscale status JSON to get all nodes."""
        try:
            res = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=8)
            if res.returncode != 0:
                return []
            data = json.loads(res.stdout)
        except Exception:
            return []

        nodes = []
        # Add Self
        self_node = data.get("Self", {})
        if self_node:
            ips = self_node.get("TailscaleIPs", [])
            ipv4 = next((ip for ip in ips if "." in ip), "")
            nodes.append({
                "hostname": self_node.get("HostName", "").lower(),
                "display_name": self_node.get("HostName", ""),
                "dns_name": self_node.get("DNSName", "").rstrip("."),
                "ip": ipv4,
                "os": self_node.get("OS", "").lower(),
                "online": True,
                "is_self": True,
                "last_seen": "active"
            })

        # Add Peers
        peers = data.get("Peer", {})
        for peer_id, peer in peers.items():
            ips = peer.get("TailscaleIPs", [])
            ipv4 = next((ip for ip in ips if "." in ip), "")
            nodes.append({
                "hostname": peer.get("HostName", "").lower(),
                "display_name": peer.get("HostName", ""),
                "dns_name": peer.get("DNSName", "").rstrip("."),
                "ip": ipv4,
                "os": peer.get("OS", "").lower(),
                "online": peer.get("Online", False),
                "is_self": False,
                "last_seen": peer.get("LastSeen", "")
            })

        return nodes

    def get_local_podman_containers(self) -> List[Dict[str, Any]]:
        """Queries Podman containers running on the local host (or WSL)."""
        containers = []

        # Try host podman first, then WSL podman fallback
        commands = [
            ["podman", "ps", "-a", "--format", "json"],
            ["wsl", "podman", "ps", "-a", "--format", "json"]
        ]

        raw_output = None
        for cmd in commands:
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
                if res.returncode == 0 and res.stdout.strip():
                    raw_output = res.stdout
                    break
            except Exception:
                continue

        if not raw_output:
            return []

        try:
            raw = json.loads(raw_output)
            for c in raw:
                names = c.get("Names", [])
                name = names[0] if names else c.get("Id", "")[:12]
                image = c.get("Image", "")
                state = c.get("State", "").lower()
                status = c.get("Status", "")

                # Categorize agent
                agent_type = "unknown"
                if "hermes-music" in image or "hermes" in image or "sp2" in name:
                    agent_type = "hermes-agent"
                elif "dawagent" in image or "dawagent" in name:
                    agent_type = "dawagent"
                elif "openclaw" in image or "mcclaw" in image:
                    agent_type = "openclaw"

                # Parse ports
                ports = []
                for p in c.get("Ports") or []:
                    h_port = p.get("host_port")
                    c_port = p.get("container_port")
                    proto = p.get("protocol", "tcp")
                    if h_port:
                        ports.append(f"{h_port}->{c_port}/{proto}")
                    elif c_port:
                        ports.append(f"{c_port}/{proto}")

                containers.append({
                    "container_id": c.get("Id", "")[:12],
                    "name": name,
                    "image": image,
                    "agent_type": agent_type,
                    "state": state,
                    "status": status,
                    "ports": ports,
                    "is_agent": agent_type in ("hermes-agent", "openclaw", "dawagent"),
                    "engine": "podman",
                    "host_node": "local"
                })
        except Exception:
            pass

        return containers

    def probe_port(self, ip: str, port: int, timeout: float = 0.5) -> bool:
        """Check if a TCP port is open on target IP."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                return s.connect_ex((ip, port)) == 0
        except Exception:
            return False

    def probe_service_details(self, ip: str, port: int) -> Dict[str, Any]:
        """Probes an open port for A2A or agent gateway fingerprints."""
        url = f"http://{ip}:{port}"
        details = {"port": port, "service": "unknown", "agent_type": "unknown", "agent_card": None}

        # Check A2A Agent Card
        try:
            card_url = f"{url}/.well-known/agent-card.json"
            req = urllib.request.Request(card_url, headers={"User-Agent": "A2A-Scanner/1.0"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    card = json.loads(resp.read().decode("utf-8"))
                    details["service"] = "a2a-server"
                    details["agent_type"] = "a2a-agent"
                    details["agent_card"] = card
                    details["name"] = card.get("name", "remote-a2a-agent")
                    return details
        except Exception:
            pass

        # Check /health or /status
        try:
            health_url = f"{url}/health"
            req = urllib.request.Request(health_url, headers={"User-Agent": "A2A-Scanner/1.0"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode("utf-8"))
                    details["service"] = body.get("agent", "health-service")
                    details["details"] = body
                    return details
        except Exception:
            pass

        # Port-based heuristics
        if port == 8080:
            details["service"] = "a2a-server"
        elif port in (18789, 18880):
            details["service"] = "openclaw-gateway"
            details["agent_type"] = "openclaw"
        elif port in (8642, 8644, 18812, 18813):
            details["service"] = "hermes-gateway"
            details["agent_type"] = "hermes-agent"

        return details

    def probe_node_ports(self, ip: str) -> List[Dict[str, Any]]:
        """Probe all candidate ports on a single node concurrently."""
        open_services = []

        def check_port(port):
            if self.probe_port(ip, port, timeout=0.4):
                return self.probe_service_details(ip, port)
            return None

        with ThreadPoolExecutor(max_workers=len(self.probe_ports)) as ex:
            results = ex.map(check_port, self.probe_ports)
            for res in results:
                if res:
                    open_services.append(res)
        return open_services

    def scan_fleet(self, probe_remote: bool = True) -> Dict[str, Any]:
        """
        Runs comprehensive discovery:
        1. Tailscale node status
        2. Podman containers on local host
        3. Fast parallel port probing for remote Hermes/OpenClaw/A2A endpoints
        """
        nodes = self.get_tailscale_nodes()
        local_containers = self.get_local_podman_containers()

        def process_node(node):
            hostname = node["hostname"]
            ip = node["ip"]
            online = node["online"]
            is_self = node.get("is_self", False)

            node_containers = []
            node_services = []

            # Assign local containers to self / local node
            if is_self or "wsl" in hostname or "local" in hostname:
                node_containers.extend(local_containers)

            # Fast parallel port probe
            if online and ip and probe_remote:
                node_services = self.probe_node_ports(ip)

            node["containers"] = node_containers
            node["services"] = node_services
            node["agent_count"] = len([c for c in node_containers if c.get("is_agent")]) + len(node_services)
            return node

        with ThreadPoolExecutor(max_workers=10) as executor:
            enriched_nodes = list(executor.map(process_node, nodes))

        return {
            "node_count": len(enriched_nodes),
            "online_count": len([n for n in enriched_nodes if n["online"]]),
            "nodes": enriched_nodes
        }


if __name__ == "__main__":
    scanner = FleetScanner()
    res = scanner.scan_fleet(probe_remote=False)
    print(f"Discovered {res['node_count']} nodes ({res['online_count']} online)")
    for n in res["nodes"]:
        if n["containers"] or n["services"]:
            print(f"[{n['hostname']}] IP: {n['ip']} - Containers: {len(n['containers'])}, Services: {len(n['services'])}")
