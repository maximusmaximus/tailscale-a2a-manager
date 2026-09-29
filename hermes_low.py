"""
Hermes-Agent Low Tier Engine.
Provides fast, lightweight reasoning for fleet orchestration and A2A inter-agent routing
via Venice.ai and the Venice Key Manager.
"""

import os
import json
import time
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


class HermesLowAgent:
    SYSTEM_PROMPT = (
        "You are Hermes-Agent Low, an agile AI fleet coordinator and multi-agent routing engine "
        "integrated with the Venice Key Manager. "
        "Your mission is to monitor Podman containers running Hermes-Agent and OpenClaw agents across "
        "the Tailscale network, control A2A communication switches, and synthesize tasks for inter-agent delegation. "
        "Provide concise, precise, and highly actionable responses."
    )

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or load_config()
        venice_cfg = self.config.get("venice", {})
        self.api_key = os.environ.get("VENICE_API_KEY") or venice_cfg.get("api_key", "")
        # Auto-discover from local venice-key-manager vault if not explicitly set
        if not self.api_key or self.api_key.startswith("your-"):
            v_vault_path = Path(__file__).resolve().parent.parent / "venice-key-manager" / "venice_vault.json"
            if v_vault_path.exists():
                try:
                    with open(v_vault_path, "r", encoding="utf-8") as vf:
                        v_data = json.load(vf)
                    self.api_key = v_data.get("venice", {}).get("inference_key") or v_data.get("venice", {}).get("admin_key", "")
                except Exception:
                    pass

        self.key_id = os.environ.get("VENICE_KEY_ID") or venice_cfg.get("key_id", "default-venice-key")
        self.base_url = (os.environ.get("VENICE_BASE_URL") or venice_cfg.get("base_url", "https://api.venice.ai/api/v1")).rstrip("/")
        self.model = os.environ.get("VENICE_MODEL") or venice_cfg.get("model", "deepseek-v4-flash")
        self.tier = venice_cfg.get("tier", "low")

    def run_inference(self, messages: List[Dict[str, str]], max_tokens: int = 500, temperature: float = 0.3) -> Dict[str, Any]:
        """Call Venice API chat completions."""
        if not self.api_key or self.api_key.startswith("your-"):
            return {
                "success": False,
                "error": "Venice API key is not configured. Set VENICE_API_KEY environment variable or update config.json."
            }

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "venice_parameters": {
                "include_venice_system_prompt": False
            }
        }

        start_time = time.time()
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latency_ms = int((time.time() - start_time) * 1000)
                choice = data.get("choices", [{}])[0]
                msg = choice.get("message", {})
                content = msg.get("content") or msg.get("reasoning_content") or ""
                return {
                    "success": True,
                    "agent": "hermes-agent-low",
                    "model": self.model,
                    "tier": self.tier,
                    "key_id": self.key_id,
                    "latency_ms": latency_ms,
                    "response": content.strip(),
                    "usage": data.get("usage", {})
                }
        except urllib.error.HTTPError as he:
            return {"success": False, "status_code": he.code, "error": he.read().decode("utf-8")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def ask(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ask Hermes Low a question or give it a command with optional fleet context."""
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT}
        ]
        if context:
            context_str = json.dumps(context, indent=2)
            messages.append({
                "role": "user",
                "content": f"[FLEET & A2A CONTEXT]:\n{context_str}\n\n[USER REQUEST]:\n{prompt}"
            })
        else:
            messages.append({"role": "user", "content": prompt})

        return self.run_inference(messages)

    def analyze_fleet(self, fleet_data: Dict[str, Any], mesh_status: Dict[str, Any]) -> Dict[str, Any]:
        """Provides an intelligent assessment of fleet status and A2A routing."""
        prompt = (
            "Analyze the current Tailscale nodes, Podman containers (Hermes and OpenClaw), "
            "and A2A mesh switches. Give a 3-bullet summary of fleet readiness, highlight which agents "
            "are active, and recommend any A2A switches that should be toggled."
        )
        context = {
            "fleet_data": fleet_data,
            "mesh_status": mesh_status
        }
        return self.ask(prompt, context=context)


if __name__ == "__main__":
    agent = HermesLowAgent()
    print("Hermes Low Agent initialized.")
    if agent.api_key and not agent.api_key.startswith("your-"):
        res = agent.ask("Hello from Hermes Low! Give a 1-sentence intro of your capabilities.")
        print("Response:", res.get("response"))
    else:
        print("Notice: VENICE_API_KEY not configured. Set environment variable to test inference.")
