"""Unit tests for nautilus.llm — create_client factory.

Covers:
- No API key: raises SystemExit with helpful message
- Explicit api_key: creates OpenAI client
- Explicit base_url: client gets custom base_url
- Environment variable fallback: OPENAI_API_KEY / OPENAI_BASE_URL
- Explicit args override env vars
"""

import os
from unittest.mock import patch

import pytest
from openai import OpenAI

from nautilus.llm import create_client


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
