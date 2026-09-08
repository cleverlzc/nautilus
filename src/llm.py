"""OpenAI-compatible API client factory and retry wrapper."""

import os
import time

from openai import (
    OpenAI,
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
    BadRequestError,
    AuthenticationError,
)


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


# Transient errors worth retrying
_RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


def complete_with_retry(client, *, retries: int = 3, stream: bool = False, **kwargs):
    """Call LLM API with exponential backoff retry on transient errors.

    Non-transient errors (BadRequestError, AuthenticationError) are raised immediately.
    After exhausting retries, raises SystemExit with a helpful message.

    When stream=True, returns a chunk iterator; caller must handle reassembly.
    """
    last_error = None
    for attempt in range(retries + 1):
        try:
            return client.chat.completions.create(stream=stream, **kwargs)
        except _RETRYABLE_ERRORS as e:
            last_error = e
            if attempt < retries:
                wait = min(2 ** attempt, 8)
                print(f"🔄 LLM API 重试 (第 {attempt + 1}/{retries} 次)，等待 {wait}s... ({type(e).__name__})")
                time.sleep(wait)
            else:
                raise SystemExit(
                    f"LLM API 调用失败，已重试 {retries} 次。最后错误：{type(e).__name__}: {e}"
                )
        except (BadRequestError, AuthenticationError):
            raise  # Non-transient, don't retry


class _StreamedToolCall:
    """Reassembled tool call from streaming deltas."""
    def __init__(self, call_id: str):
        self.id = call_id
        self.type = "function"
        self.function = _StreamedFunction()


class _StreamedFunction:
    """Reassembled function call from streaming deltas."""
    def __init__(self):
        self.name = ""
        self.arguments = ""


class _StreamedMessage:
    """Reassembled message from streaming chunks."""
    def __init__(self):
        self.content = ""
        self.tool_calls = None


def stream_complete(client, *, retries: int = 3, **kwargs):
    """Stream LLM response, print content tokens live, return assembled message.

    Reassembles delta chunks into a message object compatible with the agent loop.
    Tool call deltas are accumulated into _StreamedToolCall objects that expose
    .id, .function.name, .function.arguments (same interface as SDK objects).
    """
    kwargs["stream"] = True
    stream = complete_with_retry(client, retries=retries, **kwargs)

    message = _StreamedMessage()
    tool_calls_map = {}  # index → _StreamedToolCall

    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        # Accumulate content and print live
        if delta.content:
            message.content += delta.content
            print(delta.content, end="", flush=True)

        # Accumulate tool calls
        if delta.tool_calls:
            if message.tool_calls is None:
                message.tool_calls = []
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in tool_calls_map:
                    tool_calls_map[idx] = _StreamedToolCall(tc_delta.id or "")
                    message.tool_calls.append(tool_calls_map[idx])
                if tc_delta.id:
                    tool_calls_map[idx].id = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        tool_calls_map[idx].function.name += tc_delta.function.name
                    if tc_delta.function.arguments:
                        tool_calls_map[idx].function.arguments += tc_delta.function.arguments

    print()  # newline after streamed content
    return message

