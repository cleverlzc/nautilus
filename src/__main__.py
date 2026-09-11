"""CLI entry point for Nautilus coding agent.

Usage:
    nautilus "创建一个 hello.py"
    nautilus --model qwen-plus --base-url https://xxx "修复 bug"
    nautilus --max-iter 30 "重构 utils.py"
"""

import argparse
import sys

# Ensure stdout/stderr use UTF-8 encoding (fixes Windows GBK crash on emoji)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from .agent import run_agent


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="nautilus",
        description="Nautilus — 鹦鹉螺：螺旋逼近答案的 coding agent",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="要交给 agent 的任务描述。不传则从 stdin 读取（支持管道）。",
    )
    parser.add_argument(
        "--model",
        default="gpt-4",
        help="模型名（默认 gpt-4）。OpenAI 兼容 API 可填 qwen-plus 等。",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key。不传则读 OPENAI_API_KEY 环境变量。",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="API base URL。不传则读 OPENAI_BASE_URL 环境变量。",
    )
    parser.add_argument(
        "--max-iter",
        type=int,
        default=20,
        help="agent 循环最大迭代次数（默认 20）。",
    )
    parser.add_argument(
        "--max-tool-output",
        type=int,
        default=6000,
        help="单次工具结果回灌 LLM 的最大字符数（默认 6000，约 1500 tokens）。",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        default=False,
        help="启用流式输出，实时打印 LLM 生成的 token。",
    )
    parser.add_argument(
        "--approval",
        action="store_true",
        default=False,
        help="启用权限审批模式，bash 命令执行前需用户确认。",
    )
    parser.add_argument(
        "--text-mode",
        action="store_true",
        default=False,
        help="启用文本模式工具调用（兼容不支持 function calling 的模型，如 deepseek-r1）。",
    )
    parser.add_argument(
        "--max-context-tokens",
        type=int,
        default=32000,
        help="对话历史的 token 预算（默认 32000，超出后丢弃最旧迭代）。",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        default=False,
        help="启用 plan mode：先生成执行计划，用户确认后再执行。",
    )
    parser.add_argument(
        "--memory",
        default=None,
        help="启用记忆系统，指定记忆文件路径（如 .nautilus/memory.md）。不传则不启用。",
    )
    parser.add_argument(
        "--skills-dir",
        default=None,
        help="启用 Skills 系统，指定 skills 目录路径（如 .nautilus/skills）。不传则不启用。",
    )
    parser.add_argument(
        "--mcp-server",
        action="append",
        default=None,
        help="连接 MCP server（可多次指定）。如 --mcp-server 'npx @mcp/filesystem'",
    )

    args = parser.parse_args()

    # Get prompt from positional arg or stdin.
    prompt = args.prompt
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()

    if not prompt:
        parser.print_help()
        sys.exit(1)

    run_agent(
        prompt=prompt,
        model=args.model,
        api_key=args.api_key,
        base_url=args.base_url,
        max_iter=args.max_iter,
        max_tool_output_chars=args.max_tool_output,
        stream=args.stream,
        approval=args.approval,
        text_mode=args.text_mode,
        max_context_tokens=args.max_context_tokens,
        plan_mode=args.plan,
        memory_path=args.memory,
        skills_dir=args.skills_dir,
        mcp_servers=args.mcp_server,
    )


if __name__ == "__main__":
    main()
