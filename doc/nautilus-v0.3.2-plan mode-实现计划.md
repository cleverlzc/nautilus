# Nautilus v0.3.2 plan mode — 实现计划

## Context

v0.3.1 已完成子 agent（上下文隔离）（1116 行，155 tests + 3 E2E 场景）。`nautilus-v3-特性优先级排序.md` 将 plan mode 列为 P2 特性，独立于上下文压缩/子 agent，不依赖其他特性。

当前代码基线（v0.3.1）：1116 行 Python 源码 + 155 tests。

v0.3.2 的目标：**在 `run_agent()` 中增加 plan→execute 两阶段模式**——用户提交任务后，agent 先用 LLM 生成执行计划（文本，不调工具），用户确认后进入正常 ReAct 循环执行。减少 LLM 试错圈数（ToC：提升有效产出 T）。

## 项目位置

```
...\AIAgent\mycodingagent\nautilus\
```

## 问题分析

当前 agent 收到任务后直接进入 ReAct 循环——LLM 边想边做，可能在第 3 步才发现第 1 步方向错了，浪费迭代圈数。对于复杂任务（如"重构整个模块"），agent 可能需要 10+ 轮试错才能收敛。

plan mode 解决方案：先用 1 次 LLM 调用生成结构化执行计划（不调工具），用户确认后，将计划注入 messages 作为 assistant 上下文，agent 按计划执行——减少盲目试错。

| 维度 | 无 plan mode | 有 plan mode |
|------|-------------|-------------|
| 执行前规划 | ❌ 边想边做 | ✅ 先规划再执行 |
| 用户确认 | ❌ 无法干预方向 | ✅ 计划阶段可拒绝 |
| 试错圈数 | 高（方向错误需回溯） | 低（计划确认后按步骤执行） |

## 文件清单（4 个文件）

| 文件 | 职责 | 基线行数 | 预估行数 | 变化 |
|------|------|---------|---------|------|
| `nautilus/agent.py` | ReAct 循环 + 压缩 + 子 agent + **plan mode** | 383 | ~420 | +`plan_mode` 参数 + Phase 1 计划生成 + Phase 2 计划注入 messages |
| `nautilus/prompts.py` | 系统提示词 | 99 | ~115 | +`SYSTEM_PROMPT_PLAN` 提示词 |
| `nautilus/__main__.py` | CLI 入口 | 109 | ~115 | +`--plan` CLI 参数 |
| `tests/test_agent.py` | agent 测试 | 1025 | ~1100 | +`TestPlanMode`(3) |

## 各文件实现细节

### 1. `nautilus/agent.py` — 核心修改

**修改 `run_agent()` 签名**：

```python
def run_agent(
    prompt: str,
    model: str = "gpt-4",
    api_key: str | None = None,
    base_url: str | None = None,
    max_iter: int = 20,
    max_tool_output_chars: int = 6000,
    stream: bool = False,
    approval: bool = False,
    text_mode: bool = False,
    max_context_tokens: int = 32000,
    plan_mode: bool = False,  # NEW
) -> None:
```

**修改 `run_agent()` 函数体**：

在 `client = create_client(...)` 之后、`messages = [...]` 之前，新增 plan mode 分支：

```python
    client = create_client(api_key=api_key, base_url=base_url)
    system_prompt = SYSTEM_PROMPT_TEXT_MODE if text_mode else SYSTEM_PROMPT

    # Plan mode: Phase 1 — 生成执行计划
    if plan_mode:
        plan_response = complete_with_retry(
            client,
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_PLAN},
                {"role": "user", "content": prompt},
            ],
        )
        plan = plan_response.choices[0].message.content or ""
        print(f"📋 执行计划:\n{plan}\n")
        user_input = input("是否执行此计划? [y/N]: ").strip().lower()
        if user_input not in ("y", "yes"):
            print("用户取消了执行。")
            return
        # Phase 2: 计划已确认，将计划注入 messages 作为上下文
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": plan},
            {"role": "user", "content": "请按计划执行。"},
        ]
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

    for i in range(max_iter):
        # ... 后续 ReAct 循环逻辑不变 ...
```

**设计要点**：

- **Phase 1 不调工具**：计划生成阶段用 `SYSTEM_PROMPT_PLAN` 提示词，不传 `tools=TOOL_SCHEMAS`，LLM 只输出文本计划
- **Phase 2 计划注入**：将计划作为 `assistant` 消息注入 messages，再加一条 `user` 消息"请按计划执行"，让 LLM 在后续循环中参考计划
- **用户确认**：`input("是否执行此计划? [y/N]: ")`，拒绝则直接 return，不进入执行循环
- **不与 stream 冲突**：plan mode 的 Phase 1 不使用 stream（计划生成是单次调用），Phase 2 正常 ReAct 循环可叠加 `--stream`

### 2. `nautilus/prompts.py` — 新增 SYSTEM_PROMPT_PLAN

新增 `SYSTEM_PROMPT_PLAN` 提示词（~15 行）：

```python
SYSTEM_PROMPT_PLAN = """你是一个 coding agent 的规划模块。你的任务是分析用户的需求，生成一个清晰的执行计划。

要求：
1. 分析任务：理解用户需要做什么，拆解为具体步骤。
2. 列出步骤：用编号列表列出每个执行步骤。
3. 指明工具：每个步骤说明需要用哪个工具（read_file/write_file/edit_file/glob/grep/bash/delegate_task）。
4. 预估风险：指出可能的坑点或需要注意的地方。
5. 不要调用工具：只输出计划文本，不要尝试执行任何操作。

格式示例：
1. [glob] 搜索所有 .py 文件，了解项目结构
2. [read_file] 读取核心文件，理解现有逻辑
3. [edit_file] 修改目标文件，实现需求
4. [bash] 运行测试验证修改正确
"""
```

### 3. `nautilus/__main__.py` — 新增 --plan CLI 参数

```python
parser.add_argument(
    "--plan",
    action="store_true",
    default=False,
    help="启用 plan mode：先生成执行计划，用户确认后再执行。",
)
```

传到 `run_agent`：

```python
run_agent(
    ...
    plan_mode=args.plan,  # NEW
)
```

### 4. `tests/test_agent.py` — 新增测试

**新增 `TestPlanMode` 类**（3 tests）：

| 测试 | 覆盖场景 |
|------|---------|
| `test_plan_mode_accepted` | mock LLM Phase 1 返回计划 + 用户输入 "y" → Phase 2 进入 ReAct 循环 → 最终回答 |
| `test_plan_mode_rejected` | mock LLM Phase 1 返回计划 + 用户输入 "n" → 打印"用户取消了执行" → return，不进入循环 |
| `test_plan_mode_disabled_by_default` | `plan_mode=False`（默认）→ 不触发计划生成，直接进入 ReAct 循环（用 AssertionError 验证 input 未被调用） |

**mock 策略**：

Phase 1（计划生成）和 Phase 2（ReAct 循环）的 LLM 调用共用同一个 `mock_create_fn`，通过 messages 内容区分——Phase 1 的 system 消息是 `SYSTEM_PROMPT_PLAN`（含"规划模块"），Phase 2 的 system 消息是 `SYSTEM_PROMPT`（含"coding agent"）。

```python
def mock_create_fn(**kwargs):
    msgs = kwargs.get("messages", [])
    is_plan = len(msgs) > 0 and "规划模块" in (
        msgs[0].get("content", "") if isinstance(msgs[0], dict)
        else getattr(msgs[0], "content", "")
    )
    if is_plan:
        return plan_response  # Phase 1: 返回计划
    else:
        return react_response  # Phase 2: ReAct 循环
```

**CLI 测试**：

| 测试 | 覆盖场景 |
|------|---------|
| `test_plan_flag` | `--plan` 传参 → `plan_mode=True` |
| `test_plan_default_false` | 不传参 → `plan_mode=False` |

## 版本号更新

| 文件 | 变更 |
|------|------|
| `nautilus/__init__.py` | `0.3.1` → `0.3.2` |
| `pyproject.toml` | `version = "0.3.1"` → `version = "0.3.2"` |

## CLI 参数

v0.3.2 新增 1 个参数（共 11 个）：

```
$ nautilus --plan "重构整个模块"                      # NEW
$ nautilus --plan --approval "复杂修改任务"            # plan + approval 组合
$ nautilus --plan --stream "重构模块，实时查看"         # plan + stream 组合
```

参数（v0.3.2 新增 1 个，共 11 个）：
- `prompt` / `--model` / `--api-key` / `--base-url` / `--max-iter` / `--max-tool-output` / `--max-context-tokens` / `--stream` / `--approval` / `--text-mode`
- `--plan`（默认 False）**← v0.3.2 新增**

## 终端输出格式

```
📋 执行计划:
1. [glob] 搜索所有 .py 文件，了解项目结构
2. [read_file] 读取 calc.py，理解现有函数
3. [edit_file] 在 calc.py 末尾添加 sqrt 函数
4. [bash] 运行 python main.py 验证修改正确
是否执行此计划? [y/N]: y

💭 好的，按计划执行。
🔧 glob("*.py")
   → calc.py, main.py, utils.py
🔧 read_file("calc.py")
   → def add(a, b): ...
🔧 edit_file("calc.py", old: <20 字符>, new: <35 字符>)
   → 成功修改 calc.py
🔧 bash("python main.py")
   → [LOG] Calculator started
Result: 3
...
[exit code: 0]

✅ 已完成。按计划添加了 sqrt 函数，测试全部通过。
```

## 不修改的文件

- `nautilus/llm.py`：不涉及（plan mode 复用已有 `complete_with_retry`）
- `nautilus/tools.py`：不涉及（plan mode 不新增工具）
- `pyproject.toml` 依赖列表：无新依赖

## 验证方式

1. `pip install -e .` 安装
2. 运行单元测试：
   ```bash
   PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
   ```
3. 预期结果：155 + ~5 新增 = 160 tests 全部通过（test_agent.py +3, test_cli.py +2）
4. E2E 测试（Ollama + qwen2.5:7b）：
   ```bash
   OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
   nautilus --model "qwen2.5:7b" --max-iter 10 --plan \
   "分析这个项目的所有文件，然后添加一个 sqrt 函数到 calc.py"
   ```
5. 验证：Phase 1 生成结构化计划 → 用户确认 → Phase 2 按计划执行
