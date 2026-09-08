# Nautilus v2 实现计划

## Context

v1 已完成并通过验收（378 行 Python，4 工具，ReAct 循环，91 tests 全通过）。设计文档（`coding-agent-第一性原理设计方案.md` §五演进路线）定义 v2 目标为"可用"——在 v1 的 MVP 基础上补齐搜索、流式输出、权限审批、.gitignore 感知、错误恢复 5 个功能。

v2 的目标：**~727 行可用的 Python coding agent**（实际 727 行），支持搜索工具、流式输出、权限审批、.gitignore 感知、LLM API 错误重试。

## 项目位置

```
...\AIAgent\mycodingagent\nautilus\
```

## v2 功能清单（5 个功能）

| # | 功能 | 设计文档出处 | 优先级 |
|---|------|------------|--------|
| 1 | Grep/Glob 搜索工具 | 演进路线 + 张力 1（v2 拆出搜索类工具）+ 评估标准 D2.2 | P0 |
| 2 | 错误恢复（LLM API 重试） | 演进路线 + 系统目标 §3.5 | P0 |
| 3 | 流式输出 | 演进路线 + 张力 1 | P1 |
| 4 | 权限审批 | 演进路线 + 张力 2（v2 加 permission prompt） | P1 |
| 5 | .gitignore 感知 | 演进路线 + 评估标准 D3.3 | P2 |

## 实现顺序与依赖关系

```
#1 Grep/Glob (tools.py)     — 独立，无依赖，纯增量
#2 错误恢复 (llm.py)        — 独立，改 agent 核心循环前先做
#3 流式输出 (agent/llm)     — 依赖 #2（稳定循环后再改输出路径）
#4 权限审批 (agent/main)    — 依赖 #2#3（稳定循环后再加审批门）
#5 .gitignore 感知 (tools)  — 依赖 #1（Grep/Glob 存在后才能过滤）
```

## 文件清单（7 个源码文件 + 4 个测试文件）

| 文件 | 职责 | v1 行数 | v2 行数 | 变化 |
|------|------|---------|---------|------|
| `pyproject.toml` | 项目元数据 + 依赖(openai) + CLI 入口 | 16 | 16 | 版本号 0.1.0→0.2.0 |
| `nautilus/__init__.py` | 版本号 | 1 | 1 | 0.1.0→0.2.0 |
| `nautilus/__main__.py` | CLI 入口：argparse 解析参数，调用 agent | 68 | 89 | +`--stream`/`--approval` 参数 |
| `nautilus/prompts.py` | 系统提示词（定义 agent 行为） | 20 | 24 | +glob/grep 工具说明+搜索准则 |
| `nautilus/tools.py` | 6 个工具定义 + 执行路由 + .gitignore 过滤 | 189 | 340 | +glob/grep 函数+schema+路由+_load_gitignore/_is_ignored |
| `nautilus/llm.py` | OpenAI 兼容 API 封装 + 重试 + 流式 | 19 | 125 | +complete_with_retry+stream_complete+辅助类 |
| `nautilus/agent.py` | **核心**：agent 循环（ReAct loop）+ token 预算 + 审批 | 81 | 148 | +stream/approval 参数+审批门+stream 分支 |
| | | **378** | **727** | **+349** |

## 各功能实现细节

### Feature 1: Grep/Glob 搜索工具

**修改文件**：`tools.py`、`prompts.py`

**新增工具 Schema（OpenAI function calling 格式）：**
- `glob(pattern, root?)` — 递归匹配文件路径，用 `pathlib.Path.rglob` + `fnmatch`，cap 200 条，超过截断+标记
- `grep(pattern, path?, root?)` — 在文件中搜索匹配正则的行，返回 `path:lineno:line` 格式，cap 100 条，二进制文件跳过

**新增函数：**
```python
def glob(pattern: str, root: str = ".") -> str:
    """递归匹配文件路径，返回匹配的文件列表（最多 200 条）。"""
    # pathlib.Path.rglob + fnmatch + .gitignore 过滤

def grep(pattern: str, path: str | None = None, root: str = ".") -> str:
    """在文件中搜索匹配指定正则的行，返回 path:lineno:line 格式（最多 100 条）。"""
    # re.compile + 逐文件逐行匹配 + UnicodeDecodeError 跳过二进制
```

**prompts.py 新增：**
- 可用工具列表加 `glob`/`grep` 说明
- 准则："搜索文件或内容时，优先使用 glob/grep 而非 bash grep/find"

### Feature 2: 错误恢复（LLM API 重试）

**修改文件**：`llm.py`、`agent.py`

**llm.py 新增：**
```python
from openai import (
    APIConnectionError, APITimeoutError, RateLimitError,
    InternalServerError, BadRequestError, AuthenticationError,
)

_RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)

def complete_with_retry(client, *, retries: int = 3, stream: bool = False, **kwargs):
    """带指数退避的 LLM API 调用重试。"""
    # 可重试：APIConnectionError, APITimeoutError, RateLimitError, InternalServerError
    # 不可重试：BadRequestError, AuthenticationError（立即抛出）
    # 退避：time.sleep(min(2 ** attempt, 8))
    # 重试时打印 🔄 重试 (第 N 次)...
    # 超过 retries 次 → raise SystemExit
```

**agent.py 修改：**
- `client.chat.completions.create(...)` → `complete_with_retry(client, ...)`

### Feature 3: 流式输出

**修改文件**：`llm.py`、`agent.py`、`__main__.py`

**llm.py 新增：**
```python
class _StreamedMessage:
    """从 streaming chunks 重组的 message 对象。"""
    # content: str
    # tool_calls: list[_StreamedToolCall] | None

class _StreamedToolCall:
    """重组的 tool call，暴露 .id/.function.name/.function.arguments（兼容 agent.py）"""

class _StreamedFunction:
    """重组的 function call"""

def stream_complete(client, *, retries: int = 3, **kwargs):
    """流式调用 LLM，实时打印 content，返回组装好的 message。"""
    # stream=True，遍历 chunks
    # 累积 delta.content → 实时 print(flush=True)
    # 累积 delta.tool_calls → 组装成 _StreamedToolCall 对象
    # 返回 _StreamedMessage（兼容现有 agent.py 循环逻辑）
```

**agent.py 修改：**
- `run_agent()` 新增 `stream: bool = False` 参数
- 循环内分支：`stream=True` → 调 `stream_complete()`；`stream=False` → 原有路径不变
- stream 模式下 content 已实时打印，不重复打印 💭/✅

**__main__.py 新增：**
- `--stream` flag（默认 False）→ 传 `stream=True` 到 `run_agent()`

### Feature 4: 权限审批

**修改文件**：`agent.py`、`__main__.py`

**agent.py 修改：**
- `run_agent()` 新增 `approval: bool = False` 参数
- 循环内 bash 工具执行前审批门：
```python
if approval and call.function.name == "bash":
    user_input = input(f"   执行此命令? [y/N]: ").strip().lower()
    if user_input not in ("y", "yes"):
        result = f"用户拒绝了该命令：{command}"
        messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        continue  # 拒绝 → observation 回灌 LLM 自纠
```
- `approval=False`（默认）→ 不弹 prompt，保持 v1 行为

**__main__.py 新增：**
- `--approval` flag（默认 False）→ 传 `approval=True` 到 `run_agent()`

### Feature 5: .gitignore 感知

**修改文件**：`tools.py`

**新增函数：**
```python
def _load_gitignore(root: str = ".") -> list[str]:
    """读取 .gitignore，返回 pattern 列表。无 .gitignore 则返回空列表。"""
    # 跳过空行和注释行

def _is_ignored(path: str, patterns: list[str]) -> bool:
    """检查路径是否被 gitignore 规则匹配。"""
    # fnmatch 匹配 basename 和路径各段
    # 支持基础模式：*.log, node_modules, dist
    # 不实现完整 gitignore 语义（negation !, ** 等）
```

**tools.py 修改：**
- `glob()` 和 `grep()` 内部调用 `_is_ignored()` 过滤被忽略的文件
- `read_file()` 不加过滤（用户显式指定路径时不过滤）

## 版本号更新

| 文件 | v1 | v2 |
|------|-----|-----|
| `pyproject.toml` | `version = "0.1.0"` | `version = "0.2.0"` |
| `nautilus/__init__.py` | `__version__ = "0.1.0"` | `__version__ = "0.2.0"` |

## CLI 参数（v2 完整）

```
$ nautilus "创建一个 hello.py"
$ nautilus --model qwen-plus --base-url https://xxx "修复 bug"
$ nautilus --max-iter 30 "重构 utils.py"
$ nautilus --stream "实时输出任务"
$ nautilus --approval "需要确认的任务"
$ nautilus --stream --approval "流式+审批"
```

参数：
- `prompt`（positional，支持交互式输入）
- `--model`（默认 gpt-4）
- `--api-key`（或 OPENAI_API_KEY 环境变量）
- `--base-url`（或 OPENAI_BASE_URL 环境变量）
- `--max-iter`（默认 20）
- `--max-tool-output`（默认 6000，约 1500 tokens）
- `--stream`（默认 False，启用流式输出）
- `--approval`（默认 False，启用 bash 命令审批）

## 终端输出格式

```
💭 Agent thinking text...
🔧 read_file("src/main.py")
   → [200 lines of content]
🔧 grep("def hello", root="src")
   → src/main.py:5:def hello():
🔧 bash("python -m pytest")
   执行此命令? [y/N]: y
   → 3 passed, 1 failed
🔄 LLM API 重试 (第 1/3 次)，等待 1s... (RateLimitError)
✅ Final answer summary
```

## 测试文件清单（4 个，34 个新增测试）

| 文件 | v1 测试数 | v2 测试数 | 新增内容 |
|------|---------|---------|---------|
| `tests/test_tools.py` | 36 | 49 | TestGlob(4) + TestGrep(7) + 路由测试(2) + schema count 4→6 |
| `tests/test_agent.py` | 15 | 18 | TestRunAgentApproval(3：拒绝/同意/默认禁用) |
| `tests/test_llm.py` | 10 | 18 | TestCompleteWithRetry(5) + TestStreamComplete(3) |
| `tests/test_cli.py` | 16 | 22 | --stream(2) + --approval(2) + stdin 超时调整 |
| **合计** | **77** | **107** | **+30** |

> **注**：加上 v1 token 预算控制的 14 个测试（v1 后期补充），v2 最终测试数为 **125 个**。

## 验证方式

1. `pip install -e .` 安装
2. 运行单元测试：
   ```bash
   PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
   ```
3. 预期结果：125 passed, 0 failed
4. 设置环境变量 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`
5. 验证 v2 新功能：
   ```bash
   nautilus --stream "创建一个 hello.py，运行它，确认输出 hello world"
   nautilus --approval "运行 ls -la"
   ```
6. 验证 agent 能：读文件、写文件、编辑文件、搜索文件(glob)、搜索内容(grep)、跑命令、流式输出、审批确认、输出最终结果

## 不修改的文件

- `pyproject.toml` 依赖列表：无新依赖（全部用 stdlib：re, pathlib, fnmatch, time）
- `nautilus/tests/__init__.py`：无需改动
