from __future__ import annotations

from pathlib import Path

from compounding.skill_growth import materialize_candidate_skill_overlay
from skills.domain.auto_patch import SECTION_MARKER
from substrate.event_log import trajectory


def _synthesis(synthesis_id: str = "syn-overlay") -> dict:
    return {
        "synthesis_id": synthesis_id,
        "investigation_id": "inv-overlay",
        "target_question": "Will PsiQuantum need fault-tolerant photonic qubits?",
        "implicit_recommendation": "conditional",
        "thesis": {
            "thesis_summary": "Photonic qubit progress depends on logical qubit scaling.",
            "thesis_components": [
                {"claim": "Fault tolerance is load-bearing.", "confidence": "high"},
            ],
        },
    }


def test_materialize_candidate_skill_overlay_patches_copy_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    baseline = tmp_path / "baseline-skills"
    skill_path = baseline / "quantum-computing-knowledge" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("# Quantum\n\n## Domain Fundamentals\n- baseline fact\n")

    overlay = materialize_candidate_skill_overlay(
        _synthesis(),
        baseline_skills_root=baseline,
        overlay_parent=tmp_path,
    )

    baseline_body = skill_path.read_text()
    overlay_body = (
        overlay.overlay_skills_root
        / "quantum-computing-knowledge"
        / "SKILL.md"
    ).read_text()

    assert overlay.status == "patched"
    assert overlay.matched_domains == ("quantum-computing-knowledge",)
    assert overlay.patched_domains == ("quantum-computing-knowledge",)
    assert baseline_body == "# Quantum\n\n## Domain Fundamentals\n- baseline fact\n"
    assert "<!-- synthesis_id: syn-overlay -->" in overlay_body
    assert SECTION_MARKER in overlay_body
    assert trajectory("inv-overlay") == []


def test_materialize_candidate_skill_overlay_creates_only_overlay_for_missing_baseline(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    baseline = tmp_path / "missing-baseline"

    overlay = materialize_candidate_skill_overlay(
        _synthesis(),
        baseline_skills_root=baseline,
        overlay_parent=tmp_path,
    )

    assert not baseline.exists()
    assert overlay.status == "patched"
    assert (
        overlay.overlay_skills_root
        / "quantum-computing-knowledge"
        / "SKILL.md"
    ).exists()


def test_materialize_candidate_skill_overlay_preserves_idempotency(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    baseline = tmp_path / "baseline-skills"
    skill_path = baseline / "quantum-computing-knowledge" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "# Quantum\n\n"
        "## Auto-patched findings\n\n"
        "### From investigation `old`\n"
        "<!-- synthesis_id: syn-overlay -->\n"
    )

    overlay = materialize_candidate_skill_overlay(
        _synthesis(),
        baseline_skills_root=baseline,
        overlay_parent=tmp_path,
    )

    assert overlay.status == "already_patched"
    assert overlay.patched_domains == ()
    assert overlay.skipped_domains == ("quantum-computing-knowledge",)
    assert trajectory("inv-overlay") == []
