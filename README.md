# Nautilus 🐚

> **鹦鹉螺：螺旋逼近答案的 coding agent**
>
> Nautilus 是一个从第一性原理出发、用最小代码量表达 coding agent 本质的 Python 项目。它不是产品级工具，而是一个**学习用 MVP**——用 ~378 行代码验证"LLM + 4 个工具 + 一个 while 循环"就是 agent 的不可约核心。

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
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://xxx   # 可选，OpenAI 兼容 API
```

> **Windows 用户**：需额外设置 `PYTHONIOENCODING=utf-8`，因为 `agent.py` 使用了 emoji 字符。

### 运行

```bash
nautilus "创建一个 hello.py，运行它，确认输出 hello world"

# 指定模型和迭代上限
nautilus --model qwen-plus --base-url https://xxx "修复 bug"
nautilus --max-iter 30 "重构 utils.py"

# 支持管道输入
echo "解释这个项目" | nautilus
```

### 验证安装

```bash
nautilus --help                    # 查看 CLI 帮助
python -m pytest tests/ -v -o "addopts="   # 运行 91 个单元测试
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

---

## 项目结构

```
nautilus/
├── pyproject.toml              # 16 行 — 项目元数据 + openai 依赖 + CLI 入口
├── nautilus/                   # 源码包
│   ├── __init__.py             #  1 行 — 版本号
│   ├── __main__.py             # 68 行 — CLI 入口（argparse）
│   ├── agent.py                # 81 行 — 核心 ReAct 循环
│   ├── llm.py                  # 19 行 — OpenAI 兼容 API 客户端工厂
│   ├── prompts.py              # 20 行 — 系统提示词（6 条行为准则）
│   └── tools.py                # 189 行 — 4 个工具 + execute_tool 路由
├── tests/                      # 单元测试
│   ├── __init__.py
│   ├── test_tools.py           # 36 tests — 工具函数 + 路由 + schema
│   ├── test_agent.py           # 15 tests — 辅助函数 + mock ReAct 循环
│   ├── test_llm.py             # 10 tests — create_client 工厂
│   └── test_cli.py             # 16 tests — CLI 入口
└── README.md
```

**总计：378 行 Python 源码 + 91 个测试用例（全部通过）。**

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
    response = client.chat.completions.create(model, messages, tools=TOOL_SCHEMAS)
    message = response.choices[0].message
    if not message.tool_calls:
        print(message.content)          # 没有工具调用 = 最终回答
        return
    messages.append(message)             # 思考回灌
    for call in message.tool_calls:
        result = execute_tool(call)      # 行动
        messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
```

### 四个工具

| 工具 | 参数 | 用途 |
|------|------|------|
| `read_file` | `path` | 读取 utf-8 文本文件 |
| `write_file` | `path`, `content` | 新建文件或整文件覆盖，自动创建父目录 |
| `edit_file` | `path`, `old_string`, `new_string` | 精确局部修改，要求 old_string 精确匹配且唯一 |
| `bash` | `command` | 执行 shell 命令，30s 超时，捕获 stdout+stderr+exit code |

### 终端输出示例

```
🔧 write_file("hello.py", <20 字符>)
   → 成功写入 20 字节到 hello.py

🔧 bash("python hello.py")
   → hello world
[exit code: 0]

✅ 已完成。创建了 hello.py，运行后输出 hello world，验证通过。
```

---

## 设计决策

| 决策点 | v1 选择 | 理由 | v2+ 演进 |
|--------|---------|------|---------|
| 语言 | Python | 最少代码表达循环本质 | 可迁移 TS/Rust |
| 工具集 | read+write+edit+bash | 覆盖感知+行动+精确修改最小集 | 拆出 Grep/Glob |
| 安全 | 全自动+日志 | 学习阶段不需要审批 | 加 permission prompt |
| 上下文 | 全量历史 | 最简实现 | 加压缩+子 agent |
| 输出 | collect 后 print | 先跑通 | 加 streaming |
| 循环终止 | LLM 不调工具 = 结束 | OpenAI tool calling 原生 | 加 max_iter 兜底 |
| 迭代上限 | 20 次 | 防死循环 | 可配置 |

---

## 演进路线

```
v1 (MVP, ~378行)            v2 (可用)                 v3 (产品级)
─────────────               ─────────                ──────────
agent 循环                 + Grep/Glob(搜索)         + 子 agent(上下文隔离)
4 个核心工具               + 流式输出                + 上下文压缩
  (read/write/edit/bash)  + 权限审批                 + plan mode
OpenAI API               + .gitignore 感知          + MCP 协议
CLI                      + 错误恢复                 + 记忆系统
                                                    + Skills/插件
```

---

## 测试

```bash
cd .../AIAgent/mycodingagent/nautilus
PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
```

| 测试模块 | 测试数 | 覆盖范围 |
|---------|--------|---------|
| `test_tools.py` | 36 | read/write/edit/bash 正常+异常路径、execute_tool 路由、TOOL_SCHEMAS 结构 |
| `test_agent.py` | 15 | `_truncate`/`_print_tool_call` + mock LLM 的 ReAct 闭环/max_iter 截断/错误自纠 |
| `test_llm.py` | 10 | create_client 无 key/显式参数/环境变量/优先级链 |
| `test_cli.py` | 16 | --help/无 prompt/stdin 管道/参数解析/默认值 |
| **合计** | **91** | **全部通过** |

---

## 设计文档

| 文档 | 内容 |
|------|------|
| `coding-agent-第一性原理设计方案.md` | 第一性原理分解、标杆对比、三对设计张力、v1 架构、演进路线 |
| `nautilus-v1-实现计划.md` | 7 文件分解、工具 schema、CLI 设计、终端输出格式 |
| `nautilus-v1-实现总结.md` | 实际行数、验证结果、使用方式 |
| `nautilus-系统目标.md` | 企业架构（TOGAF 四域）+ 约束理论（Goldratt ToC/DBR）双视角分析 |
| `nautilus-结果质量评估标准.md` | Hermes 评估器三维模型适配：正确性/过程精准度/简洁度 |
| `nautilus-v1-验证报告.md` | 91 个测试用例验证报告，含已知问题和未验证项 |
| `nautilus名称含义.md` | 鹦鹉螺对数螺旋与 ReAct 循环的隐喻映射 |

---

## 已知限制

1. **Windows GBK 编码**：`agent.py` 使用 emoji（🔧✅⚠️），Windows 默认 GBK 编码会崩溃。规避：`PYTHONIOENCODING=utf-8`。
2. **无安全审批**：v1 全自动执行，无权限确认。避免在不重要的目录运行。
3. **无上下文压缩**：全量历史回灌 LLM，长任务会撑爆 context window。
4. **未验证真实 LLM API**：UT 使用 mock LLM 验证逻辑正确性，尚未用真实 API key 测试端到端。

---

## 设计哲学

> **agent 的本质不在单个组件的强度，而在组合方式。**

Claude Code 的 51 万行是在这 378 行之上叠加安全/UX/扩展/多 agent 的工程化。Nautilus 用最简组合验证：**LLM + 4 个工具 + 一个 while 循环 = coding agent 的不可约核心**。

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
