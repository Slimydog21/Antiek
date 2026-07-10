"""Contract tests for the research-brief approval gate."""

from decimal import Decimal

import pytest

from substrate.research_brief import (
    BriefState,
    ResearchBrief,
    amend,
    approve,
    brief_content_hash,
    clarifying_questions,
    fold_answers,
    link_run,
    parse_html,
    project_to_html,
    run_token,
)


def _draft(*, unattended: bool = False, price_ceiling: Decimal | None = None) -> ResearchBrief:
    return ResearchBrief(
        brief_id="brief-1",
        question="Which evidence should guide the decision?",
        scope="Compare the primary evidence and identify material uncertainty.",
        exclusions=("Unsupported speculation",),
        source_preferences=("Primary sources",),
        budget=("deep", 60, 3),
        price_ceiling=price_ceiling,
        unattended=unattended,
    )


def test_run_token_on_draft_raises() -> None:
    brief = _draft()

    with pytest.raises(ValueError, match="approved"):
        run_token(brief)


def test_unattended_brief_without_price_ceiling_raises() -> None:
    brief = approve(
        _draft(unattended=True),
        actor="operator",
        occurred_at="2026-07-11T01:00:00Z",
    )
    assert brief.state is BriefState.APPROVED

    with pytest.raises(ValueError, match="price ceiling"):
        run_token(brief)


@pytest.mark.parametrize("field", ["question", "scope"])
def test_required_prose_refuses_empty(field: str) -> None:
    values = {"question": "Question", "scope": "Scope", field: "  "}
    with pytest.raises(ValueError, match=field):
        ResearchBrief(brief_id="b", **values)


def test_html_projection_is_standalone_complete_and_round_trips() -> None:
    brief = _draft(price_ceiling=Decimal("4.25"))
    html = project_to_html(brief)
    assert html.lower().startswith("<!doctype html>")
    for value in (brief.question, brief.scope, *brief.exclusions, *brief.source_preferences):
        assert value in html
    assert parse_html(html) == brief


def test_clarifier_uses_stub_generator_and_folds_answers() -> None:
    generated_from: list[str] = []

    def stub(prompt: str) -> list[str]:
        generated_from.append(prompt)
        return ["Which market?", "Which time horizon?"]

    questions = clarifying_questions("Compare vendors", stub)
    folded = fold_answers(
        _draft(),
        questions,
        {"Which market?": "Saudi Arabia", "Which time horizon?": "Five years"},
    )
    assert generated_from == ["Compare vendors"]
    assert "Saudi Arabia" in folded.scope
    assert "Five years" in folded.scope


@pytest.mark.parametrize("count", [0, 1, 4])
def test_clarifier_rejects_question_counts_outside_two_to_three(count: int) -> None:
    with pytest.raises(ValueError, match="2 or 3"):
        clarifying_questions("Prompt", lambda _: [f"Q{i}" for i in range(count)])


def test_lifecycle_records_injected_actor_and_time() -> None:
    amended = amend(_draft(), actor="editor", occurred_at="t1")
    approved = approve(amended, actor="operator", occurred_at="t2")
    assert approved.state is BriefState.APPROVED
    assert [(e.action, e.actor, e.occurred_at) for e in approved.events] == [
        ("amended", "editor", "t1"),
        ("approved", "operator", "t2"),
    ]
    token = run_token(approved)
    assert token.brief_id == approved.brief_id
    assert token.brief_hash == brief_content_hash(approved)


def test_hash_is_stable_and_every_field_edit_changes_it() -> None:
    brief = _draft()
    assert brief_content_hash(brief) == brief_content_hash(_draft())
    edited = ResearchBrief(
        brief_id=brief.brief_id,
        question=brief.question + " Edited",
        scope=brief.scope,
        exclusions=brief.exclusions,
        source_preferences=brief.source_preferences,
        budget=brief.budget,
    )
    assert brief_content_hash(edited) != brief_content_hash(brief)
    record = link_run("run-1", brief)
    assert record.brief_id == brief.brief_id
    assert record.brief_hash == brief_content_hash(brief)
