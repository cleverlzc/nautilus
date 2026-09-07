"""Tool definitions and execution router for the mini coding agent."""

import json
import os
import subprocess


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


def bash(command: str) -> str:
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


def execute_tool(tool_call) -> str:
    """Route a tool call to the right function and return its result as a string."""
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
    if name == "bash":
        return bash(args.get("command", ""))
    return f"错误：未知工具：{name}"
