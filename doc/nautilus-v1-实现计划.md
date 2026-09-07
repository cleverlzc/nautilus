# Nautilus v1 实现计划

## Context

用户要从零开发一个 coding agent，设计参考 Claude Code / Codex / Aider 等开源项目。前面已完成第一性原理设计方案（保存在 `...\AIAgent\mycodingagent\coding-agent-第一性原理设计方案.md`），现在要落地实现 v1。

v1 的目标：**~300 行可运行的 Python coding agent**（实际 378 行），能在真实 repo 里完成"读文件→理解→修改→跑命令→报告结果"闭环。

## 项目位置

```
...\AIAgent\mycodingagent\nautilus\
```

## 文件清单（7 个文件）

| 文件 | 职责 | 预估行数 |
|------|------|---------|
| `pyproject.toml` | 项目元数据 + 依赖(openai) + CLI 入口 | ~15 |
| `nautilus/__init__.py` | 空文件/版本号 | ~3 |
| `nautilus/__main__.py` | CLI 入口：argparse 解析参数，调用 agent | ~35 |
| `nautilus/prompts.py` | 系统提示词（定义 agent 行为） | ~20 |
| `nautilus/tools.py` | 4 个工具定义 + 执行路由（read_file/write_file/edit_file/bash） | ~190 |
| `nautilus/llm.py` | OpenAI 兼容 API 封装 | ~25 |
| `nautilus/agent.py` | **核心**：agent 循环（ReAct loop） | ~45 |

## 各文件实现细节

### 1. `pyproject.toml`

```toml
[project]
name = "nautilus"
version = "0.1.0"
description = "Nautilus — 鹦鹉螺：螺旋逼近答案的 coding agent"
requires-python = ">=3.10"
dependencies = ["openai>=1.0.0"]

[project.scripts]
nautilus = "nautilus.__main__:main"
```

### 2. `nautilus/__init__.py`

```python
__version__ = "0.1.0"
```

### 3. `nautilus/prompts.py`

系统提示词，定义 agent 行为准则：
- 先读后改、最小修改、遵循项目风格
- 改完验证（跑测试）
- 完成后给摘要

### 4. `nautilus/tools.py`

**工具 Schema（OpenAI function calling 格式）：**
- `read_file(path)` — 读文件，utf-8，失败返回错误信息
- `write_file(path, content)` — 写文件（新建或整文件覆盖），自动创建父目录
- `edit_file(path, old_string, new_string)` — 精确替换文件中的指定文本（局部修改，避免整文件重写）；old_string 必须精确匹配且唯一，多处匹配时拒绝替换以防误改
- `bash(command)` — 执行 shell 命令，30s 超时，捕获 stdout+stderr

**执行路由：**
```python
def execute_tool(tool_call) -> str:
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)
    # dispatch to read_file / write_file / edit_file / bash
    # 未知工具返回错误信息（不崩溃）
```

### 5. `nautilus/llm.py`

```python
from openai import OpenAI

def create_client(api_key=None, base_url=None) -> OpenAI:
    # 优先级：参数 > 环境变量
    # OPENAI_API_KEY, OPENAI_BASE_URL
```

### 6. `nautilus/agent.py` — 核心循环

```python
def run_agent(prompt, model, api_key, base_url, max_iter):
    messages = [system_prompt, user_prompt]
    for i in range(max_iter):
        response = client.chat.completions.create(model, messages, tools)
        message = response.choices[0].message
        if message.tool_calls:
            print agent thinking
            append assistant message to history
            for each tool_call:
                print tool name + args
                result = execute_tool(tool_call)
                print truncated result
                append tool result to history
        else:
            print final answer
            return
    print "reached max iterations"
```

### 7. `nautilus/__main__.py` — CLI

```
$ nautilus "创建一个 hello.py"
$ nautilus --model qwen-plus --base-url https://xxx "修复 bug"
$ nautilus --max-iter 30 "重构 utils.py"
```

参数：
- `prompt`（positional，支持交互式输入）
- `--model`（默认 gpt-4）
- `--api-key`（或 OPENAI_API_KEY 环境变量）
- `--base-url`（或 OPENAI_BASE_URL 环境变量）
- `--max-iter`（默认 20）

## 终端输出格式

```
💭 Agent thinking text...
🔧 read_file("src/main.py")
   → [200 lines of content]
🔧 bash("python -m pytest")
   → 3 passed, 1 failed
💭 Let me fix the failing test...
🔧 write_file("src/test_main.py", ...)
   → Successfully wrote 1.2KB
✅ Final answer summary
```

## 验证方式

1. `pip install -e .` 安装
2. 设置环境变量 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`
3. 在一个测试目录运行：
   ```
   nautilus "创建一个 hello.py，运行它，确认输出 hello world"
   ```
4. 验证 agent 能：读文件、写文件、编辑文件、跑命令、输出最终结果

