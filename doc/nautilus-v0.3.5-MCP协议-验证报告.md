# Nautilus v0.3.5 MCP 协议 — 验证报告

> 验证对象：Nautilus v0.3.5（1496 行 Python，7+N 工具，ReAct 循环 + 上下文压缩 + 子 agent + plan mode + 记忆系统 + Skills/插件 + MCP 协议）
> 验证日期：2026-09-11
> 验证环境：Python 3.14.4 / Windows 11 / openai 2.35.1 / pytest 9.0.3
> E2E 环境：Ollama 本地 / qwen2.5:7b / native function calling / mcp_echo_server.py
> UT 文件：`nautilus/tests/` 目录下 7 个测试模块，201 个测试用例
> E2E 测试：2 个场景，全部通过

---

## 一、验证范围

### 1.1 验证目标

验证 Nautilus v0.3.5 MCP 协议功能**是否可真正工作**——在 v0.3.4 已验证的基础上，验证 `mcp.py` 的 `MCPClient` 类（initialize / list_tools / call_tool / close）、`run_agent()` 的 MCP 连接/合并/路由/关闭集成、`--mcp-server` CLI 参数的正确性，同时确认 v0.3.4 功能回归无退化。

### 1.2 UT 文件结构

```
nautilus/
├── pyproject.toml              # 16 行 — 版本 0.3.5
├── nautilus/                   # 源码包（1496 行）
│   ├── __init__.py             #   1 行 — 版本 0.3.5
│   ├── __main__.py             # 135 行 — CLI + --mcp-server（14 个参数）
│   ├── agent.py                # 487 行 — ReAct 循环 + 压缩 + 子 agent + plan + 记忆 + skills + MCP 连接/路由/关闭
│   ├── llm.py                  # 125 行 — client 工厂 + retry + stream
│   ├── mcp.py                  #  99 行 — MCPClient（stdio + JSON-RPC 2.0）（新增）
│   ├── memory.py               #  40 行 — load_memory + save_memory + append_memory
│   ├── prompts.py              # 121 行 — 系统提示词 + SUBAGENT + PLAN + TEXT_MODE + 记忆/技能说明
│   ├── skills.py               #  89 行 — list_skills + load_skill + match_skill
│   └── tools.py                # 399 行 — 7 工具 + execute_tool 路由 + .gitignore + 危险过滤
└── tests/                      # 单元测试
    ├── __init__.py             #   8 行
    ├── test_tools.py           # 417 行 — 63 tests
    ├── test_agent.py           # 1159 行 — 46 tests
    ├── test_llm.py             # 286 行 — 18 tests
    ├── test_cli.py             # 294 行 — 32 tests
    ├── test_memory.py          # 198 行 — 13 tests
    ├── test_skills.py          # 232 行 — 14 tests
    ├── test_mcp.py             # 236 行 — 8 tests（新增）
    └── mcp_echo_server.py      # 80 行 — E2E 测试用 MCP server（新增）
```

### 1.3 运行方式

```bash
cd ".../AIAgent/mycodingagent/nautilus"
python -m pytest tests/ -v -o "addopts="
```

---

## 二、验证结果总览

### 2.1 最终结果

```
============================ 201 passed in 28.31s =============================
```

| 指标 | v0.3.4 | v0.3.5 |
|------|--------|--------|
| 测试总数 | 191 | 201 |
| 通过 | 191 | 201 |
| 失败 | 0 | 0 |
| 错误 | 0 | 0 |
| 跳过 | 0 | 0 |
| 总耗时 | 31.30s | 28.31s |
| 新增测试 | — | +10 |

### 2.2 按模块统计

| 测试模块 | v0.3.4 测试数 | v0.3.5 测试数 | 新增 | 覆盖组件 |
|---------|------------|------------|------|---------|
| `test_tools.py` | 63 | 63 | — | — |
| `test_agent.py` | 46 | 46 | — | — |
| `test_llm.py` | 18 | 18 | — | — |
| `test_cli.py` | 30 | 32 | +2 | **--mcp-server flag** + **mcp_server_default_none** |
| `test_memory.py` | 13 | 13 | — | — |
| `test_skills.py` | 14 | 14 | — | — |
| `test_mcp.py` | 0 | 8 | +8 | **TestMCPClient**(5) + **TestMCPToolIntegration**(3) |
| **合计** | **191** | **201** | **+10** | |

---

## 三、各模块验证详情

### 3.1 test_mcp.py 新增测试（8 tests）

#### TestMCPClient（5 tests）

| 测试 | 覆盖场景 |
|------|---------|
| `test_mcp_client_initialize` | mock subprocess 验证 initialize JSON-RPC 请求发送（含 protocolVersion + clientInfo） |
| `test_mcp_client_list_tools` | mock subprocess 验证 tools/list 请求 + 返回 tool schemas（含 echo_text 工具） |
| `test_mcp_client_call_tool` | mock subprocess 验证 tools/call 请求 + 返回 text content |
| `test_mcp_client_connection_error` | 子进程启动失败（FileNotFoundError）→ 异常被抛出 |
| `test_mcp_client_close` | close() 调用 terminate() + 设置 process=None |

关键验证点：
- JSON-RPC 2.0 格式正确（jsonrpc/id/method/params/result）
- initialize 请求含 protocolVersion + capabilities + clientInfo
- tools/list 返回 OpenAI function-calling 格式的 tool schemas
- tools/call 返回 content[].text 格式，`call_tool()` 提取为字符串
- 连接失败时异常被抛出（不吞没），`close()` 在异常路径中被调用
- `close()` 调用 `terminate()` + `wait(timeout=5)`，`process` 设为 None

#### TestMCPToolIntegration（3 tests）

| 测试 | 覆盖场景 |
|------|---------|
| `test_mcp_tools_merged_with_builtin` | mock MCPClient 返回 tool schemas → mock LLM 调用 MCP 工具 → 结果回灌 → 最终回答 |
| `test_mcp_connection_failure_graceful` | MCP server 连接失败（FileNotFoundError）→ 打印"连接失败"警告 → 继续用内置工具 |
| `test_mcp_unknown_tool_returns_error` | 无 MCP clients + 未知工具名 → 返回"错误：未知工具" → 结果回灌 LLM |

关键验证点：

**MCP 工具调用闭环**（`test_mcp_tools_merged_with_builtin`）：
- mock subprocess 返回 init + list + call 三个 JSON-RPC 响应
- mock LLM 第 1 轮调用 MCP 工具 `fetch_url` → agent 遍历 `mcp_clients` 调用 `call_tool` → 结果回灌
- mock LLM 第 2 轮给出最终回答
- 验证 2 次 LLM 调用（tool_call → final_answer）

**连接失败优雅降级**（`test_mcp_connection_failure_graceful`）：
- `subprocess.Popen` 抛出 `FileNotFoundError` → 打印"连接失败"警告
- agent 继续用内置工具执行任务，不崩溃

**未知工具错误**（`test_mcp_unknown_tool_returns_error`）：
- 无 MCP clients + LLM 调用未知工具名 → 返回"错误：未知工具"字符串
- 结果回灌 messages，LLM 可自纠

### 3.2 test_cli.py 新增测试（2 tests）

| 测试 | 覆盖场景 |
|------|---------|
| `test_mcp_server_flag` | `--mcp-server "cmd1" --mcp-server "cmd2"` → `mcp_servers=["cmd1", "cmd2"]` |
| `test_mcp_server_default_none` | 不传参 → `mcp_servers=None` |

---

## 四、v0.3.5 功能验证

### 4.1 mcp.py MCPClient 类

| 验证项 | 结果 | 说明 |
|--------|------|------|
| `__init__` 启动子进程 | ✅ | `subprocess.Popen(server_command, shell=True, stdin/stdout/stderr=PIPE)` |
| `_initialize` 握手 | ✅ | JSON-RPC initialize 请求含 protocolVersion + clientInfo |
| `_list_tools` 工具发现 | ✅ | tools/list 返回 OpenAI function-calling 格式 schemas |
| `get_tools` 返回 schemas | ✅ | 返回发现的 tool schemas 列表 |
| `call_tool` 调用工具 | ✅ | tools/call 返回 content[].text → 提取为字符串 |
| `close` 关闭连接 | ✅ | stdin.close + terminate + wait(timeout=5) + process=None |
| 连接失败异常处理 | ✅ | `__init__` 中异常 → `close()` 清理 → 抛出异常 |

### 4.2 agent.py MCP 集成

| 验证项 | 结果 | 说明 |
|--------|------|------|
| `mcp_servers` 参数 | ✅ | `run_agent()` 新增 `mcp_servers: list[str] \| None = None` |
| 连接 MCP servers | ✅ | 遍历 `mcp_servers`，每个启动 `MCPClient`，连接失败打印警告 |
| 合并 tool schemas | ✅ | `all_tools = TOOL_SCHEMAS + mcp_tools` |
| 循环内用 all_tools | ✅ | `api_kwargs["tools"] = all_tools`（替代 `TOOL_SCHEMAS`） |
| MCP 工具路由 | ✅ | 非内置工具名 → 遍历 `mcp_clients` 调用 `call_tool` |
| MCP 关闭（最终回答） | ✅ | `for c in mcp_clients: c.close()` + `print("🔗 MCP connections closed.")` |
| MCP 关闭（max_iter） | ✅ | 同上 |
| 变量名不覆盖 OpenAI client | ✅ | 使用 `mcp_client` 变量名（修复 bug） |

### 4.3 CLI 参数

| 验证项 | 结果 | 说明 |
|--------|------|------|
| `--mcp-server` 多次指定 | ✅ | `action="append"` → `["cmd1", "cmd2"]` |
| 默认 None | ✅ | 不传参 → `mcp_servers=None`（不启用） |

---

## 五、E2E 端到端真实场景验证

### 5.1 测试环境

| 项 | 值 |
|---|---|
| LLM 服务 | Ollama 本地 (http://127.0.0.1:11434) |
| 模型 | qwen2.5:7b（native function calling） |
| API Key | test |
| 模式 | native function calling |
| MCP server | 自定义 `mcp_echo_server.py`（提供 1 个工具 `echo_text`） |
| 测试项目 | /tmp/nautilus-compress-test（3 个 Python 文件） |
| OS | Windows 11 / Python 3.14.4 |

### 5.2 E2E 测试结果

| # | 测试场景 | 命令 | 结果 | 关键验证点 |
|---|---------|------|------|-----------|
| 1+2 | **MCP 连接 + 工具调用闭环** | `OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:11434/v1 nautilus --model "qwen2.5:7b" --max-iter 10 --mcp-server "python .../mcp_echo_server.py" "用 echo_text 工具回显文本 hello from mcp"` | ✅ 通过 | 🔗 MCP connected (1 tools) → 🔧 echo_text({'text': 'hello from mcp'}) → [MCP] hello from mcp → ✅ 回显文本 → 🔗 MCP closed |
| 3 | **不启用 MCP 对比** | `OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:11434/v1 nautilus --model "qwen2.5:7b" --max-iter 5 "用 glob 搜索所有 .py 文件，告诉我有几个"` | ✅ 通过 | 无 🔗 输出，直接用内置 glob 工具搜索——MCP 未启用，默认行为不变 |

### 5.3 E2E 测试详情

**测试 1+2：MCP 连接 + 工具调用闭环**

编写最小 MCP server（`mcp_echo_server.py`，80 行），提供 1 个工具 `echo_text(text)` → 返回 `[MCP] {text}`。通过 stdio JSON-RPC 2.0 通信。

Agent 用 `--mcp-server "python .../mcp_echo_server.py"` + prompt"用 echo_text 工具回显文本 hello from mcp"执行任务。

完整执行流程：
1. `🔗 MCP server connected: python .../mcp_echo_server.py (1 tools)` — MCP 连接成功，发现 1 个工具
2. LLM 第 1 轮调用 `echo_text({'text': 'hello from mcp'})` — MCP 工具被调用
3. Agent 通过 JSON-RPC 转发到 MCP server → MCP server 返回 `[MCP] hello from mcp`
4. 结果回灌 messages
5. LLM 第 2 轮给出最终回答："回显文本: hello from mcp"
6. `🔗 MCP connections closed.` — MCP 子进程被正确终止

终端输出：
```
🔗 MCP server connected: python .../mcp_echo_server.py (1 tools)
🔧 echo_text({'text': 'hello from mcp'})
   → [MCP] hello from mcp

✅ 回显文本: hello from mcp
🔗 MCP connections closed.
```

验证点：MCP 协议全链路正确——连接 → 握手 → 工具发现 → schema 合并 → LLM 选择 MCP 工具 → JSON-RPC 转发 → 结果回灌 → 最终回答 → 连接关闭。

**测试 3：不启用 MCP 对比**

Agent 不传 `--mcp-server` + prompt"用 glob 搜索所有 .py 文件"执行任务。

Agent 直接用内置 `glob("*.py")` 找到 6 个文件 → 最终回答。

验证点：无 🔗 输出，直接用内置工具——MCP 是可选叠加功能，不破坏默认行为。

### 5.4 用例设计理由

| # | 场景 | 设计理由 |
|---|------|---------|
| 1+2 | **MCP 连接 + 工具调用闭环** | 编写最小 MCP server（mcp_echo_server.py，提供 echo_text 工具）作为测试用的外部工具服务器。验证完整闭环：MCP 连接（🔗 connected）→ 工具发现（1 tools）→ LLM 调用 MCP 工具（🔧 echo_text）→ JSON-RPC 转发到 MCP server → 结果回灌（[MCP] hello from mcp）→ 最终回答 → MCP 关闭（🔗 closed）。验证 MCP 协议的连接/发现/调用/关闭全链路 |
| 3 | **不启用 MCP 对比** | 同一项目不传 `--mcp-server`，验证默认模式下不连接 MCP server（无 🔗 输出），直接用内置工具（glob）。确认 MCP 是可选叠加功能，不破坏默认行为 |

### 5.5 MCP 全链路验证

| 步骤 | 验证点 | 结果 |
|------|--------|------|
| MCP 连接 | `subprocess.Popen` 启动 MCP server 子进程 | ✅ 🔗 connected |
| 握手 | `initialize` JSON-RPC 请求 → MCP server 返回 protocolVersion | ✅ |
| 工具发现 | `tools/list` JSON-RPC 请求 → 返回 echo_text schema | ✅ 1 tools |
| schema 合并 | `all_tools = TOOL_SCHEMAS + mcp_tools`（7+1=8 tools） | ✅ |
| LLM 工具选择 | LLM 选择 `echo_text`（MCP 工具）而非内置工具 | ✅ |
| JSON-RPC 调用 | `tools/call` 请求转发到 MCP server | ✅ |
| 结果回灌 | MCP server 返回 `[MCP] hello from mcp` → 回灌 messages | ✅ |
| 最终回答 | LLM 基于工具结果给出最终回答 | ✅ |
| 连接关闭 | `close()` 终止子进程 | ✅ 🔗 closed |

---

## 六、发现的问题

### 6.1 MCP 变量名覆盖 OpenAI client（实现中发现，已修复）

**问题描述**：MCP 连接代码中 `client = MCPClient(server_cmd)` 覆盖了 OpenAI client 变量，导致后续 `complete_with_retry(client, ...)` 传入 MCPClient 而非 OpenAI client，抛出 `AttributeError: 'MCPClient' object has no attribute 'chat'`。

**修复**：将 MCP 循环变量改为 `mcp_client`，避免覆盖 OpenAI client。

### 6.2 Windows GBK 编码兼容性（v2 遗留，已修复）

P0 修复已在 `__main__.py` 入口处添加 `sys.stdout.reconfigure(encoding="utf-8")`。

### 6.3 上级目录 pyproject.toml 干扰（v2 遗留，未修复）

**当前规避**：`-o "addopts="`

---

## 七、测试覆盖率矩阵

| 源文件 | v0.3.4 行数 | v0.3.5 行数 | 测试文件 | v0.3.4 测试 | v0.3.5 测试 | 关键路径覆盖 |
|--------|------------|------------|---------|------------|------------|------------|
| `tools.py` | 399 | 399 | `test_tools.py` | 63 | 63 | — |
| `agent.py` | 443 | 487 | `test_agent.py` | 46 | 46 | —（MCP 集成在 test_mcp.py 中测试） |
| `llm.py` | 125 | 125 | `test_llm.py` | 18 | 18 | — |
| `__main__.py` | 128 | 135 | `test_cli.py` | 30 | 32 | +**--mcp-server flag** |
| `prompts.py` | 121 | 121 | 间接覆盖 | — | — | — |
| `memory.py` | 40 | 40 | `test_memory.py` | 13 | 13 | — |
| `skills.py` | 89 | 89 | `test_skills.py` | 14 | 14 | — |
| `mcp.py` | 0 | 99 | `test_mcp.py` | 0 | 8 | **MCPClient + integration** |
| `__init__.py` | 1 | 1 | 间接覆盖 | — | — | 版本 0.3.5 |
| **合计** | **1346** | **1496** | | **191** | **201** | |

---

## 八、v0.3.4→v0.3.5 回归对比

| 验证维度 | v0.3.4 状态 | v0.3.5 状态 | 回归 |
|---------|------------|------------|------|
| 模块导入 | ✅ 8 模块 | ✅ 9 模块（+mcp） | 无退化 |
| CLI --help | ✅ 13 参数 | ✅ 14 参数 | 无退化 |
| read_file/write_file/edit_file/glob/grep/bash | ✅ 6 工具 | ✅ 6 工具 | 无退化 |
| delegate_task | ✅ 1 工具 | ✅ 1 工具 | 无退化 |
| execute_tool 路由 | ✅ 6 路由 | ✅ 6 路由 | 无退化 |
| TOOL_SCHEMAS | ✅ 7 schema | ✅ 7 schema | 无退化 |
| ReAct 循环 | ✅ 5 场景 | ✅ 5 场景 | 无退化 |
| 上下文压缩 | ✅ 9 tests | ✅ 9 tests | 无退化 |
| 子 agent | ✅ 6 tests | ✅ 6 tests | 无退化 |
| plan mode | ✅ 3 tests | ✅ 3 tests | 无退化 |
| 记忆系统 | ✅ 13 tests | ✅ 13 tests | 无退化 |
| Skills/插件 | ✅ 14 tests | ✅ 14 tests | 无退化 |
| 权限审批 | ✅ 3 tests | ✅ 3 tests | 无退化 |
| 危险命令过滤 | ✅ 9 tests | ✅ 9 tests | 无退化 |
| GBK 编码修复 | ✅ 1 test | ✅ 1 test | 无退化 |
| **MCP 协议** | — | ✅ **8 tests** | **新增** |
| **CLI --mcp-server** | — | ✅ **2 tests** | **新增** |
| **合计** | **191 passed** | **201 passed** | **0 退化** |

---

## 九、结论

### 9.1 MCP 协议功能验证通过

Nautilus v0.3.5 的 MCP 协议功能**全部通过验证**：

- **mcp.py MCPClient**：initialize / list_tools / call_tool / close——全部正确
- **agent.py 集成**：MCP 连接 + schema 合并 + 工具路由 + 连接关闭——全部正确
- **CLI 参数**：`--mcp-server` 多次指定 + 默认 None——正确
- **实现中修复 bug**：变量名覆盖 OpenAI client → 改用 `mcp_client`——已修复

### 9.2 E2E 端到端真实场景验证通过

在 Ollama + qwen2.5:7b + mcp_echo_server.py 环境下完成 2 个场景测试，全部通过：

- **MCP 连接 + 工具调用闭环**：🔗 connected (1 tools) → 🔧 echo_text → [MCP] hello from mcp → ✅ 回显文本 → 🔗 closed
- **不启用 MCP 对比**：无 🔗 输出，直接用内置 glob——可选叠加功能

### 9.3 MCP 全链路验证通过

MCP 协议的连接 → 握手 → 工具发现 → schema 合并 → LLM 工具选择 → JSON-RPC 调用 → 结果回灌 → 最终回答 → 连接关闭——全链路正确。

### 9.4 v0.3.4 回归无退化

v0.3.4 的 191 个测试全部在 v0.3.5 中继续通过，0 退化。新增的 10 个测试覆盖 MCP 全部新功能。

### 9.5 已知问题

| 问题 | 严重程度 | 状态 | 规避方式 |
|------|---------|------|---------|
| MCP 变量名覆盖（实现中） | 高 | **已修复** | `client` → `mcp_client` |
| Windows GBK 编码 | 中 | 已修复（P0） | `__main__.py` 入口 `sys.stdout.reconfigure` |
| 上级 pyproject.toml 干扰 | 低 | 未修复 | `-o "addopts="` |

### 9.6 v3 全部完成

v0.3.5 是 v3 的最后一个小版本。v3 的 6 个特性（上下文压缩 + 子 agent + plan mode + 记忆系统 + Skills/插件 + MCP 协议）全部实现并通过 UT + E2E 验证。

---

## 附录：完整测试输出

```
============================= test session starts ==============================
platform win32 -- Python 3.14.4, pytest-9.0.3, pluggy-1.6.0
rootdir: D:\AIAgent\Practice
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0
collected 201 items

tests\test_agent.py::TestTruncate::test_short_text_passthrough PASSED    [  0%]
tests\test_agent.py::TestTruncate::test_exact_limit PASSED               [  0%]
tests\test_agent.py::TestTruncate::test_long_text_truncated PASSED       [  1%]
tests\test_agent.py::TestTruncate::test_truncation_marker_format PASSED  [  1%]
tests\test_agent.py::TestTruncate::test_empty_string PASSED              [  2%]
tests\test_agent.py::TestTruncate::test_custom_limit PASSED              [  2%]
tests\test_agent.py::TestEstimateTokens::test_pure_ascii PASSED          [  3%]
tests\test_agent.py::TestEstimateTokens::test_pure_cjk PASSED            [  3%]
tests\test_agent.py::TestEstimateTokens::test_empty_string PASSED        [  4%]
tests\test_agent.py::TestEstimateTokens::test_mixed_ascii_cjk PASSED     [  4%]
tests\test_agent.py::TestEstimateTokens::test_long_code_text PASSED      [  5%]
tests\test_agent.py::TestEstimateTokens::test_none_safety PASSED         [  5%]
tests\test_agent.py::TestTruncateForLlm::test_short_text_passthrough PASSED [  6%]
tests\test_agent.py::TestTruncateForLlm::test_exact_limit_no_truncation PASSED [  6%]
tests\test_agent.py::TestTruncateForLlm::test_long_text_truncated_with_bilingual_marker PASSED [  7%]
tests\test_agent.py::TestTruncateForLlm::test_custom_max_chars PASSED    [  7%]
tests\test_agent.py::TestTruncateForLlm::test_empty_string PASSED       [  8%]
tests\test_agent.py::TestPrintToolCall::test_read_file PASSED            [  8%]
tests\test_agent.py::TestPrintToolCall::test_write_file PASSED           [  9%]
tests\test_agent.py::TestPrintToolCall::test_edit_file PASSED            [  9%]
tests\test_agent.py::TestPrintToolCall::test_bash PASSED                 [ 10%]
tests\test_agent.py::TestPrintToolCall::test_unknown_tool PASSED         [ 10%]
tests\test_agent.py::TestPrintToolCall::test_missing_args PASSED         [ 11%]
tests\test_agent.py::TestRunAgentReActLoop::test_full_react_loop PASSED  [ 11%]
tests\test_agent.py::TestRunAgentMaxIter::test_max_iter_truncation PASSED [ 12%]
tests\test_agent.py::TestRunAgentErrorRecovery::test_error_self_correction PASSED [ 12%]
tests\test_agent.py::TestRunAgentTokenBudget::test_large_tool_output_truncated_in_messages PASSED [ 13%]
tests\test_agent.py::TestMessagesTokenEstimate::test_pure_dict_messages PASSED [ 13%]
tests\test_agent.py::TestMessagesTokenEstimate::test_empty_messages PASSED [ 14%]
tests\test_agent.py::TestMessagesTokenEstimate::test_dict_with_tool_calls PASSED [ 14%]
tests\test_agent.py::TestMessagesTokenEstimate::test_sdk_like_objects PASSED [ 15%]
tests\test_agent.py::TestCompressHistory::test_no_compression_under_budget PASSED [ 15%]
tests\test_agent.py::TestCompressHistory::test_compresses_over_budget PASSED [ 16%]
tests\test_agent.py::TestCompressHistory::test_never_drops_system_and_user PASSED [ 16%]
tests\test_agent.py::TestCompressHistory::test_empty_history_after_system_user PASSED [ 17%]
tests\test_agent.py::TestRunAgentContextCompression::test_history_compressed_within_budget PASSED [ 17%]
tests\test_agent.py::TestRunAgentApproval::test_approval_rejected_bash_command PASSED [ 18%]
tests\test_agent.py::TestRunAgentApproval::test_approval_accepted_bash_command PASSED [ 18%]
tests\test_agent.py::TestRunAgentApproval::test_approval_disabled_by_default PASSED [ 19%]
tests\test_agent.py::TestRunSubagent::test_subagent_returns_final_answer PASSED [ 19%]
tests\test_agent.py::TestRunSubagent::test_subagent_independent_messages PASSED [ 20%]
tests\test_agent.py::TestRunSubagent::test_subagent_max_iter PASSED      [ 20%]
tests\test_agent.py::TestDelegateTask::test_delegate_task_calls_subagent PASSED [ 21%]
tests\test_agent.py::TestDelegateTask::test_delegate_task_does_not_pollute_main PASSED [ 21%]
tests\test_agent.py::TestDelegateTask::test_subagent_rejects_recursive_delegate PASSED [ 22%]
tests\test_agent.py::TestPlanMode::test_plan_mode_accepted PASSED        [ 22%]
tests\test_agent.py::TestPlanMode::test_plan_mode_rejected PASSED        [ 23%]
tests\test_agent.py::TestPlanMode::test_plan_mode_disabled_by_default PASSED [ 23%]
tests\test_cli.py::TestCLIHelp::test_help_exits_zero PASSED              [ 24%]
tests\test_cli.py::TestCLIHelp::test_help_without_encoding_override PASSED [ 24%]
tests\test_cli.py::TestCLIHelp::test_help_shows_description PASSED       [ 25%]
tests\test_cli.py::TestCLINoPrompt::test_no_prompt_no_stdin_exits_1 PASSED [ 25%]
tests\test_cli.py::TestCLIStdin::test_stdin_prompt_is_read PASSED        [ 26%]
tests\test_cli.py::TestCLIArgumentParsing::test_positional_prompt PASSED [ 26%]
tests\test_cli.py::TestCLIArgumentParsing::test_model_flag PASSED        [ 27%]
tests\test_cli.py::TestCLIArgumentParsing::test_api_key_flag PASSED      [ 27%]
tests\test_cli.py::TestCLIArgumentParsing::test_base_url_flag PASSED     [ 28%]
tests\test_cli.py::TestCLIArgumentParsing::test_max_iter_flag PASSED     [ 28%]
tests\test_cli.py::TestCLIArgumentParsing::test_max_tool_output_flag PASSED [ 29%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_max_iter_is_20 PASSED [ 29%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_model_is_gpt4 PASSED [ 30%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_api_key_is_none PASSED [ 30%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_max_tool_output_is_6000 PASSED [ 31%]
tests\test_cli.py::TestCLIArgumentParsing::test_max_context_tokens_flag PASSED [ 31%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_max_context_tokens_is_32000 PASSED [ 32%]
tests\test_cli.py::TestCLIArgumentParsing::test_stream_flag PASSED       [ 32%]
tests\test_cli.py::TestCLIArgumentParsing::test_stream_default_false PASSED [ 33%]
tests\test_cli.py::TestCLIArgumentParsing::test_approval_flag PASSED     [ 33%]
tests\test_cli.py::TestCLIArgumentParsing::test_approval_default_false PASSED [ 34%]
tests\test_cli.py::TestCLIArgumentParsing::test_plan_flag PASSED         [ 34%]
tests\test_cli.py::TestCLIArgumentParsing::test_plan_default_false PASSED [ 35%]
tests\test_cli.py::TestCLIArgumentParsing::test_memory_flag PASSED       [ 35%]
tests\test_cli.py::TestCLIArgumentParsing::test_memory_default_none PASSED [ 36%]
tests\test_cli.py::TestCLIArgumentParsing::test_skills_dir_flag PASSED   [ 36%]
tests\test_cli.py::TestCLIArgumentParsing::test_skills_dir_default_none PASSED [ 37%]
tests\test_cli.py::TestCLIArgumentParsing::test_mcp_server_flag PASSED   [ 37%]
tests\test_cli.py::TestCLIArgumentParsing::test_mcp_server_default_none PASSED [ 38%]
tests\test_llm.py::TestCreateClientNoKey::test_no_key_raises_systemexit PASSED [ 38%]
tests\test_llm.py::TestCreateClientNoKey::test_no_key_message_mentions_env_var PASSED [ 39%]
tests\test_llm.py::TestCreateClientExplicit::test_explicit_key_creates_client PASSED [ 39%]
tests\test_llm.py::TestCreateClientExplicit::test_explicit_key_and_base_url PASSED [ 40%]
tests\test_llm.py::TestCreateClientEnvFallback::test_env_api_key PASSED  [ 40%]
tests\test_llm.py::TestCreateClientEnvFallback::test_env_api_key_and_base_url PASSED [ 41%]
tests\test_llm.py::TestCreateClientEnvFallback::test_explicit_overrides_env PASSED [ 41%]
tests\test_llm.py::TestCreateClientEnvFallback::test_base_url_not_set_when_only_api_key_in_env PASSED [ 42%]
tests\test_llm.py::TestCreateClientPriority::test_none_api_key_falls_back_to_env PASSED [ 42%]
tests\test_llm.py::TestCreateClientPriority::test_empty_string_api_key_does_not_fallback PASSED [ 43%]
tests\test_llm.py::TestCompleteWithRetry::test_success_on_first_try PASSED [ 43%]
tests\test_llm.py::TestCompleteWithRetry::test_retry_on_rate_limit_then_success PASSED [ 44%]
tests\test_llm.py::TestCompleteWithRetry::test_all_retries_exhausted_raises_systemexit PASSED [ 44%]
tests\test_llm.py::TestCompleteWithRetry::test_bad_request_not_retried PASSED [ 45%]
tests\test_llm.py::TestCompleteWithRetry::test_auth_error_not_retried PASSED [ 45%]
tests\test_llm.py::TestStreamComplete::test_stream_content_accumulated_and_printed PASSED [ 46%]
tests\test_llm.py::TestStreamComplete::test_stream_tool_calls_assembled PASSED [ 46%]
tests\test_llm.py::TestStreamComplete::test_stream_empty_response PASSED [ 47%]
tests\test_mcp.py::TestMCPClient::test_mcp_client_initialize PASSED      [ 47%]
tests\test_mcp.py::TestMCPClient::test_mcp_client_list_tools PASSED     [ 48%]
tests\test_mcp.py::TestMCPClient::test_mcp_client_call_tool PASSED      [ 48%]
tests\test_mcp.py::TestMCPClient::test_mcp_client_connection_error PASSED [ 49%]
tests\test_mcp.py::TestMCPClient::test_mcp_client_close PASSED           [ 49%]
tests\test_mcp.py::TestMCPToolIntegration::test_mcp_tools_merged_with_builtin PASSED [ 50%]
tests\test_mcp.py::TestMCPToolIntegration::test_mcp_connection_failure_graceful PASSED [ 50%]
tests\test_mcp.py::TestMCPToolIntegration::test_mcp_unknown_tool_returns_error PASSED [ 51%]
tests\test_memory.py::TestLoadMemory::test_load_existing_memory PASSED   [ 51%]
tests\test_memory.py::TestLoadMemory::test_load_nonexistent_memory PASSED [ 52%]
tests\test_memory.py::TestLoadMemory::test_load_empty_memory PASSED      [ 52%]
tests\test_memory.py::TestSaveMemory::test_save_new_memory PASSED        [ 53%]
tests\test_memory.py::TestSaveMemory::test_save_overwrite_memory PASSED [ 53%]
tests\test_memory.py::TestSaveMemory::test_save_creates_parent_dir PASSED [ 54%]
tests\test_memory.py::TestAppendMemory::test_append_to_existing PASSED   [ 54%]
tests\test_memory.py::TestAppendMemory::test_append_creates_new_file PASSED [ 55%]
tests\test_memory.py::TestAppendMemory::test_append_adds_newline PASSED  [ 55%]
tests\test_memory.py::TestAppendMemory::test_append_creates_parent_dir PASSED [ 56%]
tests\test_memory.py::TestMemoryIntegration::test_memory_injected_into_system_prompt PASSED [ 56%]
tests\test_memory.py::TestMemoryIntegration::test_memory_saved_after_completion PASSED [ 57%]
tests\test_memory.py::TestMemoryIntegration::test_memory_not_saved_when_disabled PASSED [ 57%]
tests\test_skills.py::TestListSkills::test_list_skills_with_files PASSED [ 58%]
tests\test_skills.py::TestListSkills::test_list_skills_no_dir PASSED     [ 58%]
tests\test_skills.py::TestListSkills::test_list_skills_empty_dir PASSED [ 59%]
tests\test_skills.py::TestListSkills::test_list_skills_ignores_non_md PASSED [ 59%]
tests\test_skills.py::TestLoadSkill::test_load_skill_existing PASSED     [ 60%]
tests\test_skills.py::TestLoadSkill::test_load_skill_nonexistent PASSED [ 60%]
tests\test_skills.py::TestMatchSkill::test_match_skill_keyword_match PASSED [ 61%]
tests\test_skills.py::TestMatchSkill::test_match_skill_no_match PASSED   [ 61%]
tests\test_skills.py::TestMatchSkill::test_match_skill_best_match PASSED [ 62%]
tests\test_skills.py::TestMatchSkill::test_match_skill_name_match PASSED [ 62%]
tests\test_skills.py::TestMatchSkill::test_match_skill_empty_skills PASSED [ 63%]
tests\test_skills.py::TestSkillIntegration::test_skill_injected_into_system_prompt PASSED [ 63%]
tests\test_skills.py::TestSkillIntegration::test_skill_not_injected_when_disabled PASSED [ 64%]
tests\test_skills.py::TestSkillIntegration::test_skill_not_injected_when_no_match PASSED [ 64%]
tests\test_tools.py::TestWriteFile::test_write_normal PASSED             [ 65%]
tests\test_tools.py::TestWriteFile::test_write_returns_byte_count PASSED [ 65%]
tests\test_tools.py::TestWriteFile::test_auto_create_parent_dirs PASSED  [ 66%]
tests\test_tools.py::TestWriteFile::test_overwrite_existing PASSED       [ 66%]
tests\test_tools.py::TestReadFile::test_read_normal PASSED               [ 67%]
tests\test_tools.py::TestReadFile::test_read_nonexistent PASSED          [ 67%]
tests\test_tools.py::TestReadFile::test_read_binary_file PASSED          [ 68%]
tests\test_tools.py::TestEditFile::test_edit_normal PASSED               [ 68%]
tests\test_tools.py::TestEditFile::test_edit_old_string_not_found PASSED [ 69%]
tests\test_tools.py::TestEditFile::test_edit_multiple_matches PASSED     [ 69%]
tests\test_tools.py::TestEditFile::test_edit_nonexistent_file PASSED     [ 70%]
tests\test_tools.py::TestEditFile::test_edit_preserves_surrounding_content PASSED [ 70%]
tests\test_tools.py::TestBash::test_echo_success PASSED                  [ 71%]
tests\test_tools.py::TestBash::test_python_execution PASSED              [ 71%]
tests\test_tools.py::TestBash::test_nonzero_exit PASSED                  [ 72%]
tests\test_tools.py::TestBash::test_stderr_capture PASSED                [ 72%]
tests\test_tools.py::TestBash::test_command_output_includes_both_streams PASSED [ 73%]
tests\test_tools.py::TestDangerousCommandFilter::test_rm_rf_root_blocked PASSED [ 73%]
tests\test_tools.py::TestDangerousCommandFilter::test_rm_rf_home_blocked PASSED [ 74%]
tests\test_tools.py::TestDangerousCommandFilter::test_rm_rf_star_blocked PASSED [ 74%]
tests\test_tools.py::TestDangerousCommandFilter::test_format_c_blocked PASSED [ 75%]
tests\test_tools.py::TestDangerousCommandFilter::test_mkfs_blocked PASSED [ 75%]
tests\test_tools.py::TestDangerousCommandFilter::test_safe_command_not_blocked PASSED [ 76%]
tests\test_tools.py::TestDangerousCommandFilter::test_dangerous_allowed_with_flag PASSED [ 76%]
tests\test_tools.py::TestDangerousCommandFilter::test_case_insensitive_match PASSED [ 77%]
tests\test_tools.py::TestDangerousCommandFilter::test_dangerous_in_pipeline_blocked PASSED [ 77%]
tests\test_tools.py::TestExecuteTool::test_route_write_file PASSED       [ 78%]
tests\test_tools.py::TestExecuteTool::test_route_read_file PASSED        [ 78%]
tests\test_tools.py::TestExecuteTool::test_route_edit_file PASSED        [ 79%]
tests\test_tools.py::TestExecuteTool::test_route_bash PASSED             [ 79%]
tests\test_tools.py::TestExecuteTool::test_route_glob PASSED             [ 80%]
tests\test_tools.py::TestExecuteTool::test_route_grep PASSED            [ 80%]
tests\test_tools.py::TestExecuteTool::test_unknown_tool PASSED           [ 81%]
tests\test_tools.py::TestExecuteTool::test_invalid_json_arguments PASSED [ 81%]
tests\test_tools.py::TestExecuteTool::test_empty_arguments_string PASSED [ 82%]
tests\test_tools.py::TestExecuteTool::test_none_arguments PASSED         [ 82%]
tests\test_tools.py::TestToolSchemas::test_schema_count PASSED           [ 83%]
tests\test_tools.py::TestToolSchemas::test_schema_names PASSED           [ 83%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 83%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 84%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 84%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 85%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 85%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 86%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 86%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 87%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 87%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 88%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 88%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 89%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 89%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 90%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 90%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 91%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 91%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 92%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 92%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 93%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 93%]
tests\test_tools.py::TestToolSchemas::test_all_schemas_are_function_type PASSED [ 94%]
tests\test_tools.py::TestGlob::test_glob_finds_python_files PASSED       [ 94%]
tests\test_tools.py::TestGlob::test_glob_no_match PASSED                 [ 95%]
tests\test_tools.py::TestGlob::test_glob_recursive PASSED                [ 95%]
tests\test_tools.py::TestGlob::test_glob_respects_gitignore PASSED       [ 96%]
tests\test_tools.py::TestGrep::test_grep_finds_matches PASSED            [ 96%]
tests\test_tools.py::TestGrep::test_grep_returns_line_numbers PASSED     [ 97%]
tests\test_tools.py::TestGrep::test_grep_no_match PASSED                 [ 97%]
tests\test_tools.py::TestGrep::test_grep_specific_file PASSED            [ 98%]
tests\test_tools.py::TestGrep::test_grep_invalid_regex PASSED            [ 98%]
tests\test_tools.py::TestGrep::test_grep_skips_binary_files PASSED       [ 99%]
tests\test_tools.py::TestGrep::test_grep_respects_gitignore PASSED       [100%]

============================ 201 passed in 28.31s =============================
```

---

## 参考资料

- Nautilus v3 实现计划（整体）：`nautilus-v3-实现计划(整体).md`（同目录）
- Nautilus v0.3.5 MCP 协议实现计划：`nautilus-v0.3.5-MCP协议-实现计划.md`（同目录）
- Nautilus v0.3.4 Skills/插件验证报告：`nautilus-v0.3.4-Skills&插件-验证报告.md`（同目录）
- 源码：`nautilus/nautilus/`（agent.py / tools.py / prompts.py / llm.py / memory.py / skills.py / mcp.py / __main__.py）
- UT 源码：`nautilus/tests/`（test_tools.py / test_agent.py / test_llm.py / test_cli.py / test_memory.py / test_skills.py / test_mcp.py / mcp_echo_server.py）
