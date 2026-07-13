"""Recursive twin note-taker generation core — contract tests.

Pins the hard-to-vary honesty invariants for ask #4's keystone substrate. The
module has injected proposer and authorization-verifier boundaries; tests use
deterministic recording fakes — no network and no real dispatch.
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
    MAX_INSIGHTS,
    MAX_PROPOSAL_ITEM_CHARS,
    MAX_QUESTIONS,
    MAX_SYNTHESIS_CHARS,
    TWIN_AUTHORITY,
    AssetContent,
    ProposedInsight,
    ProposedQuestion,
    TwinAuthorization,
    TwinDocument,
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
    ):
        self._insights = insights
        self._questions = questions
        self._synthesis = synthesis
        self.calls = 0

    def __call__(self, asset: AssetContent, *, model_id: str) -> TwinProposal:
        self.calls += 1
        self.last_asset = asset
        return TwinProposal(
            insights=self._insights,
            questions=self._questions,
            synthesis_excerpt=self._synthesis,
        )


class _Verifier:
    def __init__(self, *, accepted: bool = True):
        self.accepted = accepted
        self.calls = 0

    def __call__(self, authorization: TwinAuthorization) -> bool:
        self.calls += 1
        self.last_authorization = authorization
        return self.accepted


def _authorization(*, asset_id: str = "asset-1", model_id: str = "m") -> TwinAuthorization:
    return TwinAuthorization(
        authorization_id="auth-1",
        account_id="account-1",
        asset_id=asset_id,
        model_id=model_id,
        budget_authority_id="hold-1",
    )


def _generate(
    asset: AssetContent,
    *,
    caller: _RecordingProposer | None = None,
    model_id: str = "m",
    verifier: _Verifier | None = None,
) -> TwinDocument:
    return generate_twin(
        asset,
        caller=caller or _RecordingProposer(),
        model_id=model_id,
        authorization=_authorization(asset_id=asset.asset_id, model_id=model_id),
        verify_authorization=verifier or _Verifier(),
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


# --- authority gate: no verified receipt -> withheld, zero dispatch ---


def test_no_authorization_withholds_and_never_dispatches() -> None:
    caller = _RecordingProposer()
    result = generate_twin(_asset(), caller=caller, model_id="m")

    assert result.withheld is True
    assert result.authorization_id is None
    assert result.budget_authority_id is None
    assert caller.calls == 0
    assert result.body.synthesis_withheld is True
    assert result.body.insights == []
    assert result.body.open_questions == []


def test_unverified_authorization_rejected_without_dispatch() -> None:
    caller = _RecordingProposer()
    verifier = _Verifier(accepted=False)

    with pytest.raises(TwinGenerationError, match="verification failed"):
        _generate(_asset(), caller=caller, verifier=verifier)

    assert verifier.calls == 1
    assert caller.calls == 0


@pytest.mark.parametrize(
    ("authorization", "message"),
    [
        (_authorization(asset_id="other"), "different asset"),
        (_authorization(model_id="other"), "different model"),
    ],
)
def test_authorization_binding_rejected_before_verification(
    authorization: TwinAuthorization, message: str
) -> None:
    caller = _RecordingProposer()
    verifier = _Verifier()

    with pytest.raises(TwinGenerationError, match=message):
        generate_twin(
            _asset(),
            caller=caller,
            model_id="m",
            authorization=authorization,
            verify_authorization=verifier,
        )

    assert verifier.calls == 0
    assert caller.calls == 0


def test_receipt_without_verifier_rejected_without_dispatch() -> None:
    caller = _RecordingProposer()
    with pytest.raises(TwinGenerationError, match="verifier"):
        generate_twin(_asset(), caller=caller, model_id="m", authorization=_authorization())
    assert caller.calls == 0


# --- authorized generation ---


def test_authorized_generation_produces_advisory_twin() -> None:
    caller = _RecordingProposer()
    verifier = _Verifier()
    result = _generate(_asset(), caller=caller, verifier=verifier)

    assert result.withheld is False
    assert result.authorization_id == "auth-1"
    assert result.budget_authority_id == "hold-1"
    assert verifier.calls == 1
    assert caller.calls == 1
    assert result.authority == TWIN_AUTHORITY
    assert result.body.insights == []  # ungrounded proposals are not graph findings
    assert result.proposed_insights == ("RAG grounds claims in cited evidence.",)
    assert len(result.body.open_questions) == 1
    assert result.body.synthesis_withheld is False
    assert result.body.synthesis_excerpt == (
        "Advisory model summary: The chapter examines RAG's effect on hallucination."
    )
    assert TWIN_AUTHORITY in result.body.agent_notes[0]


def test_empty_proposal_withheld_honestly() -> None:
    caller = _RecordingProposer(insights=(), questions=(), synthesis="   ")
    result = _generate(_asset(), caller=caller)

    assert caller.calls == 1
    assert result.withheld is True
    assert result.body.insights == []
    assert result.body.synthesis_withheld is True


def test_whitespace_only_items_are_withheld_after_normalization() -> None:
    caller = _RecordingProposer(
        insights=(ProposedInsight(text="   ", source_asset_id=""),),
        questions=(ProposedQuestion(text="\n\t"),),
        synthesis=" ",
    )
    result = _generate(_asset(), caller=caller)

    assert result.withheld is True
    assert result.proposed_insights == ()
    assert result.proposed_questions == ()


def test_model_identity_comes_from_verified_authorization() -> None:
    result = _generate(_asset(), model_id="requested-model")
    assert result.model_id == "requested-model"


# --- provenance: real, never fabricated ---


def test_insight_source_attributed_to_source_asset() -> None:
    caller = _RecordingProposer(
        insights=(ProposedInsight(text="A real claim.", source_asset_id=""),)
    )
    result = _generate(_asset(asset_id="book-42"), caller=caller)

    assert result.body.source_event_ids == ["book-42"]
    assert result.proposed_insights == ("A real claim.",)


def test_matching_explicit_source_is_accepted() -> None:
    caller = _RecordingProposer(
        insights=(ProposedInsight(text="A real claim.", source_asset_id="book-42"),)
    )
    result = _generate(_asset(asset_id="book-42"), caller=caller)

    assert result.proposed_insights == ("A real claim.",)


def test_mismatched_explicit_source_is_rejected() -> None:
    caller = _RecordingProposer(
        insights=(ProposedInsight(text="A real claim.", source_asset_id="other-asset"),)
    )

    with pytest.raises(TwinGenerationError, match="source_asset_id"):
        _generate(_asset(asset_id="book-42"), caller=caller)


def test_twin_traces_to_source_asset() -> None:
    result = _generate(_asset(asset_id="book-42"))

    assert result.body.source_event_ids == ["book-42"]
    assert result.twin_investigation_id == "twin-book-42"


def test_no_fabricated_insights_when_withheld() -> None:
    result = generate_twin(_asset(), caller=_RecordingProposer(), model_id="m")

    assert result.body.insights == []
    assert result.proposed_insights == ()
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
    result = _generate(_asset(), caller=caller)

    texts = list(result.proposed_insights)
    assert texts.count("same claim") == 1
    assert "unique claim" in texts
    assert len(result.proposed_insights) == 2


def test_empty_insight_text_dropped() -> None:
    caller = _RecordingProposer(
        insights=(
            ProposedInsight(text="   ", source_asset_id=""),
            ProposedInsight(text="real", source_asset_id=""),
        )
    )
    result = _generate(_asset(), caller=caller)

    assert result.proposed_insights == ("real",)


def test_case_and_whitespace_variants_dedup_by_canonical_text() -> None:
    caller = _RecordingProposer(
        insights=(
            ProposedInsight(text="Same   Claim", source_asset_id=""),
            ProposedInsight(text=" same claim ", source_asset_id=""),
        )
    )
    result = _generate(_asset(), caller=caller)
    assert result.proposed_insights == ("Same   Claim",)
    assert len(result.body.open_questions[0].node_id.rsplit("-", 1)[-1]) == 16


# --- idempotency ---


def test_idempotent_for_same_input_and_caller() -> None:
    asset = _asset()
    caller = _RecordingProposer()
    one = _generate(asset, caller=caller)
    two = _generate(asset, caller=caller)

    assert one.proposal_hash == two.proposal_hash
    assert one.body.content_hash() == two.body.content_hash()


def test_proposal_hash_binds_source_revision_and_model() -> None:
    caller = _RecordingProposer()
    baseline = _generate(_asset(), caller=caller)
    changed_source = _generate(
        _asset(content_text=CONTENT + " A material revision."), caller=caller
    )
    changed_model = _generate(_asset(), caller=caller, model_id="other-model")

    assert baseline.proposal_hash != changed_source.proposal_hash
    assert baseline.source_content_hash != changed_source.source_content_hash
    assert baseline.proposal_hash != changed_model.proposal_hash


# --- output is the canonical model + HTML-native ---


def test_output_is_canonical_research_artifact_body() -> None:
    result = _generate(_asset())

    assert isinstance(result.body, ResearchArtifactBody)
    assert result.body.schema_version == 1


def test_twin_renders_html_native_and_escapes() -> None:
    malicious = "<script>alert(1)</script>"
    caller = _RecordingProposer(
        insights=(ProposedInsight(text=malicious, source_asset_id=""),),
        synthesis=malicious,
    )
    result = _generate(_asset(), caller=caller)

    html_out = render_html(result.body)
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out
    assert 'data-kind="insight"' not in html_out
    assert "No insights in the graph yet." in html_out
    assert TWIN_AUTHORITY in html_out


@pytest.mark.parametrize(
    "caller",
    [
        _RecordingProposer(
            insights=tuple(
                ProposedInsight(text=f"insight {index}", source_asset_id="")
                for index in range(MAX_INSIGHTS + 1)
            )
        ),
        _RecordingProposer(
            questions=tuple(
                ProposedQuestion(text=f"question {index}") for index in range(MAX_QUESTIONS + 1)
            )
        ),
        _RecordingProposer(
            insights=(
                ProposedInsight(text="x" * (MAX_PROPOSAL_ITEM_CHARS + 1), source_asset_id=""),
            )
        ),
        _RecordingProposer(synthesis="x" * (MAX_SYNTHESIS_CHARS + 1)),
    ],
)
def test_untrusted_output_limits_fail_closed(caller: _RecordingProposer) -> None:
    with pytest.raises(TwinGenerationError, match="exceeds"):
        _generate(_asset(), caller=caller)


def test_aggregate_output_limit_fails_closed() -> None:
    caller = _RecordingProposer(
        insights=tuple(
            ProposedInsight(
                text=("x" * (MAX_PROPOSAL_ITEM_CHARS - 10)) + f"{index:010d}",
                source_asset_id="",
            )
            for index in range(21)
        ),
        questions=(),
        synthesis="",
    )

    with pytest.raises(TwinGenerationError, match="aggregate"):
        _generate(_asset(), caller=caller)


def test_malformed_proposer_result_fails_closed() -> None:
    class _MalformedProposer:
        def __call__(self, asset: AssetContent, *, model_id: str):
            return {"insights": []}

    with pytest.raises(TwinGenerationError, match="TwinProposal"):
        generate_twin(
            _asset(),
            caller=_MalformedProposer(),  # type: ignore[arg-type]
            model_id="m",
            authorization=_authorization(),
            verify_authorization=_Verifier(),
        )
