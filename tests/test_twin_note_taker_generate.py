"""Recursive twin note-taker generation core — contract tests.

Pins the hard-to-vary honesty invariants for ask #4's keystone substrate. The
module injects only the proposer; authorization is an Ed25519 receipt verified
against server configuration. Tests use deterministic fakes and no dispatch.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from dataclasses import replace
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest  # noqa: E402
from nacl.signing import SigningKey  # noqa: E402

from substrate.research_artifact.render import render_html  # noqa: E402
from substrate.research_artifact.schema import ResearchArtifactBody  # noqa: E402
from substrate.twin_note_taker.generate import (  # noqa: E402
    AUTHORITY_VERIFY_KEY_ENV,
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


def _asset(**overrides: Any) -> AssetContent:
    base: dict[str, Any] = {
        "asset_id": "asset-1",
        "title": "RAG and Hallucination",
        "content_text": CONTENT,
        "content_class": "book",
        "source_event_ids": ("evt-source-1",),
    }
    base.update(overrides)
    return AssetContent(**base)


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

    def __call__(
        self,
        asset: AssetContent,
        *,
        authorization: TwinAuthorization,
    ) -> TwinProposal:
        self.calls += 1
        self.last_asset = asset
        self.last_authorization = authorization
        return TwinProposal(
            insights=self._insights,
            questions=self._questions,
            synthesis_excerpt=self._synthesis,
        )


_AUTH_SIGNING_KEY = SigningKey.generate()


@pytest.fixture(autouse=True)
def _configured_authority_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        AUTHORITY_VERIFY_KEY_ENV,
        base64.b64encode(bytes(_AUTH_SIGNING_KEY.verify_key)).decode("ascii"),
    )


def _authorization_payload(
    *,
    authorization_id: str,
    account_id: str,
    asset_id: str,
    model_id: str,
    budget_authority_id: str,
    source_content_hash: str,
    source_event_ids: tuple[str, ...],
    expires_at_unix: int,
) -> bytes:
    return json.dumps(
        {
            "account_id": account_id,
            "asset_id": asset_id,
            "authorization_id": authorization_id,
            "budget_authority_id": budget_authority_id,
            "expires_at_unix": expires_at_unix,
            "model_id": model_id,
            "source_content_hash": source_content_hash,
            "source_event_ids": list(source_event_ids),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _authorization(
    *,
    asset_id: str = "asset-1",
    model_id: str = "m",
    source_content_hash: str | None = None,
    source_event_ids: tuple[str, ...] = ("evt-source-1",),
    expires_at_unix: int = 4_000_000_000,
    signing_key: SigningKey = _AUTH_SIGNING_KEY,
) -> TwinAuthorization:
    claims = {
        "authorization_id": "auth-1",
        "account_id": "account-1",
        "asset_id": asset_id,
        "model_id": model_id,
        "budget_authority_id": "hold-1",
        "source_content_hash": source_content_hash
        or hashlib.sha256(CONTENT.encode("utf-8")).hexdigest(),
        "source_event_ids": source_event_ids,
        "expires_at_unix": expires_at_unix,
    }
    signature = signing_key.sign(_authorization_payload(**claims)).signature
    return TwinAuthorization(
        **claims,
        signature=base64.b64encode(signature).decode("ascii"),
    )


def _generate(
    asset: AssetContent,
    *,
    caller: _RecordingProposer | None = None,
    model_id: str = "m",
) -> TwinDocument:
    return generate_twin(
        asset,
        caller=caller or _RecordingProposer(),
        model_id=model_id,
        authorization=_authorization(
            asset_id=asset.asset_id,
            model_id=model_id,
            source_content_hash=hashlib.sha256(asset.content_text.encode("utf-8")).hexdigest(),
            source_event_ids=asset.source_event_ids,
        ),
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


def test_surrounding_whitespace_cannot_bypass_raw_input_ceiling() -> None:
    caller = _RecordingProposer()
    with pytest.raises(TwinGenerationError, match="ceiling"):
        generate_twin(
            _asset(content_text=(" " * MAX_CONTENT_CHARS) + CONTENT),
            caller=caller,
            model_id="m",
        )
    assert caller.calls == 0


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


def test_forged_authorization_rejected_without_dispatch() -> None:
    caller = _RecordingProposer()
    forged = _authorization(signing_key=SigningKey.generate())

    with pytest.raises(TwinGenerationError, match="signature is invalid"):
        generate_twin(_asset(), caller=caller, model_id="m", authorization=forged)

    assert caller.calls == 0


@pytest.mark.parametrize("field", ["account_id", "budget_authority_id"])
def test_signed_account_and_budget_claims_cannot_be_tampered(field: str) -> None:
    caller = _RecordingProposer()
    authorization = replace(_authorization(), **{field: "attacker-controlled"})

    with pytest.raises(TwinGenerationError, match="signature is invalid"):
        generate_twin(_asset(), caller=caller, model_id="m", authorization=authorization)

    assert caller.calls == 0


@pytest.mark.parametrize(
    ("authorization", "message"),
    [
        (_authorization(asset_id="other"), "different asset"),
        (_authorization(model_id="other"), "different model"),
        (_authorization(source_content_hash="0" * 64), "different source revision"),
        (
            _authorization(source_event_ids=("evt-unrelated",)),
            "different source events",
        ),
    ],
)
def test_authorization_binding_rejected_before_verification(
    authorization: TwinAuthorization, message: str
) -> None:
    caller = _RecordingProposer()

    with pytest.raises(TwinGenerationError, match=message):
        generate_twin(
            _asset(),
            caller=caller,
            model_id="m",
            authorization=authorization,
        )

    assert caller.calls == 0


def test_missing_server_verify_key_rejected_without_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caller = _RecordingProposer()
    monkeypatch.delenv(AUTHORITY_VERIFY_KEY_ENV)
    with pytest.raises(TwinGenerationError, match="not configured"):
        generate_twin(_asset(), caller=caller, model_id="m", authorization=_authorization())
    assert caller.calls == 0


def test_expired_authorization_rejected_without_dispatch() -> None:
    caller = _RecordingProposer()
    with pytest.raises(TwinGenerationError, match="expired"):
        generate_twin(
            _asset(),
            caller=caller,
            model_id="m",
            authorization=_authorization(expires_at_unix=1),
        )
    assert caller.calls == 0


# --- authorized generation ---


def test_authorized_generation_produces_advisory_twin() -> None:
    caller = _RecordingProposer()
    result = _generate(_asset(), caller=caller)

    assert result.withheld is False
    assert result.authorization_id == "auth-1"
    assert result.budget_authority_id == "hold-1"
    assert caller.calls == 1
    assert caller.last_authorization.authorization_id == "auth-1"
    assert result.authority == TWIN_AUTHORITY
    assert result.body.insights == []  # ungrounded proposals are not graph findings
    assert result.proposed_insights == ("RAG grounds claims in cited evidence.",)
    assert result.proposed_questions == ("Does grounding survive distribution shift?",)
    assert result.body.open_questions == []  # proposals never enter graph collections
    assert result.body.synthesis_withheld is False
    assert result.body.synthesis_excerpt == (
        "Advisory model summary: The chapter examines RAG's effect on hallucination."
    )
    assert TWIN_AUTHORITY in result.body.agent_notes[0]
    assert "Proposed question:" in result.body.agent_notes[-1]


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

    assert result.body.source_event_ids == ["evt-source-1"]
    assert result.proposed_insights == ("A real claim.",)
    assert "Source asset: book-42" in result.body.agent_notes


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
    result = _generate(_asset(asset_id="book-42", source_event_ids=("evt-book-ingested",)))

    assert result.body.source_event_ids == ["evt-book-ingested"]
    assert result.twin_investigation_id == "twin-book-42"


@pytest.mark.parametrize("source_event_ids", [(), ("book-42",), ("evt-bad value",)])
def test_missing_or_malformed_source_event_is_rejected_without_dispatch(
    source_event_ids: tuple[str, ...],
) -> None:
    caller = _RecordingProposer()
    with pytest.raises(TwinGenerationError, match="source_event_ids"):
        generate_twin(
            _asset(source_event_ids=source_event_ids),
            caller=caller,
            model_id="m",
        )
    assert caller.calls == 0


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
    assert result.body.open_questions == []


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
    changed_raw_payload = _generate(_asset(content_text=f" {CONTENT} "), caller=caller)

    assert baseline.proposal_hash != changed_source.proposal_hash
    assert baseline.source_content_hash != changed_source.source_content_hash
    assert baseline.proposal_hash != changed_model.proposal_hash
    assert baseline.source_content_hash != changed_raw_payload.source_content_hash
    assert baseline.proposal_hash != changed_raw_payload.proposal_hash


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
    assert 'data-kind="question"' not in html_out
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
        def __call__(
            self,
            asset: AssetContent,
            *,
            authorization: TwinAuthorization,
        ):
            return {"insights": []}

    with pytest.raises(TwinGenerationError, match="TwinProposal"):
        generate_twin(
            _asset(),
            caller=_MalformedProposer(),  # type: ignore[arg-type]
            model_id="m",
            authorization=_authorization(),
        )
