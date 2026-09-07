# Coding Agent 第一性原理设计方案

> 设计哲学参考：Claude Code、OpenAI Codex CLI、Aider、OpenHands 等开源 coding agent
> 日期：2026-08-21

---

## 一、标杆项目实现语言对比

| 项目 | 语言 | 运行时 | 关键技术栈 |
|------|------|--------|-----------|
| **Claude Code** | TypeScript | Bun | React+Ink(TUI)、Commander、Zod、ripgrep、MCP SDK |
| **Codex CLI** | Rust (重写) | 原生二进制 | Rust workspace ~120 crate，npm 包只是启动器 |
| **Aider** | Python | CPython | 纯终端、git-centric |
| **OpenHands** | Python | CPython+Docker | 事件驱动、Docker 沙箱 |

两条主流路线：
- **TypeScript/Bun** — Claude Code 路线，TUI 体验最好，生态成熟
- **Rust** — Codex 重写路线，性能/安全最强，但开发成本高
- **Python** — Aider/OpenHands 路线，**最少代码量表达 agent 循环，最适合学习和快速验证**

**v1 选择 Python。** 理由：agent 的本质是循环，Python 能用最少代码把这个本质写清楚（Aider 全量也才几千行），验证设计后再迁移到 TypeScript/Rust。

---

## 二、第一性原理分解：coding agent 的不可约本质

### 2.1 为什么不能只是一个 chatbot？

一个只输出文本的 LLM，本质是 **纯认知体**——它能"想"，但不能"做"。你问它"帮我修这个 bug"，它只能告诉你"应该这样改"，但**手指碰不到文件系统**。

> coding agent = 让 LLM 长出"手"的工程。

### 2.2 五个不可约组件

从第一性原理出发，coding agent 必须有且仅有这五个本质组件，缺一个就不成立：

```
┌──────────────────────────────────────────┐
│  ① LLM (认知)   ② Tools (行动)  ③ Loop (自主)  │
│       ↑              ↓              ↻      │
│  ④ Context (记忆) ←──────────────────┘     │
│       ↑                                    │
│  ⑤ Interface (I/O)  ← user prompt         │
└──────────────────────────────────────────┘
```

**每个组件"为什么必须存在"的推导：**

| 组件 | 第一性问题 | 推导 |
|------|-----------|------|
| ① LLM | 代码任务需要理解意图+推理，规则引擎做不到 | → 必须有认知引擎 |
| ② Tools | LLM 输出只是 token，无法直接读写文件/跑命令 | → 必须有"执行器"翻译决策为现实效果 |
| ③ Loop | 单次 LLM→tool→done 是函数不是 agent | → 必须有"观察→思考→行动→观察"的循环才有自主性 |
| ④ Context | LLM 无状态，每次调用是"失忆"的 | → 必须显式维护历史才能有连续性 |
| ⑤ Interface | 没有输入通道，agent 收不到任务 | → 最少需要 CLI |

**关键洞察**：这五个组件的**组合方式**定义了 agent，而不是单个组件的强度。Claude Code 的 43 个工具 vs Aider 的 20 个，本质区别不在数量，而在**循环的控制策略**和**上下文管理策略**。

### 2.3 ReAct 循环——agent 的原子

所有 coding agent 的核心都可以归约到一个循环：

```python
while not done:
    decision = LLM(context)          # 思考：下一步做什么
    if decision is "final_answer":
        return decision              # 终止：输出给用户
    observation = execute(decision) # 行动：调用工具
    context.append(observation)     # 观察：结果回灌
```

这就是 **ReAct (Reasoning + Acting)** 模式。Claude Code、Codex、Aider 的核心循环都是它的变体。区别只在：
- `execute` 怎么做安全控制（权限/沙箱）
- `context` 怎么管理膨胀（压缩/子 agent 隔离）
- `done` 怎么判定（LLM 自己说了算 vs 外部约束）

---

## 三、设计哲学对比（结构化发散）

### 3.1 四个标杆的设计决策对比

| 设计维度 | Claude Code | Codex CLI | Aider | OpenHands |
|---------|-------------|-----------|-------|-----------|
| **工具粒度** | 精细策划 (Read/Edit/Grep/Glob 各自独立) | 沙箱优先，bash 为主 | git-centric (git diff 即审查) | Docker 沙箱内自由 |
| **安全模型** | 权限模式 (suggest/auto-edit/full-auto) | 3 级 approval mode | git diff 审查兜底 | Docker 容器隔离 |
| **上下文策略** | 子 agent 隔离 + 自动压缩 | token 计数 | repo map (文件树+符号) | file-to-line 映射 |
| **多 agent** | Swarms + Coordinator | 有限 | 无 | Planner + Agent |
| **扩展机制** | MCP + Skills | Plugins | - | Plugins |
| **agent 循环** | AsyncGenerator | Rust async | 同步循环 | 事件驱动 |

### 3.2 从对比中提炼的设计张力

发散思考后，看到**三对核心张力**，v1 必须在每对上做选择：

**张力 1：工具粒度 vs 简单性**
- 精细工具（Claude Code 的 Read/Edit/Grep 分离）→ 控制强、UX 好、可审计
- 粗粒度（一个 bash 搞定一切）→ 简单、灵活、但危险
- **v1 选择**：粗粒度起步（read + write + edit + bash 四件套），v2 再拆出搜索类工具

**张力 2：安全 vs 流畅**
- 严格审批（每步问用户）→ 安全但慢
- 全自动 → 快但可能闯祸
- **v1 选择**：先全自动打印日志（学习用），v2 加 permission prompt

**张力 3：上下文丰富 vs token 成本**
- 全量历史灌入 → 简单但很快爆 context window
- 压缩/子 agent → 省 token 但复杂
- **v1 选择**：全量历史（最简），设一个硬上限截断

### 3.3 brainstorming：v1 可以砍掉什么？

**可以砍（v1 不需要）：**
- 子 agent / 多 agent
- plan mode
- MCP 协议
- 流式输出（先 collect 再 print）
- 权限系统
- 上下文压缩
- 记忆系统
- TUI（用普通 print）

**不能砍（砍了就不是 agent）：**
- 系统提示词（定义行为）
- 工具循环（agent 本质）
- 4 个核心工具
- 对话历史

---

## 四、v1 架构方案

### 4.1 架构图

```
┌───────────────────────────────────────┐
│  __main__.py (CLI 入口)               │
│  $ python -m nautilus "修复 bug"      │
└───────────────┬───────────────────────┘
                │
                ▼
┌───────────────────────────────────────┐
│  agent.py  ← THE CORE (agent 循环)    │
│                                       │
│  messages = [system, user_prompt]     │
│  while True:                          │
│      resp = llm.chat(messages, tools) │──┐
│      if no tool_calls:                │  │
│          print(resp); break           │  │
│      for call in resp.tool_calls:     │  │
│          result = router.run(call)     │  │
│          messages.append(result)       │  │
└───────────────┬───────────────────────┘  │
                │                          │
        ┌───────┴───────────────┐          │
        ▼       ▼       ▼       ▼          │
   ┌──────┐┌──────┐┌──────┐┌──────┐        │
   │ read ││ write││ edit ││ bash │←tools │
   │_file ││_file ││_file ││      │.py    │
   └──────┘└──────┘└──────┘└──────┘        │
        │       │       │       │          │
        └───────┴───────┴───────┘          │
                │                          │
                ▼                          │
┌───────────────────────────────────────┐  │
│  llm.py (OpenAI 兼容 API 封装)         │◀─┘
│  - chat(messages, tools) → response   │
│  - tool_calling 协议处理               │
└───────────────────────────────────────┘
```

### 4.2 文件结构

```
nautilus/
├── pyproject.toml     # 依赖：openai
├── nautilus/
│   ├── __init__.py
│   ├── __main__.py    # CLI 入口，解析参数
│   ├── agent.py       # agent 循环（核心，~40 行）
│   ├── llm.py         # OpenAI API 封装
│   ├── tools.py       # 工具定义 + 执行路由
│   └── prompts.py     # 系统提示词
└── README.md
```

> **注**：项目目录为 `nautilus/`，内部包名和 CLI 命令均为 `nautilus`。

### 4.3 核心代码骨架

**agent.py — 整个 agent 的心脏，~40 行：**

```python
def run_agent(user_prompt: str, max_iter: int = 20):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    for i in range(max_iter):
        resp = llm.chat(messages, tools=TOOL_SCHEMA)
        messages.append(resp.message)
        if not resp.tool_calls:
            print(resp.content)          # 没有工具调用 = 最终回答
            return
        for call in resp.tool_calls:
            result = execute_tool(call)  # 路由到 read/write/edit/bash
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })
    print("达到最大迭代次数")
```

**tools.py — 四个工具够 v1 跑起来：**

```python
TOOLS = [
    {"type": "function", "function": {
        "name": "read_file",
        "parameters": {"path": "string"},
        "description": "读取文件内容",
    }},
    {"type": "function", "function": {
        "name": "write_file",
        "parameters": {"path": "string", "content": "string"},
        "description": "写入文件（新建或整文件覆盖）",
    }},
    {"type": "function", "function": {
        "name": "edit_file",
        "parameters": {"path": "string", "old_string": "string", "new_string": "string"},
        "description": "精确替换文件中的指定文本（局部修改，避免整文件重写）",
    }},
    {"type": "function", "function": {
        "name": "bash",
        "parameters": {"command": "string"},
        "description": "执行 shell 命令",
    }},
]
```

> 这就是整个 agent 的本质。**~300 行可运行**（实际 378 行）。Claude Code 的 51 万行是在这 378 行之上叠加安全/UX/扩展/多 agent 的工程化。

### 4.4 v1 的设计决策清单

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

## 五、演进路线

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

**v1 的验收标准**：能在一个真实 repo 里完成"读取文件→理解→修改→跑测试→报告结果"这个闭环。

---

## 六、下一步

方案已就绪，可以：

1. **直接实现 v1** — 把上面的骨架变成可运行的 Python 代码（实际 378 行）
2. **先细化某个组件设计** — 比如系统提示词怎么写、工具 schema 怎么设计、错误处理策略
3. **调整方案** — 语言/工具集/安全模型有不同想法

---

## 参考资料

- [Claude Code 源码泄露分析](https://news.qq.com/rain/a/20260331A07A8900)
- [Codex CLI Rust 重写 - InfoQ](https://www.infoq.com/news/2025/06/codex-cli-rust-native-rewrite/)
- [工业级 AI Coding Agent 源码架构解析](https://www.163.com/dy/article/KQ3FEJFE0518R7MO.html)
- [nova-code: 渐进式 Code Agent CLI 学习项目](https://github.com/nova-agents-ai/nova-code)
- [Codex CLI 源码分析](https://github.com/xiaonancs/codex-source-analysis)
