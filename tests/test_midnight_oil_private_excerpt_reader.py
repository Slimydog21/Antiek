from __future__ import annotations

import hashlib
from dataclasses import fields

import pytest

from acquisition.substack.midnight_oil import StoredAuthorizedSubstackExcerptReader
from substrate.engagement_spine.store import InMemoryEngagementStore
from substrate.midnight_oil.publication_authority_v2 import (
    ProviderProcessingCapabilityReferenceV2,
    SubstackOwnerPrivateExcerptAuthorityV2,
    substack_authority_row_v2,
)
from substrate.midnight_oil.publication_sources import ReviewedPublicationSource
from substrate.midnight_oil.substack_authorization import (
    SubstackUseAuthorizationV2,
    inspect_active_stored_substack_excerpt,
    revoke_substack_authorization,
)
from substrate.midnight_oil.substack_review import (
    claim_substack_excerpt_review,
    confirm_substack_excerpt_review,
)

_KEY = b"private-reader-purpose-key-000000"
_KEY_ID = "private-reader-purpose-key"
_UNIT = "cunit_" + "a" * 24
_PREVIEW = "b" * 64
_EXTERNAL_ID = "example.substack.com/p/private-reader"
_REF_ID = "sref_" + hashlib.sha256(
    f"substack:substack:{_EXTERNAL_ID}".encode()
).hexdigest()[:16]


def _fixture(
    *,
    store: InMemoryEngagementStore | None = None,
    suffix: str = "0001",
    external_id: str = _EXTERNAL_ID,
    text: str = "Exact multibyte research — مرحبا",
) -> tuple[
    InMemoryEngagementStore, SubstackOwnerPrivateExcerptAuthorityV2, bytes
]:
    store = store or InMemoryEngagementStore()
    ref_id = "sref_" + hashlib.sha256(
        f"substack:substack:{external_id}".encode()
    ).hexdigest()[:16]
    draft = claim_substack_excerpt_review(
        store,
        owner_id="alice",
        idempotency_key=f"private-reader-claim-{suffix}",
        collective_unit_id=_UNIT,
        collective_preview_sha256=_PREVIEW,
        ref_id=ref_id,
        canonical_url=f"https://{external_id}",
        external_id=external_id,
        selection_text=text,
        source_representation_sha256="c" * 64,
        source_representation_bytes=10_000,
        source_byte_start=100,
        lifetime_ms=60_000,
        now_ms=1_000,
        nonce=suffix[-1] * 32,
    )
    overlay = confirm_substack_excerpt_review(
        store,
        owner_id="alice",
        review_id=draft.review_id,
        expected_review_preview_sha256=draft.review_preview_sha256,
        idempotency_key=f"private-reader-confirm-{suffix}",
        key_id=_KEY_ID,
        signing_key=_KEY,
        verification_keys={_KEY_ID: _KEY},
        now_ms=2_000,
    )
    authorization, receipt = inspect_active_stored_substack_excerpt(
        store,
        owner_id="alice",
        authorization_id=overlay.authorization_id,
        expected_authorization_sha256=overlay.authorization_sha256,
        receipt_id=overlay.receipt_id,
        expected_receipt_sha256=overlay.receipt_sha256,
        verification_keys={_KEY_ID: _KEY},
        now_ms=2_001,
    )
    assert isinstance(authorization, SubstackUseAuthorizationV2)
    source = ReviewedPublicationSource(
        ref_id=ref_id,
        kind="substack",
        canonical_url=f"https://{external_id}",
        external_id=external_id,
        acquisition_mode="substack_bounded_excerpt",
        rights_use="operator_authorized_excerpt",
        max_excerpt_bytes=8_192,
    )
    row = substack_authority_row_v2(
        source=source,
        authorization=authorization,
        receipt=receipt,
        overlay=overlay,
    )
    raw = row.authority.model_dump(mode="json")
    raw["provider_processing_authority"] = ProviderProcessingCapabilityReferenceV2(
        capability_sha256="d" * 64
    ).model_dump(mode="json")
    return (
        store,
        SubstackOwnerPrivateExcerptAuthorityV2.model_validate(raw),
        text.encode("utf-8"),
    )


def test_reader_returns_only_exact_local_utf8_bytes() -> None:
    store, authority, expected = _fixture()
    result = StoredAuthorizedSubstackExcerptReader(
        store=store, verification_keys={_KEY_ID: _KEY}
    ).read(
        owner_id="alice", authority=authority, now_ms=2_002, required_until_ms=3_000
    )
    assert result.exact_bytes == expected
    assert result.receipt.excerpt_bytes == len(expected)
    assert result.receipt.excerpt_sha256 == hashlib.sha256(expected).hexdigest()
    assert result.source_acquisition_network_egress is False
    assert result.confers_execution_authority is False


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("owner_scope_sha256", "0" * 64),
        ("collective_preview_sha256", "1" * 64),
        ("overlay_sha256", "2" * 64),
        ("authorization_sha256", "3" * 64),
        ("receipt_sha256", "4" * 64),
        ("source_representation_sha256", "5" * 64),
        ("excerpt_sha256", "6" * 64),
    ),
)
def test_reader_rejects_every_detached_authority_identity(field: str, value: object) -> None:
    store, authority, _expected = _fixture()
    raw = authority.model_dump(mode="json")
    raw[field] = value
    changed = SubstackOwnerPrivateExcerptAuthorityV2.model_construct(**raw)
    with pytest.raises(ValueError):
        StoredAuthorizedSubstackExcerptReader(
            store=store, verification_keys={_KEY_ID: _KEY}
        ).read(
            owner_id="alice",
            authority=changed,
            now_ms=2_002,
            required_until_ms=3_000,
        )


def test_reader_revalidates_literal_fields_after_model_copy() -> None:
    store, authority, _expected = _fixture()
    bypass = authority.model_copy(update={"confers_execution_authority": True})
    with pytest.raises(ValueError, match="unavailable"):
        StoredAuthorizedSubstackExcerptReader(
            store=store, verification_keys={_KEY_ID: _KEY}
        ).read(
            owner_id="alice",
            authority=bypass,
            now_ms=2_002,
            required_until_ms=3_000,
        )


def test_reader_rejects_wrong_owner_and_required_horizon() -> None:
    store, authority, _expected = _fixture()
    reader = StoredAuthorizedSubstackExcerptReader(
        store=store, verification_keys={_KEY_ID: _KEY}
    )
    with pytest.raises(ValueError, match="unavailable"):
        reader.read(
            owner_id="bob", authority=authority, now_ms=2_002, required_until_ms=3_000
        )
    with pytest.raises(ValueError, match="unavailable"):
        reader.read(
            owner_id="alice",
            authority=authority,
            now_ms=2_002,
            required_until_ms=authority.expires_at_ms,
        )


def test_reader_rechecks_revocation_before_returning_bytes() -> None:
    store, authority, _expected = _fixture()
    revoke_substack_authorization(
        store,
        owner_id="alice",
        authorization_id=authority.authorization_id,
        expected_authorization_sha256=authority.authorization_sha256,
        clock_ms=lambda: 2_003,
    )
    with pytest.raises(ValueError, match="unavailable"):
        StoredAuthorizedSubstackExcerptReader(
            store=store, verification_keys={_KEY_ID: _KEY}
        ).read(
            owner_id="alice",
            authority=authority,
            now_ms=2_004,
            required_until_ms=3_000,
        )


def test_reader_has_no_network_or_generic_acquisition_surface() -> None:
    reader_fields = {field.name for field in fields(StoredAuthorizedSubstackExcerptReader)}
    assert reader_fields == {"store", "verification_keys"}
    assert not hasattr(StoredAuthorizedSubstackExcerptReader, "fetch")
    assert not hasattr(StoredAuthorizedSubstackExcerptReader, "acquire")


def test_lazy_substack_package_preserves_declared_legacy_symbol_discovery() -> None:
    import acquisition.substack as substack

    assert set(substack.__all__).issubset(dir(substack))


def test_malformed_durable_receipt_error_does_not_echo_private_text() -> None:
    store, authority, _expected = _fixture()
    canary = "UNIQUE_DURABLE_CANARY_48c2"
    logical_id = "suexcerpt_" + authority.receipt_id.removeprefix("suer_")
    original = store.get_owned_document(logical_id, "alice")
    assert original is not None
    receipt = dict(original["receipt"])
    receipt["text"] = f"before {canary}\x00 after"
    store.mutate_owned_document(
        logical_id,
        "alice",
        lambda _current: {**original, "receipt": receipt},
    )
    with pytest.raises(ValueError) as raised:
        StoredAuthorizedSubstackExcerptReader(
            store=store, verification_keys={_KEY_ID: _KEY}
        ).read(
            owner_id="alice",
            authority=authority,
            now_ms=2_002,
            required_until_ms=3_000,
        )
    assert canary not in str(raised.value)
    assert canary not in repr(raised.value)
