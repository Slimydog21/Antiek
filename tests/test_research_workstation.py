"""Unit tests for substrate.research_workstation pure-logic residual.

These tests import and call the *shipped* functions from their real start
state. No mocks of the unit under test, no re-implemented oracles, no
hardcoded theater of internal digests except where identity stability is
the behavior under test (same inputs → same twin_id).
"""

from __future__ import annotations

import math

import pytest

from substrate.research_workstation import (
    DEFAULT_RATE_CARD,
    BudgetLimit,
    ModelRateCard,
    NoteTwin,
    ResearchInstance,
    TwinItem,
    apply_merge_plan,
    build_midnight_oil_plan,
    build_note_twin,
    merge_twins,
    plan_merge,
    project_prompt_cost,
    recommend_price_ceiling,
    twin_to_html,
    twin_to_markdown,
    usage_bar,
    would_exceed_budget,
)
from substrate.research_workstation.midnight_oil import MidnightOilError
from substrate.research_workstation.model_budget import BudgetError, estimate_tokens
from substrate.research_workstation.note_twin import TwinItemError
from substrate.research_workstation.research_merge import MergeError

# ---------------------------------------------------------------------------
# Note twin
# ---------------------------------------------------------------------------


def test_build_note_twin_from_strings_and_dicts():
    twin = build_note_twin(
        "doc-alpha",
        insights=[
            "Compounding requires real retrieval reuse",
            {
                "summary": "HTML is the primary view projection",
                "quote": "move away from PDFs",
                "llm_confidence": 0.91,
            },
        ],
        open_questions=["How should midnight oil price ceilings compose with daemon caps?"],
        source_text="Sample asset body about research and reading.",
    )
    assert isinstance(twin, NoteTwin)
    assert twin.asset_id == "doc-alpha"
    assert twin.twin_id.startswith("twin:doc-alpha:")
    assert len(twin.insights) == 2
    assert twin.insights[0].kind == "insight"
    assert twin.insights[1].source_quote == "move away from PDFs"
    assert twin.insights[1].confidence == pytest.approx(0.91)
    assert len(twin.open_questions) == 1
    assert twin.open_questions[0].kind == "open_question"
    assert twin.item_count == 3
    # Source fingerprint is sha256 of source_text
    assert len(twin.source_sha256) == 64


def test_build_note_twin_stable_id_for_same_source():
    a = build_note_twin("doc-x", insights=["i1"], source_text="BODY")
    b = build_note_twin("doc-x", insights=["i1"], source_text="BODY")
    assert a.twin_id == b.twin_id
    assert a.source_sha256 == b.source_sha256


def test_build_note_twin_changes_id_when_source_changes():
    a = build_note_twin("doc-x", insights=["i1"], source_text="BODY-A")
    b = build_note_twin("doc-x", insights=["i1"], source_text="BODY-B")
    assert a.twin_id != b.twin_id


def test_twin_item_rejects_empty_and_bad_confidence():
    with pytest.raises(TwinItemError):
        TwinItem(kind="insight", text="   ")
    with pytest.raises(TwinItemError):
        TwinItem(kind="insight", text="ok", confidence=1.5)
    with pytest.raises(TwinItemError):
        TwinItem(kind="nope", text="ok")  # type: ignore[arg-type]


def test_build_note_twin_rejects_empty_asset_id():
    with pytest.raises(TwinItemError):
        build_note_twin("  ", insights=["x"])


def test_dedup_insights_by_content():
    twin = build_note_twin(
        "doc",
        insights=["Same insight", "Same insight", "Different"],
    )
    assert len(twin.insights) == 2


def test_merge_twins_unions_items():
    t1 = build_note_twin("a", insights=["shared", "only-a"], open_questions=["q-a"])
    t2 = build_note_twin("b", insights=["shared", "only-b"], open_questions=["q-b"])
    merged = merge_twins([t1, t2], merged_asset_id="a+b")
    assert merged.asset_id == "a+b"
    texts = {i.text for i in merged.insights}
    assert texts == {"shared", "only-a", "only-b"}
    qtexts = {i.text for i in merged.open_questions}
    assert qtexts == {"q-a", "q-b"}


def test_merge_twins_requires_at_least_one():
    with pytest.raises(TwinItemError):
        merge_twins([])


def test_twin_to_markdown_and_html_contain_sections():
    twin = build_note_twin(
        "paper-1",
        insights=["Insight A"],
        open_questions=["Why B?"],
        source_text="body",
    )
    md = twin_to_markdown(twin)
    assert "## Insights" in md
    assert "Insight A" in md
    assert "## Open questions" in md
    assert "Why B?" in md
    html = twin_to_html(twin)
    assert 'class="antiek-note-twin"' in html
    assert "Insight A" in html
    assert "Why B?" in html
    # Escapes HTML special chars in content
    evil = build_note_twin("x", insights=['<script>alert("x")</script>'])
    ehtml = twin_to_html(evil)
    assert "<script>" not in ehtml
    assert "&lt;script&gt;" in ehtml


def test_empty_twin_renders_honest_empty_state():
    twin = build_note_twin("empty-doc")
    assert twin.item_count == 0
    md = twin_to_markdown(twin)
    assert "No insights extracted" in md
    assert "No open questions extracted" in md


# ---------------------------------------------------------------------------
# Research merge
# ---------------------------------------------------------------------------


def _completed(iid: str, findings: str, **kwargs) -> ResearchInstance:
    return ResearchInstance(
        instance_id=iid,
        status="completed",
        findings=findings,
        **kwargs,
    )


def test_plan_merge_into_asset_requires_target_and_completed():
    inst = [
        _completed("r1", "Finding one", parent_asset_id="book-1", confidence=0.8),
        ResearchInstance(instance_id="r2", status="running", findings="wip"),
    ]
    blocked = plan_merge(inst, "into_asset")
    assert not blocked.is_executable
    assert "target_asset_id" in (blocked.blocked_reason or "")

    plan = plan_merge(inst, "into_asset", target_asset_id="book-1")
    assert plan.is_executable
    assert plan.mutates_source is True
    assert plan.requires_operator_confirm is True
    assert plan.selected_instance_ids == ("r1",)  # running excluded


def test_plan_merge_draft_never_mutates():
    inst = [_completed("r1", "A"), _completed("r2", "B")]
    plan = plan_merge(inst, "draft_merge", target_asset_id="book-1")
    assert plan.is_executable
    assert plan.mutates_source is False
    assert plan.is_executable


def test_plan_merge_collective_requires_two():
    one = [_completed("r1", "only")]
    plan = plan_merge(one, "collective")
    assert not plan.is_executable
    assert "at least 2" in (plan.blocked_reason or "")

    two = [_completed("r1", "A"), _completed("r2", "B")]
    plan2 = plan_merge(two, "collective")
    assert plan2.is_executable
    assert plan2.selected_instance_ids == ("r1", "r2")


def test_plan_merge_blocks_when_nothing_completed():
    inst = [
        ResearchInstance(instance_id="a", status="pending"),
        ResearchInstance(instance_id="b", status="failed", findings="boom"),
    ]
    plan = plan_merge(inst, "draft_merge")
    assert not plan.is_executable
    assert "no completed" in (plan.blocked_reason or "")


def test_apply_merge_plan_draft_produces_html_and_markdown():
    twin = build_note_twin("book-1", insights=["From twin"], open_questions=["Q?"])
    inst = [
        _completed(
            "r1",
            "Alpha analysis",
            highlight="selected passage",
            twin=twin,
            confidence=0.9,
        ),
        _completed("r2", "Beta analysis", confidence=0.7),
    ]
    plan = plan_merge(inst, "draft_merge")
    doc = apply_merge_plan(inst, plan)
    assert doc.is_draft is True
    assert doc.mode == "draft_merge"
    assert "Alpha analysis" in doc.body_markdown
    assert "Beta analysis" in doc.body_markdown
    assert "selected passage" in doc.body_markdown
    assert 'class="antiek-research-merge"' in doc.body_html
    assert doc.merged_twin is not None
    assert any(i.text == "From twin" for i in doc.merged_twin.insights)
    assert set(doc.source_instance_ids) == {"r1", "r2"}


def test_apply_merge_into_asset_not_draft():
    inst = [_completed("r1", "X", parent_asset_id="asset-9")]
    plan = plan_merge(inst, "into_asset", target_asset_id="asset-9")
    doc = apply_merge_plan(inst, plan)
    assert doc.is_draft is False
    assert doc.metadata["mutates_source"] is True
    assert "asset-9" in doc.title


def test_apply_blocked_plan_raises():
    inst = [_completed("r1", "x")]
    plan = plan_merge(inst, "into_asset")  # missing target
    assert not plan.is_executable
    with pytest.raises(MergeError, match="blocked"):
        apply_merge_plan(inst, plan)


def test_collective_merge_orders_by_confidence():
    inst = [
        _completed("low", "Low conf body", confidence=0.2),
        _completed("high", "High conf body", confidence=0.95),
    ]
    plan = plan_merge(inst, "collective")
    doc = apply_merge_plan(inst, plan)
    # High confidence section should appear before low in markdown
    hi = doc.body_markdown.index("High conf body")
    lo = doc.body_markdown.index("Low conf body")
    assert hi < lo


def test_research_instance_validates_fields():
    with pytest.raises(MergeError):
        ResearchInstance(instance_id="  ", status="completed")
    with pytest.raises(MergeError):
        ResearchInstance(instance_id="ok", status="completed", confidence=2.0)


def test_body_html_escapes_hostile_instance_id():
    """instance_id is untrusted enough to appear in HTML attrs/text — must escape.

    PoC: x"><img src=x onerror=alert(1)> breaks out of data-instance-id when
    unescaped and yields live markup. highlight/findings already escaped;
    instance_id must match that discipline (skeptic gap).

    The test would FAIL on the pre-fix body_html which interpolated
    instance_id raw into attributes and <h2>.
    """
    hostile = 'x"><img src=x onerror=alert(1)>'
    inst = [
        ResearchInstance(
            instance_id=hostile,
            status="completed",
            findings="safe findings",
            highlight="safe highlight",
            confidence=0.8,
        ),
    ]
    plan = plan_merge(inst, "draft_merge")
    doc = apply_merge_plan(inst, plan)
    html = doc.body_html

    # Live markup breakout must not exist (the unescaped PoC form).
    assert "<img src=x onerror=alert(1)>" not in html
    assert 'data-instance-id="x">' not in html
    # Attribute must close only after full escape of the id (no early ").
    assert 'data-instance-id="x&quot;&gt;&lt;img src=x onerror=alert(1)&gt;"' in html
    # Text node also escaped.
    assert "<h2>Instance x&quot;&gt;&lt;img src=x onerror=alert(1)&gt;</h2>" in html
    # Escaped entity form of the angle-bracketed payload is present.
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    # Benign content still present.
    assert "safe findings" in html
    assert "safe highlight" in html


# ---------------------------------------------------------------------------
# Midnight oil
# ---------------------------------------------------------------------------


def test_recommend_price_ceiling_scales_with_time_and_agents():
    short = recommend_price_ceiling(
        ["Map competitive deep-research products"],
        work_minutes=30,
        agent_count=1,
    )
    long = recommend_price_ceiling(
        ["Map competitive deep-research products"],
        work_minutes=120,
        agent_count=1,
    )
    swarm = recommend_price_ceiling(
        ["Map competitive deep-research products"],
        work_minutes=30,
        agent_count=4,
    )
    assert short.recommended_ceiling_usd > 0
    assert long.recommended_ceiling_usd > short.recommended_ceiling_usd
    assert swarm.recommended_ceiling_usd > short.recommended_ceiling_usd
    assert short.work_minutes == 30
    assert short.agent_count == 1
    assert short.goal_count == 1
    # Contingency is positive portion of expected
    assert short.contingency_usd == pytest.approx(
        short.expected_spend_usd * 0.25, rel=1e-3
    )
    assert short.recommended_ceiling_usd == pytest.approx(
        short.expected_spend_usd + short.contingency_usd, rel=1e-2
    )


def test_recommend_price_ceiling_scales_with_goals():
    one = recommend_price_ceiling(["g1"], work_minutes=60, agent_count=1)
    many = recommend_price_ceiling(
        ["g1", "g2", "g3", "g4", "g5"],
        work_minutes=60,
        agent_count=1,
    )
    assert many.estimated_tokens > one.estimated_tokens
    assert many.recommended_ceiling_usd > one.recommended_ceiling_usd


def test_midnight_oil_plan_always_requires_approval():
    plan = build_midnight_oil_plan(
        goals=["Prove arxiv connector usable in deep research"],
        work_minutes=45,
        agent_count=2,
    )
    assert plan.requires_operator_approval is True
    assert plan.goals == ("Prove arxiv connector usable in deep research",)
    assert plan.ceiling.recommended_ceiling_usd > 0
    assert plan.rate_card.model_id == DEFAULT_RATE_CARD.model_id


def test_midnight_oil_rejects_bad_inputs():
    with pytest.raises(MidnightOilError):
        recommend_price_ceiling([], work_minutes=30)
    with pytest.raises(MidnightOilError):
        recommend_price_ceiling(["ok"], work_minutes=1)
    with pytest.raises(MidnightOilError):
        recommend_price_ceiling(["ok"], work_minutes=30, agent_count=0)
    with pytest.raises(MidnightOilError):
        recommend_price_ceiling(["ok"], work_minutes=30, contingency=1.5)


def test_custom_rate_card_affects_ceiling():
    cheap = ModelRateCard(
        model_id="cheap",
        usd_per_1k_input=0.01,
        usd_per_1k_output=0.02,
        tokens_per_minute=1000,
    )
    pricey = ModelRateCard(
        model_id="pricey",
        usd_per_1k_input=5.0,
        usd_per_1k_output=15.0,
        tokens_per_minute=1000,
    )
    a = recommend_price_ceiling(["g"], 60, cheap)
    b = recommend_price_ceiling(["g"], 60, pricey)
    assert b.recommended_ceiling_usd > a.recommended_ceiling_usd
    assert a.model_id == "cheap"


def test_token_estimate_is_integer_and_positive():
    rec = recommend_price_ceiling(["goal"], work_minutes=10, agent_count=1)
    assert isinstance(rec.estimated_tokens, int)
    assert rec.estimated_tokens > 0


# ---------------------------------------------------------------------------
# Model budget projection
# ---------------------------------------------------------------------------


def test_project_prompt_cost_from_real_prompt():
    prompt = "Explain the HTML-first reading surface." * 20
    proj = project_prompt_cost(prompt, expected_output_tokens=500)
    assert proj.prompt_chars == len(prompt)
    assert proj.estimated_input_tokens == estimate_tokens(prompt)
    assert proj.estimated_output_tokens == 500
    assert proj.projected_cost_usd > 0
    # Cost must match rate card arithmetic on the returned token counts
    expected = (
        (proj.estimated_input_tokens / 1000.0) * DEFAULT_RATE_CARD.usd_per_1k_input
        + (proj.estimated_output_tokens / 1000.0) * DEFAULT_RATE_CARD.usd_per_1k_output
    )
    assert proj.projected_cost_usd == pytest.approx(round(expected, 6))


def test_usage_bar_without_projection():
    limit = BudgetLimit(limit_usd=10.0, used_usd=2.5, label="openrouter")
    bar = usage_bar(limit)
    assert bar.fraction_used == pytest.approx(0.25)
    assert bar.percent_used == pytest.approx(25.0)
    assert bar.remaining_usd == pytest.approx(7.5)
    assert bar.projected_cost_usd is None
    assert bar.would_exceed is False


def test_usage_bar_with_projection_flags_exceed():
    limit = BudgetLimit(limit_usd=1.0, used_usd=0.9, label="zai")
    # Large output makes projection blow the remaining $0.10
    proj = project_prompt_cost(
        "x" * 4000,
        expected_output_tokens=50_000,
        rate_card=ModelRateCard(
            model_id="hot",
            usd_per_1k_input=1.0,
            usd_per_1k_output=2.0,
            tokens_per_minute=1000,
        ),
    )
    assert proj.projected_cost_usd > 0.1
    assert would_exceed_budget(limit, proj) is True
    bar = usage_bar(limit, proj)
    assert bar.would_exceed is True
    assert bar.projected_used_usd is not None
    assert bar.projected_used_usd > limit.limit_usd
    assert bar.over_budget_usd > 0


def test_usage_bar_safe_prompt_does_not_exceed():
    limit = BudgetLimit(limit_usd=100.0, used_usd=1.0, label="pool")
    proj = project_prompt_cost("short", expected_output_tokens=10)
    assert would_exceed_budget(limit, proj) is False
    bar = usage_bar(limit, proj)
    assert bar.would_exceed is False
    assert bar.projected_fraction is not None
    assert bar.projected_fraction < 1.0


def test_zero_limit_blocks_any_positive_spend():
    limit = BudgetLimit(limit_usd=0.0, used_usd=0.0)
    proj = project_prompt_cost("hi", expected_output_tokens=100)
    # positive cost with zero limit
    if proj.projected_cost_usd > 0:
        assert would_exceed_budget(limit, proj) is True


def test_budget_rejects_negative():
    with pytest.raises(BudgetError):
        BudgetLimit(limit_usd=-1, used_usd=0)
    with pytest.raises(BudgetError):
        project_prompt_cost("x", expected_output_tokens=-5)


def test_estimate_tokens_empty_is_zero():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1  # 4 chars / 4 = 1
    assert estimate_tokens("a" * 9) == math.ceil(9 / 4)


# ---------------------------------------------------------------------------
# Package surface
# ---------------------------------------------------------------------------


def test_package_exports_are_importable():
    import substrate.research_workstation as rw

    for name in rw.__all__:
        assert hasattr(rw, name), name
