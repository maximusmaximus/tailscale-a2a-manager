"""
A2A Mesh Switch & Routing Controller.
Provides an ON/OFF switch per machine/container to manage A2A inter-agent communication across Tailscale.
"""

import os
import json
import time
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent / "mesh_state.json"
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


class MeshSwitchManager:
    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or STATE_PATH
        self.config = load_config()
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        # Generic default state structure
        default_state = {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "nodes": {},
            "activity_log": []
        }
        self._save_state(default_state)
        return default_state

    def _save_state(self, state: Optional[Dict[str, Any]] = None):
        if state is not None:
            self.state = state
        self.state["last_updated"] = datetime.now().isoformat()
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def sync_fleet(self, fleet_data: Dict[str, Any]) -> Dict[str, Any]:
        """Merges scanned Tailscale & Podman machines into the mesh registry."""
        nodes = fleet_data.get("nodes", [])
        added = []
        updated = []

        for n in nodes:
            hostname = n.get("hostname", "").lower()
            ip = n.get("ip", "")
            if not hostname or not ip:
                continue

            containers = [c.get("name") for c in n.get("containers", [])]
            services = n.get("services", [])
            is_self = n.get("is_self", False)
            agent_status = n.get("agent_status", {})
            hermes_running = n.get("hermes_running", False)
            openclaw_running = n.get("openclaw_running", False)
            dawagent_running = n.get("dawagent_running", False)

            if hostname not in self.state["nodes"]:
                # Enable self by default, others require explicit toggle
                self.state["nodes"][hostname] = {
                    "hostname": hostname,
                    "display_name": n.get("display_name", hostname),
                    "ip": ip,
                    "os": n.get("os", "unknown"),
                    "online": n.get("online", False),
                    "a2a_enabled": is_self,
                    "endpoint": f"http://{ip}:8080/a2a/v1/message",
                    "port": 8080,
                    "agent_type": "hermes-podman" if containers else "node",
                    "containers": containers,
                    "services": services,
                    "agent_status": agent_status,
                    "hermes_running": hermes_running,
                    "openclaw_running": openclaw_running,
                    "dawagent_running": dawagent_running,
                    "last_seen": n.get("last_seen", ""),
                    "last_toggled": datetime.now().isoformat()
                }
                added.append(hostname)
            else:
                existing = self.state["nodes"][hostname]
                existing["ip"] = ip
                existing["online"] = n.get("online", False)
                existing["containers"] = containers
                existing["services"] = services
                existing["agent_status"] = agent_status
                existing["hermes_running"] = hermes_running
                existing["openclaw_running"] = openclaw_running
                existing["dawagent_running"] = dawagent_running
                existing["last_seen"] = n.get("last_seen", "")
                updated.append(hostname)

        self._save_state()
        return {"added": added, "updated": updated, "total_registered": len(self.state["nodes"])}

    def toggle_switch(self, target: str, enable: bool) -> Dict[str, Any]:
        """Turns the A2A communication switch ON or OFF for a machine or container."""
        target_lower = target.strip().lower()
        matched_node = None

        # Match by hostname, IP, or container name
        for h, n in self.state["nodes"].items():
            if h == target_lower or n.get("ip") == target_lower or target_lower in [c.lower() for c in n.get("containers", [])]:
                matched_node = n
                break

        if not matched_node:
            return {
                "success": False,
                "error": f"Target '{target}' not found in registered Tailscale fleet. Run fleet scan first."
            }

        prev_state = matched_node.get("a2a_enabled", False)
        matched_node["a2a_enabled"] = bool(enable)
        matched_node["last_toggled"] = datetime.now().isoformat()

        # Log toggle event
        event = {
            "timestamp": datetime.now().isoformat(),
            "target": matched_node["hostname"],
            "action": "ENABLED" if enable else "DISABLED",
            "previous_state": prev_state
        }
        self.state.setdefault("activity_log", []).append(event)
        self.state["activity_log"] = self.state["activity_log"][-50:]
        self._save_state()

        return {
            "success": True,
            "target": matched_node["hostname"],
            "ip": matched_node["ip"],
            "a2a_enabled": matched_node["a2a_enabled"],
            "status": "A2A Communication ON" if enable else "A2A Communication OFF",
            "containers": matched_node.get("containers", [])
        }

    def list_mesh_status(self) -> Dict[str, Any]:
        """Returns overview of enabled and disabled nodes in the A2A mesh."""
        enabled = []
        disabled = []

        for h, n in self.state["nodes"].items():
            summary = {
                "hostname": h,
                "ip": n.get("ip"),
                "online": n.get("online", False),
                "a2a_enabled": n.get("a2a_enabled", False),
                "containers": n.get("containers", []),
                "services": n.get("services", []),
                "agent_status": n.get("agent_status", {}),
                "hermes_running": n.get("hermes_running", False),
                "openclaw_running": n.get("openclaw_running", False),
                "dawagent_running": n.get("dawagent_running", False),
                "endpoint": n.get("endpoint")
            }
            if n.get("a2a_enabled"):
                enabled.append(summary)
            else:
                disabled.append(summary)

        nodes_val = list(self.state["nodes"].values())
        return {
            "total_nodes": len(self.state["nodes"]),
            "enabled_count": len(enabled),
            "disabled_count": len(disabled),
            "hermes_running_count": sum(1 for n in nodes_val if n.get("hermes_running")),
            "openclaw_running_count": sum(1 for n in nodes_val if n.get("openclaw_running")),
            "dawagent_running_count": sum(1 for n in nodes_val if n.get("dawagent_running")),
            "enabled_nodes": enabled,
            "disabled_nodes": disabled
        }

    def send_a2a_message(self, target: str, message: str, sender: str = "controller") -> Dict[str, Any]:
        """Dispatches an A2A message to a target if its switch is ON."""
        target_lower = target.strip().lower()
        node = None
        for h, n in self.state["nodes"].items():
            if h == target_lower or n.get("ip") == target_lower or target_lower in [c.lower() for c in n.get("containers", [])]:
                node = n
                break

        if not node:
            return {"success": False, "error": f"Node '{target}' not found."}

        if not node.get("a2a_enabled"):
            return {
                "success": False,
                "error": f"Node '{node['hostname']}' has its A2A communication switch turned OFF. Enable it first using a2a_toggle_node."
            }

        endpoint = node.get("endpoint", f"http://{node['ip']}:8080/a2a/v1/message")
        auth_token = os.environ.get("A2A_AUTH_TOKEN") or node.get("auth_token") or self.config.get("a2a", {}).get("local_auth_token", "")

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "A2A-MeshController/1.0"
        }
        if auth_token and not auth_token.startswith("your-"):
            headers["Authorization"] = f"Bearer {auth_token}"

        payload = {
            "message": message,
            "sender": sender,
            "target": node["hostname"],
            "timestamp": datetime.now().isoformat()
        }

        req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers)
        start_time = time.time()
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                latency_ms = int((time.time() - start_time) * 1000)
                return {
                    "success": True,
                    "target": node["hostname"],
                    "endpoint": endpoint,
                    "latency_ms": latency_ms,
                    "response": resp_data
                }
        except urllib.error.HTTPError as he:
            return {"success": False, "status_code": he.code, "error": he.read().decode("utf-8")}
        except Exception as e:
            return {"success": False, "error": str(e), "endpoint": endpoint}


if __name__ == "__main__":
    mgr = MeshSwitchManager()
    status = mgr.list_mesh_status()
    print(f"Mesh Status: {status['enabled_count']} enabled, {status['disabled_count']} disabled")
