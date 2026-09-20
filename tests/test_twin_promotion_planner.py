"""Authority, identity, bounds, and promote-once tests for twin promotion plans."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import FrozenInstanceError

import pytest
from nacl.signing import SigningKey

import substrate.twin_note_taker.promotion_planner as planner_module
from substrate.graph.insight_question import insight_node_id, question_node_id
from substrate.twin_note_taker.generate import (
    AUTHORITY_VERIFY_KEY_ENV,
    TWIN_AUTHORITY,
    AssetContent,
    ProposedInsight,
    ProposedQuestion,
    TwinDocument,
    TwinGenerationReceipt,
    TwinProposal,
    generate_twin,
    proposal_receipt_hash,
    source_asset_receipt_hash,
)
from substrate.twin_note_taker.promotion_planner import (
    DuplicateObservation,
    PromotableFinding,
    PromotionSource,
    TwinPromotionError,
    TwinPromotionPlan,
    plan_twin_promotion,
    predicted_node_id,
)

_SIGNING_KEY = SigningKey.generate()
_CONTENT = (
    "A sufficiently long source explains how signed advisory twin notes can seed "
    "questions without silently becoming canonical graph truth."
)


@pytest.fixture(autouse=True)
def _verify_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        AUTHORITY_VERIFY_KEY_ENV,
        base64.b64encode(bytes(_SIGNING_KEY.verify_key)).decode("ascii"),
    )


def _receipt_payload(claims: dict[str, object]) -> bytes:
    value = dict(claims)
    source_event_ids = value["source_event_ids"]
    assert isinstance(source_event_ids, tuple)
    value["source_event_ids"] = list(source_event_ids)
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _document(
    asset_id: str,
    *,
    insights: tuple[str, ...] = ("Signed twin insight",),
    questions: tuple[str, ...] = ("What evidence would falsify it?",),
    model_id: str = "model-1",
    account_id: str = "account-1",
) -> TwinDocument:
    asset = AssetContent(
        asset_id=asset_id,
        title=f"Source {asset_id}",
        content_text=f"{_CONTENT} {asset_id}",
        content_class="research",
        source_event_ids=(f"evt-{asset_id}",),
    )
    proposal = TwinProposal(
        insights=tuple(ProposedInsight(text, "") for text in insights),
        questions=tuple(ProposedQuestion(text) for text in questions),
        synthesis_excerpt="A bounded advisory synthesis.",
    )
    claims: dict[str, object] = {
        "receipt_id": f"receipt-{asset_id}",
        "account_id": account_id,
        "asset_id": asset_id,
        "model_id": model_id,
        "budget_authority_id": f"hold-{asset_id}",
        "source_content_hash": hashlib.sha256(asset.content_text.encode()).hexdigest(),
        "source_asset_hash": source_asset_receipt_hash(asset),
        "source_event_ids": asset.source_event_ids,
        "proposal_payload_hash": proposal_receipt_hash(asset, proposal),
        "expires_at_unix": 4_000_000_000,
    }
    signature = _SIGNING_KEY.sign(_receipt_payload(claims)).signature
    receipt = TwinGenerationReceipt(
        **claims,  # type: ignore[arg-type]
        signature=base64.b64encode(signature).decode("ascii"),
    )
    return generate_twin(
        asset,
        model_id=model_id,
        authenticated_account_id=account_id,
        proposal=proposal,
        receipt=receipt,
    )


def test_plan_accepts_only_exact_collection_of_exact_sealed_documents() -> None:
    document = _document("asset-1")
    assert plan_twin_promotion([document]).document_count == 1
    assert plan_twin_promotion((document,)).document_count == 1
    with pytest.raises(TwinPromotionError, match="list or tuple"):
        plan_twin_promotion(iter((document,)))  # type: ignore[arg-type]
    with pytest.raises(TwinPromotionError, match="exact TwinDocument"):
        plan_twin_promotion([object()])  # type: ignore[list-item]


def test_raw_findings_and_caller_provenance_are_not_api_inputs() -> None:
    with pytest.raises(TypeError):
        plan_twin_promotion(  # type: ignore[call-arg]
            asset_id="forged", insights=[], open_questions=[]
        )


def test_signed_claims_are_derived_from_document() -> None:
    document = _document("asset-claims", model_id="model-audit")
    finding = plan_twin_promotion([document]).canonical_insights[0]
    assert finding.source.asset_id == document.asset_id
    assert finding.source.account_id == document.account_id
    assert finding.source.twin_investigation_id == document.twin_investigation_id
    assert finding.source.authority == TWIN_AUTHORITY
    assert finding.source.model_id == "model-audit"
    assert finding.source.receipt_id == document.receipt_id
    assert finding.source.budget_authority_id == document.budget_authority_id
    assert finding.source.source_content_hash == document.source_content_hash
    assert finding.source.proposal_hash == document.proposal_hash


def test_output_constructors_are_closed() -> None:
    for cls in (PromotionSource, PromotableFinding, DuplicateObservation, TwinPromotionPlan):
        with pytest.raises(TwinPromotionError):
            cls()


def test_execution_contract_and_node_ids_match_default_writers() -> None:
    document = _document(
        "asset-id",
        insights=("  Mixed   CASE insight  ",),
        questions=("Same question?",),
    )
    plan = plan_twin_promotion([document])
    assert plan.authority == "advisory"
    assert plan.identity_scope == "account-1"
    assert plan.owner_user_id == "account-1"
    assert plan.semantic_dedup is False
    insight = plan.canonical_insights[0]
    question = plan.canonical_questions[0]
    assert insight.node_id == insight_node_id(insight.text, identity_scope="account-1")
    assert question.node_id == question_node_id(question.text, identity_scope="account-1")
    assert (
        predicted_node_id("insight", insight.text, identity_scope="account-1")
        == insight.node_id
    )
    assert (
        predicted_node_id("question", question.text, identity_scope="account-1")
        == question.node_id
    )


def test_cross_document_duplicates_are_observations_not_promotions() -> None:
    first = _document("asset-first", insights=("Shared   finding",), questions=())
    second = _document("asset-second", insights=(" shared finding ",), questions=())
    plan = plan_twin_promotion([first, second])
    assert plan.total_promotable == 1
    assert len(plan.canonical_insights) == 1
    assert plan.duplicates_observed == 1
    duplicate = plan.duplicate_observations[0]
    canonical = plan.canonical_insights[0]
    assert duplicate.node_id == canonical.node_id
    assert duplicate.duplicate_of_node_id == canonical.node_id
    assert duplicate.source.asset_id == "asset-second"
    assert duplicate.canonical_source_asset_id == "asset-first"
    assert all(type(item) is PromotableFinding for item in plan.canonical_insights)


def test_same_text_across_kinds_remains_two_canonical_nodes() -> None:
    document = _document(
        "asset-kinds", insights=("Same text",), questions=("Same text",)
    )
    plan = plan_twin_promotion([document])
    assert plan.total_promotable == 2
    assert plan.canonical_insights[0].node_id != plan.canonical_questions[0].node_id
    assert plan.duplicate_observations == ()


def test_empty_batch_is_an_honest_immutable_plan() -> None:
    plan = plan_twin_promotion([])
    assert plan.is_empty
    assert plan.document_count == 0
    assert plan.identity_scope is None
    assert plan.owner_user_id is None
    assert plan.canonical_insights == ()
    assert plan.canonical_questions == ()
    assert plan.duplicate_observations == ()
    with pytest.raises(FrozenInstanceError):
        plan.authority = "canonical"  # type: ignore[misc]


def test_withheld_document_is_rejected() -> None:
    asset = AssetContent(
        asset_id="asset-withheld",
        title="Withheld",
        content_text=_CONTENT,
        content_class="research",
        source_event_ids=("evt-withheld",),
    )
    withheld = generate_twin(
        asset, model_id="model-1", authenticated_account_id="account-1"
    )
    assert withheld.withheld
    with pytest.raises(TwinPromotionError, match="withheld"):
        plan_twin_promotion([withheld])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("authority", "canonical", "advisory"),
        ("receipt_id", None, "exact strings"),
        ("source_content_hash", "bad", "sha256"),
        ("proposed_insights", ["forged"], "exact tuple"),
        ("proposed_insights", ("forged canonical text",), "no longer matches"),
        ("proposed_questions", (" padded ",), "proposal item is invalid"),
    ],
)
def test_tampered_materialized_claims_fail_closed(
    field: str, value: object, message: str
) -> None:
    document = _document("asset-tamper")
    object.__setattr__(document, field, value)
    with pytest.raises(TwinPromotionError, match=message):
        plan_twin_promotion([document])


def test_document_count_and_batch_bounds_apply_before_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document("asset-bounds")
    with pytest.raises(TwinPromotionError, match="document count"):
        plan_twin_promotion([document] * (planner_module.MAX_PROMOTION_DOCUMENTS + 1))

    monkeypatch.setattr(planner_module, "MAX_PROMOTION_FINDINGS", 1)
    with pytest.raises(TwinPromotionError, match="finding count"):
        plan_twin_promotion([document])

    monkeypatch.setattr(planner_module, "MAX_PROMOTION_FINDINGS", 10)
    monkeypatch.setattr(planner_module, "MAX_PROMOTION_TOTAL_CHARS", 1)
    with pytest.raises(TwinPromotionError, match="batch promotion"):
        plan_twin_promotion([document])


def test_mixed_account_batch_is_rejected_before_cross_account_dedup() -> None:
    first = _document("asset-private-a", account_id="account-a")
    second = _document("asset-private-b", account_id="account-b")
    with pytest.raises(TwinPromotionError, match="exactly one account"):
        plan_twin_promotion([first, second])
    assert predicted_node_id(
        "insight", "same", identity_scope="account-a"
    ) != predicted_node_id("insight", "same", identity_scope="account-b")


@pytest.mark.parametrize(
    ("kind", "text"),
    [
        ("bogus", "text"),
        ("insight", ""),
        ("question", "   "),
        ("insight", 1),
    ],
)
def test_predicted_node_id_is_type_closed_and_nonblank(
    kind: object, text: object
) -> None:
    with pytest.raises(TwinPromotionError):
        predicted_node_id(kind, text, identity_scope="account-1")  # type: ignore[arg-type]


def test_plan_order_and_first_canonical_source_are_deterministic() -> None:
    a = _document("asset-a", insights=("One", "Shared"), questions=("Q one",))
    b = _document("asset-b", insights=("shared", "Two"), questions=("Q two",))
    first = plan_twin_promotion([a, b])
    second = plan_twin_promotion([a, b])
    assert first == second
    assert tuple(item.text for item in first.canonical_insights) == ("One", "Shared", "Two")
    assert first.duplicate_observations[0].canonical_source_asset_id == "asset-a"
