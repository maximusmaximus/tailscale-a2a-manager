@echo off
cd /d "%~dp0"
echo Starting Tailscale A2A Swarm Web Dashboard...
python web_server.py
pause
