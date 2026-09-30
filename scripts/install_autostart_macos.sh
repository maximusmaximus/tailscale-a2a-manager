#!/usr/bin/env bash
# ==============================================================================
# Install A2A Node Auto-start on macOS (launchd Agent)
# Ensures A2A daemon restarts automatically on system boot & user login.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCH_DIR="${HOME}/Library/LaunchAgents"
PLIST_FILE="${LAUNCH_DIR}/com.antigravity.a2a.plist"

mkdir -p "${LAUNCH_DIR}"

PYTHON_BIN=$(which python3 || echo "/usr/bin/python3")

cat <<EOF > "${PLIST_FILE}"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.antigravity.a2a</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>${SCRIPT_DIR}/launcher.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>
    <key>StandardOutPath</key>
    <string>${HOME}/Library/Logs/a2a-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${HOME}/Library/Logs/a2a-stderr.log</string>
</dict>
</plist>
EOF

launchctl unload "${PLIST_FILE}" 2>/dev/null || true
launchctl load "${PLIST_FILE}"

echo "[OK] A2A Node launchd service installed and loaded:"
echo "     ${PLIST_FILE}"
