"""Memory system for cross-session context persistence."""

import os


def load_memory(path: str = ".nautilus/memory.md") -> str:
    """读取记忆文件，返回内容字符串。无文件返回空字符串。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, OSError):
        return ""


def save_memory(path: str, content: str) -> str:
    """保存记忆内容到文件。自动创建父目录。"""
    try:
        parent = os.path.dirname(path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"记忆已保存到 {path}"
    except Exception as e:
        return f"错误：保存记忆失败：{e}"


def append_memory(path: str, entry: str) -> str:
    """追加一条记忆条目到记忆文件。自动创建父目录。"""
    try:
        parent = os.path.dirname(path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry)
            if not entry.endswith("\n"):
                f.write("\n")
        return f"记忆已追加到 {path}"
    except Exception as e:
        return f"错误：追加记忆失败：{e}"
