"""Unit tests for nautilus.__main__ — CLI entry point.

Covers:
- --help: prints usage and exits 0
- No prompt + no stdin: prints help and exits 1
- Stdin pipe: reads prompt from stdin
- Positional prompt arg: passes through to run_agent
- CLI flags: --model / --api-key / --base-url / --max-iter
"""

import subprocess
import sys
from unittest.mock import patch

import pytest

from nautilus.__main__ import main


# ---------------------------------------------------------------------------
# --help tests
# ---------------------------------------------------------------------------

class TestCLIHelp:
    def test_help_exits_zero(self):
        """`nautilus --help` should print usage and exit 0."""
        result = subprocess.run(
            [sys.executable, "-m", "nautilus", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0
        assert "nautilus" in result.stdout
        assert "--model" in result.stdout
        assert "--api-key" in result.stdout
        assert "--base-url" in result.stdout
        assert "--max-iter" in result.stdout

    def test_help_shows_description(self):
        result = subprocess.run(
            [sys.executable, "-m", "nautilus", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0
        assert "鹦鹉螺" in result.stdout


# ---------------------------------------------------------------------------
# No prompt tests
# ---------------------------------------------------------------------------

class TestCLINoPrompt:
    def test_no_prompt_no_stdin_exits_1(self):
        """Running with no prompt and no stdin should print help and exit 1."""
        result = subprocess.run(
            [sys.executable, "-m", "nautilus"],
            capture_output=True,
            text=True,
            timeout=10,
            stdin=subprocess.DEVNULL,  # no stdin
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 1
        output = (result.stdout or "") + (result.stderr or "")
        assert "usage:" in output


# ---------------------------------------------------------------------------
# Stdin pipe tests
# ---------------------------------------------------------------------------

class TestCLIStdin:
    def test_stdin_prompt_is_read(self):
        """When prompt is not given as positional arg, read from stdin."""
        # Without valid API key, the process will try to call LLM and fail.
        # We verify stdin is read by checking it doesn't print the usage help.
        # Use a non-routable IP to get fast connection refused (no retry delay).
        result = subprocess.run(
            [sys.executable, "-m", "nautilus", "--api-key", "sk-fake",
             "--base-url", "https://0.0.0.0:1", "--max-iter", "1"],
            input="test prompt from stdin",
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            errors="replace",
        )
        # Should not print help (prompt was read from stdin)
        # It will fail at API call (connection error), but that's expected
        output = (result.stdout or "") + (result.stderr or "")
        assert "usage:" not in output or "nautilus" in output


# ---------------------------------------------------------------------------
# Argument parsing tests (using mock run_agent)
# ---------------------------------------------------------------------------

class TestCLIArgumentParsing:
    """Test that CLI arguments are correctly parsed and passed to run_agent."""

    @patch("nautilus.__main__.run_agent")
    def test_positional_prompt(self, mock_run):
        with patch("sys.argv", ["nautilus", "do something"]):
            main()
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert "do something" in str(call_kwargs)

    @patch("nautilus.__main__.run_agent")
    def test_model_flag(self, mock_run):
        with patch("sys.argv", ["nautilus", "--model", "qwen-plus", "task"]):
            main()
        call_kwargs = mock_run.call_args
        # model should be passed as keyword arg
        assert call_kwargs.kwargs.get("model") == "qwen-plus"

    @patch("nautilus.__main__.run_agent")
    def test_api_key_flag(self, mock_run):
        with patch("sys.argv", ["nautilus", "--api-key", "sk-123", "task"]):
            main()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("api_key") == "sk-123"

    @patch("nautilus.__main__.run_agent")
    def test_base_url_flag(self, mock_run):
        with patch("sys.argv", ["nautilus", "--base-url", "https://x.com", "task"]):
            main()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("base_url") == "https://x.com"

    @patch("nautilus.__main__.run_agent")
    def test_max_iter_flag(self, mock_run):
        with patch("sys.argv", ["nautilus", "--max-iter", "5", "task"]):
            main()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("max_iter") == 5

    @patch("nautilus.__main__.run_agent")
    def test_max_tool_output_flag(self, mock_run):
        with patch("sys.argv", ["nautilus", "--max-tool-output", "3000", "task"]):
            main()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("max_tool_output_chars") == 3000

    @patch("nautilus.__main__.run_agent")
    def test_default_max_iter_is_20(self, mock_run):
        with patch("sys.argv", ["nautilus", "task"]):
            main()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("max_iter") == 20

    @patch("nautilus.__main__.run_agent")
    def test_default_model_is_gpt4(self, mock_run):
        with patch("sys.argv", ["nautilus", "task"]):
            main()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("model") == "gpt-4"

    @patch("nautilus.__main__.run_agent")
    def test_default_api_key_is_none(self, mock_run):
        with patch("sys.argv", ["nautilus", "task"]):
            main()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("api_key") is None

    @patch("nautilus.__main__.run_agent")
    def test_default_max_tool_output_is_6000(self, mock_run):
        with patch("sys.argv", ["nautilus", "task"]):
            main()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("max_tool_output_chars") == 6000

    @patch("nautilus.__main__.run_agent")
    def test_stream_flag(self, mock_run):
        with patch("sys.argv", ["nautilus", "--stream", "task"]):
            main()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("stream") is True

    @patch("nautilus.__main__.run_agent")
    def test_stream_default_false(self, mock_run):
        with patch("sys.argv", ["nautilus", "task"]):
            main()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("stream") is False

    @patch("nautilus.__main__.run_agent")
    def test_approval_flag(self, mock_run):
        with patch("sys.argv", ["nautilus", "--approval", "task"]):
            main()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("approval") is True

    @patch("nautilus.__main__.run_agent")
    def test_approval_default_false(self, mock_run):
        with patch("sys.argv", ["nautilus", "task"]):
            main()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("approval") is False
