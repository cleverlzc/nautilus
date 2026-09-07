"""OpenAI-compatible API client factory."""

import os

from openai import OpenAI


def create_client(api_key: str | None = None, base_url: str | None = None) -> OpenAI:
    """Create an OpenAI client. Priority: explicit args > environment vars."""
    key = api_key or os.environ.get("OPENAI_API_KEY")
    url = base_url or os.environ.get("OPENAI_BASE_URL")
    if not key:
        raise SystemExit(
            "未提供 API key。请设置 OPENAI_API_KEY 环境变量，或用 --api-key 参数传入。"
        )
    kwargs = {"api_key": key}
    if url:
        kwargs["base_url"] = url
    return OpenAI(**kwargs)
