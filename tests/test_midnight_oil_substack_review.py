from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from substrate.engagement_spine.store import InMemoryEngagementStore
from substrate.midnight_oil.substack_authorization import (
    SubstackUseAuthorizationV2,
    require_active_stored_substack_authorization,
)
from substrate.midnight_oil.substack_review import (
    ConfirmedSubstackReviewOverlay,
    claim_substack_excerpt_review,
    confirm_substack_excerpt_review,
    list_confirmed_substack_reviews,
    review_draft_projection,
    substack_review_overlay_sha256,
)

_KEY = b"r" * 32
_EXTERNAL_ID = "antiek.substack.com/p/research-workstations"
_REF_ID = "sref_" + hashlib.sha256(f"substack:substack:{_EXTERNAL_ID}".encode()).hexdigest()[:16]
_UNIT_ID = "cunit_" + "a" * 24
_PREVIEW = "b" * 64


def _claim(
    store: InMemoryEngagementStore,
    *,
    owner_id: str = "alice",
    idempotency_key: str = "review-key-0001",
    text: str = 'A & B — "private research".',
    now_ms: int = 1_000,
    nonce: str = "1" * 32,
):
    return claim_substack_excerpt_review(
        store,
        owner_id=owner_id,
        idempotency_key=idempotency_key,
        collective_unit_id=_UNIT_ID,
        collective_preview_sha256=_PREVIEW,
        ref_id=_REF_ID,
        canonical_url=f"https://{_EXTERNAL_ID}",
        external_id=_EXTERNAL_ID,
        selection_text=text,
        source_representation_sha256="c" * 64,
        source_representation_bytes=10_000,
        source_byte_start=100,
        lifetime_ms=60_000,
        now_ms=now_ms,
        nonce=nonce,
    )


def test_review_claim_is_exact_replay_with_stable_server_identity_and_no_active_html() -> None:
    store = InMemoryEngagementStore()
    first = _claim(store)
    replay = _claim(store, now_ms=9_000, nonce="2" * 32)
    assert replay == first
    assert replay.issued_at_ms == 1_000
    assert replay.nonce == "1" * 32
    projection = review_draft_projection(first)
    assert projection["selection_text"] == first.selection_text
    assert "html" not in projection
    assert "signature" not in projection
    assert projection["publication_execution_enabled"] is False
    with pytest.raises(ValueError, match="idempotency key conflicts"):
        _claim(store, text="changed selection")


def test_confirmation_creates_v2_authority_receipt_and_review_only_overlay() -> None:
    store = InMemoryEngagementStore()
    draft = _claim(store)
    overlay = confirm_substack_excerpt_review(
        store,
        owner_id="alice",
        review_id=draft.review_id,
        expected_review_preview_sha256=draft.review_preview_sha256,
        idempotency_key="confirm-key-0001",
        key_id="substack-purpose-2026-07",
        signing_key=_KEY,
        verification_keys={"substack-purpose-2026-07": _KEY},
        now_ms=2_000,
    )
    assert overlay.publication_execution_enabled is False
    assert overlay.requires_manifest_v2 is True
    assert overlay.content_class == "personal_reading"
    assert list_confirmed_substack_reviews(
        store,
        owner_id="alice",
        collective_unit_id=_UNIT_ID,
        collective_preview_sha256=_PREVIEW,
    ) == (overlay,)
    authorization = require_active_stored_substack_authorization(
        store,
        owner_id="alice",
        authorization_id=overlay.authorization_id,
        expected_authorization_sha256=overlay.authorization_sha256,
        verification_keys={"substack-purpose-2026-07": _KEY},
        now_ms=2_001,
    )
    assert isinstance(authorization, SubstackUseAuthorizationV2)
    assert authorization.owner_affirms_lawful_access is True
    assert authorization.owner_affirms_provider_processing is True
    rotated_key = b"n" * 32
    replay = confirm_substack_excerpt_review(
        store,
        owner_id="alice",
        review_id=draft.review_id,
        expected_review_preview_sha256=draft.review_preview_sha256,
        idempotency_key="confirm-key-0001",
        key_id="substack-purpose-2026-08",
        signing_key=rotated_key,
        verification_keys={
            "substack-purpose-2026-07": _KEY,
            "substack-purpose-2026-08": rotated_key,
        },
        now_ms=draft.expires_at_ms,
    )
    assert replay == overlay


def test_list_reviews_reproves_index_key_row_hash_and_embedded_identity() -> None:
    store = InMemoryEngagementStore()
    draft = _claim(store)
    overlay = confirm_substack_excerpt_review(
        store,
        owner_id="alice",
        review_id=draft.review_id,
        expected_review_preview_sha256=draft.review_preview_sha256,
        idempotency_key="confirm-list-integrity-0001",
        key_id="substack-purpose-2026-07",
        signing_key=_KEY,
        verification_keys={"substack-purpose-2026-07": _KEY},
        now_ms=2_000,
    )
    original = store.get_owned_document(overlay.overlay_id, "alice")
    assert original is not None
    store.mutate_owned_document(
        overlay.overlay_id,
        "alice",
        lambda _current: {**original, "overlay_sha256": "0" * 64},
    )
    with pytest.raises(ValueError, match="binding conflicts"):
        list_confirmed_substack_reviews(
            store,
            owner_id="alice",
            collective_unit_id=_UNIT_ID,
            collective_preview_sha256=_PREVIEW,
        )

    forged_raw = overlay.model_dump(mode="json")
    forged_raw["excerpt_bytes"] = overlay.excerpt_bytes + 1
    forged_raw["source_byte_end"] = overlay.source_byte_end + 1
    forged_digest = substack_review_overlay_sha256(forged_raw)
    forged_raw.update(
        overlay_id="csubrev_" + forged_digest[:24],
        overlay_sha256=forged_digest,
    )
    forged = ConfirmedSubstackReviewOverlay.model_validate(forged_raw)
    store.mutate_owned_document(
        overlay.overlay_id,
        "alice",
        lambda _current: {
            **original,
            "overlay_sha256": forged.overlay_sha256,
            "overlay": forged.model_dump(mode="json"),
        },
    )
    with pytest.raises(ValueError, match="binding conflicts"):
        list_confirmed_substack_reviews(
            store,
            owner_id="alice",
            collective_unit_id=_UNIT_ID,
            collective_preview_sha256=_PREVIEW,
        )


@pytest.mark.parametrize(
    "fault_step",
    ["claim", "reservation", "authorization", "receipt", "overlay", "bind", "index", "settle"],
)
def test_confirmation_repairs_each_ambiguous_write_after_key_rotation(
    fault_step: str,
) -> None:
    store = InMemoryEngagementStore()
    draft = _claim(store)
    original_mutate = store.mutate_owned_document
    armed = True

    def faulting_mutate(logical_id: str, owner_id: str, mutation: Any) -> dict[str, Any]:
        nonlocal armed
        result = original_mutate(logical_id, owner_id, mutation)
        matches = (
            (
                fault_step == "claim"
                and logical_id.startswith("substack_review_confirm_")
                and result.get("state") == "claimed"
            )
            or (fault_step == "authorization" and logical_id.startswith("suauth_"))
            or (fault_step == "receipt" and logical_id.startswith("suexcerpt_"))
            or (fault_step == "overlay" and logical_id.startswith("csubrev_"))
            or (
                fault_step == "reservation"
                and logical_id.startswith("csubidx_")
                and bool(result.get("reservation_ids"))
                and not bool(result.get("overlay_ids"))
            )
            or (
                fault_step == "bind"
                and logical_id.startswith("substack_review_confirm_")
                and result.get("state") == "claimed"
                and isinstance(result.get("overlay_id"), str)
            )
            or (
                fault_step == "index"
                and logical_id.startswith("csubidx_")
                and bool(result.get("overlay_ids"))
                and not bool(result.get("reservation_ids"))
            )
            or (
                fault_step == "settle"
                and logical_id.startswith("substack_review_confirm_")
                and result.get("state") == "applied"
            )
        )
        if armed and matches:
            armed = False
            raise RuntimeError(f"crash after {fault_step}")
        return result

    store.mutate_owned_document = faulting_mutate  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match=f"crash after {fault_step}"):
        confirm_substack_excerpt_review(
            store,
            owner_id="alice",
            review_id=draft.review_id,
            expected_review_preview_sha256=draft.review_preview_sha256,
            idempotency_key="confirm-crash-key-0001",
            key_id="old-key",
            signing_key=_KEY,
            verification_keys={"old-key": _KEY},
            now_ms=2_000,
        )
    store.mutate_owned_document = original_mutate  # type: ignore[method-assign]
    new_key = b"n" * 32
    repaired = confirm_substack_excerpt_review(
        store,
        owner_id="alice",
        review_id=draft.review_id,
        expected_review_preview_sha256=draft.review_preview_sha256,
        idempotency_key="confirm-crash-key-0001",
        key_id="new-key",
        signing_key=new_key,
        verification_keys={"old-key": _KEY, "new-key": new_key},
        now_ms=draft.expires_at_ms,
    )
    assert repaired.review_id == draft.review_id
    assert repaired.publication_execution_enabled is False


def test_applied_replay_rejects_independently_hashed_cross_binding_drift() -> None:
    store = InMemoryEngagementStore()
    draft = _claim(store)
    overlay = confirm_substack_excerpt_review(
        store,
        owner_id="alice",
        review_id=draft.review_id,
        expected_review_preview_sha256=draft.review_preview_sha256,
        idempotency_key="confirm-integrity-key-0001",
        key_id="old-key",
        signing_key=_KEY,
        verification_keys={"old-key": _KEY},
        now_ms=2_000,
    )
    forged_raw = overlay.model_dump(mode="json")
    forged_raw["excerpt_bytes"] = overlay.excerpt_bytes + 1
    forged_raw["source_byte_end"] = overlay.source_byte_end + 1
    forged_digest = substack_review_overlay_sha256(forged_raw)
    forged_raw.update(
        overlay_id="csubrev_" + forged_digest[:24],
        overlay_sha256=forged_digest,
    )
    forged = ConfirmedSubstackReviewOverlay.model_validate(forged_raw)
    store.mutate_owned_document(
        forged.overlay_id,
        "alice",
        lambda current: {
            "document_type": "confirmed_substack_review_overlay",
            "overlay_sha256": forged.overlay_sha256,
            "overlay": forged.model_dump(mode="json"),
        },
    )
    confirmation_rows = store.list_owned_documents(
        "alice", logical_prefix="substack_review_confirm_", after_logical_id=None, limit=10
    )
    assert len(confirmation_rows) == 1
    confirmation_id, _ = confirmation_rows[0]
    store.mutate_owned_document(
        confirmation_id,
        "alice",
        lambda current: {**(current or {}), "overlay_id": forged.overlay_id},
    )
    with pytest.raises(ValueError, match="reconciliation"):
        confirm_substack_excerpt_review(
            store,
            owner_id="alice",
            review_id=draft.review_id,
            expected_review_preview_sha256=draft.review_preview_sha256,
            idempotency_key="confirm-integrity-key-0001",
            key_id="old-key",
            signing_key=_KEY,
            verification_keys={"old-key": _KEY},
            now_ms=2_100,
        )


def test_review_index_admits_only_one_of_two_concurrent_boundary_confirmations() -> None:
    store = InMemoryEngagementStore()

    def claim_and_confirm(index: int):
        draft = _claim(
            store,
            idempotency_key=f"review-capacity-{index:04d}",
            nonce=hashlib.sha256(f"nonce-{index}".encode()).hexdigest()[:32],
        )
        return (
            index,
            draft,
            confirm_substack_excerpt_review(
                store,
                owner_id="alice",
                review_id=draft.review_id,
                expected_review_preview_sha256=draft.review_preview_sha256,
                idempotency_key=f"confirm-capacity-{index:04d}",
                key_id="capacity-key",
                signing_key=_KEY,
                verification_keys={"capacity-key": _KEY},
                now_ms=2_000,
            ),
        )

    for index in range(63):
        claim_and_confirm(index)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(claim_and_confirm, index) for index in (63, 64)]
        outcomes: list[tuple[int, Any, Any]] = []
        errors: list[ValueError] = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except ValueError as exc:
                errors.append(exc)
    assert len(outcomes) == 1
    assert len(errors) == 1 and "limit is reached" in str(errors[0])
    overlays = list_confirmed_substack_reviews(
        store,
        owner_id="alice",
        collective_unit_id=_UNIT_ID,
        collective_preview_sha256=_PREVIEW,
    )
    assert len(overlays) == 64
    winning_index, winning_draft, winning_overlay = outcomes[0]
    assert (
        confirm_substack_excerpt_review(
            store,
            owner_id="alice",
            review_id=winning_draft.review_id,
            expected_review_preview_sha256=winning_draft.review_preview_sha256,
            idempotency_key=f"confirm-capacity-{winning_index:04d}",
            key_id="capacity-key",
            signing_key=_KEY,
            verification_keys={"capacity-key": _KEY},
            now_ms=winning_draft.expires_at_ms,
        )
        == winning_overlay
    )
    losing_index = ({63, 64} - {winning_index}).pop()
    losing_draft = _claim(
        store,
        idempotency_key=f"review-capacity-{losing_index:04d}",
        nonce=hashlib.sha256(f"nonce-{losing_index}".encode()).hexdigest()[:32],
    )
    with pytest.raises(ValueError, match="limit is reached"):
        confirm_substack_excerpt_review(
            store,
            owner_id="alice",
            review_id=losing_draft.review_id,
            expected_review_preview_sha256=losing_draft.review_preview_sha256,
            idempotency_key=f"confirm-capacity-{losing_index:04d}",
            key_id="capacity-key",
            signing_key=_KEY,
            verification_keys={"capacity-key": _KEY},
            now_ms=2_100,
        )
    for rejected_index in (65, 66, 67):
        rejected_draft = _claim(
            store,
            idempotency_key=f"review-capacity-{rejected_index:04d}",
            nonce=hashlib.sha256(f"nonce-{rejected_index}".encode()).hexdigest()[:32],
        )
        with pytest.raises(ValueError, match="limit is reached"):
            confirm_substack_excerpt_review(
                store,
                owner_id="alice",
                review_id=rejected_draft.review_id,
                expected_review_preview_sha256=rejected_draft.review_preview_sha256,
                idempotency_key=f"confirm-capacity-{rejected_index:04d}",
                key_id="capacity-key",
                signing_key=_KEY,
                verification_keys={"capacity-key": _KEY},
                now_ms=2_100,
            )
    for prefix in ("suauth_", "suexcerpt_", "csubrev_"):
        assert (
            len(
                store.list_owned_documents(
                    "alice", logical_prefix=prefix, after_logical_id=None, limit=100
                )
            )
            == 64
        )
    index_row = store.get_owned_document("csubidx_" + _UNIT_ID.removeprefix("cunit_"), "alice")
    assert index_row is not None
    assert index_row.get("reservation_ids") == []


def test_confirmation_is_owner_private_preview_bound_and_expiring() -> None:
    store = InMemoryEngagementStore()
    draft = _claim(store)
    with pytest.raises(KeyError, match="unavailable"):
        confirm_substack_excerpt_review(
            store,
            owner_id="mallory",
            review_id=draft.review_id,
            expected_review_preview_sha256=draft.review_preview_sha256,
            idempotency_key="confirm-key-0001",
            key_id="substack-purpose-2026-07",
            signing_key=_KEY,
            verification_keys={"substack-purpose-2026-07": _KEY},
            now_ms=2_000,
        )
    with pytest.raises(ValueError, match="preview changed"):
        confirm_substack_excerpt_review(
            store,
            owner_id="alice",
            review_id=draft.review_id,
            expected_review_preview_sha256="0" * 64,
            idempotency_key="confirm-key-0001",
            key_id="substack-purpose-2026-07",
            signing_key=_KEY,
            verification_keys={"substack-purpose-2026-07": _KEY},
            now_ms=2_000,
        )
    with pytest.raises(ValueError, match="expired"):
        confirm_substack_excerpt_review(
            store,
            owner_id="alice",
            review_id=draft.review_id,
            expected_review_preview_sha256=draft.review_preview_sha256,
            idempotency_key="confirm-key-0001",
            key_id="substack-purpose-2026-07",
            signing_key=_KEY,
            verification_keys={"substack-purpose-2026-07": _KEY},
            now_ms=draft.expires_at_ms,
        )


def test_review_rejects_markup_whole_source_and_false_bounds_before_storage() -> None:
    store = InMemoryEngagementStore()
    with pytest.raises(ValueError, match="markup"):
        _claim(store, text="<img src=x>")
    with pytest.raises(ValueError, match="lifetime"):
        claim_substack_excerpt_review(
            store,
            owner_id="alice",
            idempotency_key="review-key-0002",
            collective_unit_id=_UNIT_ID,
            collective_preview_sha256=_PREVIEW,
            ref_id=_REF_ID,
            canonical_url=f"https://{_EXTERNAL_ID}",
            external_id=_EXTERNAL_ID,
            selection_text="complete",
            source_representation_sha256="c" * 64,
            source_representation_bytes=8,
            source_byte_start=0,
            lifetime_ms=1,
            now_ms=1_000,
            nonce="3" * 32,
        )
