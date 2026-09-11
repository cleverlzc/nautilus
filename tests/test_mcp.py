"""Unit tests for nautilus.mcp — MCP client and tool integration.

Covers:
- MCPClient: initialize / list_tools / call_tool / connection error / close
- MCP tool integration: tools merged / MCP tool called in loop / connection failure graceful
"""

import json
from unittest.mock import MagicMock, patch, mock_open

import pytest

from nautilus.mcp import MCPClient


# ---------------------------------------------------------------------------
# MCPClient tests
# ---------------------------------------------------------------------------

class TestMCPClient:
    """Test MCPClient with mocked subprocess."""

    def _create_mock_process(self, responses):
        """Create a mock subprocess that returns pre-defined JSON-RPC responses."""
        mock_proc = MagicMock()
        response_iter = iter(responses)
        mock_proc.stdout.readline = lambda: next(response_iter)
        mock_proc.stdin = MagicMock()
        mock_proc.wait = MagicMock(return_value=0)
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        return mock_proc

    def test_mcp_client_initialize(self):
        """MCPClient sends initialize request on construction."""
        init_response = json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
            }
        }) + "\n"
        list_response = json.dumps({
            "jsonrpc": "2.0", "id": 2, "result": {"tools": []}
        }) + "\n"

        mock_proc = self._create_mock_process([init_response, list_response])

        with patch("subprocess.Popen", return_value=mock_proc):
            client = MCPClient("echo fake_server")

        # initialize was sent (stdin.write called)
        assert mock_proc.stdin.write.called
        written = mock_proc.stdin.write.call_args_list[0][0][0]
        data = json.loads(written.strip())
        assert data["method"] == "initialize"
        assert "protocolVersion" in data["params"]

    def test_mcp_client_list_tools(self):
        """MCPClient discovers tools from server."""
        init_response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n"
        tools = [
            {"type": "function", "function": {"name": "fetch_url", "description": "Fetch URL", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}}
        ]
        list_response = json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"tools": tools}}) + "\n"

        mock_proc = self._create_mock_process([init_response, list_response])

        with patch("subprocess.Popen", return_value=mock_proc):
            client = MCPClient("echo fake_server")

        discovered = client.get_tools()
        assert len(discovered) == 1
        assert discovered[0]["function"]["name"] == "fetch_url"

    def test_mcp_client_call_tool(self):
        """MCPClient calls a tool and returns text result."""
        init_response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n"
        list_response = json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}) + "\n"
        call_response = json.dumps({
            "jsonrpc": "2.0", "id": 3, "result": {
                "content": [{"type": "text", "text": "Hello from MCP!"}]
            }
        }) + "\n"

        mock_proc = self._create_mock_process([init_response, list_response, call_response])

        with patch("subprocess.Popen", return_value=mock_proc):
            client = MCPClient("echo fake_server")
            result = client.call_tool("fetch_url", {"url": "http://example.com"})

        assert result == "Hello from MCP!"

    def test_mcp_client_connection_error(self):
        """MCPClient raises exception when subprocess fails to start."""
        with patch("subprocess.Popen", side_effect=FileNotFoundError("command not found")):
            with pytest.raises(FileNotFoundError):
                MCPClient("nonexistent_command")

    def test_mcp_client_close(self):
        """MCPClient.close() terminates subprocess."""
        init_response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n"
        list_response = json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}) + "\n"

        mock_proc = self._create_mock_process([init_response, list_response])
        mock_proc.stdin.close = MagicMock()

        with patch("subprocess.Popen", return_value=mock_proc):
            client = MCPClient("echo fake_server")
            client.close()

        mock_proc.terminate.assert_called_once()
        assert client.process is None


# ---------------------------------------------------------------------------
# MCP tool integration tests
# ---------------------------------------------------------------------------

class TestMCPToolIntegration:
    """Test MCP tool integration with agent loop."""

    def test_mcp_tools_merged_with_builtin(self, tmp_path, monkeypatch):
        """MCP tool schemas should be merged with TOOL_SCHEMAS and called in loop."""
        monkeypatch.chdir(tmp_path)

        init_response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n"
        tools = [
            {"type": "function", "function": {"name": "fetch_url", "description": "Fetch", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}}
        ]
        list_response = json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"tools": tools}}) + "\n"
        call_response = json.dumps({
            "jsonrpc": "2.0", "id": 3, "result": {
                "content": [{"type": "text", "text": "url content"}]
            }
        }) + "\n"

        # All responses in order: init, list, call
        all_responses = [init_response, list_response, call_response]
        mock_proc = MagicMock()
        mock_proc.stdout.readline = lambda: next(iter(all_responses))
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write = MagicMock()
        mock_proc.stdin.close = MagicMock()
        mock_proc.wait = MagicMock(return_value=0)
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()

        # Agent calls MCP tool → gets result → final answer
        responses = [
            MagicMock(choices=[MagicMock(message=MagicMock(
                content="fetching",
                tool_calls=[MagicMock(id="c1", function=MagicMock(name="fetch_url", arguments='{"url": "http://x"}'))]
            ))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content="done", tool_calls=None))]),
        ]

        idx = [0]
        def mock_create_fn(**kwargs):
            i = idx[0]
            idx[0] += 1
            return responses[i]

        mock_llm_client = MagicMock()
        mock_llm_client.chat.completions.create = mock_create_fn

        with patch("nautilus.agent.create_client", return_value=mock_llm_client):
            with patch("subprocess.Popen", return_value=mock_proc):
                from nautilus.agent import run_agent
                run_agent(
                    prompt="fetch url",
                    model="mock-model",
                    api_key="sk-fake",
                    max_iter=5,
                    mcp_servers=["echo fake_mcp"],
                )

        # MCP tool was called (2 LLM calls: tool_call → final answer)
        assert idx[0] == 2

    def test_mcp_connection_failure_graceful(self, tmp_path, capsys, monkeypatch):
        """MCP server connection failure should print warning, not crash."""
        monkeypatch.chdir(tmp_path)

        # Agent gets final answer without MCP tools
        response = MagicMock(choices=[MagicMock(message=MagicMock(content="done", tool_calls=None))])

        mock_client = MagicMock()
        mock_client.chat.completions.create = MagicMock(return_value=response)

        with patch("nautilus.agent.create_client", return_value=mock_client):
            with patch("subprocess.Popen", side_effect=FileNotFoundError("not found")):
                from nautilus.agent import run_agent
                run_agent(
                    prompt="task",
                    model="mock-model",
                    api_key="sk-fake",
                    max_iter=5,
                    mcp_servers=["nonexistent_cmd"],
                )

        captured = capsys.readouterr()
        assert "连接失败" in captured.out or "connection failed" in captured.out

    def test_mcp_unknown_tool_returns_error(self, tmp_path, capsys, monkeypatch):
        """When tool is not built-in and no MCP client can handle it, return error."""
        monkeypatch.chdir(tmp_path)

        # Agent calls unknown tool → error result → final answer
        responses = [
            MagicMock(choices=[MagicMock(message=MagicMock(
                content="calling",
                tool_calls=[MagicMock(id="c1", function=MagicMock(name="unknown_tool", arguments='{}'))]
            ))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content="done", tool_calls=None))]),
        ]

        idx = [0]
        def mock_create_fn(**kwargs):
            i = idx[0]
            idx[0] += 1
            return responses[i]

        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create_fn

        with patch("nautilus.agent.create_client", return_value=mock_client):
            from nautilus.agent import run_agent
            run_agent(
                prompt="task",
                model="mock-model",
                api_key="sk-fake",
                max_iter=5,
            )

        # No MCP clients, unknown tool → error message
        captured = capsys.readouterr()
        assert "错误" in captured.out or "error" in captured.out.lower()
