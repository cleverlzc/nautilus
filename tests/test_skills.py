"""Unit tests for nautilus.skills — skills system.

Covers:
- list_skills: with files / no dir / empty dir / non-md ignored
- load_skill: existing / nonexistent
- match_skill: keyword match / no match / best match / name match
- Skill integration: injection into system prompt / disabled
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from nautilus.skills import list_skills, load_skill, match_skill


# ---------------------------------------------------------------------------
# list_skills tests
# ---------------------------------------------------------------------------

class TestListSkills:
    def test_list_skills_with_files(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "deploy.md").write_text(
            "---\nkeywords: deploy, build\ndescription: 部署项目\n---\n\n# 部署\n步骤",
            encoding="utf-8",
        )
        (skills_dir / "test.md").write_text(
            "---\nkeywords: test, 测试\ndescription: 测试项目\n---\n\n# 测试",
            encoding="utf-8",
        )

        skills = list_skills(str(skills_dir))
        assert len(skills) == 2
        names = {s["name"] for s in skills}
        assert names == {"deploy", "test"}
        deploy = next(s for s in skills if s["name"] == "deploy")
        assert "deploy" in deploy["keywords"]
        assert "build" in deploy["keywords"]
        assert deploy["description"] == "部署项目"
        assert "步骤" in deploy["content"]

    def test_list_skills_no_dir(self, tmp_path):
        skills = list_skills(str(tmp_path / "nonexistent"))
        assert skills == []

    def test_list_skills_empty_dir(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skills = list_skills(str(skills_dir))
        assert skills == []

    def test_list_skills_ignores_non_md(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "deploy.md").write_text("---\nkeywords: deploy\n---\n\n# 部署", encoding="utf-8")
        (skills_dir / "notes.txt").write_text("not a skill", encoding="utf-8")
        (skills_dir / "README.md").write_text("---\nkeywords: readme\n---\n\n# readme", encoding="utf-8")

        skills = list_skills(str(skills_dir))
        assert len(skills) == 2  # deploy.md + README.md, not notes.txt


# ---------------------------------------------------------------------------
# load_skill tests
# ---------------------------------------------------------------------------

class TestLoadSkill:
    def test_load_skill_existing(self, tmp_path):
        path = tmp_path / "deploy.md"
        path.write_text("# 部署\n步骤", encoding="utf-8")
        result = load_skill(str(path))
        assert "部署" in result
        assert "步骤" in result

    def test_load_skill_nonexistent(self, tmp_path):
        result = load_skill(str(tmp_path / "nonexistent.md"))
        assert result == ""


# ---------------------------------------------------------------------------
# match_skill tests
# ---------------------------------------------------------------------------

class TestMatchSkill:
    def test_match_skill_keyword_match(self):
        skills = [
            {"name": "deploy", "keywords": ["deploy", "部署"], "content": "部署步骤"},
            {"name": "test", "keywords": ["test", "测试"], "content": "测试步骤"},
        ]
        result = match_skill("请帮我部署项目", skills)
        assert result == "部署步骤"

    def test_match_skill_no_match(self):
        skills = [
            {"name": "deploy", "keywords": ["deploy", "部署"], "content": "部署步骤"},
        ]
        result = match_skill("帮我写一个 hello.py", skills)
        assert result is None

    def test_match_skill_best_match(self):
        skills = [
            {"name": "deploy", "keywords": ["deploy"], "content": "部署"},
            {"name": "build_deploy", "keywords": ["build", "deploy", "test"], "content": "构建+部署+测试"},
        ]
        # "deploy" skill: keyword "deploy" matches (1) + name "deploy" matches (1) = 2
        # "build_deploy" skill: keywords "build"(1) + "deploy"(1) + "test"(0) = 2; name doesn't fully match = 2
        # Tie → first wins. Let's make it clearly better:
        skills = [
            {"name": "deploy", "keywords": ["deploy"], "content": "仅部署"},
            {"name": "build_deploy", "keywords": ["build", "deploy", "test"], "content": "构建+部署+测试"},
        ]
        result = match_skill("帮我 build 并 deploy 和 test 项目", skills)
        # build_deploy: build(1) + deploy(1) + test(1) = 3 > deploy: deploy(1) + name(1) = 2
        assert result == "构建+部署+测试"

    def test_match_skill_name_match(self):
        skills = [
            {"name": "deploy", "keywords": [], "content": "部署步骤"},
        ]
        result = match_skill("请执行 deploy 流程", skills)
        assert result == "部署步骤"

    def test_match_skill_empty_skills(self):
        result = match_skill("any prompt", [])
        assert result is None


# ---------------------------------------------------------------------------
# Skill integration tests
# ---------------------------------------------------------------------------

class TestSkillIntegration:
    """Test skill injection into system prompt."""

    def test_skill_injected_into_system_prompt(self, tmp_path, capsys, monkeypatch):
        """Matching skill content should appear in system prompt."""
        monkeypatch.chdir(tmp_path)
        skills_dir = ".nautilus/skills"
        os.makedirs(skills_dir)
        with open(f"{skills_dir}/deploy.md", "w", encoding="utf-8") as f:
            f.write("---\nkeywords: deploy, 部署\n---\n\n# 部署\n1. [bash] build\n2. [bash] deploy")

        captured_messages = []

        def mock_create_fn(**kwargs):
            msgs = kwargs.get("messages", [])
            captured_messages.append(list(msgs))
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content="done", tool_calls=None))]
            )

        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create_fn

        with patch("nautilus.agent.create_client", return_value=mock_client):
            from nautilus.agent import run_agent
            run_agent(
                prompt="部署项目到生产环境",
                model="mock-model",
                api_key="sk-fake",
                max_iter=5,
                skills_dir=skills_dir,
            )

        assert len(captured_messages) >= 1
        system_msg = captured_messages[0][0]
        system_content = system_msg.get("content", "") if isinstance(system_msg, dict) else ""
        assert "技能指导" in system_content
        assert "部署" in system_content
        assert "build" in system_content

    def test_skill_not_injected_when_disabled(self, tmp_path, capsys, monkeypatch):
        """When skills_dir=None, no skill content in system prompt."""
        monkeypatch.chdir(tmp_path)

        captured_messages = []

        def mock_create_fn(**kwargs):
            msgs = kwargs.get("messages", [])
            captured_messages.append(list(msgs))
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content="done", tool_calls=None))]
            )

        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create_fn

        with patch("nautilus.agent.create_client", return_value=mock_client):
            from nautilus.agent import run_agent
            run_agent(
                prompt="部署项目",
                model="mock-model",
                api_key="sk-fake",
                max_iter=5,
                skills_dir=None,
            )

        assert len(captured_messages) >= 1
        system_msg = captured_messages[0][0]
        system_content = system_msg.get("content", "") if isinstance(system_msg, dict) else ""
        assert "## 技能指导" not in system_content

    def test_skill_not_injected_when_no_match(self, tmp_path, capsys, monkeypatch):
        """When no skill matches the prompt, no skill content injected."""
        monkeypatch.chdir(tmp_path)
        skills_dir = ".nautilus/skills"
        os.makedirs(skills_dir)
        with open(f"{skills_dir}/deploy.md", "w", encoding="utf-8") as f:
            f.write("---\nkeywords: deploy, 部署\n---\n\n# 部署\n步骤")

        captured_messages = []

        def mock_create_fn(**kwargs):
            msgs = kwargs.get("messages", [])
            captured_messages.append(list(msgs))
            return MagicMock(
                choices=[MagicMock(message=MagicMock(content="done", tool_calls=None))]
            )

        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create_fn

        with patch("nautilus.agent.create_client", return_value=mock_client):
            from nautilus.agent import run_agent
            run_agent(
                prompt="创建一个 hello.py 文件",
                model="mock-model",
                api_key="sk-fake",
                max_iter=5,
                skills_dir=skills_dir,
            )

        assert len(captured_messages) >= 1
        system_msg = captured_messages[0][0]
        system_content = system_msg.get("content", "") if isinstance(system_msg, dict) else ""
        assert "## 技能指导" not in system_content
