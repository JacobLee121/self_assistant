"""Project skills loaded through Google ADK SkillToolset."""

from __future__ import annotations

from pathlib import Path

from google.adk.skills import Skill
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = PROJECT_ROOT / "skills"


def load_project_skills() -> list[Skill]:
    """Load all project-local ADK skills from the skills directory."""
    if not SKILLS_DIR.exists():
        return []

    skills: list[Skill] = []
    for skill_dir in sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir()):
        if (skill_dir / "SKILL.md").exists() or (skill_dir / "skill.md").exists():
            skills.append(load_skill_from_dir(skill_dir))
    return skills


def build_skill_toolset() -> SkillToolset | None:
    """Create the ADK SkillToolset for project-local skills."""
    skills = load_project_skills()
    if not skills:
        return None
    return SkillToolset(skills=skills)


def format_project_skills_instruction() -> str:
    """Format project skills for direct injection into ADK LLM requests."""
    skills = load_project_skills()
    if not skills:
        return ""

    chunks = [
        "项目内 ADK Skills:",
        "当用户请求匹配下列 skill 时，必须按对应 skill 的 instructions 执行。",
        "这些 skills 是本项目 Agent 的运行时能力，不是 Codex 开发环境技能。",
    ]
    for skill in skills:
        chunks.append(
            "\n".join([
                f"<skill name=\"{skill.name}\">",
                f"description: {skill.description}",
                "instructions:",
                skill.instructions,
                "</skill>",
            ])
        )
    return "\n\n".join(chunks)


def append_project_skills_to_request(llm_request) -> None:
    """Append project skill instructions to an ADK LlmRequest."""
    instructions = format_project_skills_instruction()
    if instructions:
        llm_request.append_instructions([instructions])
