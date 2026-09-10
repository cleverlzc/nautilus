# Nautilus v0.3.1 子 agent（上下文隔离）— 实现总结

## 文件清单（实际）

**7 个源码文件 + 4 个测试文件**，位于 `...\AIAgent\mycodingagent\nautilus\`：

| 文件 | v0.3.0 行数 | v0.3.1 行数 | 职责 |
|------|------------|------------|------|
| `pyproject.toml` | 16 | 16 | 项目元数据 + openai 依赖 + CLI 入口（版本 0.3.1） |
| `nautilus/__init__.py` | 1 | 1 | 版本号（0.3.1） |
| `nautilus/prompts.py` | 75 | 99 | 系统提示词 + SYSTEM_PROMPT_TEXT_MODE + **SYSTEM_PROMPT_SUBAGENT** + 准则 7 + delegate_task 工具说明 |
| `nautilus/tools.py` | 382 | 399 | 7 个工具 schema + execute_tool 路由 + .gitignore 过滤 + 危险命令过滤（**+delegate_task schema**） |
| `nautilus/llm.py` | 125 | 125 | OpenAI 兼容 client 工厂 + complete_with_retry + stream_complete |
| `nautilus/agent.py` | 295 | 383 | **核心 ReAct 循环** + token 预算控制 + stream/approval/text_mode 分支 + 上下文压缩 + **子 agent（run_subagent + delegate_task 处理）** |
| `nautilus/__main__.py` | 109 | 109 | CLI 入口 + GBK 编码修复 + 10 个参数（无新增） |
| **源码合计** | **987** | **1116** | |

**总计 1116 行 Python 源码**（v0.3.1 新增约 129 行源码 + 9 个测试，主要是 `run_subagent()` 函数 + `delegate_task` 处理分支 + `_print_tool_call` 格式化 + `SYSTEM_PROMPT_SUBAGENT` + `delegate_task` schema）。

## v0.3.1 新增功能（1 个）

| # | 功能 | 核心实现 |
|---|------|---------|
| 1 | **子 agent（上下文隔离）** | `agent.py` 新增 `run_subagent()` 函数（~55 行）：独立 messages 列表 + 独立 ReAct 循环 + 只返回最终结果字符串 + 禁止递归 delegate_task。`run_agent()` 循环内新增 `delegate_task` 处理分支：检测到 `delegate_task` 工具调用时调用 `run_subagent()`，子 agent 结果回灌主循环。`tools.py` 新增 `delegate_task` schema（7 工具）。`prompts.py` 新增准则 7 + `SYSTEM_PROMPT_SUBAGENT` 子 agent 提示词 |

### 上下文隔离机制

| 维度 | 无子 agent | 有子 agent |
|------|-----------|-----------|
| 主循环 messages 增长 | 子任务每轮迭代 +2 条 | 子任务完成 +1 条（仅结果） |
| 上下文隔离 | ❌ 子任务中间步骤污染主循环 | ✅ 独立 messages 列表 |
| 压缩依赖 | 依赖压缩丢弃旧消息 | 子 agent 内部自行压缩 |

### 设计要点

- **独立 messages**：子 agent 使用独立 messages 列表，与主 agent 完全隔离
- **只返回结果**：子 agent 完成后只返回最终回答字符串，中间工具调用步骤不回灌主循环
- **禁止递归**：子 agent 调用 `delegate_task` 时返回错误字符串，不递归调用 `run_subagent()`
- **复用基础设施**：子 agent 复用 `_compress_history` + `execute_tool` + `complete_with_retry`，不支持 stream/approval/plan_mode
- **SYSTEM_PROMPT_SUBAGENT**：简化版系统提示词，不含 delegate_task 工具（禁止递归），不含"完成后给摘要"准则

## 验证结果

### 单元测试

- ✅ 所有模块导入正常
- ✅ CLI `--help` 输出正确（10 参数，无新增）
- ✅ 子 agent 验证（返回最终回答 / 独立 messages / max_iter 截断 3 种场景）
- ✅ delegate_task 集成验证（主 agent 调用 delegate_task / 主循环不被污染 / 子 agent 拒绝递归 3 种场景）
- ✅ TOOL_SCHEMAS 更新验证（6→7，含 delegate_task schema 结构）
- ✅ 单元测试 155 passed, 0 failed

### E2E 端到端真实场景（Ollama + qwen2.5:7b）

- ✅ 基础委派：主 agent 调用 delegate_task → 子 agent 独立 read_file → 返回函数数量 → 主 agent 引用子结果
- ✅ 多步子任务：主 agent 调用 delegate_task → 子 agent 独立 glob+grep → 返回函数统计 → 主 agent 总结
- ✅ 对比验证：用 delegate_task 主循环 2 次迭代 vs 不用 3 次迭代——上下文隔离生效

## 测试覆盖

| 测试模块 | v0.3.0 测试数 | v0.3.1 测试数 | 新增内容 |
|---------|------------|------------|---------|
| `test_agent.py` | 37 | 43 | TestRunSubagent(3) + TestDelegateTask(3) |
| `test_tools.py` | 58 | 63 | TestToolSchemas 更新：schema count 6→7 + delegate_task params/required/description |
| `test_cli.py` | 24 | 24 | — |
| `test_llm.py` | 18 | 18 | — |
| **合计** | **146** | **155** | **+9** |

## 使用方式

```bash
cd ".../AIAgent/mycodingagent/nautilus"
pip install -e .
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://xxx   # 可选，OpenAI 兼容 API

# v0.3.1 新增：子 agent 上下文隔离（LLM 自行决定何时委派）
nautilus "分析这个项目的所有文件结构和函数定义"

# 显式引导 LLM 使用 delegate_task
nautilus "用 delegate_task 委派子 agent 搜索所有 .py 文件并分析每个文件的函数数量"

# 组合使用
nautilus --stream --max-context-tokens 16000 "复杂任务，需要多步搜索和修改"

# 运行单元测试
PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
```

## 核心洞察

v0.3.0 的 `_compress_history` 通过丢弃旧消息控制上下文——但复杂子任务（如"搜索所有包含 X 的文件并读取内容"）本身可能需要 5-10 轮迭代，全部在主循环执行会迅速膨胀 messages。即使压缩，主 agent 也丢失了子任务的中间结果。

v0.3.1 补齐了这个缺口：主 agent 只需 1 次 `delegate_task` 工具调用，子任务的多步 ReAct 循环在子 agent 的独立 messages 中完成，主 agent 只接收最终结果字符串——1 条消息而非 10+ 条。这形成了**两层上下文控制**——单条截断 + 整体压缩（v0.3.0）+ 上下文隔离（v0.3.1）。

E2E 对比验证确认：用 `delegate_task` 主循环 2 次迭代 vs 不用 3 次迭代——子 agent 的 glob+grep 中间步骤完全隔离，主循环上下文不膨胀。子 agent 是 v0.3.2 plan mode 的基础——plan mode 生成的计划步骤可以委派子 agent 逐步执行。
