"""Sprint 17 program.md acceptance checks."""

from __future__ import annotations

from pathlib import Path


SPRINT17_PROGRAM_ROLES = (
    "decomposer",
    "evidence_retriever",
    "parameter_extractor",
    "connector",
    "synthesizer",
    "challenger",
    "grounder",
    "note_taker",
    "user_agent",
    "creative_writer",
    "interviewer",
    "voice_note_followup",
)


def test_sprint17_program_md_files_exist_for_named_roles():
    missing = [
        role for role in SPRINT17_PROGRAM_ROLES
        if not Path("roles", role, "program.md").is_file()
    ]

    assert missing == []


def test_sprint17_program_md_files_follow_autoresearch_shape():
    required_fragments = (
        "What this role does",
        "What good output looks like",
        "What to avoid",
        "Hypotheses to try when iterating",
        "Cross-references",
    )
    failures: dict[str, list[str]] = {}
    for role in SPRINT17_PROGRAM_ROLES:
        text = Path("roles", role, "program.md").read_text(encoding="utf-8")
        missing = [fragment for fragment in required_fragments if fragment not in text]
        if missing:
            failures[role] = missing

    assert failures == {}


def test_synthesizer_program_codifies_voice_style_discipline():
    text = Path("roles/synthesizer/program.md").read_text(encoding="utf-8").lower()

    assert "voice and style discipline" in text
    assert "master-spec §5" in text
    assert "em-dash" in text
    assert "padding constructions" in text
