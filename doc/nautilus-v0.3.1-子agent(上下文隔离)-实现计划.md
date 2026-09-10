# Nautilus v0.3.1 子 agent（上下文隔离）— 实现计划

## Context

v0.3.0 已完成上下文压缩（987 行，146 tests + 4 E2E 场景）。`nautilus-v3-特性优先级排序.md` 将子 agent 列为 P1 第二特性，依赖上下文压缩。

当前代码基线（v0.3.0）：987 行 Python 源码 + 146 tests。

v0.3.1 的目标：**在主 agent 的 ReAct 循环中增加子 agent 委派能力**——主 agent 通过 `delegate_task` 工具将独立子任务委派给子 agent 执行，子 agent 使用独立的 messages 列表完成 ReAct 循环后只返回最终结果字符串给主 agent，不污染主循环上下文。这是上下文压缩的延伸——压缩是"丢弃旧消息"，子 agent 是"把长子任务的上下文隔离到独立循环"（ToC：降低主循环库存 I，提升有效产出 T）。

## 项目位置

```
...\AIAgent\mycodingagent\nautilus\
```

## 问题分析

v0.3.0 的 `_compress_history` 通过丢弃旧消息控制上下文——但复杂子任务（如"搜索所有包含 X 的文件并读取内容"）本身可能需要 5-10 轮迭代，全部在主循环执行会迅速膨胀 messages。即使压缩，主 agent 也丢失了子任务的中间结果。

子 agent 解决方案：主 agent 只需 1 次工具调用（`delegate_task`），子任务的所有中间步骤在子 agent 的独立 messages 中完成，主 agent 只接收最终结果字符串——1 条消息而非 10+ 条。

| 维度 | 无子 agent | 有子 agent |
|------|-----------|-----------|
| 主循环 messages 增长 | 子任务每轮迭代 +2 条 | 子任务完成 +1 条（仅结果） |
| 上下文隔离 | ❌ 子任务中间步骤污染主循环 | ✅ 独立 messages 列表 |
| 压缩依赖 | 依赖压缩丢弃旧消息 | 子 agent 内部自行压缩 |

## 文件清单（4 个文件）

| 文件 | 职责 | 基线行数 | 预估行数 | 变化 |
|------|------|---------|---------|------|
| `nautilus/agent.py` | ReAct 循环 + 压缩 + **子 agent** | 295 | ~383 | +`run_subagent()` 函数 + `delegate_task` 处理分支 + `_print_tool_call` 新增 delegate_task 格式化 |
| `nautilus/tools.py` | 6 工具 + 路由 | 382 | ~399 | +`delegate_task` schema（6→7 工具） |
| `nautilus/prompts.py` | 系统提示词 | 75 | ~99 | +`delegate_task` 工具说明 + `SYSTEM_PROMPT_SUBAGENT` 子 agent 提示词 |
| `tests/test_agent.py` | agent 测试 | 769 | ~990 | +`TestRunSubagent` + `TestDelegateTask` |
| `tests/test_tools.py` | tools 测试 | 416 | ~446 | +`TestToolSchemas` 更新（schema count 6→7 + delegate_task params/required/description） |

## 各文件实现细节

### 1. `nautilus/agent.py` — 核心修改

**新增 `run_subagent()` 函数**（~55 行）：

子 agent 是 `run_agent()` 的简化版——独立 messages 列表、独立 ReAct 循环、只返回最终结果字符串（不打印 ✅，不接收用户输入）。子 agent 不支持 stream/approval/plan_mode（保持最小化），但复用 `_compress_history` 和 `execute_tool`。

```python
def run_subagent(
    prompt: str,
    client,
    model: str = "gpt-4",
    max_iter: int = 10,
    max_tool_output_chars: int = 6000,
    max_context_tokens: int = 32000,
    text_mode: bool = False,
) -> str:
    """Run a sub-agent with independent messages list. Returns final answer string.

    Sub-agent has its own ReAct loop, does not print ✅, does not accept user input.
    Uses _compress_history to control its own context budget.
    Does NOT support delegate_task (no recursive sub-agents).
    """
    system_prompt = SYSTEM_PROMPT_TEXT_MODE if text_mode else SYSTEM_PROMPT_SUBAGENT
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    for i in range(max_iter):
        _compress_history(messages, max_context_tokens)

        api_kwargs = {"model": model, "messages": messages}
        if not text_mode:
            api_kwargs["tools"] = TOOL_SCHEMAS

        response = complete_with_retry(client, **api_kwargs)
        message = response.choices[0].message

        if text_mode:
            tool_calls = _parse_tool_calls_from_text(message.content or "")
            message.tool_calls = tool_calls if tool_calls else None

        if not message.tool_calls:
            return message.content or ""

        if text_mode:
            messages.append({"role": "assistant", "content": message.content})
        else:
            messages.append(message)

        for call in message.tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": call.function.arguments}

            if call.function.name == "delegate_task":
                result = "错误：子 agent 不支持委派子任务（不允许递归）。"
            else:
                result = execute_tool(call)

            if text_mode:
                truncated = _truncate_for_llm(result, max_tool_output_chars)
                messages.append({"role": "user", "content": f"[工具结果] {truncated}"})
            else:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": _truncate_for_llm(result, max_tool_output_chars),
                    }
                )

    return "子 agent 达到最大迭代次数，未完成任务。"
```

**修改 `run_agent()` 循环内 `delegate_task` 处理**（~5 行）：

在 `for call in message.tool_calls:` 循环中，`delegate_task` 特殊处理——调用 `run_subagent()` 而非 `execute_tool()`：

```python
for call in message.tool_calls:
    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        args = {"_raw": call.function.arguments}

    _print_tool_call(call.function.name, args)

    # delegate_task: 委派子任务到独立子 agent
    if call.function.name == "delegate_task":
        sub_prompt = args.get("prompt", "")
        print(f"   📤 委派子 agent: {sub_prompt[:60]}...")
        result = run_subagent(
            prompt=sub_prompt,
            client=client,
            model=model,
            max_iter=10,
            max_tool_output_chars=max_tool_output_chars,
            max_context_tokens=max_context_tokens,
            text_mode=text_mode,
        )
        print(f"   📥 子 agent 完成: {result[:60]}...")
    elif approval and call.function.name == "bash":
        command = args.get("command", "")
        user_input = input(f"   执行此命令? [y/N]: ").strip().lower()
        if user_input not in ("y", "yes"):
            result = f"用户拒绝了该命令：{command}"
            print(f"   → {result}\n")
            if text_mode:
                messages.append({"role": "user", "content": f"[工具结果] {result}"})
            else:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": _truncate_for_llm(result, max_tool_output_chars),
                    }
                )
            continue

        result = execute_tool(call, allow_dangerous=True)
        print(f"   → {_truncate(result)}\n")
    else:
        result = execute_tool(call, allow_dangerous=approval)
        print(f"   → {_truncate(result)}\n")

    # ... 现有 messages.append 逻辑不变 ...
```

**修改 `_print_tool_call()` 新增 delegate_task 格式化**（~2 行）：

```python
elif name == "delegate_task":
    print(f'🔧 delegate_task("{args.get("prompt", "")[:60]}...")')
```

### 2. `nautilus/tools.py` — 新增 delegate_task schema

在 `TOOL_SCHEMAS` 列表中新增第 7 个工具 schema：

```python
{
    "type": "function",
    "function": {
        "name": "delegate_task",
        "description": "将子任务委派给独立子 agent 执行，隔离上下文。子 agent 有独立的对话历史，完成后只返回最终结果，不污染主循环。适用于需要多步工具调用的独立子任务。",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "子任务描述。应包含足够上下文让子 agent 独立完成。",
                }
            },
            "required": ["prompt"],
        },
    },
},
```

> **注**：`delegate_task` 不在 `execute_tool` 路由中——它需要 `client` 引用，属于 agent 层逻辑，在 `run_agent()` 循环中直接处理。

### 3. `nautilus/prompts.py` — 新增工具说明 + 子 agent 提示词

**修改 `SYSTEM_PROMPT` 可用工具列表**（+1 行）：

```
- delegate_task(prompt)：将子任务委派给独立子 agent 执行，隔离上下文。
```

**修改 `SYSTEM_PROMPT` 准则**（+1 行）：

```
7. 子任务隔离：复杂子任务（需多步工具调用）优先用 delegate_task 委派子 agent，避免污染主循环上下文。
```

**新增 `SYSTEM_PROMPT_SUBAGENT`**（~15 行）：

子 agent 的简化版系统提示词——只关注执行子任务并返回结果，不含"完成后给摘要"等准则，不含 `delegate_task` 工具（禁止递归）：

```python
SYSTEM_PROMPT_SUBAGENT = """你是一个子 agent，负责执行主 agent 委派的子任务。

行为准则：
1. 先读后改：修改任何文件前，先用 read_file 读它。
2. 最小修改：只改必要的部分。
3. 改完验证：如有测试命令，改完后跑一遍。
4. 完成后直接给出结果：用简洁的语言描述你做了什么、结果如何。

可用工具：
- read_file(path)：读取文件内容。
- write_file(path, content)：写入文件。
- edit_file(path, old_string, new_string)：精确替换文本。
- glob(pattern, root?)：搜索文件路径。
- grep(pattern, path?, root?)：搜索文件内容。
- bash(command)：执行 shell 命令。

搜索优先用 glob/grep 而非 bash。
任务完成后直接给出最终回答。
"""
```

**修改 `SYSTEM_PROMPT_TEXT_MODE`** 同步新增 `delegate_task` 说明 + 准则 7。

### 4. `tests/test_agent.py` — 新增测试

**新增 `TestRunSubagent` 类**（3 tests）：

| 测试 | 覆盖场景 |
|------|---------|
| `test_subagent_returns_final_answer` | mock LLM 2 轮（read_file→最终回答），验证 `run_subagent()` 返回最终回答字符串 |
| `test_subagent_independent_messages` | mock LLM 捕获 messages，验证子 agent messages 与主 agent messages 完全独立 |
| `test_subagent_max_iter` | mock LLM 持续调工具，验证 max_iter=3 后返回"子 agent 达到最大迭代次数" |

**新增 `TestDelegateTask` 类**（3 tests）：

| 测试 | 覆盖场景 |
|------|---------|
| `test_delegate_task_calls_subagent` | mock LLM 主循环调用 `delegate_task`，验证 `run_subagent()` 被调用 + 结果回灌主循环 messages |
| `test_delegate_task_does_not_pollute_main` | mock LLM 验证主 agent messages 不含子 agent 的中间工具调用步骤 |
| `test_subagent_rejects_recursive_delegate` | mock LLM 子 agent 调用 `delegate_task`，验证返回"子 agent 不支持委派子任务"错误 |

## 版本号更新

| 文件 | 变更 |
|------|------|
| `nautilus/__init__.py` | `0.3.0` → `0.3.1` |
| `pyproject.toml` | `version = "0.3.0"` → `version = "0.3.1"` |

## CLI 参数

v0.3.1 无新增 CLI 参数（子 agent 复用主 agent 的 model/client/text_mode/max_tool_output_chars/max_context_tokens 配置）。

参数（v0.3.1 不变，共 10 个）：
- `prompt` / `--model` / `--api-key` / `--base-url` / `--max-iter` / `--max-tool-output` / `--max-context-tokens` / `--stream` / `--approval` / `--text-mode`

## 终端输出格式

新增 `delegate_task` 的输出格式：

```
💭 我先搜索相关文件，然后委派子 agent 分析每个文件的内容。
🔧 glob("*.py")
   → calc.py, main.py, utils.py
🔧 delegate_task("读取 calc.py，分析所有函数的功能")
   📤 委派子 agent: 读取 calc.py，分析所有函数的功能
   📥 子 agent 完成: calc.py 包含 add/subtract/multiply/divide/power/factor...
   → calc.py 包含 add/subtract/multiply/divide/power/factorial/fibonacci 7 个函数...

✅ 分析完成。
```

## 不修改的文件

- `nautilus/llm.py`：不涉及（子 agent 复用已有 `complete_with_retry`）
- `nautilus/__main__.py`：不涉及（无新 CLI 参数）
- `pyproject.toml` 依赖列表：无新依赖

## 验证方式

1. `pip install -e .` 安装
2. 运行单元测试：
   ```bash
   PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
   ```
3. 预期结果：146 + ~9 新增 = 155 tests 全部通过（test_agent.py +6 + test_tools.py +3）
4. E2E 测试（Ollama + qwen2.5:7b）：
   ```bash
   OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
   nautilus --model "qwen2.5:7b" --max-iter 10 \
   "用 delegate_task 委派子 agent 搜索所有 .py 文件并分析每个文件的函数数量"
   ```
5. 验证：子 agent 独立执行 + 结果回灌主循环 + 主循环上下文不被污染
