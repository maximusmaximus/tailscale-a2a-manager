# Tailscale A2A Swarm Manager & Hermes Low

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![MCP Protocol](https://img.shields.io/badge/MCP-2024--11--05-green.svg)](https://modelcontextprotocol.io/)
[![Tailscale](https://img.shields.io/badge/Mesh-Tailscale-blue.svg)](https://tailscale.com/)

A centralized control plane and Model Context Protocol (MCP) server that links your Tailscale mesh network with local and remote Podman containers running **Hermes-Agent** and **OpenClaw** agents.

Powered by **Hermes-Agent Low tier** via [Venice.ai](https://venice.ai) and the Venice Key Manager.

---

## 🚀 Key Capabilities

1. **Tailscale & Podman Discovery**:
   - Queries `tailscale status` to inventory all nodes (IPs, MagicDNS, online states).
   - Inspects Podman / Docker containers across machines to identify running agents (`hermes-agent`, `dawagent`, `openclaw`).
2. **A2A Communication Switch (ON / OFF)**:
   - Provides a per-machine / per-agent switch to control inter-agent communication.
   - Only nodes with their switch turned **ON** can send or receive messages across the A2A mesh.
3. **Hermes-Agent Low Tier (Venice Key Manager)**:
   - Integrated with Venice Key Manager inference keys.
   - Low-tier model (`deepseek-v4-flash`) for rapid, budget-friendly fleet telemetry analysis, task drafting, and inter-agent coordination.
4. **Passcode-Protected MCP Interface**:
   - Compliant with Model Context Protocol (MCP) JSON-RPC 2.0.
   - Restricts control operations to authenticated users via passcode.
5. **Interactive Browser Dashboard**:
   - Cyber/terminal dark UI running on port `8670`.
   - Real-time switchboard to flip A2A communication switches ON/OFF with live visual feedback.
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
|               Tailscale A2A Swarm Manager (mcp_server.py)                         |
+-------------------+-------------------------------+-------------------------------+
                    │                               │                               │
                    ▼                               ▼                               ▼
       [Fleet & Podman Scanner]           [A2A Swarm Switch]         [Hermes-Agent Low Tier]
        fleet_scanner.py                  mesh_switch.py             hermes_low.py
       - Tailscale Status API            - ON/OFF toggle per node   - Venice Key Manager
       - Podman Inspection:               - Block/allow messages       Inference Engine
         * hermes-agent                   - Direct A2A messaging    - Low-latency reasoning
         * openclaw / dawagent                                       (deepseek-v4-flash)
```

---

## 📦 Quickstart

### 1. Installation

```bash
git clone https://github.com/maximusmaximus/tailscale-a2a-manager.git
cd tailscale-a2a-manager

# Copy environment variables
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
| `a2a_get_mesh_status` | none | Lists all registered nodes and their current switch states (Enabled vs Disabled). |
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
