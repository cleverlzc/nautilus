"""Unit tests for nautilus.agent — helpers + ReAct loop (mock LLM).

Covers:
- _truncate: short text passthrough, long text truncation with marker
- _print_tool_call: all tool name formatting (requires UTF-8 stdout)
- run_agent with mock LLM: full ReAct loop (write→bash→final answer)
- run_agent with mock LLM: max_iter truncation
- run_agent with mock LLM: error self-correction (edit fails → write succeeds)

NOTE: Run with PYTHONIOENCODING=utf-8 on Windows to handle emoji in agent.py.
"""

import io
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from nautilus.agent import _print_tool_call, _truncate, run_agent


# ---------------------------------------------------------------------------
# Mock LLM infrastructure
# ---------------------------------------------------------------------------

class MockFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class MockToolCall:
    def __init__(self, call_id: str, name: str, arguments: str):
        self.id = call_id
        self.function = MockFunction(name, arguments)


class MockMessage:
    def __init__(self, content: str, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class MockResponse:
    def __init__(self, message):
        self.choices = [MagicMock()]
        self.choices[0].message = message


def make_response(content, tool_calls=None):
    """Shorthand to create a MockResponse."""
    return MockResponse(MockMessage(content=content, tool_calls=tool_calls))


def make_tool_call(call_id, name, args_dict):
    """Shorthand to create a MockToolCall from a dict."""
    return MockToolCall(call_id, name, json.dumps(args_dict))


# ---------------------------------------------------------------------------
# _truncate tests
# ---------------------------------------------------------------------------

class TestTruncate:
    def test_short_text_passthrough(self):
        assert _truncate("short text") == "short text"

    def test_exact_limit(self):
        text = "x" * 2000
        assert _truncate(text, limit=2000) == text

    def test_long_text_truncated(self):
        text = "x" * 3000
        result = _truncate(text, limit=2000)
        assert len(result) > 2000  # includes truncation marker
        assert "已截断" in result
        assert "3000" in result

    def test_truncation_marker_format(self):
        text = "x" * 3000
        result = _truncate(text, limit=2000)
        assert "共 3000 字符" in result

    def test_empty_string(self):
        assert _truncate("") == ""

    def test_custom_limit(self):
        text = "x" * 100
        result = _truncate(text, limit=50)
        assert "已截断" in result
        assert "共 100 字符" in result


# ---------------------------------------------------------------------------
# _print_tool_call tests
# ---------------------------------------------------------------------------

class TestPrintToolCall:
    """NOTE: These tests require UTF-8 stdout. On Windows with GBK encoding,
    emoji characters in agent.py will cause UnicodeEncodeError.
    Run with: PYTHONIOENCODING=utf-8 python -m pytest tests/test_agent.py
    """

    def test_read_file(self, capsys):
        _print_tool_call("read_file", {"path": "src/main.py"})
        captured = capsys.readouterr()
        assert "read_file" in captured.out
        assert "src/main.py" in captured.out

    def test_write_file(self, capsys):
        _print_tool_call("write_file", {"path": "out.py", "content": "hello" * 100})
        captured = capsys.readouterr()
        assert "write_file" in captured.out
        assert "out.py" in captured.out
        assert "字符" in captured.out

    def test_edit_file(self, capsys):
        _print_tool_call("edit_file", {
            "path": "src/main.py",
            "old_string": "old",
            "new_string": "new",
        })
        captured = capsys.readouterr()
        assert "edit_file" in captured.out

    def test_bash(self, capsys):
        _print_tool_call("bash", {"command": "python -m pytest"})
        captured = capsys.readouterr()
        assert "bash" in captured.out
        assert "python -m pytest" in captured.out

    def test_unknown_tool(self, capsys):
        _print_tool_call("unknown_tool", {"arg": "value"})
        captured = capsys.readouterr()
        assert "unknown_tool" in captured.out

    def test_missing_args(self, capsys):
        _print_tool_call("read_file", {})
        captured = capsys.readouterr()
        assert "read_file" in captured.out


# ---------------------------------------------------------------------------
# run_agent with mock LLM — full ReAct loop
# ---------------------------------------------------------------------------

class TestRunAgentReActLoop:
    """Test the core ReAct loop with a mock LLM client.

    Scenario: Agent creates a file, runs it, reports success.
    - iter 1: LLM calls write_file(hello.py, 'print("hello world")')
    - iter 2: LLM calls bash('python hello.py')
    - iter 3: LLM gives final answer (no tool_calls)
    """

    @pytest.fixture
    def mock_responses(self):
        return [
            make_response(
                content="我来创建一个 hello.py 文件。",
                tool_calls=[make_tool_call("call_1", "write_file", {
                    "path": "hello.py",
                    "content": 'print("hello world")',
                })],
            ),
            make_response(
                content="文件已创建，我来运行验证。",
                tool_calls=[make_tool_call("call_2", "bash", {
                    "command": "python hello.py",
                })],
            ),
            make_response(
                content='已完成。创建了 hello.py，运行后输出 hello world，验证通过。',
                tool_calls=None,
            ),
        ]

    def test_full_react_loop(self, mock_responses, tmp_path, capsys, monkeypatch):
        monkeypatch.chdir(tmp_path)
        call_index = [0]

        def mock_create_fn(**kwargs):
            idx = call_index[0]
            call_index[0] += 1
            assert idx < len(mock_responses), f"Unexpected LLM call #{idx}"
            return mock_responses[idx]

        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create_fn

        with patch("nautilus.agent.create_client", return_value=mock_client):
            run_agent(
                prompt="创建一个 hello.py，运行它，确认输出 hello world",
                model="mock-model",
                api_key="sk-fake",
                max_iter=20,
            )

        # Verify 3 LLM calls were made (write, bash, final answer)
        assert call_index[0] == 3

        # Verify the file was actually created by the tool
        assert (tmp_path / "hello.py").exists()
        content = (tmp_path / "hello.py").read_text(encoding="utf-8")
        assert "hello world" in content

        # Verify final answer was printed
        captured = capsys.readouterr()
        assert "已完成" in captured.out


# ---------------------------------------------------------------------------
# run_agent — max_iter truncation
# ---------------------------------------------------------------------------

class TestRunAgentMaxIter:
    """Scenario: LLM always calls tools, never gives a final answer.
    Agent should stop at max_iter and print warning.
    """

    def test_max_iter_truncation(self, tmp_path, capsys, monkeypatch):
        monkeypatch.chdir(tmp_path)

        looping_response = make_response(
            content="thinking...",
            tool_calls=[make_tool_call("call_loop", "bash", {
                "command": "echo looping",
            })],
        )

        call_count = [0]

        def mock_create_fn(**kwargs):
            call_count[0] += 1
            return looping_response

        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create_fn

        with patch("nautilus.agent.create_client", return_value=mock_client):
            run_agent(
                prompt="loop forever",
                model="mock-model",
                api_key="sk-fake",
                max_iter=3,
            )

        # Verify exactly 3 iterations were made
        assert call_count[0] == 3

        # Verify warning was printed
        captured = capsys.readouterr()
        assert "达到最大迭代次数" in captured.out
        assert "3" in captured.out


# ---------------------------------------------------------------------------
# run_agent — error self-correction
# ---------------------------------------------------------------------------

class TestRunAgentErrorRecovery:
    """Scenario: LLM tries edit_file on non-existent file (fails),
    then self-corrects by using write_file to create it (succeeds),
    then gives final answer.
    """

    @pytest.fixture
    def mock_responses(self):
        return [
            make_response(
                content="让我修改这个文件。",
                tool_calls=[make_tool_call("call_1", "edit_file", {
                    "path": "config.py",
                    "old_string": "old",
                    "new_string": "new",
                })],
            ),
            make_response(
                content="文件不存在，我先创建它。",
                tool_calls=[make_tool_call("call_2", "write_file", {
                    "path": "config.py",
                    "content": "new",
                })],
            ),
            make_response(
                content="文件创建成功。",
                tool_calls=None,
            ),
        ]

    def test_error_self_correction(self, mock_responses, tmp_path, capsys, monkeypatch):
        monkeypatch.chdir(tmp_path)
        idx = [0]

        def mock_create_fn(**kwargs):
            i = idx[0]
            idx[0] += 1
            assert i < len(mock_responses), f"Unexpected LLM call #{i}"
            return mock_responses[i]

        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create_fn

        with patch("nautilus.agent.create_client", return_value=mock_client):
            run_agent(
                prompt="修改 config.py",
                model="mock-model",
                api_key="sk-fake",
                max_iter=10,
            )

        # Verify config.py was created via self-correction
        assert (tmp_path / "config.py").exists()

        # Verify error observation was fed back (shown in output)
        captured = capsys.readouterr()
        assert "文件不存在" in captured.out
        assert "文件创建成功" in captured.out
