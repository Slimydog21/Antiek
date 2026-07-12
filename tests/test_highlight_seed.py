"""Tests for substrate.reading.highlight_seed -- pure highlight -> research seed."""

from __future__ import annotations

import pytest

from substrate.reading.highlight_seed import (
    FormulatedQuestion,
    Highlight,
    InvalidSeedError,
    ParentAssetContext,
    ResearchSeed,
    approve_seed,
    formulate_research_seed,
)


class StubFormulator:
    """Deterministic formulator for tests -- stands in for the model-backed one."""

    def __init__(self, question: str, rationale: str | None = None) -> None:
        self._question = question
        self._rationale = rationale

    def formulate(
        self, highlight: Highlight, context: ParentAssetContext
    ) -> FormulatedQuestion:
        return FormulatedQuestion(question=self._question, rationale=self._rationale)


def _ctx(asset_id: str = "asset-1") -> ParentAssetContext:
    return ParentAssetContext(asset_id=asset_id, title="Some Paper", asset_kind="paper")


def _highlight(text: str = "attention is all you need", asset_id: str = "asset-1") -> Highlight:
    return Highlight(text=text, parent_asset_id=asset_id)


# --- happy path -----------------------------------------------------------


def test_formulate_returns_proposed_seed_with_provenance() -> None:
    seed = formulate_research_seed(
        _highlight(), _ctx(), formulator=StubFormulator("Why is attention sufficient?")
    )

    assert seed.status == "proposed"
    assert seed.question == "Why is attention sufficient?"
    assert seed.highlight.text == "attention is all you need"
    assert seed.highlight.parent_asset_id == "asset-1"
    assert seed.parent_asset.asset_id == "asset-1"
    assert seed.parent_asset.title == "Some Paper"
    assert seed.superseded_by is None
    assert seed.seed_id.startswith("seed_")
    assert seed.schema_version == 1


def test_formulate_injects_formulator_pure_no_network() -> None:
    """The formulator is the only question source; no model call happens here."""
    captured: list[str] = []

    class CapturingFormulator:
        def formulate(
            self, highlight: Highlight, context: ParentAssetContext
        ) -> FormulatedQuestion:
            captured.append(highlight.text)
            return FormulatedQuestion(question="chased?")

    seed = formulate_research_seed(_highlight("raw"), _ctx(), formulator=CapturingFormulator())

    assert seed.question == "chased?"
    assert captured == ["raw"]  # the formulator saw the (normalized) highlight


# --- content-addressed identity ------------------------------------------


def test_same_highlight_and_question_yield_same_id() -> None:
    h = _highlight("identical text")
    a = formulate_research_seed(h, _ctx(), formulator=StubFormulator("same Q?"))
    b = formulate_research_seed(h, _ctx(), formulator=StubFormulator("same Q?"))
    assert a.seed_id == b.seed_id


def test_different_question_yields_different_id() -> None:
    h = _highlight("shared text")
    a = formulate_research_seed(h, _ctx(), formulator=StubFormulator("question one?"))
    b = formulate_research_seed(h, _ctx(), formulator=StubFormulator("question two?"))
    assert a.seed_id != b.seed_id


def test_different_parent_yields_different_id() -> None:
    h1 = _highlight("shared text", asset_id="asset-A")
    h2 = _highlight("shared text", asset_id="asset-B")
    a = formulate_research_seed(h1, ParentAssetContext(asset_id="asset-A"), formulator=StubFormulator("Q?"))
    b = formulate_research_seed(h2, ParentAssetContext(asset_id="asset-B"), formulator=StubFormulator("Q?"))
    assert a.seed_id != b.seed_id


def test_rationale_excluded_from_identity() -> None:
    h = _highlight("shared text")
    a = formulate_research_seed(
        h, _ctx(), formulator=StubFormulator("Q?", rationale="because A")
    )
    b = formulate_research_seed(
        h, _ctx(), formulator=StubFormulator("Q?", rationale="because B")
    )
    assert a.seed_id == b.seed_id
    assert a.rationale != b.rationale


def test_highlight_id_distinct_from_unknown() -> None:
    """An unknown highlight_id (None) must not collide with a known one."""
    h_known = Highlight(text="t", parent_asset_id="a", highlight_id="h-1")
    h_unknown = Highlight(text="t", parent_asset_id="a", highlight_id=None)
    a = formulate_research_seed(h_known, ParentAssetContext(asset_id="a"), formulator=StubFormulator("Q?"))
    b = formulate_research_seed(h_unknown, ParentAssetContext(asset_id="a"), formulator=StubFormulator("Q?"))
    assert a.seed_id != b.seed_id


# --- validation / honesty -------------------------------------------------


def test_empty_highlight_rejected() -> None:
    with pytest.raises(InvalidSeedError, match="non-empty highlight"):
        formulate_research_seed(_highlight("   "), _ctx(), formulator=StubFormulator("Q?"))


def test_empty_question_rejected() -> None:
    with pytest.raises(InvalidSeedError, match="empty question"):
        formulate_research_seed(_highlight(), _ctx(), formulator=StubFormulator("   "))


def test_parent_mismatch_rejected() -> None:
    h = _highlight(asset_id="asset-1")
    mismatched = ParentAssetContext(asset_id="asset-OTHER")
    with pytest.raises(InvalidSeedError, match="does not match"):
        formulate_research_seed(h, mismatched, formulator=StubFormulator("Q?"))


def test_unknowns_surface_as_none_not_fabricated() -> None:
    h = Highlight(text="t", parent_asset_id="a")  # highlight_id, scope unknown
    ctx = ParentAssetContext(asset_id="a")  # title, asset_kind unknown
    seed = formulate_research_seed(h, ctx, formulator=StubFormulator("Q?"))

    assert seed.highlight.highlight_id is None
    assert seed.highlight.scope is None
    assert seed.parent_asset.title is None
    assert seed.parent_asset.asset_kind is None


def test_whitespace_normalized_in_stored_highlight_and_question() -> None:
    seed = formulate_research_seed(
        _highlight("  padded text  "),
        _ctx(),
        formulator=StubFormulator("  padded question?  "),
    )
    assert seed.highlight.text == "padded text"
    assert seed.question == "padded question?"


# --- consent gate lifecycle -----------------------------------------------


def test_seed_leaves_proposed_not_dispatched() -> None:
    seed = formulate_research_seed(_highlight(), _ctx(), formulator=StubFormulator("Q?"))
    assert seed.status == "proposed"  # the launch gate: not yet consented


def test_approve_transitions_to_approved() -> None:
    seed = formulate_research_seed(_highlight(), _ctx(), formulator=StubFormulator("Q?"))
    approved = approve_seed(seed)
    assert approved.status == "approved"
    assert seed.status == "proposed"  # original unchanged (model_copy, not mutate)


def test_approve_is_idempotent() -> None:
    seed = formulate_research_seed(_highlight(), _ctx(), formulator=StubFormulator("Q?"))
    once = approve_seed(seed)
    twice = approve_seed(once)
    assert once.status == "approved"
    assert twice.status == "approved"
    assert once.seed_id == twice.seed_id


def test_approve_preserves_identity() -> None:
    seed = formulate_research_seed(_highlight(), _ctx(), formulator=StubFormulator("Q?"))
    approved = approve_seed(seed)
    assert approved.seed_id == seed.seed_id  # consent does not change identity
    assert approved.question == seed.question


# --- round-trip serialization --------------------------------------------


def test_seed_serializes_round_trip() -> None:
    seed = formulate_research_seed(
        _highlight(), _ctx(), formulator=StubFormulator("Q?", rationale="why")
    )
    approved = approve_seed(seed)
    revived = ResearchSeed.model_validate(approved.model_dump())
    assert revived == approved
    assert revived.status == "approved"
