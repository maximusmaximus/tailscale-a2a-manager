# Tailscale A2A Swarm Manager & Hermes Low

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![MCP Protocol](https://img.shields.io/badge/MCP-2024--11--05-green.svg)](https://modelcontextprotocol.io/)
[![Tailscale](https://img.shields.io/badge/Mesh-Tailscale-blue.svg)](https://tailscale.com/)

A centralized control plane and Model Context Protocol (MCP) server that links your Tailscale mesh network with local and remote Podman containers running **Hermes-Agent** and **OpenClaw** agents.

Powered by **Hermes-Agent Low tier** via [Venice.ai](https://venice.ai) and the Venice Key Manager.

---

## 🚀 Key Capabilities

1. **Tailscale & Agent Discovery**:
   - Queries `tailscale status` to inventory all nodes across the mesh (IPs, MagicDNS, OS, online states).
   - Real-time detection of **Hermes Agent**, **OpenClaw Agent**, and **DAWAgent** running or stopped on each device.
   - Dual inspection via local container runtimes (Podman / Docker) and fast remote HTTP/TCP port fingerprinting (`:8650`, `:8080`, `:18789`, `:18880`, `:8642`, `:18812`).
2. **A2A Communication Switch (ON / OFF)**:
   - Provides a per-machine / per-agent switchboard to control inter-agent communication.
   - Only nodes with their switch turned **ON** can send or receive messages across the A2A mesh.
3. **Hermes-Agent Low Tier (Venice Key Manager)**:
   - Integrated with Venice Key Manager inference keys.
   - Low-tier model (`deepseek-v4-flash`) for rapid, budget-friendly fleet telemetry analysis, task drafting, and inter-agent coordination.
4. **Passcode-Protected MCP Interface**:
   - Compliant with Model Context Protocol (MCP) JSON-RPC 2.0.
   - Restricts control operations to authenticated users via passcode.
5. **Interactive Browser Dashboard**:
   - Cyber/terminal dark UI running on port `8670` (accessible via localhost and Tailscale IP).
   - Real-time switchboard to flip A2A communication switches ON/OFF with live visual indicators.
   - Live Agent Diagnostics Matrix with quick filters (`All Nodes`, `Hermes Active`, `OpenClaw Active`, `Online Only`).
   - Direct message dispatch console and conversational Hermes-Agent Low terminal.

---

## 🏗️ Architecture

```text
+-----------------------------------------------------------------------------------+
|                           MCP Client (Antigravity / Claude / Cursor)              |
+-----------------------------------------------------------------------------------+
                                         │
                                [Passcode Protected]
                                         ▼
+-----------------------------------------------------------------------------------+
|               Tailscale A2A Swarm Manager (mcp_server.py & web_server.py)         |
+-------------------+-------------------------------+-------------------------------+
                    │                               │                               │
                    ▼                               ▼                               ▼
       [Fleet & Agent Scanner]            [A2A Swarm Switch]         [Hermes-Agent Low Tier]
        fleet_scanner.py                  mesh_switch.py             hermes_low.py
       - Tailscale Status API            - ON/OFF toggle per node   - Venice Key Manager
       - Container Inspection:            - Block/allow messages       Inference Engine
         * hermes-agent (sp2)             - Direct A2A messaging    - Low-latency reasoning
         * openclaw / dawagent                                       (deepseek-v4-flash)
       - Remote port fingerprinting:
         * 8650 (Hermes Controller)
         * 18789/18880 (OpenClaw)
         * 8080 (A2A Node Server)
```

---

## 📦 Quickstart

### 1. Installation

```bash
git clone https://github.com/maximusmaximus/tailscale-a2a-manager.git
cd tailscale-a2a-manager

# Copy environment variables template
cp .env.example .env
```

Edit `.env` or set environment variables:
```bash
# Venice.ai Credentials
VENICE_API_KEY=your-venice-api-key
VENICE_KEY_ID=your-venice-key-id
VENICE_MODEL=deepseek-v4-flash

# Security Passcode
A2A_MCP_PASSCODE=your-secret-passcode
A2A_AUTH_TOKEN=your-a2a-auth-token
```

### 2. Run Tests

```bash
python test_manager.py
```

### 3. Launch Web Dashboard

```bash
# Start on default port 8670 (accessible via localhost and Tailscale IP)
python web_server.py

# Or on Windows via batch launcher:
start_web.bat
```

Open **`http://localhost:8670`** or `http://<tailscale-ip>:8670` in your browser. Enter your passcode to unlock the live switchboard, container inspector, message dispatcher, and Hermes Low terminal.

---

## 🤖 Antigravity Node Onboarding Prompt

To connect and manage another machine running **Google Antigravity** (local or remote across your Tailscale mesh), copy and paste the prompt below into the Antigravity session on that target device.

The agent will autonomously discover its Tailscale networking, configure a secure background A2A listener, inspect running Podman/Docker containers (Hermes Agent, OpenClaw Agent, etc.), verify local firewall rules, and report its connection block:

### 📋 The Prompt to Paste:

```text
I need you to configure yourself as an A2A (Agent2Agent) Node on this machine, exposed exclusively over our Tailscale network so you can be managed, switched, and dispatched tasks via our Tailscale A2A Swarm Manager workflow.

Please execute the following steps autonomously:

1. Tailscale Network Discovery:
   - Run `tailscale ip -4` and `tailscale status` to determine this machine's Tailscale IPv4 address and MagicDNS hostname.
   - Note the exact Tailscale interface or IP.

2. A2A Service Protocol & Listener:
   - Set up or enable your background A2A daemon listening on port 8080.
   - BIND STRICTLY to your discovered Tailscale IPv4 address (e.g., http://100.x.y.z:8080).
   - DO NOT bind to 0.0.0.0 or any public/external interface to ensure zero exposure outside the Tailscale network.

3. Endpoints & Standards:
   - Ensure the following three endpoints are active and responsive:
     * GET /health -> Return JSON 200 OK:
       {"status": "online", "agent": "<your-machine-hostname>", "tailscale_ip": "<your-tailscale-ip>", "port": 8080, "uptime_seconds": ...}
     * GET /.well-known/agent-card.json -> Return an Agent Card JSON declaring:
       - name: "<hostname>-agent"
       - capabilities: e.g. local GPU rendering, audio/DSP pipelines, container management, or Hermes/OpenClaw execution.
       - endpoints: {"message": "/a2a/v1/message"}
     * POST /a2a/v1/message -> Accept incoming task JSON:
       {"message": "<task-description>", "sender": "<sender-id>", "target": "<hostname>"}
       Authenticate requests using a Bearer token.

4. Local Agent & Container Inspection:
   - Check local container engines (Podman or Docker) using `podman ps -a` or `docker ps -a`.
   - Identify if any Hermes-Agent (e.g. `sp2`, `hermes-music`), OpenClaw, or DAWAgent containers are running.
   - Include these discovered containers and their mapped ports in your agent card capabilities.

5. Firewall Security:
   - Verify and ensure your host firewall (Windows Defender Firewall, ufw, or iptables) permits inbound TCP on port 8080 strictly from the Tailscale subnet (100.64.0.0/10) or Tailscale adapter.

6. Launch Daemon & Confirm:
   - Start the listener as a persistent background daemon/service.
   - Test `http://<your-tailscale-ip>:8080/health` locally to confirm 200 OK.
   - Output your completed Client Configuration Block:
     * Hostname & OS
     * Tailscale IPv4 & MagicDNS
     * A2A Endpoint URL
     * Bearer Auth Token
     * Discovered Agents / Containers
   - Acknowledge that you are ready to receive tasks dispatched via the Tailscale A2A Swarm Manager switchboard.
```

### ⚡ What Happens Next:
1. **Auto-Discovery**: Open your Swarm Manager web dashboard (`http://localhost:8670` or `http://<manager-ip>:8670`) and click **"Full Deep Port Probe"** (or call the `tailscale_scan_fleet` MCP tool).
2. **Detection**: The manager scans the Tailscale mesh, detects the new agent's port `8080` A2A service, pulls its `agent-card.json`, and identifies whether Hermes or OpenClaw agents are running.
3. **Switch ON**: Flip the node's **A2A Communication Switch** to **ON** in the dashboard (or via `a2a_toggle_switch`).
4. **Dispatch**: Dispatch tasks directly to that agent through the dashboard dispatcher, Hermes-Agent Low reasoning terminal, or MCP tools.

---

## 🔌 MCP Configuration

Add the server to your MCP configuration file (e.g., `mcp_config.json` or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "tailscale-a2a-manager": {
      "command": "python",
      "args": ["path/to/tailscale-a2a-manager/mcp_server.py"],
      "env": {
        "A2A_MCP_PASSCODE": "your-secret-passcode",
        "VENICE_API_KEY": "your-venice-api-key",
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

---

## 🛠️ MCP Tools Catalog

| Tool | Parameters | Purpose |
| :--- | :--- | :--- |
| `a2a_auth` | `passcode` *(string)* | Authenticate user session with security passcode. |
| `tailscale_scan_fleet` | `probe_remote_ports` *(bool)* | Discovers Tailscale machines and probes running Podman containers for Hermes and OpenClaw agents. Automatically syncs them with the switch registry. |
| `a2a_toggle_switch` | `target` *(string)*, `enable` *(bool)* | **The Communication Switch**: Turns A2A messaging ON or OFF for a machine hostname or container. |
| `a2a_get_mesh_status` | none | Lists all registered nodes and their current switch states (Enabled vs Disabled) along with Hermes/OpenClaw running states. |
| `a2a_send_message` | `target`, `message`, `sender` | Sends an A2A message to an enabled node. Rejects if the node's switch is turned OFF. |
| `hermes_low_ask` | `prompt`, `include_fleet_context` | Prompts Hermes-Agent Low (Venice AI) with live fleet context to analyze containers or plan inter-agent tasks. |
| `a2a_change_passcode` | `old_passcode`, `new_passcode` | Updates the security passcode. |

---

## 🔒 Security

* **Zero Hardcoded Secrets**: Secrets are loaded exclusively from environment variables or local `.env` files.
* **Passcode Protection**: Unauthenticated MCP calls are rejected with `401 Unauthorized`.
* **Subnet-Bounded**: A2A endpoints bind strictly to private Tailscale mesh interfaces (`100.64.0.0/10`), preventing external internet exposure.

---

## 📄 License

MIT License. See [LICENSE](LICENSE).
