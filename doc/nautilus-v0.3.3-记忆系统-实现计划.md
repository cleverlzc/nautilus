# Nautilus v0.3.3 记忆系统 — 实现计划

## Context

v0.3.2 已完成 plan mode（1168 行，160 tests + 3 E2E 场景）。`nautilus-v3-特性优先级排序.md` 将记忆系统列为 P3 特性，独立于上下文压缩/子 agent/plan mode。

当前代码基线（v0.3.2）：1168 行 Python 源码 + 160 tests。

v0.3.3 的目标：**让 agent 跨会话保持上下文**——agent 自动读取项目级记忆文件（`.nautilus/memory.md`），将已有记忆注入 system prompt；任务完成后自动将本次任务的 prompt + 最终回答摘要追加到记忆文件。避免每次从零理解项目（ToC：降低运行费用 OE）。

## 项目位置

```
...\AIAgent\mycodingagent\nautilus\
```

## 问题分析

当前 agent 每次运行都是"失忆"的——不记得上次做了什么、项目结构是什么、哪些文件已修改。用户每次需要重新告诉 agent 项目的上下文。

记忆系统解决方案：agent 启动时自动读取 `.nautilus/memory.md`，将内容注入 system prompt 的"项目记忆"段落；任务完成后自动将本次任务摘要追加到记忆文件。下次运行时 agent 能看到历史记忆，实现跨会话上下文保持。

| 维度 | 无记忆系统 | 有记忆系统 |
|------|-----------|-----------|
| 跨会话上下文 | ❌ 每次从零开始 | ✅ 读取历史记忆 |
| 项目理解 | 需要用户/工具重新探索 | 记忆中已有项目结构摘要 |
| 重复劳动 | 每次重新 glob/grep 了解项目 | 记忆中有上次的发现 |
| 运行费用 OE | 高（重复探索） | 低（记忆复用） |

## 文件清单（5 个文件，含 1 个新文件）

| 文件 | 职责 | 基线行数 | 预估行数 | 变化 |
|------|------|---------|---------|------|
| `nautilus/memory.py` | **新文件**：记忆加载/保存/追加 | 0 | ~40 | `load_memory()` + `save_memory()` + `append_memory()` |
| `nautilus/agent.py` | ReAct 循环 + plan mode + **记忆注入/保存** | 412 | ~445 | +`memory_path` 参数 + 加载记忆注入 system prompt + 循环后保存记忆 + import |
| `nautilus/prompts.py` | 系统提示词 | 115 | ~125 | +记忆相关说明 |
| `nautilus/__main__.py` | CLI 入口 | 116 | ~123 | +`--memory` CLI 参数 |
| `tests/test_memory.py` | **新文件**：记忆系统测试 | 0 | ~100 | `TestLoadMemory` + `TestSaveMemory` + `TestAppendMemory` + `TestMemoryIntegration` |

## 各文件实现细节

### 1. `nautilus/memory.py` — 新文件（~40 行）

```python
"""Memory system for cross-session context persistence."""

import os


def load_memory(path: str = ".nautilus/memory.md") -> str:
    """读取记忆文件，返回内容字符串。无文件返回空字符串。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, OSError):
        return ""


def save_memory(path: str, content: str) -> str:
    """保存记忆内容到文件。自动创建父目录。"""
    try:
        parent = os.path.dirname(path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"记忆已保存到 {path}"
    except Exception as e:
        return f"错误：保存记忆失败：{e}"


def append_memory(path: str, entry: str) -> str:
    """追加一条记忆条目到记忆文件。自动创建父目录。"""
    try:
        parent = os.path.dirname(path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry)
            if not entry.endswith("\n"):
                f.write("\n")
        return f"记忆已追加到 {path}"
    except Exception as e:
        return f"错误：追加记忆失败：{e}"
```

### 2. `nautilus/agent.py` — 核心修改

**修改 `run_agent()` 签名**：

```python
def run_agent(
    ...
    plan_mode: bool = False,
    memory_path: str | None = None,  # NEW: None = 不启用记忆
) -> None:
```

**修改函数体——加载记忆注入 system prompt**：

在 `system_prompt = SYSTEM_PROMPT_TEXT_MODE if text_mode else SYSTEM_PROMPT` 之后：

```python
    # Load memory and inject into system prompt
    if memory_path:
        memory = load_memory(memory_path)
        if memory:
            system_prompt += f"\n\n## 项目记忆\n{memory}"
```

**修改函数体——循环后保存记忆**：

需要从 ReAct 循环中提取最终回答。当前 `run_agent` 在最终回答时直接 `print + return`，不保存回答。需要改为先保存到变量，再 `print + return`，最后在 return 前保存记忆。

```python
    for i in range(max_iter):
        ...
        if not message.tool_calls:
            final_answer = message.content or ""
            if final_answer and not stream:
                print(f"\n✅ {final_answer}")
            elif final_answer and stream:
                print("\n✅ (流式输出完成)")
            # Save memory before returning
            if memory_path and final_answer:
                append_memory(memory_path, f"## {prompt}\n{final_answer}\n")
                print(f"💾 记忆已保存到 {memory_path}")
            return
        ...

    # max_iter reached
    if memory_path:
        append_memory(memory_path, f"## {prompt}\n(达到最大迭代次数，未完成)\n")
    print(f"\n⚠️  达到最大迭代次数 ({max_iter})，agent 终止。")
```

**import 新增**：

```python
from .memory import load_memory, append_memory
```

### 3. `nautilus/prompts.py` — 新增记忆说明

在 `SYSTEM_PROMPT` 和 `SYSTEM_PROMPT_TEXT_MODE` 的末尾新增：

```
如果系统提示词中包含"项目记忆"段落，请参考其中的历史信息来理解项目上下文。
```

### 4. `nautilus/__main__.py` — 新增 --memory CLI 参数

```python
parser.add_argument(
    "--memory",
    default=None,
    help="启用记忆系统，指定记忆文件路径（如 .nautilus/memory.md）。不传则不启用。",
)
```

传到 `run_agent`：

```python
run_agent(
    ...
    memory_path=args.memory,
)
```

### 5. `tests/test_memory.py` — 新文件（~100 行）

**TestLoadMemory（3 tests）**：

| 测试 | 覆盖场景 |
|------|---------|
| `test_load_existing_memory` | 有记忆文件 → 返回内容字符串 |
| `test_load_nonexistent_memory` | 无记忆文件 → 返回空字符串 |
| `test_load_empty_memory` | 空文件 → 返回空字符串 |

**TestSaveMemory（3 tests）**：

| 测试 | 覆盖场景 |
|------|---------|
| `test_save_new_memory` | 新建记忆文件（含自动建目录） |
| `test_save_overwrite_memory` | 覆盖已有记忆文件 |
| `test_save_creates_parent_dir` | 父目录不存在时自动创建 |

**TestAppendMemory（3 tests）**：

| 测试 | 覆盖场景 |
|------|---------|---------|
| `test_append_to_existing` | 追加到已有文件 |
| `test_append_creates_new_file` | 文件不存在时自动创建 |
| `test_append_adds_newline` | 追加内容末尾自动换行 |

**TestMemoryIntegration（2 tests）**：

| 测试 | 覆盖场景 |
|------|---------|
| `test_memory_injected_into_system_prompt` | mock LLM 捕获 messages，验证 system prompt 含"项目记忆"段落 |
| `test_memory_saved_after_completion` | mock LLM 最终回答 → 验证记忆文件被追加 prompt + 回答 |

## 版本号更新

| 文件 | 变更 |
|------|------|
| `nautilus/__init__.py` | `0.3.2` → `0.3.3` |
| `pyproject.toml` | `version = "0.3.2"` → `version = "0.3.3"` |

## CLI 参数

v0.3.3 新增 1 个参数（共 12 个）：

```
$ nautilus --memory .nautilus/memory.md "继续上次的项目分析任务"
$ nautilus --memory .nautilus/memory.md --plan "重构模块"
$ nautilus "不启用记忆的任务"  # 不传 --memory 则不启用
```

参数（v0.3.3 新增 1 个，共 12 个）：
- `prompt` / `--model` / `--api-key` / `--base-url` / `--max-iter` / `--max-tool-output` / `--max-context-tokens` / `--stream` / `--approval` / `--text-mode` / `--plan`
- `--memory`（默认 None，不启用）**← v0.3.3 新增**

## 终端输出格式

```
💾 记忆已保存到 .nautilus/memory.md          # 任务完成后

📋 执行计划:                                 # plan mode
...
是否执行此计划? [y/N]: y

💭 根据记忆，上次已经分析了 calc.py...
🔧 read_file("calc.py")
   → def add(a, b): ...
✅ 已完成。添加了 sqrt 函数。

💾 记忆已保存到 .nautilus/memory.md
```

## 不修改的文件

- `nautilus/llm.py`：不涉及
- `nautilus/tools.py`：不涉及
- `pyproject.toml` 依赖列表：无新依赖（仅用 stdlib os）

## 验证方式

1. `pip install -e .` 安装
2. 运行单元测试：
   ```bash
   PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
   ```
3. 预期结果：160 + ~11 新增 = ~171 tests 全部通过
4. E2E 测试（Ollama + qwen2.5:7b）：
   ```bash
   OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
   nautilus --model "qwen2.5:7b" --max-iter 10 \
   --memory .nautilus/memory.md \
   "分析这个项目的所有 Python 文件，统计函数数量"

   # 第二次运行，验证记忆被加载
   OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
   nautilus --model "qwen2.5:7b" --max-iter 10 \
   --memory .nautilus/memory.md \
   "上次我让你做了什么？"
   ```
5. 验证：第一次运行后 `.nautilus/memory.md` 被创建 + 第二次运行时 system prompt 含"项目记忆"段落
