"""Contract tests for signed, spend-free twin materialization."""

from __future__ import annotations

import base64
import hashlib
import inspect
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
    MAX_IDENTIFIER_CHARS,
    MAX_INSIGHTS,
    MAX_PROPOSAL_ITEM_CHARS,
    MAX_QUESTIONS,
    MAX_SOURCE_EVENTS,
    MAX_SYNTHESIS_CHARS,
    MAX_TITLE_CHARS,
    TWIN_AUTHORITY,
    AssetContent,
    ProposedInsight,
    ProposedQuestion,
    TwinDocument,
    TwinGenerationError,
    TwinGenerationReceipt,
    TwinProposal,
    generate_twin,
    proposal_receipt_hash,
    source_asset_receipt_hash,
)

CONTENT = (
    "This chapter argues that retrieval-augmented generation reduces hallucination "
    "by grounding claims in cited evidence, but the open question is whether the "
    "grounding survives distribution shift in the source corpus."
)
_SIGNING_KEY = SigningKey.generate()


@pytest.fixture(autouse=True)
def _configured_verify_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        AUTHORITY_VERIFY_KEY_ENV,
        base64.b64encode(bytes(_SIGNING_KEY.verify_key)).decode("ascii"),
    )


def _asset(**overrides: Any) -> AssetContent:
    values: dict[str, Any] = {
        "asset_id": "asset-1",
        "title": "RAG and Hallucination",
        "content_text": CONTENT,
        "content_class": "book",
        "source_event_ids": ("evt-source-1",),
    }
    values.update(overrides)
    return AssetContent(**values)


def _proposal(
    *,
    insights: tuple[ProposedInsight, ...] = (
        ProposedInsight("RAG grounds claims in cited evidence.", ""),
    ),
    questions: tuple[ProposedQuestion, ...] = (
        ProposedQuestion("Does grounding survive distribution shift?"),
    ),
    synthesis: str = "The chapter examines RAG's effect on hallucination.",
) -> TwinProposal:
    return TwinProposal(insights, questions, synthesis)


def _receipt_payload(claims: dict[str, Any]) -> bytes:
    serializable = dict(claims)
    serializable["source_event_ids"] = list(serializable["source_event_ids"])
    return json.dumps(serializable, sort_keys=True, separators=(",", ":")).encode()


def _receipt(
    asset: AssetContent,
    proposal: TwinProposal,
    *,
    account_id: str = "account-1",
    model_id: str = "m",
    receipt_id: str = "receipt-1",
    budget_authority_id: str = "hold-1",
    source_content_hash: str | None = None,
    source_asset_hash: str | None = None,
    source_event_ids: tuple[str, ...] | None = None,
    proposal_payload_hash: str | None = None,
    expires_at_unix: int = 4_000_000_000,
    signing_key: SigningKey = _SIGNING_KEY,
) -> TwinGenerationReceipt:
    claims: dict[str, Any] = {
        "receipt_id": receipt_id,
        "account_id": account_id,
        "asset_id": asset.asset_id,
        "model_id": model_id,
        "budget_authority_id": budget_authority_id,
        "source_content_hash": source_content_hash
        or hashlib.sha256(asset.content_text.encode()).hexdigest(),
        "source_asset_hash": source_asset_hash or source_asset_receipt_hash(asset),
        "source_event_ids": source_event_ids or asset.source_event_ids,
        "proposal_payload_hash": proposal_payload_hash or proposal_receipt_hash(asset, proposal),
        "expires_at_unix": expires_at_unix,
    }
    signature = signing_key.sign(_receipt_payload(claims)).signature
    return TwinGenerationReceipt(
        **claims,
        signature=base64.b64encode(signature).decode("ascii"),
    )


def _generate(
    asset: AssetContent,
    proposal: TwinProposal | None = None,
    *,
    account_id: str = "account-1",
    model_id: str = "m",
) -> TwinDocument:
    completed = proposal or _proposal()
    return generate_twin(
        asset,
        model_id=model_id,
        authenticated_account_id=account_id,
        proposal=completed,
        receipt=_receipt(asset, completed, account_id=account_id, model_id=model_id),
    )


def test_core_has_no_dispatch_seam() -> None:
    assert "caller" not in inspect.signature(generate_twin).parameters


@pytest.mark.parametrize(
    ("asset", "model_id", "account_id", "message"),
    [
        (_asset(asset_id="  "), "m", "account-1", "asset_id"),
        (_asset(), "  ", "account-1", "model_id"),
        (_asset(), "m", "  ", "authenticated_account_id"),
        (_asset(content_text="tiny"), "m", "account-1", "too short"),
        (_asset(content_text="x" * (MAX_CONTENT_CHARS + 1)), "m", "account-1", "ceiling"),
        (_asset(source_event_ids=()), "m", "account-1", "source_event_ids"),
        (_asset(source_event_ids=("book-42",)), "m", "account-1", "source_event_ids"),
    ],
)
def test_invalid_source_request_fails_closed(
    asset: AssetContent, model_id: str, account_id: str, message: str
) -> None:
    with pytest.raises(TwinGenerationError, match=message):
        generate_twin(
            asset,
            model_id=model_id,
            authenticated_account_id=account_id,
        )


def test_surrounding_whitespace_cannot_bypass_raw_input_ceiling() -> None:
    with pytest.raises(TwinGenerationError, match="ceiling"):
        generate_twin(
            _asset(content_text=(" " * MAX_CONTENT_CHARS) + CONTENT),
            model_id="m",
            authenticated_account_id="account-1",
        )


def test_without_completed_proposal_returns_honest_withheld_twin() -> None:
    result = generate_twin(_asset(), model_id="m", authenticated_account_id="account-1")
    assert result.withheld is True
    assert result.receipt_id is None
    assert result.account_id is None
    assert result.body.insights == []
    assert result.body.open_questions == []
    assert result.body.synthesis_withheld is True


@pytest.mark.parametrize("proposal_present", [True, False])
def test_proposal_and_receipt_must_arrive_together(proposal_present: bool) -> None:
    asset = _asset()
    proposal = _proposal()
    with pytest.raises(TwinGenerationError, match="provided together"):
        generate_twin(
            asset,
            model_id="m",
            authenticated_account_id="account-1",
            proposal=proposal if proposal_present else None,
            receipt=None if proposal_present else _receipt(asset, proposal),
        )


def test_valid_receipt_materializes_advisory_non_graph_twin() -> None:
    result = _generate(_asset())
    assert result.withheld is False
    assert result.receipt_id == "receipt-1"
    assert result.account_id == "account-1"
    assert result.budget_authority_id == "hold-1"
    assert result.model_id == "m"
    assert result.authority == TWIN_AUTHORITY
    assert result.proposed_insights == ("RAG grounds claims in cited evidence.",)
    assert result.proposed_questions == ("Does grounding survive distribution shift?",)
    assert result.body.insights == []
    assert result.body.open_questions == []
    assert TWIN_AUTHORITY in result.body.agent_notes[0]
    assert any(note.startswith("Proposed question:") for note in result.body.agent_notes)
    assert result.body.source_event_ids == []
    assert result.body.synthesis_excerpt is None
    assert result.body.synthesis_withheld is True
    assert any(note.startswith("Proposed synthesis:") for note in result.body.agent_notes)


def test_forged_signature_is_rejected() -> None:
    asset, proposal = _asset(), _proposal()
    forged = _receipt(asset, proposal, signing_key=SigningKey.generate())
    with pytest.raises(TwinGenerationError, match="signature is invalid"):
        generate_twin(
            asset,
            model_id="m",
            authenticated_account_id="account-1",
            proposal=proposal,
            receipt=forged,
        )


def test_signed_budget_claim_cannot_be_tampered() -> None:
    asset, proposal = _asset(), _proposal()
    tampered = replace(_receipt(asset, proposal), budget_authority_id="attacker-hold")
    with pytest.raises(TwinGenerationError, match="signature is invalid"):
        generate_twin(
            asset,
            model_id="m",
            authenticated_account_id="account-1",
            proposal=proposal,
            receipt=tampered,
        )


def test_receipt_is_bound_to_authenticated_account() -> None:
    asset, proposal = _asset(), _proposal()
    receipt = _receipt(asset, proposal, account_id="account-2")
    with pytest.raises(TwinGenerationError, match="different authenticated account"):
        generate_twin(
            asset,
            model_id="m",
            authenticated_account_id="account-1",
            proposal=proposal,
            receipt=receipt,
        )


@pytest.mark.parametrize(
    ("receipt", "message"),
    [
        (_receipt(_asset(asset_id="other"), _proposal()), "different asset"),
        (_receipt(_asset(), _proposal(), model_id="other"), "different model"),
        (
            _receipt(_asset(), _proposal(), source_content_hash="0" * 64),
            "different source revision",
        ),
        (
            _receipt(_asset(), _proposal(), source_asset_hash="0" * 64),
            "different source metadata",
        ),
        (
            _receipt(_asset(), _proposal(), source_event_ids=("evt-unrelated",)),
            "different source events",
        ),
        (
            _receipt(_asset(), _proposal(), proposal_payload_hash="0" * 64),
            "different proposal",
        ),
    ],
)
def test_receipt_binding_substitution_is_rejected(
    receipt: TwinGenerationReceipt, message: str
) -> None:
    with pytest.raises(TwinGenerationError, match=message):
        generate_twin(
            _asset(),
            model_id="m",
            authenticated_account_id="account-1",
            proposal=_proposal(),
            receipt=receipt,
        )


def test_missing_verify_key_and_expired_receipt_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset, proposal = _asset(), _proposal()
    monkeypatch.delenv(AUTHORITY_VERIFY_KEY_ENV)
    with pytest.raises(TwinGenerationError, match="not configured"):
        generate_twin(
            asset,
            model_id="m",
            authenticated_account_id="account-1",
            proposal=proposal,
            receipt=_receipt(asset, proposal),
        )
    monkeypatch.setenv(
        AUTHORITY_VERIFY_KEY_ENV,
        base64.b64encode(bytes(_SIGNING_KEY.verify_key)).decode(),
    )
    with pytest.raises(TwinGenerationError, match="expired"):
        generate_twin(
            asset,
            model_id="m",
            authenticated_account_id="account-1",
            proposal=proposal,
            receipt=_receipt(asset, proposal, expires_at_unix=1),
        )


def test_whitespace_only_proposal_is_withheld_after_normalization() -> None:
    proposal = _proposal(
        insights=(ProposedInsight("  ", ""),),
        questions=(ProposedQuestion("\n"),),
        synthesis="\t",
    )
    result = _generate(_asset(), proposal)
    assert result.withheld is True
    assert result.proposed_insights == ()
    assert result.proposed_questions == ()


def test_proposer_cannot_fabricate_another_source_asset() -> None:
    asset = _asset(asset_id="book-42")
    proposal = _proposal(insights=(ProposedInsight("Claim", "other-asset"),))
    with pytest.raises(TwinGenerationError, match="source_asset_id"):
        proposal_receipt_hash(asset, proposal)


def test_canonical_text_dedup_is_stable() -> None:
    proposal = _proposal(
        insights=(
            ProposedInsight("Same   Claim", ""),
            ProposedInsight(" same claim ", ""),
            ProposedInsight("Different", ""),
        )
    )
    result = _generate(_asset(), proposal)
    assert result.proposed_insights == ("Same   Claim", "Different")


def test_receipt_replay_is_pure_and_idempotent() -> None:
    asset, proposal = _asset(), _proposal()
    receipt = _receipt(asset, proposal)
    kwargs = {
        "model_id": "m",
        "authenticated_account_id": "account-1",
        "proposal": proposal,
        "receipt": receipt,
    }
    one = generate_twin(asset, **kwargs)  # type: ignore[arg-type]
    two = generate_twin(asset, **kwargs)  # type: ignore[arg-type]
    assert one == two
    assert one.proposal_hash == two.proposal_hash
    assert one.body.content_hash() == two.body.content_hash()


@pytest.mark.parametrize(
    "changed",
    [
        _asset(title="Attacker title"),
        _asset(content_class="attacker-class"),
    ],
)
def test_receipt_binds_all_output_affecting_source_metadata(changed: AssetContent) -> None:
    asset, proposal = _asset(), _proposal()
    receipt = _receipt(asset, proposal)
    with pytest.raises(TwinGenerationError, match="different source metadata"):
        generate_twin(
            changed,
            model_id="m",
            authenticated_account_id="account-1",
            proposal=proposal,
            receipt=receipt,
        )


def test_returned_body_is_detached_from_signed_document_state() -> None:
    result = _generate(_asset())
    body = result.body
    body.source_event_ids.append("evt-forged")
    assert result.body.source_event_ids == []
    assert result.body.insights == []


def test_hashes_bind_exact_raw_source_and_model() -> None:
    baseline = _generate(_asset())
    changed_source = _generate(_asset(content_text=CONTENT + " Revision."))
    changed_whitespace = _generate(_asset(content_text=f" {CONTENT} "))
    changed_model = _generate(_asset(), model_id="other-model")
    assert baseline.source_content_hash != changed_source.source_content_hash
    assert baseline.proposal_hash != changed_source.proposal_hash
    assert baseline.proposal_hash != changed_whitespace.proposal_hash
    assert baseline.proposal_hash != changed_model.proposal_hash


def test_html_is_escaped_and_proposals_never_render_as_graph_nodes() -> None:
    malicious = "<script>alert(1)</script>"
    proposal = _proposal(
        insights=(ProposedInsight(malicious, ""),),
        questions=(ProposedQuestion(malicious),),
        synthesis=malicious,
    )
    result = _generate(_asset(), proposal)
    assert isinstance(result.body, ResearchArtifactBody)
    html_out = render_html(result.body)
    assert malicious not in html_out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out
    assert 'data-kind="insight"' not in html_out
    assert 'data-kind="question"' not in html_out
    assert TWIN_AUTHORITY in html_out


@pytest.mark.parametrize(
    "proposal",
    [
        _proposal(
            insights=tuple(
                ProposedInsight(f"insight {index}", "") for index in range(MAX_INSIGHTS + 1)
            )
        ),
        _proposal(
            questions=tuple(
                ProposedQuestion(f"question {index}") for index in range(MAX_QUESTIONS + 1)
            )
        ),
        _proposal(insights=(ProposedInsight("x" * (MAX_PROPOSAL_ITEM_CHARS + 1), ""),)),
        _proposal(insights=(ProposedInsight(" " * (MAX_PROPOSAL_ITEM_CHARS + 1), ""),)),
        _proposal(insights=(ProposedInsight("claim", " " * (MAX_IDENTIFIER_CHARS + 1)),)),
        _proposal(questions=(ProposedQuestion(" " * (MAX_PROPOSAL_ITEM_CHARS + 1)),)),
        _proposal(synthesis="x" * (MAX_SYNTHESIS_CHARS + 1)),
        _proposal(synthesis=" " * (MAX_SYNTHESIS_CHARS + 1)),
    ],
)
def test_untrusted_output_limits_fail_closed(proposal: TwinProposal) -> None:
    with pytest.raises(TwinGenerationError, match="exceeds"):
        proposal_receipt_hash(_asset(), proposal)


def test_aggregate_output_limit_fails_closed() -> None:
    proposal = _proposal(
        insights=tuple(
            ProposedInsight(("x" * (MAX_PROPOSAL_ITEM_CHARS - 10)) + f"{index:010d}", "")
            for index in range(21)
        ),
        questions=(),
        synthesis="",
    )
    with pytest.raises(TwinGenerationError, match="aggregate"):
        proposal_receipt_hash(_asset(), proposal)


@pytest.mark.parametrize(
    ("asset", "model_id", "account_id", "message"),
    [
        (_asset(asset_id="x" * (MAX_IDENTIFIER_CHARS + 1)), "m", "account-1", "asset_id"),
        (_asset(asset_id=" " * (MAX_IDENTIFIER_CHARS + 1)), "m", "account-1", "asset_id"),
        (_asset(title="x" * (MAX_TITLE_CHARS + 1)), "m", "account-1", "title"),
        (
            _asset(content_class=" " * (MAX_IDENTIFIER_CHARS + 1)),
            "m",
            "account-1",
            "content_class",
        ),
        (
            _asset(
                source_event_ids=tuple(f"evt-{index}" for index in range(MAX_SOURCE_EVENTS + 1))
            ),
            "m",
            "account-1",
            "count ceiling",
        ),
        (_asset(), "m" * (MAX_IDENTIFIER_CHARS + 1), "account-1", "model_id"),
        (_asset(), " " * (MAX_IDENTIFIER_CHARS + 1), "account-1", "model_id"),
        (_asset(), "m", "a" * (MAX_IDENTIFIER_CHARS + 1), "authenticated_account_id"),
        (_asset(), "m", " " * (MAX_IDENTIFIER_CHARS + 1), "authenticated_account_id"),
    ],
)
def test_untrusted_metadata_limits_fail_closed(
    asset: AssetContent, model_id: str, account_id: str, message: str
) -> None:
    with pytest.raises(TwinGenerationError, match=message):
        generate_twin(asset, model_id=model_id, authenticated_account_id=account_id)


@pytest.mark.parametrize(
    "asset",
    [
        _asset(content_text="x" * (MAX_CONTENT_CHARS + 1)),
        _asset(title="x" * (MAX_TITLE_CHARS + 1)),
        _asset(asset_id=" " * (MAX_IDENTIFIER_CHARS + 1)),
        _asset(source_event_ids=("evt-" + ("x" * (MAX_IDENTIFIER_CHARS + 1)),)),
        _asset(source_event_ids=tuple(f"evt-{index}" for index in range(MAX_SOURCE_EVENTS + 1))),
    ],
)
def test_public_receipt_hash_helpers_enforce_source_bounds(asset: AssetContent) -> None:
    with pytest.raises(TwinGenerationError, match="ceiling"):
        source_asset_receipt_hash(asset)
    with pytest.raises(TwinGenerationError, match="ceiling"):
        proposal_receipt_hash(asset, _proposal())


def test_package_exports_public_contract() -> None:
    from substrate.twin_note_taker import generate_twin as public_generate_twin

    assert public_generate_twin is generate_twin


def test_receipt_raw_claims_are_bounded_before_parsing() -> None:
    asset, proposal = _asset(), _proposal()
    valid = _receipt(asset, proposal)
    hostile = [
        replace(valid, receipt_id=" " * (MAX_IDENTIFIER_CHARS + 1)),
        replace(valid, source_content_hash=" " * (MAX_IDENTIFIER_CHARS + 1)),
        replace(valid, signature=" " * (MAX_IDENTIFIER_CHARS + 1)),
        replace(valid, source_event_ids=("evt-" + ("x" * (MAX_IDENTIFIER_CHARS + 1)),)),
        replace(valid, expires_at_unix=10**10_000),
    ]
    for receipt in hostile:
        with pytest.raises(TwinGenerationError):
            generate_twin(
                asset,
                model_id="m",
                authenticated_account_id="account-1",
                proposal=proposal,
                receipt=receipt,
            )


def test_exact_builtin_types_prevent_overridable_string_bypasses() -> None:
    class _LyingString(str):
        def __len__(self) -> int:
            return 1

        def strip(self, chars: str | None = None) -> str:
            return self

    with pytest.raises(TwinGenerationError, match="exact strings"):
        generate_twin(
            _asset(content_text=_LyingString("x" * (MAX_CONTENT_CHARS + 1))),
            model_id="m",
            authenticated_account_id="account-1",
        )
    with pytest.raises(TwinGenerationError, match="exact strings"):
        proposal_receipt_hash(
            _asset(), _proposal(insights=(ProposedInsight(_LyingString("claim"), ""),))
        )
