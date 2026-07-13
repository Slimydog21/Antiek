"""Tests for substrate/twin_note_taker/promotion_planner.py — twin → graph (ask #4)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from substrate.twin_note_taker.promotion_planner import (
    PromotableFinding,
    TwinPromotionError,
    TwinPromotionPlan,
    canonical_text,
    plan_twin_promotion,
    predicted_node_id,
)


@dataclass
class FakeFinding:
    node_id: str
    text: str


def _plan(insights=(), questions=(), asset="asset-7", inv="inv-1"):
    return plan_twin_promotion(
        asset_id=asset,
        investigation_id=inv,
        insights=list(insights),
        open_questions=list(questions),
    )


# ---------------------------------------------------------------------------
# execution-faithfulness: predicted_node_id is deterministic content-addressed
# ---------------------------------------------------------------------------


def test_predicted_node_id_deterministic():
    a = predicted_node_id("insight", "attention scales quadratically")
    b = predicted_node_id("insight", "attention scales quadratically")
    assert a == b
    assert a.startswith("insight-")  # prefix IS part of the id
    assert len(a.split("-")[1]) == 16  # SHA-256 truncated to 16 hex


def test_predicted_node_id_insight_vs_question_differ():
    a = predicted_node_id("insight", "same text")
    b = predicted_node_id("question", "same text")
    assert a != b


def test_predicted_node_id_bad_kind_rejected():
    with pytest.raises(TwinPromotionError):
        predicted_node_id("bogus", "text")


def test_canonical_text_normalizes():
    assert canonical_text("  Hello   WORLD  ") == "hello world"
    assert canonical_text("A\n\nB") == "a b"


# ---------------------------------------------------------------------------
# basic planning
# ---------------------------------------------------------------------------


def test_plan_one_insight():
    plan = _plan(insights=[FakeFinding("n1", "transformers are powerful")])
    assert plan.total_promotable == 1
    assert len(plan.promotable_insights) == 1
    f = plan.promotable_insights[0]
    assert f.kind == "insight"
    assert f.source_asset_id == "asset-7"
    assert f.source_investigation_id == "inv-1"
    assert f.dedup_of is None
    assert f.predicted_node_id == predicted_node_id("insight", "transformers are powerful")


def test_plan_questions_and_insights():
    plan = _plan(
        insights=[FakeFinding("n1", "alpha")],
        questions=[FakeFinding("q1", "what next?")],
    )
    assert len(plan.promotable_insights) == 1
    assert len(plan.promotable_questions) == 1
    assert plan.promotable_questions[0].kind == "question"


def test_empty_plan_is_empty():
    plan = _plan()
    assert plan.is_empty is True
    assert plan.total_promotable == 0


# ---------------------------------------------------------------------------
# blank filtering — never promote empty
# ---------------------------------------------------------------------------


def test_blank_texts_filtered():
    plan = _plan(
        insights=[
            FakeFinding("n1", "   "),
            FakeFinding("n2", ""),
            FakeFinding("n3", "real insight"),
        ]
    )
    assert len(plan.promotable_insights) == 1
    assert plan.promotable_insights[0].text == "real insight"
    assert plan.blank_filtered == 2


# ---------------------------------------------------------------------------
# content-addressed dedup — same canonical text = same node_id
# ---------------------------------------------------------------------------


def test_dedup_same_text_within_insights():
    plan = _plan(
        insights=[
            FakeFinding("n1", "attention scales"),
            FakeFinding("n2", "attention scales"),  # same canonical text
        ]
    )
    assert len(plan.promotable_insights) == 2  # both appear
    # but the second is marked dedup_of the first
    canonical = plan.promotable_insights[0]
    dup = plan.promotable_insights[1]
    assert canonical.dedup_of is None
    assert dup.dedup_of == canonical.predicted_node_id
    assert canonical.predicted_node_id == dup.predicted_node_id
    assert plan.dedup_collapsed == 1


def test_dedup_across_whitespace_normalization():
    # "Attention   Scales" and "attention scales" canonicalize to the same node_id
    plan = _plan(
        insights=[
            FakeFinding("n1", "Attention   Scales"),
            FakeFinding("n2", "attention scales"),
        ]
    )
    assert plan.promotable_insights[0].predicted_node_id == plan.promotable_insights[1].predicted_node_id
    assert plan.dedup_collapsed == 1


def test_dedup_across_insights_and_questions_not_merged():
    # an insight and a question with the same text get DIFFERENT node_ids
    # (different kind prefix) — they do not dedup
    plan = _plan(
        insights=[FakeFinding("n1", "same text")],
        questions=[FakeFinding("q1", "same text")],
    )
    assert len(plan.promotable_insights) == 1
    assert len(plan.promotable_questions) == 1
    assert plan.promotable_insights[0].predicted_node_id != plan.promotable_questions[0].predicted_node_id
    assert plan.dedup_collapsed == 0


# ---------------------------------------------------------------------------
# provenance — every promotion traceable
# ---------------------------------------------------------------------------


def test_provenance_carried():
    plan = _plan(
        insights=[FakeFinding("n1", "x")],
        asset="asset-42",
        inv="inv-99",
    )
    f = plan.promotable_insights[0]
    assert f.source_asset_id == "asset-42"
    assert f.source_investigation_id == "inv-99"


def test_empty_provenance_rejected():
    with pytest.raises(TwinPromotionError):
        plan_twin_promotion(
            asset_id="  ", investigation_id="inv", insights=[], open_questions=[]
        )
    with pytest.raises(TwinPromotionError):
        plan_twin_promotion(
            asset_id="a", investigation_id="  ", insights=[], open_questions=[]
        )


# ---------------------------------------------------------------------------
# advisory authority — plan is data, no execution
# ---------------------------------------------------------------------------


def test_plan_is_frozen_value():
    plan = _plan(insights=[FakeFinding("n1", "x")])
    assert isinstance(plan, TwinPromotionPlan)
    assert isinstance(plan.promotable_insights, tuple)
    assert isinstance(plan.promotable_insights[0], PromotableFinding)


def test_plan_is_pure_idempotent():
    args = dict(
        asset_id="a", investigation_id="i",
        insights=[FakeFinding("n1", "x")],
        open_questions=[],
    )
    assert plan_twin_promotion(**args) == plan_twin_promotion(**args)


# ---------------------------------------------------------------------------
# cross-asset reuse — the recursion signal
# ---------------------------------------------------------------------------


def test_same_insight_from_different_assets_same_node_id():
    plan_a = _plan(insights=[FakeFinding("n1", "shared insight")], asset="a1", inv="i1")
    plan_b = _plan(insights=[FakeFinding("n2", "shared insight")], asset="a2", inv="i2")
    # content-addressed: same text → same node_id, regardless of source asset
    assert plan_a.promotable_insights[0].predicted_node_id == plan_b.promotable_insights[0].predicted_node_id
    # but provenance differs
    assert plan_a.promotable_insights[0].source_asset_id == "a1"
    assert plan_b.promotable_insights[0].source_asset_id == "a2"


def test_dedup_collapsed_count_is_honest():
    plan = _plan(
        insights=[
            FakeFinding("n1", "unique"),
            FakeFinding("n2", "dup"),
            FakeFinding("n3", "dup"),
            FakeFinding("n4", "dup"),
        ]
    )
    # 1 unique + 3 dups of "dup" → dedup_collapsed counts the collapses
    assert plan.dedup_collapsed == 2  # n3 and n4 collapse onto n2
    assert len(plan.promotable_insights) == 4  # all appear, marked


# ---------------------------------------------------------------------------
# Mirror-parity guard (turn-128 hardening).
# ---------------------------------------------------------------------------
from substrate.graph.insight_question import (  # noqa: E402
    canonical_text as main_canonical_text,
)
from substrate.graph.ops import (  # noqa: E402
    content_addressed_id as main_content_addressed_id,
)

_PARITY_CASES = [
    "",
    "simple text",
    "  Leading   spaces  ",
    "Mixed" "\t" "WHITESPACE" "\n" "Newlines",
    "café résumé naïve",
    "identical",
    "IDENTICAL",
]


def test_canonical_text_mirror_matches_on_main_implementation():
    for case in _PARITY_CASES:
        assert canonical_text(case) == main_canonical_text(case), (
            f"canonical_text mirror drifted for {case!r}: "
            f"planner={canonical_text(case)!r} "
            f"main={main_canonical_text(case)!r}"
        )


def test_predicted_node_id_matches_on_main_content_addressing():
    from substrate.twin_note_taker.promotion_planner import predicted_node_id

    for kind in ("insight", "question"):
        for case in _PARITY_CASES:
            expected = main_content_addressed_id(kind, main_canonical_text(case))
            actual = predicted_node_id(kind, case)
            assert actual == expected, (
                f"predicted_node_id drifted for kind={kind!r} text={case!r}: "
                f"planner={actual!r} main={expected!r}"
            )
