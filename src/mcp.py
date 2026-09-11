"""MCP client for external tool server integration (stdio transport)."""

import json
import subprocess


class MCPClient:
    """MCP client: connect to MCP server via stdio, discover and call tools.

    Uses JSON-RPC 2.0 protocol over subprocess stdin/stdout.
    """

    def __init__(self, server_command: str):
        """Start MCP server subprocess and initialize connection.

        Args:
            server_command: Shell command to start MCP server (e.g. "npx @mcp/filesystem")
        """
        self.process = None
        self._request_id = 0
        self._tools = []
        try:
            self.process = subprocess.Popen(
                server_command,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            self._initialize()
            self._tools = self._list_tools()
        except Exception:
            self.close()
            raise

    def _send_request(self, method: str, params: dict | None = None) -> dict:
        """Send JSON-RPC 2.0 request and return response result."""
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
        }
        if params:
            request["params"] = params
        line = json.dumps(request) + "\n"
        self.process.stdin.write(line)
        self.process.stdin.flush()
        response_line = self.process.stdout.readline()
        if not response_line:
            raise ConnectionError("MCP server closed connection")
        response = json.loads(response_line)
        if "error" in response:
            raise Exception(f"MCP error: {response['error']}")
        return response.get("result", {})

    def _initialize(self) -> dict:
        """Send initialize request to MCP server."""
        return self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "nautilus", "version": "0.3.5"},
        })

    def _list_tools(self) -> list[dict]:
        """Discover tools from MCP server. Returns list of tool schemas."""
        result = self._send_request("tools/list")
        return result.get("tools", [])

    def get_tools(self) -> list[dict]:
        """Return discovered tool schemas in OpenAI function-calling format."""
        return self._tools

    def call_tool(self, name: str, arguments: dict) -> str:
        """Call a tool on MCP server. Returns result as string."""
        result = self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        # MCP returns content as list of {type, text} dicts
        content = result.get("content", [])
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
        return "\n".join(texts) if texts else str(result)

    def close(self):
        """Close connection and terminate subprocess."""
        if self.process:
            try:
                self.process.stdin.close()
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
            self.process = None
