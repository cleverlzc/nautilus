# Nautilus 🐚

> **鹦鹉螺：螺旋逼近答案的 coding agent**
>
> Nautilus 是一个从第一性原理出发、用最小代码量表达 coding agent 本质的 Python 项目。它不是产品级工具，而是一个**学习项目**——用 ~895 行代码验证"LLM + 6 个工具 + 一个 while 循环"就是 coding agent 的不可约核心，并通过 E2E 真实场景验证确认可用。

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
export OPENAI_API_KEY=test-ollama-local-serving(eg.)
export OPENAI_BASE_URL=http://127.0.0.1:11434/v1(eg.)
```

> **Windows 用户**：需额外设置 `PYTHONIOENCODING=utf-8`，因为 `agent.py` 使用了 emoji 字符。

### 运行

```bash
# v2 基础用法（支持 function calling 的模型）
nautilus "创建一个 hello.py，运行它，确认输出 hello world"

# 指定模型和迭代上限
nautilus --model qwen-plus --base-url https://xxx "修复 bug"
nautilus --max-iter 30 "重构 utils.py"

# v2 新增：流式输出
nautilus --stream "解释这个项目的架构"

# v2 新增：权限审批（bash 命令执行前需确认）
nautilus --approval "运行 rm -rf build/"

# v2 新增：组合使用
nautilus --stream --approval "修复 src/calculator.py 中的除法 bug，然后跑测试"

# v2 新增：text-mode（兼容不支持 function calling 的模型，如 deepseek-r1）
nautilus --model deepseek-r1:8b --text-mode "创建一个 hello.py，运行它"

# 支持管道输入
echo "解释这个项目" | nautilus
```

### 验证安装

```bash
nautilus --help                                         # 查看 CLI 帮助
PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="  # 运行 125 个单元测试
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
| `--stream` | 启用流式输出，实时打印 LLM 生成的 token | `False` |
| `--approval` | 启用权限审批，bash 命令执行前需用户确认 | `False` |
| `--text-mode` | 启用文本模式工具调用（兼容不支持 function calling 的模型） | `False` |

---

## 项目结构

```
nautilus/
├── pyproject.toml              # 16 行 — 项目元数据 + openai 依赖 + CLI 入口（v0.2.0）
├── nautilus/                   # 源码包（895 行）
│   ├── __init__.py             #   1 行 — 版本号
│   ├── __main__.py             #  96 行 — CLI 入口（argparse + 9 个参数）
│   ├── agent.py                # 258 行 — 核心 ReAct 循环 + token 预算 + stream/approval/text_mode 分支 + stream 序列化修复
│   ├── llm.py                  # 125 行 — OpenAI 兼容 client 工厂 + complete_with_retry + stream_complete
│   ├── prompts.py              #  75 行 — 系统提示词 + SYSTEM_PROMPT_TEXT_MODE
│   └── tools.py                # 340 行 — 6 个工具 + execute_tool 路由 + .gitignore 过滤
├── tests/                      # 单元测试（125 个，全部通过）
│   ├── __init__.py             #   8 行
│   ├── test_tools.py           # 371 行 — 49 tests
│   ├── test_agent.py           # 604 行 — 28 tests
│   ├── test_llm.py             # 286 行 — 18 tests
│   └── test_cli.py             # 207 行 — 22 tests
└── README.md
```

**总计：895 行 Python 源码 + 125 个测试用例（全部通过）。**

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
    if text_mode:
        message = stream_complete(client, model=model, messages=messages)
    else:
        response = complete_with_retry(client, model=model, messages=messages, tools=TOOL_SCHEMAS)
        message = response.choices[0].message

    if text_mode:
        message.tool_calls = _parse_tool_calls_from_text(message.content)

    if not message.tool_calls:
        print(message.content)          # 没有工具调用 = 最终回答
        return
    messages.append(message)             # 思考回灌
    for call in message.tool_calls:
        result = execute_tool(call)      # 行动
        messages.append({"role": "tool", "tool_call_id": call.id,
                         "content": _truncate_for_llm(result, max_tool_output_chars)})
```

### 六个工具

| 工具 | 参数 | 用途 |
|------|------|------|
| `read_file` | `path` | 读取 utf-8 文本文件 |
| `write_file` | `path`, `content` | 新建文件或整文件覆盖，自动创建父目录 |
| `edit_file` | `path`, `old_string`, `new_string` | 精确局部修改，要求 old_string 精确匹配且唯一 |
| `glob` | `pattern`, `root?` | 递归搜索匹配文件名的文件路径，cap 200 条 |
| `grep` | `pattern`, `path?`, `root?` | 在文件中搜索匹配正则的行，返回 path:lineno:line，cap 100 条 |
| `bash` | `command` | 执行 shell 命令，30s 超时，捕获 stdout+stderr+exit code |

### v2 功能

| 功能 | 实现 |
|------|------|
| **Grep/Glob 搜索工具** | 纯 Python 实现（pathlib + fnmatch + re），自动过滤 .gitignore |
| **错误恢复** | `complete_with_retry()` 指数退避重试 3 次，区分可重试（RateLimit/Connection/Timeout/InternalError）和不可重试（BadRequest/Auth）错误 |
| **流式输出** | `stream_complete()` chunk 重组，content 实时 print(flush=True)，tool_calls 累积组装 |
| **权限审批** | `--approval` 模式下 bash 执行前弹 `input("执行此命令? [y/N]")`，拒绝则 observation 回灌 LLM 自纠 |
| **.gitignore 感知** | `_load_gitignore()` + `_is_ignored()`，glob/grep 内部自动过滤被忽略文件 |
| **token 预算控制** | `_truncate_for_llm()` 截断工具结果回灌 LLM（默认 6000 字符），双语标记 |
| **text-mode** | `--text-mode` prompt-based 工具调用，兼容不支持 function calling 的模型 |

### 终端输出示例

```
💭 我来创建一个 hello.py 文件。
🔧 write_file("hello.py", <20 字符>)
   → 成功写入 20 字节到 hello.py

🔧 bash("python hello.py")
   → hello world
[exit code: 0]

✅ 已完成。创建了 hello.py，运行后输出 hello world，验证通过。
```

---

## 设计决策

| 决策点 | v1 选择 | v2 演进 | v3+ 计划 |
|--------|---------|---------|---------|
| 语言 | Python | — | 可迁移 TS/Rust |
| 工具集 | read+write+edit+bash | + glob+grep | — |
| 安全 | 全自动+日志 | + 权限审批（--approval） | — |
| 上下文 | 全量历史 | + token 预算截断 | 加压缩+子 agent |
| 输出 | collect 后 print | + 流式输出（--stream） | — |
| 循环终止 | LLM 不调工具=结束 | + max_iter 兜底 | — |
| LLM 兼容 | OpenAI function calling | + text-mode（--text-mode） | — |
| 错误处理 | 无 | + 指数退避重试 | — |

---

## 演进路线

```
v1 (MVP, ~378行)            v2 (可用, ~895行)          v3 (产品级)
─────────────               ─────────────              ──────────
agent 循环                 + Grep/Glob(搜索)           + 子 agent(上下文隔离)
4 个核心工具               + 流式输出                   + 上下文压缩
  (read/write/edit/bash)  + 权限审批                    + plan mode
OpenAI API               + .gitignore 感知             + MCP 协议
CLI                      + 错误恢复                    + 记忆系统
                         + token 预算控制               + Skills/插件
                         + text-mode 适配
                         v0.2.0
```

**v1 验收标准**：能在真实 repo 里完成"读取文件→理解→修改→跑测试→报告结果"闭环。✅ 已通过

**v2 验收标准**：在真实 LLM 环境下使用 `--stream --approval` 或 `--text-mode` 完成搜索+修改+验证闭环。✅ 已通过（Ollama + deepseek-r1:8b）

---

## 测试

### 单元测试

```bash
cd .../AIAgent/mycodingagent/nautilus
PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
```

| 测试模块 | 测试数 | 覆盖范围 |
|---------|--------|---------|
| `test_tools.py` | 49 | read/write/edit/glob/grep/bash 正常+异常路径、execute_tool 路由、TOOL_SCHEMAS(6)、.gitignore 过滤 |
| `test_agent.py` | 28 | _truncate/_estimate_tokens/_truncate_for_llm/_print_tool_call + mock ReAct 闭环/max_iter/错误自纠/token 预算/审批 |
| `test_llm.py` | 18 | create_client 工厂 + complete_with_retry 重试 + stream_complete 流式 |
| `test_cli.py` | 22 | --help/stdin/参数解析 + --stream/--approval/--max-tool-output/--text-mode |
| **合计** | **125** | **全部通过** |

### E2E 端到端测试

**text-mode（deepseek-r1:8b）**：

| 场景 | 命令 | 结果 |
|------|------|------|
| 基础任务 | `nautilus --text-mode "创建 hello.py，运行它"` | ✅ write_file → bash → hello world |
| Grep/Glob | `nautilus --text-mode "用 glob 搜索 .py，用 grep 搜索 divide"` | ✅ glob 找到 3 文件 → grep 定位 calc.py:4 |
| 流式输出 | `nautilus --text-mode --stream "read hello.py"` | ✅ token 实时打印 → read_file → 回答 |
| 权限审批（同意） | `echo "y" \| nautilus --text-mode --approval "echo ok"` | ✅ 弹 prompt → y → bash 执行成功 |
| 权限审批（拒绝） | `echo "n" \| nautilus --text-mode --approval "echo no"` | ✅ bash 未执行 → 直接文字回答 |

**native function calling（qwen2.5:7b）**：

| 场景 | 命令 | 结果 |
|------|------|------|
| 基础任务 | `nautilus "创建 hello.py，运行它"` | ✅ write_file → bash（python3 失败自纠）→ hello world |
| Grep/Glob | `nautilus "用 glob 搜索 .py，用 grep 搜索 divide"` | ✅ glob 找到 3 文件 → grep 定位 calc.py:4+6 |
| 流式输出 | `nautilus --stream "read hello.py"` | ✅ read_file → 流式打印 → 正确回答 |
| 权限审批（同意） | `echo "y" \| nautilus --approval "echo ok"` | ✅ 弹 prompt → y → bash 执行成功 |
| 权限审批（拒绝） | `echo "n" \| nautilus --approval "echo no"` | ✅ bash 未执行 → observation 回灌 |
| 流式+审批 | `echo "y" \| nautilus --stream --approval "echo combined"` | ✅ 组合正常工作 |

---

## 设计文档

| 文档 | 内容 |
|------|------|
| `coding-agent-第一性原理设计方案.md` | 第一性原理分解、标杆对比、三对设计张力、v1/v2 架构、演进路线 |
| `nautilus-v1-实现计划.md` | v1 7 文件分解、工具 schema、CLI 设计 |
| `nautilus-v1-实现总结.md` | v1 实际行数、验证结果、使用方式 |
| `nautilus-v1-验证报告.md` | v1 77 个测试用例验证报告 |
| `nautilus-v2-实现计划.md` | v2 5 功能实现细节、文件清单、CLI 参数 |
| `nautilus-v2-实现总结.md` | v2 实际行数、6 功能验证结果、E2E 测试结果、使用方式 |
| `nautilus-v2-验证报告.md` | v2 125 个测试 + 5 个 E2E 场景验证报告 |
| `nautilus-系统目标.md` | 企业架构（TOGAF 四域）+ 约束理论（Goldratt ToC/DBR）双视角分析 |
| `nautilus-结果质量评估标准.md` | Hermes 评估器三维模型适配：正确性/过程精准度/简洁度 |
| `nautilus名称含义.md` | 鹦鹉螺对数螺旋与 ReAct 循环的隐喻映射 |

---

## 已知限制

1. **Windows GBK 编码**：`agent.py` 使用 emoji（🔧✅⚠️💭🔄），Windows 默认 GBK 编码会崩溃。规避：`PYTHONIOENCODING=utf-8`。
2. **text-mode 精度**：不支持 function calling 的模型依赖 prompt-based 工具调用，模型可能不严格遵循 ` ```tool_call {json} ` ` 格式，需要更强的系统提示词引导。
3. **无上下文压缩**：全量历史回灌 LLM（有 token 预算截断兜底），长任务仍可能撑爆 context window。
4. **bash 无安全过滤**：`shell=True` 无命令过滤（有 `--approval` 审批门可选）。

---

## 设计哲学

> **agent 的本质不在单个组件的强度，而在组合方式。**

Claude Code 的 51 万行是在这 895 行之上叠加多 agent / 上下文压缩 / MCP 协议 / 记忆系统 / Skills 插件的工程化。Nautilus 用最简组合验证：**LLM + 6 个工具 + 一个 while 循环 = 可用的 coding agent**。

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
