# Nautilus v0.3.0 上下文压缩 — 实现总结

## 文件清单（实际）

**7 个源码文件 + 4 个测试文件**，位于 `...\AIAgent\mycodingagent\nautilus\`：

| 文件 | v2 行数 | v0.3.0 行数 | 职责 |
|------|---------|------------|------|
| `pyproject.toml` | 16 | 16 | 项目元数据 + openai 依赖 + CLI 入口（版本 0.3.0） |
| `nautilus/__init__.py` | 1 | 1 | 版本号（0.3.0） |
| `nautilus/prompts.py` | 75 | 75 | 系统提示词 + SYSTEM_PROMPT_TEXT_MODE |
| `nautilus/tools.py` | 382 | 382 | 6 个工具 + execute_tool 路由 + .gitignore 过滤 + 危险命令过滤 |
| `nautilus/llm.py` | 125 | 125 | OpenAI 兼容 client 工厂 + complete_with_retry + stream_complete |
| `nautilus/agent.py` | 259 | 295 | **核心 ReAct 循环** + token 预算控制 + stream/approval/text_mode 分支 + **上下文压缩** |
| `nautilus/__main__.py` | 100 | 109 | CLI 入口 + GBK 编码修复 + 10 个参数（含 `--max-context-tokens`） |
| **源码合计** | **895+P0** | **987** | |

> **注**：v2 后期补充的 P0 修复（GBK 编码修复 + bash 危险命令过滤）已计入 v2 行数。v0.3.0 的增量全部来自上下文压缩功能。

**总计 987 行 Python 源码**（v0.3.0 新增约 36 行源码 + 11 个测试，主要是 `_messages_token_estimate` + `_compress_history` + `max_context_tokens` 参数 + `--max-context-tokens` CLI 参数）。

## v0.3.0 新增功能（1 个）

| # | 功能 | 核心实现 |
|---|------|---------|
| 1 | **上下文压缩** | `agent.py` 新增 `_messages_token_estimate()`（18 行）：遍历 messages，对每条消息的 content + tool_calls arguments 调用已有 `_estimate_tokens()`，处理 dict 和 SDK 对象两种格式。新增 `_compress_history()`（6 行）：滑动窗口从 index 2 逐条弹出最旧消息，直到预算达标或只剩 system+user。`run_agent()` 新增 `max_context_tokens: int = 32000` 参数，循环体开头调用 `_compress_history`。`__main__.py` 新增 `--max-context-tokens` CLI 参数 |

### 两层 token 防护

| 防护层 | 函数 | 作用 | 默认值 |
|--------|------|------|--------|
| 单条工具结果截断 | `_truncate_for_llm(result, max_chars)` | 截断单个工具调用的返回结果 | 6000 字符（~1500 tokens） |
| 整体对话历史预算 | `_compress_history(messages, max_tokens)` | 丢弃最旧迭代，控制 messages 总 token | 32000 tokens |

### 设计要点

- **策略**：滑动窗口丢弃最旧迭代（不做 LLM 总结，避免额外 LLM 调用——尊重 ToC 服从约束）
- **安全保证**：`len(messages) > 2` 防止丢弃 system+user，避免无限循环
- **模式兼容**：`_messages_token_estimate` 同时处理 dict（text_mode/stream）和 SDK 对象（native）两种消息格式
- **预算选择**：默认 32000 tokens（~128K context 的保守 25%），`--max-context-tokens` 可配

## 验证结果

- ✅ 所有模块导入正常
- ✅ CLI `--help` 输出正确（含 `--max-context-tokens`）
- ✅ token 估算验证（纯 dict / 空 / dict+tool_calls / SDK 对象 4 种场景）
- ✅ 历史压缩验证（未超预算不压缩 / 超预算逐条弹出 / 永不丢弃 system+user / 仅剩 system+user 停止 4 种场景）
- ✅ ReAct 循环集成验证（mock LLM 8 轮迭代 + 大输出，messages 被压缩到预算以内）
- ✅ CLI 参数验证（`--max-context-tokens 8000` 传参 + 默认值 32000）
- ✅ 单元测试 146 passed, 0 failed

## 测试覆盖

| 测试模块 | v2 测试数 | v0.3.0 测试数 | 新增内容 |
|---------|---------|------------|---------|
| `test_agent.py` | 28 | 37 | TestMessagesTokenEstimate(4) + TestCompressHistory(4) + TestRunAgentContextCompression(1) |
| `test_cli.py` | 22 | 24 | test_max_context_tokens_flag(1) + test_default_max_context_tokens_is_32000(1) |
| `test_tools.py` | 58 | 58 | — |
| `test_llm.py` | 18 | 18 | — |
| **合计** | **135** | **146** | **+11** |

> **注**：v2 后期补充的 P0 修复新增 10 个测试（TestDangerousCommandFilter(9) + test_help_without_encoding_override(1)），已计入 v2 测试数。

## 使用方式

```bash
cd ".../AIAgent/mycodingagent/nautilus"
pip install -e .
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://xxx   # 可选，OpenAI 兼容 API

# v0.3.0 新增：上下文压缩（默认 32000 tokens，无需额外参数）
nautilus "创建一个 hello.py，运行它，确认输出 hello world"

# v0.3.0 新增：调整上下文预算
nautilus --max-context-tokens 8000 "长任务，多轮迭代"

# 组合使用
nautilus --stream --approval --max-context-tokens 16000 "复杂任务"

# text-mode + 上下文压缩
nautilus --model deepseek-r1:8b --text-mode --max-context-tokens 4000 "创建文件"

# 运行单元测试
PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
```

## 核心洞察

v2 的 `_truncate_for_llm` 只管单条工具结果——一次 `read_file` 读取大文件，截断到 6000 字符就结束了。但整个 `messages` 列表在 10+ 轮迭代后累积的总 token 无人看管——这是 ToC 框架中的"次瓶颈"（context window），长任务会因历史膨胀失败。

v0.3.0 补齐了这个缺口：`_compress_history` 在每轮 LLM 调用前检查 `messages` 总 token，超预算时从最旧迭代开始丢弃，永不触碰 system+user。这形成了**两层 token 防护**——单条截断 + 整体预算——让 agent 在长任务中不会因 context window 溢出而崩溃。

不做 LLM 总结（避免额外 LLM 调用——尊重 ToC 服从约束），滑动窗口是最简正确实现。上下文压缩是 v0.3.1 子 agent 的前置依赖——子 agent 的独立 messages 列表也需要压缩来控制上下文。
