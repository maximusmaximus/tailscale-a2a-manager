"""
Web Dashboard Server for Tailscale A2A Swarm Manager.
Provides an interactive, real-time browser interface and REST API
exposing all MCP capabilities: fleet scanning, container inspection,
A2A communication switches, message dispatching, and Hermes-Agent Low reasoning.
"""

import os
import sys
import json
import time
import secrets
import logging
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fleet_scanner import FleetScanner
from mesh_switch import MeshSwitchManager
from hermes_low import HermesLowAgent

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("a2a_web")

CONFIG_PATH = PROJECT_ROOT / "config.json"
ENV_PATH = PROJECT_ROOT / ".env"
WEB_DIR = PROJECT_ROOT / "web"


def load_env_file():
    """Lightweight .env loader (zero external dependencies)."""
    if ENV_PATH.exists():
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("\"'").strip()
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception as e:
            logger.warning(f"Error loading .env: {e}")


load_env_file()


def load_config() -> dict:
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    return cfg


class WebDashboardHandler(BaseHTTPRequestHandler):
    server_version = "Tailscale-A2A-Web/1.0.0"

    def log_message(self, format, *args):
        logger.info(f"[{self.client_address[0]}] {format % args}")

    def send_json(self, status_code: int, data: dict, headers: dict = None):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Passcode")
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Passcode")
        self.end_headers()

    def _read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        try:
            raw = self.rfile.read(content_length)
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _is_authenticated(self) -> bool:
        # Check Authorization Bearer token
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token in self.server.active_sessions:
                if time.time() < self.server.active_sessions[token]:
                    return True
                else:
                    del self.server.active_sessions[token]

        # Check X-Passcode header
        passcode_header = self.headers.get("X-Passcode", "").strip()
        if passcode_header and passcode_header == self.server.passcode:
            return True

        return False

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Static Web UI (index.html)
        if path in ("/", "/index.html"):
            index_path = WEB_DIR / "index.html"
            if index_path.exists():
                try:
                    with open(index_path, "r", encoding="utf-8") as f:
                        content = f.read().encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception as e:
                    self.send_error(500, f"Error reading index.html: {e}")
                    return
            else:
                self.send_error(404, "Web interface file not found")
                return

        # API: Public status check
        if path == "/api/status":
            self.send_json(200, {
                "status": "online",
                "service": "tailscale-a2a-manager",
                "uptime_seconds": round(time.time() - self.server.start_time, 1),
                "auth_required": True,
                "timestamp": datetime.now().isoformat()
            })
            return

        # Protected API Endpoints
        if not self._is_authenticated():
            self.send_json(401, {
                "error": "Unauthorized",
                "message": "Valid passcode or session token required."
            })
            return

        if path == "/api/fleet":
            fleet = self.server.scanner.scan_fleet(probe_remote=False)
            self.send_json(200, fleet)

        elif path == "/api/mesh":
            mesh = self.server.mesh_mgr.list_mesh_status()
            self.send_json(200, mesh)

        elif path == "/api/logs":
            logs = self.server.mesh_mgr.state.get("activity_log", [])
            self.send_json(200, {"logs": logs})

        else:
            self.send_json(404, {"error": "Not Found", "path": path})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()

        # Public Auth Endpoint: /api/auth
        if path == "/api/auth":
            passcode = body.get("passcode", "").strip()
            if passcode == self.server.passcode:
                token = secrets.token_hex(16)
                self.server.active_sessions[token] = time.time() + self.server.session_duration
                self.send_json(200, {
                    "success": True,
                    "authenticated": True,
                    "token": token,
                    "expires_in_minutes": int(self.server.session_duration / 60),
                    "message": "Authentication successful"
                })
            else:
                self.send_json(401, {"success": False, "authenticated": False, "error": "Invalid passcode"})
            return

        # Enforce Authentication on all other POST endpoints
        if not self._is_authenticated():
            self.send_json(401, {"error": "Unauthorized", "message": "Authentication required."})
            return

        if path == "/api/scan":
            probe_remote = body.get("probe_remote", True)
            fleet_data = self.server.scanner.scan_fleet(probe_remote=probe_remote)
            sync_res = self.server.mesh_mgr.sync_fleet(fleet_data)
            self.send_json(200, {
                "success": True,
                "fleet": fleet_data,
                "sync": sync_res
            })

        elif path == "/api/toggle":
            target = body.get("target")
            enable = body.get("enable")
            if target is None or enable is None:
                self.send_json(400, {"error": "Missing 'target' or 'enable' in request body."})
                return
            res = self.server.mesh_mgr.toggle_switch(target, enable)
            self.send_json(200, res)

        elif path == "/api/send":
            target = body.get("target")
            message = body.get("message")
            sender = body.get("sender", "web-dashboard")
            if not target or not message:
                self.send_json(400, {"error": "Missing 'target' or 'message' in request body."})
                return
            res = self.server.mesh_mgr.send_a2a_message(target, message, sender=sender)
            self.send_json(200, res)

        elif path == "/api/hermes":
            prompt = body.get("prompt", "")
            include_fleet = body.get("include_fleet_context", True)
            if not prompt:
                self.send_json(400, {"error": "Missing 'prompt' in request body."})
                return
            context = None
            if include_fleet:
                context = {
                    "mesh": self.server.mesh_mgr.list_mesh_status()
                }
            res = self.server.hermes_low.ask(prompt, context=context)
            self.send_json(200, res)

        else:
            self.send_json(404, {"error": "Not Found", "path": path})


class A2AWebServer(ThreadingHTTPServer):
    def __init__(self, server_address, RequestHandlerClass):
        super().__init__(server_address, RequestHandlerClass)
        self.config = load_config()
        self.scanner = FleetScanner(self.config)
        self.mesh_mgr = MeshSwitchManager()
        self.hermes_low = HermesLowAgent(self.config)
        self.passcode = os.environ.get("A2A_MCP_PASSCODE") or self.config.get("security", {}).get("mcp_passcode", "change-this-passcode")
        self.active_sessions: dict = {}
        self.session_duration = self.config.get("security", {}).get("session_expiry_minutes", 60) * 60
        self.start_time = time.time()


def run_web_server(host: str = "0.0.0.0", port: int = 8670):
    host = os.environ.get("A2A_WEB_HOST") or host
    port = int(os.environ.get("A2A_WEB_PORT") or port)

    server = A2AWebServer((host, port), WebDashboardHandler)
    logger.info(f"==================================================")
    logger.info(f" Tailscale A2A Swarm Web Dashboard")
    logger.info(f" Listening on:       http://{host}:{port}")
    logger.info(f" Local Web UI:       http://127.0.0.1:{port}")
    logger.info(f" Auth Protected:     Yes (Passcode Gate)")
    logger.info(f"==================================================")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping Web Dashboard server...")
        server.server_close()


if __name__ == "__main__":
    port_arg = 8670
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port_arg = int(sys.argv[1])
    run_web_server(port=port_arg)
