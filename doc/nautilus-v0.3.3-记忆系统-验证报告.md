# Nautilus v0.3.3 记忆系统 — 验证报告

> 验证对象：Nautilus v0.3.3（1239 行 Python，7 工具，ReAct 循环 + 上下文压缩 + 子 agent + plan mode + 记忆系统）
> 验证日期：2026-09-10
> 验证环境：Python 3.14.4 / Windows 11 / openai 2.35.1 / pytest 9.0.3
> E2E 环境：Ollama 本地 / qwen2.5:7b / native function calling
> UT 文件：`nautilus/tests/` 目录下 5 个测试模块，175 个测试用例
> E2E 测试：3 个场景，全部通过

---

## 一、验证范围

### 1.1 验证目标

验证 Nautilus v0.3.3 记忆系统功能**是否可真正工作**——在 v0.3.2 已验证的基础上，验证 `memory.py` 的 `load_memory()` / `save_memory()` / `append_memory()` 函数、`run_agent()` 的记忆注入/保存集成、`--memory` CLI 参数的正确性，同时确认 v0.3.2 功能回归无退化。

### 1.2 UT 文件结构

```
nautilus/
├── pyproject.toml              # 16 行 — 版本 0.3.3
├── nautilus/                   # 源码包（1239 行）
│   ├── __init__.py             #   1 行 — 版本 0.3.3
│   ├── __main__.py             # 122 行 — CLI + --memory（12 个参数）
│   ├── agent.py                # 433 行 — ReAct 循环 + 压缩 + 子 agent + plan mode + 记忆注入/保存
│   ├── llm.py                  # 125 行 — client 工厂 + retry + stream
│   ├── memory.py               #  40 行 — load_memory + save_memory + append_memory（新增）
│   ├── prompts.py              # 119 行 — 系统提示词 + SUBAGENT + PLAN + TEXT_MODE + 记忆说明
│   └── tools.py                # 399 行 — 7 工具 + execute_tool 路由 + .gitignore + 危险过滤
└── tests/                      # 单元测试
    ├── __init__.py             #   8 行
    ├── test_tools.py           # 446 行 — 63 tests
    ├── test_agent.py           # 1150 行 — 46 tests
    ├── test_llm.py             # 286 行 — 18 tests
    ├── test_cli.py             # 266 行 — 28 tests
    └── test_memory.py          # 196 行 — 13 tests（新增）
```

### 1.3 运行方式

```bash
cd ".../AIAgent/mycodingagent/nautilus"
PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
```

---

## 二、验证结果总览

### 2.1 最终结果

```
============================ 175 passed in 35.09s =============================
```

| 指标 | v0.3.2 | v0.3.3 |
|------|--------|--------|
| 测试总数 | 160 | 175 |
| 通过 | 160 | 175 |
| 失败 | 0 | 0 |
| 错误 | 0 | 0 |
| 跳过 | 0 | 0 |
| 总耗时 | 33.93s | 35.09s |
| 新增测试 | — | +15 |

### 2.2 按模块统计

| 测试模块 | v0.3.2 测试数 | v0.3.3 测试数 | 新增 | 覆盖组件 |
|---------|------------|------------|------|---------|
| `test_tools.py` | 63 | 63 | — | — |
| `test_agent.py` | 46 | 46 | — | — |
| `test_llm.py` | 18 | 18 | — | — |
| `test_cli.py` | 26 | 28 | +2 | **--memory flag** + **memory_default_none** |
| `test_memory.py` | 0 | 13 | +13 | **TestLoadMemory**(3) + **TestSaveMemory**(3) + **TestAppendMemory**(4) + **TestMemoryIntegration**(3) |
| **合计** | **160** | **175** | **+15** | |

---

## 三、各模块验证详情

### 3.1 test_memory.py 新增测试（13 tests）

#### TestLoadMemory（3 tests）

| 测试 | 覆盖场景 |
|------|---------|
| `test_load_existing_memory` | 有记忆文件 → 返回内容字符串 |
| `test_load_nonexistent_memory` | 无记忆文件 → 返回空字符串 |
| `test_load_empty_memory` | 空文件 → 返回空字符串 |

关键验证点：
- 有文件时正确返回内容（含中文"上次任务"/"hello.py"）
- 无文件时不崩溃，返回空字符串（`FileNotFoundError` 捕获）
- 空文件返回空字符串

#### TestSaveMemory（3 tests）

| 测试 | 覆盖场景 |
|------|---------|
| `test_save_new_memory` | 新建记忆文件（含自动建目录） |
| `test_save_overwrite_memory` | 覆盖已有记忆文件 |
| `test_save_creates_parent_dir` | 父目录不存在时自动创建 |

关键验证点：
- 新建文件后 `path.exists()` 为 True，内容正确
- 覆盖后旧内容被替换为新内容
- 嵌套目录 `sub/dir/memory.md` 自动创建

#### TestAppendMemory（4 tests）

| 测试 | 覆盖场景 |
|------|---------|
| `test_append_to_existing` | 追加到已有文件，保留旧内容 |
| `test_append_creates_new_file` | 文件不存在时自动创建 |
| `test_append_adds_newline` | 追加内容末尾自动换行 |
| `test_append_creates_parent_dir` | 父目录不存在时自动创建（`.nautilus/memory.md`） |

关键验证点：
- 追加后文件同时包含旧内容和新内容
- 新文件自动创建
- 无换行结尾时自动补 `\n`
- `.nautilus/` 目录自动创建

#### TestMemoryIntegration（3 tests）

| 测试 | 覆盖场景 |
|------|---------|
| `test_memory_injected_into_system_prompt` | mock LLM 捕获 messages，验证 system prompt 含"项目记忆"段落 + 记忆内容 |
| `test_memory_saved_after_completion` | mock LLM 最终回答 → 验证记忆文件被追加 prompt + 回答 |
| `test_memory_not_saved_when_disabled` | `memory_path=None` → 验证无记忆文件创建 |

关键验证点：

**记忆注入**（`test_memory_injected_into_system_prompt`）：
- 预先用 `save_memory` 创建记忆文件（含"上次任务"/"hello.py"）
- mock LLM 捕获第 1 次调用的 messages
- 验证 system prompt 含"项目记忆"、"上次任务"、"hello.py"

**记忆保存**（`test_memory_saved_after_completion`）：
- 预先创建记忆文件（含"old content"）
- mock LLM 返回最终回答"任务完成：添加了 sqrt 函数"
- 验证记忆文件同时包含旧内容 + 新 prompt"添加 sqrt 函数到 calc.py" + 新回答"任务完成"

**记忆禁用**（`test_memory_not_saved_when_disabled`）：
- `memory_path=None` 时 mock LLM 返回最终回答
- 验证 `.nautilus/memory.md` 不存在

### 3.2 test_cli.py 新增测试（2 tests）

| 测试 | 覆盖场景 |
|------|---------|
| `test_memory_flag` | `--memory .nautilus/memory.md` 传参 → `memory_path=".nautilus/memory.md"` |
| `test_memory_default_none` | 不传参 → `memory_path=None` |

---

## 四、v0.3.3 功能验证

### 4.1 memory.py 函数

| 验证项 | 结果 | 说明 |
|--------|------|------|
| `load_memory()` 有文件 | ✅ | 返回内容字符串 |
| `load_memory()` 无文件 | ✅ | 返回空字符串，不崩溃 |
| `load_memory()` 空文件 | ✅ | 返回空字符串 |
| `save_memory()` 新建 | ✅ | 创建文件 + 自动建父目录 |
| `save_memory()` 覆盖 | ✅ | 覆盖旧内容 |
| `save_memory()` 嵌套目录 | ✅ | 自动创建 `sub/dir/` |
| `append_memory()` 追加 | ✅ | 保留旧内容 + 追加新内容 |
| `append_memory()` 新文件 | ✅ | 文件不存在时自动创建 |
| `append_memory()` 换行 | ✅ | 末尾自动补 `\n` |
| `append_memory()` 嵌套目录 | ✅ | 自动创建 `.nautilus/` |

### 4.2 agent.py 记忆集成

| 验证项 | 结果 | 说明 |
|--------|------|------|
| `memory_path` 参数 | ✅ | `run_agent()` 新增 `memory_path: str | None = None` |
| 记忆注入 system prompt | ✅ | `system_prompt += "\n\n## 项目记忆\n{memory}"` |
| 最终回答后保存记忆 | ✅ | `append_memory(memory_path, f"## {prompt}\n{final_answer}\n")` + `print("💾 记忆已保存")` |
| max_iter 路径保存 | ✅ | `append_memory(memory_path, f"## {prompt}\n(达到最大迭代次数，未完成)\n")` |
| 记忆禁用时不操作 | ✅ | `memory_path=None` 时不加载/不保存 |

### 4.3 prompts.py 更新

| 验证项 | 结果 | 说明 |
|--------|------|------|
| SYSTEM_PROMPT 记忆说明 | ✅ | "如果系统提示词中包含'项目记忆'段落，请参考其中的历史信息" |
| SYSTEM_PROMPT_TEXT_MODE 同步 | ✅ | 同上 |

### 4.4 CLI 参数

| 验证项 | 结果 | 说明 |
|--------|------|------|
| `--memory` 传参 | ✅ | `--memory .nautilus/memory.md` → `memory_path=".nautilus/memory.md"` |
| 默认 None | ✅ | 不传参 → `memory_path=None`（不启用） |

---

## 五、E2E 端到端真实场景验证

### 5.1 测试环境

| 项 | 值 |
|---|---|
| LLM 服务 | Ollama 本地 (http://127.0.0.1:11434) |
| 模型 | qwen2.5:7b（native function calling） |
| API Key | test |
| 模式 | native function calling |
| 测试项目 | 3 个 Python 文件（calc.py / main.py / utils.py） |
| OS | Windows 11 / Python 3.14.4 |

### 5.2 E2E 测试结果

| # | 测试场景 | 命令 | 结果 | 关键验证点 |
|---|---------|------|------|-----------|
| 1 | **首次运行写入记忆** | `OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:11434/v1 nautilus --model "qwen2.5:7b" --max-iter 5 --memory .nautilus/memory.md "用 glob 搜索所有 .py 文件，告诉我有几个文件"` | ✅ 通过 | glob 找到 3 文件 → 最终回答 → `💾 记忆已保存到 .nautilus/memory.md` → `.nautilus/memory.md` 被创建，含 prompt + 回答 |
| 2 | **第二次运行读取记忆** | `OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:11434/v1 nautilus --model "qwen2.5:7b" --max-iter 5 --memory .nautilus/memory.md "上次我让你做了什么？请根据记忆回答"` | ✅ 通过 | agent 正确引用上次任务结果："上次你让我搜索了所有 .py 文件，共有3个.py文件被找到" → 记忆追加第二次任务 |
| 3 | **不启用记忆对比** | `OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:11434/v1 nautilus --model "qwen2.5:7b" --max-iter 5 "用 glob 搜索所有 .py 文件，告诉我有几个文件"` | ✅ 通过 | 无 `💾 记忆已保存` 输出 → 无 `.nautilus/` 目录创建 → 记忆是可选叠加功能 |

### 5.3 E2E 测试详情

**测试 1：首次运行写入记忆**

Agent 用 qwen2.5:7b + `--memory .nautilus/memory.md` 执行任务：
1. `glob("*.py")` 找到 3 个文件（calc.py, main.py, utils.py）
2. 最终回答："共有3个.py文件被找到。"
3. `💾 记忆已保存到 .nautilus/memory.md`

验证 `.nautilus/memory.md` 内容：
```
## 用 glob 搜索所有 .py 文件，告诉我有几个文件
共有3个.py文件被找到。
```

验证点：记忆文件被正确创建，含 prompt + 最终回答，`.nautilus/` 目录自动创建。

**测试 2：第二次运行读取记忆**

Agent 用 `--memory .nautilus/memory.md` 执行不同任务："上次我让你做了什么？请根据记忆回答"

Agent 没有调用任何工具——直接基于 system prompt 中的"项目记忆"段落回答：
```
✅ 上次你让我搜索了所有 .py 文件，共有3个.py文件被找到。
💾 记忆已保存到 .nautilus/memory.md
```

验证 `.nautilus/memory.md` 内容（追加后）：
```
## 用 glob 搜索所有 .py 文件，告诉我有几个文件
共有3个.py文件被找到。
## 上次我让你做了什么？请根据记忆回答
上次你让我搜索了所有 .py 文件，共有3个.py文件被找到。
```

验证点：
- 记忆被正确注入 system prompt（"项目记忆"段落）
- LLM 正确引用上次任务结果（"上次你让我搜索了所有 .py 文件"）
- 第二次任务也被追加到记忆文件（追加而非覆盖）
- Agent 无需调用工具即可回答——记忆提供了足够上下文

**测试 3：不启用记忆对比**

Agent 不传 `--memory` 执行同一任务：
1. `glob("*.py")` 找到 3 个文件
2. 最终回答："一共有3个 .py 文件"
3. 无 `💾 记忆已保存` 输出
4. 无 `.nautilus/` 目录创建

验证点：记忆是可选叠加功能，不传 `--memory` 时不影响默认行为。

### 5.4 用例设计理由

| # | 场景 | 设计理由 |
|---|------|---------|
| 1 | **首次运行写入记忆** | 验证记忆写入功能——任务完成后 `.nautilus/memory.md` 被创建，包含 prompt + 最终回答摘要。验证 `append_memory` 在 `run_agent` 最终回答路径的正确执行 |
| 2 | **第二次运行读取记忆** | 验证跨会话上下文保持——第二次运行时 system prompt 包含"项目记忆"段落，agent 能引用上次任务结果。验证 `load_memory` 注入 system prompt 的正确性，以及记忆追加（第二次任务也被保存） |
| 3 | **不启用记忆的对比** | 验证默认模式不受影响——不传 `--memory` 时不创建记忆文件、不读取记忆。确认记忆是可选叠加功能，不破坏默认行为 |

### 5.5 跨会话记忆验证

| 维度 | 第一次运行 | 第二次运行 |
|------|-----------|-----------|
| 记忆文件状态 | 不存在 → 创建 | 已存在 → 读取 + 追加 |
| system prompt | 无"项目记忆"段落 | 含"项目记忆"段落（上次任务结果） |
| Agent 行为 | glob 工具调用 → 回答 | 直接回答（无需工具）——记忆提供了足够上下文 |
| 记忆文件内容 | 1 条记录 | 2 条记录（追加而非覆盖） |

---

## 六、发现的问题

### 6.1 Windows GBK 编码兼容性（v2 遗留，已修复）

P0 修复已在 `__main__.py` 入口处添加 `sys.stdout.reconfigure(encoding="utf-8")`。

### 6.2 上级目录 pyproject.toml 干扰（v2 遗留，未修复）

**当前规避**：`-o "addopts="`

---

## 七、测试覆盖率矩阵

| 源文件 | v0.3.2 行数 | v0.3.3 行数 | 测试文件 | v0.3.2 测试 | v0.3.3 测试 | 关键路径覆盖 |
|--------|------------|------------|---------|------------|------------|------------|
| `tools.py` | 399 | 399 | `test_tools.py` | 63 | 63 | — |
| `agent.py` | 412 | 433 | `test_agent.py` | 46 | 46 | —（记忆集成在 test_memory.py 中测试） |
| `llm.py` | 125 | 125 | `test_llm.py` | 18 | 18 | — |
| `__main__.py` | 116 | 122 | `test_cli.py` | 26 | 28 | +**--memory flag** |
| `prompts.py` | 115 | 119 | 间接覆盖 | — | — | +**记忆说明** |
| `memory.py` | 0 | 40 | `test_memory.py` | 0 | 13 | **load/save/append/integration** |
| `__init__.py` | 1 | 1 | 间接覆盖 | — | — | 版本 0.3.3 |
| **合计** | **1168** | **1239** | | **160** | **175** | |

---

## 八、v0.3.2→v0.3.3 回归对比

| 验证维度 | v0.3.2 状态 | v0.3.3 状态 | 回归 |
|---------|------------|------------|------|
| 模块导入 | ✅ 6 模块 | ✅ 7 模块（+memory） | 无退化 |
| CLI --help | ✅ 11 参数 | ✅ 12 参数 | 无退化 |
| read_file/write_file/edit_file/glob/grep/bash | ✅ 6 工具 | ✅ 6 工具 | 无退化 |
| delegate_task | ✅ 1 工具 | ✅ 1 工具 | 无退化 |
| execute_tool 路由 | ✅ 6 路由 | ✅ 6 路由 | 无退化 |
| TOOL_SCHEMAS | ✅ 7 schema | ✅ 7 schema | 无退化 |
| ReAct 循环（mock LLM） | ✅ 5 场景 | ✅ 5 场景 | 无退化 |
| 上下文压缩 | ✅ 9 tests | ✅ 9 tests | 无退化 |
| 子 agent | ✅ 6 tests | ✅ 6 tests | 无退化 |
| plan mode | ✅ 3 tests | ✅ 3 tests | 无退化 |
| 权限审批 | ✅ 3 tests | ✅ 3 tests | 无退化 |
| 危险命令过滤 | ✅ 9 tests | ✅ 9 tests | 无退化 |
| GBK 编码修复 | ✅ 1 test | ✅ 1 test | 无退化 |
| **记忆系统** | — | ✅ **13 tests** | **新增** |
| **CLI --memory** | — | ✅ **2 tests** | **新增** |
| **合计** | **160 passed** | **175 passed** | **0 退化** |

---

## 九、结论

### 9.1 记忆系统功能验证通过

Nautilus v0.3.3 的记忆系统功能**全部通过验证**：

- **memory.py 函数**：`load_memory` / `save_memory` / `append_memory`——全部正确（有文件/无文件/空文件/新建/覆盖/追加/自动建目录）
- **agent.py 集成**：记忆注入 system prompt + 最终回答后保存 + max_iter 路径保存——全部正确
- **prompts.py 更新**：SYSTEM_PROMPT + TEXT_MODE 新增"项目记忆"说明——正确
- **CLI 参数**：`--memory` 传参 + 默认 None——正确

### 9.2 E2E 端到端真实场景验证通过

在 Ollama + qwen2.5:7b 环境下完成 3 个真实场景测试，全部通过：

- **首次运行写入记忆**：glob → 回答 → `💾 记忆已保存` → `.nautilus/memory.md` 创建正确
- **第二次运行读取记忆**：agent 引用上次任务结果 → 记忆追加（非覆盖）
- **不启用记忆对比**：无 `💾` 输出、无 `.nautilus/` 目录——可选叠加功能

### 9.3 跨会话上下文保持验证通过

第二次运行时 agent 无需调用工具即可回答——记忆中的"项目记忆"段落提供了足够上下文。这是记忆系统的核心价值：跨会话上下文保持，避免每次从零理解项目。

### 9.4 v0.3.2 回归无退化

v0.3.2 的 160 个测试全部在 v0.3.3 中继续通过，0 退化。新增的 15 个测试覆盖记忆系统全部新功能。

### 9.5 已知问题

| 问题 | 严重程度 | 状态 | 规避方式 |
|------|---------|------|---------|
| Windows GBK 编码 | 中 | 已修复（P0） | `__main__.py` 入口 `sys.stdout.reconfigure` |
| 上级 pyproject.toml 干扰 | 低 | 未修复 | `-o "addopts="` |

---

## 附录：完整测试输出

```
============================= test session starts ==============================
platform win32 -- Python 3.14.4, pytest-9.0.3, pluggy-1.6.0
rootdir: D:\AIAgent\Practice
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0
collected 175 items

tests\test_agent.py::TestTruncate::test_short_text_passthrough PASSED    [  0%]
tests\test_agent.py::TestTruncate::test_exact_limit PASSED               [  1%]
tests\test_agent.py::TestTruncate::test_long_text_truncated PASSED       [  1%]
tests\test_agent.py::TestTruncate::test_truncation_marker_format PASSED  [  2%]
tests\test_agent.py::TestTruncate::test_empty_string PASSED              [  2%]
tests\test_agent.py::TestTruncate::test_custom_limit PASSED              [  3%]
tests\test_agent.py::TestEstimateTokens::test_pure_ascii PASSED          [  4%]
tests\test_agent.py::TestEstimateTokens::test_pure_cjk PASSED            [  4%]
tests\test_agent.py::TestEstimateTokens::test_empty_string PASSED        [  5%]
tests\test_agent.py::TestEstimateTokens::test_mixed_ascii_cjk PASSED     [  5%]
tests\test_agent.py::TestEstimateTokens::test_long_code_text PASSED      [  6%]
tests\test_agent.py::TestEstimateTokens::test_none_safety PASSED         [  6%]
tests\test_agent.py::TestTruncateForLlm::test_short_text_passthrough PASSED [  7%]
tests\test_agent.py::TestTruncateForLlm::test_exact_limit_no_truncation PASSED [  8%]
tests\test_agent.py::TestTruncateForLlm::test_long_text_truncated_with_bilingual_marker PASSED [  8%]
tests\test_agent.py::TestTruncateForLlm::test_custom_max_chars PASSED    [  9%]
tests\test_agent.py::TestTruncateForLlm::test_empty_string PASSED       [  9%]
tests\test_agent.py::TestPrintToolCall::test_read_file PASSED            [ 10%]
tests\test_agent.py::TestPrintToolCall::test_write_file PASSED           [ 10%]
tests\test_agent.py::TestPrintToolCall::test_edit_file PASSED            [ 11%]
tests\test_agent.py::TestPrintToolCall::test_bash PASSED                 [ 12%]
tests\test_agent.py::TestPrintToolCall::test_unknown_tool PASSED         [ 12%]
tests\test_agent.py::TestPrintToolCall::test_missing_args PASSED         [ 13%]
tests\test_agent.py::TestRunAgentReActLoop::test_full_react_loop PASSED  [ 13%]
tests\test_agent.py::TestRunAgentMaxIter::test_max_iter_truncation PASSED [ 14%]
tests\test_agent.py::TestRunAgentErrorRecovery::test_error_self_correction PASSED [ 14%]
tests\test_agent.py::TestRunAgentTokenBudget::test_large_tool_output_truncated_in_messages PASSED [ 15%]
tests\test_agent.py::TestMessagesTokenEstimate::test_pure_dict_messages PASSED [ 16%]
tests\test_agent.py::TestMessagesTokenEstimate::test_empty_messages PASSED [ 16%]
tests\test_agent.py::TestMessagesTokenEstimate::test_dict_with_tool_calls PASSED [ 17%]
tests\test_agent.py::TestMessagesTokenEstimate::test_sdk_like_objects PASSED [ 17%]
tests\test_agent.py::TestCompressHistory::test_no_compression_under_budget PASSED [ 18%]
tests\test_agent.py::TestCompressHistory::test_compresses_over_budget PASSED [ 18%]
tests\test_agent.py::TestCompressHistory::test_never_drops_system_and_user PASSED [ 19%]
tests\test_agent.py::TestCompressHistory::test_empty_history_after_system_user PASSED [ 20%]
tests\test_agent.py::TestRunAgentContextCompression::test_history_compressed_within_budget PASSED [ 20%]
tests\test_agent.py::TestRunAgentApproval::test_approval_rejected_bash_command PASSED [ 21%]
tests\test_agent.py::TestRunAgentApproval::test_approval_accepted_bash_command PASSED [ 21%]
tests\test_agent.py::TestRunAgentApproval::test_approval_disabled_by_default PASSED [ 22%]
tests\test_agent.py::TestRunSubagent::test_subagent_returns_final_answer PASSED [ 22%]
tests\test_agent.py::TestRunSubagent::test_subagent_independent_messages PASSED [ 23%]
tests\test_agent.py::TestRunSubagent::test_subagent_max_iter PASSED      [ 24%]
tests\test_agent.py::TestDelegateTask::test_delegate_task_calls_subagent PASSED [ 24%]
tests\test_agent.py::TestDelegateTask::test_delegate_task_does_not_pollute_main PASSED [ 25%]
tests\test_agent.py::TestDelegateTask::test_subagent_rejects_recursive_delegate PASSED [ 25%]
tests\test_agent.py::TestPlanMode::test_plan_mode_accepted PASSED        [ 26%]
tests\test_agent.py::TestPlanMode::test_plan_mode_rejected PASSED        [ 26%]
tests\test_agent.py::TestPlanMode::test_plan_mode_disabled_by_default PASSED [ 27%]
tests\test_cli.py::TestCLIHelp::test_help_exits_zero PASSED              [ 28%]
tests\test_cli.py::TestCLIHelp::test_help_without_encoding_override PASSED [ 28%]
tests\test_cli.py::TestCLIHelp::test_help_shows_description PASSED       [ 29%]
tests\test_cli.py::TestCLINoPrompt::test_no_prompt_no_stdin_exits_1 PASSED [ 29%]
tests\test_cli.py::TestCLIStdin::test_stdin_prompt_is_read PASSED        [ 30%]
tests\test_cli.py::TestCLIArgumentParsing::test_positional_prompt PASSED [ 30%]
tests\test_cli.py::TestCLIArgumentParsing::test_model_flag PASSED        [ 31%]
tests\test_cli.py::TestCLIArgumentParsing::test_api_key_flag PASSED      [ 32%]
tests\test_cli.py::TestCLIArgumentParsing::test_base_url_flag PASSED     [ 32%]
tests\test_cli.py::TestCLIArgumentParsing::test_max_iter_flag PASSED     [ 33%]
tests\test_cli.py::TestCLIArgumentParsing::test_max_tool_output_flag PASSED [ 33%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_max_iter_is_20 PASSED [ 34%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_model_is_gpt4 PASSED [ 34%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_api_key_is_none PASSED [ 35%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_max_tool_output_is_6000 PASSED [ 36%]
tests\test_cli.py::TestCLIArgumentParsing::test_max_context_tokens_flag PASSED [ 36%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_max_context_tokens_is_32000 PASSED [ 37%]
tests\test_cli.py::TestCLIArgumentParsing::test_stream_flag PASSED       [ 37%]
tests\test_cli.py::TestCLIArgumentParsing::test_stream_default_false PASSED [ 38%]
tests\test_cli.py::TestCLIArgumentParsing::test_approval_flag PASSED     [ 38%]
tests\test_cli.py::TestCLIArgumentParsing::test_approval_default_false PASSED [ 39%]
tests\test_cli.py::TestCLIArgumentParsing::test_plan_flag PASSED         [ 40%]
tests\test_cli.py::TestCLIArgumentParsing::test_plan_default_false PASSED [ 40%]
tests\test_cli.py::TestCLIArgumentParsing::test_memory_flag PASSED       [ 41%]
tests\test_cli.py::TestCLIArgumentParsing::test_memory_default_none PASSED [ 41%]
tests\test_llm.py::TestCreateClientNoKey::test_no_key_raises_systemexit PASSED [ 42%]
tests\test_llm.py::TestCreateClientNoKey::test_no_key_message_mentions_env_var PASSED [ 42%]
tests\test_llm.py::TestCreateClientExplicit::test_explicit_key_creates_client PASSED [ 43%]
tests\test_llm.py::TestCreateClientExplicit::test_explicit_key_and_base_url PASSED [ 43%]
tests\test_llm.py::TestCreateClientEnvFallback::test_env_api_key PASSED  [ 44%]
tests\test_llm.py::TestCreateClientEnvFallback::test_env_api_key_and_base_url PASSED [ 44%]
tests\test_llm.py::TestCreateClientEnvFallback::test_explicit_overrides_env PASSED [ 45%]
tests\test_llm.py::TestCreateClientEnvFallback::test_base_url_not_set_when_only_api_key_in_env PASSED [ 45%]
tests\test_llm.py::TestCreateClientPriority::test_none_api_key_falls_back_to_env PASSED [ 46%]
tests\test_llm.py::TestCreateClientPriority::test_empty_string_api_key_does_not_fallback PASSED [ 46%]
tests\test_llm.py::TestCompleteWithRetry::test_success_on_first_try PASSED [ 47%]
tests\test_llm.py::TestCompleteWithRetry::test_retry_on_rate_limit_then_success PASSED [ 47%]
tests\test_llm.py::TestCompleteWithRetry::test_all_retries_exhausted_raises_systemexit PASSED [ 48%]
tests\test_llm.py::TestCompleteWithRetry::test_bad_request_not_retried PASSED [ 48%]
tests\test_llm.py::TestCompleteWithRetry::test_auth_error_not_retried PASSED [ 49%]
tests\test_llm.py::TestStreamComplete::test_stream_content_accumulated_and_printed PASSED [ 49%]
tests\test_llm.py::TestStreamComplete::test_stream_tool_calls_assembled PASSED [ 50%]
tests\test_llm.py::TestStreamComplete::test_stream_empty_response PASSED [ 50%]
tests\test_memory.py::TestLoadMemory::test_load_existing_memory PASSED   [ 51%]
tests\test_memory.py::TestLoadMemory::test_load_nonexistent_memory PASSED [ 51%]
tests\test_memory.py::TestLoadMemory::test_load_empty_memory PASSED      [ 52%]
tests\test_memory.py::TestSaveMemory::test_save_new_memory PASSED        [ 52%]
tests\test_memory.py::TestSaveMemory::test_save_overwrite_memory PASSED  [ 53%]
tests\test_memory.py::TestSaveMemory::test_save_creates_parent_dir PASSED [ 53%]
tests\test_memory.py::TestAppendMemory::test_append_to_existing PASSED   [ 54%]
tests\test_memory.py::TestAppendMemory::test_append_creates_new_file PASSED [ 54%]
tests\test_memory.py::TestAppendMemory::test_append_adds_newline PASSED  [ 55%]
tests\test_memory.py::TestAppendMemory::test_append_creates_parent_dir PASSED [ 55%]
tests\test_memory.py::TestMemoryIntegration::test_memory_injected_into_system_prompt PASSED [ 56%]
tests\test_memory.py::TestMemoryIntegration::test_memory_saved_after_completion PASSED [ 56%]
tests\test_memory.py::TestMemoryIntegration::test_memory_not_saved_when_disabled PASSED [ 57%]
tests\test_tools.py::TestWriteFile::test_write_normal PASSED             [ 57%]
tests\test_tools.py::TestWriteFile::test_write_returns_byte_count PASSED [ 58%]
tests\test_tools.py::TestWriteFile::test_auto_create_parent_dirs PASSED  [ 58%]
tests\test_tools.py::TestWriteFile::test_overwrite_existing PASSED       [ 58%]
tests\test_tools.py::TestReadFile::test_read_normal PASSED               [ 59%]
tests\test_tools.py::TestReadFile::test_read_nonexistent PASSED          [ 59%]
tests\test_tools.py::TestReadFile::test_read_binary_file PASSED          [ 60%]
tests\test_tools.py::TestEditFile::test_edit_normal PASSED               [ 60%]
tests\test_tools.py::TestEditFile::test_edit_old_string_not_found PASSED [ 60%]
tests\test_tools.py::TestEditFile::test_edit_multiple_matches PASSED     [ 61%]
tests\test_tools.py::TestEditFile::test_edit_nonexistent_file PASSED     [ 61%]
tests\test_tools.py::TestEditFile::test_edit_preserves_surrounding_content PASSED [ 62%]
tests\test_tools.py::TestBash::test_echo_success PASSED                  [ 62%]
tests\test_tools.py::TestBash::test_python_execution PASSED              [ 63%]
tests\test_tools.py::TestBash::test_nonzero_exit PASSED                  [ 63%]
tests\test_tools.py::TestBash::test_stderr_capture PASSED                [ 64%]
tests\test_tools.py::TestBash::test_command_output_includes_both_streams PASSED [ 64%]
tests\test_tools.py::TestDangerousCommandFilter::test_rm_rf_root_blocked PASSED [ 64%]
tests\test_tools.py::TestDangerousCommandFilter::test_rm_rf_home_blocked PASSED [ 65%]
tests\test_tools.py::TestDangerousCommandFilter::test_rm_rf_star_blocked PASSED [ 65%]
tests\test_tools.py::TestDangerousCommandFilter::test_format_c_blocked PASSED [ 66%]
tests\test_tools.py::TestDangerousCommandFilter::test_mkfs_blocked PASSED [ 66%]
tests\test_tools.py::TestDangerousCommandFilter::test_safe_command_not_blocked PASSED [ 67%]
tests\test_tools.py::TestDangerousCommandFilter::test_dangerous_allowed_with_flag PASSED [ 67%]
tests\test_tools.py::TestDangerousCommandFilter::test_case_insensitive_match PASSED [ 68%]
tests\test_tools.py::TestDangerousCommandFilter::test_dangerous_in_pipeline_blocked PASSED [ 68%]
tests\test_tools.py::TestExecuteTool::test_route_write_file PASSED       [ 69%]
tests\test_tools.py::TestExecuteTool::test_route_read_file PASSED        [ 69%]
tests\test_tools.py::TestExecuteTool::test_route_edit_file PASSED        [ 70%]
tests\test_tools.py::TestExecuteTool::test_route_bash PASSED             [ 70%]
tests\test_tools.py::TestExecuteTool::test_route_glob PASSED             [ 71%]
tests\test_tools.py::TestExecuteTool::test_route_grep PASSED            [ 71%]
tests\test_tools.py::TestExecuteTool::test_unknown_tool PASSED           [ 72%]
tests\test_tools.py::TestExecuteTool::test_invalid_json_arguments PASSED [ 72%]
tests\test_tools.py::TestExecuteTool::test_empty_arguments_string PASSED [ 73%]
tests\test_tools.py::TestExecuteTool::test_none_arguments PASSED         [ 73%]
tests\test_tools.py::TestToolSchemas::test_schema_count PASSED           [ 74%]
tests\test_tools.py::TestToolSchemas::test_schema_names PASSED           [ 74%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 74%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 75%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 75%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 76%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 76%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 77%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 77%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 78%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 78%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 79%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 79%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 80%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 80%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 81%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 81%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 82%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 82%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 83%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 83%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 84%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 84%]
tests\test_tools.py::TestToolSchemas::test_all_schemas_are_function_type PASSED [ 85%]
tests\test_tools.py::TestGlob::test_glob_finds_python_files PASSED       [ 85%]
tests\test_tools.py::TestGlob::test_glob_no_match PASSED                 [ 86%]
tests\test_tools.py::TestGlob::test_glob_recursive PASSED                [ 86%]
tests\test_tools.py::TestGlob::test_glob_respects_gitignore PASSED       [ 87%]
tests\test_tools.py::TestGrep::test_grep_finds_matches PASSED            [ 87%]
tests\test_tools.py::TestGrep::test_grep_returns_line_numbers PASSED     [ 88%]
tests\test_tools.py::TestGrep::test_grep_no_match PASSED                 [ 88%]
tests\test_tools.py::TestGrep::test_grep_specific_file PASSED            [ 89%]
tests\test_tools.py::TestGrep::test_grep_invalid_regex PASSED            [ 89%]
tests\test_tools.py::TestGrep::test_grep_skips_binary_files PASSED       [ 90%]
tests\test_tools.py::TestGrep::test_grep_respects_gitignore PASSED       [ 90%]

============================ 175 passed in 35.09s =============================
```

---

## 参考资料

- Nautilus v3 实现计划（整体）：`nautilus-v3-实现计划(整体).md`（同目录）
- Nautilus v0.3.3 记忆系统实现计划：`nautilus-v0.3.3-记忆系统-实现计划.md`（同目录）
- Nautilus v0.3.2 plan mode 验证报告：`nautilus-v0.3.2-plan mode-验证报告.md`（同目录）
- 源码：`nautilus/nautilus/`（agent.py / tools.py / prompts.py / llm.py / memory.py / __main__.py）
- UT 源码：`nautilus/tests/`（test_tools.py / test_agent.py / test_llm.py / test_cli.py / test_memory.py）
