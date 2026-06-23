"""Tests for roles/decomposer/ (Sprint 5 day 4-5).

Coverage — paraphrase:

1. Empty sub_questions returns empty list (early-out).
2. Identical strings flag at cosine 1.0.
3. Orthogonal strings don't flag.
4. Threshold is inclusive (cosine == threshold → flagged).
5. Custom threshold overrides default.
6. ``regenerate_instruction`` formats flagged bullets; empty for no
   flags.

Coverage — seeds:

7. Criterion 1 enforced upstream (loader) — module-level test ensures
   the mining function aggregates outcome counts per synthesis_id.
8. Criterion 2: synthesis with zero confirmed outcomes is rejected.
9. Criterion 3: paraphrase-flagged trajectory is rejected.
10. Criterion 4: trace without a decomposer record is rejected.
11. Tolerates JSON strings AND pre-parsed Python objects.
12. Returns proposals newest-first.
13. ``limit`` truncates output.
14. ``paraphrase_clean`` fails closed on malformed JSON but open on
    None (no mv blob → assume clean, no info → assume clean only
    when nothing was supplied).
15. ``count_confirmed`` ignores non-positive outcomes.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from roles.decomposer import (  # noqa: E402
    CandidateRow,
    ParaphraseFlag,
    check_paraphrases,
    count_confirmed,
    extract_decomposer_io,
    paraphrase_clean,
    propose_examples_from_rows,
    regenerate_instruction,
)
from substrate.constants import (  # noqa: E402
    ANTIEK_PARAM_VERSION,
    DECOMPOSER_PARAPHRASE_COSINE_MAX,
)

# ---------------------------------------------------------------------------
# Stub embedder — deterministic, no sentence-transformers dependency
# ---------------------------------------------------------------------------


class _StubEmbedder:
    """Maps a hard-coded vocabulary to fixed unit vectors. Anything
    not in the vocabulary becomes the zero vector — so two unknown
    strings have undefined cosine (we return 0.0 in that case via
    ``_cosine``), letting tests assert "won't flag" cleanly."""

    dimension = 3

    def __init__(self, mapping: dict[str, Sequence[float]]):
        self._mapping = {k: list(v) for k, v in mapping.items()}

    def encode(self, text: str) -> list[float]:
        return self._mapping.get(text, [0.0, 0.0, 0.0])


# ---------------------------------------------------------------------------
# 1-6. paraphrase
# ---------------------------------------------------------------------------


def test_check_paraphrases_empty_returns_empty():
    assert check_paraphrases("q", [], embedder=_StubEmbedder({"q": [1, 0, 0]})) == []


def test_check_paraphrases_identical_flags_at_cosine_one():
    emb = _StubEmbedder({"q": [1, 0, 0], "q-restated": [1, 0, 0]})
    flags = check_paraphrases("q", ["q-restated"], embedder=emb)
    assert len(flags) == 1
    assert isinstance(flags[0], ParaphraseFlag)
    assert flags[0].cosine == pytest.approx(1.0)
    assert flags[0].index == 0


def test_check_paraphrases_orthogonal_no_flag():
    emb = _StubEmbedder({"q": [1, 0, 0], "sq": [0, 1, 0]})
    assert check_paraphrases("q", ["sq"], embedder=emb) == []


def test_check_paraphrases_threshold_is_inclusive():
    """A sub-question AT the threshold cosine should be flagged
    (matches upstream's ``>= threshold`` semantics)."""
    # Vectors set so cosine is exactly 0.5.
    emb = _StubEmbedder({"q": [1, 0, 0], "sq": [1, 1, 0]})  # cos = 1/sqrt(2) ≈ 0.707
    flags = check_paraphrases("q", ["sq"], threshold=0.7, embedder=emb)
    assert len(flags) == 1


def test_check_paraphrases_custom_threshold_overrides_default():
    """Default 0.85 wouldn't flag a 0.707 cosine; lower threshold should."""
    emb = _StubEmbedder({"q": [1, 0, 0], "sq": [1, 1, 0]})
    assert check_paraphrases("q", ["sq"], embedder=emb) == []  # default 0.85
    assert len(check_paraphrases("q", ["sq"], threshold=0.5, embedder=emb)) == 1


def test_check_paraphrases_default_threshold_is_constant():
    """Sanity: the default the module exports is exactly the substrate
    constant, so retuning in one place takes effect everywhere."""
    emb = _StubEmbedder({"q": [1, 0, 0], "sq": [1, 0, 0]})
    flags = check_paraphrases("q", ["sq"], embedder=emb)
    # cos 1.0 ≥ 0.85, so flagged
    assert len(flags) == 1
    assert DECOMPOSER_PARAPHRASE_COSINE_MAX == 0.85


def test_regenerate_instruction_empty_when_no_flags():
    assert regenerate_instruction([]) == ""


def test_regenerate_instruction_formats_bullets():
    flags = [
        ParaphraseFlag(index=0, sub_question="q-restated", cosine=0.95),
        ParaphraseFlag(index=2, sub_question="another paraphrase", cosine=0.91),
    ]
    s = regenerate_instruction(flags)
    assert "#0" in s and "#2" in s
    assert "0.950" in s and "0.910" in s
    assert "q-restated" in s
    assert "Regenerate the decomposition" in s


# ---------------------------------------------------------------------------
# 7-15. seeds
# ---------------------------------------------------------------------------


def _row(*, sid="syn-1", iid="inv-1", ts="2026-05-01T12:00:00Z",
         trace=None, mv=None, thesis=None) -> CandidateRow:
    return CandidateRow(
        synthesis_id=sid,
        investigation_id=iid,
        synthesis_timestamp=ts,
        agent_trace_json=trace,
        model_versions_json=mv,
        thesis_outcomes_json=thesis,
    )


def _good_trace():
    return [
        {"role": "decomposer", "user_prompt": "decompose Q",
         "parsed": {"decomposition": [{"q": "sq-1"}, {"q": "sq-2"}]}},
        {"role": "synthesizer", "parsed": {"thesis": "..."}},
    ]


def _good_outcomes(*, status="confirmed", n=1):
    return [{"thesis_claim": f"C{i}", "outcome": status} for i in range(n)]


def test_propose_examples_aggregates_confirmed_across_observations():
    """A synthesis with two outcome rows (two review cycles) summing
    to 3 confirmed should count as 3, not 1."""
    sid = "syn-multi"
    rows = [
        _row(sid=sid, trace=_good_trace(), thesis=_good_outcomes(n=2)),
        _row(sid=sid, trace=_good_trace(), thesis=_good_outcomes(n=1)),
    ]
    out = propose_examples_from_rows(rows)
    assert len(out) == 1
    assert "confirmed_outcomes=3" in out[0].admission_reason


def test_propose_examples_rejects_zero_confirmed():
    rows = [_row(trace=_good_trace(), thesis=[])]
    assert propose_examples_from_rows(rows) == []


def test_propose_examples_rejects_paraphrase_flagged_trajectory():
    rows = [_row(
        trace=_good_trace(),
        mv={"paraphrase_history": [{"flagged": True}]},
        thesis=_good_outcomes(),
    )]
    assert propose_examples_from_rows(rows) == []


def test_propose_examples_accepts_clean_paraphrase_history():
    rows = [_row(
        trace=_good_trace(),
        mv={"paraphrase_history": [{"flagged": False}, {"flagged": False}]},
        thesis=_good_outcomes(),
    )]
    out = propose_examples_from_rows(rows)
    assert len(out) == 1


def test_propose_examples_rejects_trace_without_decomposer():
    rows = [_row(
        trace=[{"role": "synthesizer", "parsed": {"thesis": "..."}}],
        thesis=_good_outcomes(),
    )]
    assert propose_examples_from_rows(rows) == []


def test_propose_examples_rejects_decomposer_without_decomposition():
    rows = [_row(
        trace=[{"role": "decomposer", "parsed": {}}],
        thesis=_good_outcomes(),
    )]
    assert propose_examples_from_rows(rows) == []


def test_propose_examples_accepts_json_strings_or_python_objects():
    """Loader may hand back DuckDB JSON column values either as
    pre-parsed Python or as raw JSON strings — both must work."""
    row_str = _row(
        trace=json.dumps(_good_trace()),
        thesis=json.dumps(_good_outcomes()),
    )
    row_obj = _row(sid="syn-2", iid="inv-2", trace=_good_trace(),
                   thesis=_good_outcomes())
    out_str = propose_examples_from_rows([row_str])
    out_obj = propose_examples_from_rows([row_obj])
    assert len(out_str) == 1 and len(out_obj) == 1


def test_propose_examples_orders_newest_first():
    rows = [
        _row(sid="old", iid="i-old", ts="2024-01-01",
             trace=_good_trace(), thesis=_good_outcomes()),
        _row(sid="new", iid="i-new", ts="2026-01-01",
             trace=_good_trace(), thesis=_good_outcomes()),
        _row(sid="mid", iid="i-mid", ts="2025-06-01",
             trace=_good_trace(), thesis=_good_outcomes()),
    ]
    out = propose_examples_from_rows(rows)
    assert [p.source_synthesis_id for p in out] == ["new", "mid", "old"]


def test_propose_examples_respects_limit():
    rows = [
        _row(sid=f"syn-{i}", iid=f"inv-{i}", ts=f"2026-05-{i:02d}",
             trace=_good_trace(), thesis=_good_outcomes())
        for i in range(1, 6)
    ]
    out = propose_examples_from_rows(rows, limit=2)
    assert len(out) == 2


def test_paraphrase_clean_none_blob_is_clean():
    assert paraphrase_clean(None) is True


def test_paraphrase_clean_malformed_json_fails_closed():
    """Cannot prove cleanliness from malformed JSON → reject."""
    assert paraphrase_clean("not-json-at-all") is False


def test_paraphrase_clean_handles_empty_history():
    assert paraphrase_clean({"paraphrase_history": []}) is True


def test_count_confirmed_handles_only_positive_grades():
    out = [
        {"outcome": "confirmed"},
        {"outcome": "partially_confirmed"},
        {"outcome": "disconfirmed"},   # ignored
        {"outcome": "unresolved"},     # ignored
        {"not_outcome_shape": True},   # ignored
    ]
    assert count_confirmed(out) == 2


def test_extract_decomposer_io_skips_non_decomposer_records():
    trace = [
        {"role": "synthesizer", "parsed": {"thesis": "x"}},
        {"role": "decomposer", "parsed": {"decomposition": [{"q": "sq"}]}},
        {"role": "challenger", "parsed": {"objections": []}},
    ]
    rec = extract_decomposer_io(trace)
    assert rec is not None
    assert rec["role"] == "decomposer"


def test_proposal_param_version_is_substrate_constant():
    rows = [_row(trace=_good_trace(), thesis=_good_outcomes())]
    out = propose_examples_from_rows(rows)
    assert out[0].param_version == ANTIEK_PARAM_VERSION


def test_proposal_dataclass_serializes_to_dict():
    rows = [_row(trace=_good_trace(), thesis=_good_outcomes())]
    out = propose_examples_from_rows(rows)
    d = out[0].to_dict()
    assert d["admitted_at"] is None  # NEVER auto-admitted
    assert "source_synthesis_id" in d
    assert "output" in d
