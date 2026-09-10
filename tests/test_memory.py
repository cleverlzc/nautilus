"""Unit tests for nautilus.memory — memory system.

Covers:
- load_memory: existing file / nonexistent / empty file
- save_memory: new file / overwrite / auto-create parent dir
- append_memory: append to existing / create new file / newline handling
- Memory integration: injection into system prompt / saving after completion
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from nautilus.memory import append_memory, load_memory, save_memory


# ---------------------------------------------------------------------------
# load_memory tests
# ---------------------------------------------------------------------------

class TestLoadMemory:
    def test_load_existing_memory(self, tmp_path):
        path = tmp_path / "memory.md"
        path.write_text("## 上次任务\n完成 hello.py\n", encoding="utf-8")
        result = load_memory(str(path))
        assert "上次任务" in result
        assert "hello.py" in result

    def test_load_nonexistent_memory(self, tmp_path):
        path = tmp_path / "nonexistent.md"
        result = load_memory(str(path))
        assert result == ""

    def test_load_empty_memory(self, tmp_path):
        path = tmp_path / "empty.md"
        path.write_text("", encoding="utf-8")
        result = load_memory(str(path))
        assert result == ""


# ---------------------------------------------------------------------------
# save_memory tests
# ---------------------------------------------------------------------------

class TestSaveMemory:
    def test_save_new_memory(self, tmp_path):
        path = tmp_path / "memory.md"
        result = save_memory(str(path), "## memory content\n")
        assert "成功" in result or "保存" in result
        assert path.exists()
        assert "memory content" in path.read_text(encoding="utf-8")

    def test_save_overwrite_memory(self, tmp_path):
        path = tmp_path / "memory.md"
        path.write_text("old content", encoding="utf-8")
        save_memory(str(path), "new content")
        assert path.read_text(encoding="utf-8") == "new content"

    def test_save_creates_parent_dir(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "memory.md"
        result = save_memory(str(path), "nested content")
        assert "保存" in result
        assert path.exists()
        assert "nested content" in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# append_memory tests
# ---------------------------------------------------------------------------

class TestAppendMemory:
    def test_append_to_existing(self, tmp_path):
        path = tmp_path / "memory.md"
        path.write_text("## task 1\ndone 1\n", encoding="utf-8")
        append_memory(str(path), "## task 2\ndone 2")
        content = path.read_text(encoding="utf-8")
        assert "task 1" in content
        assert "task 2" in content
        assert content.endswith("\n")

    def test_append_creates_new_file(self, tmp_path):
        path = tmp_path / "memory.md"
        append_memory(str(path), "## first task\nfirst result")
        content = path.read_text(encoding="utf-8")
        assert "first task" in content
        assert content.endswith("\n")

    def test_append_adds_newline(self, tmp_path):
        path = tmp_path / "memory.md"
        append_memory(str(path), "no trailing newline")
        content = path.read_text(encoding="utf-8")
        assert content.endswith("\n")

    def test_append_creates_parent_dir(self, tmp_path):
        path = tmp_path / ".nautilus" / "memory.md"
        append_memory(str(path), "## task\nresult")
        assert path.exists()
        assert "task" in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Memory integration tests
# ---------------------------------------------------------------------------

class TestMemoryIntegration:
    """Test memory injection into system prompt and saving after completion."""

    def test_memory_injected_into_system_prompt(self, tmp_path, capsys, monkeypatch):
        """Memory file content should appear in system prompt."""
        monkeypatch.chdir(tmp_path)
        memory_path = ".nautilus/memory.md"
        save_memory(memory_path, "## 上次任务\n创建了 hello.py\n")

        captured_messages = []

        def mock_create_fn(**kwargs):
            msgs = kwargs.get("messages", [])
            captured_messages.append(list(msgs))
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content="done", tool_calls=None))]
            )

        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create_fn

        with patch("nautilus.agent.create_client", return_value=mock_client):
            from nautilus.agent import run_agent
            run_agent(
                prompt="继续上次任务",
                model="mock-model",
                api_key="sk-fake",
                max_iter=5,
                memory_path=memory_path,
            )

        # System prompt should contain "项目记忆" and memory content
        assert len(captured_messages) >= 1
        system_msg = captured_messages[0][0]
        system_content = system_msg.get("content", "") if isinstance(system_msg, dict) else ""
        assert "项目记忆" in system_content
        assert "上次任务" in system_content
        assert "hello.py" in system_content

    def test_memory_saved_after_completion(self, tmp_path, capsys, monkeypatch):
        """After task completion, memory file should be appended with prompt + answer."""
        monkeypatch.chdir(tmp_path)
        memory_path = ".nautilus/memory.md"
        save_memory(memory_path, "## 上次\nold content\n")

        def mock_create_fn(**kwargs):
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content="任务完成：添加了 sqrt 函数", tool_calls=None))]
            )

        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create_fn

        with patch("nautilus.agent.create_client", return_value=mock_client):
            from nautilus.agent import run_agent
            run_agent(
                prompt="添加 sqrt 函数到 calc.py",
                model="mock-model",
                api_key="sk-fake",
                max_iter=5,
                memory_path=memory_path,
            )

        # Memory file should now contain both old and new entries
        content = open(memory_path, "r", encoding="utf-8").read()
        assert "上次" in content  # old memory
        assert "添加 sqrt 函数" in content  # new prompt
        assert "任务完成" in content  # new answer

    def test_memory_not_saved_when_disabled(self, tmp_path, capsys, monkeypatch):
        """When memory_path=None, no memory file should be created."""
        monkeypatch.chdir(tmp_path)

        def mock_create_fn(**kwargs):
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content="done", tool_calls=None))]
            )

        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create_fn

        with patch("nautilus.agent.create_client", return_value=mock_client):
            from nautilus.agent import run_agent
            run_agent(
                prompt="task",
                model="mock-model",
                api_key="sk-fake",
                max_iter=5,
                memory_path=None,
            )

        # No memory file should exist
        assert not os.path.exists(".nautilus/memory.md")
