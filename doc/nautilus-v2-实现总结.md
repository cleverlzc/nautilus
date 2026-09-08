# Nautilus v2 实现总结

## 文件清单（实际）

**7 个源码文件 + 4 个测试文件**，位于 `...\AIAgent\mycodingagent\nautilus\`：

| 文件 | v1 行数 | v2 行数 | 职责 |
|------|---------|---------|------|
| `pyproject.toml` | 16 | 16 | 项目元数据 + openai 依赖 + CLI 入口（版本 0.2.0） |
| `nautilus/__init__.py` | 1 | 1 | 版本号（0.2.0） |
| `nautilus/prompts.py` | 20 | 75 | 系统提示词 + glob/grep 工具说明 + 搜索准则 + SYSTEM_PROMPT_TEXT_MODE |
| `nautilus/tools.py` | 189 | 340 | 6 个工具 schema + read/write/edit/glob/grep/bash + execute_tool 路由 + .gitignore 过滤 |
| `nautilus/llm.py` | 19 | 125 | OpenAI 兼容 client 工厂 + complete_with_retry + stream_complete |
| `nautilus/agent.py` | 81 | 241 | **核心 ReAct 循环** + token 预算控制 + stream/approval/text_mode 分支 |
| `nautilus/__main__.py` | 68 | 96 | CLI 入口 + `--stream`/`--approval`/`--text-mode` 参数 |
| **源码合计** | **378** | **878** | |

**总计 878 行 Python 源码**（比 v1 的 378 行增加 500 行，主要是 glob/grep 工具函数、重试+流式封装、审批门逻辑、text-mode 解析器）。

> **注**：v1 后期补充的 token 预算控制（`_estimate_tokens`/`_truncate_for_llm`）已计入 v1 行数。

## v2 新增功能（5 个）

| # | 功能 | 核心实现 |
|---|------|---------|
| 1 | **Grep/Glob 搜索工具** | `tools.py` 新增 `glob()`（pathlib.rglob + fnmatch，cap 200）和 `grep()`（re 搜索，cap 100，跳过二进制）+ 2 个 schema + 路由 |
| 2 | **错误恢复** | `llm.py` 新增 `complete_with_retry()`（指数退避 3 次，可重试 RateLimitError/ConnectionError/TimeoutError/InternalServerError，不可重试 BadRequestError/AuthenticationError） |
| 3 | **流式输出** | `llm.py` 新增 `stream_complete()`（chunk 重组 + 实时 print content）+ `_StreamedMessage`/`_StreamedToolCall` 辅助类；`agent.py` 加 `stream` 参数分支 |
| 4 | **权限审批** | `agent.py` 加 `approval` 参数，bash 执行前 `input("执行此命令? [y/N]")`，拒绝则 observation 回灌 LLM 自纠 |
| 5 | **.gitignore 感知** | `tools.py` 新增 `_load_gitignore()`/`_is_ignored()`，glob/grep 内部自动过滤被忽略文件 |
| 6 | **text-mode 适配** | E2E 测试中发现 deepseek-r1 不支持 function calling，实现 `--text-mode` prompt-based 工具调用：`prompts.py` 新增 `SYSTEM_PROMPT_TEXT_MODE`，`agent.py` 新增 `_parse_tool_calls_from_text()` 解析 ` ```tool_call {json} ` ` 格式 |

## 验证结果

### 单元测试

- ✅ 所有模块导入正常
- ✅ CLI `--help` 输出正确（含 `--stream`/`--approval`/`--text-mode`）
- ✅ 六个工具函数实测可用（write→read roundtrip、edit 精确替换+多处匹配拦截、glob 递归匹配、grep 正则搜索+行号、bash 成功/失败均正确捕获）
- ✅ LLM API 重试机制验证（RateLimitError 重试后成功、BadRequestError 不重试、超限后 SystemExit）
- ✅ 流式输出验证（content 累积 + tool_calls 重组 + 实时打印）
- ✅ 权限审批验证（拒绝→observation 回灌、同意→正常执行、默认禁用不弹 prompt）
- ✅ .gitignore 过滤验证（glob/grep 排除 node_modules/*.log，无 .gitignore 时不过滤）
- ✅ 单元测试 125 passed, 0 failed

### E2E 端到端真实场景（Ollama + deepseek-r1:8b + text-mode）

- ✅ 基础任务：write_file 创建 hello.py → bash 运行 → 输出 hello world → 最终回答
- ✅ Grep/Glob：glob 找到 3 个 .py 文件 → grep 定位 calc.py:4:def divide → 报告结果
- ✅ 流式输出：--stream 实时打印 token → read_file 工具调用 → 最终回答
- ✅ 权限审批（同意）：--approval 弹 prompt → 用户 y → bash 执行成功
- ✅ 权限审批（拒绝）：--approval 弹 prompt → 用户 n → bash 未执行

## 测试覆盖

| 测试模块 | v1 测试数 | v2 测试数 | 新增内容 |
|---------|---------|---------|---------|
| `test_tools.py` | 36 | 49 | TestGlob(4) + TestGrep(7) + 路由(2) + schema 4→6 |
| `test_agent.py` | 15 | 18 | TestRunAgentApproval(3：拒绝/同意/默认禁用) |
| `test_llm.py` | 10 | 18 | TestCompleteWithRetry(5) + TestStreamComplete(3) |
| `test_cli.py` | 16 | 22 | --stream(2) + --approval(2) + stdin 超时调整 |
| **合计** | **77** | **107** | **+30** |

> 加上 v1 后期补充的 token 预算 14 个测试（TestEstimateTokens 6 + TestTruncateForLlm 5 + TestRunAgentTokenBudget 1 + CLI 2），v2 最终测试数为 **125 个**。

## 使用方式

```bash
cd ".../AIAgent/mycodingagent/nautilus"
pip install -e .
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://xxx   # 可选，OpenAI 兼容 API

# v1 基础用法（完全兼容）
nautilus "创建一个 hello.py，运行它，确认输出 hello world"

# v2 新增：流式输出
nautilus --stream "解释这个项目的架构"

# v2 新增：权限审批（bash 命令执行前需确认）
nautilus --approval "运行 rm -rf build/"

# v2 新增：组合使用
nautilus --stream --approval "修复 src/calculator.py 中的除法 bug，然后跑测试"

# v2 新增：text-mode（兼容不支持 function calling 的模型）
OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
nautilus --model deepseek-r1:8b --text-mode "创建一个 hello.py，运行它"

# 运行单元测试
PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
```

## 核心洞察

v1 验证了 agent 的不可约本质——**LLM + 4 个工具 + 一个 while 循环**。

v2 在此基础上补齐了"可用"的 5 个工程化能力 + 1 个 E2E 适配：搜索工具让 LLM 用更少 token 表达意图（挖尽瓶颈），错误恢复让 agent 不因网络抖动崩溃（提升鲁棒性），流式输出降低用户感知延迟（降低监督 OE），权限审批为 bash 危险命令加人类确认（安全兜底），.gitignore 感知避免垃圾文件污染上下文（控制库存），text-mode 适配让 agent 兼容任何 LLM（不限 function calling）。

E2E 端到端真实场景验证（Ollama + deepseek-r1:8b）确认 agent 在真实 LLM 下正确工作——ReAct 循环、工具调用、流式输出、权限审批全部通过。

Claude Code 的 51 万行是在这 878 行之上继续叠加多 agent / 上下文压缩 / MCP 协议 / 记忆系统 / Skills 插件的工程化。
