#!/usr/bin/env bash
# ==============================================================================
# Install A2A Node Auto-start on Linux (systemd user unit)
# Ensures A2A daemon restarts automatically on system boot & Tailscale connection.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMD_DIR="${HOME}/.config/systemd/user"
SERVICE_FILE="${SYSTEMD_DIR}/a2a-node.service"

mkdir -p "${SYSTEMD_DIR}"

cat <<EOF > "${SERVICE_FILE}"
[Unit]
Description=Tailscale A2A Node & Swarm Agent Daemon
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${SCRIPT_DIR}
ExecStart=$(which python3) ${SCRIPT_DIR}/launcher.py
Restart=always
RestartSec=5s
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable a2a-node.service
systemctl --user restart a2a-node.service

echo "[OK] A2A Node systemd service installed and enabled:"
echo "     ${SERVICE_FILE}"
echo "[*] Status check:"
systemctl --user status a2a-node.service --no-pager || true
