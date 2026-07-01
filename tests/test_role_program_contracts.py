"""Program.md coverage for prompt-bearing roles."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROLES = REPO / "roles"


def test_every_prompt_bearing_role_has_program_md():
    missing: list[str] = []
    empty: list[str] = []
    for role_dir in sorted(path for path in ROLES.iterdir() if path.is_dir()):
        if role_dir.name.startswith("__"):
            continue
        if not (role_dir / "prompt.py").exists():
            continue
        program = role_dir / "program.md"
        if not program.exists():
            missing.append(role_dir.name)
            continue
        text = program.read_text(encoding="utf-8")
        if not text.strip():
            empty.append(role_dir.name)
    assert missing == []
    assert empty == []
