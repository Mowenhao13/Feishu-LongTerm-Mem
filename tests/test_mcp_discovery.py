"""Test MCP server discovery via stdio protocol.

This test starts the MCP server and verifies that all tools
can be discovered via the standard MCP protocol with proper
initialize handshake.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _send_json(proc: subprocess.Popen, msg: dict, raw: bool = False) -> str:
    """Send a JSON message over stdin and read a JSON response from stdout."""
    if raw:
        payload = json.dumps(msg) + "\n"
    else:
        payload = json.dumps(msg) + "\n"
    proc.stdin.write(payload)
    proc.stdin.flush()

    line = proc.stdout.readline()
    while line.strip() == "":
        line = proc.stdout.readline()
    return line.strip()


def test_mcp_server_stdio_discovery():
    """启动 MCP server 并通过 stdio JSON-RPC 协议发现工具。"""
    server_script = str(PROJECT_ROOT / "src/mcp_server/server.py")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    proc = subprocess.Popen(
        [sys.executable, server_script],
        cwd=str(PROJECT_ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    # Step 1: Initialize handshake
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }

    init_response_raw = _send_json(proc, init_request)
    init_response = json.loads(init_response_raw)
    assert init_response.get("jsonrpc") == "2.0"
    assert init_response.get("id") == 1
    assert "result" in init_response, f"Init failed: {init_response}"
    result = init_response["result"]
    assert "protocolVersion" in result
    assert "serverInfo" in result
    assert "capabilities" in result
    assert "tools" in result["capabilities"], "Server should advertise tools capability"

    # Step 2: Send initialized notification (no id)
    notif = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    proc.stdin.write(json.dumps(notif) + "\n")
    proc.stdin.flush()

    # Step 3: List tools
    list_tools_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }

    tools_response_raw = _send_json(proc, list_tools_request)
    tools_response = json.loads(tools_response_raw)
    assert tools_response.get("jsonrpc") == "2.0"
    assert "result" in tools_response, f"tools/list failed: {tools_response}"

    tools = tools_response["result"].get("tools", [])
    assert len(tools) >= 9, f"Expected at least 9 tools, got {len(tools)}"

    tool_names = [t["name"] for t in tools]
    expected_tools = [
        "search", "decision", "extract_decision", "classify_topic",
        "detect_crosstopic", "check_conflict", "list_topics", "stats", "timeline",
    ]
    for name in expected_tools:
        assert name in tool_names, f"Tool '{name}' should be discoverable"

    for t in tools:
        assert "description" in t, f"Tool '{t['name']}' must have a description"
        assert "inputSchema" in t, f"Tool '{t['name']}' must have inputSchema"

    # Step 4: Clean up
    proc.terminate()
    proc.wait(5)

    print(f"Discovery OK: {len(tools)} tools found")
    print(f"Tools: {', '.join(tool_names)}")
    print(f"Server: {result['serverInfo']['name']} v{result['serverInfo'].get('version', '?')}")