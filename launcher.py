"""
A2A Swarm Services Supervisor & Auto-starter.
Checks if A2A Node Server (:8080) and Web Dashboard (:8670) are active.
If either service is stopped, starts it in the background. Idempotent and safe to run on boot.
"""

import os
import sys
import socket
import subprocess
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
A2A_SERVER_DIR = BASE_DIR.parent / "a2a-server"
MANAGER_DIR = BASE_DIR


def is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def is_port_listening(port: int) -> bool:
    if is_port_open(port, "127.0.0.1"):
        return True
    try:
        res = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0 and res.stdout.strip():
            ts_ip = res.stdout.strip()
            if is_port_open(port, ts_ip):
                return True
    except Exception:
        pass
    return False


def ensure_services():
    python_exe = sys.executable
    no_window = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW

    # 1. Check A2A Server (port 8080)
    if not is_port_listening(8080):
        server_py = A2A_SERVER_DIR / "server.py"
        if server_py.exists():
            print(f"[Launcher] Starting A2A Node Server (port 8080)...")
            subprocess.Popen([python_exe, str(server_py)], cwd=str(A2A_SERVER_DIR), creationflags=no_window)
        else:
            print(f"[Launcher] Warning: {server_py} not found.")
    else:
        print("[Launcher] A2A Node Server (port 8080) is already running.")

    # 2. Check Web Dashboard (port 8670)
    if not is_port_listening(8670):
        web_server_py = MANAGER_DIR / "web_server.py"
        if web_server_py.exists():
            print(f"[Launcher] Starting A2A Web Dashboard (port 8670)...")
            subprocess.Popen([python_exe, str(web_server_py)], cwd=str(MANAGER_DIR), creationflags=no_window)
        else:
            print(f"[Launcher] Warning: {web_server_py} not found.")
    else:
        print("[Launcher] A2A Web Dashboard (port 8670) is already running.")

    # 3. Check Venice Key Manager (port 8844)
    VENICE_DIR = BASE_DIR.parent / "venice-key-manager"
    if not is_port_listening(8844):
        supervisor_py = VENICE_DIR / "supervisor.py"
        if supervisor_py.exists():
            print("[Launcher] Starting Venice Key Manager Supervisor (port 8844)...")
            subprocess.Popen([python_exe, str(supervisor_py), "--run"], cwd=str(VENICE_DIR), creationflags=no_window)
        else:
            print(f"[Launcher] Warning: {supervisor_py} not found.")
    else:
        print("[Launcher] Venice Key Manager (port 8844) is already running.")


if __name__ == "__main__":
    ensure_services()
