# Nautilus v0.3.5 MCP 协议 — 实现计划

## Context

v0.3.4 已完成 Skills/插件（1346 行，191 tests + 3 E2E 场景）。`nautilus-v3-特性优先级排序.md` 将 MCP 协议列为 P4 特性——扩展机制，不直接打破瓶颈，ROI 最低但完成 v3 最后一块拼图。

当前代码基线（v0.3.4）：1346 行 Python 源码 + 191 tests。

v0.3.5 的目标：**让 agent 可接入外部工具服务器**——通过 MCP（Model Context Protocol）协议连接 MCP server（stdio 传输），动态发现并调用其提供的工具。扩展工具集，让 agent 的能力不再局限于 7 个内置工具。

## 项目位置

```
...\AIAgent\mycodingagent\nautilus\
```

## 问题分析

当前 agent 只有 7 个内置工具（read/write/edit/glob/grep/bash/delegate_task）。如果用户需要 agent 操作数据库、调用 API、读取 Jira ticket 等外部能力，只能通过 bash 间接实现——不安全且不标准。

MCP 协议解决方案：agent 启动时连接 MCP server（通过 stdio 子进程），动态发现 server 提供的工具 schema，合并到 `TOOL_SCHEMAS` 中。LLM 调用 MCP 工具时，agent 通过 JSON-RPC 2.0 协议转发请求到 MCP server，获取结果回灌 messages。

| 维度 | 无 MCP | 有 MCP |
|------|--------|--------|
| 工具集 | 7 个内置工具 | 7 + N 个 MCP 工具（动态扩展） |
| 外部能力 | 仅 bash 间接操作 | 标准 JSON-RPC 协议直接调用 |
| 工具发现 | 静态（代码中定义） | 动态（运行时从 server 发现） |
| 扩展性 | 需修改源码 | 连接新 MCP server 即可 |

## MCP 协议简介

MCP（Model Context Protocol）是 Anthropic 提出的开放协议，让 LLM agent 与外部工具服务器标准化通信：

- **传输**：stdio（子进程）或 SSE（HTTP）
- **协议**：JSON-RPC 2.0
- **方法**：`initialize`（握手）→ `tools/list`（发现工具）→ `tools/call`（调用工具）
- **工具 schema**：OpenAI function-calling 格式兼容

v0.3.5 最小实现仅支持 **stdio 传输**——通过 `subprocess.Popen` 启动 MCP server 子进程，通过 stdin/stdout JSON-RPC 通信。

## 文件清单（5 个文件，含 2 个新文件）

| 文件 | 职责 | 基线行数 | 预估行数 | 变化 |
|------|------|---------|---------|------|
| `nautilus/mcp.py` | **新文件**：MCP client（stdio 传输 + JSON-RPC） | 0 | ~100 | `MCPClient` 类 + `list_tools()` + `call_tool()` + `close()` |
| `nautilus/agent.py` | ReAct 循环 + skills + **MCP 连接/合并/调用** | 443 | ~480 | +`mcp_servers` 参数 + 连接 MCP servers + 合并 schema + delegate_task/exclude MCP 路由 |
| `nautilus/tools.py` | 7 工具 + 路由 + **MCP 路由** | 399 | ~415 | `execute_tool()` 新增 `mcp_clients` 参数 + MCP 路由分支 |
| `nautilus/__main__.py` | CLI 入口 | 128 | ~135 | +`--mcp-server` CLI 参数（可多次指定） |
| `tests/test_mcp.py` | **新文件**：MCP 测试 | 0 | ~120 | `TestMCPClient` + `TestMCPToolIntegration` |

## 各文件实现细节

### 1. `nautilus/mcp.py` — 新文件（~100 行）

```python
"""MCP client for external tool server integration (stdio transport)."""

import json
import subprocess


class MCPClient:
    """MCP client: connect to MCP server via stdio, discover and call tools.

    Uses JSON-RPC 2.0 protocol over subprocess stdin/stdout.
    """

    def __init__(self, server_command: str):
        """Start MCP server subprocess and initialize connection.

        Args:
            server_command: Shell command to start MCP server (e.g. "npx @mcp/filesystem")
        """
        self.process = None
        self._request_id = 0
        self._tools = []
        try:
            self.process = subprocess.Popen(
                server_command,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            self._initialize()
            self._tools = self._list_tools()
        except Exception as e:
            self.close()
            raise

    def _send_request(self, method: str, params: dict | None = None) -> dict:
        """Send JSON-RPC 2.0 request and return response result."""
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
        }
        if params:
            request["params"] = params
        line = json.dumps(request) + "\n"
        self.process.stdin.write(line)
        self.process.stdin.flush()
        response_line = self.process.stdout.readline()
        if not response_line:
            raise ConnectionError("MCP server closed connection")
        response = json.loads(response_line)
        if "error" in response:
            raise Exception(f"MCP error: {response['error']}")
        return response.get("result", {})

    def _initialize(self) -> dict:
        """Send initialize request to MCP server."""
        return self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "nautilus", "version": "0.3.5"},
        })

    def _list_tools(self) -> list[dict]:
        """Discover tools from MCP server. Returns list of tool schemas."""
        result = self._send_request("tools/list")
        return result.get("tools", [])

    def get_tools(self) -> list[dict]:
        """Return discovered tool schemas in OpenAI function-calling format."""
        return self._tools

    def call_tool(self, name: str, arguments: dict) -> str:
        """Call a tool on MCP server. Returns result as string."""
        result = self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        # MCP returns content as list of {type, text} dicts
        content = result.get("content", [])
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
        return "\n".join(texts) if texts else str(result)

    def close(self):
        """Close connection and terminate subprocess."""
        if self.process:
            try:
                self.process.stdin.close()
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
            self.process = None
```

### 2. `nautilus/agent.py` — 核心修改

**修改 `run_agent()` 签名**：

```python
def run_agent(
    ...
    skills_dir: str | None = None,
    mcp_servers: list[str] | None = None,  # NEW: list of MCP server commands
) -> None:
```

**修改函数体——连接 MCP servers + 合并 schema**：

在 skills 注入之后、plan mode 之前：

```python
    # Connect to MCP servers and merge tool schemas
    mcp_clients = []
    mcp_tools = []
    if mcp_servers:
        from .mcp import MCPClient
        for server_cmd in mcp_servers:
            try:
                client = MCPClient(server_cmd)
                mcp_clients.append(client)
                mcp_tools.extend(client.get_tools())
                print(f"🔗 MCP server connected: {server_cmd} ({len(client.get_tools())} tools)")
            except Exception as e:
                print(f"⚠️  MCP server connection failed: {server_cmd}: {e}")

    # Merge tool schemas
    all_tools = TOOL_SCHEMAS + mcp_tools
```

**修改循环体——用 `all_tools` 替代 `TOOL_SCHEMAS`**：

```python
    api_kwargs = {"model": model, "messages": messages}
    if not text_mode:
        api_kwargs["tools"] = all_tools  # was: TOOL_SCHEMAS
```

**修改工具执行——MCP 路由**：

在 delegate_task 分支之后、approval/bash 分支中，`execute_tool` 调用需传入 `mcp_clients`：

```python
    # delegate_task: handled by run_subagent (existing)
    # MCP tools: check if tool name is not a built-in tool
    elif call.function.name not in ("read_file", "write_file", "edit_file", "glob", "grep", "bash", "delegate_task"):
        # Try MCP clients
        result = None
        for mcp_client in mcp_clients:
            try:
                result = mcp_client.call_tool(call.function.name, args)
                break
            except Exception:
                continue
        if result is None:
            result = f"错误：未知工具：{call.function.name}"
        print(f"   → {_truncate(result)}\n")
    elif approval and call.function.name == "bash":
        ...
```

**循环结束后关闭 MCP 连接**：

在函数末尾（max_iter 和 return 之前）：

```python
    # Close MCP connections
    for client in mcp_clients:
        client.close()
```

需要在所有 return 路径之前关闭——使用 try/finally 或在 return 前显式关闭。

### 3. `nautilus/tools.py` — 不修改

MCP 路由在 `agent.py` 中处理（因为需要 `mcp_clients` 引用），`execute_tool()` 不修改。MCP 工具不经过 `execute_tool`，直接在 agent 循环中路由。

### 4. `nautilus/__main__.py` — 新增 --mcp-server CLI 参数

```python
parser.add_argument(
    "--mcp-server",
    action="append",
    default=None,
    help="连接 MCP server（可多次指定）。如 --mcp-server 'npx @mcp/filesystem'",
)
```

传到 `run_agent`：

```python
run_agent(
    ...
    mcp_servers=args.mcp_server,
)
```

### 5. `tests/test_mcp.py` — 新文件（~120 行）

**TestMCPClient（5 tests）**：

| 测试 | 覆盖场景 |
|------|---------|
| `test_mcp_client_initialize` | mock subprocess 验证 initialize JSON-RPC 请求 |
| `test_mcp_client_list_tools` | mock subprocess 验证 tools/list 请求 + 返回 tool schemas |
| `test_mcp_client_call_tool` | mock subprocess 验证 tools/call 请求 + 返回结果 |
| `test_mcp_client_connection_error` | 子进程启动失败 → 异常被抛出 |
| `test_mcp_client_close` | close() 终止子进程 |

**TestMCPToolIntegration（3 tests）**：

| 测试 | 覆盖场景 |
|------|---------|
| `test_mcp_tools_merged_with_builtin` | mock MCPClient 返回 tool schemas → 验证 `all_tools` = TOOL_SCHEMAS + mcp_tools |
| `test_mcp_tool_called_in_loop` | mock LLM 调用 MCP 工具名 → mock MCPClient.call_tool 返回结果 → 结果回灌 messages |
| `test_mcp_connection_failure_graceful` | MCP server 连接失败 → 打印警告 → 继续用内置工具 |

**CLI 测试**：

| 测试 | 覆盖场景 |
|------|---------|
| `test_mcp_server_flag` | `--mcp-server "cmd1" --mcp-server "cmd2"` → `mcp_servers=["cmd1", "cmd2"]` |
| `test_mcp_server_default_none` | 不传参 → `mcp_servers=None` |

## 版本号更新

| 文件 | 变更 |
|------|------|
| `nautilus/__init__.py` | `0.3.4` → `0.3.5` |
| `pyproject.toml` | `version = "0.3.4"` → `version = "0.3.5"` |

## CLI 参数

v0.3.5 新增 1 个参数（共 14 个）：

```
$ nautilus --mcp-server "npx @mcp/filesystem /tmp" "读取 /tmp/test.txt"
$ nautilus --mcp-server "npx @mcp/filesystem" --mcp-server "python db_mcp_server.py" "查询数据库"
$ nautilus "不启用 MCP 的任务"  # 不传 --mcp-server 则不启用
```

参数（v0.3.5 新增 1 个，共 14 个）：
- `prompt` / `--model` / `--api-key` / `--base-url` / `--max-iter` / `--max-tool-output` / `--max-context-tokens` / `--stream` / `--approval` / `--text-mode` / `--plan` / `--memory` / `--skills-dir`
- `--mcp-server`（可多次指定，默认 None）**← v0.3.5 新增**

## 终端输出格式

```
🔗 MCP server connected: npx @mcp/filesystem (3 tools)      # v0.3.5 MCP 连接

💭 我来读取文件。
🔧 read_file("/tmp/test.txt")                                 # 内置工具
   → file content here
🔧 mcp__filesystem__read_file("/tmp/data.csv")                # MCP 工具
   → csv data here
✅ 已完成。

🔗 MCP connections closed.                                   # v0.3.5 MCP 关闭
```

## 不修改的文件

- `nautilus/llm.py`：不涉及
- `nautilus/memory.py`：不涉及
- `nautilus/skills.py`：不涉及
- `nautilus/tools.py`：不涉及（MCP 路由在 agent.py 中处理）
- `nautilus/prompts.py`：不涉及（MCP 工具 schema 动态合并，不需修改系统提示词）
- `pyproject.toml` 依赖列表：无新依赖（仅用 stdlib subprocess, json）

## 验证方式

1. `pip install -e .` 安装
2. 运行单元测试：
   ```bash
   PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
   ```
3. 预期结果：191 + ~10 新增 = ~201 tests 全部通过
4. E2E 测试（需要真实 MCP server，或 mock 子进程）：
   ```bash
   # 如果有 MCP server 可用：
   OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
   nautilus --model "qwen2.5:7b" --max-iter 10 \
   --mcp-server "npx @mcp/filesystem /tmp" \
   "读取 /tmp/test.txt 文件内容"
   ```
5. 验证：MCP server 连接成功 + 工具发现 + MCP 工具调用 + 结果回灌 + 连接关闭
