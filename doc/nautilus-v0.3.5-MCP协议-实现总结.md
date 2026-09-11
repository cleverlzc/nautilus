# Nautilus v0.3.5 MCP 协议 — 实现总结

## 文件清单（实际）

**10 个源码文件 + 8 个测试文件**，位于 `...\AIAgent\mycodingagent\nautilus\`：

| 文件 | v0.3.4 行数 | v0.3.5 行数 | 职责 |
|------|------------|------------|------|
| `pyproject.toml` | 16 | 16 | 项目元数据 + openai 依赖 + CLI 入口（版本 0.3.5） |
| `nautilus/__init__.py` | 1 | 1 | 版本号（0.3.5） |
| `nautilus/mcp.py` | 0 | 99 | **新文件**：`MCPClient` 类（stdio + JSON-RPC 2.0） |
| `nautilus/skills.py` | 89 | 89 | `list_skills` + `load_skill` + `match_skill` |
| `nautilus/memory.py` | 40 | 40 | `load_memory` + `save_memory` + `append_memory` |
| `nautilus/prompts.py` | 121 | 121 | 系统提示词 + SUBAGENT + PLAN + TEXT_MODE + 记忆/技能说明 |
| `nautilus/tools.py` | 399 | 399 | 7 个工具 + execute_tool 路由 + .gitignore 过滤 + 危险命令过滤 |
| `nautilus/llm.py` | 125 | 125 | OpenAI 兼容 client 工厂 + complete_with_retry + stream_complete |
| `nautilus/agent.py` | 443 | 487 | **核心 ReAct 循环** + 全部 v3 特性 + **MCP 连接/合并/路由/关闭** |
| `nautilus/__main__.py` | 128 | 135 | CLI 入口 + GBK 编码修复 + 14 个参数（含 `--mcp-server`） |
| **源码合计** | **1346** | **1496** | |

**总计 1496 行 Python 源码**（v0.3.5 新增约 150 行源码 + 10 个测试，主要是 `mcp.py` 新文件 + `run_agent` MCP 连接/合并/路由/关闭集成 + `--mcp-server` CLI 参数）。

## v0.3.5 新增功能（1 个）

| # | 功能 | 核心实现 |
|---|------|---------|
| 1 | **MCP 协议** | `mcp.py` 新文件（99 行）：`MCPClient` 类通过 `subprocess.Popen` 启动 MCP server 子进程，通过 stdio JSON-RPC 2.0 通信。`__init__` 启动子进程 + `_initialize` 握手 + `_list_tools` 发现工具 → `get_tools` 返回 OpenAI function-calling 格式 schemas → `call_tool` 调用工具 + `close` 终止子进程。`agent.py` `run_agent()` 新增 `mcp_servers` 参数：启动时连接 MCP servers + `all_tools = TOOL_SCHEMAS + mcp_tools` 合并 schema + 循环内用 `all_tools` + 非内置工具名遍历 `mcp_clients` 调用 `call_tool` + 循环后关闭所有连接。`__main__.py` 新增 `--mcp-server` CLI 参数（`action="append"` 可多次指定） |

### MCP 全链路

| 步骤 | 实现 | 验证 |
|------|------|------|
| 连接 | `MCPClient.__init__` → `subprocess.Popen` → `_initialize` 握手 | ✅ 🔗 connected |
| 工具发现 | `_list_tools` → `tools/list` JSON-RPC → 返回 tool schemas | ✅ N tools |
| schema 合并 | `all_tools = TOOL_SCHEMAS + mcp_tools` | ✅ 7+N tools |
| LLM 工具选择 | LLM 从 `all_tools` 中选择 MCP 工具 | ✅ |
| JSON-RPC 调用 | `call_tool` → `tools/call` JSON-RPC → 结果回灌 | ✅ |
| 连接关闭 | `close()` → `terminate` + `wait(timeout=5)` | ✅ 🔗 closed |

### 设计要点

- **stdio 传输**：通过 `subprocess.Popen` 启动 MCP server 子进程，stdin/stdout JSON-RPC 通信（最小实现，不支持 SSE）
- **JSON-RPC 2.0**：`{"jsonrpc":"2.0","id":N,"method":"...","params":{...}}` → `{"jsonrpc":"2.0","id":N,"result":{...}}`
- **schema 兼容**：MCP server 返回的 tool schemas 是 OpenAI function-calling 格式，可直接合并到 `TOOL_SCHEMAS`
- **非内置工具路由**：agent 循环中检测工具名不在 7 个内置工具中 → 遍历 `mcp_clients` 调用 `call_tool`
- **可选启用**：`mcp_servers=None`（默认）不启用；传 `--mcp-server "cmd"` 启用（可多次指定）
- **优雅降级**：MCP server 连接失败 → 打印警告 → 继续用内置工具
- **变量名安全**：使用 `mcp_client` 变量名，避免覆盖 OpenAI `client` 变量

## 实现中修复的 bug

| bug | 描述 | 修复 |
|-----|------|------|
| MCP 变量名覆盖 OpenAI client | `client = MCPClient(...)` 覆盖了 OpenAI `client`，导致 `complete_with_retry(client, ...)` 传入 MCPClient → `AttributeError: 'MCPClient' object has no attribute 'chat'` | 改为 `mcp_client = MCPClient(...)` |

## 验证结果

### 单元测试

- ✅ 所有模块导入正常（9 模块，含新增 `mcp.py`）
- ✅ CLI `--help` 输出正确（14 参数，含 `--mcp-server`）
- ✅ MCPClient 验证（initialize / list_tools / call_tool / connection_error / close 5 种场景）
- ✅ MCP 集成验证（工具合并+调用 / 连接失败优雅降级 / 未知工具错误 3 种场景）
- ✅ 单元测试 201 passed, 0 failed

### E2E 端到端真实场景（Ollama + qwen2.5:7b + mcp_echo_server.py）

- ✅ MCP 连接 + 工具调用闭环：🔗 connected (1 tools) → 🔧 echo_text → [MCP] hello from mcp → ✅ 回显文本 → 🔗 closed
- ✅ 不启用 MCP 对比：无 🔗 输出，直接用内置 glob——可选叠加功能

## 测试覆盖

| 测试模块 | v0.3.4 测试数 | v0.3.5 测试数 | 新增内容 |
|---------|------------|------------|---------|
| `test_mcp.py` | 0 | 8 | TestMCPClient(5) + TestMCPToolIntegration(3) |
| `test_cli.py` | 30 | 32 | test_mcp_server_flag(1) + test_mcp_server_default_none(1) |
| `test_agent.py` | 46 | 46 | — |
| `test_tools.py` | 63 | 63 | — |
| `test_llm.py` | 18 | 18 | — |
| `test_memory.py` | 13 | 13 | — |
| `test_skills.py` | 14 | 14 | — |
| **合计** | **191** | **201** | **+10** |

## 使用方式

```bash
cd ".../AIAgent/mycodingagent/nautilus"
pip install -e .
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://xxx   # 可选，OpenAI 兼容 API

# v0.3.5 新增：MCP 协议（连接外部工具服务器）
nautilus --mcp-server "npx @mcp/filesystem /tmp" "读取 /tmp/test.txt"

# 多个 MCP server
nautilus --mcp-server "npx @mcp/filesystem" --mcp-server "python db_mcp_server.py" "查询数据库"

# MCP + 记忆 + plan mode 组合
nautilus --mcp-server "npx @mcp/filesystem" --memory .nautilus/memory.md --plan "分析项目"

# 不启用 MCP（默认行为）
nautilus "创建一个 hello.py，运行它"

# 运行单元测试
python -m pytest tests/ -v -o "addopts="
```

## 核心洞察

当前 agent 只有 7 个内置工具（read/write/edit/glob/grep/bash/delegate_task）。如果用户需要 agent 操作数据库、调用 API、读取 Jira ticket 等外部能力，只能通过 bash 间接实现——不安全且不标准。

v0.3.5 补齐了这个缺口：agent 启动时连接 MCP server（通过 stdio 子进程），动态发现 server 提供的工具 schema，合并到 `TOOL_SCHEMAS` 中。LLM 调用 MCP 工具时，agent 通过 JSON-RPC 2.0 协议转发请求到 MCP server，获取结果回灌 messages。工具集从 7 个静态内置扩展为 7+N 个动态发现——agent 的能力不再局限于源码中定义的工具。

E2E 验证确认：自定义 MCP server（mcp_echo_server.py）提供 echo_text 工具 → agent 连接成功 + 发现 1 个工具 + LLM 选择 MCP 工具 + JSON-RPC 调用 + 结果回灌 + 最终回答 + 连接关闭——全链路正确。

v0.3.5 是 v3 的最后一个小版本。v3 的 6 个特性（上下文压缩 + 子 agent + plan mode + 记忆系统 + Skills/插件 + MCP 协议）全部实现并通过 UT + E2E 验证。Nautilus 从 v1 的 378 行 MVP 成长为 1496 行产品级 coding agent。
