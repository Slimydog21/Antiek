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


def test_explicit_curated_excerpt_policy_is_recorded_and_viewable():
    store = InMemoryHostStore()
    result = ingest_hosted_document(
        owner_id="owner",
        raw=b"A short, rights-cleared public-domain catalog excerpt.",
        source_format="text",
        store=store,
        authorization=HostAuthorization("public_domain"),
        emit_document_loaded=lambda *args: "evt-excerpt",
        investigation_id="catalog",
        minimum_viewable_words=1,
    )
    assert result.state == "ready"
    stored = store.get_document(result.document_id)
    assert stored is not None
    assert stored["minimum_viewable_words"] == 1


@pytest.mark.parametrize(
    ("authorization", "source_uri", "message"),
    [
        (HostAuthorization("public_domain"), "private://original", "different license"),
        (HostAuthorization("private_upload"), "other://source", "different source"),
    ],
)
def test_identical_bytes_cannot_relabel_existing_authority(authorization, source_uri, message):
    store = InMemoryHostStore()
    ingest_hosted_document(
        owner_id="owner",
        raw=_body(),
        source_format="text",
        store=store,
        authorization=HostAuthorization("private_upload"),
        emit_document_loaded=lambda *args: "evt-original",
        investigation_id="inv",
        source_uri="private://original",
    )
    with pytest.raises(ValueError, match=message):
        ingest_hosted_document(
            owner_id="owner",
            raw=_body(),
            source_format="text",
            store=store,
            authorization=authorization,
            emit_document_loaded=lambda *args: "evt-forbidden",
            investigation_id="inv",
            source_uri=source_uri,
        )


def test_store_failure_prevents_event_emission():
    class FailingStore(InMemoryHostStore):
        def put_document(self, document_id, doc):
            raise OSError("disk unavailable")

    emitted: list[str] = []
    with pytest.raises(OSError, match="disk unavailable"):
        ingest_hosted_document(
            owner_id="owner",
            raw=_body(),
            source_format="text",
            store=FailingStore(),
            authorization=HostAuthorization("private_upload"),
            emit_document_loaded=lambda *args: emitted.append("event") or "evt",
            investigation_id="inv",
        )
    assert emitted == []


def test_pending_retry_uses_idempotent_emitter_after_ready_write_failure():
    class FailReadyWriteOnceStore(InMemoryHostStore):
        failed = False

        def put_document(self, document_id, doc):
            if doc.get("state") == "ready" and not self.failed:
                self.failed = True
                raise OSError("ready write interrupted")
            super().put_document(document_id, doc)

    store = FailReadyWriteOnceStore()
    receipts: dict[tuple[str, str, str], str] = {}
    physical_appends: list[str] = []

    def idempotent_emit(investigation_id, document_id, extracted, size_bytes, source_uri):
        key = (investigation_id, document_id, extracted.canonical_content_hash)
        if key not in receipts:
            receipts[key] = "evt-once"
            physical_appends.append("evt-once")
        return receipts[key]

    kwargs = dict(
        owner_id="owner",
        raw=_body(),
        source_format="text",
        store=store,
        authorization=HostAuthorization("private_upload"),
        emit_document_loaded=idempotent_emit,
        investigation_id="inv",
    )
    with pytest.raises(OSError, match="ready write interrupted"):
        ingest_hosted_document(**kwargs)
    pending_id = next(iter(store._docs))
    assert store.get_document(pending_id)["state"] == "pending"

    recovered = ingest_hosted_document(**kwargs)
    assert recovered.state == "ready"
    assert recovered.document_loaded_event_id == "evt-once"
    assert physical_appends == ["evt-once"]
