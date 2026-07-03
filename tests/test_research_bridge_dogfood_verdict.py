"""Deep Research Bridge dogfood verdict tests."""

from __future__ import annotations

from pathlib import Path

from substrate.research_bridge.dogfood_verdict import (
    validate_verdict_doc,
    write_verdict_scaffold,
)


def test_write_verdict_scaffold_preserves_existing_doc(tmp_path: Path) -> None:
    path = tmp_path / "adrb_post_dogfood_verdict.md"
    assert write_verdict_scaffold(path).written is True
    path.write_text("operator verdict\n", encoding="utf-8")

    result = write_verdict_scaffold(path)

    assert result.written is False
    assert path.read_text(encoding="utf-8") == "operator verdict\n"


def test_validate_verdict_doc_rejects_scaffold_placeholders(tmp_path: Path) -> None:
    path = tmp_path / "adrb_post_dogfood_verdict.md"
    write_verdict_scaffold(path)

    result = validate_verdict_doc(path)

    assert result.ok is False
    assert "replace all TODO placeholders" in result.missing_requirements
    assert "Mode A Verdict must declare SHIP, KILL, or ITERATE" in (
        result.missing_requirements
    )


def test_validate_verdict_doc_requires_mode_local_citations(tmp_path: Path) -> None:
    path = tmp_path / "adrb_post_dogfood_verdict.md"
    path.write_text(
        """# Antiek Deep Research Bridge Post-Dogfood Verdict

## Evidence Sources

- Operator log: `runs/adrb/operator-log.md`
- Metrics report: `runs/adrb/dogfood_metrics.md`

## Mode A Verdict

Verdict: SHIP

Evidence:
- The draft flow worked, but this section is missing local citations.

## Mode B Verdict

Verdict: ITERATE

Evidence:
- `operator-log.md` records mixed prompt usefulness.
- `dogfood_metrics.md` records 60.0% would-run signals.

## Next 3 Sharp Questions

1. Which draft failures matter?
2. Which prompt failures matter?
3. Which timing failures matter?

## Wave 4

Decision: conditional Wave 4 for Mode B prompt sharpening only.
""",
        encoding="utf-8",
    )

    result = validate_verdict_doc(path)

    assert result.ok is False
    assert (
        "Mode A Verdict must cite both operator-log.md and dogfood_metrics.md"
        in result.missing_requirements
    )


def test_validate_verdict_doc_requires_exactly_three_questions(tmp_path: Path) -> None:
    path = tmp_path / "adrb_post_dogfood_verdict.md"
    path.write_text(
        """# Antiek Deep Research Bridge Post-Dogfood Verdict

## Mode A Verdict

Verdict: ITERATE

Evidence:
- `operator-log.md` shows three publishable drafts and two heavy edits.
- `dogfood_metrics.md` records 3 Mode A draft exports.

## Mode B Verdict

Verdict: SHIP

Evidence:
- `operator-log.md` says four projects ran at least one generated prompt.
- `dogfood_metrics.md` shows 80.0% would-run signals.

## Next 3 Sharp Questions

1. What makes Mode A drafts publishable without manual rewrite?
2. Which prompt classes drive repeat Mode B usage?
3. Does session timing predict bridge abandonment?
4. Which provider is cheapest?

## Wave 4

Decision: decline Wave 4 until the next dogfood cohort.
""",
        encoding="utf-8",
    )

    result = validate_verdict_doc(path)

    assert result.ok is False
    assert "expected exactly 3 next sharp questions, found 4" in (
        result.missing_requirements
    )


def test_validate_verdict_doc_requires_wave4_candidate_when_proposed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "adrb_post_dogfood_verdict.md"
    path.write_text(
        """# Antiek Deep Research Bridge Post-Dogfood Verdict

## Mode A Verdict

Verdict: ITERATE

Evidence:
- `operator-log.md` shows three publishable drafts and two heavy edits.
- `dogfood_metrics.md` records 3 Mode A draft exports.

## Mode B Verdict

Verdict: SHIP

Evidence:
- `operator-log.md` says four projects ran at least one generated prompt.
- `dogfood_metrics.md` shows 80.0% would-run signals.

## Next 3 Sharp Questions

1. What makes Mode A drafts publishable without manual rewrite?
2. Which prompt classes drive repeat Mode B usage?
3. Does session timing predict bridge abandonment?

## Wave 4

Decision: propose Wave 4 for Mode A outline sharpening.
""",
        encoding="utf-8",
    )

    result = validate_verdict_doc(path)

    assert result.ok is False
    assert "Wave 4 proposal must name at least one candidate" in (
        result.missing_requirements
    )


def test_validate_verdict_doc_allows_wave4_decline_without_candidates(
    tmp_path: Path,
) -> None:
    path = tmp_path / "adrb_post_dogfood_verdict.md"
    path.write_text(
        """# Antiek Deep Research Bridge Post-Dogfood Verdict

## Mode A Verdict

Verdict: KILL

Evidence:
- `operator-log.md` records zero drafts the operator would send.
- `dogfood_metrics.md` records 0 Mode A draft exports.

## Mode B Verdict

Verdict: KILL

Evidence:
- `operator-log.md` records no generated prompt follow-through.
- `dogfood_metrics.md` shows 0.0% would-run signals.

## Next 3 Sharp Questions

1. What non-bridge workflow should absorb the useful parts?
2. Which substrate metrics should be retired?
3. What evidence would justify reopening the bridge?

## Wave 4

Decision: decline Wave 4; no Wave 4 until a new operator pull appears.
""",
        encoding="utf-8",
    )

    result = validate_verdict_doc(path)

    assert result.ok is True
    assert result.mode_a_verdict == "KILL"
    assert result.mode_b_verdict == "KILL"


def test_validate_verdict_doc_accepts_evidence_backed_verdict(tmp_path: Path) -> None:
    path = tmp_path / "adrb_post_dogfood_verdict.md"
    path.write_text(
        """# Antiek Deep Research Bridge Post-Dogfood Verdict

## Evidence Sources

- Operator log: `runs/adrb/operator-log.md`
- Metrics report: `runs/adrb/dogfood_metrics.md`

## Mode A Verdict

Verdict: ITERATE

Evidence:
- `operator-log.md` shows three publishable drafts and two heavy edits.
- `dogfood_metrics.md` records 3 Mode A draft exports.

Salvage if killed or iterated:
- Keep draft export tracking and narrow the outline generator.

## Mode B Verdict

Verdict: SHIP

Evidence:
- `operator-log.md` says four projects ran at least one generated prompt.
- `dogfood_metrics.md` shows 80.0% would-run signals.

Salvage if killed or iterated:
- None; ship the prompt review loop as the primary bridge mode.

## Next 3 Sharp Questions

1. What makes Mode A drafts publishable without manual rewrite?
2. Which prompt classes drive repeat Mode B usage?
3. Does session timing predict bridge abandonment?

## Wave 4

Decision: propose Wave 4 only for Mode A outline sharpening.

Candidates:
1. Outline quality harness.
2. Prompt provenance view.
3. Session abandonment metrics.
""",
        encoding="utf-8",
    )

    result = validate_verdict_doc(path)

    assert result.ok is True
    assert result.mode_a_verdict == "ITERATE"
    assert result.mode_b_verdict == "SHIP"
    assert len(result.next_questions) == 3
