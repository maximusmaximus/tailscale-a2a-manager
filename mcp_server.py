"""
Tailscale A2A Swarm Manager & Hermes Low MCP Server.
Model Context Protocol (MCP) JSON-RPC 2.0 Server over Stdio.
Enforces passcode-based authentication for controlling Tailscale nodes,
Podman agent inspection, and A2A communication switches.
"""

import os
import sys
import json
import time
import secrets
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fleet_scanner import FleetScanner
from mesh_switch import MeshSwitchManager
from hermes_low import HermesLowAgent

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("a2a_mcp")

CONFIG_PATH = PROJECT_ROOT / "config.json"


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


class A2AMCPServer:
    PROTOCOL_VERSION = "2024-11-05"
    SERVER_NAME = "tailscale-a2a-manager"
    SERVER_VERSION = "1.0.0"

    def __init__(self):
        self.config = load_config()
        self.scanner = FleetScanner(self.config)
        self.mesh_mgr = MeshSwitchManager()
        self.hermes_low = HermesLowAgent(self.config)
        self.passcode = (
            os.environ.get("A2A_MCP_PASSCODE")
            or self.config.get("security", {}).get("mcp_passcode", "change-this-passcode")
        )
        self.active_sessions: Dict[str, float] = {}
        self.session_duration = self.config.get("security", {}).get("session_expiry_minutes", 60) * 60
        self.default_session_authenticated = False

    def _is_authenticated(self, args: Dict[str, Any]) -> bool:
        if self.default_session_authenticated:
            return True

        supplied_passcode = args.get("passcode")
        if supplied_passcode and supplied_passcode == self.passcode:
            return True

        token = args.get("session_token")
        if token and token in self.active_sessions:
            if time.time() < self.active_sessions[token]:
                return True
            else:
                del self.active_sessions[token]

        return False

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "a2a_auth",
                "description": "Authenticate user session with the required passcode to unlock A2A mesh controls and fleet operations.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "passcode": {
                            "type": "string",
                            "description": "The security passcode configured for the A2A fleet manager."
                        }
                    },
                    "required": ["passcode"]
                }
            },
            {
                "name": "tailscale_scan_fleet",
                "description": "Scans the Tailscale network and inspects Podman/Docker containers to discover nodes running Hermes or OpenClaw agents. Syncs them with the A2A mesh switch.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "passcode": {
                            "type": "string",
                            "description": "Optional passcode if not previously authenticated."
                        },
                        "probe_remote_ports": {
                            "type": "boolean",
                            "description": "Whether to perform network port probing on remote Tailscale peers (default: true)."
                        }
                    }
                }
            },
            {
                "name": "a2a_toggle_switch",
                "description": "Turns the A2A communication switch ON or OFF for a machine, IP, or Podman container. Enabled nodes can exchange messages and tasks.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Machine hostname or container name."
                        },
                        "enable": {
                            "type": "boolean",
                            "description": "True to turn A2A communication ON, False to turn OFF."
                        },
                        "passcode": {
                            "type": "string",
                            "description": "Optional passcode if not previously authenticated."
                        }
                    },
                    "required": ["target", "enable"]
                }
            },
            {
                "name": "a2a_get_mesh_status",
                "description": "Lists all registered Tailscale machines and containers, showing their A2A communication switch state (ON/OFF), IP, and agent status.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "passcode": {
                            "type": "string",
                            "description": "Optional passcode if not previously authenticated."
                        }
                    }
                }
            },
            {
                "name": "a2a_send_message",
                "description": "Sends an A2A message or task to an enabled node on Tailscale. Fails if the target's switch is turned OFF.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Target machine hostname or container name."
                        },
                        "message": {
                            "type": "string",
                            "description": "The task prompt or payload to dispatch via A2A."
                        },
                        "sender": {
                            "type": "string",
                            "description": "Optional sender name (default: 'mcp-controller')."
                        },
                        "passcode": {
                            "type": "string",
                            "description": "Optional passcode if not previously authenticated."
                        }
                    },
                    "required": ["target", "message"]
                }
            },
            {
                "name": "hermes_low_ask",
                "description": "Queries the Hermes-Agent Low tier model (powered by Venice Key Manager) for rapid multi-agent fleet analysis or task formulation.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "Instruction or question for Hermes-Agent Low."
                        },
                        "include_fleet_context": {
                            "type": "boolean",
                            "description": "Whether to inject live Tailscale fleet and A2A switch status into the prompt context (default: true)."
                        },
                        "passcode": {
                            "type": "string",
                            "description": "Optional passcode if not previously authenticated."
                        }
                    },
                    "required": ["prompt"]
                }
            },
            {
                "name": "a2a_change_passcode",
                "description": "Updates the security passcode for the A2A Fleet Manager. Requires currently valid passcode.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "old_passcode": {
                            "type": "string",
                            "description": "The current valid passcode."
                        },
                        "new_passcode": {
                            "type": "string",
                            "description": "The new passcode to set."
                        }
                    },
                    "required": ["old_passcode", "new_passcode"]
                }
            }
        ]

    def execute_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if name == "a2a_auth":
            passcode = args.get("passcode", "")
            if passcode == self.passcode:
                token = secrets.token_hex(16)
                self.active_sessions[token] = time.time() + self.session_duration
                self.default_session_authenticated = True
                return {
                    "success": True,
                    "authenticated": True,
                    "session_token": token,
                    "expires_in_minutes": int(self.session_duration / 60),
                    "message": "Authentication successful. Access granted to A2A mesh controls and fleet operations."
                }
            return {
                "success": False,
                "authenticated": False,
                "error": "Invalid passcode."
            }

        if name == "a2a_change_passcode":
            old_p = args.get("old_passcode", "")
            new_p = args.get("new_passcode", "")
            if old_p != self.passcode:
                return {"success": False, "error": "Current passcode is incorrect."}
            if not new_p or len(new_p) < 4:
                return {"success": False, "error": "New passcode must be at least 4 characters long."}

            self.passcode = new_p
            self.config.setdefault("security", {})["mcp_passcode"] = new_p
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
            return {"success": True, "message": "Passcode updated successfully."}

        if not self._is_authenticated(args):
            return {
                "success": False,
                "error": "Unauthorized",
                "message": (
                    "Authentication required. Call 'a2a_auth' with the valid passcode, "
                    "or include 'passcode': '<secret>' with this request."
                )
            }

        if name == "tailscale_scan_fleet":
            probe_remote = args.get("probe_remote_ports", True)
            fleet_data = self.scanner.scan_fleet(probe_remote=probe_remote)
            sync_res = self.mesh_mgr.sync_fleet(fleet_data)
            return {
                "success": True,
                "fleet_summary": {
                    "node_count": fleet_data.get("node_count"),
                    "online_count": fleet_data.get("online_count"),
                    "mesh_synced": sync_res
                },
                "nodes": fleet_data.get("nodes")
            }

        elif name == "a2a_toggle_switch":
            target = args.get("target")
            enable = args.get("enable")
            return self.mesh_mgr.toggle_switch(target, enable)

        elif name == "a2a_get_mesh_status":
            return {
                "success": True,
                "mesh": self.mesh_mgr.list_mesh_status()
            }

        elif name == "a2a_send_message":
            target = args.get("target")
            message = args.get("message")
            sender = args.get("sender", "mcp-controller")
            return self.mesh_mgr.send_a2a_message(target, message, sender=sender)

        elif name == "hermes_low_ask":
            prompt = args.get("prompt")
            include_ctx = args.get("include_fleet_context", True)
            context = None
            if include_ctx:
                context = {
                    "mesh": self.mesh_mgr.list_mesh_status()
                }
            return self.hermes_low.ask(prompt, context=context)

        return {"error": f"Unknown tool: {name}"}

    def handle_request(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": self.SERVER_NAME,
                        "version": self.SERVER_VERSION
                    }
                }
            }

        elif method == "notifications/initialized":
            return None

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": self.get_tool_definitions()
                }
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})
            try:
                result = self.execute_tool(tool_name, args)
                is_error = "error" in result and not result.get("success", True)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, indent=2)
                            }
                        ],
                        "isError": is_error
                    }
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                        "isError": True
                    }
                }

        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method '{method}' not found"}
            }

    def run_stdio(self):
        logger.info("Tailscale A2A Swarm Manager MCP Server started (Stdio transport).")
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                resp = self.handle_request(req)
                if resp is not None:
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
            except json.JSONDecodeError:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"}
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()
            except Exception as e:
                logger.error(f"Error in server loop: {e}")


if __name__ == "__main__":
    server = A2AMCPServer()
    server.run_stdio()
