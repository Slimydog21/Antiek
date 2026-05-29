"""SPR-03 M6 — extraction-quality check in substrate.quality_gate.

Distinguishes real extracted text from OCR garbage / near-empty output before
ingest, REUSING acquisition.corpus_quality's calibrated heuristics (real-word
ratio, OCR-garbage) rather than re-deriving thresholds, plus an explicit
near-empty / single-repeated-glyph guard.

The check is a QUALITY decision only: a failing extraction is REJECTED (not
rerouted), and it NEVER touches content_class / servability — passing quality
is not a license grant (the §9.0 deny-by-default invariant is unaffected).
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.quality_gate import (  # noqa: E402
    CandidateNote,
    CheckResult,
    CheckResultKind,
    QualityGateVerdict,
    check_extraction_quality,
    check_verification,
    check_voice_style,
    run_quality_gate,
)

# Clean, real prose (well above the 0.60 real-word-ratio + 20-token floors).
_CLEAN = (
    "The transformer architecture replaced recurrent layers with attention. "
    "Each token attends to every other token in the sequence, and the model "
    "learns position through added encodings. This parallelism is why training "
    "scales across many accelerators where recurrent models could not. "
    "The result reshaped natural language processing over the following years."
)

# OCR garble: low alpha-char ratio + single-char speckle, vowel-free runs.
_OCR_GARBAGE = (
    "rn cl l l 1 1 0 // \\ |  rn  vv  l  l  9 8 7 ~ ` ^ %% $$ ## @@ "
    "l rn cl ii 1l 0O  \\/  |_|  rn rn rn  l l l l  cl cl  9 0 1 2 3 4 5"
)

# Near-empty: a few whitespace-only / trivial tokens.
_NEAR_EMPTY = "   \n\t  "

# Single repeated glyph — degenerate extraction artifact.
_REPEATED_GLYPH = "a" * 500


def _note(prose: str) -> CandidateNote:
    return CandidateNote(
        note_id="extract-1", user_id="corpus",
        prose=prose, claims=("c-1",),
        claim_evidence={"c-1": ("chunk-a",)},
        cited_source_tiers=(2,),
    )


# ---------------------------------------------------------------------------
# The check in isolation
# ---------------------------------------------------------------------------


def test_clean_text_accepted():
    r = check_extraction_quality(_note(_CLEAN))
    assert r.kind == CheckResultKind.PASS
    assert r.check_name == "extraction_quality"
    assert r.score > 0.6


def test_ocr_garbage_rejected():
    r = check_extraction_quality(_note(_OCR_GARBAGE))
    assert r.kind == CheckResultKind.FAIL
    assert r.reasons  # carries a why


def test_near_empty_rejected():
    r = check_extraction_quality(_note(_NEAR_EMPTY))
    assert r.kind == CheckResultKind.FAIL
    assert "empty" in r.reasons[0].lower()


def test_single_repeated_glyph_rejected():
    """A 500-char run of one glyph is one long token — the token-ratio checks
    could paradoxically pass it, so the distinct-character guard catches it."""
    r = check_extraction_quality(_note(_REPEATED_GLYPH))
    assert r.kind == CheckResultKind.FAIL
    assert "distinct" in r.reasons[0].lower()


def test_check_returns_only_a_checkresult_never_a_content_class():
    """The check yields a CheckResult and nothing else — it has no field that
    could carry / mutate content_class or servability (quality-only)."""
    r = check_extraction_quality(_note(_CLEAN))
    assert isinstance(r, CheckResult)
    assert not hasattr(r, "content_class")
    assert not hasattr(r, "servability")


# ---------------------------------------------------------------------------
# Integration with the gate — a failing extraction is REJECTED, not warned
# ---------------------------------------------------------------------------


def test_gate_rejects_garbage_extraction():
    """run_quality_gate with the extraction check rejects OCR garbage — verdict
    REJECT (it is not a document), NOT reroute-private."""
    verdict = run_quality_gate(
        _note(_OCR_GARBAGE),
        verification_check=check_verification,
        extraction_quality_check=check_extraction_quality,
    )
    assert verdict.verdict == QualityGateVerdict.REJECT
    assert any(
        c.check_name == "extraction_quality" and c.kind == CheckResultKind.FAIL
        for c in verdict.checks
    )


def test_gate_passes_clean_extraction():
    """Clean extracted text + a verified note passes to PASS_PUBLIC; the
    extraction check did not falsely block a real document."""
    verdict = run_quality_gate(
        _note(_CLEAN),
        verification_check=check_verification,
        voice_style_check=check_voice_style,
        extraction_quality_check=check_extraction_quality,
    )
    assert verdict.verdict == QualityGateVerdict.PASS_PUBLIC


def test_extraction_check_omittable_backward_compatible():
    """When the extraction check is NOT passed, the gate behaves exactly as
    before (the param is optional) — clean note still PASS_PUBLIC."""
    verdict = run_quality_gate(
        _note(_CLEAN),
        verification_check=check_verification,
    )
    assert verdict.verdict == QualityGateVerdict.PASS_PUBLIC
    # No extraction_quality check ran.
    assert all(c.check_name != "extraction_quality" for c in verdict.checks)


def test_extraction_fail_rejects_even_when_other_checks_pass():
    """An extraction FAIL rejects even when verification passes — garbage with
    a citation is still garbage (it overrides a would-be reroute/pass)."""
    verdict = run_quality_gate(
        _note(_REPEATED_GLYPH),
        verification_check=check_verification,
        extraction_quality_check=check_extraction_quality,
    )
    assert verdict.verdict == QualityGateVerdict.REJECT
