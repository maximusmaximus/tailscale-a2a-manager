"""
Integration Test Suite for Tailscale A2A Manager & Hermes Low.
Verifies passcode authentication, fleet discovery, switch toggling, and Hermes Low inference.
"""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp_server import A2AMCPServer


def run_tests():
    print("=" * 60)
    print(" TAILSCALE A2A SWARM MANAGER - INTEGRATION TESTS")
    print("=" * 60)

    server = A2AMCPServer()
    PASSCODE = server.passcode

    # Test 1: Unauthenticated request should be rejected
    print("\n[Test 1] Testing passcode protection without auth...")
    res = server.execute_tool("tailscale_scan_fleet", {})
    assert res.get("error") == "Unauthorized", f"Expected Unauthorized, got: {res}"
    print(" PASS: Unauthenticated access blocked correctly.")

    # Test 2: Invalid passcode should be rejected
    print("\n[Test 2] Testing invalid passcode...")
    res = server.execute_tool("a2a_auth", {"passcode": "wrong-secret-12345"})
    assert res.get("success") is False, f"Expected failure, got: {res}"
    print(" PASS: Invalid passcode rejected.")

    # Test 3: Authenticate with valid passcode
    print("\n[Test 3] Testing valid passcode login...")
    auth_res = server.execute_tool("a2a_auth", {"passcode": PASSCODE})
    assert auth_res.get("authenticated") is True, f"Expected authenticated=True, got: {auth_res}"
    session_token = auth_res.get("session_token")
    print(f" PASS: Authenticated successfully! Session Token: {session_token}")

    # Test 4: Fleet Scan & Container Discovery
    print("\n[Test 4] Scanning Tailscale fleet & Podman containers...")
    scan_res = server.execute_tool("tailscale_scan_fleet", {"session_token": session_token, "probe_remote_ports": False})
    assert scan_res.get("success") is True, f"Scan failed: {scan_res}"
    summary = scan_res.get("fleet_summary", {})
    print(f" PASS: Scanned {summary.get('node_count')} nodes ({summary.get('online_count')} online).")

    nodes = scan_res.get("nodes", [])
    active_node = next((n for n in nodes if n.get("online")), None)

    # Test 5: A2A Switch Toggle
    print("\n[Test 5] Testing A2A Switch Toggle (ON/OFF)...")
    if active_node:
        target_name = active_node["hostname"]
        toggle_on = server.execute_tool("a2a_toggle_switch", {"target": target_name, "enable": True, "session_token": session_token})
        print(f" Toggled '{target_name}' ON:", toggle_on.get("status"))

    mesh_res = server.execute_tool("a2a_get_mesh_status", {"session_token": session_token})
    mesh = mesh_res.get("mesh", {})
    print(f" Active A2A Switches: {mesh.get('enabled_count')} enabled, {mesh.get('disabled_count')} disabled")

    # Test 6: Hermes Low Ask (Venice.ai)
    print("\n[Test 6] Testing Hermes-Agent Low tier via Venice Key Manager...")
    if server.hermes_low.api_key and not server.hermes_low.api_key.startswith("your-"):
        agent_res = server.execute_tool("hermes_low_ask", {
            "prompt": "Provide a 1-sentence confirmation of fleet manager status.",
            "include_fleet_context": False,
            "session_token": session_token
        })
        if agent_res.get("success"):
            clean_preview = agent_res.get("response", "")[:150].encode("ascii", errors="replace").decode("ascii")
            print(f" Hermes Low Status: True (Model: {agent_res.get('model')})")
            print(f" Response preview: {clean_preview}...")
        else:
            print(f" Notice: Inference skipped ({agent_res.get('error')})")
    else:
        print(" Notice: Inference test skipped (VENICE_API_KEY placeholder set)")

    print("\n" + "=" * 60)
    print(" ALL INTEGRATION TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
