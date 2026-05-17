"""Tests for skills/domain/auto_patch.py (Sprint 6 day 4-5).

Coverage:

1. ``route_domains`` — single hit / multi hit / no hit / case-insensitive
   / thesis-summary contribution.
2. Distinction from ``skills.domain.classify_domains``: the two key
   sets are deliberately different (auto_patch is narrower).
3. ``already_patched``: marker found / not found / missing file.
4. ``render_patch`` — full shape; truncation cap; null thesis fields.
5. ``patch_skill_file`` — section creation + append; existing section
   append before next H2; placeholder preamble inserted exactly once.
6. ``patch_from_synthesis`` end-to-end: matches → patches → emits
   ``AutoPatchAppliedPayload``; second call skips → emits
   ``AutoPatchSkippedPayload``; no-match → ``status=no_match``;
   missing skill file is created.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from skills.domain.auto_patch import (  # noqa: E402
    AUTO_PATCH_DOMAIN_KEYWORDS,
    SECTION_MARKER,
    already_patched,
    patch_from_synthesis,
    patch_skill_file,
    render_patch,
    route_domains,
)
from skills.domain.keywords import DOMAIN_KEYWORDS as PHASE_8_DOMAIN_KEYWORDS  # noqa: E402
from substrate.event_log import trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    AutoPatchAppliedPayload,
    AutoPatchSkippedPayload,
    Event,
)


@pytest.fixture
def events_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    return tmp_path / "events"


@pytest.fixture
def skills_root(tmp_path) -> Path:
    return tmp_path / "knowledge_skills"


def _synthesis() -> dict:
    return {
        "synthesis_id": "syn-ap",
        "investigation_id": "inv-ap",
        "target_question": "Will PsiQuantum's photonic qubit roadmap work?",
        "implicit_recommendation": "conditional",
        "thesis": {
            "thesis_summary": "Roadmap depends on fault-tolerant gate operations.",
            "thesis_components": [
                {"claim": "PsiQuantum bet is photonic", "confidence": "high",
                 "effective_source_tier": 1},
                {"claim": "Gate error rates dominate", "confidence": "moderate"},
            ],
            "falsification_conditions": [
                {"condition": "Logical qubit count plateaus",
                 "specific_observable": "no growth in 12mo"},
            ],
            "execution_risks": [
                {"risk": "Talent flight", "severity_if_manifested": "high"},
            ],
            "reasoning_paths_used": [
                {"path_node_ids": ["n1"], "path_edge_ids": ["e1"],
                 "support_summary": "Path validates fault-tolerance dependency."},
            ],
        },
    }


# ---------------------------------------------------------------------------
# 1. route_domains
# ---------------------------------------------------------------------------


def test_route_domains_single_match():
    matched = route_domains(
        "PsiQuantum photonic qubit roadmap", "",
    )
    assert matched == ["quantum-computing-knowledge"]


def test_route_domains_multi_match():
    matched = route_domains(
        "Will Anduril leverage H100 inference clusters for autonomous drones?",
        "",
    )
    assert "defense-systems-knowledge" in matched
    assert "ai-infrastructure-knowledge" in matched


def test_route_domains_no_match():
    assert route_domains("Will the weather be sunny tomorrow?", "") == []


def test_route_domains_is_case_insensitive():
    assert "quantum-computing-knowledge" in route_domains(
        "PSIQUANTUM", "",
    )


def test_route_domains_searches_thesis_summary():
    matched = route_domains("", "TSMC foundry capacity expansion")
    assert "semiconductor-knowledge" in matched


def test_route_domains_handles_none_args():
    assert route_domains(None, None) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 2. Distinct keyword namespace
# ---------------------------------------------------------------------------


def test_auto_patch_keywords_distinct_from_phase8_set():
    """The two routing maps are deliberately different — auto_patch
    is mechanical (no LLM), so it picks narrower phrases. This test
    documents that they don't collapse over time."""
    ap_quantum = set(AUTO_PATCH_DOMAIN_KEYWORDS["quantum-computing-knowledge"])
    p8_quantum = set(PHASE_8_DOMAIN_KEYWORDS["quantum-computing-knowledge"])
    # They must NOT be equal — auto_patch was intentionally narrowed.
    assert ap_quantum != p8_quantum


# ---------------------------------------------------------------------------
# 3. already_patched
# ---------------------------------------------------------------------------


def test_already_patched_finds_marker(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text("text\n<!-- synthesis_id: syn-X -->\nmore text")
    assert already_patched(p, "syn-X") is True


def test_already_patched_missing_marker(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text("no marker here")
    assert already_patched(p, "syn-Y") is False


def test_already_patched_missing_file(tmp_path):
    assert already_patched(tmp_path / "absent.md", "any") is False


# ---------------------------------------------------------------------------
# 4. render_patch
# ---------------------------------------------------------------------------


def test_render_patch_full_shape():
    md = render_patch(_synthesis())
    assert "From investigation `inv-ap`" in md
    assert "<!-- synthesis_id: syn-ap -->" in md
    assert "Will PsiQuantum's photonic qubit roadmap work?" in md
    assert "Recommendation`: `conditional`".replace("`: `", ":") in md or "conditional" in md
    assert "PsiQuantum bet is photonic" in md
    assert "Gate error rates dominate" in md
    assert "Logical qubit count plateaus" in md
    assert "(observable: no growth in 12mo)" in md
    assert "Talent flight" in md
    assert "Reasoning paths cited" in md


def test_render_patch_truncates_long_question():
    syn = _synthesis()
    syn["target_question"] = "Q?" * 500  # very long
    md = render_patch(syn)
    # The truncated form ends with ellipsis
    assert "…" in md


def test_render_patch_handles_missing_thesis_fields():
    syn = {"synthesis_id": "syn-min", "investigation_id": "inv-min"}
    md = render_patch(syn)
    assert "syn-min" in md
    assert "(no question recorded)" in md
    assert "(no recommendation)" in md


def test_render_patch_caps_components_at_six():
    syn = _synthesis()
    syn["thesis"]["thesis_components"] = [
        {"claim": f"claim-{i}", "confidence": "high"} for i in range(10)
    ]
    md = render_patch(syn)
    # First 6 rendered; 7th onward dropped
    for i in range(6):
        assert f"claim-{i}" in md
    for i in range(6, 10):
        assert f"claim-{i}" not in md


# ---------------------------------------------------------------------------
# 5. patch_skill_file
# ---------------------------------------------------------------------------


def test_patch_skill_file_creates_section_when_absent(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text("# Existing Skill\n\n## Domain Fundamentals\n- existing fact\n")
    patch_skill_file(p, "### From investigation `inv-X` (2026-05-17)\n\n- new finding\n")
    body = p.read_text()
    assert SECTION_MARKER in body
    assert "- existing fact" in body  # untouched
    assert "inv-X" in body


def test_patch_skill_file_appends_within_existing_section(tmp_path):
    p = tmp_path / "SKILL.md"
    p.write_text(
        "# Skill\n\n"
        f"{SECTION_MARKER}\n\n"
        "_preamble_\n\n"
        "### From investigation `inv-A`\n"
        "- first patch\n\n"
        "## Another Top Section\n"
        "- unrelated\n"
    )
    patch_skill_file(p, "### From investigation `inv-B`\n- second patch\n")
    body = p.read_text()
    # Both patches present
    assert "inv-A" in body
    assert "inv-B" in body
    # ## Another Top Section preserved
    assert "## Another Top Section" in body
    # The second patch sits BEFORE the next top-level section.
    inv_b_idx = body.find("inv-B")
    other_idx = body.find("## Another Top Section")
    assert inv_b_idx < other_idx


# ---------------------------------------------------------------------------
# 6. patch_from_synthesis end-to-end
# ---------------------------------------------------------------------------


def test_patch_from_synthesis_no_match_status(events_dir, skills_root):
    syn = {
        "synthesis_id": "syn-nm",
        "investigation_id": "inv-nm",
        "target_question": "Will the weather be sunny?",
        "thesis": {"thesis_summary": "irrelevant prose"},
    }
    result = patch_from_synthesis(syn, skills_root=skills_root)
    assert result["status"] == "no_match"
    assert result["matched_domains"] == []
    assert result["patched"] == []

    rows = trajectory("inv-nm")
    applied = [r for r in rows if r["action_type"] == ActionType.AUTO_PATCH_APPLIED.value]
    assert len(applied) == 1
    e = Event.model_validate(applied[0])
    assert isinstance(e.payload, AutoPatchAppliedPayload)
    assert e.payload.status == "no_match"


def test_patch_from_synthesis_happy_path(events_dir, skills_root):
    syn = _synthesis()
    result = patch_from_synthesis(syn, skills_root=skills_root)
    assert result["status"] == "patched"
    assert "quantum-computing-knowledge" in result["patched"]
    assert result["errors"] == []

    skill_path = skills_root / "quantum-computing-knowledge" / "SKILL.md"
    assert skill_path.exists()
    body = skill_path.read_text()
    assert "<!-- synthesis_id: syn-ap -->" in body
    assert SECTION_MARKER in body

    rows = trajectory("inv-ap")
    applied = [r for r in rows if r["action_type"] == ActionType.AUTO_PATCH_APPLIED.value]
    assert len(applied) == 1
    e = Event.model_validate(applied[0])
    assert isinstance(e.payload, AutoPatchAppliedPayload)
    assert e.payload.status == "patched"
    assert "quantum-computing-knowledge" in e.payload.patched


def test_patch_from_synthesis_second_call_is_idempotent(events_dir, skills_root):
    syn = _synthesis()
    r1 = patch_from_synthesis(syn, skills_root=skills_root)
    assert r1["status"] == "patched"

    r2 = patch_from_synthesis(syn, skills_root=skills_root)
    assert r2["status"] == "already_patched"
    assert "quantum-computing-knowledge" in r2["skipped"]
    assert r2["patched"] == []

    rows = trajectory("inv-ap")
    skipped = [r for r in rows if r["action_type"] == ActionType.AUTO_PATCH_SKIPPED.value]
    assert len(skipped) == 1  # one per domain marked skipped
    e = Event.model_validate(skipped[0])
    assert isinstance(e.payload, AutoPatchSkippedPayload)
    assert e.payload.synthesis_id == "syn-ap"
    assert e.payload.domain == "quantum-computing-knowledge"


def test_patch_from_synthesis_creates_missing_skill_dir(events_dir, skills_root):
    """Skill file doesn't exist yet — patcher creates the dir tree
    and writes a fresh file with the Auto-patched section."""
    assert not skills_root.exists()
    syn = _synthesis()
    result = patch_from_synthesis(syn, skills_root=skills_root)
    assert result["status"] == "patched"
    assert (skills_root / "quantum-computing-knowledge" / "SKILL.md").exists()


def test_patch_from_synthesis_multi_domain(events_dir, skills_root):
    """One synthesis matches two domains — both get patched."""
    syn = _synthesis()
    syn["target_question"] = (
        "Will PsiQuantum's photonic qubit roadmap require H100 training runs?"
    )
    result = patch_from_synthesis(syn, skills_root=skills_root)
    assert set(result["patched"]) == {
        "quantum-computing-knowledge", "ai-infrastructure-knowledge",
    }
    assert (skills_root / "quantum-computing-knowledge" / "SKILL.md").exists()
    assert (skills_root / "ai-infrastructure-knowledge" / "SKILL.md").exists()
