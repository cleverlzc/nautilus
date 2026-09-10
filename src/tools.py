"""Tool definitions and execution router for the coding agent."""

import fnmatch
import json
import os
import re
import subprocess
from pathlib import Path


# OpenAI function-calling schema for the core tools.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容（utf-8 文本文件）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径（相对或绝对）。",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入文件。如果父目录不存在会自动创建。已存在则覆盖。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件路径。",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的完整内容。",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "精确修改文件内容。通过查找 old_string 并替换为 new_string 来实现局部修改，避免整文件重写。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要修改的文件路径。",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "要替换的原始文本（必须精确匹配）。",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "替换后的新文本。",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "递归搜索匹配指定模式的文件路径。支持 glob 通配符（*.py, **/*.ts 等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "文件名匹配模式，如 *.py、**/*.ts。",
                    },
                    "root": {
                        "type": "string",
                        "description": "搜索根目录（默认当前目录）。",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "在文件中搜索匹配指定正则的行，返回 path:lineno:line 格式。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "正则表达式搜索模式。",
                    },
                    "path": {
                        "type": "string",
                        "description": "限定搜索的文件路径（可选，不传则搜索整个 root）。",
                    },
                    "root": {
                        "type": "string",
                        "description": "搜索根目录（默认当前目录）。",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "执行 shell 命令，返回 stdout+stderr。30 秒超时。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令。",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_task",
            "description": "将子任务委派给独立子 agent 执行，隔离上下文。子 agent 有独立的对话历史，完成后只返回最终结果，不污染主循环。适用于需要多步工具调用的独立子任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "子任务描述。应包含足够上下文让子 agent 独立完成。",
                    }
                },
                "required": ["prompt"],
            },
        },
    },
]


def read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"错误：文件不存在：{path}"
    except UnicodeDecodeError:
        return f"错误：无法以 utf-8 解码（可能是二进制文件）：{path}"
    except Exception as e:
        return f"错误：读取失败：{e}"


def write_file(path: str, content: str) -> str:
    try:
        parent = os.path.dirname(path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        size = len(content.encode("utf-8"))
        return f"成功写入 {size} 字节到 {path}"
    except Exception as e:
        return f"错误：写入失败：{e}"


def edit_file(path: str, old_string: str, new_string: str) -> str:
    """精确替换文件中的指定文本。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return f"错误：文件不存在：{path}"
    except UnicodeDecodeError:
        return f"错误：无法以 utf-8 解码（可能是二进制文件）：{path}"
    except Exception as e:
        return f"错误：读取失败：{e}"

    if old_string not in content:
        return f"错误：在文件中找不到要替换的文本。请确认 old_string 与文件内容完全匹配。"

    count = content.count(old_string)
    if count > 1:
        return f"错误：找到 {count} 处匹配。请提供更多上下文以确保唯一匹配。"

    new_content = content.replace(old_string, new_string, 1)

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"成功修改 {path}"
    except Exception as e:
        return f"错误：写入失败：{e}"


# Patterns that indicate potentially destructive shell commands.
# If matched and not --approval, the command is blocked with a warning.
_DANGEROUS_PATTERNS = [
    "rm -rf /",
    "rm -rf ~",
    "rm -rf *",
    "rm -rf .",
    "rmdir /s /q",
    "format c:",
    "format /fs:",
    "mkfs.",
    "dd if=/dev/zero",
    "dd if=/dev/random",
    ":(){:|:&};:",
    "shutdown",
    "reboot",
    "halt",
    "init 0",
    "init 6",
]


def _check_dangerous(command: str) -> str | None:
    """Return a warning message if the command matches a dangerous pattern, else None."""
    lower = command.lower().strip()
    for pattern in _DANGEROUS_PATTERNS:
        if pattern in lower:
            return (
                f"⚠️ 危险命令检测：命令匹配危险模式 '{pattern}'。"
                f"如需执行，请使用 --approval 模式并确认。"
            )
    return None


def bash(command: str, allow_dangerous: bool = False) -> str:
    # Check for dangerous commands (unless explicitly allowed via --approval)
    if not allow_dangerous:
        warning = _check_dangerous(command)
        if warning:
            return warning
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n[stderr]\n" if output else "") + result.stderr
        output += f"\n[exit code: {result.returncode}]"
        return output.strip() or f"[exit code: {result.returncode}]"
    except subprocess.TimeoutExpired:
        return "错误：命令执行超过 30 秒超时"
    except Exception as e:
        return f"错误：执行失败：{e}"


def _load_gitignore(root: str = ".") -> list[str]:
    """读取 .gitignore，返回 pattern 列表。无 .gitignore 则返回空列表。"""
    gitignore_path = os.path.join(root, ".gitignore")
    patterns = []
    try:
        with open(gitignore_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line.rstrip("/"))
    except (FileNotFoundError, OSError):
        pass
    return patterns


def _is_ignored(path: str, patterns: list[str]) -> bool:
    """检查路径是否被 gitignore 规则匹配。支持基础模式（*.log, node_modules, dist）。"""
    if not patterns:
        return False
    basename = os.path.basename(path)
    for pattern in patterns:
        if fnmatch.fnmatch(basename, pattern) or fnmatch.fnmatch(path, pattern):
            return True
        # 匹配路径中的任意目录段
        parts = path.replace("\\", "/").split("/")
        for part in parts:
            if fnmatch.fnmatch(part, pattern):
                return True
    return False


def glob(pattern: str, root: str = ".") -> str:
    """递归匹配文件路径，返回匹配的文件列表（最多 200 条）。"""
    try:
        gitignore_patterns = _load_gitignore(root)
        results = []
        base = Path(root)
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(base)).replace("\\", "/")
            if _is_ignored(rel, gitignore_patterns):
                continue
            # 匹配 pattern：支持 basename 和 ** 前缀
            if fnmatch.fnmatch(p.name, pattern) or fnmatch.fnmatch(rel, pattern):
                results.append(rel)
            if len(results) >= 200:
                results.append(f"... [结果过多，仅显示前 200 条]")
                break
        if not results:
            return "未找到匹配文件。"
        return "\n".join(results)
    except Exception as e:
        return f"错误：搜索失败：{e}"


def grep(pattern: str, path: str | None = None, root: str = ".") -> str:
    """在文件中搜索匹配指定正则的行，返回 path:lineno:line 格式（最多 100 条）。"""
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"错误：正则表达式无效：{e}"

    try:
        gitignore_patterns = _load_gitignore(root)
        results = []
        base = Path(root)

        if path:
            # 限定搜索单个文件
            target = Path(path)
            files_to_search = [target if target.is_absolute() else base / target]
        else:
            # 递归搜索整个 root
            files_to_search = [p for p in base.rglob("*") if p.is_file()]

        for filepath in files_to_search:
            rel = str(filepath.relative_to(base)) if filepath.is_relative_to(base) else str(filepath)
            if _is_ignored(rel.replace("\\", "/"), gitignore_patterns):
                continue
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for lineno, line in enumerate(f, 1):
                        if regex.search(line):
                            results.append(f"{rel}:{lineno}:{line.rstrip()}")
                            if len(results) >= 100:
                                results.append(f"... [匹配过多，仅显示前 100 条]")
                                return "\n".join(results)
            except (UnicodeDecodeError, OSError):
                continue  # 跳过二进制文件和不可读文件

        if not results:
            return "未找到匹配行。"
        return "\n".join(results)
    except Exception as e:
        return f"错误：搜索失败：{e}"


def execute_tool(tool_call, allow_dangerous: bool = False) -> str:
    """Route a tool call to the right function and return its result as a string.

    When allow_dangerous=True, bypass dangerous command filtering (used by --approval).
    """
    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments or "{}")
    except json.JSONDecodeError as e:
        return f"错误：工具参数解析失败：{e}"

    if name == "read_file":
        return read_file(args.get("path", ""))
    if name == "write_file":
        return write_file(args.get("path", ""), args.get("content", ""))
    if name == "edit_file":
        return edit_file(
            args.get("path", ""),
            args.get("old_string", ""),
            args.get("new_string", ""),
        )
    if name == "glob":
        return glob(args.get("pattern", ""), args.get("root", "."))
    if name == "grep":
        return grep(args.get("pattern", ""), args.get("path"), args.get("root", "."))
    if name == "bash":
        return bash(args.get("command", ""), allow_dangerous=allow_dangerous)
    return f"错误：未知工具：{name}"
