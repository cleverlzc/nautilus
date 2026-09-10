# Nautilus v0.3.2 plan mode — 实现总结

## 文件清单（实际）

**7 个源码文件 + 4 个测试文件**，位于 `...\AIAgent\mycodingagent\nautilus\`：

| 文件 | v0.3.1 行数 | v0.3.2 行数 | 职责 |
|------|------------|------------|------|
| `pyproject.toml` | 16 | 16 | 项目元数据 + openai 依赖 + CLI 入口（版本 0.3.2） |
| `nautilus/__init__.py` | 1 | 1 | 版本号（0.3.2） |
| `nautilus/prompts.py` | 99 | 115 | 系统提示词 + SUBAGENT + TEXT_MODE + **SYSTEM_PROMPT_PLAN** |
| `nautilus/tools.py` | 399 | 399 | 7 个工具 + execute_tool 路由 + .gitignore 过滤 + 危险命令过滤 |
| `nautilus/llm.py` | 125 | 125 | OpenAI 兼容 client 工厂 + complete_with_retry + stream_complete |
| `nautilus/agent.py` | 383 | 412 | **核心 ReAct 循环** + token 预算控制 + stream/approval/text_mode 分支 + 上下文压缩 + 子 agent + **plan mode（Phase 1 计划生成 + Phase 2 计划注入）** |
| `nautilus/__main__.py` | 109 | 116 | CLI 入口 + GBK 编码修复 + 11 个参数（含 `--plan`） |
| **源码合计** | **1116** | **1168** | |

**总计 1168 行 Python 源码**（v0.3.2 新增约 52 行源码 + 5 个测试，主要是 `plan_mode` 参数 + Phase 1/2 分支 + `SYSTEM_PROMPT_PLAN` 提示词 + `--plan` CLI 参数）。

## v0.3.2 新增功能（1 个）

| # | 功能 | 核心实现 |
|---|------|---------|
| 1 | **plan mode** | `agent.py` `run_agent()` 新增 `plan_mode: bool = False` 参数。Phase 1：用 `SYSTEM_PROMPT_PLAN` 提示词调用 LLM 生成结构化执行计划（不传 tools，纯文本），打印 `📋 执行计划` + `input("是否执行此计划? [y/N]:")`。Phase 2：用户确认后，将计划注入 messages（assistant 消息 + user"请按计划执行"），进入正常 ReAct 循环。`prompts.py` 新增 `SYSTEM_PROMPT_PLAN` 提示词（5 条要求 + 格式示例）。`__main__.py` 新增 `--plan` CLI 参数 |

### 两阶段流程

| 阶段 | 输入 | 输出 | 工具 |
|------|------|------|------|
| Phase 1（计划生成） | user prompt + `SYSTEM_PROMPT_PLAN` | 结构化计划文本（步骤列表+工具指明+预估风险） | 不调用工具 |
| Phase 2（计划执行） | system prompt + user prompt + assistant(计划) + user("请按计划执行") | ReAct 循环执行 + 最终回答 | 正常 7 工具 |

### 设计要点

- **Phase 1 不调工具**：计划生成阶段用 `SYSTEM_PROMPT_PLAN` 提示词，不传 `tools=TOOL_SCHEMAS`，LLM 只输出文本计划
- **Phase 2 计划注入**：将计划作为 `assistant` 消息注入 messages，再加一条 `user` 消息"请按计划执行"，让 LLM 在后续循环中参考计划
- **用户确认门**：`input("是否执行此计划? [y/N]: ")`，拒绝则直接 return，不进入执行循环
- **不与 stream 冲突**：plan mode 的 Phase 1 不使用 stream（计划生成是单次调用），Phase 2 正常 ReAct 循环可叠加 `--stream`
- **组合兼容**：可与 `--stream`、`--approval`、`--text-mode`、`--max-context-tokens` 组合使用

## 验证结果

### 单元测试

- ✅ 所有模块导入正常
- ✅ CLI `--help` 输出正确（11 参数，含 `--plan`）
- ✅ plan mode 验证（计划+确认→执行 / 计划+拒绝→退出 / 默认禁用不触发 3 种场景）
- ✅ 单元测试 160 passed, 0 failed

### E2E 端到端真实场景（Ollama + qwen2.5:7b）

- ✅ 计划+确认+执行：Phase 1 生成 7 步结构化计划（含工具指明+预估风险）→ 用户 y → Phase 2 执行工具调用
- ✅ 计划+拒绝：Phase 1 生成 5 步计划+注意事项 → 用户 n → "用户取消了执行" → 未进入 ReAct 循环
- ✅ 对比验证：默认模式直接进入 ReAct 循环，无 📋 输出，无 input 确认

## 测试覆盖

| 测试模块 | v0.3.1 测试数 | v0.3.2 测试数 | 新增内容 |
|---------|------------|------------|---------|
| `test_agent.py` | 43 | 46 | TestPlanMode(3：accepted / rejected / disabled_by_default) |
| `test_cli.py` | 24 | 26 | test_plan_flag(1) + test_plan_default_false(1) |
| `test_tools.py` | 63 | 63 | — |
| `test_llm.py` | 18 | 18 | — |
| **合计** | **155** | **160** | **+5** |

## 使用方式

```bash
cd ".../AIAgent/mycodingagent/nautilus"
pip install -e .
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://xxx   # 可选，OpenAI 兼容 API

# v0.3.2 新增：plan mode（先生成计划，用户确认后再执行）
nautilus --plan "分析这个项目的所有文件结构和函数定义"

# plan + approval 组合
nautilus --plan --approval "复杂修改任务"

# plan + stream 组合
nautilus --plan --stream "重构整个模块"

# 默认模式（不用 plan mode，直接执行）
nautilus "创建一个 hello.py，运行它"

# 运行单元测试
PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
```

## 核心洞察

当前 agent 收到任务后直接进入 ReAct 循环——LLM 边想边做，可能在第 3 步才发现第 1 步方向错了，浪费迭代圈数。对于复杂任务（如"重构整个模块"），agent 可能需要 10+ 轮试错才能收敛。

v0.3.2 补齐了这个缺口：plan mode 让 agent 先用 1 次 LLM 调用生成结构化执行计划（步骤列表+工具指明+预估风险），用户确认后，将计划注入 messages 作为 assistant 上下文，agent 按计划执行——减少盲目试错。这形成了**先规划再执行**的两阶段模式（ToC：提升有效产出 T——减少 LLM 试错圈数）。

E2E 验证确认：plan mode 正确生成结构化计划 → 用户确认门正确工作（y→执行 / n→退出）→ 默认模式行为不变。plan mode 是 v0.3.3 记忆系统的基础——记忆可以为计划生成提供项目上下文。
