# Nautilus v0.3.3 记忆系统 — 实现总结

## 文件清单（实际）

**8 个源码文件 + 5 个测试文件**，位于 `...\AIAgent\mycodingagent\nautilus\`：

| 文件 | v0.3.2 行数 | v0.3.3 行数 | 职责 |
|------|------------|------------|------|
| `pyproject.toml` | 16 | 16 | 项目元数据 + openai 依赖 + CLI 入口（版本 0.3.3） |
| `nautilus/__init__.py` | 1 | 1 | 版本号（0.3.3） |
| `nautilus/memory.py` | 0 | 40 | **新文件**：`load_memory()` + `save_memory()` + `append_memory()` |
| `nautilus/prompts.py` | 115 | 119 | 系统提示词 + SUBAGENT + PLAN + TEXT_MODE + **记忆说明** |
| `nautilus/tools.py` | 399 | 399 | 7 个工具 + execute_tool 路由 + .gitignore 过滤 + 危险命令过滤 |
| `nautilus/llm.py` | 125 | 125 | OpenAI 兼容 client 工厂 + complete_with_retry + stream_complete |
| `nautilus/agent.py` | 412 | 433 | **核心 ReAct 循环** + token 预算控制 + stream/approval/text_mode/plan_mode 分支 + 上下文压缩 + 子 agent + plan mode + **记忆注入/保存** |
| `nautilus/__main__.py` | 116 | 122 | CLI 入口 + GBK 编码修复 + 12 个参数（含 `--memory`） |
| **源码合计** | **1168** | **1239** | |

**总计 1239 行 Python 源码**（v0.3.3 新增约 71 行源码 + 15 个测试，主要是 `memory.py` 新文件 + `run_agent` 记忆注入/保存集成 + `SYSTEM_PROMPT_PLAN` 记忆说明 + `--memory` CLI 参数）。

## v0.3.3 新增功能（1 个）

| # | 功能 | 核心实现 |
|---|------|---------|
| 1 | **记忆系统** | `memory.py` 新文件（40 行）：`load_memory()` 读取记忆文件 + `save_memory()` 保存 + `append_memory()` 追加，均自动创建父目录。`agent.py` `run_agent()` 新增 `memory_path` 参数：启动时 `load_memory` 注入 system prompt"项目记忆"段落；最终回答后 `append_memory` 保存 prompt + 回答；max_iter 路径也保存。`prompts.py` 新增"如果系统提示词中包含'项目记忆'段落，请参考其中的历史信息"说明。`__main__.py` 新增 `--memory` CLI 参数 |

### 跨会话上下文保持机制

| 维度 | 无记忆系统 | 有记忆系统 |
|------|-----------|-----------|
| 跨会话上下文 | ❌ 每次从零开始 | ✅ 读取历史记忆注入 system prompt |
| 项目理解 | 需要用户/工具重新探索 | 记忆中已有上次任务摘要 |
| 重复劳动 | 每次重新 glob/grep 了解项目 | 记忆中有上次的发现 |
| 运行费用 OE | 高（重复探索） | 低（记忆复用） |

### 设计要点

- **可选启用**：`memory_path=None`（默认）不启用记忆；传 `--memory .nautilus/memory.md` 启用
- **注入 system prompt**：`system_prompt += "\n\n## 项目记忆\n{memory}"`，LLM 在后续循环中可参考历史记忆
- **自动保存**：任务完成（最终回答）或 max_iter 截断时自动 `append_memory`，保存 prompt + 回答摘要
- **追加而非覆盖**：`append_memory` 追加新条目，保留历史记忆
- **自动建目录**：`save_memory` / `append_memory` 自动创建 `.nautilus/` 目录

## 验证结果

### 单元测试

- ✅ 所有模块导入正常（7 模块，含新增 `memory.py`）
- ✅ CLI `--help` 输出正确（12 参数，含 `--memory`）
- ✅ memory.py 函数验证（load 有/无/空文件 + save 新建/覆盖/建目录 + append 追加/新建/换行/建目录 10 种场景）
- ✅ 记忆集成验证（注入 system prompt / 完成后保存 / 禁用时不操作 3 种场景）
- ✅ 单元测试 175 passed, 0 failed

### E2E 端到端真实场景（Ollama + qwen2.5:7b）

- ✅ 首次运行写入记忆：glob → 回答 → `💾 记忆已保存到 .nautilus/memory.md` → `.nautilus/memory.md` 创建正确（含 prompt + 回答）
- ✅ 第二次运行读取记忆：agent 引用上次任务结果"上次你让我搜索了所有 .py 文件，共有3个.py文件被找到"→ 无需调用工具 → 记忆追加第二次任务
- ✅ 不启用记忆对比：无 `💾` 输出、无 `.nautilus/` 目录创建——可选叠加功能

## 测试覆盖

| 测试模块 | v0.3.2 测试数 | v0.3.3 测试数 | 新增内容 |
|---------|------------|------------|---------|
| `test_memory.py` | 0 | 13 | TestLoadMemory(3) + TestSaveMemory(3) + TestAppendMemory(4) + TestMemoryIntegration(3) |
| `test_cli.py` | 26 | 28 | test_memory_flag(1) + test_memory_default_none(1) |
| `test_agent.py` | 46 | 46 | — |
| `test_tools.py` | 63 | 63 | — |
| `test_llm.py` | 18 | 18 | — |
| **合计** | **160** | **175** | **+15** |

## 使用方式

```bash
cd ".../AIAgent/mycodingagent/nautilus"
pip install -e .
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://xxx   # 可选，OpenAI 兼容 API

# v0.3.3 新增：启用记忆系统（跨会话上下文保持）
nautilus --memory .nautilus/memory.md "分析这个项目的所有文件结构和函数定义"

# 第二次运行，agent 能引用上次的记忆
nautilus --memory .nautilus/memory.md "上次我让你做了什么？"

# 记忆 + plan mode 组合
nautilus --memory .nautilus/memory.md --plan "继续上次的重构任务"

# 不启用记忆（默认行为）
nautilus "创建一个 hello.py，运行它"

# 运行单元测试
PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
```

## 核心洞察

当前 agent 每次运行都是"失忆"的——不记得上次做了什么、项目结构是什么、哪些文件已修改。用户每次需要重新告诉 agent 项目的上下文。

v0.3.3 补齐了这个缺口：agent 启动时自动读取 `.nautilus/memory.md`，将内容注入 system prompt 的"项目记忆"段落；任务完成后自动将本次任务的 prompt + 最终回答摘要追加到记忆文件。下次运行时 agent 能看到历史记忆，实现跨会话上下文保持。

E2E 验证确认：第一次运行后 `.nautilus/memory.md` 被正确创建（含 prompt + 回答）；第二次运行时 agent 无需调用工具即可回答"上次你让我做了什么"——记忆中的"项目记忆"段落提供了足够上下文。记忆系统是 v0.3.4 Skills/插件的基础——Skills 的经验沉淀需要记忆系统做存储。
