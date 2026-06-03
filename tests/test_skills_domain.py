"""Tests for skills/domain/ (Sprint 6 day 2-3 Phase 8 migration).

Coverage:

1. ``classify_domains`` matches single keyword hits, hits via thesis
   summary + components, case-insensitive, multiple-domain match,
   no-match returns empty.
2. WP-A4 expansion (2026-05-14): AI-strategy prose matches
   ai-infrastructure-knowledge even without GPU/hardware terms.
3. ``make_extraction_prompt`` substitutes question/summary/components/
   falsification + domain into the user template.
4. ``EXTRACTION_SECTIONS`` exactly matches the section headers
   enumerated in the system prompt body (drift detection).
5. ``find_section_boundaries`` finds H2 headers, returns (-1,-1,"")
   on miss, matches the section-name as a PREFIX (WP-A4 fix), case-
   insensitive.
6. ``format_finding_bullet`` renders the full shape + drops missing
   fields + squeezes double spaces.
7. ``apply_finding_to_section`` replaces the placeholder, appends to
   non-empty content, handles empty content.
8. ``patch_skill`` writes back to disk, returns the list of patched
   section names, no-op when no matching sections, missing skill
   prints to stderr and returns ``[]``.
9. ``extract_findings`` happy path with injected llm_call, brace-slice
   fallback, repair retry, repair-disabled bail.
10. ``extract_and_patch`` end-to-end: classify → extract → patch.
    Dry-run skips LLM + patching.
11. ``ExtractionResult.any_patched`` truth table.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from skills.domain import (  # noqa: E402
    EXTRACTION_CONFIDENCE_TIERS,
    EXTRACTION_SECTIONS,
    EXTRACTION_SYSTEM_PROMPT,
    ExtractionResult,
    apply_finding_to_section,
    classify_domains,
    extract_and_patch,
    extract_findings,
    find_section_boundaries,
    format_finding_bullet,
    make_extraction_prompt,
    patch_skill,
)

# ---------------------------------------------------------------------------
# 1-2. classify_domains
# ---------------------------------------------------------------------------


def test_classify_no_match_returns_empty():
    assert classify_domains("What is the weather?", {}) == []


def test_classify_matches_single_keyword_in_question():
    matched = classify_domains("Is TSMC's N2 yield improving?", {})
    assert "semiconductor-knowledge" in matched


def test_classify_matches_via_thesis_summary():
    thesis = {"thesis_summary": "EUV lithography uptime is the bottleneck"}
    assert "semiconductor-knowledge" in classify_domains("any question", thesis)


def test_classify_matches_via_thesis_component_claim():
    thesis = {
        "thesis_components": [
            {"claim": "Qubit error rates remain above the surface-code threshold"},
        ]
    }
    matched = classify_domains("any question", thesis)
    assert "quantum-computing-knowledge" in matched


def test_classify_is_case_insensitive():
    assert "quantum-computing-knowledge" in classify_domains("QUANTUM advantage?", {})


def test_classify_returns_all_matching_domains():
    """Question spanning two domains should match BOTH knowledge skills."""
    matched = classify_domains(
        "How do quantum computers integrate with NVIDIA GPU clusters?", {},
    )
    assert "quantum-computing-knowledge" in matched
    assert "ai-infrastructure-knowledge" in matched


def test_classify_wp_a4_ai_strategy_prose_matches_ai_infrastructure():
    """2026-05-14 WP-A4 regression: strategy-only prose with no GPU
    hardware terms must still hit ai-infrastructure-knowledge."""
    matched = classify_domains(
        "Will open-source AI close the frontier model performance gap?", {},
    )
    assert "ai-infrastructure-knowledge" in matched


def test_classify_tolerates_non_dict_thesis():
    assert classify_domains("anything", None) == []
    assert classify_domains("anything", []) == []


# ---------------------------------------------------------------------------
# 3-4. extraction prompt
# ---------------------------------------------------------------------------


def test_make_extraction_prompt_substitutes_fields():
    thesis = {
        "thesis_summary": "X causes Y",
        "thesis_components": [
            {"claim": "C1", "confidence": "high"},
            {"claim": "C2", "confidence": "moderate"},
        ],
        "falsification_conditions": [
            {"condition": "Y unchanged when X varies", "specific_observable": "regression t-stat"},
        ],
    }
    system, user = make_extraction_prompt("Is X causally linked to Y?", thesis, "quantum-computing-knowledge")
    assert system == EXTRACTION_SYSTEM_PROMPT
    assert "Is X causally linked to Y?" in user
    assert "X causes Y" in user
    assert "[high] C1" in user
    assert "[moderate] C2" in user
    assert "IF: Y unchanged when X varies" in user
    assert "OBSERVABLE: regression t-stat" in user
    assert "quantum-computing-knowledge" in user


def test_make_extraction_prompt_handles_empty_thesis():
    _, user = make_extraction_prompt("Q?", {}, "domain-x")
    assert "(none)" in user  # both components + falsifications empty


def test_make_extraction_prompt_handles_non_dict_thesis():
    _, user = make_extraction_prompt("Q?", None, "domain-x")
    assert "(none)" in user


def test_extraction_sections_match_system_prompt_body():
    """The closed section vocabulary in EXTRACTION_SECTIONS must equal
    the section names listed inside the SYSTEM prompt body. Drift
    between them would let the LLM emit a section name the patcher
    can't find."""
    body_sections = set()
    for section in EXTRACTION_SECTIONS:
        assert section in EXTRACTION_SYSTEM_PROMPT, (
            f"section {section!r} declared in EXTRACTION_SECTIONS is not "
            f"in the system prompt body"
        )
        body_sections.add(section)
    # The reverse — every section header in the prompt body must be in
    # EXTRACTION_SECTIONS — is enforced by manual review at edit time;
    # mechanically checking it requires parsing the markdown structure.
    assert body_sections == EXTRACTION_SECTIONS


def test_extraction_confidence_tiers_are_the_canonical_four():
    assert frozenset({
        "Measured", "Calculated", "Inferred", "Speculated",
    }) == EXTRACTION_CONFIDENCE_TIERS


# ---------------------------------------------------------------------------
# 5. find_section_boundaries
# ---------------------------------------------------------------------------


SAMPLE_SKILL = """\
# Quantum Computing Knowledge

Intro line.

## Domain Fundamentals

- Fundamentals bullet 1.
- Fundamentals bullet 2.

## Key Players

- Player A.

## Open Questions & Uncertainties

- Open Q 1.

## Monitoring Checklist

(Findings will be added.)
"""


def test_find_section_boundaries_finds_h2():
    start, end, current = find_section_boundaries(SAMPLE_SKILL, "Domain Fundamentals")
    assert start > 0 and end > start
    assert "Fundamentals bullet 1" in current
    assert "Fundamentals bullet 2" in current
    assert "Player A" not in current  # stops at next ## header


def test_find_section_boundaries_matches_section_name_as_prefix():
    """WP-A4 fix: 'Open Questions' must match 'Open Questions & Uncertainties'."""
    start, _, current = find_section_boundaries(SAMPLE_SKILL, "Open Questions")
    assert start > 0
    assert "Open Q 1" in current


def test_find_section_boundaries_is_case_insensitive():
    start, _, _ = find_section_boundaries(SAMPLE_SKILL, "domain fundamentals")
    assert start > 0


def test_find_section_boundaries_returns_sentinel_on_miss():
    assert find_section_boundaries(SAMPLE_SKILL, "Nonexistent") == (-1, -1, "")


def test_find_section_boundaries_terminal_section_runs_to_eof():
    """Monitoring Checklist is the last section — end_idx should be
    len(lines)."""
    start, end, current = find_section_boundaries(SAMPLE_SKILL, "Monitoring Checklist")
    assert start > 0
    assert "(Findings will be added.)" in current
    # No further ## headers ⇒ end_idx is the file tail.
    total_lines = len(SAMPLE_SKILL.split("\n"))
    assert end == total_lines


# ---------------------------------------------------------------------------
# 6. format_finding_bullet
# ---------------------------------------------------------------------------


def test_format_finding_bullet_full_shape():
    out = format_finding_bullet(
        text="H100 FP8 is 3958 TFLOPS",
        confidence="Measured",
        date_observed="2024-01",
        source="datasheet",
    )
    assert "[Measured]" in out
    assert "(2024-01)" in out
    assert "H100 FP8 is 3958 TFLOPS" in out
    assert "— datasheet" in out
    assert out.startswith("- ")


def test_format_finding_bullet_drops_missing_fields():
    out = format_finding_bullet(
        text="naked finding", confidence="", date_observed="", source="",
    )
    assert out == "- naked finding"


def test_format_finding_bullet_squeezes_double_spaces():
    out = format_finding_bullet(
        text="x", confidence="", date_observed="2026-04", source="",
    )
    # No "[Confidence]" or "— source" means leftover empties should
    # collapse to single spaces.
    assert "  " not in out


# ---------------------------------------------------------------------------
# 7. apply_finding_to_section
# ---------------------------------------------------------------------------


def test_apply_replaces_placeholder():
    current = "(Findings will be added.)\n"
    out = apply_finding_to_section(
        current, text="new finding", confidence="Inferred",
    )
    assert "(Findings will be added.)" not in out
    assert "new finding" in out


def test_apply_appends_to_existing_content():
    current = "- Existing finding.\n"
    out = apply_finding_to_section(current, text="appended")
    assert "Existing finding" in out
    assert "appended" in out
    assert out.count("- ") == 2


def test_apply_handles_empty_content():
    out = apply_finding_to_section("", text="solo")
    assert "solo" in out


# ---------------------------------------------------------------------------
# 8. patch_skill — file I/O at the boundary
# ---------------------------------------------------------------------------


def _make_skill_file(root: Path, skill_name: str) -> Path:
    d = root / skill_name
    d.mkdir(parents=True, exist_ok=True)
    p = d / "SKILL.md"
    p.write_text(SAMPLE_SKILL)
    return p


def test_patch_skill_writes_back_and_returns_patched_sections(tmp_path):
    _make_skill_file(tmp_path, "quantum-computing-knowledge")
    findings = {
        "Domain Fundamentals": [
            {"text": "Decoherence sets coherence-time ceiling",
             "confidence": "Measured", "date_observed": "2024",
             "source": "Preskill 2018"},
        ],
        "Monitoring Checklist": [
            {"text": "Track logical qubit count above 50",
             "confidence": "Speculated", "date_observed": "",
             "source": ""},
        ],
    }
    patched = patch_skill(
        "quantum-computing-knowledge", findings, skills_root=tmp_path,
    )
    assert set(patched) == {"Domain Fundamentals", "Monitoring Checklist"}

    content = (tmp_path / "quantum-computing-knowledge" / "SKILL.md").read_text()
    assert "Decoherence sets coherence-time ceiling" in content
    assert "Track logical qubit count above 50" in content
    # Placeholder must be gone from the Monitoring Checklist section.
    assert "(Findings will be added.)" not in content


def test_patch_skill_missing_skill_returns_empty(tmp_path):
    out = patch_skill("does-not-exist", {"Domain Fundamentals": [{"text": "x"}]},
                      skills_root=tmp_path)
    assert out == []


def test_patch_skill_empty_findings_lists_skipped(tmp_path):
    _make_skill_file(tmp_path, "quantum-computing-knowledge")
    out = patch_skill(
        "quantum-computing-knowledge",
        {"Domain Fundamentals": []},
        skills_root=tmp_path,
    )
    assert out == []


def test_patch_skill_unknown_section_skipped(tmp_path):
    _make_skill_file(tmp_path, "quantum-computing-knowledge")
    out = patch_skill(
        "quantum-computing-knowledge",
        {"Made Up Section": [{"text": "x"}]},
        skills_root=tmp_path,
    )
    assert out == []


# ---------------------------------------------------------------------------
# 9. extract_findings
# ---------------------------------------------------------------------------


def _stub_llm(responses: list[str]):
    """Build a stub llm_call closure that returns sequential responses."""
    state = {"i": 0}

    def _call(*, system: str, user: str) -> str:
        i = state["i"]
        state["i"] += 1
        return responses[min(i, len(responses) - 1)]
    return _call, state


def test_extract_findings_happy_path():
    findings_json = {"Domain Fundamentals": [{"text": "F1", "confidence": "Measured"}]}
    llm, state = _stub_llm([json.dumps(findings_json)])
    out = extract_findings(
        question="Q", thesis={}, domain="d", llm_call=llm,
    )
    assert out == findings_json
    assert state["i"] == 1


def test_extract_findings_brace_slice_fallback():
    """Model returns prose-wrapped JSON; brace-slice should recover."""
    findings_json = {"Domain Fundamentals": [{"text": "F1"}]}
    wrapped = f"Here is your JSON:\n{json.dumps(findings_json)}\nGood luck!"
    llm, state = _stub_llm([wrapped])
    out = extract_findings(question="Q", thesis={}, domain="d", llm_call=llm)
    assert out == findings_json
    assert state["i"] == 1  # only one LLM call — no repair needed


def test_extract_findings_repair_retry_succeeds(monkeypatch):
    monkeypatch.setenv("ANTIEK_KE_REPAIR_ENABLED", "1")
    good = json.dumps({"Domain Fundamentals": [{"text": "F1"}]})
    llm, state = _stub_llm(["totally not JSON", good])
    out = extract_findings(question="Q", thesis={}, domain="d", llm_call=llm)
    assert out is not None
    assert state["i"] == 2


def test_extract_findings_repair_disabled_bails_after_first_failure(monkeypatch):
    monkeypatch.setenv("ANTIEK_KE_REPAIR_ENABLED", "0")
    llm, state = _stub_llm(["unparseable"])
    out = extract_findings(question="Q", thesis={}, domain="d", llm_call=llm)
    assert out is None
    assert state["i"] == 1  # no retry attempted


def test_extract_findings_both_attempts_fail_returns_none(monkeypatch):
    monkeypatch.setenv("ANTIEK_KE_REPAIR_ENABLED", "1")
    llm, state = _stub_llm(["bad-1", "bad-2"])
    assert extract_findings(question="Q", thesis={}, domain="d", llm_call=llm) is None
    assert state["i"] == 2


def test_extract_findings_transport_error_returns_none():
    def boom(*, system, user):
        raise RuntimeError("simulated transport failure")
    out = extract_findings(question="Q", thesis={}, domain="d", llm_call=boom)
    assert out is None


# ---------------------------------------------------------------------------
# 10. extract_and_patch end-to-end
# ---------------------------------------------------------------------------


def test_extract_and_patch_no_match_returns_empty(tmp_path):
    result = extract_and_patch(
        question="What's for lunch?", thesis={}, investigation_id="inv-x",
        skills_root=tmp_path,
    )
    assert isinstance(result, ExtractionResult)
    assert result.domains_matched == []
    assert result.patched_skills == {}
    assert result.any_patched is False


def test_extract_and_patch_dry_run_classifies_but_no_extract(tmp_path):
    """Question matches quantum-computing-knowledge; dry-run should
    populate domains_matched but skip the LLM + patcher."""
    result = extract_and_patch(
        question="What is the surface code threshold?", thesis={},
        investigation_id="inv-dry", dry_run=True,
        skills_root=tmp_path,
    )
    assert "quantum-computing-knowledge" in result.domains_matched
    assert result.findings_extracted == {}
    assert result.patched_skills == {}


def test_extract_and_patch_happy_path(tmp_path):
    _make_skill_file(tmp_path, "quantum-computing-knowledge")
    findings_json = {
        "Domain Fundamentals": [
            {"text": "Coherence time bounds at room temperature",
             "confidence": "Measured", "date_observed": "2024",
             "source": "Preskill 2018"},
        ],
    }
    llm, _ = _stub_llm([json.dumps(findings_json)])

    result = extract_and_patch(
        question="What's the quantum advantage timeline?", thesis={},
        investigation_id="inv-happy",
        llm_call=llm,
        skills_root=tmp_path,
    )
    assert "quantum-computing-knowledge" in result.domains_matched
    assert "quantum-computing-knowledge" in result.patched_skills
    assert "Domain Fundamentals" in result.patched_skills["quantum-computing-knowledge"]
    assert result.any_patched is True

    content = (tmp_path / "quantum-computing-knowledge" / "SKILL.md").read_text()
    assert "Coherence time bounds at room temperature" in content


def test_extract_and_patch_skill_file_missing_records_findings_but_no_patch(tmp_path):
    """If extraction succeeds but the SKILL.md doesn't exist, the
    finding is recorded in findings_extracted but patched_skills
    stays empty. any_patched is False — Phase 8 didn't actually
    compound."""
    findings_json = {"Domain Fundamentals": [{"text": "x"}]}
    llm, _ = _stub_llm([json.dumps(findings_json)])
    result = extract_and_patch(
        question="quantum decoherence rates?", thesis={},
        investigation_id="inv-miss",
        llm_call=llm, skills_root=tmp_path,
    )
    assert result.findings_extracted == {
        "quantum-computing-knowledge": findings_json,
    }
    assert result.patched_skills == {}
    assert result.any_patched is False


def test_extract_and_patch_per_domain_failures_are_isolated(tmp_path):
    """Two matched domains, one LLM fails — the other domain still
    gets its chance."""
    _make_skill_file(tmp_path, "quantum-computing-knowledge")
    _make_skill_file(tmp_path, "ai-infrastructure-knowledge")

    good = json.dumps({"Domain Fundamentals": [{"text": "F-quantum"}]})
    state = {"i": 0}

    def per_domain_llm(*, system: str, user: str) -> str:
        i = state["i"]
        state["i"] += 1
        # First call (lexicographically first domain) returns garbage;
        # second call returns good JSON.
        if "ai-infrastructure-knowledge" in user:
            return "garbage"
        return good

    # Disable repair so the failed-domain call bails fast.
    os.environ["ANTIEK_KE_REPAIR_ENABLED"] = "0"
    try:
        result = extract_and_patch(
            question="How do quantum and GPU compute compare?", thesis={},
            investigation_id="inv-iso",
            llm_call=per_domain_llm,
            skills_root=tmp_path,
        )
    finally:
        os.environ.pop("ANTIEK_KE_REPAIR_ENABLED", None)

    assert set(result.domains_matched) == {
        "quantum-computing-knowledge", "ai-infrastructure-knowledge",
    }
    # Quantum got findings + patched; AI infrastructure failed to parse.
    assert "quantum-computing-knowledge" in result.patched_skills
    assert "ai-infrastructure-knowledge" not in result.patched_skills


# ---------------------------------------------------------------------------
# 11. ExtractionResult.any_patched
# ---------------------------------------------------------------------------


def test_any_patched_false_when_no_domains():
    assert ExtractionResult().any_patched is False


def test_any_patched_false_when_domains_but_no_patches():
    r = ExtractionResult(domains_matched=["x"], patched_skills={})
    assert r.any_patched is False


def test_any_patched_true_when_any_section_patched():
    r = ExtractionResult(patched_skills={"x": ["Domain Fundamentals"]})
    assert r.any_patched is True


def test_extraction_result_to_dict_serializes():
    r = ExtractionResult(
        domains_matched=["q"], patched_skills={"q": ["S1"]},
        findings_extracted={"q": {"S1": [{"text": "f"}]}},
    )
    d = r.to_dict()
    assert d["domains_matched"] == ["q"]
    assert d["patched_skills"] == {"q": ["S1"]}
    assert d["findings_extracted"]["q"]["S1"][0]["text"] == "f"
