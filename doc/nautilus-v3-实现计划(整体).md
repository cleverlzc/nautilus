# Nautilus v3 实现计划

## Context

v2 已完成并通过 E2E 验证（895 行，6 工具，125 tests + 11 E2E 场景）。v2 后期补充的 P0 修复（GBK 编码修复 + bash 危险命令过滤）归属 v2 范围，已随 v2 一起发布。

设计文档（`coding-agent-第一性原理设计方案.md` §五演进路线）定义 v3 目标为"产品级"，结合 v3 大颗粒特性实现优先级排序文档（`nautilus-v3-特性优先级排序.md` §优先级排序（从高到低））——在 v2"可用"基础上补齐上下文压缩、子 agent、plan mode、记忆系统、Skills/插件、MCP 协议 6 个大颗粒特性。

v3 采用**小版本迭代**策略：每个特性对应一个小版本，逐个实现、逐个验证、逐个发布，降低大颗粒特性的实施风险。

当前代码基线（v2 含 P0 修复后）：987 行 Python 源码 + 146 tests。

## 项目位置

```
...\AIAgent\mycodingagent\nautilus\
```

## v3 小版本计划（6 个迭代）

| 小版本 | 特性 | 优先级 | 依赖 | 预估行数 |
|--------|------|--------|------|---------|
| v0.3.0 | 上下文压缩 | P1 | — | ~+60 行 |
| v0.3.1 | 子 agent（上下文隔离） | P1 | 上下文压缩 | ~+120 行 |
| v0.3.2 | plan mode | P2 | — | ~+80 行 |
| v0.3.3 | 记忆系统 | P3 | — | ~+100 行 |
| v0.3.4 | Skills/插件 | P3 | 记忆系统 | ~+80 行 |
| v0.3.5 | MCP 协议 | P4 | — | ~+150 行 |

> **注**：P0（GBK 编码修复 + bash 危险命令过滤）已随 v2 发布，不计入 v3 范围。v3 从 P1 开始。

---

## v0.3.0：上下文压缩

### Context

Nautilus v2 的 `messages` 列表在 ReAct 循环中无界增长——每轮迭代追加 assistant 消息 + tool 结果消息，10+ 轮后总 token 可能超出 context window。当前只有单条工具结果的截断（`_truncate_for_llm`），没有对整体历史做预算控制。这是 ToC 框架中的"次瓶颈"（context window），也是子 agent 的前置依赖。

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `nautilus/nautilus/agent.py` | 新增 `_messages_token_estimate(messages)`（~18 行）：遍历 messages，对每条消息的 content + tool_calls arguments 调用已有 `_estimate_tokens()`，处理 dict 和 SDK 对象两种格式。新增 `_compress_history(messages, max_tokens)`（~6 行）：滑动窗口从 index 2 逐条弹出最旧消息，直到预算达标或只剩 system+user。`run_agent()` 新增 `max_context_tokens: int = 32000` 参数，循环体开头（LLM 调用前）调用 `_compress_history` |
| `nautilus/nautilus/__main__.py` | 新增 `--max-context-tokens` CLI 参数（默认 32000），传到 `run_agent(max_context_tokens=...)` |
| `tests/test_agent.py` | 新增 `TestMessagesTokenEstimate`（4 tests：纯 dict / 空 / dict+tool_calls / SDK 对象）、`TestCompressHistory`（4 tests：未超预算不压缩 / 超预算逐条弹出 / 永不丢弃 system+user / 仅剩 system+user）、`TestRunAgentContextCompression`（1 test：mock LLM 多轮迭代 + 大输出，验证 messages 被压缩到预算以内） |
| `tests/test_cli.py` | 新增 `test_max_context_tokens_flag` + `test_default_max_context_tokens_is_32000`（2 tests） |

### 实现细节

**策略**：滑动窗口丢弃最旧迭代（不做 LLM 总结，避免额外 LLM 调用——ToC 服从约束）

**agent.py 新增函数**：
```python
def _messages_token_estimate(messages) -> int:
    """Estimate total tokens across all messages (dict or SDK objects)."""
    total = 0
    for m in messages:
        if isinstance(m, dict):
            total += _estimate_tokens(m.get("content", ""))
            for tc in m.get("tool_calls", []) or []:
                fn = tc.get("function", {})
                total += _estimate_tokens(fn.get("arguments", ""))
        else:
            total += _estimate_tokens(getattr(m, "content", "") or "")
            for tc in getattr(m, "tool_calls", None) or []:
                fn = getattr(tc, "function", None)
                if fn is not None:
                    total += _estimate_tokens(getattr(fn, "arguments", "") or "")
    return total

def _compress_history(messages, max_tokens: int) -> None:
    """In-place sliding window: drop oldest messages (after system+user)
    until estimated tokens fit the budget. Never touches system/user."""
    while len(messages) > 2 and _messages_token_estimate(messages) > max_tokens:
        messages.pop(2)
```

**run_agent 循环体**：
```python
for i in range(max_iter):
    _compress_history(messages, max_context_tokens)  # NEW: 每轮 LLM 调用前压缩
    # ... 后续逻辑不变 ...
```

**预算**：默认 32000 tokens（~128K context 的保守 25%），`--max-context-tokens` 可配。与已有的 `_truncate_for_llm`（单条工具结果截断）形成两层防护。

### 版本号更新

| 文件 | 变更 |
|------|------|
| `nautilus/__init__.py` | `0.2.0` → `0.3.0` |
| `pyproject.toml` | `version = "0.2.0"` → `version = "0.3.0"` |

### 验证方式

```bash
cd .../AIAgent/mycodingagent/nautilus
PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
```
预期：146 + ~11 新增 ≈ 157 tests 全部通过

---

## v0.3.1：子 agent（上下文隔离）

### Context

子 agent 是上下文压缩的延伸——压缩是"丢弃旧消息"，子 agent 是"把长子任务的上下文隔离到独立循环"。主 agent 可以派生子 agent 执行独立子任务（如"搜索所有包含 X 的文件"），子 agent 用独立的 messages 列表完成循环后只返回最终结果给主 agent，不污染主循环上下文。

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `nautilus/agent.py` | 新增 `run_subagent(prompt, client, model, max_iter, ...)` 函数：独立 messages 列表 + 独立 ReAct 循环 + 只返回最终结果字符串。主 agent 通过新工具 `delegate_task` 调用 |
| `nautilus/tools.py` | 新增 `delegate_task` 工具 schema + 路由。该工具内部调用 `run_subagent()`，不在 `execute_tool` 中直接执行（需要 client 引用，属于 agent 层逻辑） |
| `nautilus/prompts.py` | 可用工具列表新增 `delegate_task(prompt, ...)` 说明 + 准则"复杂子任务可委派子 agent 隔离上下文" |
| `nautilus/__main__.py` | 无新参数（子 agent 复用主 agent 的 model/client 配置） |

### 实现细节

**agent.py 新增 `run_subagent()`**：
```python
def run_subagent(prompt, client, model, max_iter=10, max_tool_output_chars=6000, ...):
    """运行子 agent，独立 messages 列表，返回最终结果字符串。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_SUBAGENT},
        {"role": "user", "content": prompt},
    ]
    for i in range(max_iter):
        _compress_history(messages, max_context_tokens)
        response = complete_with_retry(client, model=model, messages=messages, tools=TOOL_SCHEMAS)
        message = response.choices[0].message
        if not message.tool_calls:
            return message.content or ""
        messages.append(message)
        for call in message.tool_calls:
            result = execute_tool(call, ...)
            messages.append({"role": "tool", ...})
    return "子 agent 达到最大迭代次数，未完成任务。"
```

**agent.py `run_agent()` 循环内新增 `delegate_task` 处理**：
```python
for call in message.tool_calls:
    if call.function.name == "delegate_task":
        # 委派子任务到独立 agent
        result = run_subagent(args.get("prompt", ""), client, model, ...)
    else:
        result = execute_tool(call, allow_dangerous=approval)
```

**tools.py 新增 `delegate_task` schema**：
```python
{
    "type": "function",
    "function": {
        "name": "delegate_task",
        "description": "将子任务委派给独立子 agent 执行，隔离上下文。",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "子任务描述"}
            },
            "required": ["prompt"]
        }
    }
}
```

**prompts.py 新增 `SYSTEM_PROMPT_SUBAGENT`**：
- 简化版系统提示词，只关注执行子任务并返回结果，不含"完成后给摘要"等准则

### 测试

- `TestRunSubagent`：mock LLM 验证子 agent 独立 messages 列表 + 只返回最终结果
- `TestDelegateTask`：mock LLM 验证主 agent 调用 `delegate_task` + 子 agent 结果回灌主循环
- 验证主 agent messages 不被子 agent 的中间步骤污染

### 版本号更新

`0.3.0` → `0.3.1`

---

## v0.3.2：plan mode

### Context

plan mode 让 agent 先规划再执行——用户提交任务后，agent 先用 LLM 生成执行计划（文本），用户确认后进入执行阶段。减少 LLM 试错圈数（ToC：提升有效产出 T）。

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `nautilus/agent.py` | `run_agent()` 新增 `plan_mode: bool = False` 参数。plan_mode=True 时第一阶段调用 LLM 生成计划（不调工具，仅输出文本），打印计划 + `input("是否执行此计划? [y/N]")`，用户确认后进入第二阶段（正常 ReAct 循环） |
| `nautilus/prompts.py` | 新增 `SYSTEM_PROMPT_PLAN` 提示词：要求 LLM 输出结构化执行计划（步骤列表），不调用工具 |
| `nautilus/__main__.py` | 新增 `--plan` CLI 参数 |

### 实现细节

**agent.py `run_agent()` plan 分支**：
```python
if plan_mode:
    # Phase 1: 生成计划
    plan_response = complete_with_retry(client, model=model,
        messages=[{"role": "system", "content": SYSTEM_PROMPT_PLAN},
                  {"role": "user", "content": prompt}])
    plan = plan_response.choices[0].message.content
    print(f"📋 执行计划:\n{plan}\n")
    user_input = input("是否执行此计划? [y/N]: ").strip().lower()
    if user_input not in ("y", "yes"):
        print("用户取消了执行。")
        return
    # Phase 2: 正常 ReAct 循环（计划已确认）
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": plan},
        {"role": "user", "content": "请按计划执行。"},
    ]
```

### 测试

- `TestPlanMode`：mock LLM 验证计划生成 + 用户确认 → 进入执行循环
- `TestPlanModeRejected`：mock LLM + 用户拒绝 → 退出
- CLI `--plan` 参数测试

### 版本号更新

`0.3.1` → `0.3.2`

---

## v0.3.3：记忆系统

### Context

记忆系统让 agent 跨会话保持上下文——agent 自动读取/写入项目级记忆文件（如 `.nautilus/memory.md`），记录项目结构、关键决策、已完成的任务等。避免每次从零理解项目（ToC：降低运行费用 OE）。

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `nautilus/memory.py` | **新文件**。`load_memory(path)` + `save_memory(path, content)` + `Memory` 类管理记忆条目 |
| `nautilus/agent.py` | `run_agent()` 开头加载记忆文件注入 system prompt；循环结束后自动保存关键记忆 |
| `nautilus/prompts.py` | 系统提示词新增记忆相关说明 |
| `nautilus/__main__.py` | 新增 `--memory` CLI 参数（默认 `.nautilus/memory.md`） |

### 实现细节

**memory.py**：
```python
def load_memory(path: str = ".nautilus/memory.md") -> str:
    """读取记忆文件，返回内容字符串。无文件返回空字符串。"""

def save_memory(path: str, content: str) -> str:
    """保存记忆内容到文件。自动创建父目录。"""

def append_memory(path: str, entry: str) -> str:
    """追加一条记忆条目到记忆文件。"""
```

**agent.py 集成**：
```python
def run_agent(..., memory_path: str = ".nautilus/memory.md"):
    # 加载记忆
    memory = load_memory(memory_path)
    system_content = SYSTEM_PROMPT
    if memory:
        system_content += f"\n\n## 项目记忆\n{memory}"
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt},
    ]
    # ... ReAct 循环 ...
    # 循环结束后保存记忆（简单版：保存用户 prompt + 最终回答摘要）
    final_answer = ...  # 从循环中提取
    if final_answer:
        append_memory(memory_path, f"## {prompt}\n{final_answer}\n")
```

### 测试

- `TestLoadMemory`：有文件/无文件/空文件
- `TestSaveMemory`：新建/覆盖/自动建目录
- `TestMemoryIntegration`：mock LLM 验证记忆注入 system prompt + 循环后保存

### 版本号更新

`0.3.2` → `0.3.3`

---

## v0.3.4：Skills/插件

### Context

Skills 让 agent 可复用工作流——将常见任务的解决方案沉淀为 Skill 文件（如 `.nautilus/skills/deploy.md`），agent 遇到类似任务时自动加载 Skill 指导执行。降低重复劳动（ToC：降低 OE）。

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `nautilus/skills.py` | **新文件**。`list_skills(dir)` + `load_skill(dir, name)` + `match_skill(prompt, skills)` |
| `nautilus/agent.py` | `run_agent()` 开头扫描 skills 目录，匹配当前 prompt 的 skill，注入 system prompt |
| `nautilus/prompts.py` | 系统提示词新增 skill 相关说明 |
| `nautilus/__main__.py` | 新增 `--skills-dir` CLI 参数（默认 `.nautilus/skills`） |

### 实现细节

**skills.py**：
```python
def list_skills(skills_dir: str = ".nautilus/skills") -> list[dict]:
    """扫描 skills 目录，返回 skill 元信息列表。"""
    # 每个 skill 是一个 .md 文件，文件名 = skill 名
    # 文件内容 = skill 指导（markdown）

def load_skill(skill_path: str) -> str:
    """读取 skill 文件内容。"""

def match_skill(prompt: str, skills: list[dict]) -> str | None:
    """简单关键词匹配：skill 元信息中的 keywords 与 prompt 重叠则返回。"""
    # skill 文件头部可包含 YAML frontmatter: keywords, description
```

### 测试

- `TestListSkills`：有目录/无目录/空目录
- `TestLoadSkill`：正常读取/文件不存在
- `TestMatchSkill`：关键词匹配/不匹配/多 skill 匹配取最佳
- `TestSkillIntegration`：mock LLM 验证 skill 注入 system prompt

### 版本号更新

`0.3.3` → `0.3.4`

---

## v0.3.5：MCP 协议

### Context

MCP（Model Context Protocol）让 agent 可接入外部工具服务器——通过标准化协议连接 MCP server，动态发现并调用其提供的工具。扩展工具集（ToC：扩展机制，不直接打破瓶颈）。

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `nautilus/mcp.py` | **新文件**。MCP client 实现：连接 MCP server（stdio/SSE）、发现工具、调用工具 |
| `nautilus/tools.py` | `execute_tool()` 新增 MCP 工具路由分支；`TOOL_SCHEMAS` 动态合并 MCP server 提供的 tool schemas |
| `nautilus/agent.py` | `run_agent()` 启动时连接 MCP servers，合并工具 schema |
| `nautilus/__main__.py` | 新增 `--mcp-server` CLI 参数（可多次指定） |

### 实现细节

**mcp.py**（最小实现，仅支持 stdio 传输）：
```python
class MCPClient:
    """MCP client: 连接 MCP server，发现并调用工具。"""
    def __init__(self, server_command: str):
        # 启动子进程，通过 stdio 通信
        # JSON-RPC 2.0 协议

    def list_tools(self) -> list[dict]:
        """调用 MCP server 的 tools/list 方法，返回 tool schemas。"""

    def call_tool(self, name: str, arguments: dict) -> str:
        """调用 MCP server 的 tools/call 方法，返回结果。"""

    def close(self):
        """关闭连接。"""
```

**tools.py 集成**：
```python
def execute_tool(tool_call, allow_dangerous=False, mcp_client=None):
    name = tool_call.function.name
    # ... 现有 6 个工具路由 ...
    # 如果不在内置工具中，尝试 MCP
    if mcp_client:
        return mcp_client.call_tool(name, args)
    return f"错误：未知工具：{name}"
```

**agent.py 集成**：
```python
def run_agent(..., mcp_servers=None):
    mcp_clients = []
    mcp_tools = []
    for server_cmd in (mcp_servers or []):
        client = MCPClient(server_cmd)
        mcp_clients.append(client)
        mcp_tools.extend(client.list_tools())

    # 合并工具 schema
    all_tools = TOOL_SCHEMAS + mcp_tools
    # 循环中用 all_tools 替代 TOOL_SCHEMAS
```

### 测试

- `TestMCPClient`：mock 子进程验证 JSON-RPC 通信
- `TestMCPToolIntegration`：mock MCP server + mock LLM 验证 MCP 工具调用
- CLI `--mcp-server` 参数测试

### 版本号更新

`0.3.4` → `0.3.5`

---

## 版本号规划

| 小版本 | `__init__.py` / `pyproject.toml` | 特性 |
|--------|------|------|
| v0.3.0 | `0.3.0` | 上下文压缩 |
| v0.3.1 | `0.3.1` | 子 agent（上下文隔离） |
| v0.3.2 | `0.3.2` | plan mode |
| v0.3.3 | `0.3.3` | 记忆系统 |
| v0.3.4 | `0.3.4` | Skills/插件 |
| v0.3.5 | `0.3.5` | MCP 协议 |

## v3 CLI 参数（完整规划）

```
$ nautilus "创建一个 hello.py"
$ nautilus --stream --approval "修复 bug"
$ nautilus --text-mode --max-context-tokens 8000 "长任务"
$ nautilus --plan "重构整个模块"                     # v0.3.2
$ nautilus --memory .nautilus/memory.md "继续上次任务"  # v0.3.3
$ nautilus --skills-dir .nautilus/skills "部署项目"    # v0.3.4
$ nautilus --mcp-server "npx @mcp/filesystem" "读取外部文件"  # v0.3.5
```

参数（v3 完整）：
- `prompt`（positional，支持交互式输入）
- `--model`（默认 gpt-4）
- `--api-key`（或 OPENAI_API_KEY 环境变量）
- `--base-url`（或 OPENAI_BASE_URL 环境变量）
- `--max-iter`（默认 20）
- `--max-tool-output`（默认 6000）
- `--max-context-tokens`（默认 32000，v0.3.0）
- `--stream`（默认 False）
- `--approval`（默认 False）
- `--text-mode`（默认 False）
- `--plan`（默认 False，v0.3.2）
- `--memory`（默认 `.nautilus/memory.md`，v0.3.3）
- `--skills-dir`（默认 `.nautilus/skills`，v0.3.4）
- `--mcp-server`（可多次指定，v0.3.5）

## v3 新增文件

| 文件 | 小版本 | 用途 |
|------|--------|------|
| `nautilus/memory.py` | v0.3.3 | 记忆系统（加载/保存/追加） |
| `nautilus/skills.py` | v0.3.4 | Skills 管理（列表/加载/匹配） |
| `nautilus/mcp.py` | v0.3.5 | MCP client（连接/发现/调用） |

## 终端输出格式（v3 完整）

```
📋 执行计划:                              # v0.3.2 plan mode
1. 搜索相关文件
2. 修改 calculator.py
3. 运行测试验证
是否执行此计划? [y/N]: y

💭 好的，我来搜索相关文件。
🔧 glob("*.py")
   → calc.py, hello.py, utils.py
🔧 delegate_task("搜索所有包含 divide 的文件")  # v0.3.1 子 agent
   → 子 agent 完成：calc.py:4:def divide(a, b):
🔧 edit_file("calc.py", old: <15 字符>, new: <20 字符>)
   → 成功修改 calc.py
🔧 bash("python -m pytest")
   执行此命令? [y/N]: y                     # v2 权限审批
   → 3 passed
🔄 LLM API 重试 (第 1/3 次)，等待 1s...      # v2 错误恢复
✅ 已完成。修复了除法 bug，测试全部通过。

💾 记忆已保存到 .nautilus/memory.md          # v0.3.3 记忆系统
```

## 不修改的文件

- `pyproject.toml` 依赖列表：v3 无新依赖（全部用 Python stdlib：subprocess, json, os, re, pathlib, fnmatch）
- `nautilus/tests/__init__.py`：无需改动

## 验证方式

每个小版本发布时：
1. 运行单元测试：`PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="`
2. 运行 E2E 测试（Ollama + qwen2.5:7b 或 deepseek-r1:8b）
3. 更新版本号 `__init__.py` + `pyproject.toml`
4. 生成对应小版本的实现总结 + 验证报告

## v3 完成后的预期规模

| 维度 | v2 基线 | v3 预估 |
|------|---------|---------|
| 源码行数 | 895 | ~1500 |
| 测试数 | 125 | ~200+ |
| 工具数 | 6 | 7（+delegate_task）+ MCP 动态扩展 |
| CLI 参数 | 9 | 13 |
| 新文件 | 0 | 3（memory.py, skills.py, mcp.py） |
| E2E 场景 | 11 | ~15+ |
