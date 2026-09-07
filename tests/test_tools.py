"""Unit tests for nautilus.tools — tool functions + execute_tool router.

Covers:
- read_file: normal read, non-existent file, binary file
- write_file: normal write, auto-create parent dirs
- edit_file: normal edit, old_string not found, multiple matches
- bash: success, non-zero exit, stderr capture
- execute_tool: routing for all 4 tools, unknown tool, invalid JSON, empty args
"""

import json
import os
import tempfile

import pytest

from nautilus.tools import (
    TOOL_SCHEMAS,
    bash,
    edit_file,
    execute_tool,
    read_file,
    write_file,
)


# ---------------------------------------------------------------------------
# Mock tool_call object (mimics OpenAI ChatCompletionMessageToolCall)
# ---------------------------------------------------------------------------

class MockFunction:
    """Mimics openai.types.chat.chat_completion_message_tool_call.Function."""

    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class MockToolCall:
    """Mimics openai.types.chat.ChatCompletionMessageToolCall."""

    def __init__(self, call_id: str, name: str, arguments: str):
        self.id = call_id
        self.function = MockFunction(name, arguments)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_file(tmp_path):
    """Return a path inside a temp directory for testing file operations."""
    return str(tmp_path / "test_file.py")


# ---------------------------------------------------------------------------
# write_file tests
# ---------------------------------------------------------------------------

class TestWriteFile:
    def test_write_normal(self, tmp_file):
        result = write_file(tmp_file, 'print("hello")')
        assert "成功" in result
        assert os.path.exists(tmp_file)

    def test_write_returns_byte_count(self, tmp_file):
        result = write_file(tmp_file, "abc")
        assert "3 字节" in result

    def test_auto_create_parent_dirs(self, tmp_path):
        nested = str(tmp_path / "sub" / "dir" / "file.txt")
        result = write_file(nested, "nested content")
        assert "成功" in result
        assert os.path.exists(nested)

    def test_overwrite_existing(self, tmp_file):
        write_file(tmp_file, "old content")
        result = write_file(tmp_file, "new content")
        assert "成功" in result
        assert read_file(tmp_file) == "new content"


# ---------------------------------------------------------------------------
# read_file tests
# ---------------------------------------------------------------------------

class TestReadFile:
    def test_read_normal(self, tmp_file):
        write_file(tmp_file, "line1\nline2")
        assert read_file(tmp_file) == "line1\nline2"

    def test_read_nonexistent(self, tmp_path):
        path = str(tmp_path / "nonexistent.py")
        result = read_file(path)
        assert "错误" in result
        assert "文件不存在" in result

    def test_read_binary_file(self, tmp_path):
        path = str(tmp_path / "binary.bin")
        with open(path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
        result = read_file(path)
        assert "错误" in result
        assert "utf-8" in result or "解码" in result


# ---------------------------------------------------------------------------
# edit_file tests
# ---------------------------------------------------------------------------

class TestEditFile:
    def test_edit_normal(self, tmp_file):
        write_file(tmp_file, 'print("hello")')
        result = edit_file(tmp_file, 'print("hello")', 'print("world")')
        assert "成功" in result
        assert read_file(tmp_file) == 'print("world")'

    def test_edit_old_string_not_found(self, tmp_file):
        write_file(tmp_file, "existing content")
        result = edit_file(tmp_file, "nonexistent text", "something")
        assert "错误" in result
        assert "找不到" in result

    def test_edit_multiple_matches(self, tmp_file):
        write_file(tmp_file, "x = 1\nx = 1\n")
        result = edit_file(tmp_file, "x = 1", "x = 2")
        assert "错误" in result
        assert "2 处匹配" in result

    def test_edit_nonexistent_file(self, tmp_path):
        path = str(tmp_path / "missing.py")
        result = edit_file(path, "old", "new")
        assert "错误" in result
        assert "文件不存在" in result

    def test_edit_preserves_surrounding_content(self, tmp_file):
        write_file(tmp_file, "line1\ntarget\nline3")
        result = edit_file(tmp_file, "target", "replaced")
        assert "成功" in result
        content = read_file(tmp_file)
        assert "line1" in content
        assert "replaced" in content
        assert "line3" in content


# ---------------------------------------------------------------------------
# bash tests
# ---------------------------------------------------------------------------

class TestBash:
    def test_echo_success(self):
        result = bash("echo hello_bash")
        assert "hello_bash" in result
        assert "exit code: 0" in result

    def test_python_execution(self):
        result = bash('python -c "print(42)"')
        assert "42" in result
        assert "exit code: 0" in result

    def test_nonzero_exit(self):
        result = bash("exit 1")
        assert "exit code: 1" in result

    def test_stderr_capture(self):
        result = bash("echo error_msg >&2")
        assert "error_msg" in result
        assert "exit code: 0" in result

    def test_command_output_includes_both_streams(self):
        result = bash('echo stdout_line && echo stderr_line >&2')
        assert "stdout_line" in result
        assert "stderr_line" in result


# ---------------------------------------------------------------------------
# execute_tool router tests
# ---------------------------------------------------------------------------

class TestExecuteTool:
    def test_route_write_file(self, tmp_file):
        call = MockToolCall("c1", "write_file",
                            json.dumps({"path": tmp_file, "content": "hello"}))
        result = execute_tool(call)
        assert "成功" in result
        assert os.path.exists(tmp_file)

    def test_route_read_file(self, tmp_file):
        write_file(tmp_file, "content here")
        call = MockToolCall("c2", "read_file", json.dumps({"path": tmp_file}))
        assert execute_tool(call) == "content here"

    def test_route_edit_file(self, tmp_file):
        write_file(tmp_file, "old")
        call = MockToolCall("c3", "edit_file",
                            json.dumps({"path": tmp_file, "old_string": "old", "new_string": "new"}))
        result = execute_tool(call)
        assert "成功" in result
        assert read_file(tmp_file) == "new"

    def test_route_bash(self):
        call = MockToolCall("c4", "bash", json.dumps({"command": "echo routed"}))
        result = execute_tool(call)
        assert "routed" in result

    def test_unknown_tool(self):
        call = MockToolCall("c5", "unknown_tool", json.dumps({}))
        result = execute_tool(call)
        assert "错误" in result
        assert "未知工具" in result

    def test_invalid_json_arguments(self):
        call = MockToolCall("c6", "read_file", "{invalid json}")
        result = execute_tool(call)
        assert "错误" in result
        assert "解析失败" in result

    def test_empty_arguments_string(self):
        call = MockToolCall("c7", "read_file", "")
        result = execute_tool(call)
        # Empty args -> args defaults to {}, path defaults to "" -> file not found
        assert "错误" in result

    def test_none_arguments(self):
        call = MockToolCall("c8", "read_file", None)
        result = execute_tool(call)
        # None args -> json.loads("{}") -> path="" -> file not found
        assert "错误" in result


# ---------------------------------------------------------------------------
# TOOL_SCHEMAS structure tests
# ---------------------------------------------------------------------------

class TestToolSchemas:
    def test_schema_count(self):
        assert len(TOOL_SCHEMAS) == 4

    def test_schema_names(self):
        names = {s["function"]["name"] for s in TOOL_SCHEMAS}
        assert names == {"read_file", "write_file", "edit_file", "bash"}

    @pytest.mark.parametrize("tool_name,expected_params", [
        ("read_file", ["path"]),
        ("write_file", ["path", "content"]),
        ("edit_file", ["path", "old_string", "new_string"]),
        ("bash", ["command"]),
    ])
    def test_schema_parameters(self, tool_name, expected_params):
        schema = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == tool_name)
        params = list(schema["function"]["parameters"]["properties"].keys())
        assert params == expected_params

    @pytest.mark.parametrize("tool_name", ["read_file", "write_file", "edit_file", "bash"])
    def test_schema_has_required(self, tool_name):
        schema = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == tool_name)
        required = schema["function"]["parameters"].get("required", [])
        assert len(required) > 0

    @pytest.mark.parametrize("tool_name", ["read_file", "write_file", "edit_file", "bash"])
    def test_schema_has_description(self, tool_name):
        schema = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == tool_name)
        assert schema["function"]["description"]

    def test_all_schemas_are_function_type(self):
        for schema in TOOL_SCHEMAS:
            assert schema["type"] == "function"
