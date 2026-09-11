# Nautilus 🐚

> **鹦鹉螺：螺旋逼近答案的 coding agent**
>
> Nautilus 是一个从第一性原理出发、用最小代码量表达 coding agent 本质的 Python 项目。它不是产品级工具，而是一个**学习项目**——用 ~1496 行代码验证"LLM + 7+N 个工具 + 一个 while 循环 + 上下文压缩 + 子 agent + plan mode + 记忆系统 + Skills/插件 + MCP 协议"就是 coding agent 的产品级核心，并通过 E2E 真实场景验证确认可用。

名称取自鹦鹉螺的对数螺旋（Logarithmic Spiral）：ReAct 循环不是原地打转的死循环，而是螺旋式逼近——每一圈 Thought→Action→Observation 都基于上一轮观察修正认知，朝答案收敛。

---

## 快速开始

### 安装

```bash
cd .../AIAgent/mycodingagent/nautilus
pip install -e .
```

依赖：`openai>=1.0.0`，Python >= 3.10。

### 配置

```bash
# OpenAI 官方 API
export OPENAI_API_KEY=sk-xxx

# 或 OpenAI 兼容 API（Ollama / vLLM / LM Studio 等）
export OPENAI_API_KEY=test
export OPENAI_BASE_URL=http://127.0.0.1:11434/v1
```

> **Windows 用户**：GBK 编码修复已内置（`__main__.py` 入口 `sys.stdout.reconfigure`），无需额外设置 `PYTHONIOENCODING`。

### 运行

```bash
# 基础用法（支持 function calling 的模型）
nautilus "创建一个 hello.py，运行它，确认输出 hello world"

# 指定模型和迭代上限
nautilus --model qwen2.5:7b --max-iter 30 "重构 utils.py"

# v2 新增：流式输出
nautilus --stream "解释这个项目的架构"

# v2 新增：权限审批（bash 命令执行前需确认）
nautilus --approval "运行 rm -rf build/"

# v2 新增：text-mode（兼容不支持 function calling 的模型，如 deepseek-r1）
nautilus --model deepseek-r1:8b --text-mode "创建一个 hello.py，运行它"

# v3 新增：上下文压缩（默认 32000 tokens，超出后丢弃最旧迭代）
nautilus --max-context-tokens 8000 "长任务，多轮迭代"

# v3 新增：子 agent 上下文隔离（LLM 自行决定何时委派）
nautilus "用 delegate_task 委派子 agent 搜索所有 .py 文件并分析"

# v3 新增：plan mode（先生成计划，用户确认后再执行）
nautilus --plan "重构整个模块"

# v3 新增：记忆系统（跨会话上下文保持）
nautilus --memory .nautilus/memory.md "分析这个项目的所有文件结构"

# v3 新增：Skills/插件（工作流复用）
nautilus --skills-dir .nautilus/skills "部署项目到生产环境"

# v3 新增：MCP 协议（连接外部工具服务器）
nautilus --mcp-server "npx @mcp/filesystem /tmp" "读取 /tmp/test.txt"

# 组合使用
nautilus --stream --approval --plan --memory .nautilus/memory.md --skills-dir .nautilus/skills --mcp-server "npx @mcp/filesystem" "复杂任务"

# 支持管道输入
echo "解释这个项目" | nautilus
```

### 验证安装

```bash
nautilus --help                                         # 查看 CLI 帮助
python -m pytest tests/ -v -o "addopts="                # 运行 201 个单元测试
```

---

## CLI 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `prompt` | 任务描述（位置参数，不传则从 stdin 读取） | — |
| `--model` | 模型名 | `gpt-4` |
| `--api-key` | API key（不传则读 `OPENAI_API_KEY` 环境变量） | `None` |
| `--base-url` | API base URL（不传则读 `OPENAI_BASE_URL` 环境变量） | `None` |
| `--max-iter` | agent 循环最大迭代次数 | `20` |
| `--max-tool-output` | 单次工具结果回灌 LLM 的最大字符数（约 1500 tokens） | `6000` |
| `--max-context-tokens` | 对话历史的 token 预算（超出后丢弃最旧迭代） | `32000` |
| `--stream` | 启用流式输出，实时打印 LLM 生成的 token | `False` |
| `--approval` | 启用权限审批，bash 命令执行前需用户确认 | `False` |
| `--text-mode` | 启用文本模式工具调用（兼容不支持 function calling 的模型） | `False` |
| `--plan` | 启用 plan mode：先生成执行计划，用户确认后再执行 | `False` |
| `--memory` | 启用记忆系统，指定记忆文件路径（如 `.nautilus/memory.md`） | `None` |
| `--skills-dir` | 启用 Skills 系统，指定 skills 目录路径（如 `.nautilus/skills`） | `None` |
| `--mcp-server` | 连接 MCP server（可多次指定），如 `--mcp-server 'npx @mcp/filesystem'` | `None` |

---

## 项目结构

```
nautilus/
├── pyproject.toml              # 16 行 — 项目元数据 + openai 依赖 + CLI 入口（v0.3.5）
├── nautilus/                   # 源码包（1496 行）
│   ├── __init__.py             #   1 行 — 版本号（0.3.5）
│   ├── __main__.py             # 135 行 — CLI 入口（argparse + 14 个参数 + GBK 编码修复）
│   ├── agent.py                # 487 行 — ReAct 循环 + 上下文压缩 + 子 agent + plan mode + 记忆 + skills + MCP 连接/路由/关闭
│   ├── llm.py                  # 125 行 — OpenAI 兼容 client 工厂 + complete_with_retry + stream_complete
│   ├── mcp.py                  #  99 行 — MCPClient（stdio + JSON-RPC 2.0）
│   ├── memory.py               #  40 行 — load_memory + save_memory + append_memory
│   ├── prompts.py              # 121 行 — 系统提示词 + SUBAGENT + PLAN + TEXT_MODE + 记忆/技能说明
│   ├── skills.py               #  89 行 — list_skills + load_skill + match_skill + frontmatter 解析
│   └── tools.py                # 399 行 — 7 个工具 + execute_tool 路由 + .gitignore 过滤 + 危险命令过滤
├── tests/                      # 单元测试（201 个，全部通过）
│   ├── __init__.py             #   8 行
│   ├── test_tools.py           # 417 行 — 63 tests
│   ├── test_agent.py           # 1159 行 — 46 tests
│   ├── test_llm.py             # 286 行 — 18 tests
│   ├── test_cli.py             # 294 行 — 32 tests
│   ├── test_memory.py          # 198 行 — 13 tests
│   ├── test_skills.py          # 232 行 — 14 tests
│   ├── test_mcp.py             # 236 行 — 8 tests
│   └── mcp_echo_server.py      #  80 行 — E2E 测试用 MCP server
└── README.md
```

**总计：1496 行 Python 源码 + 201 个测试用例（全部通过）。**

---

## 架构

Nautilus 的不可约本质是五个组件：

```
┌──────────────────────────────────────────┐
│  ① LLM (认知)   ② Tools (行动)  ③ Loop (自主)  │
│       ↑              ↓              ↻      │
│  ④ Context (记忆) ←──────────────────┘     │
│       ↑                                    │
│  ⑤ Interface (I/O)  ← user prompt         │
└──────────────────────────────────────────┘
```

### 核心循环（agent.py）

```python
for i in range(max_iter):
    _compress_history(messages, max_context_tokens)  # v3: 上下文压缩

    if plan_mode and i == 0:
        # v3: Phase 1 — 生成执行计划，用户确认后注入 messages
        ...

    if stream:
        message = stream_complete(client, model=model, messages=messages)
    else:
        response = complete_with_retry(client, model=model, messages=messages, tools=all_tools)
        message = response.choices[0].message

    if not message.tool_calls:
        # 最终回答 — 保存记忆后返回
        if memory_path and final_answer:
            append_memory(memory_path, f"## {prompt}\n{final_answer}\n")
        return
    messages.append(message)             # 思考回灌
    for call in message.tool_calls:
        if call.function.name == "delegate_task":
            result = run_subagent(prompt=..., client=client)  # v3: 子 agent
        else:
            result = execute_tool(call)  # 行动
        messages.append({"role": "tool", "tool_call_id": call.id,
                         "content": _truncate_for_llm(result, max_tool_output_chars)})
```

### 七个内置工具 + N 个 MCP 工具

| 工具 | 参数 | 用途 |
|------|------|------|
| `read_file` | `path` | 读取 utf-8 文本文件 |
| `write_file` | `path`, `content` | 新建文件或整文件覆盖，自动创建父目录 |
| `edit_file` | `path`, `old_string`, `new_string` | 精确局部修改，要求 old_string 精确匹配且唯一 |
| `glob` | `pattern`, `root?` | 递归搜索匹配文件名的文件路径，cap 200 条 |
| `grep` | `pattern`, `path?`, `root?` | 在文件中搜索匹配正则的行，返回 path:lineno:line，cap 100 条 |
| `delegate_task` | `prompt` | 将子任务委派给独立子 agent 执行，隔离上下文 |
| `bash` | `command` | 执行 shell 命令，30s 超时，捕获 stdout+stderr+exit code |

### 功能演进

| 功能 | 版本 | 实现 |
|------|------|------|
| **Grep/Glob 搜索工具** | v2 | 纯 Python（pathlib + fnmatch + re），自动过滤 .gitignore |
| **错误恢复** | v2 | `complete_with_retry()` 指数退避重试 3 次，区分可重试/不可重试错误 |
| **流式输出** | v2 | `stream_complete()` chunk 重组，content 实时 print(flush=True) |
| **权限审批** | v2 | `--approval` 模式下 bash 执行前弹 `input`，拒绝则 observation 回灌 LLM 自纠 |
| **.gitignore 感知** | v2 | `_load_gitignore()` + `_is_ignored()`，glob/grep 自动过滤 |
| **token 预算控制** | v1 | `_truncate_for_llm()` 截断单条工具结果（默认 6000 字符） |
| **text-mode** | v2 | `--text-mode` prompt-based 工具调用，兼容任何 LLM |
| **GBK 编码修复** | v2+P0 | `__main__.py` 入口 `sys.stdout.reconfigure(encoding="utf-8")` |
| **危险命令过滤** | v2+P0 | `_DANGEROUS_PATTERNS` 黑名单 + `--approval` 绕过 |
| **上下文压缩** | v3.0 | `_compress_history()` 滑动窗口丢弃最旧迭代（默认 32000 tokens） |
| **子 agent** | v3.1 | `run_subagent()` 独立 messages + ReAct 循环 + 禁止递归 |
| **plan mode** | v3.2 | `--plan` Phase 1 生成计划 + 用户确认 + Phase 2 计划注入执行 |
| **记忆系统** | v3.3 | `--memory` 跨会话上下文保持（加载注入 system prompt + 完成后追加保存） |
| **Skills/插件** | v3.4 | `--skills-dir` 工作流复用（关键词匹配 skill 注入 system prompt"技能指导"段落） |
| **MCP 协议** | v3.5 | `--mcp-server` 连接外部工具服务器（stdio + JSON-RPC 2.0，动态发现+调用 MCP 工具） |

### 终端输出示例

```
📋 执行计划:                                    # v3 plan mode
1. [glob] 搜索所有 .py 文件
2. [read_file] 读取 calc.py
3. [edit_file] 添加 sqrt 函数
4. [bash] 运行测试验证
是否执行此计划? [y/N]: y

💭 好的，按计划执行。
🔧 delegate_task("读取 calc.py，分析所有函数")     # v3 子 agent
   📤 委派子 agent: 读取 calc.py，分析所有函数
   📥 子 agent 完成: calc.py 包含 7 个函数...
   → calc.py 包含 7 个函数...
🔧 edit_file("calc.py", old: <20 字符>, new: <35 字符>)
   → 成功修改 calc.py
🔧 bash("python main.py")
   执行此命令? [y/N]: y                            # v2 权限审批
   → [LOG] Calculator started
Result: 3
...
[exit code: 0]

✅ 已完成。添加了 sqrt 函数，测试全部通过。

💾 记忆已保存到 .nautilus/memory.md               # v3 记忆系统
🔗 MCP connections closed.                            # v3 MCP 协议
```

---

## 设计决策

| 决策点 | v1 选择 | v2 演进 | v3 演进 |
|--------|---------|---------|---------|
| 语言 | Python | — | — |
| 工具集 | read+write+edit+bash | + glob+grep | + delegate_task |
| 安全 | 全自动+日志 | + 权限审批 + 危险命令过滤 | — |
| 上下文 | 全量历史 + token 预算截断 | — | + 整体压缩 + 子 agent 隔离 |
| 输出 | collect 后 print | + 流式输出 | — |
| 循环终止 | LLM 不调工具=结束 | + max_iter 兜底 | — |
| LLM 兼容 | OpenAI function calling | + text-mode | — |
| 错误处理 | 无 | + 指数退避重试 | — |
| 执行模式 | 直接执行 | — | + plan mode（先规划再执行） |
| 跨会话 | 无 | — | + 记忆系统 |
| 工作流复用 | 无 | — | + Skills/插件（关键词匹配注入） |
| 工具扩展 | 7 内置工具 | — | + MCP 协议（动态发现外部工具） |
| 编码 | GBK 崩溃 | + GBK 修复 | — |

---

## 演进路线

```
v1 (MVP, ~378行)            v2 (可用, ~895行)          v3 (产品级, ~1496行)
─────────────               ─────────────              ──────────────
agent 循环                 + Grep/Glob(搜索)           + 上下文压缩 (v0.3.0) ✅
4 个核心工具               + 流式输出                   + 子 agent (v0.3.1) ✅
  (read/write/edit/bash)  + 权限审批                    + plan mode (v0.3.2) ✅
token 预算控制             + .gitignore 感知             + 记忆系统 (v0.3.3) ✅
OpenAI API               + 错误恢复                    + Skills/插件 (v0.3.4) ✅
CLI                      + text-mode 适配               + MCP 协议 (v0.3.5) ✅
                         + GBK 编码修复
                         + 危险命令过滤
                         v0.2.0                       v0.3.5
```

**v1 验收标准**：能在真实 repo 里完成"读取文件→理解→修改→跑测试→报告结果"闭环。✅ 已通过

**v2 验收标准**：在真实 LLM 环境下使用 `--stream --approval` 或 `--text-mode` 完成搜索+修改+验证闭环。✅ 已通过（Ollama + qwen2.5:7b / deepseek-r1:8b）

**v3 验收标准**：上下文压缩 + 子 agent + plan mode + 记忆系统 + Skills/插件 + MCP 协议在真实 LLM 下全部通过。✅ 已通过（v0.3.0~v0.3.5 全部完成）

---

## 测试

### 单元测试

```bash
cd .../AIAgent/mycodingagent/nautilus
python -m pytest tests/ -v -o "addopts="
```

| 测试模块 | 测试数 | 覆盖范围 |
|---------|--------|---------|
| `test_tools.py` | 63 | read/write/edit/glob/grep/bash/delegate_task + execute_tool 路由 + TOOL_SCHEMAS(7) + .gitignore 过滤 + 危险命令过滤 |
| `test_agent.py` | 46 | _truncate/_estimate_tokens/_truncate_for_llm/_print_tool_call + mock ReAct 闭环/max_iter/错误自纠/token 预算/审批/子 agent/plan mode |
| `test_llm.py` | 18 | create_client 工厂 + complete_with_retry 重试 + stream_complete 流式 |
| `test_cli.py` | 32 | --help/stdin/参数解析 + 14 个 CLI 参数测试 |
| `test_memory.py` | 13 | load_memory/save_memory/append_memory + 记忆注入/保存/禁用集成 |
| `test_skills.py` | 14 | list_skills/load_skill/match_skill + 技能注入/禁用/无匹配集成 |
| `test_mcp.py` | 8 | MCPClient initialize/list_tools/call_tool/close + MCP 工具合并/调用/失败降级集成 |
| **合计** | **201** | **全部通过** |

### E2E 端到端测试

**native function calling（qwen2.5:7b）**：

| 场景 | 命令 | 结果 |
|------|------|------|
| 基础任务 | `nautilus "创建 hello.py，运行它"` | ✅ write_file → bash → hello world |
| Grep/Glob | `nautilus "用 glob 搜索 .py，用 grep 搜索 divide"` | ✅ glob 找到 3 文件 → grep 定位 calc.py |
| 流式输出 | `nautilus --stream "read hello.py"` | ✅ read_file → 流式打印 → 正确回答 |
| 权限审批（同意） | `echo "y" \| nautilus --approval "echo ok"` | ✅ 弹 prompt → y → bash 执行成功 |
| 权限审批（拒绝） | `echo "n" \| nautilus --approval "echo no"` | ✅ bash 未执行 → observation 回灌 |
| 上下文压缩 | `nautilus --max-context-tokens 1500 "7 步任务"` | ✅ 压缩触发后 agent 仍正确完成 |
| 子 agent | `nautilus "用 delegate_task 委派子 agent 搜索"` | ✅ 子 agent 独立执行 → 结果回灌主循环 |
| plan mode（确认） | `echo "y" \| nautilus --plan "分析项目"` | ✅ Phase 1 生成计划 → Phase 2 执行 |
| plan mode（拒绝） | `echo "n" \| nautilus --plan "添加函数"` | ✅ "用户取消了执行" → 不进入循环 |
| 记忆（首次写入） | `nautilus --memory .nautilus/memory.md "glob 搜索"` | ✅ 💾 记忆已保存 → 文件创建正确 |
| 记忆（第二次读取） | `nautilus --memory .nautilus/memory.md "上次做了什么？"` | ✅ agent 引用上次结果 → 记忆追加 |
| Skills（有匹配） | `nautilus --skills-dir .nautilus/skills "部署项目"` | ✅ Agent 按 skill 步骤执行（building→testing→deploying） |
| Skills（无匹配） | `nautilus --skills-dir .nautilus/skills "glob 搜索文件"` | ✅ skill 未匹配，agent 按默认行为执行 |
| MCP（连接+调用） | `nautilus --mcp-server "python mcp_echo_server.py" "用 echo_text 回显 hello"` | ✅ 🔗 connected → 🔧 echo_text → [MCP] hello → 🔗 closed |

**text-mode（deepseek-r1:8b）**：

| 场景 | 命令 | 结果 |
|------|------|------|
| 基础任务 | `nautilus --text-mode "创建 hello.py"` | ✅ write_file → bash → hello world |
| Grep/Glob | `nautilus --text-mode "glob + grep 搜索"` | ✅ glob 找到 3 文件 → grep 定位 |
| 流式输出 | `nautilus --text-mode --stream "read hello.py"` | ✅ token 实时打印 → 回答 |
| 权限审批 | `nautilus --text-mode --approval "echo ok"` | ✅ 弹 prompt → 确认/拒绝 |

---

## 设计文档

| 文档 | 内容 |
|------|------|
| `coding-agent-第一性原理设计方案.md` | 第一性原理分解、标杆对比、三对设计张力、v1/v2/v3 架构、演进路线 |
| `nautilus-v1-实现计划.md` | v1 7 文件分解、工具 schema、CLI 设计 |
| `nautilus-v1-实现总结.md` | v1 实际行数、验证结果、使用方式 |
| `nautilus-v1-验证报告.md` | v1 77 个测试用例验证报告 |
| `nautilus-v2-实现计划.md` | v2 5 功能实现细节、文件清单、CLI 参数 |
| `nautilus-v2-实现总结.md` | v2 实际行数、6 功能验证结果、E2E 测试结果 |
| `nautilus-v2-验证报告.md` | v2 125 个测试 + 11 个 E2E 场景验证报告 |
| `nautilus-v3-特性优先级排序.md` | v3 9 个候选特性优先级排序（ToC + 工程视角） |
| `nautilus-v3-实现计划(整体).md` | v3 6 个小版本（v0.3.0~v0.3.5）整体实现计划 |
| `nautilus-v0.3.0-上下文压缩-实现计划.md` | v0.3.0 上下文压缩实现计划 |
| `nautilus-v0.3.0-上下文压缩-实现总结.md` | v0.3.0 实现总结 |
| `nautilus-v0.3.0-上下文压缩-验证报告.md` | v0.3.0 146 tests + 4 E2E 场景验证报告 |
| `nautilus-v0.3.1-子agent(上下文隔离)-实现计划.md` | v0.3.1 子 agent 实现计划 |
| `nautilus-v0.3.1-子agent(上下文隔离)-实现总结.md` | v0.3.1 实现总结 |
| `nautilus-v0.3.1-子agent(上下文隔离)-验证报告.md` | v0.3.1 155 tests + 3 E2E 场景验证报告 |
| `nautilus-v0.3.2-plan mode-实现计划.md` | v0.3.2 plan mode 实现计划 |
| `nautilus-v0.3.2-plan mode-实现总结.md` | v0.3.2 实现总结 |
| `nautilus-v0.3.2-plan mode-验证报告.md` | v0.3.2 160 tests + 3 E2E 场景验证报告 |
| `nautilus-v0.3.3-记忆系统-实现计划.md` | v0.3.3 记忆系统实现计划 |
| `nautilus-v0.3.3-记忆系统-实现总结.md` | v0.3.3 实现总结 |
| `nautilus-v0.3.3-记忆系统-验证报告.md` | v0.3.3 175 tests + 3 E2E 场景验证报告 |
| `nautilus-v0.3.4-Skills&插件-实现计划.md` | v0.3.4 Skills/插件实现计划 |
| `nautilus-v0.3.4-Skills&插件-实现总结.md` | v0.3.4 实现总结 |
| `nautilus-v0.3.4-Skills&插件-验证报告.md` | v0.3.4 191 tests + 3 E2E 场景验证报告 |
| `nautilus-v0.3.5-MCP协议-实现计划.md` | v0.3.5 MCP 协议实现计划 |
| `nautilus-v0.3.5-MCP协议-实现总结.md` | v0.3.5 实现总结 |
| `nautilus-v0.3.5-MCP协议-验证报告.md` | v0.3.5 201 tests + 2 E2E 场景验证报告 |
| `nautilus-mvp(v1+v2)审视报告.md` | 资深 coding agent 工程师视角的 v1+v2 MVP 审视报告 |
| `nautilus-系统目标.md` | 企业架构（TOGAF 四域）+ 约束理论（Goldratt ToC/DBR）双视角分析 |
| `nautilus-结果质量评估标准.md` | Hermes 评估器三维模型适配：正确性/过程精准度/简洁度 |
| `nautilus名称含义.md` | 鹦鹉螺对数螺旋与 ReAct 循环的隐喻映射 |

---

## 已知限制

1. **text-mode 精度**：不支持 function calling 的模型依赖 prompt-based 工具调用，模型可能不严格遵循 ` ```tool_call {json} ` ` 格式，需要更强的系统提示词引导。
2. **上下文压缩**：`_compress_history` 丢弃最旧迭代而非总结，过小预算（<1000 tokens）可能导致 agent 失去关键上下文。
3. **bash 无沙箱**：`shell=True` 无容器隔离（有 `--approval` 审批门 + 危险命令黑名单兜底）。
4. **记忆无检索**：当前记忆系统是全量追加+全量注入，无向量检索/关键词搜索（长记忆文件会膨胀 system prompt）。
5. **Skills 关键词匹配**：当前 skill 匹配是简单关键词重叠，无语义匹配/向量检索（复杂 prompt 可能匹配不准）。
6. **MCP 仅 stdio 传输**：当前 MCP 实现仅支持 stdio 子进程传输，不支持 SSE/HTTP 传输。
7. **上级目录 pyproject.toml 干扰**：pytest 运行需 `-o "addopts="` 覆盖上级配置。

---

## 设计哲学

> **agent 的本质不在单个组件的强度，而在组合方式。**

Claude Code 的 51 万行是在这 1496 行之上叠加更复杂的安全/UX/扩展/多 agent 的工程化。Nautilus 用最简组合验证：**LLM + 7+N 个工具 + 一个 while 循环 + 上下文压缩 + 子 agent + plan mode + 记忆系统 + Skills/插件 + MCP 协议 = 产品级 coding agent**。

参考标杆：

| 项目 | 语言 | 关键特征 |
|------|------|---------|
| Claude Code | TypeScript/Bun | 精细工具策划（43 个）、MCP + Skills |
| Codex CLI | Rust (重写) | 沙箱优先、性能/安全最强 |
| Aider | Python | git-centric、纯终端 |
| OpenHands | Python+Docker | 事件驱动、Docker 沙箱、多 agent |

---

## License

个人学习项目，无开源协议。
