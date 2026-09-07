"""The core ReAct loop — the heart of the mini coding agent."""

from .llm import create_client
from .prompts import SYSTEM_PROMPT
from .tools import TOOL_SCHEMAS, execute_tool


def _truncate(text: str, limit: int = 2000) -> str:
    """Truncate long tool outputs for terminal display."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [已截断，共 {len(text)} 字符]"


def _print_tool_call(name: str, args: dict) -> None:
    """Print a one-line summary of the tool call."""
    if name == "read_file":
        print(f'🔧 read_file("{args.get("path", "")}")')
    elif name == "write_file":
        path = args.get("path", "")
        content = args.get("content", "")
        print(f'🔧 write_file("{path}", <{len(content)} 字符>)')
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

        # Append the assistant's thinking+tool_calls to history (required by the API).
        messages.append(message)

        # Execute each tool call and feed results back.
        for call in message.tool_calls:
            import json

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
                    "content": result,
                }
            )

    print(f"\n⚠️  达到最大迭代次数 ({max_iter})，agent 终止。")
