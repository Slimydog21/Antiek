"""Contract tests for bounded advisory-twin retrieval."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import FrozenInstanceError
from typing import Any

import pytest
from nacl.signing import SigningKey

from substrate.twin_note_taker.generate import (
    AUTHORITY_VERIFY_KEY_ENV,
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
from substrate.twin_note_taker.search import (
    MAX_QUERY_CHARS,
    MAX_QUERY_TERMS,
    MAX_SEARCH_LIMIT,
    TwinIndex,
    TwinSearchError,
    TwinSearchHit,
    TwinSearchRecord,
    search_twins,
)

_SIGNING_KEY = SigningKey.generate()


@pytest.fixture(autouse=True)
def _configured_verify_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        AUTHORITY_VERIFY_KEY_ENV,
        base64.b64encode(bytes(_SIGNING_KEY.verify_key)).decode("ascii"),
    )


def _receipt_payload(claims: dict[str, Any]) -> bytes:
    payload = dict(claims)
    payload["source_event_ids"] = list(payload["source_event_ids"])
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _document(
    asset_id: str,
    *,
    insights: tuple[str, ...] = ("transformers improve retrieval",),
    questions: tuple[str, ...] = ("How does retrieval change?",),
    model_id: str = "model-1",
) -> TwinDocument:
    asset = AssetContent(
        asset_id=asset_id,
        title=f"Asset {asset_id}",
        content_text=(
            "This source contains enough exact text to support signed advisory twin generation."
        ),
        content_class="research",
        source_event_ids=(f"evt-{asset_id}",),
    )
    proposal = TwinProposal(
        tuple(ProposedInsight(text, asset_id) for text in insights),
        tuple(ProposedQuestion(text) for text in questions),
        "A bounded advisory summary.",
    )
    claims: dict[str, Any] = {
        "receipt_id": f"receipt-{asset_id}-{model_id}",
        "account_id": "account-1",
        "asset_id": asset_id,
        "model_id": model_id,
        "budget_authority_id": f"hold-{asset_id}",
        "source_content_hash": hashlib.sha256(asset.content_text.encode()).hexdigest(),
        "source_asset_hash": source_asset_receipt_hash(asset),
        "source_event_ids": asset.source_event_ids,
        "proposal_payload_hash": proposal_receipt_hash(asset, proposal),
        "expires_at_unix": 4_000_000_000,
    }
    receipt = TwinGenerationReceipt(
        **claims,
        signature=base64.b64encode(
            _SIGNING_KEY.sign(_receipt_payload(claims)).signature
        ).decode("ascii"),
    )
    return generate_twin(
        asset,
        model_id=model_id,
        authenticated_account_id="account-1",
        proposal=proposal,
        receipt=receipt,
    )


def test_empty_query_and_empty_index_return_immutable_empty() -> None:
    index = TwinIndex.build([])
    assert search_twins(index, "anything") == ()
    populated = TwinIndex.build([_document("asset-1")])
    assert search_twins(populated, "") == ()
    assert search_twins(populated, "   !!!") == ()


def test_limit_zero_or_negative_returns_empty() -> None:
    index = TwinIndex.build([_document("asset-1")])
    assert search_twins(index, "transformers", limit=0) == ()
    assert search_twins(index, "transformers", limit=-1) == ()


def test_only_matching_records_are_returned() -> None:
    index = TwinIndex.build(
        [
            _document("asset-1", insights=("transformers are powerful",), questions=()),
            _document("asset-2", insights=(), questions=("What is the weather?",)),
        ]
    )
    hits = search_twins(index, "transformers")
    assert len(hits) == 1
    assert hits[0].record.asset_id == "asset-1"
    assert search_twins(index, "unmatched") == ()


def test_hit_explains_term_frequency_and_score() -> None:
    index = TwinIndex.build(
        [_document("asset-1", insights=("attention attention transformers",), questions=())]
    )
    hit = search_twins(index, "attention")[0]
    assert hit.matched_terms == ("attention",)
    assert hit.term_frequency["attention"] == 2
    assert hit.score > 0


def test_repeated_query_terms_do_not_amplify_score() -> None:
    index = TwinIndex.build([_document("asset-1", insights=("cat cat",), questions=())])
    once = search_twins(index, "cat")[0]
    repeated = search_twins(index, "cat cat cat cat")[0]
    assert repeated.score == once.score
    assert repeated.matched_terms == once.matched_terms


def test_rare_term_outweighs_common_term() -> None:
    index = TwinIndex.build(
        [
            _document("asset-1", insights=("rare common",), questions=()),
            _document("asset-2", insights=("common",), questions=()),
            _document("asset-3", insights=("common",), questions=()),
            _document("asset-4", insights=("common",), questions=()),
        ]
    )
    assert search_twins(index, "rare common")[0].record.asset_id == "asset-1"


def test_equal_scores_use_stable_record_id_tiebreak() -> None:
    first = _document("asset-a", insights=("term term",), questions=())
    second = _document("asset-b", insights=("term term",), questions=())
    hits = search_twins(TwinIndex.build([second, first]), "term")
    assert [hit.record.record_id for hit in hits] == sorted(
        hit.record.record_id for hit in hits
    )


def test_limit_caps_results() -> None:
    documents = [
        _document(f"asset-{index}", insights=("term",), questions=())
        for index in range(5)
    ]
    assert len(search_twins(TwinIndex.build(documents), "term", limit=3)) == 3


def test_kind_filter_restricts_without_promoting_authority() -> None:
    index = TwinIndex.build(
        [_document("asset-1", insights=("shared term",), questions=("shared term?",))]
    )
    hits = search_twins(index, "shared term", kind_filter="question")
    assert len(hits) == 1
    assert hits[0].record.kind == "question"
    assert hits[0].record.authority == TWIN_AUTHORITY
    assert search_twins(index, "shared", kind_filter="stale-kind") == ()


def test_unicode_terms_are_searchable() -> None:
    index = TwinIndex.build(
        [
            _document(
                "asset-unicode",
                insights=("mañana التقنية 研究",),
                questions=(),
            )
        ]
    )
    assert search_twins(index, "MAÑANA")
    assert search_twins(index, "التقنية")
    assert search_twins(index, "研究")


def test_nfkc_equivalent_text_matches() -> None:
    index = TwinIndex.build(
        [_document("asset-1", insights=("Ｆｕｌｌｗｉｄｔｈ",), questions=())]
    )
    assert search_twins(index, "fullwidth")


def test_receipt_evidence_is_carried_but_never_called_graph_provenance() -> None:
    document = _document("asset-1", model_id="model-a")
    record = TwinIndex.build([document]).records[0]
    assert record.receipt_id == document.receipt_id
    assert record.budget_authority_id == document.budget_authority_id
    assert record.source_content_hash == document.source_content_hash
    assert record.proposal_hash == document.proposal_hash
    assert record.model_id == "model-a"
    assert not hasattr(record, "provenance")


def test_withheld_twin_cannot_enter_index() -> None:
    asset = AssetContent(
        asset_id="asset-empty",
        title="Empty twin",
        content_text="This source has enough content but no completed signed proposal.",
        source_event_ids=("evt-empty",),
    )
    withheld = generate_twin(
        asset,
        model_id="model-1",
        authenticated_account_id="account-1",
    )
    assert withheld.withheld is True
    with pytest.raises(TwinSearchError, match="withheld"):
        TwinIndex.build([withheld])


def test_document_and_record_public_constructors_are_closed() -> None:
    with pytest.raises(TwinGenerationError, match="generate_twin"):
        TwinDocument()
    with pytest.raises(TwinSearchError, match="TwinIndex.build"):
        TwinSearchRecord()
    with pytest.raises(TwinSearchError, match="TwinIndex.build"):
        TwinIndex()


def test_duplicate_materialized_twin_is_rejected() -> None:
    document = _document("asset-1")
    with pytest.raises(TwinSearchError, match="duplicate"):
        TwinIndex.build([document, document])


def test_index_and_hit_explanations_are_deeply_immutable() -> None:
    index = TwinIndex.build([_document("asset-1")])
    with pytest.raises(FrozenInstanceError):
        index.records = ()  # type: ignore[misc]
    with pytest.raises(TypeError):
        index._by_id["forged"] = index.records[0]  # type: ignore[index]
    hit = search_twins(index, "transformers")[0]
    with pytest.raises(TypeError):
        hit.term_frequency["transformers"] = 999  # type: ignore[index]


def test_search_is_deterministic_and_returns_tuple() -> None:
    index = TwinIndex.build([_document("asset-1")])
    first = search_twins(index, "transformers retrieval")
    second = search_twins(index, "transformers retrieval")
    assert isinstance(first, tuple)
    assert first == second
    assert isinstance(first[0], TwinSearchHit)


@pytest.mark.parametrize(
    ("query", "limit", "message"),
    [
        ("x" * (MAX_QUERY_CHARS + 1), 10, "query exceeds"),
        ("term", MAX_SEARCH_LIMIT + 1, "limit exceeds"),
        ("term", True, "exact integer"),
    ],
)
def test_query_and_limit_bounds_fail_closed(query: str, limit: int, message: str) -> None:
    index = TwinIndex.build([_document("asset-1")])
    with pytest.raises(TwinSearchError, match=message):
        search_twins(index, query, limit=limit)


def test_distinct_query_term_ceiling_fails_closed() -> None:
    query = " ".join(f"t{index}" for index in range(MAX_QUERY_TERMS + 1))
    index = TwinIndex.build([_document("asset-1")])
    with pytest.raises(TwinSearchError, match="too many"):
        search_twins(index, query)


def test_exact_container_and_string_types_are_required() -> None:
    document = _document("asset-1")
    with pytest.raises(TwinSearchError, match="exact list or tuple"):
        TwinIndex.build(iter([document]))  # type: ignore[arg-type]
    index = TwinIndex.build([document])
    with pytest.raises(TwinSearchError, match="exact string"):
        search_twins(index, 42)  # type: ignore[arg-type]
