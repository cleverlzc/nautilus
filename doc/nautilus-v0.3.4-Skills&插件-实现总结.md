# Nautilus v0.3.4 Skills/插件 — 实现总结

## 文件清单（实际）

**9 个源码文件 + 6 个测试文件**，位于 `...\AIAgent\mycodingagent\nautilus\`：

| 文件 | v0.3.3 行数 | v0.3.4 行数 | 职责 |
|------|------------|------------|------|
| `pyproject.toml` | 16 | 16 | 项目元数据 + openai 依赖 + CLI 入口（版本 0.3.4） |
| `nautilus/__init__.py` | 1 | 1 | 版本号（0.3.4） |
| `nautilus/skills.py` | 0 | 89 | **新文件**：`list_skills()` + `load_skill()` + `match_skill()` + `_read_file()` + `_parse_frontmatter()` |
| `nautilus/memory.py` | 40 | 40 | `load_memory()` + `save_memory()` + `append_memory()` |
| `nautilus/prompts.py` | 119 | 121 | 系统提示词 + SUBAGENT + PLAN + TEXT_MODE + 记忆/技能说明 |
| `nautilus/tools.py` | 399 | 399 | 7 个工具 + execute_tool 路由 + .gitignore 过滤 + 危险命令过滤 |
| `nautilus/llm.py` | 125 | 125 | OpenAI 兼容 client 工厂 + complete_with_retry + stream_complete |
| `nautilus/agent.py` | 433 | 443 | **核心 ReAct 循环** + token 预算控制 + stream/approval/text_mode/plan_mode 分支 + 上下文压缩 + 子 agent + plan mode + 记忆注入/保存 + **skills 匹配注入** |
| `nautilus/__main__.py` | 122 | 128 | CLI 入口 + GBK 编码修复 + 13 个参数（含 `--skills-dir`） |
| **源码合计** | **1239** | **1346** | |

**总计 1346 行 Python 源码**（v0.3.4 新增约 107 行源码 + 16 个测试，主要是 `skills.py` 新文件 + `run_agent` skills 匹配注入集成 + `--skills-dir` CLI 参数）。

## v0.3.4 新增功能（1 个）

| # | 功能 | 核心实现 |
|---|------|---------|
| 1 | **Skills/插件** | `skills.py` 新文件（89 行）：`list_skills()` 扫描 skills 目录返回 skill 元信息列表（含 name/path/keywords/description/content）+ `load_skill()` 读取 skill 文件 + `match_skill()` 关键词匹配返回最佳 skill 内容 + `_read_file()` + `_parse_frontmatter()` 解析 YAML frontmatter。`agent.py` `run_agent()` 新增 `skills_dir` 参数：启动时 `list_skills` + `match_skill` 匹配当前 prompt，匹配成功则注入 system prompt"技能指导"段落。`prompts.py` 新增"如果系统提示词中包含'技能指导'段落，请按其中的步骤和注意事项执行任务"说明。`__main__.py` 新增 `--skills-dir` CLI 参数 |

### Skill 文件格式

每个 skill 是一个 `.md` 文件，文件名 = skill 名。文件头部可包含 YAML frontmatter：

```markdown
---
keywords: deploy, 部署, build
description: 部署项目到生产环境
---

# 部署项目

1. [bash] 运行 `echo building...` 模拟构建
2. [bash] 运行 `echo testing...` 模拟测试
3. [bash] 运行 `echo deploying...` 模拟部署
```

### 设计要点

- **关键词匹配**：`match_skill` 对 skill 的 keywords + skill 名称与 prompt 做关键词匹配，返回匹配度最高的 skill 内容
- **YAML frontmatter**：`_parse_frontmatter` 解析 `---` 包裹的 keywords 和 description 字段
- **注入 system prompt**：匹配成功时 `system_prompt += "\n\n## 技能指导\n{matched}"`，LLM 在后续循环中参考 skill 步骤
- **可选启用**：`skills_dir=None`（默认）不启用；传 `--skills-dir .nautilus/skills` 启用
- **无匹配不注入**：prompt 不含任何 skill keywords 时 `match_skill` 返回 None，不注入

## 验证结果

### 单元测试

- ✅ 所有模块导入正常（8 模块，含新增 `skills.py`）
- ✅ CLI `--help` 输出正确（13 参数，含 `--skills-dir`）
- ✅ skills.py 函数验证（list 有/无/空/非.md + load 有/无 + match 关键词/无/最佳/名称/空 + frontmatter 解析）
- ✅ skills 集成验证（注入 system prompt / 禁用不注入 / 无匹配不注入 3 种场景）
- ✅ 单元测试 191 passed, 0 failed

### E2E 端到端真实场景（Ollama + qwen2.5:7b）

- ✅ 有 skill 匹配：Agent 严格按 skill 3 步顺序执行（building→testing→deploying）→ 最终回答"项目部署完成"
- ✅ 无 skill 匹配：Agent 直接用 glob 搜索文件（未按部署步骤执行），skill 未匹配未注入
- ✅ 不启用 skills 对比：同一"部署"prompt 不注入 skill，agent 询问项目信息——可选叠加功能

## 测试覆盖

| 测试模块 | v0.3.3 测试数 | v0.3.4 测试数 | 新增内容 |
|---------|------------|------------|---------|
| `test_skills.py` | 0 | 14 | TestListSkills(4) + TestLoadSkill(2) + TestMatchSkill(5) + TestSkillIntegration(3) |
| `test_cli.py` | 28 | 30 | test_skills_dir_flag(1) + test_skills_dir_default_none(1) |
| `test_agent.py` | 46 | 46 | — |
| `test_tools.py` | 63 | 63 | — |
| `test_llm.py` | 18 | 18 | — |
| `test_memory.py` | 13 | 13 | — |
| **合计** | **175** | **191** | **+16** |

## 使用方式

```bash
cd ".../AIAgent/mycodingagent/nautilus"
pip install -e .
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://xxx   # 可选，OpenAI 兼容 API

# v0.3.4 新增：Skills 系统（工作流复用）
# 1. 准备 skill 文件
mkdir -p .nautilus/skills
cat > .nautilus/skills/deploy.md << 'EOF'
---
keywords: deploy, 部署, build
description: 部署项目到生产环境
---

# 部署项目

1. [bash] 运行 `npm run build` 构建项目
2. [bash] 运行 `npm test` 确保测试通过
3. [bash] 运行 `npm run deploy` 部署到生产环境
EOF

# 2. 运行 agent，skill 自动匹配注入
nautilus --skills-dir .nautilus/skills "部署项目到生产环境"

# Skills + 记忆 + plan mode 组合
nautilus --skills-dir .nautilus/skills --memory .nautilus/memory.md --plan "部署项目"

# 不启用 Skills（默认行为）
nautilus "创建一个 hello.py，运行它"

# 运行单元测试
python -m pytest tests/ -v -o "addopts="
```

## 核心洞察

当前 agent 每次执行相似任务时都从零开始——即使上次已经摸索出"部署项目需要先 build 再 test 再 deploy"的流程，下次仍需重新试错。记忆系统保存了任务摘要，但不保存可复用的工作流指导。

v0.3.4 补齐了这个缺口：用户将常见任务的解决方案写为 Skill 文件（markdown），agent 启动时扫描 skills 目录，通过关键词匹配找到与当前 prompt 相关的 skill，将 skill 内容注入 system prompt 的"技能指导"段落。LLM 在后续循环中可参考 skill 的步骤指导执行。

E2E 验证确认：有 skill 匹配时 agent 严格按 skill 步骤顺序执行（building→testing→deploying），零试错圈数；无匹配或不启用时 agent 按默认行为执行。Skills 系统是 v0.3.5 MCP 协议的基础——MCP 扩展工具集，Skills 指导工具使用的工作流。
