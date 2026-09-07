"""The core ReAct loop — the heart of the mini coding agent."""

import json

from .llm import create_client
from .prompts import SYSTEM_PROMPT
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
    elif name == "bash":
        print(f'🔧 bash("{args.get("command", "")}")')
    else:
        print(f"🔧 {name}({args})")


def run_agent(
    prompt: str,
    model: str = "gpt-4",
    api_key: str | None = None,
    base_url: str | None = None,
    max_iter: int = 20,
    max_tool_output_chars: int = 6000,
) -> None:
    """Run the agent loop: think → act → observe → repeat until done."""
    client = create_client(api_key=api_key, base_url=base_url)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    for i in range(max_iter):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOL_SCHEMAS,
        )
        message = response.choices[0].message

        # If the model didn't call any tool, this is the final answer.
        if not message.tool_calls:
            if message.content:
                print(f"\n✅ {message.content}")
            return

        # Print assistant thinking if present.
        if message.content:
            print(f"💭 {message.content}")

        # Append the assistant's thinking+tool_calls to history (required by the API).
        messages.append(message)

        # Execute each tool call and feed results back.
        for call in message.tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": call.function.arguments}

            _print_tool_call(call.function.name, args)
            result = execute_tool(call)
            print(f"   → {_truncate(result)}\n")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": _truncate_for_llm(result, max_tool_output_chars),
                }
            )

    print(f"\n⚠️  达到最大迭代次数 ({max_iter})，agent 终止。")
