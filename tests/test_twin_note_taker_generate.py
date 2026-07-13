"""Recursive twin note-taker generation core — contract tests.

Pins the hard-to-vary honesty invariants for ask #4's keystone substrate. The
module is pure except ONE injected ``TwinProposer``; tests inject a deterministic
recording fake — no network, no dispatch.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest  # noqa: E402

from substrate.research_artifact.render import render_html  # noqa: E402
from substrate.research_artifact.schema import ResearchArtifactBody  # noqa: E402
from substrate.twin_note_taker.generate import (  # noqa: E402
    MAX_CONTENT_CHARS,
    TWIN_AUTHORITY,
    AssetContent,
    ProposedInsight,
    ProposedQuestion,
    TwinGenerationError,
    TwinProposal,
    generate_twin,
)

CONTENT = (
    "This chapter argues that retrieval-augmented generation reduces hallucination "
    "by grounding claims in cited evidence, but the open question is whether the "
    "grounding survives distribution shift in the source corpus."
)


def _asset(**overrides: str) -> AssetContent:
    base: dict[str, str] = {
        "asset_id": "asset-1",
        "title": "RAG and Hallucination",
        "content_text": CONTENT,
        "content_class": "book",
    }
    base.update(overrides)
    return AssetContent(**base)  # type: ignore[arg-type]


class _RecordingProposer:
    """A deterministic fake TwinProposer that records invocations."""

    def __init__(
        self,
        insights: tuple[ProposedInsight, ...] = (
            ProposedInsight(text="RAG grounds claims in cited evidence.", source_asset_id=""),
        ),
        questions: tuple[ProposedQuestion, ...] = (
            ProposedQuestion(text="Does grounding survive distribution shift?"),
        ),
        synthesis: str = "The chapter examines RAG's effect on hallucination.",
        model_id: str = "",
    ):
        self._insights = insights
        self._questions = questions
        self._synthesis = synthesis
        self._model_id = model_id
        self.calls = 0

    def __call__(self, asset: AssetContent, *, model_id: str) -> TwinProposal:
        self.calls += 1
        self.last_asset = asset
        return TwinProposal(
            insights=self._insights,
            questions=self._questions,
            synthesis_excerpt=self._synthesis,
            model_id=self._model_id or model_id,
        )


# --- fail-closed validation ---


def test_empty_asset_id_rejected() -> None:
    with pytest.raises(TwinGenerationError, match="asset_id"):
        generate_twin(_asset(asset_id="  "), caller=_RecordingProposer(), model_id="m")


def test_empty_model_id_rejected() -> None:
    with pytest.raises(TwinGenerationError, match="model_id"):
        generate_twin(_asset(), caller=_RecordingProposer(), model_id="  ")


def test_short_content_rejected_no_twin_from_nothing() -> None:
    with pytest.raises(TwinGenerationError, match="too short"):
        generate_twin(
            _asset(content_text="tiny"),
            caller=_RecordingProposer(),
            model_id="m",
        )


def test_oversized_content_rejected() -> None:
    with pytest.raises(TwinGenerationError, match="ceiling"):
        generate_twin(
            _asset(content_text="x" * (MAX_CONTENT_CHARS + 1)),
            caller=_RecordingProposer(),
            model_id="m",
        )


# --- authority gate: no ack -> withheld, zero dispatch ---


def test_no_operator_ack_withholds_and_never_dispatches() -> None:
    caller = _RecordingProposer()
    result = generate_twin(_asset(), caller=caller, model_id="m", operator_ack=False)

    assert result.withheld is True
    assert result.operator_ack is False
    assert caller.calls == 0  # the only dispatch seam; never hit
    assert result.body.synthesis_withheld is True
    assert result.body.insights == []
    assert result.body.open_questions == []


# --- acked generation ---


def test_acked_generation_produces_advisory_twin() -> None:
    caller = _RecordingProposer()
    result = generate_twin(_asset(), caller=caller, model_id="m", operator_ack=True)

    assert result.withheld is False
    assert result.operator_ack is True
    assert caller.calls == 1
    assert result.authority == TWIN_AUTHORITY  # advisory, not assertive
    assert len(result.body.insights) == 1
    assert len(result.body.open_questions) == 1
    assert result.body.synthesis_withheld is False
    assert result.body.synthesis_excerpt == "The chapter examines RAG's effect on hallucination."


def test_empty_proposal_withheld_honestly() -> None:
    caller = _RecordingProposer(insights=(), questions=(), synthesis="   ", model_id="m")
    result = generate_twin(_asset(), caller=caller, model_id="m", operator_ack=True)

    assert caller.calls == 1  # dispatched (acked) but proposed nothing
    assert result.withheld is True  # honest: never invents insights
    assert result.body.insights == []
    assert result.body.synthesis_withheld is True


def test_caller_model_id_passthrough() -> None:
    caller = _RecordingProposer(model_id="actually-used")
    result = generate_twin(_asset(), caller=caller, model_id="requested", operator_ack=True)

    assert result.model_id == "actually-used"


# --- provenance: real, never fabricated ---


def test_insight_source_attributed_to_source_asset() -> None:
    caller = _RecordingProposer(
        insights=(ProposedInsight(text="A real claim.", source_asset_id=""),)
    )
    result = generate_twin(
        _asset(asset_id="book-42"), caller=caller, model_id="m", operator_ack=True
    )

    assert result.body.insights[0].source_document_id == "book-42"


def test_matching_explicit_source_is_accepted() -> None:
    caller = _RecordingProposer(
        insights=(ProposedInsight(text="A real claim.", source_asset_id="book-42"),)
    )
    result = generate_twin(
        _asset(asset_id="book-42"), caller=caller, model_id="m", operator_ack=True
    )

    assert result.body.insights[0].source_document_id == "book-42"


def test_mismatched_explicit_source_is_rejected() -> None:
    caller = _RecordingProposer(
        insights=(ProposedInsight(text="A real claim.", source_asset_id="other-asset"),)
    )

    with pytest.raises(TwinGenerationError, match="source_asset_id"):
        generate_twin(
            _asset(asset_id="book-42"),
            caller=caller,
            model_id="m",
            operator_ack=True,
        )


def test_twin_traces_to_source_asset() -> None:
    result = generate_twin(
        _asset(asset_id="book-42"), caller=_RecordingProposer(), model_id="m", operator_ack=True
    )

    assert result.body.source_event_ids == ["book-42"]
    assert result.twin_investigation_id == "twin-book-42"


def test_no_fabricated_insights_when_withheld() -> None:
    result = generate_twin(_asset(), caller=_RecordingProposer(), model_id="m", operator_ack=False)

    assert result.body.insights == []
    assert result.body.open_questions == []
    assert result.body.synthesis_withheld is True


# --- content-addressed dedup ---


def test_duplicate_insight_text_deduped() -> None:
    caller = _RecordingProposer(
        insights=(
            ProposedInsight(text="same claim", source_asset_id=""),
            ProposedInsight(text="same claim", source_asset_id=""),
            ProposedInsight(text="unique claim", source_asset_id=""),
        )
    )
    result = generate_twin(_asset(), caller=caller, model_id="m", operator_ack=True)

    texts = [i.text for i in result.body.insights]
    assert texts.count("same claim") == 1
    assert "unique claim" in texts
    assert len(result.body.insights) == 2


def test_empty_insight_text_dropped() -> None:
    caller = _RecordingProposer(
        insights=(
            ProposedInsight(text="   ", source_asset_id=""),
            ProposedInsight(text="real", source_asset_id=""),
        )
    )
    result = generate_twin(_asset(), caller=caller, model_id="m", operator_ack=True)

    assert [i.text for i in result.body.insights] == ["real"]


# --- idempotency ---


def test_idempotent_for_same_input_and_caller() -> None:
    asset = _asset()
    caller = _RecordingProposer()
    one = generate_twin(asset, caller=caller, model_id="m", operator_ack=True)
    two = generate_twin(asset, caller=caller, model_id="m", operator_ack=True)

    assert one.proposal_hash == two.proposal_hash
    assert one.body.content_hash() == two.body.content_hash()


# --- output is the canonical model + HTML-native ---


def test_output_is_canonical_research_artifact_body() -> None:
    result = generate_twin(_asset(), caller=_RecordingProposer(), model_id="m", operator_ack=True)

    assert isinstance(result.body, ResearchArtifactBody)
    assert result.body.schema_version == 1


def test_twin_renders_html_native_and_escapes() -> None:
    malicious = "<script>alert(1)</script>"
    caller = _RecordingProposer(
        insights=(ProposedInsight(text=malicious, source_asset_id=""),),
        synthesis=malicious,
    )
    result = generate_twin(_asset(), caller=caller, model_id="m", operator_ack=True)

    html_out = render_html(result.body)
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out
