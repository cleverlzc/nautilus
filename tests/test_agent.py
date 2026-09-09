"""Unit tests for nautilus.agent — helpers + ReAct loop (mock LLM).

Covers:
- _estimate_tokens: ASCII/CJK/mixed/empty token estimation
- _truncate: short text passthrough, long text truncation with marker
- _truncate_for_llm: LLM feed truncation with bilingual marker
- _print_tool_call: all tool name formatting (requires UTF-8 stdout)
- run_agent with mock LLM: full ReAct loop (write→bash→final answer)
- run_agent with mock LLM: max_iter truncation
- run_agent with mock LLM: error self-correction (edit fails → write succeeds)
- run_agent with mock LLM: token budget truncation on large tool output

NOTE: Run with PYTHONIOENCODING=utf-8 on Windows to handle emoji in agent.py.
"""

import io
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from nautilus.agent import (
    _compress_history,
    _estimate_tokens,
    _messages_token_estimate,
    _print_tool_call,
    _truncate,
    _truncate_for_llm,
    run_agent,
)


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
# _estimate_tokens tests
# ---------------------------------------------------------------------------

class TestEstimateTokens:
    def test_pure_ascii(self):
        # "hello world" = 11 chars, 11//4 = 2
        assert _estimate_tokens("hello world") == 2

    def test_pure_cjk(self):
        # "你好世界" = 4 chars, 4//2 = 2
        assert _estimate_tokens("你好世界") == 2

    def test_empty_string(self):
        assert _estimate_tokens("") == 0

    def test_mixed_ascii_cjk(self):
        # "hello 你好" = 6 ASCII + 2 CJK → 6//4 + 2//2 = 1 + 1 = 2
        assert _estimate_tokens("hello 你好") == 2

    def test_long_code_text(self):
        # 4000 chars of ASCII → 1000 tokens
        text = "x" * 4000
        assert _estimate_tokens(text) == 1000

    def test_none_safety(self):
        assert _estimate_tokens(None) == 0


# ---------------------------------------------------------------------------
# _truncate_for_llm tests
# ---------------------------------------------------------------------------

class TestTruncateForLlm:
    def test_short_text_passthrough(self):
        assert _truncate_for_llm("short text") == "short text"

    def test_exact_limit_no_truncation(self):
        text = "x" * 6000
        assert _truncate_for_llm(text, max_chars=6000) == text

    def test_long_text_truncated_with_bilingual_marker(self):
        text = "x" * 10000
        result = _truncate_for_llm(text, max_chars=6000)
        assert len(result) > 6000  # includes marker
        assert result[:6000] == text[:6000]
        assert "输出已截断" in result
        assert "Output truncated" in result
        assert "10000" in result
        assert "6000" in result

    def test_custom_max_chars(self):
        text = "x" * 500
        result = _truncate_for_llm(text, max_chars=100)
        assert result[:100] == text[:100]
        assert "500" in result
        assert "100" in result

    def test_empty_string(self):
        assert _truncate_for_llm("") == ""


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


# ---------------------------------------------------------------------------
# run_agent — token budget truncation on large tool output
# ---------------------------------------------------------------------------

class TestRunAgentTokenBudget:
    """Scenario: bash returns a very large output (10000 chars).
    The agent should truncate it before feeding to LLM messages,
    and the truncation marker should be present in the tool result message.
    """

    def test_large_tool_output_truncated_in_messages(self, tmp_path, capsys, monkeypatch):
        monkeypatch.chdir(tmp_path)

        # Capture messages passed to the LLM on the 2nd call
        captured_messages = []

        large_output = "x" * 10000

        responses = [
            make_response(
                content="running command",
                tool_calls=[make_tool_call("call_1", "bash", {
                    "command": "echo big_output",
                })],
            ),
            make_response(
                content="done",
                tool_calls=None,
            ),
        ]

        idx = [0]

        def mock_create_fn(**kwargs):
            i = idx[0]
            idx[0] += 1
            # Capture messages on every call
            captured_messages.append(list(kwargs.get("messages", [])))
            assert i < len(responses), f"Unexpected LLM call #{i}"
            return responses[i]

        # Patch execute_tool to return our large output
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create_fn

        with patch("nautilus.agent.create_client", return_value=mock_client):
            with patch("nautilus.agent.execute_tool", return_value=large_output):
                run_agent(
                    prompt="run a command with big output",
                    model="mock-model",
                    api_key="sk-fake",
                    max_iter=5,
                    max_tool_output_chars=500,  # small budget for testing
                )

        # The 2nd LLM call (idx=1) should have received messages containing
        # the truncated tool result
        assert len(captured_messages) >= 2

        # Find the tool message in the 2nd call's messages
        tool_messages = [
            m for m in captured_messages[1]
            if isinstance(m, dict) and m.get("role") == "tool"
        ]
        assert len(tool_messages) == 1

        tool_content = tool_messages[0]["content"]
        # Should be truncated (not the full 10000 chars)
        assert len(tool_content) < 10000
        # Should contain the truncation marker
        assert "输出已截断" in tool_content
        assert "Output truncated" in tool_content
        assert "10000" in tool_content
        assert "500" in tool_content


# ---------------------------------------------------------------------------
# _messages_token_estimate tests
# ---------------------------------------------------------------------------

class TestMessagesTokenEstimate:
    def test_pure_dict_messages(self):
        messages = [
            {"role": "system", "content": "hello world"},
            {"role": "user", "content": "你好世界"},
        ]
        # "hello world" = 11 ASCII → 2 tokens; "你好世界" = 4 CJK → 2 tokens
        assert _messages_token_estimate(messages) == 4

    def test_empty_messages(self):
        assert _messages_token_estimate([]) == 0

    def test_dict_with_tool_calls(self):
        messages = [
            {"role": "system", "content": "sys"},
            {
                "role": "assistant",
                "content": "thinking",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "bash", "arguments": '{"command":"echo hi"}'}},
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "hi"},
        ]
        total = _messages_token_estimate(messages)
        assert total > 0
        # "sys" = 3 ASCII → 0 tokens (3//4=0)
        # "thinking" = 8 ASCII → 2 tokens
        # '{"command":"echo hi"}' = 21 ASCII → 5 tokens
        # "hi" = 2 ASCII → 0 tokens
        assert total == 7  # 0+2+5+0

    def test_sdk_like_objects(self):
        """Messages with attribute access (not dict) should also work."""
        class FakeFn:
            def __init__(self, args):
                self.arguments = args

        class FakeToolCall:
            def __init__(self, args):
                self.function = FakeFn(args)

        class FakeMsg:
            def __init__(self, content, tool_calls=None):
                self.content = content
                self.tool_calls = tool_calls

        messages = [
            FakeMsg(content="hello world", tool_calls=[FakeToolCall('{"path":"x"}')]),
        ]
        # "hello world" = 11 ASCII → 2; '{"path":"x"}' = 12 ASCII → 3
        assert _messages_token_estimate(messages) == 5


# ---------------------------------------------------------------------------
# _compress_history tests
# ---------------------------------------------------------------------------

class TestCompressHistory:
    def test_no_compression_under_budget(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "task"},
            {"role": "assistant", "content": "reply"},
            {"role": "tool", "tool_call_id": "1", "content": "result"},
        ]
        _compress_history(messages, max_tokens=100000)
        assert len(messages) == 4  # nothing dropped

    def test_compresses_over_budget(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "task"},
            {"role": "assistant", "content": "x" * 1000},
            {"role": "tool", "tool_call_id": "1", "content": "y" * 1000},
            {"role": "assistant", "content": "z" * 1000},
            {"role": "tool", "tool_call_id": "2", "content": "w" * 1000},
        ]
        # Total ~4000 chars ASCII → ~1000 tokens. Budget=500 → must drop.
        _compress_history(messages, max_tokens=500)
        assert len(messages) < 6  # some dropped
        assert len(messages) >= 2  # system+user always kept

    def test_never_drops_system_and_user(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "task"},
            {"role": "assistant", "content": "x" * 10000},
            {"role": "tool", "tool_call_id": "1", "content": "y" * 10000},
        ]
        # Even with tiny budget, system+user survive
        _compress_history(messages, max_tokens=1)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_empty_history_after_system_user(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "task"},
        ]
        _compress_history(messages, max_tokens=1)
        assert len(messages) == 2  # can't pop, only 2 left


# ---------------------------------------------------------------------------
# run_agent — context compression integration
# ---------------------------------------------------------------------------

class TestRunAgentContextCompression:
    """Verify that run_agent compresses history across many iterations."""

    def test_history_compressed_within_budget(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        captured = []

        # 8 iterations, each appending a large tool result
        responses = [
            make_response(
                content=f"iter {n}",
                tool_calls=[make_tool_call(f"c{n}", "bash", {"command": f"echo iter{n}"})],
            )
            for n in range(8)
        ] + [make_response(content="done", tool_calls=None)]

        idx = [0]

        def mock_create_fn(**kwargs):
            captured.append(list(kwargs.get("messages", [])))
            i = idx[0]
            idx[0] += 1
            assert i < len(responses), f"Unexpected LLM call #{i}"
            return responses[i]

        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create_fn

        with patch("nautilus.agent.create_client", return_value=mock_client):
            with patch("nautilus.agent.execute_tool", return_value="x" * 2000):
                run_agent(
                    prompt="task",
                    model="mock-model",
                    api_key="sk-fake",
                    max_iter=10,
                    max_context_tokens=800,
                    max_tool_output_chars=5000,
                )

        # Later LLM calls should have bounded messages (system+user + few recent)
        assert len(captured) >= 2
        for msgs in captured:
            assert len(msgs) >= 2  # system+user always kept

        # The last captured messages should be within budget
        from nautilus.agent import _messages_token_estimate
        final_tokens = _messages_token_estimate(captured[-1])
        assert final_tokens <= 800 or len(captured[-1]) == 2


# ---------------------------------------------------------------------------
# run_agent — permission approval for bash
# ---------------------------------------------------------------------------

class TestRunAgentApproval:
    """Test the permission approval gate for bash commands.

    When approval=True, bash commands should prompt the user.
    - User says 'n' → command refused, observation fed back to LLM
    - User says 'y' → command executed normally
    - approval=False (default) → no prompt, executes directly
    """

    def test_approval_rejected_bash_command(self, tmp_path, capsys, monkeypatch):
        """User rejects bash command → refusal observation fed back to LLM."""
        monkeypatch.chdir(tmp_path)

        responses = [
            make_response(
                content="running command",
                tool_calls=[make_tool_call("call_1", "bash", {
                    "command": "rm -rf /",
                })],
            ),
            make_response(
                content="understood, command was rejected",
                tool_calls=None,
            ),
        ]

        idx = [0]

        def mock_create_fn(**kwargs):
            i = idx[0]
            idx[0] += 1
            return responses[i]

        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create_fn

        # Mock input() to reject
        with patch("nautilus.agent.create_client", return_value=mock_client):
            with patch("builtins.input", return_value="n"):
                run_agent(
                    prompt="run rm -rf /",
                    model="mock-model",
                    api_key="sk-fake",
                    max_iter=5,
                    approval=True,
                )

        captured = capsys.readouterr()
        assert "用户拒绝了该命令" in captured.out

    def test_approval_accepted_bash_command(self, tmp_path, capsys, monkeypatch):
        """User accepts bash command → executed normally."""
        monkeypatch.chdir(tmp_path)

        responses = [
            make_response(
                content="running command",
                tool_calls=[make_tool_call("call_1", "bash", {
                    "command": "echo hello_approval",
                })],
            ),
            make_response(
                content="done",
                tool_calls=None,
            ),
        ]

        idx = [0]

        def mock_create_fn(**kwargs):
            i = idx[0]
            idx[0] += 1
            return responses[i]

        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create_fn

        with patch("nautilus.agent.create_client", return_value=mock_client):
            with patch("builtins.input", return_value="y"):
                run_agent(
                    prompt="run echo",
                    model="mock-model",
                    api_key="sk-fake",
                    max_iter=5,
                    approval=True,
                )

        captured = capsys.readouterr()
        assert "hello_approval" in captured.out
        assert "exit code: 0" in captured.out

    def test_approval_disabled_by_default(self, tmp_path, capsys, monkeypatch):
        """approval=False (default) → no prompt, executes directly."""
        monkeypatch.chdir(tmp_path)

        responses = [
            make_response(
                content="running command",
                tool_calls=[make_tool_call("call_1", "bash", {
                    "command": "echo no_approval",
                })],
            ),
            make_response(
                content="done",
                tool_calls=None,
            ),
        ]

        idx = [0]

        def mock_create_fn(**kwargs):
            i = idx[0]
            idx[0] += 1
            return responses[i]

        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create_fn

        with patch("nautilus.agent.create_client", return_value=mock_client):
            # input() should never be called
            with patch("builtins.input", side_effect=AssertionError("input() should not be called")):
                run_agent(
                    prompt="run echo",
                    model="mock-model",
                    api_key="sk-fake",
                    max_iter=5,
                    approval=False,
                )

        captured = capsys.readouterr()
        assert "no_approval" in captured.out
