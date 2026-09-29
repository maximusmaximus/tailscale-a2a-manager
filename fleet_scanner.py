"""
Fleet Scanner for Tailscale & Podman Agent Discovery.
Discovers Tailscale nodes and identifies Podman/Docker containers running Hermes or OpenClaw agents.
Provides per-device agent status (RUNNING, STOPPED, NOT_DETECTED, OFFLINE).
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
            "probe_ports", [8080, 8650, 18789, 18880, 18790, 18812, 18813, 8642, 8644]
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

                # Categorize agent: Check dawagent first to prevent dawagent images from being misclassified
                agent_type = "unknown"
                if "dawagent" in image or "dawagent" in name:
                    agent_type = "dawagent"
                elif "hermes-music" in image or "hermes" in image or "sp2" in name:
                    agent_type = "hermes-agent"
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

    def probe_port(self, ip: str, port: int, timeout: float = 0.35) -> bool:
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

        # Check Hermes Fleet Controller on port 8650 or HTTP endpoints
        if port == 8650 or port in (8080, 8642, 8644, 18812, 18813, 18789, 18880):
            try:
                req = urllib.request.Request(f"{url}/", headers={"User-Agent": "A2A-Scanner/1.0"})
                with urllib.request.urlopen(req, timeout=0.8) as resp:
                    body_snippet = resp.read(2048).decode("utf-8", errors="replace")
                    if "Hermes Fleet Controller" in body_snippet or "hermes" in body_snippet.lower():
                        details["service"] = "hermes-fleet-controller"
                        details["agent_type"] = "hermes-agent"
                        details["name"] = "Hermes Fleet Controller"
                        return details
            except urllib.error.HTTPError as e:
                try:
                    body_snippet = e.read(2048).decode("utf-8", errors="replace")
                    if "Hermes Fleet Controller" in body_snippet or "hermes" in body_snippet.lower():
                        details["service"] = "hermes-fleet-controller"
                        details["agent_type"] = "hermes-agent"
                        details["name"] = "Hermes Fleet Controller"
                        return details
                except Exception:
                    pass
            except Exception:
                pass

        # Check A2A Agent Card
        try:
            card_url = f"{url}/.well-known/agent-card.json"
            req = urllib.request.Request(card_url, headers={"User-Agent": "A2A-Scanner/1.0"})
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                if resp.status == 200:
                    card = json.loads(resp.read().decode("utf-8"))
                    details["service"] = "a2a-server"
                    details["agent_type"] = "a2a-agent"
                    details["agent_card"] = card
                    details["name"] = card.get("name", "remote-a2a-agent")
                    return details
        except Exception:
            pass

        # Check /health endpoint
        try:
            health_url = f"{url}/health"
            req = urllib.request.Request(health_url, headers={"User-Agent": "A2A-Scanner/1.0"})
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode("utf-8"))
                    details["service"] = body.get("agent", "health-service")
                    details["details"] = body
                    if "rocketmq" in body or body.get("status") == "up":
                        details["agent_type"] = "a2a-agent"
                    return details
        except Exception:
            pass

        # Heuristics based on confirmed ports
        if port == 8650:
            details["service"] = "hermes-fleet-controller"
            details["agent_type"] = "hermes-agent"
        elif port == 8080:
            details["service"] = "a2a-server"
        elif port in (18789, 18880, 18790):
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
            if self.probe_port(ip, port, timeout=0.35):
                return self.probe_service_details(ip, port)
            return None

        with ThreadPoolExecutor(max_workers=len(self.probe_ports)) as ex:
            results = ex.map(check_port, self.probe_ports)
            for res in results:
                if res:
                    open_services.append(res)
        return open_services

    def determine_agent_status(self, node: Dict[str, Any], containers: List[Dict[str, Any]], services: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Determines the exact RUNNING / STOPPED / NOT_DETECTED status
        for Hermes, OpenClaw, and DAWAgent on a specific device.
        """
        online = node.get("online", False)
        hostname = node.get("hostname", "").lower()

        # 1. Hermes Agent Status
        hermes_info = {
            "running": False,
            "status": "NOT_DETECTED",
            "source": "none",
            "details": "No Hermes service detected"
        }
        hermes_containers = [c for c in containers if c.get("agent_type") == "hermes-agent"]
        running_hermes_c = [c for c in hermes_containers if c.get("state") == "running"]
        if running_hermes_c:
            c = running_hermes_c[0]
            hermes_info["running"] = True
            hermes_info["status"] = "RUNNING"
            hermes_info["source"] = "container"
            hermes_info["details"] = f"Podman container '{c['name']}' ({c.get('status', 'running')})"
        elif hermes_containers:
            c = hermes_containers[0]
            hermes_info["running"] = False
            hermes_info["status"] = "STOPPED"
            hermes_info["source"] = "container"
            hermes_info["details"] = f"Podman container '{c['name']}' stopped ({c.get('status', 'exited')})"
        else:
            hermes_services = [s for s in services if s.get("agent_type") == "hermes-agent" or "hermes" in s.get("service", "").lower()]
            if hermes_services:
                s = hermes_services[0]
                hermes_info["running"] = True
                hermes_info["status"] = "RUNNING"
                hermes_info["source"] = "service"
                svc_title = "Hermes Fleet Controller" if s.get("port") == 8650 else s.get("service", "Hermes Service")
                hermes_info["details"] = f"{svc_title} active on port {s.get('port')}"
            elif not online:
                hermes_info["status"] = "OFFLINE"
                hermes_info["details"] = "Device offline"

        # 2. OpenClaw Agent Status
        openclaw_info = {
            "running": False,
            "status": "NOT_DETECTED",
            "source": "none",
            "details": "No OpenClaw service detected"
        }
        openclaw_containers = [c for c in containers if c.get("agent_type") == "openclaw"]
        running_oc_c = [c for c in openclaw_containers if c.get("state") == "running"]
        if running_oc_c:
            c = running_oc_c[0]
            openclaw_info["running"] = True
            openclaw_info["status"] = "RUNNING"
            openclaw_info["source"] = "container"
            openclaw_info["details"] = f"Container '{c['name']}' ({c.get('status', 'running')})"
        elif openclaw_containers:
            c = openclaw_containers[0]
            openclaw_info["running"] = False
            openclaw_info["status"] = "STOPPED"
            openclaw_info["source"] = "container"
            openclaw_info["details"] = f"Container '{c['name']}' stopped"
        else:
            oc_services = [s for s in services if s.get("agent_type") == "openclaw" or "openclaw" in s.get("service", "").lower()]
            if oc_services:
                s = oc_services[0]
                openclaw_info["running"] = True
                openclaw_info["status"] = "RUNNING"
                openclaw_info["source"] = "service"
                openclaw_info["details"] = f"OpenClaw Gateway active on port {s.get('port')}"
            elif "mcclaw" in hostname or "openclaw" in hostname:
                if online:
                    openclaw_info["running"] = True
                    openclaw_info["status"] = "RUNNING"
                    openclaw_info["source"] = "node_role"
                    openclaw_info["details"] = "OpenClaw agent host active on Tailscale"
                else:
                    openclaw_info["running"] = False
                    openclaw_info["status"] = "OFFLINE"
                    openclaw_info["details"] = "OpenClaw host offline"
            elif not online:
                openclaw_info["status"] = "OFFLINE"
                openclaw_info["details"] = "Device offline"

        # 3. DAWAgent Status
        dawagent_info = {
            "running": False,
            "status": "NOT_DETECTED",
            "source": "none",
            "details": "No DAWAgent detected"
        }
        daw_containers = [c for c in containers if c.get("agent_type") == "dawagent"]
        running_daw_c = [c for c in daw_containers if c.get("state") == "running"]
        if running_daw_c:
            c = running_daw_c[0]
            dawagent_info["running"] = True
            dawagent_info["status"] = "RUNNING"
            dawagent_info["source"] = "container"
            dawagent_info["details"] = f"Podman container '{c['name']}' ({c.get('status', 'running')})"
        elif daw_containers:
            c = daw_containers[0]
            dawagent_info["running"] = False
            dawagent_info["status"] = "STOPPED"
            dawagent_info["source"] = "container"
            dawagent_info["details"] = f"Podman container '{c['name']}' stopped"
        elif not online:
            dawagent_info["status"] = "OFFLINE"
            dawagent_info["details"] = "Device offline"

        return {
            "hermes": hermes_info,
            "openclaw": openclaw_info,
            "dawagent": dawagent_info
        }

    def scan_fleet(self, probe_remote: bool = True) -> Dict[str, Any]:
        """
        Runs comprehensive discovery:
        1. Tailscale node status
        2. Podman containers on local host
        3. Fast parallel port probing for remote Hermes/OpenClaw/A2A endpoints
        4. Structured agent status classification per node
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

            agent_status = self.determine_agent_status(node, node_containers, node_services)

            node["containers"] = node_containers
            node["services"] = node_services
            node["agent_status"] = agent_status
            node["hermes_running"] = agent_status["hermes"]["running"]
            node["openclaw_running"] = agent_status["openclaw"]["running"]
            node["dawagent_running"] = agent_status["dawagent"]["running"]
            node["agent_count"] = (
                (1 if node["hermes_running"] else 0) +
                (1 if node["openclaw_running"] else 0) +
                (1 if node["dawagent_running"] else 0)
            )
            return node

        with ThreadPoolExecutor(max_workers=10) as executor:
            enriched_nodes = list(executor.map(process_node, nodes))

        hermes_running_nodes = sum(1 for n in enriched_nodes if n.get("hermes_running"))
        openclaw_running_nodes = sum(1 for n in enriched_nodes if n.get("openclaw_running"))
        dawagent_running_nodes = sum(1 for n in enriched_nodes if n.get("dawagent_running"))

        return {
            "node_count": len(enriched_nodes),
            "online_count": len([n for n in enriched_nodes if n["online"]]),
            "hermes_running_count": hermes_running_nodes,
            "openclaw_running_count": openclaw_running_nodes,
            "dawagent_running_count": dawagent_running_nodes,
            "nodes": enriched_nodes
        }


if __name__ == "__main__":
    scanner = FleetScanner()
    res = scanner.scan_fleet(probe_remote=True)
    print(f"Discovered {res['node_count']} nodes ({res['online_count']} online)")
    print(f"Summary: Hermes Running: {res['hermes_running_count']} | OpenClaw Running: {res['openclaw_running_count']} | DAWAgent Running: {res['dawagent_running_count']}")
    for n in res["nodes"]:
        astat = n["agent_status"]
        print(f"[{n['hostname']}] Hermes: {astat['hermes']['status']} | OpenClaw: {astat['openclaw']['status']} | DAWAgent: {astat['dawagent']['status']}")
