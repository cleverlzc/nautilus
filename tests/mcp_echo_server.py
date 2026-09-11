"""Minimal MCP server for E2E testing.

Provides one tool: echo_text(text) → returns the text prefixed with [MCP].
Communicates via stdio using JSON-RPC 2.0 (line-delimited).

Usage:
    python mcp_echo_server.py
"""

import json
import sys


def handle_initialize(req):
    return {
        "jsonrpc": "2.0",
        "id": req["id"],
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mcp-echo-server", "version": "0.1.0"},
        },
    }


def handle_tools_list(req):
    return {
        "jsonrpc": "2.0",
        "id": req["id"],
        "result": {
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "echo_text",
                        "description": "Echo the input text with [MCP] prefix. Useful for testing MCP connectivity.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "text": {
                                    "type": "string",
                                    "description": "Text to echo back",
                                }
                            },
                            "required": ["text"],
                        },
                    },
                }
            ]
        },
    }


def handle_tools_call(req):
    params = req.get("params", {})
    name = params.get("name", "")
    arguments = params.get("arguments", {})

    if name == "echo_text":
        text = arguments.get("text", "")
        result_text = f"[MCP] {text}"
    else:
        result_text = f"Unknown tool: {name}"

    return {
        "jsonrpc": "2.0",
        "id": req["id"],
        "result": {
            "content": [{"type": "text", "text": result_text}]
        },
    }


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = req.get("method", "")

        if method == "initialize":
            response = handle_initialize(req)
        elif method == "tools/list":
            response = handle_tools_list(req)
        elif method == "tools/call":
            response = handle_tools_call(req)
        else:
            response = {
                "jsonrpc": "2.0",
                "id": req.get("id", 0),
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            }

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
