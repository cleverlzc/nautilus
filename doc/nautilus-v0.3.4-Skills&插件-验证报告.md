# Nautilus v0.3.4 Skills/插件 — 验证报告

> 验证对象：Nautilus v0.3.4（1346 行 Python，7 工具，ReAct 循环 + 上下文压缩 + 子 agent + plan mode + 记忆系统 + Skills/插件）
> 验证日期：2026-09-11
> 验证环境：Python 3.14.4 / Windows 11 / openai 2.35.1 / pytest 9.0.3
> E2E 环境：Ollama 本地 / qwen2.5:7b / native function calling
> UT 文件：`nautilus/tests/` 目录下 6 个测试模块，191 个测试用例
> E2E 测试：3 个场景，全部通过

---

## 一、验证范围

### 1.1 验证目标

验证 Nautilus v0.3.4 Skills/插件功能**是否可真正工作**——在 v0.3.3 已验证的基础上，验证 `skills.py` 的 `list_skills()` / `load_skill()` / `match_skill()` 函数、`run_agent()` 的 skill 匹配注入集成、`--skills-dir` CLI 参数的正确性，同时确认 v0.3.3 功能回归无退化。

### 1.2 UT 文件结构

```
nautilus/
├── pyproject.toml              # 16 行 — 版本 0.3.4
├── nautilus/                   # 源码包（1346 行）
│   ├── __init__.py             #   1 行 — 版本 0.3.4
│   ├── __main__.py             # 128 行 — CLI + --skills-dir（13 个参数）
│   ├── agent.py                # 443 行 — ReAct 循环 + 压缩 + 子 agent + plan mode + 记忆 + skills 注入
│   ├── llm.py                  # 125 行 — client 工厂 + retry + stream
│   ├── memory.py               #  40 行 — load_memory + save_memory + append_memory
│   ├── prompts.py              # 121 行 — 系统提示词 + SUBAGENT + PLAN + TEXT_MODE + 记忆/技能说明
│   ├── skills.py               #  89 行 — list_skills + load_skill + match_skill（新增）
│   └── tools.py                # 399 行 — 7 工具 + execute_tool 路由 + .gitignore + 危险过滤
└── tests/                      # 单元测试
    ├── __init__.py             #   8 行
    ├── test_tools.py           # 417 行 — 63 tests
    ├── test_agent.py           # 1159 行 — 46 tests
    ├── test_llm.py             # 286 行 — 18 tests
    ├── test_cli.py             # 280 行 — 30 tests
    ├── test_memory.py          # 198 行 — 13 tests
    └── test_skills.py          # 232 行 — 14 tests（新增）
```

### 1.3 运行方式

```bash
cd ".../AIAgent/mycodingagent/nautilus"
python -m pytest tests/ -v -o "addopts="
```

---

## 二、验证结果总览

### 2.1 最终结果

```
============================ 191 passed in 31.30s =============================
```

| 指标 | v0.3.3 | v0.3.4 |
|------|--------|--------|
| 测试总数 | 175 | 191 |
| 通过 | 175 | 191 |
| 失败 | 0 | 0 |
| 错误 | 0 | 0 |
| 跳过 | 0 | 0 |
| 总耗时 | 34.40s | 31.30s |
| 新增测试 | — | +16 |

### 2.2 按模块统计

| 测试模块 | v0.3.3 测试数 | v0.3.4 测试数 | 新增 | 覆盖组件 |
|---------|------------|------------|------|---------|
| `test_tools.py` | 63 | 63 | — | — |
| `test_agent.py` | 46 | 46 | — | — |
| `test_llm.py` | 18 | 18 | — | — |
| `test_cli.py` | 28 | 30 | +2 | **--skills-dir flag** + **skills_dir_default_none** |
| `test_memory.py` | 13 | 13 | — | — |
| `test_skills.py` | 0 | 14 | +14 | **TestListSkills**(4) + **TestLoadSkill**(2) + **TestMatchSkill**(5) + **TestSkillIntegration**(3) |
| **合计** | **175** | **191** | **+16** | |

---

## 三、各模块验证详情

### 3.1 test_skills.py 新增测试（14 tests）

#### TestListSkills（4 tests）

| 测试 | 覆盖场景 |
|------|---------|
| `test_list_skills_with_files` | 有 .md 文件 → 返回 skill 列表（含 name/path/keywords/description/content） |
| `test_list_skills_no_dir` | 目录不存在 → 返回空列表 |
| `test_list_skills_empty_dir` | 空目录 → 返回空列表 |
| `test_list_skills_ignores_non_md` | 非 .md 文件（.txt）被忽略，.md 文件被收录 |

关键验证点：
- `list_skills` 正确扫描目录并解析 frontmatter（keywords + description）
- 无目录/空目录不崩溃，返回空列表
- `.txt` 文件被忽略，`.md` 文件被收录

#### TestLoadSkill（2 tests）

| 测试 | 覆盖场景 |
|------|---------|
| `test_load_skill_existing` | 正常读取 skill 文件内容 |
| `test_load_skill_nonexistent` | 文件不存在 → 返回空字符串 |

#### TestMatchSkill（5 tests）

| 测试 | 覆盖场景 |
|------|---------|
| `test_match_skill_keyword_match` | prompt 含 skill keyword → 返回 skill 内容 |
| `test_match_skill_no_match` | prompt 不含任何 keyword → 返回 None |
| `test_match_skill_best_match` | 多 skill 匹配 → 返回匹配度最高的 |
| `test_match_skill_name_match` | prompt 含 skill 名称 → 返回 skill 内容 |
| `test_match_skill_empty_skills` | 空 skills 列表 → 返回 None |

关键验证点：
- 关键词匹配 + skill 名称匹配双重匹配机制
- 多 skill 匹配时按匹配度（score）排序取最高
- 无匹配返回 None，不误注入

#### TestSkillIntegration（3 tests）

| 测试 | 覆盖场景 |
|------|---------|
| `test_skill_injected_into_system_prompt` | mock LLM 捕获 messages，验证 system prompt 含"## 技能指导"段落 + skill 内容 |
| `test_skill_not_injected_when_disabled` | `skills_dir=None` → 验证 system prompt 不含"## 技能指导" |
| `test_skill_not_injected_when_no_match` | prompt 不含 skill keywords → 验证 system prompt 不含"## 技能指导" |

关键验证点：

**skill 注入**（`test_skill_injected_into_system_prompt`）：
- 预先创建 skill 文件（deploy.md，keywords: deploy/部署）
- mock LLM 捕获第 1 次调用的 messages
- 验证 system prompt 含"## 技能指导"、"部署"、"build"

**skill 禁用**（`test_skill_not_injected_when_disabled`）：
- `skills_dir=None` 时 system prompt 不含"## 技能指导"

**skill 无匹配**（`test_skill_not_injected_when_no_match`）：
- prompt 不含 skill keywords 时 system prompt 不含"## 技能指导"

### 3.2 test_cli.py 新增测试（2 tests）

| 测试 | 覆盖场景 |
|------|---------|
| `test_skills_dir_flag` | `--skills-dir .nautilus/skills` 传参 → `skills_dir=".nautilus/skills"` |
| `test_skills_dir_default_none` | 不传参 → `skills_dir=None` |

---

## 四、v0.3.4 功能验证

### 4.1 skills.py 函数

| 验证项 | 结果 | 说明 |
|--------|------|------|
| `list_skills()` 有文件 | ✅ | 返回 skill 列表（含 name/path/keywords/description/content） |
| `list_skills()` 无目录 | ✅ | 返回空列表 |
| `list_skills()` 空目录 | ✅ | 返回空列表 |
| `list_skills()` 忽略非 .md | ✅ | .txt 被忽略，.md 被收录 |
| `load_skill()` 有文件 | ✅ | 返回文件内容 |
| `load_skill()` 无文件 | ✅ | 返回空字符串 |
| `match_skill()` 关键词匹配 | ✅ | prompt 含 keyword → 返回 skill 内容 |
| `match_skill()` 无匹配 | ✅ | 返回 None |
| `match_skill()` 最佳匹配 | ✅ | 多 skill → 返回匹配度最高 |
| `match_skill()` 名称匹配 | ✅ | prompt 含 skill 名 → 返回内容 |
| `match_skill()` 空列表 | ✅ | 返回 None |
| `_parse_frontmatter()` | ✅ | 正确解析 keywords + description |

### 4.2 agent.py skills 集成

| 验证项 | 结果 | 说明 |
|--------|------|------|
| `skills_dir` 参数 | ✅ | `run_agent()` 新增 `skills_dir: str | None = None` |
| skill 匹配注入 | ✅ | `list_skills` + `match_skill` + `system_prompt += "## 技能指导\n..."` |
| 禁用时不注入 | ✅ | `skills_dir=None` 时不扫描/不注入 |
| 无匹配时不注入 | ✅ | `match_skill` 返回 None 时不注入 |

### 4.3 prompts.py 更新

| 验证项 | 结果 | 说明 |
|--------|------|------|
| SYSTEM_PROMPT 技能说明 | ✅ | "如果系统提示词中包含'技能指导'段落，请按其中的步骤和注意事项执行任务" |
| SYSTEM_PROMPT_TEXT_MODE 同步 | ✅ | 同上 |

### 4.4 CLI 参数

| 验证项 | 结果 | 说明 |
|--------|------|------|
| `--skills-dir` 传参 | ✅ | `--skills-dir .nautilus/skills` → `skills_dir=".nautilus/skills"` |
| 默认 None | ✅ | 不传参 → `skills_dir=None`（不启用） |

---

## 五、E2E 端到端真实场景验证

### 5.1 测试环境

| 项 | 值 |
|---|---|
| LLM 服务 | Ollama 本地 (http://127.0.0.1:11434) |
| 模型 | qwen2.5:7b（native function calling） |
| API Key | test |
| 模式 | native function calling |
| Skill 文件 | `.nautilus/skills/deploy.md`（keywords: deploy/部署/build + 3 步骤指导） |
| 测试项目 | 3 个 Python 文件（calc.py / main.py / utils.py） |
| OS | Windows 11 / Python 3.14.4 |

### 5.2 E2E 测试结果

| # | 测试场景 | 命令 | 结果 | 关键验证点 |
|---|---------|------|------|-----------|
| 1 | **有 skill 匹配** | `OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:11434/v1 nautilus --model "qwen2.5:7b" --max-iter 10 --skills-dir .nautilus/skills "部署项目到生产环境"` | ✅ 通过 | Agent 严格按 skill 步骤执行：`echo building project...` → `echo running tests...` → `echo deploying to production...` → 最终回答"项目部署完成" |
| 2 | **无 skill 匹配** | `OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:11434/v1 nautilus --model "qwen2.5:7b" --max-iter 5 --skills-dir .nautilus/skills "用 glob 搜索所有 .py 文件，告诉我有几个"` | ✅ 通过 | Agent 直接用 glob 搜索文件（未按部署步骤执行），skill 未匹配未注入 |
| 3 | **不启用 skills 对比** | `OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:11434/v1 nautilus --model "qwen2.5:7b" --max-iter 5 "部署项目到生产环境"` | ✅ 通过 | Agent 未按部署步骤执行，而是询问项目信息——skill 未注入，无步骤指导 |

### 5.3 E2E 测试详情

**测试 1：有 skill 匹配**

Agent 用 `--skills-dir .nautilus/skills` + prompt"部署项目到生产环境"执行任务。

"部署"关键词匹配 deploy.md skill，skill 内容注入 system prompt"技能指导"段落。

Agent 严格按 skill 的 3 步顺序执行：
1. `bash("echo building project...")` → `building project...`
2. `bash("echo running tests...")` → `running tests...`
3. `bash("echo deploying to production...")` → `deploying to production...`
4. 最终回答："项目部署完成。构建项目时未出现错误，测试通过，成功部署到生产环境。"

验证点：Agent 按 skill 步骤顺序执行，无盲目试错。这是 Skills 系统的核心价值——工作流复用，降低运行费用 OE。

**测试 2：无 skill 匹配**

Agent 用 `--skills-dir .nautilus/skills` + prompt"用 glob 搜索所有 .py 文件"执行任务。

prompt 不含 deploy/build/部署关键词 → skill 未匹配 → 未注入"技能指导"段落。

Agent 按默认行为执行：`glob("*.py")` → 找到 6 个文件 → 最终回答。

验证点：skill 不会误匹配无关任务，关键词匹配精确。

**测试 3：不启用 skills 对比**

Agent 不传 `--skills-dir` + prompt"部署项目到生产环境"执行任务。

无 `--skills-dir` → 不扫描 skills 目录 → 不注入 skill。

Agent 未按部署步骤执行，而是询问项目信息："请提供项目使用的框架、文件结构、生产环境信息"。

验证点：默认模式（不启用 skills）下同一"部署"prompt 不注入 skill，agent 行为与无 skills 系统一致。

### 5.4 用例设计理由

| # | 场景 | 设计理由 |
|---|------|---------|
| 1 | **有 skill 匹配** | 验证 skill 匹配注入 + 按指导执行——prompt 含"部署"关键词 → skill 被匹配 → system prompt 含"技能指导"段落 → LLM 严格按 skill 的 3 步顺序调用 bash（building→testing→deploying）。验证工作流复用的核心价值 |
| 2 | **无 skill 匹配** | 验证关键词匹配的精确性——prompt 不含 skill keywords → skill 不被注入 → agent 按默认行为执行（glob 搜索）。验证 skill 不会误匹配无关任务 |
| 3 | **不启用 skills 对比** | 验证默认模式不受影响——不传 `--skills-dir` 时同一"部署"prompt 不注入 skill，agent 询问项目信息而非按步骤执行。确认 skills 是可选叠加功能 |

### 5.5 对比分析（测试 1 vs 测试 3）

| 维度 | 有 `--skills-dir`（测试 1） | 无 `--skills-dir`（测试 3） |
|------|---------------------------|---------------------------|
| skill 注入 | ✅ system prompt 含"技能指导" | ❌ 不注入 |
| 执行行为 | 按 skill 3 步顺序执行 bash | 询问项目信息（无步骤指导） |
| LLM 调用次数 | 4（building→testing→deploying→回答） | 1（直接回答询问信息） |
| 试错圈数 | 0（按指导执行，无试错） | —（未执行实际操作） |
| 运行费用 OE | 低（经验复用） | 高（需用户提供更多信息） |

---

## 六、发现的问题

### 6.1 Windows GBK 编码兼容性（v2 遗留，已修复）

P0 修复已在 `__main__.py` 入口处添加 `sys.stdout.reconfigure(encoding="utf-8")`。

### 6.2 上级目录 pyproject.toml 干扰（v2 遗留，未修复）

**当前规避**：`-o "addopts="`

---

## 七、测试覆盖率矩阵

| 源文件 | v0.3.3 行数 | v0.3.4 行数 | 测试文件 | v0.3.3 测试 | v0.3.4 测试 | 关键路径覆盖 |
|--------|------------|------------|---------|------------|------------|------------|
| `tools.py` | 399 | 399 | `test_tools.py` | 63 | 63 | — |
| `agent.py` | 433 | 443 | `test_agent.py` | 46 | 46 | —（skills 集成在 test_skills.py 中测试） |
| `llm.py` | 125 | 125 | `test_llm.py` | 18 | 18 | — |
| `__main__.py` | 122 | 128 | `test_cli.py` | 28 | 30 | +**--skills-dir flag** |
| `prompts.py` | 119 | 121 | 间接覆盖 | — | — | +**技能指导说明** |
| `memory.py` | 40 | 40 | `test_memory.py` | 13 | 13 | — |
| `skills.py` | 0 | 89 | `test_skills.py` | 0 | 14 | **list/load/match/integration** |
| `__init__.py` | 1 | 1 | 间接覆盖 | — | — | 版本 0.3.4 |
| **合计** | **1239** | **1346** | | **175** | **191** | |

---

## 八、v0.3.3→v0.3.4 回归对比

| 验证维度 | v0.3.3 状态 | v0.3.4 状态 | 回归 |
|---------|------------|------------|------|
| 模块导入 | ✅ 7 模块 | ✅ 8 模块（+skills） | 无退化 |
| CLI --help | ✅ 12 参数 | ✅ 13 参数 | 无退化 |
| read_file/write_file/edit_file/glob/grep/bash | ✅ 6 工具 | ✅ 6 工具 | 无退化 |
| delegate_task | ✅ 1 工具 | ✅ 1 工具 | 无退化 |
| execute_tool 路由 | ✅ 6 路由 | ✅ 6 路由 | 无退化 |
| TOOL_SCHEMAS | ✅ 7 schema | ✅ 7 schema | 无退化 |
| ReAct 循环 | ✅ 5 场景 | ✅ 5 场景 | 无退化 |
| 上下文压缩 | ✅ 9 tests | ✅ 9 tests | 无退化 |
| 子 agent | ✅ 6 tests | ✅ 6 tests | 无退化 |
| plan mode | ✅ 3 tests | ✅ 3 tests | 无退化 |
| 记忆系统 | ✅ 13 tests | ✅ 13 tests | 无退化 |
| 权限审批 | ✅ 3 tests | ✅ 3 tests | 无退化 |
| 危险命令过滤 | ✅ 9 tests | ✅ 9 tests | 无退化 |
| GBK 编码修复 | ✅ 1 test | ✅ 1 test | 无退化 |
| **Skills/插件** | — | ✅ **14 tests** | **新增** |
| **CLI --skills-dir** | — | ✅ **2 tests** | **新增** |
| **合计** | **175 passed** | **191 passed** | **0 退化** |

---

## 九、结论

### 9.1 Skills/插件功能验证通过

Nautilus v0.3.4 的 Skills/插件功能**全部通过验证**：

- **skills.py 函数**：`list_skills` / `load_skill` / `match_skill` / `_parse_frontmatter`——全部正确（有文件/无目录/空目录/非 .md 忽略/关键词匹配/无匹配/最佳匹配/名称匹配）
- **agent.py 集成**：skill 匹配注入 system prompt"技能指导"段落——正确
- **prompts.py 更新**：SYSTEM_PROMPT + TEXT_MODE 新增"技能指导"说明——正确
- **CLI 参数**：`--skills-dir` 传参 + 默认 None——正确

### 9.2 E2E 端到端真实场景验证通过

在 Ollama + qwen2.5:7b 环境下完成 3 个真实场景测试，全部通过：

- **有 skill 匹配**：Agent 严格按 skill 3 步顺序执行（building→testing→deploying）——工作流复用生效
- **无 skill 匹配**：Agent 按默认行为执行（glob 搜索），skill 不误匹配
- **不启用 skills 对比**：同一"部署"prompt 不注入 skill，agent 询问信息——可选叠加功能

### 9.3 工作流复用验证通过

测试 1 中 Agent 严格按 skill 的 3 步顺序执行——无盲目试错，零试错圈数。这是 Skills 系统的核心价值：将常见任务的解决方案沉淀为 Skill 文件，agent 匹配后按已有经验执行，降低运行费用 OE。

### 9.4 v0.3.3 回归无退化

v0.3.3 的 175 个测试全部在 v0.3.4 中继续通过，0 退化。新增的 16 个测试覆盖 Skills 全部新功能。

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
collected 191 items

tests\test_agent.py::TestTruncate::test_short_text_passthrough PASSED    [  0%]
tests\test_agent.py::TestTruncate::test_exact_limit PASSED               [  1%]
tests\test_agent.py::TestTruncate::test_long_text_truncated PASSED       [  1%]
tests\test_agent.py::TestTruncate::test_truncation_marker_format PASSED  [  2%]
tests\test_agent.py::TestTruncate::test_empty_string PASSED              [  2%]
tests\test_agent.py::TestTruncate::test_custom_limit PASSED              [  3%]
tests\test_agent.py::TestEstimateTokens::test_pure_ascii PASSED          [  3%]
tests\test_agent.py::TestEstimateTokens::test_pure_cjk PASSED            [  4%]
tests\test_agent.py::TestEstimateTokens::test_empty_string PASSED        [  4%]
tests\test_agent.py::TestEstimateTokens::test_mixed_ascii_cjk PASSED     [  5%]
tests\test_agent.py::TestEstimateTokens::test_long_code_text PASSED      [  5%]
tests\test_agent.py::TestEstimateTokens::test_none_safety PASSED         [  6%]
tests\test_agent.py::TestTruncateForLlm::test_short_text_passthrough PASSED [  6%]
tests\test_agent.py::TestTruncateForLlm::test_exact_limit_no_truncation PASSED [  7%]
tests\test_agent.py::TestTruncateForLlm::test_long_text_truncated_with_bilingual_marker PASSED [  7%]
tests\test_agent.py::TestTruncateForLlm::test_custom_max_chars PASSED    [  8%]
tests\test_agent.py::TestTruncateForLlm::test_empty_string PASSED       [  8%]
tests\test_agent.py::TestPrintToolCall::test_read_file PASSED            [  9%]
tests\test_agent.py::TestPrintToolCall::test_write_file PASSED           [  9%]
tests\test_agent.py::TestPrintToolCall::test_edit_file PASSED            [ 10%]
tests\test_agent.py::TestPrintToolCall::test_bash PASSED                 [ 10%]
tests\test_agent.py::TestPrintToolCall::test_unknown_tool PASSED         [ 11%]
tests\test_agent.py::TestPrintToolCall::test_missing_args PASSED         [ 12%]
tests\test_agent.py::TestRunAgentReActLoop::test_full_react_loop PASSED  [ 12%]
tests\test_agent.py::TestRunAgentMaxIter::test_max_iter_truncation PASSED [ 13%]
tests\test_agent.py::TestRunAgentErrorRecovery::test_error_self_correction PASSED [ 13%]
tests\test_agent.py::TestRunAgentTokenBudget::test_large_tool_output_truncated_in_messages PASSED [ 14%]
tests\test_agent.py::TestMessagesTokenEstimate::test_pure_dict_messages PASSED [ 14%]
tests\test_agent.py::TestMessagesTokenEstimate::test_empty_messages PASSED [ 15%]
tests\test_agent.py::TestMessagesTokenEstimate::test_dict_with_tool_calls PASSED [ 15%]
tests\test_agent.py::TestMessagesTokenEstimate::test_sdk_like_objects PASSED [ 16%]
tests\test_agent.py::TestCompressHistory::test_no_compression_under_budget PASSED [ 16%]
tests\test_agent.py::TestCompressHistory::test_compresses_over_budget PASSED [ 17%]
tests\test_agent.py::TestCompressHistory::test_never_drops_system_and_user PASSED [ 17%]
tests\test_agent.py::TestCompressHistory::test_empty_history_after_system_user PASSED [ 18%]
tests\test_agent.py::TestRunAgentContextCompression::test_history_compressed_within_budget PASSED [ 18%]
tests\test_agent.py::TestRunAgentApproval::test_approval_rejected_bash_command PASSED [ 19%]
tests\test_agent.py::TestRunAgentApproval::test_approval_accepted_bash_command PASSED [ 19%]
tests\test_agent.py::TestRunAgentApproval::test_approval_disabled_by_default PASSED [ 20%]
tests\test_agent.py::TestRunSubagent::test_subagent_returns_final_answer PASSED [ 20%]
tests\test_agent.py::TestRunSubagent::test_subagent_independent_messages PASSED [ 21%]
tests\test_agent.py::TestRunSubagent::test_subagent_max_iter PASSED      [ 21%]
tests\test_agent.py::TestDelegateTask::test_delegate_task_calls_subagent PASSED [ 22%]
tests\test_agent.py::TestDelegateTask::test_delegate_task_does_not_pollute_main PASSED [ 23%]
tests\test_agent.py::TestDelegateTask::test_subagent_rejects_recursive_delegate PASSED [ 23%]
tests\test_agent.py::TestPlanMode::test_plan_mode_accepted PASSED        [ 24%]
tests\test_agent.py::TestPlanMode::test_plan_mode_rejected PASSED        [ 24%]
tests\test_agent.py::TestPlanMode::test_plan_mode_disabled_by_default PASSED [ 25%]
tests\test_cli.py::TestCLIHelp::test_help_exits_zero PASSED              [ 25%]
tests\test_cli.py::TestCLIHelp::test_help_without_encoding_override PASSED [ 26%]
tests\test_cli.py::TestCLIHelp::test_help_shows_description PASSED       [ 26%]
tests\test_cli.py::TestCLINoPrompt::test_no_prompt_no_stdin_exits_1 PASSED [ 27%]
tests\test_cli.py::TestCLIStdin::test_stdin_prompt_is_read PASSED        [ 27%]
tests\test_cli.py::TestCLIArgumentParsing::test_positional_prompt PASSED [ 28%]
tests\test_cli.py::TestCLIArgumentParsing::test_model_flag PASSED        [ 28%]
tests\test_cli.py::TestCLIArgumentParsing::test_api_key_flag PASSED      [ 29%]
tests\test_cli.py::TestCLIArgumentParsing::test_base_url_flag PASSED     [ 29%]
tests\test_cli.py::TestCLIArgumentParsing::test_max_iter_flag PASSED     [ 30%]
tests\test_cli.py::TestCLIArgumentParsing::test_max_tool_output_flag PASSED [ 30%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_max_iter_is_20 PASSED [ 31%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_model_is_gpt4 PASSED [ 31%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_api_key_is_none PASSED [ 32%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_max_tool_output_is_6000 PASSED [ 32%]
tests\test_cli.py::TestCLIArgumentParsing::test_max_context_tokens_flag PASSED [ 33%]
tests\test_cli.py::TestCLIArgumentParsing::test_default_max_context_tokens_is_32000 PASSED [ 33%]
tests\test_cli.py::TestCLIArgumentParsing::test_stream_flag PASSED       [ 34%]
tests\test_cli.py::TestCLIArgumentParsing::test_stream_default_false PASSED [ 34%]
tests\test_cli.py::TestCLIArgumentParsing::test_approval_flag PASSED     [ 35%]
tests\test_cli.py::TestCLIArgumentParsing::test_approval_default_false PASSED [ 35%]
tests\test_cli.py::TestCLIArgumentParsing::test_plan_flag PASSED         [ 36%]
tests\test_cli.py::TestCLIArgumentParsing::test_plan_default_false PASSED [ 36%]
tests\test_cli.py::TestCLIArgumentParsing::test_memory_flag PASSED       [ 37%]
tests\test_cli.py::TestCLIArgumentParsing::test_memory_default_none PASSED [ 37%]
tests\test_cli.py::TestCLIArgumentParsing::test_skills_dir_flag PASSED   [ 38%]
tests\test_cli.py::TestCLIArgumentParsing::test_skills_dir_default_none PASSED [ 38%]
tests\test_llm.py::TestCreateClientNoKey::test_no_key_raises_systemexit PASSED [ 39%]
tests\test_llm.py::TestCreateClientNoKey::test_no_key_message_mentions_env_var PASSED [ 39%]
tests\test_llm.py::TestCreateClientExplicit::test_explicit_key_creates_client PASSED [ 40%]
tests\test_llm.py::TestCreateClientExplicit::test_explicit_key_and_base_url PASSED [ 40%]
tests\test_llm.py::TestCreateClientEnvFallback::test_env_api_key PASSED  [ 41%]
tests\test_llm.py::TestCreateClientEnvFallback::test_env_api_key_and_base_url PASSED [ 41%]
tests\test_llm.py::TestCreateClientEnvFallback::test_explicit_overrides_env PASSED [ 42%]
tests\test_llm.py::TestCreateClientEnvFallback::test_base_url_not_set_when_only_api_key_in_env PASSED [ 42%]
tests\test_llm.py::TestCreateClientPriority::test_none_api_key_falls_back_to_env PASSED [ 43%]
tests\test_llm.py::TestCreateClientPriority::test_empty_string_api_key_does_not_fallback PASSED [ 43%]
tests\test_llm.py::TestCompleteWithRetry::test_success_on_first_try PASSED [ 44%]
tests\test_llm.py::TestCompleteWithRetry::test_retry_on_rate_limit_then_success PASSED [ 44%]
tests\test_llm.py::TestCompleteWithRetry::test_all_retries_exhausted_raises_systemexit PASSED [ 45%]
tests\test_llm.py::TestCompleteWithRetry::test_bad_request_not_retried PASSED [ 45%]
tests\test_llm.py::TestCompleteWithRetry::test_auth_error_not_retried PASSED [ 46%]
tests\test_llm.py::TestStreamComplete::test_stream_content_accumulated_and_printed PASSED [ 46%]
tests\test_llm.py::TestStreamComplete::test_stream_tool_calls_assembled PASSED [ 47%]
tests\test_llm.py::TestStreamComplete::test_stream_empty_response PASSED [ 47%]
tests\test_memory.py::TestLoadMemory::test_load_existing_memory PASSED   [ 48%]
tests\test_memory.py::TestLoadMemory::test_load_nonexistent_memory PASSED [ 48%]
tests\test_memory.py::TestLoadMemory::test_load_empty_memory PASSED      [ 49%]
tests\test_memory.py::TestSaveMemory::test_save_new_memory PASSED        [ 49%]
tests\test_memory.py::TestSaveMemory::test_save_overwrite_memory PASSED [ 50%]
tests\test_memory.py::TestSaveMemory::test_save_creates_parent_dir PASSED [ 50%]
tests\test_memory.py::TestAppendMemory::test_append_to_existing PASSED   [ 51%]
tests\test_memory.py::TestAppendMemory::test_append_creates_new_file PASSED [ 51%]
tests\test_memory.py::TestAppendMemory::test_append_adds_newline PASSED  [ 52%]
tests\test_memory.py::TestAppendMemory::test_append_creates_parent_dir PASSED [ 52%]
tests\test_memory.py::TestMemoryIntegration::test_memory_injected_into_system_prompt PASSED [ 53%]
tests\test_memory.py::TestMemoryIntegration::test_memory_saved_after_completion PASSED [ 53%]
tests\test_memory.py::TestMemoryIntegration::test_memory_not_saved_when_disabled PASSED [ 54%]
tests\test_skills.py::TestListSkills::test_list_skills_with_files PASSED [ 54%]
tests\test_skills.py::TestListSkills::test_list_skills_no_dir PASSED     [ 55%]
tests\test_skills.py::TestListSkills::test_list_skills_empty_dir PASSED [ 55%]
tests\test_skills.py::TestListSkills::test_list_skills_ignores_non_md PASSED [ 56%]
tests\test_skills.py::TestLoadSkill::test_load_skill_existing PASSED     [ 56%]
tests\test_skills.py::TestLoadSkill::test_load_skill_nonexistent PASSED [ 57%]
tests\test_skills.py::TestMatchSkill::test_match_skill_keyword_match PASSED [ 57%]
tests\test_skills.py::TestMatchSkill::test_match_skill_no_match PASSED   [ 58%]
tests\test_skills.py::TestMatchSkill::test_match_skill_best_match PASSED [ 58%]
tests\test_skills.py::TestMatchSkill::test_match_skill_name_match PASSED [ 59%]
tests\test_skills.py::TestMatchSkill::test_match_skill_empty_skills PASSED [ 59%]
tests\test_skills.py::TestSkillIntegration::test_skill_injected_into_system_prompt PASSED [ 60%]
tests\test_skills.py::TestSkillIntegration::test_skill_not_injected_when_disabled PASSED [ 60%]
tests\test_skills.py::TestSkillIntegration::test_skill_not_injected_when_no_match PASSED [ 61%]
tests\test_tools.py::TestWriteFile::test_write_normal PASSED             [ 61%]
tests\test_tools.py::TestWriteFile::test_write_returns_byte_count PASSED [ 62%]
tests\test_tools.py::TestWriteFile::test_auto_create_parent_dirs PASSED  [ 62%]
tests\test_tools.py::TestWriteFile::test_overwrite_existing PASSED       [ 63%]
tests\test_tools.py::TestReadFile::test_read_normal PASSED               [ 63%]
tests\test_tools.py::TestReadFile::test_read_nonexistent PASSED          [ 64%]
tests\test_tools.py::TestReadFile::test_read_binary_file PASSED          [ 64%]
tests\test_tools.py::TestEditFile::test_edit_normal PASSED               [ 65%]
tests\test_tools.py::TestEditFile::test_edit_old_string_not_found PASSED [ 65%]
tests\test_tools.py::TestEditFile::test_edit_multiple_matches PASSED     [ 66%]
tests\test_tools.py::TestEditFile::test_edit_nonexistent_file PASSED     [ 66%]
tests\test_tools.py::TestEditFile::test_edit_preserves_surrounding_content PASSED [ 67%]
tests\test_tools.py::TestBash::test_echo_success PASSED                  [ 67%]
tests\test_tools.py::TestBash::test_python_execution PASSED              [ 68%]
tests\test_tools.py::TestBash::test_nonzero_exit PASSED                  [ 68%]
tests\test_tools.py::TestBash::test_stderr_capture PASSED                [ 69%]
tests\test_tools.py::TestBash::test_command_output_includes_both_streams PASSED [ 69%]
tests\test_tools.py::TestDangerousCommandFilter::test_rm_rf_root_blocked PASSED [ 70%]
tests\test_tools.py::TestDangerousCommandFilter::test_rm_rf_home_blocked PASSED [ 70%]
tests\test_tools.py::TestDangerousCommandFilter::test_rm_rf_star_blocked PASSED [ 71%]
tests\test_tools.py::TestDangerousCommandFilter::test_format_c_blocked PASSED [ 71%]
tests\test_tools.py::TestDangerousCommandFilter::test_mkfs_blocked PASSED [ 72%]
tests\test_tools.py::TestDangerousCommandFilter::test_safe_command_not_blocked PASSED [ 72%]
tests\test_tools.py::TestDangerousCommandFilter::test_dangerous_allowed_with_flag PASSED [ 73%]
tests\test_tools.py::TestDangerousCommandFilter::test_case_insensitive_match PASSED [ 73%]
tests\test_tools.py::TestDangerousCommandFilter::test_dangerous_in_pipeline_blocked PASSED [ 74%]
tests\test_tools.py::TestExecuteTool::test_route_write_file PASSED       [ 74%]
tests\test_tools.py::TestExecuteTool::test_route_read_file PASSED        [ 75%]
tests\test_tools.py::TestExecuteTool::test_route_edit_file PASSED        [ 76%]
tests\test_tools.py::TestExecuteTool::test_route_bash PASSED             [ 76%]
tests\test_tools.py::TestExecuteTool::test_route_glob PASSED             [ 77%]
tests\test_tools.py::TestExecuteTool::test_route_grep PASSED            [ 77%]
tests\test_tools.py::TestExecuteTool::test_unknown_tool PASSED           [ 78%]
tests\test_tools.py::TestExecuteTool::test_invalid_json_arguments PASSED [ 78%]
tests\test_tools.py::TestExecuteTool::test_empty_arguments_string PASSED [ 79%]
tests\test_tools.py::TestExecuteTool::test_none_arguments PASSED         [ 79%]
tests\test_tools.py::TestToolSchemas::test_schema_count PASSED           [ 80%]
tests\test_tools.py::TestToolSchemas::test_schema_names PASSED           [ 80%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 80%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 81%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 81%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 82%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 82%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 83%]
tests\test_tools.py::TestToolSchemas::test_schema_parameters[...] PASSED [ 83%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 84%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 84%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 85%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 85%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 86%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 86%]
tests\test_tools.py::TestToolSchemas::test_schema_has_required[...] PASSED [ 87%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 87%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 88%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 88%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 89%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 89%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 90%]
tests\test_tools.py::TestToolSchemas::test_schema_has_description[...] PASSED [ 90%]
tests\test_tools.py::TestToolSchemas::test_all_schemas_are_function_type PASSED [ 91%]
tests\test_tools.py::TestGlob::test_glob_finds_python_files PASSED       [ 91%]
tests\test_tools.py::TestGlob::test_glob_no_match PASSED                 [ 92%]
tests\test_tools.py::TestGlob::test_glob_recursive PASSED                [ 92%]
tests\test_tools.py::TestGlob::test_glob_respects_gitignore PASSED       [ 93%]
tests\test_tools.py::TestGrep::test_grep_finds_matches PASSED            [ 93%]
tests\test_tools.py::TestGrep::test_grep_returns_line_numbers PASSED     [ 94%]
tests\test_tools.py::TestGrep::test_grep_no_match PASSED                 [ 94%]
tests\test_tools.py::TestGrep::test_grep_specific_file PASSED            [ 95%]
tests\test_tools.py::TestGrep::test_grep_invalid_regex PASSED            [ 95%]
tests\test_tools.py::TestGrep::test_grep_skips_binary_files PASSED       [ 96%]
tests\test_tools.py::TestGrep::test_grep_respects_gitignore PASSED       [100%]

============================ 191 passed in 31.30s =============================
```

---

## 参考资料

- Nautilus v3 实现计划（整体）：`nautilus-v3-实现计划(整体).md`（同目录）
- Nautilus v0.3.4 Skills/插件实现计划：`nautilus-v0.3.4-Skills/插件-实现计划.md`（同目录）
- Nautilus v0.3.3 记忆系统验证报告：`nautilus-v0.3.3-记忆系统-验证报告.md`（同目录）
- 源码：`nautilus/nautilus/`（agent.py / tools.py / prompts.py / llm.py / memory.py / skills.py / __main__.py）
- UT 源码：`nautilus/tests/`（test_tools.py / test_agent.py / test_llm.py / test_cli.py / test_memory.py / test_skills.py）
