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
            "name": name[:-3],
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
