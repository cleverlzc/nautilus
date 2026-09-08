"""The core ReAct loop — the heart of the mini coding agent."""

import json
import re

from .llm import create_client, complete_with_retry, stream_complete
from .prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_TEXT_MODE
from .tools import TOOL_SCHEMAS, execute_tool


def _estimate_tokens(text: str) -> int:
    """Approximate token count without external tokenizers.

    Heuristic: ~4 chars/token for ASCII (English/code), ~2 chars/token for CJK.
    """
    if not text:
        return 0
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    non_ascii = len(text) - ascii_chars
    return ascii_chars // 4 + non_ascii // 2


def _truncate(text: str, limit: int = 2000) -> str:
    """Truncate long tool outputs for terminal display."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [已截断，共 {len(text)} 字符]"


def _truncate_for_llm(text: str, max_chars: int = 6000) -> str:
    """Truncate tool output before feeding to LLM to control context window usage.

    Unlike _truncate (display-only), this adds a bilingual marker so the LLM
    knows the output was cut and can request more if needed.
    """
    if len(text) <= max_chars:
        return text
    return (
        text[:max_chars]
        + f"\n... [输出已截断，共 {len(text)} 字符，仅保留前 {max_chars} 字符]"
        + f" [Output truncated, {len(text)}→{max_chars} chars]"
    )


def _print_tool_call(name: str, args: dict) -> None:
    """Print a one-line summary of the tool call."""
    if name == "read_file":
        print(f'🔧 read_file("{args.get("path", "")}")')
    elif name == "write_file":
        path = args.get("path", "")
        content = args.get("content", "")
        print(f'🔧 write_file("{path}", <{len(content)} 字符>)')
    elif name == "edit_file":
        path = args.get("path", "")
        old_len = len(args.get("old_string", ""))
        new_len = len(args.get("new_string", ""))
        print(f'🔧 edit_file("{path}", old: <{old_len} 字符>, new: <{new_len} 字符>)')
    elif name == "glob":
        print(f'🔧 glob("{args.get("pattern", "")}")')
    elif name == "grep":
        print(f'🔧 grep("{args.get("pattern", "")}")')
    elif name == "bash":
        print(f'🔧 bash("{args.get("command", "")}")')
    else:
        print(f"🔧 {name}({args})")


# ---------------------------------------------------------------------------
# Text-mode tool call parsing (for models without native function calling)
# ---------------------------------------------------------------------------

# Matches: ```tool_call\n{...json...}\n```  or  ```tool_call\r\n{...}\r\n```
_TOOL_CALL_RE = re.compile(r"```tool_call\s*\n(.*?)\n```", re.DOTALL)
# Also matches bare ```tool_call {json}``` on a single line
_TOOL_CALL_RE_ALT = re.compile(r"```tool_call\s+(\{.*?\})\s*```", re.DOTALL)


class _TextModeToolCall:
    """Simulated tool call object compatible with execute_tool."""
    def __init__(self, call_id: str, name: str, arguments: str):
        self.id = call_id
        self.function = _TextModeFunction(name, arguments)


class _TextModeFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


def _parse_tool_calls_from_text(content: str) -> list:
    """Parse tool calls from model text output in text mode.

    Looks for ```tool_call ... ``` blocks containing JSON.
    Returns list of _TextModeToolCall objects, or empty list if none found.
    """
    tool_calls = []

    # Try multi-line format first: ```tool_call\n{json}\n```
    for match in _TOOL_CALL_RE.finditer(content):
        json_str = match.group(1).strip()
        try:
            data = json.loads(json_str)
            name = data.get("name", "")
            args = data.get("args", data)
            tool_calls.append(_TextModeToolCall(
                call_id=f"text_call_{len(tool_calls)}",
                name=name,
                arguments=json.dumps(args, ensure_ascii=False),
            ))
        except (json.JSONDecodeError, KeyError):
            continue

    # If no multi-line matches, try single-line format
    if not tool_calls:
        for match in _TOOL_CALL_RE_ALT.finditer(content):
            json_str = match.group(1).strip()
            try:
                data = json.loads(json_str)
                name = data.get("name", "")
                args = data.get("args", data)
                tool_calls.append(_TextModeToolCall(
                    call_id=f"text_call_{len(tool_calls)}",
                    name=name,
                    arguments=json.dumps(args, ensure_ascii=False),
                ))
            except (json.JSONDecodeError, KeyError):
                continue

    return tool_calls


def run_agent(
    prompt: str,
    model: str = "gpt-4",
    api_key: str | None = None,
    base_url: str | None = None,
    max_iter: int = 20,
    max_tool_output_chars: int = 6000,
    stream: bool = False,
    approval: bool = False,
    text_mode: bool = False,
) -> None:
    """Run the agent loop: think → act → observe → repeat until done.

    When text_mode=True, uses prompt-based tool calling instead of OpenAI
    function calling. This enables compatibility with models that don't
    support native tool_calls (e.g., deepseek-r1 on Ollama).
    """
    client = create_client(api_key=api_key, base_url=base_url)
    system_prompt = SYSTEM_PROMPT_TEXT_MODE if text_mode else SYSTEM_PROMPT
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    for i in range(max_iter):
        # In text mode, don't pass tools= to the API (model uses prompt-based calling)
        api_kwargs = {"model": model, "messages": messages}
        if not text_mode:
            api_kwargs["tools"] = TOOL_SCHEMAS

        if stream:
            message = stream_complete(client, **api_kwargs)
        else:
            response = complete_with_retry(client, **api_kwargs)
            message = response.choices[0].message

        # In text mode, parse tool calls from the text content
        if text_mode:
            tool_calls = _parse_tool_calls_from_text(message.content or "")
            message.tool_calls = tool_calls if tool_calls else None

        # If the model didn't call any tool, this is the final answer.
        if not message.tool_calls:
            if message.content and not stream:
                print(f"\n✅ {message.content}")
            elif message.content and stream:
                print("\n✅ (流式输出完成)")
            return

        # Print assistant thinking if present (non-stream mode; stream already printed).
        # In text mode, strip the tool_call block from display.
        display_content = message.content or ""
        if text_mode:
            display_content = _TOOL_CALL_RE.sub("", display_content).strip()
        if display_content and not stream:
            print(f"💭 {display_content}")

        # Append the assistant's message to history.
        # In text mode, append as a plain dict (no tool_calls field for API).
        # In stream mode (native), _StreamedMessage is not JSON-serializable by the SDK,
        # so convert to dict with tool_calls in OpenAI format.
        if text_mode:
            messages.append({"role": "assistant", "content": message.content})
        elif stream:
            msg_dict = {"role": "assistant", "content": message.content}
            if message.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]
            messages.append(msg_dict)
        else:
            messages.append(message)

        # Execute each tool call and feed results back.
        for call in message.tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": call.function.arguments}

            _print_tool_call(call.function.name, args)

            # Permission prompt for bash commands (if approval enabled).
            if approval and call.function.name == "bash":
                command = args.get("command", "")
                user_input = input(f"   执行此命令? [y/N]: ").strip().lower()
                if user_input not in ("y", "yes"):
                    result = f"用户拒绝了该命令：{command}"
                    print(f"   → {result}\n")
                    if text_mode:
                        messages.append({"role": "user", "content": f"[工具结果] {result}"})
                    else:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": _truncate_for_llm(result, max_tool_output_chars),
                            }
                        )
                    continue

            result = execute_tool(call)
            print(f"   → {_truncate(result)}\n")

            # In text mode, feed results back as user messages (no tool_call_id)
            if text_mode:
                truncated = _truncate_for_llm(result, max_tool_output_chars)
                messages.append({"role": "user", "content": f"[工具结果] {truncated}"})
            else:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": _truncate_for_llm(result, max_tool_output_chars),
                    }
                )

    print(f"\n⚠️  达到最大迭代次数 ({max_iter})，agent 终止。")
