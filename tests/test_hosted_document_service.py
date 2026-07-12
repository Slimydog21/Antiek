from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from services.hosted_documents import HostAuthorization, ingest_hosted_document
from substrate.marketplace_host import InMemoryHostStore


def _body() -> bytes:
    return " ".join(f"research-word-{i}" for i in range(80)).encode()


def test_ingest_server_mints_owner_bound_identity_and_emits_once():
    store = InMemoryHostStore()
    events: list[tuple[str, str]] = []

    def emit(investigation_id, document_id, extracted, size_bytes, source_uri):
        events.append((investigation_id, document_id))
        assert extracted.viewable is True
        assert size_bytes == len(_body())
        assert source_uri is None
        return "evt-hosted-1"

    kwargs = dict(
        owner_id="owner-a",
        raw=_body(),
        source_format="text",
        store=store,
        authorization=HostAuthorization("private_upload"),
        emit_document_loaded=emit,
        investigation_id="inv-reading",
        title="Research notes",
    )
    first = ingest_hosted_document(**kwargs)
    second = ingest_hosted_document(**kwargs)
    other_owner = ingest_hosted_document(**{**kwargs, "owner_id": "owner-b"})

    assert first.state == "ready"
    assert first.document_id == second.document_id
    assert second.already_hosted is True
    assert second.document_loaded_event_id == "evt-hosted-1"
    assert other_owner.document_id != first.document_id
    assert len(events) == 2


def test_concurrent_reingest_emits_once_for_same_owner_and_source():
    store = InMemoryHostStore()
    emitted: list[str] = []

    def emit(investigation_id, document_id, extracted, size_bytes, source_uri):
        emitted.append(document_id)
        return "evt-concurrent"

    def ingest():
        return ingest_hosted_document(
            owner_id="owner",
            raw=_body(),
            source_format="text",
            store=store,
            authorization=HostAuthorization("private_upload"),
            emit_document_loaded=emit,
            investigation_id="inv",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: ingest(), range(16)))

    assert len({result.document_id for result in results}) == 1
    assert emitted == [results[0].document_id]
    assert sum(not result.already_hosted for result in results) == 1


def test_non_viewable_source_persists_receipt_without_event_or_fake_body():
    store = InMemoryHostStore()

    def forbidden_emit(*args):
        raise AssertionError("non-viewable content must not emit document.loaded")

    result = ingest_hosted_document(
        owner_id="owner",
        raw=b"tiny",
        source_format="text",
        store=store,
        authorization=HostAuthorization("private_upload"),
        emit_document_loaded=forbidden_emit,
        investigation_id="inv",
    )
    assert result.state == "non_viewable"
    assert result.non_viewable_reason == "low_word_count"
    assert result.body_text == ""
    assert result.document_loaded_event_id is None


def test_purchased_content_requires_entitlement_proof():
    with pytest.raises(ValueError, match="requires entitlement_id"):
        ingest_hosted_document(
            owner_id="owner",
            raw=_body(),
            source_format="text",
            store=InMemoryHostStore(),
            authorization=HostAuthorization("purchased"),
            emit_document_loaded=lambda *args: "evt",
            investigation_id="inv",
        )


def test_entitlement_proof_cannot_be_attached_to_private_upload():
    with pytest.raises(ValueError, match="only valid for purchased"):
        HostAuthorization("private_upload", entitlement_id="receipt").validate()
