"""Collective-analysis draft writer — mechanical combination (§5 invariants)."""

from __future__ import annotations

import pytest

from substrate.collective_analysis_writer import (
    CollectiveAnalysisError,
    CollectiveDraftAnalysis,
    compose_draft_analysis,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _body(
    *,
    inv: str = "inv-1",
    insights: list[str] | None = None,
    questions: list[str] | None = None,
    synthesis: str | None = "Synthesis of the findings.",
    withheld: bool = False,
) -> ResearchArtifactBody:
    # None = use sensible defaults; [] = truly empty (no insights/questions).
    final_insights = (
        [ArtifactInsight(node_id=f"n-{i}", text=t, source_document_id=f"d-{i}")
         for i, t in enumerate(insights)]
        if insights is not None
        else [ArtifactInsight(node_id="n0", text="default insight", source_document_id="d0")]
    )
    final_questions = (
        [ArtifactQuestion(node_id=f"q-{i}", text=t) for i, t in enumerate(questions)]
        if questions is not None
        else []
    )
    return ResearchArtifactBody(
        schema_version=1,
        investigation_id=inv,
        problem_question=f"What does {inv} reveal?",
        insights=final_insights,
        open_questions=final_questions,
        synthesis_excerpt=synthesis,
        synthesis_withheld=withheld,
    )


# --- combination mechanics ------------------------------------------------ #


def test_two_instances_merged_into_one_document() -> None:
    draft = compose_draft_analysis(
        parent_asset_id="asset-1",
        instances=[_body(inv="inv-a"), _body(inv="inv-b")],
    )
    assert isinstance(draft, CollectiveDraftAnalysis)
    assert draft.draft is True
    assert draft.source_instance_ids == ("inv-a", "inv-b")
    assert "inv-a" in draft.combined_html
    assert "inv-b" in draft.combined_html
    assert "<section>" in draft.combined_html


def test_findings_included_in_combined_html() -> None:
    draft = compose_draft_analysis(
        parent_asset_id="asset-1",
        instances=[_body()],
        findings=["manual note one", "manual note two"],
    )
    assert "manual note one" in draft.combined_html
    assert "manual note two" in draft.combined_html


def test_empty_instance_set_rejected() -> None:
    with pytest.raises(CollectiveAnalysisError, match="at least one"):
        compose_draft_analysis(parent_asset_id="asset-1", instances=[])


def test_empty_parent_rejected() -> None:
    with pytest.raises(CollectiveAnalysisError, match="parent_asset_id"):
        compose_draft_analysis(parent_asset_id="  ", instances=[_body()])


# --- no invented content (invariant #1) ----------------------------------- #


def test_missing_synthesis_shows_pending_not_fabricated() -> None:
    incomplete = _body(inv="inv-x", synthesis=None)
    draft = compose_draft_analysis(
        parent_asset_id="asset-1",
        instances=[incomplete],
        instance_complete_flags={"inv-x": False},
    )
    assert "pending" in draft.combined_html.lower()
    assert "inv-x" in draft.combined_html


def test_withheld_synthesis_shown_as_none() -> None:
    withheld = _body(inv="inv-w", withheld=True)
    draft = compose_draft_analysis(
        parent_asset_id="asset-1",
        instances=[withheld],
    )
    # withheld synthesis is None in the contribution — honest placeholder
    assert "inv-w" in draft.combined_html


def test_empty_instance_honest_not_dropped() -> None:
    empty = _body(inv="inv-empty", insights=[], questions=[], synthesis=None)
    draft = compose_draft_analysis(
        parent_asset_id="asset-1",
        instances=[empty],
    )
    assert "inv-empty" in draft.combined_html
    assert "No insights" in draft.combined_html


# --- provenance + idempotency (invariants #2) ----------------------------- #


def test_same_input_produces_same_hash() -> None:
    args = dict(
        parent_asset_id="asset-1",
        instances=[_body(inv="inv-a"), _body(inv="inv-b")],
        findings=["f1"],
    )
    d1 = compose_draft_analysis(**args)
    d2 = compose_draft_analysis(**args)
    assert d1.findings_hash == d2.findings_hash
    assert d1.analysis_id == d2.analysis_id


def test_different_findings_produce_different_hash() -> None:
    d1 = compose_draft_analysis(parent_asset_id="a", instances=[_body()], findings=["f1"])
    d2 = compose_draft_analysis(parent_asset_id="a", instances=[_body()], findings=["f2"])
    assert d1.findings_hash != d2.findings_hash


def test_source_instance_ids_preserve_order() -> None:
    draft = compose_draft_analysis(
        parent_asset_id="a",
        instances=[_body(inv="z"), _body(inv="a"), _body(inv="m")],
    )
    assert draft.source_instance_ids == ("z", "a", "m")


# --- HTML escaping (invariant #3) ----------------------------------------- #


def test_html_in_content_is_escaped() -> None:
    body = _body(inv="inv-x", insights=["<script>alert(1)</script>"])
    draft = compose_draft_analysis(
        parent_asset_id="asset-1",
        instances=[body],
    )
    assert "<script>alert(1)</script>" not in draft.combined_html
    assert "&lt;script&gt;" in draft.combined_html


def test_combined_html_is_valid_structure() -> None:
    draft = compose_draft_analysis(
        parent_asset_id="asset-1",
        instances=[_body()],
    )
    assert draft.combined_html.startswith("<!doctype html>")
    assert "</html>" in draft.combined_html


# --- incomplete flag honesty (invariant #5) ------------------------------- #


def test_incomplete_instance_marked_in_html() -> None:
    draft = compose_draft_analysis(
        parent_asset_id="asset-1",
        instances=[_body(inv="inc")],
        instance_complete_flags={"inc": False},
    )
    assert "not DeepResearchComplete" in draft.combined_html
    assert any(not c.complete for c in draft.instance_contributions)


def test_complete_instance_not_flagged() -> None:
    draft = compose_draft_analysis(
        parent_asset_id="asset-1",
        instances=[_body(inv="ok")],
        instance_complete_flags={"ok": True},
    )
    assert "not DeepResearchComplete" not in draft.combined_html
    assert all(c.complete for c in draft.instance_contributions)


# --- footer findings_hash non-empty (defect 1 fix) ------------------------ #


def test_footer_renders_findings_hash_non_empty() -> None:
    """The provenance footer must show the real findings_hash, never empty."""
    draft = compose_draft_analysis(
        parent_asset_id="asset-1",
        instances=[_body(inv="inv-a")],
        findings=["f1"],
    )
    expected = f"findings_hash=sha256:{draft.findings_hash}"
    assert expected in draft.combined_html
    # never the empty-hash footer that promised a value and showed none
    assert "findings_hash=sha256:" + '"' not in draft.combined_html
    assert "findings_hash=sha256:<" not in draft.combined_html


def test_footer_hash_matches_dataclass_hash() -> None:
    """The footer hash is the one true hash (same source as analysis_id)."""
    draft = compose_draft_analysis(
        parent_asset_id="asset-1",
        instances=[_body(inv="inv-a"), _body(inv="inv-b")],
    )
    assert f"sha256:{draft.findings_hash}" in draft.combined_html
    assert draft.analysis_id == f"collective-draft-{draft.findings_hash[:16]}"


# --- same-parent cohesion enforcement (defect 2 fix) ---------------------- #


def test_cohesion_mismatch_raises_when_parents_attested() -> None:
    """A caller attesting a different parent is rejected — no silent mis-attribute."""
    with pytest.raises(CollectiveAnalysisError, match="attests parent"):
        compose_draft_analysis(
            parent_asset_id="asset-1",
            instances=[_body(inv="inv-a")],
            instance_parent_asset_ids={"inv-a": "asset-DIFFERENT"},
        )


def test_cohesion_matching_parents_succeed() -> None:
    """When all attested parents match the requested parent, the merge proceeds."""
    draft = compose_draft_analysis(
        parent_asset_id="asset-1",
        instances=[_body(inv="inv-a"), _body(inv="inv-b")],
        instance_parent_asset_ids={"inv-a": "asset-1", "inv-b": "asset-1"},
    )
    assert draft.source_instance_ids == ("inv-a", "inv-b")


def test_cohesion_partial_attestation_rejects_only_mismatch() -> None:
    """Only the mismatched instance triggers rejection; a partial map is honest."""
    with pytest.raises(CollectiveAnalysisError, match="inv-b"):
        compose_draft_analysis(
            parent_asset_id="asset-1",
            instances=[_body(inv="inv-a"), _body(inv="inv-b")],
            # inv-a attested correctly; inv-b attests a different parent
            instance_parent_asset_ids={"inv-a": "asset-1", "inv-b": "asset-OTHER"},
        )


def test_cohesion_omitted_map_is_caller_contract() -> None:
    """No parent map = caller's contract (the pure layer cannot infer parents)."""
    # succeeds without enforcement — cohesion is the caller's responsibility
    draft = compose_draft_analysis(
        parent_asset_id="asset-1",
        instances=[_body(inv="inv-a")],
    )
    assert draft.parent_asset_id == "asset-1"
