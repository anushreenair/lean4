from pathlib import Path

from agent import load_skill


def test_skill_is_loaded_and_contains_documentation_first_instruction():
    skill = load_skill(Path("SKILL.md"))

    assert skill.loaded
    assert "official Lean documentation" in skill.instructions
