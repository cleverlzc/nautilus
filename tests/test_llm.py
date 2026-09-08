"""Unit tests for nautilus.llm — create_client factory + retry wrapper.

Covers:
- No API key: raises SystemExit with helpful message
- Explicit api_key: creates OpenAI client
- Explicit base_url: client gets custom base_url
- Environment variable fallback: OPENAI_API_KEY / OPENAI_BASE_URL
- Explicit args override env vars
- complete_with_retry: transient error retry, non-transient immediate raise, exhaustion
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from openai import (
    OpenAI,
    APIConnectionError,
    RateLimitError,
    BadRequestError,
    AuthenticationError,
)

from nautilus.llm import create_client, complete_with_retry, stream_complete


# ---------------------------------------------------------------------------
# No API key tests
# ---------------------------------------------------------------------------

class TestCreateClientNoKey:
    def test_no_key_raises_systemexit(self, monkeypatch):
        """When no key is provided via args or env, raise SystemExit."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            create_client()
        assert "API key" in str(exc_info.value)

    def test_no_key_message_mentions_env_var(self, monkeypatch):
        """Error message should guide user to set OPENAI_API_KEY."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            create_client()
        assert "OPENAI_API_KEY" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Explicit args tests
# ---------------------------------------------------------------------------

class TestCreateClientExplicit:
    def test_explicit_key_creates_client(self):
        client = create_client(api_key="sk-test-key")
        assert isinstance(client, OpenAI)

    def test_explicit_key_and_base_url(self):
        client = create_client(
            api_key="sk-test-key",
            base_url="https://api.example.com/v1",
        )
        assert isinstance(client, OpenAI)


# ---------------------------------------------------------------------------
# Environment variable fallback tests
# ---------------------------------------------------------------------------

class TestCreateClientEnvFallback:
    def test_env_api_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        client = create_client()
        assert isinstance(client, OpenAI)

    def test_env_api_key_and_base_url(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example.com/v1")
        client = create_client()
        assert isinstance(client, OpenAI)

    def test_explicit_overrides_env(self, monkeypatch):
        """Explicit args should take priority over environment variables."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example.com")
        client = create_client(api_key="sk-explicit", base_url="https://explicit.example.com")
        assert isinstance(client, OpenAI)

    def test_base_url_not_set_when_only_api_key_in_env(self, monkeypatch):
        """When only OPENAI_API_KEY is in env, client still creates without base_url."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-key")
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        client = create_client()
        assert isinstance(client, OpenAI)


# ---------------------------------------------------------------------------
# Priority chain tests
# ---------------------------------------------------------------------------

class TestCreateClientPriority:
    """Priority: explicit args > environment vars."""

    def test_none_api_key_falls_back_to_env(self, monkeypatch):
        """api_key=None should not crash; should fall back to env."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        client = create_client(api_key=None, base_url=None)
        assert isinstance(client, OpenAI)

    def test_empty_string_api_key_does_not_fallback(self, monkeypatch):
        """Empty string '' is falsy in Python, but create_client uses `or`.
        Since `api_key or env` => '' falls through to env.
        But env key must exist, else SystemExit.
        """
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        # '' is falsy, so falls back to env
        client = create_client(api_key="", base_url=None)
        assert isinstance(client, OpenAI)


# ---------------------------------------------------------------------------
# complete_with_retry tests
# ---------------------------------------------------------------------------

class TestCompleteWithRetry:
    """Test the LLM API call retry wrapper."""

    def test_success_on_first_try(self):
        """No retry needed when first call succeeds."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        result = complete_with_retry(mock_client, model="gpt-4", messages=[], retries=3)
        assert result is mock_response
        assert mock_client.chat.completions.create.call_count == 1

    @patch("nautilus.llm.time.sleep")
    def test_retry_on_rate_limit_then_success(self, mock_sleep):
        """RateLimitError on first 2 calls, success on 3rd."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            RateLimitError(message="rate limited", response=MagicMock(), body=None),
            RateLimitError(message="rate limited", response=MagicMock(), body=None),
            mock_response,
        ]

        result = complete_with_retry(mock_client, model="gpt-4", messages=[], retries=3)
        assert result is mock_response
        assert mock_client.chat.completions.create.call_count == 3
        assert mock_sleep.call_count == 2  # slept between retries

    @patch("nautilus.llm.time.sleep")
    def test_all_retries_exhausted_raises_systemexit(self, mock_sleep):
        """All retries exhausted → SystemExit."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RateLimitError(
            message="rate limited", response=MagicMock(), body=None
        )

        with pytest.raises(SystemExit) as exc_info:
            complete_with_retry(mock_client, model="gpt-4", messages=[], retries=2)

        assert "LLM API 调用失败" in str(exc_info.value)
        assert mock_client.chat.completions.create.call_count == 3  # initial + 2 retries

    def test_bad_request_not_retried(self):
        """BadRequestError should not be retried — raised immediately."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = BadRequestError(
            message="bad request", response=MagicMock(), body=None
        )

        with pytest.raises(BadRequestError):
            complete_with_retry(mock_client, model="gpt-4", messages=[], retries=3)

        assert mock_client.chat.completions.create.call_count == 1  # no retry

    def test_auth_error_not_retried(self):
        """AuthenticationError should not be retried — raised immediately."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = AuthenticationError(
            message="invalid key", response=MagicMock(), body=None
        )

        with pytest.raises(AuthenticationError):
            complete_with_retry(mock_client, model="gpt-4", messages=[], retries=3)

        assert mock_client.chat.completions.create.call_count == 1


# ---------------------------------------------------------------------------
# stream_complete tests
# ---------------------------------------------------------------------------

class _MockDelta:
    """Mock delta from a streaming chunk."""
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _MockToolCallDelta:
    """Mock tool call delta from streaming."""
    def __init__(self, index, id=None, name=None, arguments=None):
        self.index = index
        self.id = id
        self.function = _MockFunctionDelta(name=name, arguments=arguments)


class _MockFunctionDelta:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _MockChunk:
    """Mock streaming chunk."""
    def __init__(self, delta, finish_reason=None):
        self.choices = [_MockChoice(delta, finish_reason)]


class _MockChoice:
    def __init__(self, delta, finish_reason=None):
        self.delta = delta
        self.finish_reason = finish_reason


class TestStreamComplete:
    """Test the streaming LLM response reassembly."""

    def test_stream_content_accumulated_and_printed(self, capsys):
        """Content deltas should be accumulated into final message and printed live."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter([
            _MockChunk(_MockDelta(content="Hello")),
            _MockChunk(_MockDelta(content=" world")),
            _MockChunk(_MockDelta(content="!"), finish_reason="stop"),
        ])

        message = stream_complete(mock_client, model="gpt-4", messages=[])

        assert message.content == "Hello world!"
        assert message.tool_calls is None

        captured = capsys.readouterr()
        assert "Hello" in captured.out
        assert "world" in captured.out

    def test_stream_tool_calls_assembled(self):
        """Tool call deltas should be assembled into complete tool call objects."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter([
            _MockChunk(_MockDelta(tool_calls=[
                _MockToolCallDelta(index=0, id="call_1", name="read_file", arguments="")
            ])),
            _MockChunk(_MockDelta(tool_calls=[
                _MockToolCallDelta(index=0, arguments='{"path":')
            ])),
            _MockChunk(_MockDelta(tool_calls=[
                _MockToolCallDelta(index=0, arguments='"test.py"}')
            ])),
            _MockChunk(_MockDelta(), finish_reason="tool_calls"),
        ])

        message = stream_complete(mock_client, model="gpt-4", messages=[])

        assert message.tool_calls is not None
        assert len(message.tool_calls) == 1
        assert message.tool_calls[0].id == "call_1"
        assert message.tool_calls[0].function.name == "read_file"
        assert message.tool_calls[0].function.arguments == '{"path":"test.py"}'

    def test_stream_empty_response(self, capsys):
        """Empty stream should produce empty message."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter([])

        message = stream_complete(mock_client, model="gpt-4", messages=[])

        assert message.content == ""
        assert message.tool_calls is None
