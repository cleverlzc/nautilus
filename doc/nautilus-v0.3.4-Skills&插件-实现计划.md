# Nautilus v0.3.4 Skills/插件 — 实现计划

## Context

v0.3.3 已完成记忆系统（1239 行，175 tests + 3 E2E 场景）。`nautilus-v3-特性优先级排序.md` 将 Skills/插件列为 P3 特性，依赖记忆系统做存储。

当前代码基线（v0.3.3）：1239 行 Python 源码 + 175 tests。

v0.3.4 的目标：**让 agent 可复用工作流**——将常见任务的解决方案沉淀为 Skill 文件（如 `.nautilus/skills/deploy.md`），agent 启动时扫描 skills 目录，匹配当前 prompt 的 skill 注入 system prompt，指导 LLM 按已有经验执行。降低重复劳动（ToC：降低运行费用 OE）。

## 项目位置

```
...\AIAgent\mycodingagent\nautilus\
```

## 问题分析

当前 agent 每次执行相似任务时都从零开始——即使上次已经摸索出"部署项目需要先 build 再 test 再 deploy"的流程，下次仍需重新试错。记忆系统保存了任务摘要，但不保存可复用的工作流指导。

Skills 解决方案：用户将常见任务的解决方案写为 Skill 文件（markdown），agent 启动时扫描 skills 目录，通过关键词匹配找到与当前 prompt 相关的 skill，将 skill 内容注入 system prompt 的"技能指导"段落。LLM 在后续循环中可参考 skill 的步骤指导执行。

| 维度 | 无 Skills | 有 Skills |
|------|----------|----------|
| 工作流复用 | ❌ 每次从零试错 | ✅ 注入已有经验指导 |
| 重复劳动 | 每次重新摸索流程 | skill 提供步骤指导 |
| 运行费用 OE | 高（试错迭代多） | 低（按经验执行，减少试错） |

## Skill 文件格式

每个 skill 是一个 `.md` 文件，文件名 = skill 名。文件头部可包含 YAML frontmatter：

```markdown
---
keywords: deploy, build, test
description: 部署项目到生产环境
---

# 部署项目

1. [bash] 运行 `npm run build` 构建项目
2. [bash] 运行 `npm test` 确保测试通过
3. [bash] 运行 `npm run deploy` 部署到生产环境

注意事项：
- build 前确保依赖已安装
- deploy 前确认测试全部通过
```

## 文件清单（5 个文件，含 2 个新文件）

| 文件 | 职责 | 基线行数 | 预估行数 | 变化 |
|------|------|---------|---------|------|
| `nautilus/skills.py` | **新文件**：skills 扫描/加载/匹配 | 0 | ~60 | `list_skills()` + `load_skill()` + `match_skill()` |
| `nautilus/agent.py` | ReAct 循环 + 记忆 + **skills 注入** | 433 | ~450 | +`skills_dir` 参数 + 扫描匹配 + 注入 system prompt |
| `nautilus/prompts.py` | 系统提示词 | 119 | ~125 | +技能指导说明 |
| `nautilus/__main__.py` | CLI 入口 | 122 | ~129 | +`--skills-dir` CLI 参数 |
| `tests/test_skills.py` | **新文件**：skills 测试 | 0 | ~120 | `TestListSkills` + `TestLoadSkill` + `TestMatchSkill` + `TestSkillIntegration` |

## 各文件实现细节

### 1. `nautilus/skills.py` — 新文件（~60 行）

```python
"""Skills system for reusable workflow guidance."""

import os
import re


def list_skills(skills_dir: str = ".nautilus/skills") -> list[dict]:
    """扫描 skills 目录，返回 skill 元信息列表。

    每个 skill 是一个 .md 文件，文件名 = skill 名。
    文件头部可包含 YAML frontmatter: keywords, description。
    """
    skills = []
    if not os.path.isdir(skills_dir):
        return skills
    for name in sorted(os.listdir(skills_dir)):
        if not name.endswith(".md"):
            continue
        path = os.path.join(skills_dir, name)
        content = _read_file(path)
        keywords, description = _parse_frontmatter(content)
        skills.append({
            "name": name[:-3],  # remove .md
            "path": path,
            "keywords": keywords,
            "description": description,
            "content": content,
        })
    return skills


def load_skill(skill_path: str) -> str:
    """读取 skill 文件内容。"""
    return _read_file(skill_path)


def match_skill(prompt: str, skills: list[dict]) -> str | None:
    """简单关键词匹配：skill 的 keywords 与 prompt 重叠则返回 skill 内容。

    返回匹配度最高的 skill 内容，无匹配返回 None。
    """
    best_match = None
    best_score = 0
    prompt_lower = prompt.lower()
    for skill in skills:
        score = 0
        for keyword in skill["keywords"]:
            if keyword.lower() in prompt_lower:
                score += 1
        # 也匹配 skill 名称
        if skill["name"].lower() in prompt_lower:
            score += 1
        if score > best_score:
            best_score = score
            best_match = skill["content"]
    return best_match


def _read_file(path: str) -> str:
    """读取文件内容。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, OSError):
        return ""


def _parse_frontmatter(content: str) -> tuple[list[str], str]:
    """解析 YAML frontmatter，返回 (keywords, description)。

    格式：
    ---
    keywords: deploy, build, test
    description: 部署项目
    ---
    """
    keywords = []
    description = ""
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return keywords, description
    frontmatter = match.group(1)
    for line in frontmatter.split("\n"):
        line = line.strip()
        if line.lower().startswith("keywords:"):
            raw = line.split(":", 1)[1].strip()
            keywords = [k.strip() for k in raw.split(",") if k.strip()]
        elif line.lower().startswith("description:"):
            description = line.split(":", 1)[1].strip()
    return keywords, description
```

### 2. `nautilus/agent.py` — 核心修改

**修改 `run_agent()` 签名**：

```python
def run_agent(
    ...
    memory_path: str | None = None,
    skills_dir: str | None = None,  # NEW: None = 不启用 skills
) -> None:
```

**修改函数体——加载匹配的 skill 注入 system prompt**：

在记忆注入之后、plan mode 之前：

```python
    # Load memory and inject into system prompt
    if memory_path:
        memory = load_memory(memory_path)
        if memory:
            system_prompt += f"\n\n## 项目记忆\n{memory}"

    # Load matching skill and inject into system prompt
    if skills_dir:
        from .skills import list_skills, match_skill
        skills = list_skills(skills_dir)
        if skills:
            matched = match_skill(prompt, skills)
            if matched:
                system_prompt += f"\n\n## 技能指导\n{matched}"
```

**import 新增**：

```python
from .skills import list_skills, match_skill
```

### 3. `nautilus/prompts.py` — 新增技能说明

在 `SYSTEM_PROMPT` 和 `SYSTEM_PROMPT_TEXT_MODE` 的记忆说明之后新增：

```
如果系统提示词中包含"技能指导"段落，请按其中的步骤和注意事项执行任务。
```

### 4. `nautilus/__main__.py` — 新增 --skills-dir CLI 参数

```python
parser.add_argument(
    "--skills-dir",
    default=None,
    help="启用 Skills 系统，指定 skills 目录路径（如 .nautilus/skills）。不传则不启用。",
)
```

传到 `run_agent`：

```python
run_agent(
    ...
    skills_dir=args.skills_dir,
)
```

### 5. `tests/test_skills.py` — 新文件（~120 行）

**TestListSkills（4 tests）**：

| 测试 | 覆盖场景 |
|------|---------|
| `test_list_skills_with_files` | 有 .md 文件 → 返回 skill 列表（含 name/path/keywords/description/content） |
| `test_list_skills_no_dir` | 目录不存在 → 返回空列表 |
| `test_list_skills_empty_dir` | 空目录 → 返回空列表 |
| `test_list_skills_ignores_non_md` | 非 .md 文件被忽略 |

**TestLoadSkill（2 tests）**：

| 测试 | 覆盖场景 |
|------|---------|
| `test_load_skill_existing` | 正常读取 skill 文件内容 |
| `test_load_skill_nonexistent` | 文件不存在 → 返回空字符串 |

**TestMatchSkill（4 tests）**：

| 测试 | 覆盖场景 |
|------|---------|
| `test_match_skill_keyword_match` | prompt 含 skill keyword → 返回 skill 内容 |
| `test_match_skill_no_match` | prompt 不含任何 keyword → 返回 None |
| `test_match_skill_best_match` | 多 skill 匹配 → 返回匹配度最高的 |
| `test_match_skill_name_match` | prompt 含 skill 名称 → 返回 skill 内容 |

**TestSkillIntegration（2 tests）**：

| 测试 | 覆盖场景 |
|------|---------|
| `test_skill_injected_into_system_prompt` | mock LLM 捕获 messages，验证 system prompt 含"技能指导"段落 + skill 内容 |
| `test_skill_not_injected_when_disabled` | `skills_dir=None` → 验证 system prompt 不含"技能指导" |

## 版本号更新

| 文件 | 变更 |
|------|------|
| `nautilus/__init__.py` | `0.3.3` → `0.3.4` |
| `pyproject.toml` | `version = "0.3.3"` → `version = "0.3.4"` |

## CLI 参数

v0.3.4 新增 1 个参数（共 13 个）：

```
$ nautilus --skills-dir .nautilus/skills "部署项目到生产环境"
$ nautilus --skills-dir .nautilus/skills --memory .nautilus/memory.md "部署项目"
$ nautilus "不启用 skills 的任务"  # 不传 --skills-dir 则不启用
```

参数（v0.3.4 新增 1 个，共 13 个）：
- `prompt` / `--model` / `--api-key` / `--base-url` / `--max-iter` / `--max-tool-output` / `--max-context-tokens` / `--stream` / `--approval` / `--text-mode` / `--plan` / `--memory`
- `--skills-dir`（默认 None，不启用）**← v0.3.4 新增**

## 终端输出格式

Skills 是内部注入机制，不直接改变终端输出格式。当 skill 被匹配注入时，LLM 的行为会受 skill 指导影响——例如按 skill 中的步骤顺序调用工具。

## 不修改的文件

- `nautilus/llm.py`：不涉及
- `nautilus/tools.py`：不涉及（skills 不是工具，是 system prompt 注入）
- `nautilus/memory.py`：不涉及
- `pyproject.toml` 依赖列表：无新依赖（仅用 stdlib os, re）

## 验证方式

1. `pip install -e .` 安装
2. 运行单元测试：
   ```bash
   PYTHONIOENCODING=utf-8 python -m pytest tests/ -v -o "addopts="
   ```
3. 预期结果：175 + ~12 新增 = ~187 tests 全部通过
4. E2E 测试（Ollama + qwen2.5:7b）：
   ```bash
   # 准备 skill 文件
   mkdir -p .nautilus/skills
   cat > .nautilus/skills/deploy.md << 'EOF'
   ---
   keywords: deploy, 部署, build
   description: 部署项目到生产环境
   ---

   # 部署项目

   1. [bash] 运行 `echo building...` 模拟构建
   2. [bash] 运行 `echo testing...` 模拟测试
   3. [bash] 运行 `echo deploying...` 模拟部署
   EOF

   # 运行 agent，验证 skill 被匹配注入
   OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
   nautilus --model "qwen2.5:7b" --max-iter 10 \
   --skills-dir .nautilus/skills \
   "部署项目到生产环境"
   ```
5. 验证：agent 按 skill 步骤执行（building→testing→deploying），而非盲目试错
