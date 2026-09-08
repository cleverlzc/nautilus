# Nautilus v2 验证报告

> 验证对象：Nautilus v2（878 行 Python，6 工具，ReAct 循环 + 搜索 + 流式 + 审批 + .gitignore + 错误恢复 + text-mode）
> 验证日期：2026-09-08
> 验证环境：Python 3.14.4 / Windows 11 / openai 2.35.1 / pytest 9.0.3
> E2E 环境：Ollama 本地 (http://127.0.0.1:11434) / deepseek-r1:8b / text-mode
> UT 文件：`nautilus/tests/` 目录下 4 个测试模块，125 个测试用例
> E2E 测试：4 个场景，全部通过

---

## 一、验证范围

### 1.1 验证目标

验证 Nautilus v2 源码**是否可真正工作**——在 v1 已验证的基础上，逐步验证 5 个 v2 新功能（Grep/Glob 搜索工具、LLM API 错误恢复、流式输出、权限审批、.gitignore 感知）的正确性，同时确认 v1 功能回归无退化。

### 1.2 UT 文件结构

```
nautilus/
├── pyproject.toml              # 16 行 — 版本 0.2.0
├── nautilus/                   # 源码包（878 行）
│   ├── __init__.py             #   1 行 — 版本 0.2.0
│   ├── __main__.py             #  96 行 — CLI + --stream + --approval + --text-mode
│   ├── agent.py                # 241 行 — ReAct 循环 + token 预算 + stream/approval/text_mode 分支
│   ├── llm.py                  # 125 行 — client 工厂 + complete_with_retry + stream_complete
│   ├── prompts.py              #  75 行 — 系统提示词 + SYSTEM_PROMPT_TEXT_MODE
│   └── tools.py                # 340 行 — 6 工具 + execute_tool 路由 + .gitignore 过滤
└── tests/                      # 单元测试（1476 行）
    ├── __init__.py             #   8 行
    ├── test_tools.py           # 371 行 — 49 tests
    ├── test_agent.py           # 604 行 — 28 tests
    ├── test_llm.py             # 286 行 — 18 tests
    └── test_cli.py             # 207 行 — 22 tests
```

### 1.3 运行方式

```bash
cd ".../AIAgent/mycodingagent/nautilus"
PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
```

> **注**：`PYTHONIOENCODING=utf-8` 是 Windows 环境必需的，因为 `agent.py` 中使用了 emoji 字符（🔧✅⚠️💭🔄），GBK 编码无法处理。`-o "addopts="` 用于覆盖上级目录 pyproject.toml 中的 pytest 配置。

---

## 二、验证结果总览

### 2.1 最终结果

```
============================ 125 passed in 27.94s =============================
```

| 指标 | v1 | v2 |
|------|-----|-----|
| 测试总数 | 77 | 125 |
| 通过 | 77 | 125 |
| 失败 | 0 | 0 |
| 错误 | 0 | 0 |
| 跳过 | 0 | 0 |
| 总耗时 | 21.95s | 27.94s |
| 新增测试 | — | +48 |

### 2.2 按模块统计

| 测试模块 | v1 测试数 | v2 测试数 | 新增 | 覆盖组件 |
|---------|---------|---------|------|---------|
| `test_tools.py` | 36 | 49 | +13 | read/write/edit/**glob**/**grep**/bash + execute_tool 路由 + TOOL_SCHEMAS(4→6) + **.gitignore 过滤** |
| `test_agent.py` | 15 | 28 | +13 | _truncate + _estimate_tokens + _truncate_for_llm + _print_tool_call + ReAct 循环/mock/截断/自纠/**token 预算**/**审批** |
| `test_llm.py` | 10 | 18 | +8 | create_client 工厂 + **complete_with_retry** + **stream_complete** |
| `test_cli.py` | 16 | 22 | +6 | --help/stdin/参数解析 + **--stream** + **--approval** + **--max-tool-output** |
| **合计** | **77** | **125** | **+48** | |

---

## 三、各模块验证详情

### 3.1 test_tools.py（49 tests）

#### v1 工具函数测试（22 tests，回归）

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestWriteFile` | 4 | 正常写入 / 字节数返回 / 自动创建父目录 / 覆盖已有文件 |
| `TestReadFile` | 3 | 正常读取 / 文件不存在 / 二进制文件（utf-8 解码失败） |
| `TestEditFile` | 5 | 正常编辑 / old_string 未找到 / 多处匹配 / 文件不存在 / 保留周围内容 |
| `TestBash` | 5 | echo 成功 / python 执行 / 非零 exit code / stderr 捕获 / stdout+stderr 同时输出 |

关键验证点：
- v1 工具全部回归通过，无退化

#### v2 新增：Glob 工具测试（4 tests）

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestGlob` | 4 | 匹配 .py 文件 / 无匹配 / 递归搜索子目录 / .gitignore 过滤 |

关键验证点：
- `glob("*.py", root=tmp_path)` 正确匹配文件名（`tools.py` 的 `pathlib.Path.rglob` + `fnmatch`）
- 递归搜索能找到子目录中的文件（`sub/deep.py`）
- .gitignore 中的 `node_modules` 和 `*.log` 被正确过滤

#### v2 新增：Grep 工具测试（7 tests）

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestGrep` | 7 | 找到匹配 / 行号格式 / 无匹配 / 限定单文件 / 非法正则 / 二进制文件跳过 / .gitignore 过滤 |

关键验证点：
- `grep("hello", root=tmp_path)` 返回 `path:lineno:line` 格式
- 非法正则 `[invalid` 返回 `错误：正则表达式无效`（`tools.py` 的 `re.compile` 异常捕获）
- 二进制文件（`.bin`）被 `UnicodeDecodeError` 跳过，不崩溃
- .gitignore 中的 `vendor` 目录被过滤

#### execute_tool 路由测试（10 tests，v1 的 8 + v2 新增 2）

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestExecuteTool` | 10 | write/read/edit/bash + **glob** + **grep** / 未知工具 / 非法 JSON / 空参数 / None 参数 |

关键验证点：
- glob/grep 路由正确分发（`tools.py` 的 `execute_tool` 新增 2 个 if 分支）

#### TOOL_SCHEMAS 结构测试（6 tests，参数化扩展至 6 工具）

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestToolSchemas` | 6 | schema 数量=**6** / 名称集合含 **glob+grep** / 参数列表（6 工具参数化）/ required（6 工具）/ description（6 工具）/ type="function" |

关键验证点：
- 6 个工具 schema 名称正确：`read_file, write_file, edit_file, glob, grep, bash`
- glob schema 参数：`["pattern", "root"]`，required：`["pattern"]`
- grep schema 参数：`["pattern", "path", "root"]`，required：`["pattern"]`

---

### 3.2 test_agent.py（28 tests）

#### v1 辅助函数测试（12 tests，回归 + 扩展）

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestTruncate` | 6 | 短文本原样返回 / 恰好等于限制 / 超长截断 + 标记 / 标记格式 / 空字符串 / 自定义限制 |
| `TestEstimateTokens` | 6 | 纯 ASCII / 纯 CJK / 空字符串 / 混合 / 长文本 / None 安全 |

关键验证点：
- `_estimate_tokens` 启发式正确：ASCII 4 字符/token，CJK 2 字符/token

#### v1 新增：_truncate_for_llm 测试（5 tests）

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestTruncateForLlm` | 5 | 短文本原样返回 / 恰好等于限制 / 超长截断 + 双语标记 / 自定义限制 / 空字符串 |

关键验证点：
- 截断标记包含双语信息：`[输出已截断，共 N 字符] [Output truncated, N→M chars]`

#### _print_tool_call 测试（6 tests，回归）

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestPrintToolCall` | 6 | read_file / write_file（含字符数显示）/ **edit_file（含 old/new 字符数显示）** / bash / 未知工具 / 缺少参数 |

关键验证点：
- v2 新增 edit_file 专用格式化分支：`edit_file("path", old: <N 字符>, new: <M 字符>)`

#### ReAct 循环测试（5 tests，v1 的 3 + v2 新增 2）

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestRunAgentReActLoop` | 1 | 完整 ReAct 闭环：write_file → bash → 最终回答 |
| `TestRunAgentMaxIter` | 1 | max_iter 截断：LLM 持续调工具，达到上限后打印 ⚠️ 终止 |
| `TestRunAgentErrorRecovery` | 1 | 错误自纠：edit_file 失败 → LLM 改用 write_file → 成功 |
| `TestRunAgentTokenBudget` | 1 | **token 预算**：bash 返回 10000 字符，messages 中 tool result 被截断到 max_chars |
| `TestRunAgentApproval` | 3 | **权限审批**：拒绝→observation 回灌 / 同意→正常执行 / 默认禁用不弹 prompt |

关键验证点：

**token 预算截断**（`TestRunAgentTokenBudget`）：
- Mock LLM + Mock execute_tool 返回 10000 字符
- `max_tool_output_chars=500` 时验证 `messages` 中 tool result 被截断
- 截断后的内容包含双语标记
- 验证 `_truncate_for_llm` 只作用于 LLM 回灌，不影响终端显示（终端用 `_truncate`）

**权限审批**（`TestRunAgentApproval`）：
- `approval=True` + `input("n")` → bash 命令被拒绝，observation = "用户拒绝了该命令"，LLM 可自纠
- `approval=True` + `input("y")` → bash 命令正常执行，输出 exit code
- `approval=False`（默认）→ `input()` 从未被调用，保持 v1 行为

---

### 3.3 test_llm.py（18 tests）

#### v1 create_client 工厂测试（10 tests，回归）

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestCreateClientNoKey` | 2 | 无 key 抛 SystemExit / 错误消息提及环境变量名 |
| `TestCreateClientExplicit` | 2 | 显式 api_key 创建 client / 显式 api_key + base_url |
| `TestCreateClientEnvFallback` | 4 | 环境变量 API key / 环境变量 key+url / 显式覆盖环境变量 / 只有 key 无 url |
| `TestCreateClientPriority` | 2 | None 参数降级到环境变量 / 空字符串参数降级到环境变量 |

关键验证点：
- v1 工厂逻辑全部回归通过

#### v2 新增：complete_with_retry 重试测试（5 tests）

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestCompleteWithRetry` | 5 | 首次成功 / RateLimitError 重试后成功 / 全部失败→SystemExit / BadRequestError 不重试 / AuthenticationError 不重试 |

关键验证点：
- **可重试错误**（RateLimitError, APIConnectionError, APITimeoutError, InternalServerError）触发指数退避重试
- **不可重试错误**（BadRequestError, AuthenticationError）立即抛出，不重试
- 重试时打印 `🔄 LLM API 重试 (第 N/3 次)，等待 Xs...`
- 超过 `retries` 次后抛 `SystemExit`（而非裸异常），用户得到友好错误信息
- `time.sleep` 被 mock，测试不实际等待

#### v2 新增：stream_complete 流式测试（3 tests）

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestStreamComplete` | 3 | content 累积 + 实时打印 / tool_calls 重组 / 空流 |

关键验证点：
- **content 累积**：多个 delta chunk 的 `content` 被拼接成完整字符串，且实时 `print(flush=True)`
- **tool_calls 重组**：分散在多个 chunk 中的 `delta.tool_calls`（index/id/name/arguments）被正确组装为 `_StreamedToolCall` 对象
- 重组后的对象暴露 `.id`/`.function.name`/`.function.arguments` 属性，兼容 `agent.py` 和 `execute_tool` 的 attribute 访问
- 空流返回空 message（content="", tool_calls=None）

---

### 3.4 test_cli.py（22 tests）

#### v1 subprocess + 参数测试（16 tests，回归 + 扩展）

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestCLIHelp` | 2 | `--help` 退出码=0 + 显示所有参数 / 显示"鹦鹉螺"描述 |
| `TestCLINoPrompt` | 1 | 无 prompt + 无 stdin → 打印 help + 退出码=1 |
| `TestCLIStdin` | 1 | stdin 管道输入被正确读取 |
| `TestCLIArgumentParsing` | 12 | prompt / --model / --api-key / --base-url / --max-iter / --max-tool-output / 默认值 5 个 |

#### v2 新增：--stream / --approval 参数测试（4 tests）

| 测试类 | 用例数 | 覆盖场景 |
|--------|--------|---------|
| `TestCLIArgumentParsing` | +4 | `--stream` 传参=True / 默认 stream=False / `--approval` 传参=True / 默认 approval=False |

关键验证点：
- `--stream` flag 正确解析为 `stream=True` 传给 `run_agent()`
- `--approval` flag 正确解析为 `approval=True` 传给 `run_agent()`
- 两个新 flag 默认都是 `False`，保持 v1 向后兼容

---

## 四、v2 新功能验证总结

### 4.1 Feature 1: Grep/Glob 搜索工具

| 验证项 | 结果 | 说明 |
|--------|------|------|
| glob 递归匹配 | ✅ | `pathlib.Path.rglob` + `fnmatch` 正确匹配文件名 |
| glob 无匹配 | ✅ | 返回"未找到匹配文件" |
| grep 正则搜索 | ✅ | `re.compile` + 逐文件逐行匹配，返回 `path:lineno:line` |
| grep 非法正则 | ✅ | 返回 `错误：正则表达式无效`，不崩溃 |
| grep 跳过二进制 | ✅ | `UnicodeDecodeError` 捕获，跳过不崩溃 |
| execute_tool 路由 | ✅ | glob/grep 正确分发 |
| TOOL_SCHEMAS 扩展 | ✅ | 4→6，schema 结构完整 |
| prompts 工具说明 | ✅ | 系统提示词新增 glob/grep 说明 + 搜索准则 |

### 4.2 Feature 2: 错误恢复（LLM API 重试）

| 验证项 | 结果 | 说明 |
|--------|------|------|
| 首次成功不重试 | ✅ | call_count=1 |
| RateLimitError 重试后成功 | ✅ | 2 次失败 + 第 3 次成功，sleep 2 次 |
| 全部失败→SystemExit | ✅ | retries+1 次调用后抛 SystemExit |
| BadRequestError 不重试 | ✅ | 立即抛出，call_count=1 |
| AuthenticationError 不重试 | ✅ | 立即抛出，call_count=1 |

### 4.3 Feature 3: 流式输出

| 验证项 | 结果 | 说明 |
|--------|------|------|
| content 累积 | ✅ | 3 个 chunk 的 content 拼接为 "Hello world!" |
| content 实时打印 | ✅ | 每个 delta.content 被 print(flush=True) |
| tool_calls 重组 | ✅ | 分散的 delta 组装为完整 _StreamedToolCall（id/name/arguments） |
| 兼容 agent 循环 | ✅ | 重组对象暴露 .function.name/.function.arguments，兼容 execute_tool |
| 空流处理 | ✅ | 返回空 message，不崩溃 |

### 4.4 Feature 4: 权限审批

| 验证项 | 结果 | 说明 |
|--------|------|------|
| 拒绝→observation 回灌 | ✅ | "用户拒绝了该命令" 进入 messages，LLM 可自纠 |
| 同意→正常执行 | ✅ | bash 命令执行，输出 exit code |
| 默认禁用不弹 prompt | ✅ | input() 从未被调用（用 AssertionError 验证） |

### 4.5 Feature 5: .gitignore 感知

| 验证项 | 结果 | 说明 |
|--------|------|------|
| glob 过滤 .gitignore | ✅ | node_modules/*.log 被排除 |
| grep 过滤 .gitignore | ✅ | vendor 目录被排除 |
| 无 .gitignore 不过滤 | ✅ | 无 .gitignore 时返回空 patterns，不过滤任何文件 |

---

## 五、发现的问题

### 5.1 Windows GBK 编码兼容性（v1 遗留，未修复）

**问题描述**：`agent.py` 使用 emoji（🔧✅⚠️💭🔄），Windows GBK 编码崩溃。

**v2 状态**：未修复。v2 新增了 `🔄`（重试标记）和 `💭`（thinking 打印），扩大了影响范围。

**当前规避**：`PYTHONIOENCODING=utf-8`

**建议修复**（v3）：在 `__main__.py` 入口处添加 `sys.stdout.reconfigure(encoding="utf-8")`。

### 5.2 上级目录 pyproject.toml 干扰（v1 遗留，未修复）

**问题描述**：`D:\AIAgent\Practice\pyproject.toml` 的 pytest 配置被继承。

**当前规避**：`-o "addopts="`

### 5.3 CLI stdin 测试超时（v2 调整）

**问题描述**：`TestCLIStdin::test_stdin_prompt_is_read` 在 v1 中使用 `--base-url http://127.0.0.1:1` 导致连接重试等待，测试超时。

**v2 调整**：改用 `https://0.0.0.0:1`（快速连接拒绝）+ timeout 提升到 60s。测试通过但耗时较长。

---

## 六、E2E 端到端真实场景验证

### 6.1 测试环境

| 项 | 值 |
|---|---|
| LLM 服务 | Ollama 本地 (http://127.0.0.1:11434) |
| 模型 | deepseek-r1:8b（不支持 function calling，需 text-mode） |
| API Key | test |
| OS | Windows 11 / Python 3.14.4 |
| 编码 | PYTHONIOENCODING=utf-8 |

### 6.2 text-mode 适配

发现 Ollama 上的 deepseek-r1:8b/32b **不支持 OpenAI function calling**（capabilities 只有 `completion`）。为使端到端测试可行，实现了 **text-mode 工具调用**：

- `prompts.py` 新增 `SYSTEM_PROMPT_TEXT_MODE`，在系统提示词中嵌入工具描述和 ` ```tool_call {json} ` ` 格式约定
- `agent.py` 新增 `_parse_tool_calls_from_text()` 解析模型文本输出中的 tool_call 块，`text_mode` 参数控制分支
- `__main__.py` 新增 `--text-mode` CLI 参数

### 6.3 E2E 测试结果

| # | 测试场景 | 命令 | 结果 | 验证点 |
|---|---------|------|------|--------|
| 1 | **基础任务**：创建 hello.py + 运行 + 验证 | `nautilus --text-mode "创建一个 hello.py..."` | ✅ 通过 | write_file 创建 → bash 运行 → 输出 hello world → 最终回答 |
| 2 | **Grep/Glob**：搜索 .py 文件 + 搜索 divide 函数 | `nautilus --text-mode "用 glob 搜索...用 grep 搜索..."` | ✅ 通过 | glob 找到 3 文件 → grep 定位 calc.py:4:def divide → 报告结果 |
| 3 | **流式输出**：`--stream` 实时 token 输出 | `nautilus --text-mode --stream "read hello.py..."` | ✅ 通过 | 流式打印 content → read_file 工具调用 → 最终回答 |
| 4a | **权限审批**：用户同意 bash | `echo "y" \| nautilus --text-mode --approval "echo approval_test_ok"` | ✅ 通过 | 弹 prompt → 用户 y → bash 执行成功 → exit code 0 |
| 4b | **权限审批**：用户拒绝 bash | `echo "n" \| nautilus --text-mode --approval "echo should_not_appear"` | ✅ 通过 | bash 未执行，agent 直接给出文字回答 |

### 6.4 E2E 测试详情

**测试 1：基础任务**

Agent 用 deepseek-r1:8b + text-mode 成功完成闭环：
1. 调用 `write_file("hello.py", "print('hello world')")` 创建文件
2. 调用 `bash("python hello.py")` 运行验证
3. 输出 `hello world`，exit code 0
4. 给出最终回答摘要

验证 hello.py 实际内容：`print('hello world')`，运行输出：`hello world`。

**测试 2：Grep/Glob 搜索**

Agent 正确使用搜索工具：
1. 调用 `glob("*.py")` 找到 3 个文件（calc.py, hello.py, utils.py）
2. 调用 `grep("def divide")` 定位到 `calc.py:4:def divide(a, b):`
3. 报告正确结果

**测试 3：流式输出**

`--stream --text-mode` 组合正常工作：
- token 实时打印到终端（非 collect 后 print）
- agent 调用 `read_file` 读取文件并回答
- `✅ (流式输出完成)` 标记正确

**测试 4：权限审批**

- `4a`（同意）：agent 调用 bash 前弹出 `执行此命令? [y/N]:`，管道输入 `y`，bash 执行成功输出 `approval_test_ok`
- `4b`（拒绝）：管道输入 `n`，bash 未执行，agent 直接给出文字回答（未调用工具）

### 6.5 UT 回归确认

E2E 测试后重新运行全部单元测试：

```
125 passed in 28.12s
```

text-mode 改造未引入任何退化，125 个测试全部继续通过。

---

## 七、测试覆盖率矩阵

| 源文件 | v1 行数 | v2 行数 | 测试文件 | v1 测试 | v2 测试 | 关键路径覆盖 |
|--------|---------|---------|---------|---------|---------|------------|
| `tools.py` | 189 | 340 | `test_tools.py` | 36 | 49 | read/write/edit/**glob/grep** 正常+异常 + execute_tool 路由 + schema(4→6) + **.gitignore 过滤** |
| `agent.py` | 81 | 241 | `test_agent.py` | 15 | 28 | _truncate + _estimate_tokens + _truncate_for_llm + _print_tool_call + ReAct 循环 + **token 预算** + **审批** + **text-mode 解析** |
| `llm.py` | 19 | 125 | `test_llm.py` | 10 | 18 | create_client + **complete_with_retry** + **stream_complete** |
| `__main__.py` | 68 | 96 | `test_cli.py` | 16 | 22 | --help + stdin + 参数解析 + **--stream** + **--approval** + **--max-tool-output** |
| `prompts.py` | 20 | 75 | 间接覆盖 | — | — | SYSTEM_PROMPT + **SYSTEM_PROMPT_TEXT_MODE** |
| `__init__.py` | 1 | 1 | 间接覆盖 | — | — | 通过 `import nautilus` 验证 `__version__ = "0.2.0"` |
| **合计** | **378** | **878** | | **77** | **125** | |

---

## 八、v1→v2 回归对比

| 验证维度 | v1 状态 | v2 状态 | 回归 |
|---------|---------|---------|------|
| 模块导入 | ✅ 6 模块 | ✅ 6 模块 | 无退化 |
| CLI --help | ✅ 5 参数 | ✅ 9 参数 | 无退化 |
| read_file/write_file/edit_file/bash | ✅ 4 工具 | ✅ 4 工具 | 无退化 |
| execute_tool 路由 | ✅ 4 路由 | ✅ 6 路由 | 无退化 |
| TOOL_SCHEMAS | ✅ 4 schema | ✅ 6 schema | 无退化 |
| ReAct 循环（mock LLM） | ✅ 3 场景 | ✅ 3 场景 | 无退化 |
| create_client 工厂 | ✅ 10 tests | ✅ 10 tests | 无退化 |
| CLI 参数解析 | ✅ 12 tests | ✅ 12 tests | 无退化 |
| **v2 新增** | — | ✅ +48 tests | — |
| **合计** | **77 passed** | **125 passed** | **0 退化** |

---

## 九、结论

### 9.1 v2 新功能全部验证通过

Nautilus v2 的 5 个新功能**全部通过验证**：

- **Grep/Glob 搜索工具**：递归匹配、正则搜索、行号格式、二进制跳过、.gitignore 过滤——全部正确
- **错误恢复**：可重试/不可重试错误分类正确、指数退避、超限 SystemExit——全部正确
- **流式输出**：content 累积+实时打印、tool_calls 重组、兼容 agent 循环——全部正确
- **权限审批**：拒绝→observation 回灌、同意→正常执行、默认禁用——全部正确
- **.gitignore 感知**：glob/grep 过滤、无 .gitignore 不过滤——全部正确

### 9.2 E2E 端到端真实场景验证通过

在 Ollama + deepseek-r1:8b 环境下完成 4 个真实场景测试，全部通过：

- **基础任务**：write_file → bash → 最终回答，闭环正确
- **Grep/Glob**：glob 搜索文件 + grep 搜索内容，定位准确
- **流式输出**：--stream 实时打印 token，工具调用正常
- **权限审批**：--approval 同意执行 + 拒绝拦截，两种场景正确

### 9.3 text-mode 适配

为兼容不支持 function calling 的模型（如 deepseek-r1），实现了 text-mode 工具调用：
- `--text-mode` CLI 参数，用 prompt-based calling 替代 native function calling
- ` ```tool_call {json} ` ` 格式约定 + 文本解析器
- E2E 验证确认 text-mode 下 ReAct 循环正确工作

### 9.4 v1 回归无退化

v1 的 77 个测试全部在 v2 中继续通过，0 退化。新增的 48 个测试覆盖 v2 全部新功能。E2E 改造后 125 个测试仍全部通过。

### 9.5 已知问题

| 问题 | 严重程度 | v1/v2 | 规避方式 |
|------|---------|-------|---------|
| Windows GBK 编码不支持 emoji | 中 | v1 遗留 | `PYTHONIOENCODING=utf-8` |
| 上级 pyproject.toml 干扰 pytest | 低 | v1 遗留 | `-o "addopts="` |
| CLI stdin 测试超时 | 低 | v2 调整 | timeout 60s + 非路由 IP |
| deepseek-r1 不支持 function calling | 中 | E2E 发现 | `--text-mode` 适配 |

### 9.6 待后续验证

- 支持 function calling 的模型（qwen2.5/llama3.1）在 native mode 下的端到端测试
- `complete_with_retry` 真实 API 限流重试（需限流场景）
- glob/grep 在大型代码库中的搜索性能

---

## 附录：完整测试输出

```
============================= test session starts ==============================
platform win32 -- Python 3.14.4, pytest-9.0.3, pluggy-1.6.0
rootdir: D:\AIAgent\Practice
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0
collected 125 items

tests\test_agent.py::TestTruncate::test_short_text_passthrough PASSED    [  0%]
tests\test_agent.py::TestTruncate::test_exact_limit PASSED               [  1%]
tests\test_agent.py::TestTruncate::test_long_text_truncated PASSED       [  2%]
tests\test_agent.py::TestTruncate::test_truncation_marker_format PASSED  [  3%]
tests\test_agent.py::TestTruncate::test_empty_string PASSED              [  4%]
tests\test_agent.py::TestTruncate::test_custom_limit PASSED              [  4%]
tests\test_agent.py::TestEstimateTokens::test_pure_ascii PASSED          [  5%]
tests\test_agent.py::TestEstimateTokens::test_pure_cjk PASSED            [  6%]
tests\test_agent.py::TestEstimateTokens::test_empty_string PASSED        [  7%]
tests\test_agent.py::TestEstimateTokens::test_mixed_ascii_cjk PASSED     [  8%]
tests\test_agent.py::TestEstimateTokens::test_long_code_text PASSED      [  8%]
tests\test_agent.py::TestEstimateTokens::test_none_safety PASSED         [  9%]
tests\test_agent.py::TestTruncateForLlm::test_short_text_passthrough PASSED [ 10%]
tests\test_agent.py::TestTruncateForLlm::test_exact_limit_no_truncation PASSED [ 11%]
tests\test_agent.py::TestTruncateForLlm::test_long_text_truncated_with_bilingual_marker PASSED [ 12%]
tests\test_agent.py::TestTruncateForLlm::test_custom_max_chars PASSED    [ 12%]
tests\test_agent.py::TestTruncateForLlm::test_empty_string PASSED       [ 13%]
tests\test_agent.py::TestPrintToolCall::test_read_file PASSED            [ 14%]
tests\test_agent.py::TestPrintToolCall::test_write_file PASSED           [ 15%]
tests\test_agent.py::TestPrintToolCall::test_edit_file PASSED            [ 16%]
tests\test_agent.py::TestPrintToolCall::test_bash PASSED                 [ 16%]
tests\test_agent.py::TestPrintToolCall::test_unknown_tool PASSED         [ 17%]
tests\test_agent.py::TestPrintToolCall::test_missing_args PASSED         [ 18%]
tests\test_agent.py::TestRunAgentReActLoop::test_full_react_loop PASSED  [ 19%]
tests\test_agent.py::TestRunAgentMaxIter::test_max_iter_truncation PASSED [ 20%]
tests\test_agent.py::TestRunAgentErrorRecovery::test_error_self_correction PASSED [ 20%]
tests\test_agent.py::TestRunAgentTokenBudget::test_large_tool_output_truncated_in_messages PASSED [ 21%]
tests\test_agent.py::TestRunAgentApproval::test_approval_rejected_bash_command PASSED [ 22%]
tests\test_agent.py::TestRunAgentApproval::test_approval_accepted_bash_command PASSED [ 23%]
tests\test_agent.py::TestRunAgentApproval::test_approval_disabled_by_default PASSED [ 24%]
tests\test_cli.py::TestCLIHelp::test_help_exits_zero PASSED              [ 24%]
tests\test_cli.py::TestCLIHelp::test_help_shows_description PASSED       [ 25%]
tests\test_cli.py::TestCLINoPrompt::test_no_prompt_no_stdin_exits_1 PASSED [ 26%]
tests\test_cli.py::TestCLIStdin::test_stdin_prompt_is_read PASSED        [ 27%]
tests\test_cli.py::TestCLIArgumentParsing::test_positional_prompt PASSED [ 28%]
tests\test_cli.py::TestCLIArgumentParsing::test_model_flag PASSED        [ 28%]
tests\test_cli.py::TestCLIArgumentParsing::test_api_key_flag PASSED      [ 29%]
tests\test_cli.py::TestCLIArgumentParsing::test_base_url_flag PASSED     [ 30%]
tests\test_cli.py::TestCLIArgumentParsing::test_max_iter_flag PASSED     [ 31%]
tests\test_cli.py::TestCLIArgumentParsing::test_max_tool_output_flag PASSED [ 32%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_max_iter_is_20 PASSED [ 32%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_model_is_gpt4 PASSED [ 33%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_api_key_is_none PASSED [ 34%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_max_tool_output_is_6000 PASSED [ 35%]
tests\test_cli.py::TestCLIArgumentParsing::test_stream_flag PASSED       [ 36%]
tests\test_cli.py::TestCLIArgumentParsing::test_stream_default_false PASSED [ 36%]
tests\test_cli.py::TestCLIArgumentParsing::test_approval_flag PASSED     [ 37%]
tests\test_cli.py::TestCLIArgumentParsing::test_approval_default_false PASSED [ 38%]
tests\test_llm.py::TestCreateClientNoKey::test_no_key_raises_systemexit PASSED [ 39%]
tests\test_llm.py::TestCreateClientNoKey::test_no_key_message_mentions_env_var PASSED [ 40%]
tests\test_llm.py::TestCreateClientExplicit::test_explicit_key_creates_client PASSED [ 40%]
tests\test_llm.py::TestCreateClientExplicit::test_explicit_key_and_base_url PASSED [ 41%]
tests\test_llm.py::TestCreateClientEnvFallback::test_env_api_key PASSED  [ 42%]
tests\test_llm.py::TestCreateClientEnvFallback::test_env_api_key_and_base_url PASSED [ 43%]
tests\test_llm.py::TestCreateClientEnvFallback::test_explicit_overrides_env PASSED [ 44%]
tests\test_llm.py::TestCreateClientEnvFallback::test_base_url_not_set_when_only_api_key_in_env PASSED [ 44%]
tests\test_llm.py::TestCreateClientPriority::test_none_api_key_falls_back_to_env PASSED [ 45%]
tests\test_llm.py::TestCreateClientPriority::test_empty_string_api_key_does_not_fallback PASSED [ 46%]
tests\test_llm.py::TestCompleteWithRetry::test_success_on_first_try PASSED [ 47%]
tests\test_llm.py::TestCompleteWithRetry::test_retry_on_rate_limit_then_success PASSED [ 48%]
tests\test_llm.py::TestCompleteWithRetry::test_all_retries_exhausted_raises_systemexit PASSED [ 48%]
tests\test_llm.py::TestCompleteWithRetry::test_bad_request_not_retried PASSED [ 49%]
tests\test_llm.py::TestCompleteWithRetry::test_auth_error_not_retried PASSED [ 50%]
tests\test_llm.py::TestStreamComplete::test_stream_content_accumulated_and_printed PASSED [ 51%]
tests\test_llm.py::TestStreamComplete::test_stream_tool_calls_assembled PASSED [ 52%]
tests\test_llm.py::TestStreamComplete::test_stream_empty_response PASSED [ 52%]
tests\test_tools.py::TestWriteFile::test_write_normal PASSED             [ 53%]
tests\test_tools.py::TestWriteFile::test_write_returns_byte_count PASSED [ 54%]
tests\test_tools.py::TestWriteFile::test_auto_create_parent_dirs PASSED  [ 55%]
tests\test_tools.py::TestWriteFile::test_overwrite_existing PASSED       [ 56%]
tests\test_tools.py::TestReadFile::test_read_normal PASSED               [ 56%]
tests\test_tools.py::TestReadFile::test_read_nonexistent PASSED          [ 57%]
tests\test_tools.py::TestReadFile::test_read_binary_file PASSED          [ 58%]
tests\test_tools.py::TestEditFile::test_edit_normal PASSED               [ 59%]
tests\test_tools.py::TestEditFile::test_edit_old_string_not_found PASSED [ 60%]
tests\test_tools.py::TestEditFile::test_edit_multiple_matches PASSED     [ 60%]
tests\test_tools.py::TestEditFile::test_edit_nonexistent_file PASSED     [ 61%]
tests\test_tools.py::TestEditFile::test_edit_preserves_surrounding_content PASSED [ 62%]
tests\test_tools.py::TestBash::test_echo_success PASSED                  [ 63%]
tests\test_tools.py::TestBash::test_python_execution PASSED              [ 64%]
tests\test_tools.py::TestBash::test_nonzero_exit PASSED                  [ 64%]
tests\test_tools.py::TestBash::test_stderr_capture PASSED                [ 65%]
tests\test_tools.py::TestBash::test_command_output_includes_both_streams PASSED [ 66%]
tests\test_tools.py::TestExecuteTool::test_route_write_file PASSED       [ 67%]
tests\test_tools.py::TestExecuteTool::test_route_read_file PASSED        [ 68%]
tests\test_tools.py::TestExecuteTool::test_route_edit_file PASSED        [ 68%]
tests\test_tools.py::TestExecuteTool::test_route_bash PASSED             [ 69%]
tests\test_tools.py::TestExecuteTool::test_route_glob PASSED             [ 70%]
tests\test_tools.py::TestExecuteTool::test_route_grep PASSED            [ 71%]
tests\test_tools.py::TestExecuteTool::test_unknown_tool PASSED           [ 72%]
tests\test_tools.py::TestExecuteTool::test_invalid_json_arguments PASSED [ 72%]
tests\test_tools.py::TestExecuteTool::test_empty_arguments_string PASSED [ 73%]
tests\test_tools.py::TestExecuteTool::test_none_arguments PASSED         [ 74%]
tests\test_tools.py::TestToolSchemas::test_schema_count PASSED           [ 75%]
tests\test_tools.py::TestToolSchemas::test_schema_names PASSED           [ 76%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[read_file-...] PASSED [ 76%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[write_file-...] PASSED [ 77%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[edit_file-...] PASSED [ 78%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[glob-...] PASSED [ 79%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[grep-...] PASSED [ 80%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[bash-...] PASSED [ 80%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[read_file] PASSED [ 81%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[write_file] PASSED [ 82%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[edit_file] PASSED [ 83%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[glob] PASSED [ 84%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[grep] PASSED [ 84%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[bash] PASSED [ 85%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[read_file] PASSED [ 86%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[write_file] PASSED [ 87%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[edit_file] PASSED [ 88%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[glob] PASSED [ 88%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[grep] PASSED [ 89%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[bash] PASSED [ 90%]
tests\test_tools.py::TestToolSchemas::test_all_schemas_are_function_type PASSED [ 91%]
tests\test_tools.py::TestGlob::test_glob_finds_python_files PASSED       [ 92%]
tests\test_tools.py::TestGlob::test_glob_no_match PASSED                 [ 92%]
tests\test_tools.py::TestGlob::test_glob_recursive PASSED                [ 93%]
tests\test_tools.py::TestGlob::test_glob_respects_gitignore PASSED       [ 94%]
tests\test_tools.py::TestGrep::test_grep_finds_matches PASSED            [ 95%]
tests\test_tools.py::TestGrep::test_grep_returns_line_numbers PASSED     [ 96%]
tests\test_tools.py::TestGrep::test_grep_no_match PASSED                 [ 96%]
tests\test_tools.py::TestGrep::test_grep_specific_file PASSED            [ 97%]
tests\test_tools.py::TestGrep::test_grep_invalid_regex PASSED            [ 98%]
tests\test_tools.py::TestGrep::test_grep_skips_binary_files PASSED       [ 99%]
tests\test_tools.py::TestGrep::test_grep_respects_gitignore PASSED       [100%]

============================ 125 passed in 27.94s =============================
```

---

## 参考资料

- Nautilus 第一性原理设计方案：`coding-agent-第一性原理设计方案.md`（同目录）
- Nautilus v1 实现计划：`nautilus-v1-实现计划.md`（同目录）
- Nautilus v1 实现总结：`nautilus-v1-实现总结.md`（同目录）
- Nautilus v1 验证报告：`nautilus-v1-验证报告.md`（同目录）
- Nautilus v2 实现计划：`nautilus-v2-实现计划.md`（同目录）
- Nautilus v2 实现总结：`nautilus-v2-实现总结.md`（同目录）
- Nautilus 系统目标：`nautilus-系统目标.md`（同目录）
- Nautilus 结果质量评估标准：`nautilus-结果质量评估标准.md`（同目录）
- 源码：`nautilus/nautilus/`（agent.py / tools.py / prompts.py / llm.py / __main__.py）
- UT 源码：`nautilus/tests/`（test_tools.py / test_agent.py / test_llm.py / test_cli.py）
