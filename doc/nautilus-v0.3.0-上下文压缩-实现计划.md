# Nautilus v0.3.0 上下文压缩 — 实现计划

## Context

v2 已完成并通过 E2E 验证（895 行，6 工具，125 tests + 11 E2E 场景），P0 修复（GBK 编码修复 + bash 危险命令过滤）已随 v2 发布。设计文档（`coding-agent-第一性原理设计方案.md` §五演进路线）定义 v3 演进路线，`nautilus-v3-特性优先级排序.md` 将上下文压缩列为 P1 首要特性。

当前代码基线（v2 含 P0 修复后）：987 行 Python 源码 + 146 tests。

v0.3.0 的目标：**在 ReAct 循环中增加整体上下文预算控制**，打破 context window 次瓶颈（ToC 框架），降低库存（I），为 v0.3.1 子 agent 提供前置依赖。

## 项目位置

```
...\AIAgent\mycodingagent\nautilus\
```

## 问题分析

v2 的 `messages` 列表在 ReAct 循环中无界增长——每轮迭代追加 assistant 消息 + tool 结果消息，10+ 轮后总 token 可能超出 context window。当前只有单条工具结果的截断（`_truncate_for_llm`，默认 6000 字符），没有对整体历史做预算控制。

| 防护层 | 已有 | v0.3.0 新增 |
|--------|------|-----------|
| 单条工具结果截断 | ✅ `_truncate_for_llm(result, 6000)` | — |
| 整体对话历史预算 | ❌ 无 | ✅ `_compress_history(messages, 32000)` |

## 文件清单（4 个文件）

| 文件 | 职责 | 基线行数 | 预估行数 | 变化 |
|------|------|---------|---------|------|
| `nautilus/agent.py` | ReAct 循环 + token 预算控制 + 压缩 | 295 | ~350 | +`_messages_token_estimate` + `_compress_history` + `max_context_tokens` 参数 + 循环调用 |
| `nautilus/__main__.py` | CLI 入口 | 109 | ~118 | +`--max-context-tokens` 参数 |
| `tests/test_agent.py` | agent 测试 | 769 | ~860 | +`TestMessagesTokenEstimate` + `TestCompressHistory` + `TestRunAgentContextCompression` |
| `tests/test_cli.py` | CLI 测试 | 236 | ~250 | +`--max-context-tokens` 参数测试 |

## 各文件实现细节

### 1. `nautilus/agent.py` — 核心修改

**新增 `_messages_token_estimate(messages)` 函数**（~18 行）：

遍历 messages 列表，对每条消息的 `content` + `tool_calls[].function.arguments` 调用已有 `_estimate_tokens()`（line 11-20）。需处理两种消息格式：

- **dict 格式**（text_mode / stream 模式）：`m.get("content", "")` + `m.get("tool_calls", [])`
- **SDK 对象格式**（native 模式）：`getattr(m, "content", "")` + `getattr(m, "tool_calls", None)`

```python
def _messages_token_estimate(messages) -> int:
    """Estimate total tokens across all messages (dict or SDK objects)."""
    total = 0
    for m in messages:
        if isinstance(m, dict):
            total += _estimate_tokens(m.get("content", ""))
            for tc in m.get("tool_calls", []) or []:
                fn = tc.get("function", {})
                total += _estimate_tokens(fn.get("arguments", ""))
        else:
            total += _estimate_tokens(getattr(m, "content", "") or "")
            for tc in getattr(m, "tool_calls", None) or []:
                fn = getattr(tc, "function", None)
                if fn is not None:
                    total += _estimate_tokens(getattr(fn, "arguments", "") or "")
    return total
```

**新增 `_compress_history(messages, max_tokens)` 函数**（~6 行）：

滑动窗口策略——从 index 2 逐条弹出最旧消息（永不丢弃 system index 0 和 user index 1），直到总 token 回到预算以内或只剩 system+user。不做 LLM 总结（避免额外 LLM 调用，尊重 ToC 服从约束）。

```python
def _compress_history(messages, max_tokens: int) -> None:
    """In-place sliding window: drop oldest messages (after system+user)
    until estimated tokens fit the budget. Never touches system/user."""
    while len(messages) > 2 and _messages_token_estimate(messages) > max_tokens:
        messages.pop(2)
```

**安全保证**：`len(messages) > 2` 防止丢弃 system+user，避免无限循环。

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
    max_context_tokens: int = 32000,  # NEW
) -> None:
```

**修改循环体**：

在每轮 LLM 调用前调用 `_compress_history`：

```python
for i in range(max_iter):
    _compress_history(messages, max_context_tokens)  # NEW: 压缩历史
    # ... 后续逻辑不变 ...
```

**预算默认值选择**：

默认 `max_context_tokens = 32000`（~128K context 的保守 25%）。理由：
- deepseek-r1:8b / qwen2.5:7b 广告 131072 context，但 Ollama 默认 `num_ctx` 可能更小
- 32000 留足空间给 LLM 输出/reasoning tokens
- 与已有 `_truncate_for_llm`（单条 6000 字符 ≈ 1500 tokens）形成两层防护

### 2. `nautilus/__main__.py` — CLI 参数

新增 `--max-context-tokens` 参数：

```python
parser.add_argument(
    "--max-context-tokens",
    type=int,
    default=32000,
    help="对话历史的 token 预算（默认 32000，超出后丢弃最旧迭代）。",
)
```

传到 `run_agent`：

```python
run_agent(
    ...
    max_context_tokens=args.max_context_tokens,  # NEW
)
```

### 3. `tests/test_agent.py` — 新增测试

**新增 `TestMessagesTokenEstimate` 类**（4 tests）：

| 测试 | 覆盖场景 |
|------|---------|
| `test_pure_dict_messages` | 纯 dict messages，验证 content token 估算 |
| `test_empty_messages` | 空 messages 列表返回 0 |
| `test_dict_with_tool_calls` | dict 含 tool_calls，验证 arguments 也计入 |
| `test_sdk_like_objects` | SDK 对象（attribute 访问），验证 getattr 路径 |

**新增 `TestCompressHistory` 类**（4 tests）：

| 测试 | 覆盖场景 |
|------|---------|
| `test_no_compression_under_budget` | 未超预算时不压缩，messages 不变 |
| `test_compresses_over_budget` | 超预算时逐条弹出最旧消息 |
| `test_never_drops_system_and_user` | 极小预算时只保留 system+user，不无限循环 |
| `test_empty_history_after_system_user` | 仅剩 system+user 时停止 |

**新增 `TestRunAgentContextCompression` 类**（1 test）：

mock LLM 8 轮迭代 + mock execute_tool 返回大输出（2000 字符/轮），`max_context_tokens=800`。验证：
- 每轮 LLM 调用前 messages 被压缩
- 后续调用的 messages 长度小于早期调用
- 最终 messages 总 token ≤ 预算（或仅剩 system+user）
- system+user 始终保留

### 4. `tests/test_cli.py` — CLI 参数测试

| 测试 | 覆盖场景 |
|------|---------|
| `test_max_context_tokens_flag` | `--max-context-tokens 8000` 传参到 `run_agent(max_context_tokens=8000)` |
| `test_default_max_context_tokens_is_32000` | 不传参时默认 32000 |

## 版本号更新

| 文件 | 变更 |
|------|------|
| `nautilus/__init__.py` | `0.2.0` → `0.3.0` |
| `pyproject.toml` | `version = "0.2.0"` → `version = "0.3.0"` |

## CLI 参数（v0.3.0 完整）

```
$ nautilus "创建一个 hello.py"
$ nautilus --max-context-tokens 8000 "长任务"          # NEW
$ nautilus --stream --max-context-tokens 16000 "复杂任务"
```

参数（v0.3.0 新增 1 个，共 10 个）：
- `prompt`（positional，支持交互式输入）
- `--model`（默认 gpt-4）
- `--api-key`（或 OPENAI_API_KEY 环境变量）
- `--base-url`（或 OPENAI_BASE_URL 环境变量）
- `--max-iter`（默认 20）
- `--max-tool-output`（默认 6000）
- `--max-context-tokens`（默认 32000）**← v0.3.0 新增**
- `--stream`（默认 False）
- `--approval`（默认 False）
- `--text-mode`（默认 False）

## 终端输出格式

压缩是内部机制，不改变终端输出格式。当历史被压缩时，LLM 不再看到最旧的迭代——但用户终端仍能看到完整的执行轨迹（`🔧` 工具调用 + `→` 观察结果 + `✅` 最终回答）。

## 不修改的文件

- `nautilus/llm.py`：不涉及（压缩在 agent 层）
- `nautilus/tools.py`：不涉及（单条工具结果截断保持不变，这是另一层）
- `nautilus/prompts.py`：不涉及
- `pyproject.toml` 依赖列表：无新依赖（复用已有 `_estimate_tokens`）

## 验证方式

1. `pip install -e .` 安装
2. 运行单元测试：
   ```bash
   PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
   ```
3. 预期结果：135 + ~11 新增 = 146 tests 全部通过
4. 验证 agent 能：在长任务（多轮迭代）中自动压缩历史，不因 context window 溢出而失败
