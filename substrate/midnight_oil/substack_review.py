"""Owner-private review/confirmation overlay for one Substack excerpt.

The overlay is deliberately not a publication manifest or spend authority.
It binds a second human review to an immutable collective revision while the
existing production Substack guard remains closed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.engagement_spine.store import EngagementStore

from .substack_authorization import (
    MAX_SUBSTACK_AUTHORIZATION_LIFETIME_MS,
    MAX_SUBSTACK_EXCERPT_BYTES,
    SUBSTACK_PRIVATE_USE_POLICY_SHA256,
    SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
    SubstackExcerptReceipt,
    SubstackUseAuthorizationV2,
    canonical_substack_post,
    create_substack_excerpt_receipt,
    owner_scope_sha256,
    signed_substack_authorization,
    store_substack_authorization,
    store_substack_excerpt_receipt,
    stored_substack_authorization_state,
    validate_substack_excerpt_selection,
    verify_substack_authorization,
)

_REVIEW_DOMAIN = b"antiek.midnight-oil.substack-review-preview.v1\x00"
_REQUEST_DOMAIN = b"antiek.midnight-oil.substack-review-request.v1\x00"
_OVERLAY_DOMAIN = b"antiek.midnight-oil.substack-review-overlay.v1\x00"
_CONFIRM_DOMAIN = b"antiek.midnight-oil.substack-review-confirm.v1\x00"
_KEY_DOMAIN = b"antiek.midnight-oil.substack-review-key.v1\x00"
_IDEMPOTENCY_RE = re.compile(r"[A-Za-z0-9._:-]{8,128}")
_MAX_CONFIRMED_REVIEWS_PER_COLLECTIVE = 64


class _ReviewCapacityError(ValueError):
    pass


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SubstackExcerptReviewDraft(_Closed):
    schema_version: Literal[1] = 1
    review_id: str = Field(pattern=r"^sureview_[0-9a-f]{24}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collective_unit_id: str = Field(pattern=r"^cunit_[0-9a-f]{24}$")
    collective_preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ref_id: str = Field(pattern=r"^sref_[0-9a-f]{16}$")
    canonical_url: str = Field(min_length=1, max_length=2_048)
    external_id: str = Field(min_length=1, max_length=1_024)
    selection_text: str = Field(min_length=1, max_length=MAX_SUBSTACK_EXCERPT_BYTES)
    excerpt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    excerpt_bytes: int = Field(ge=1, le=MAX_SUBSTACK_EXCERPT_BYTES)
    source_representation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_representation_bytes: int = Field(ge=1, le=100_000_000)
    source_byte_start: int = Field(ge=0)
    source_byte_end: int = Field(gt=0)
    owner_affirms_lawful_access: Literal[True]
    owner_affirms_provider_processing: Literal[True]
    partial_excerpt_affirmed: Literal[True]
    redistribution_authorized: Literal[False]
    training_authorized: Literal[False]
    publication_authorized: Literal[False]
    issued_at_ms: int = Field(ge=0)
    not_before_ms: int = Field(ge=0)
    expires_at_ms: int = Field(gt=0)
    authorization_id: str = Field(pattern=r"^sua_[0-9a-f]{24}$")
    nonce: str = Field(pattern=r"^[0-9a-f]{32}$")
    state: Literal["awaiting_confirmation"]

    @model_validator(mode="after")
    def _canonical(self) -> SubstackExcerptReviewDraft:
        canonical_substack_post(self.canonical_url, self.external_id)
        encoded, digest, end = validate_substack_excerpt_selection(
            text=self.selection_text,
            source_representation_bytes=self.source_representation_bytes,
            source_byte_start=self.source_byte_start,
            max_excerpt_bytes=MAX_SUBSTACK_EXCERPT_BYTES,
        )
        if (
            self.excerpt_sha256 != digest
            or self.excerpt_bytes != len(encoded)
            or self.source_byte_end != end
        ):
            raise ValueError("Substack review selection conflicts")
        if not self.issued_at_ms == self.not_before_ms < self.expires_at_ms:
            raise ValueError("Substack review validity interval conflicts")
        if self.expires_at_ms - self.not_before_ms > MAX_SUBSTACK_AUTHORIZATION_LIFETIME_MS:
            raise ValueError("Substack review validity exceeds the bound")
        if self.review_preview_sha256 != substack_review_preview_sha256(self):
            raise ValueError("Substack review preview hash conflicts")
        return self


class ConfirmedSubstackReviewOverlay(_Closed):
    schema_version: Literal[1] = 1
    overlay_id: str = Field(pattern=r"^csubrev_[0-9a-f]{24}$")
    overlay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_id: str = Field(pattern=r"^sureview_[0-9a-f]{24}$")
    review_preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collective_unit_id: str = Field(pattern=r"^cunit_[0-9a-f]{24}$")
    collective_preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ref_id: str = Field(pattern=r"^sref_[0-9a-f]{16}$")
    authorization_id: str = Field(pattern=r"^sua_[0-9a-f]{24}$")
    authorization_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_id: str = Field(pattern=r"^suer_[0-9a-f]{24}$")
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    excerpt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    excerpt_bytes: int = Field(ge=1, le=MAX_SUBSTACK_EXCERPT_BYTES)
    source_byte_start: int = Field(ge=0)
    source_byte_end: int = Field(gt=0)
    expires_at_ms: int = Field(gt=0)
    content_class: Literal["personal_reading"]
    rights_tier: Literal["not_applicable"]
    rights_use: Literal["operator_authorized_excerpt"]
    provider_constraints_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    requires_manifest_v2: Literal[True]
    publication_execution_enabled: Literal[False]
    state: Literal["confirmed_owner_private_authority_review"]

    @model_validator(mode="after")
    def _canonical(self) -> ConfirmedSubstackReviewOverlay:
        digest = substack_review_overlay_sha256(self)
        if self.overlay_sha256 != digest or self.overlay_id != "csubrev_" + digest[:24]:
            raise ValueError("Substack review overlay identity conflicts")
        if self.provider_constraints_sha256 != SUBSTACK_PROVIDER_CONSTRAINTS_SHA256:
            raise ValueError("Substack review provider constraints conflict")
        return self


def _canonical(value: Mapping[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _digest(domain: bytes, value: Mapping[str, object]) -> str:
    return hashlib.sha256(domain + _canonical(value)).hexdigest()


def _without(value: Mapping[str, object], *fields: str) -> dict[str, object]:
    return {key: item for key, item in value.items() if key not in fields}


def substack_review_preview_sha256(
    draft: SubstackExcerptReviewDraft | Mapping[str, object],
) -> str:
    raw = draft.model_dump(mode="json") if isinstance(draft, BaseModel) else dict(draft)
    return _digest(_REVIEW_DOMAIN, _without(raw, "review_preview_sha256"))


def substack_review_overlay_sha256(
    overlay: ConfirmedSubstackReviewOverlay | Mapping[str, object],
) -> str:
    raw = overlay.model_dump(mode="json") if isinstance(overlay, BaseModel) else dict(overlay)
    return _digest(_OVERLAY_DOMAIN, _without(raw, "overlay_id", "overlay_sha256"))


def _logical_id(prefix: str, owner_id: str, idempotency_key: str) -> str:
    if _IDEMPOTENCY_RE.fullmatch(idempotency_key) is None:
        raise ValueError("Substack review idempotency key is invalid")
    digest = hashlib.sha256(
        _KEY_DOMAIN + owner_scope_sha256(owner_id).encode() + b"\x00" + idempotency_key.encode()
    ).hexdigest()[:24]
    return prefix + digest


def claim_substack_excerpt_review(
    store: EngagementStore,
    *,
    owner_id: str,
    idempotency_key: str,
    collective_unit_id: str,
    collective_preview_sha256: str,
    ref_id: str,
    canonical_url: str,
    external_id: str,
    selection_text: str,
    source_representation_sha256: str,
    source_representation_bytes: int,
    source_byte_start: int,
    lifetime_ms: int,
    now_ms: int,
    nonce: str,
) -> SubstackExcerptReviewDraft:
    if type(now_ms) is not int or now_ms < 0:
        raise ValueError("Substack review server time is invalid")
    if (
        type(lifetime_ms) is not int
        or not 60_000 <= lifetime_ms <= MAX_SUBSTACK_AUTHORIZATION_LIFETIME_MS
    ):
        raise ValueError("Substack review lifetime is invalid")
    if re.fullmatch(r"[0-9a-f]{32}", nonce) is None:
        raise ValueError("Substack review nonce is invalid")
    canonical_substack_post(canonical_url, external_id)
    encoded, excerpt_sha256, source_byte_end = validate_substack_excerpt_selection(
        text=selection_text,
        source_representation_bytes=source_representation_bytes,
        source_byte_start=source_byte_start,
        max_excerpt_bytes=MAX_SUBSTACK_EXCERPT_BYTES,
    )
    review_id = _logical_id("sureview_", owner_id, idempotency_key)
    authorization_id = (
        "sua_"
        + hashlib.sha256(
            b"antiek.midnight-oil.substack-review-authorization-id.v1\x00"
            + review_id.encode()
            + nonce.encode()
        ).hexdigest()[:24]
    )
    request_material: dict[str, object] = {
        "collective_unit_id": collective_unit_id,
        "collective_preview_sha256": collective_preview_sha256,
        "ref_id": ref_id,
        "canonical_url": canonical_url,
        "external_id": external_id,
        "selection_text": selection_text,
        "source_representation_sha256": source_representation_sha256,
        "source_representation_bytes": source_representation_bytes,
        "source_byte_start": source_byte_start,
        "lifetime_ms": lifetime_ms,
        "owner_affirms_lawful_access": True,
        "owner_affirms_provider_processing": True,
    }
    request_sha256 = _digest(_REQUEST_DOMAIN, request_material)
    raw: dict[str, object] = {
        "schema_version": 1,
        "review_id": review_id,
        "request_sha256": request_sha256,
        "collective_unit_id": collective_unit_id,
        "collective_preview_sha256": collective_preview_sha256,
        "ref_id": ref_id,
        "canonical_url": canonical_url,
        "external_id": external_id,
        "selection_text": selection_text,
        "excerpt_sha256": excerpt_sha256,
        "excerpt_bytes": len(encoded),
        "source_representation_sha256": source_representation_sha256,
        "source_representation_bytes": source_representation_bytes,
        "source_byte_start": source_byte_start,
        "source_byte_end": source_byte_end,
        "owner_affirms_lawful_access": True,
        "owner_affirms_provider_processing": True,
        "partial_excerpt_affirmed": True,
        "redistribution_authorized": False,
        "training_authorized": False,
        "publication_authorized": False,
        "issued_at_ms": now_ms,
        "not_before_ms": now_ms,
        "expires_at_ms": now_ms + lifetime_ms,
        "authorization_id": authorization_id,
        "nonce": nonce,
        "state": "awaiting_confirmation",
    }
    raw["review_preview_sha256"] = substack_review_preview_sha256(raw)
    candidate = SubstackExcerptReviewDraft.model_validate(raw)

    def claim(current: dict[str, object] | None) -> dict[str, object]:
        if current is not None:
            if current.get("document_type") != "substack_excerpt_review_draft":
                raise ValueError("Substack review identity requires reconciliation")
            existing = SubstackExcerptReviewDraft.model_validate(current.get("draft"))
            if not hmac.compare_digest(existing.request_sha256, request_sha256):
                raise ValueError("Substack review idempotency key conflicts")
            return current
        return {
            "document_type": "substack_excerpt_review_draft",
            "review_id": review_id,
            "request_sha256": request_sha256,
            "draft": candidate.model_dump(mode="json"),
        }

    row = store.mutate_owned_document(review_id, owner_id, claim)
    return SubstackExcerptReviewDraft.model_validate(row.get("draft"))


def _load_applied_review_overlay(
    store: EngagementStore,
    *,
    owner_id: str,
    draft: SubstackExcerptReviewDraft,
    overlay_id: object,
    verification_keys: Mapping[str, bytes],
    now_ms: int,
) -> ConfirmedSubstackReviewOverlay:
    if not isinstance(overlay_id, str) or re.fullmatch(r"csubrev_[0-9a-f]{24}", overlay_id) is None:
        raise ValueError("Substack confirmation requires reconciliation")
    row = store.get_owned_document(overlay_id, owner_id)
    if row is None or row.get("document_type") != "confirmed_substack_review_overlay":
        raise ValueError("Substack confirmation requires reconciliation")
    overlay = ConfirmedSubstackReviewOverlay.model_validate(row.get("overlay"))
    if (
        row.get("overlay_sha256") != overlay.overlay_sha256
        or overlay.overlay_id != overlay_id
        or overlay.review_id != draft.review_id
        or overlay.review_preview_sha256 != draft.review_preview_sha256
        or overlay.collective_unit_id != draft.collective_unit_id
        or overlay.collective_preview_sha256 != draft.collective_preview_sha256
        or overlay.ref_id != draft.ref_id
    ):
        raise ValueError("Substack confirmation requires reconciliation")
    authority_state = stored_substack_authorization_state(
        store,
        owner_id=owner_id,
        authorization_id=overlay.authorization_id,
        expected_authorization_sha256=overlay.authorization_sha256,
        verification_keys=verification_keys,
        now_ms=now_ms,
    )
    if authority_state in {"unavailable", "reconciliation_required"}:
        raise ValueError("Substack confirmation requires reconciliation")
    authorization_row = store.get_owned_document(
        "suauth_" + overlay.authorization_id.removeprefix("sua_"), owner_id
    )
    if (
        authorization_row is None
        or authorization_row.get("document_type") != "midnight_oil_substack_authorization"
        or authorization_row.get("authorization_sha256") != overlay.authorization_sha256
    ):
        raise ValueError("Substack confirmation requires reconciliation")
    authorization = SubstackUseAuthorizationV2.model_validate(
        authorization_row.get("authorization")
    )
    verification_time = min(
        max(now_ms, authorization.not_before_ms), authorization.expires_at_ms - 1
    )
    verify_substack_authorization(
        authorization,
        verification_keys=verification_keys,
        owner_id=owner_id,
        now_ms=verification_time,
        collective_unit_id=draft.collective_unit_id,
        collective_preview_sha256=draft.collective_preview_sha256,
        ref_id=draft.ref_id,
    )
    if (
        authorization.authorization_id != overlay.authorization_id
        or authorization.authorization_sha256 != overlay.authorization_sha256
        or authorization.canonical_url != draft.canonical_url
        or authorization.external_id != draft.external_id
        or authorization.source_representation_sha256 != draft.source_representation_sha256
        or authorization.source_representation_bytes != draft.source_representation_bytes
        or authorization.source_byte_start != draft.source_byte_start
        or authorization.source_byte_end != draft.source_byte_end
        or authorization.excerpt_sha256 != draft.excerpt_sha256
        or authorization.excerpt_bytes != draft.excerpt_bytes
        or authorization.expires_at_ms != draft.expires_at_ms
        or overlay.excerpt_sha256 != draft.excerpt_sha256
        or overlay.excerpt_bytes != draft.excerpt_bytes
        or overlay.source_byte_start != draft.source_byte_start
        or overlay.source_byte_end != draft.source_byte_end
        or overlay.expires_at_ms != draft.expires_at_ms
    ):
        raise ValueError("Substack confirmation requires reconciliation")
    receipt_id = "suexcerpt_" + overlay.receipt_id.removeprefix("suer_")
    receipt_row = store.get_owned_document(receipt_id, owner_id)
    if (
        receipt_row is None
        or receipt_row.get("document_type") != "midnight_oil_substack_excerpt_receipt"
        or receipt_row.get("receipt_sha256") != overlay.receipt_sha256
    ):
        raise ValueError("Substack confirmation requires reconciliation")
    receipt = SubstackExcerptReceipt.model_validate(receipt_row.get("receipt"))
    if (
        receipt.receipt_id != overlay.receipt_id
        or receipt.receipt_sha256 != overlay.receipt_sha256
        or receipt.authorization_id != overlay.authorization_id
        or receipt.authorization_sha256 != overlay.authorization_sha256
        or receipt.owner_scope_sha256 != owner_scope_sha256(owner_id)
        or receipt.collective_unit_id != draft.collective_unit_id
        or receipt.collective_preview_sha256 != draft.collective_preview_sha256
        or receipt.ref_id != draft.ref_id
        or receipt.canonical_url != draft.canonical_url
        or receipt.external_id != draft.external_id
        or receipt.excerpt_sha256 != overlay.excerpt_sha256
        or receipt.excerpt_bytes != overlay.excerpt_bytes
        or receipt.source_representation_sha256 != draft.source_representation_sha256
        or receipt.source_representation_bytes != draft.source_representation_bytes
        or receipt.source_byte_start != overlay.source_byte_start
        or receipt.source_byte_end != overlay.source_byte_end
        or receipt.text != draft.selection_text
    ):
        raise ValueError("Substack confirmation requires reconciliation")
    return overlay


def _validated_review_index_lists(
    row: Mapping[str, object],
    *,
    collective_unit_id: str,
    collective_preview_sha256: str,
) -> tuple[list[str], list[str]]:
    overlay_ids = row.get("overlay_ids")
    reservation_ids = row.get("reservation_ids", [])
    if (
        row.get("document_type") != "collective_substack_review_index"
        or row.get("collective_unit_id") != collective_unit_id
        or row.get("collective_preview_sha256") != collective_preview_sha256
        or not isinstance(overlay_ids, list)
        or not isinstance(reservation_ids, list)
    ):
        raise ValueError("Substack review index requires reconciliation")
    overlays = [str(value) for value in overlay_ids]
    reservations = [str(value) for value in reservation_ids]
    if (
        any(re.fullmatch(r"csubrev_[0-9a-f]{24}", value) is None for value in overlays)
        or any(
            re.fullmatch(r"substack_review_confirm_[0-9a-f]{24}", value) is None
            for value in reservations
        )
        or len(set(overlays)) != len(overlays)
        or len(set(reservations)) != len(reservations)
        or len(overlays) + len(reservations) > _MAX_CONFIRMED_REVIEWS_PER_COLLECTIVE
    ):
        raise ValueError("Substack review index requires reconciliation")
    return overlays, reservations


def confirm_substack_excerpt_review(
    store: EngagementStore,
    *,
    owner_id: str,
    review_id: str,
    expected_review_preview_sha256: str,
    idempotency_key: str,
    key_id: str,
    signing_key: bytes,
    verification_keys: Mapping[str, bytes],
    now_ms: int,
) -> ConfirmedSubstackReviewOverlay:
    row = store.get_owned_document(review_id, owner_id)
    if row is None or row.get("document_type") != "substack_excerpt_review_draft":
        raise KeyError("Substack review is unavailable")
    draft = SubstackExcerptReviewDraft.model_validate(row.get("draft"))
    if not hmac.compare_digest(draft.review_preview_sha256, expected_review_preview_sha256):
        raise ValueError("Substack review preview changed")
    if type(now_ms) is not int or now_ms < 0:
        raise ValueError("Substack review server time is invalid")
    confirm_id = _logical_id("substack_review_confirm_", owner_id, idempotency_key)
    request_sha256 = _digest(
        _CONFIRM_DOMAIN,
        {
            "review_id": review_id,
            "review_preview_sha256": draft.review_preview_sha256,
        },
    )

    def claim(current: dict[str, object] | None) -> dict[str, object]:
        if current is not None:
            if (
                current.get("document_type") != "substack_excerpt_review_confirmation"
                or current.get("request_sha256") != request_sha256
                or current.get("state") not in {"claimed", "applied", "rejected_capacity"}
                or not isinstance(current.get("signing_key_id"), str)
                or type(current.get("confirmed_at_ms")) is not int
                or current.get("review_id") != draft.review_id
                or current.get("review_preview_sha256") != draft.review_preview_sha256
                or current.get("collective_unit_id") != draft.collective_unit_id
                or current.get("collective_preview_sha256") != draft.collective_preview_sha256
                or current.get("recovery_idempotency_key") != idempotency_key
            ):
                raise ValueError("Substack confirmation idempotency key conflicts")
            return current
        current_signing_key = verification_keys.get(key_id)
        if current_signing_key is None or not hmac.compare_digest(current_signing_key, signing_key):
            raise ValueError("Substack confirmation signing key conflicts")
        if not draft.not_before_ms <= now_ms < draft.expires_at_ms:
            raise ValueError("Substack review is expired or not active")
        return {
            "document_type": "substack_excerpt_review_confirmation",
            "request_sha256": request_sha256,
            "signing_key_id": key_id,
            "confirmed_at_ms": now_ms,
            "review_id": draft.review_id,
            "review_preview_sha256": draft.review_preview_sha256,
            "collective_unit_id": draft.collective_unit_id,
            "collective_preview_sha256": draft.collective_preview_sha256,
            "recovery_idempotency_key": idempotency_key,
            "state": "claimed",
        }

    confirmation = store.mutate_owned_document(confirm_id, owner_id, claim)
    if confirmation.get("state") == "rejected_capacity":
        raise ValueError("Substack review limit is reached for this collective")
    if confirmation.get("state") == "applied":
        return _load_applied_review_overlay(
            store,
            owner_id=owner_id,
            draft=draft,
            overlay_id=confirmation.get("overlay_id"),
            verification_keys=verification_keys,
            now_ms=now_ms,
        )
    confirmed_at_ms = confirmation.get("confirmed_at_ms")
    if (
        type(confirmed_at_ms) is not int
        or not draft.not_before_ms <= confirmed_at_ms < draft.expires_at_ms
    ):
        raise ValueError("Substack confirmation requires reconciliation")
    index_id = "csubidx_" + draft.collective_unit_id.removeprefix("cunit_")

    def reserve_capacity(current: dict[str, object] | None) -> dict[str, object]:
        if current is None:
            return {
                "document_type": "collective_substack_review_index",
                "collective_unit_id": draft.collective_unit_id,
                "collective_preview_sha256": draft.collective_preview_sha256,
                "overlay_ids": [],
                "reservation_ids": [confirm_id],
            }
        overlay_ids, reservation_ids = _validated_review_index_lists(
            current,
            collective_unit_id=draft.collective_unit_id,
            collective_preview_sha256=draft.collective_preview_sha256,
        )
        expected_overlay_id = confirmation.get("overlay_id")
        if isinstance(expected_overlay_id, str) and expected_overlay_id in overlay_ids:
            return current
        if confirm_id in reservation_ids:
            return current
        if len(overlay_ids) + len(reservation_ids) >= _MAX_CONFIRMED_REVIEWS_PER_COLLECTIVE:
            raise _ReviewCapacityError("Substack review limit is reached for this collective")
        return {
            **current,
            "reservation_ids": sorted([*reservation_ids, confirm_id]),
        }

    try:
        store.mutate_owned_document(index_id, owner_id, reserve_capacity)
    except _ReviewCapacityError as exc:

        def reject_capacity(current: dict[str, object] | None) -> dict[str, object]:
            if (
                current is None
                or current.get("request_sha256") != request_sha256
                or current.get("state") != "claimed"
            ):
                raise ValueError("Substack confirmation requires reconciliation")
            return {**current, "state": "rejected_capacity"}

        store.mutate_owned_document(confirm_id, owner_id, reject_capacity)
        raise ValueError(str(exc)) from exc
    pinned_key_id = confirmation.get("signing_key_id")
    if not isinstance(pinned_key_id, str):
        raise ValueError("Substack confirmation requires reconciliation")
    pinned_signing_key = verification_keys.get(pinned_key_id)
    if pinned_signing_key is None:
        raise ValueError("Substack confirmation pinned signing key is unavailable")
    authorization = signed_substack_authorization(
        {
            "schema_version": 2,
            "authorization_id": draft.authorization_id,
            "owner_scope_sha256": owner_scope_sha256(owner_id),
            "collective_unit_id": draft.collective_unit_id,
            "collective_preview_sha256": draft.collective_preview_sha256,
            "ref_id": draft.ref_id,
            "canonical_url": draft.canonical_url,
            "external_id": draft.external_id,
            "origin": "owner_selected_excerpt_v1",
            "use_scope": "owner_private_model_context",
            "owner_affirms_lawful_access": True,
            "owner_affirms_provider_processing": True,
            "provider_processing_scope": "requires_compatible_provider_capability",
            "provider_constraints_id": "antiek-substack-provider-constraints-v1",
            "provider_constraints_sha256": SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
            "redistribution_authorized": False,
            "training_authorized": False,
            "publication_authorized": False,
            "one_excerpt_only": True,
            "max_excerpt_bytes": MAX_SUBSTACK_EXCERPT_BYTES,
            "representation_evidence": "owner_attestation_unverified",
            "source_representation_sha256": draft.source_representation_sha256,
            "source_representation_bytes": draft.source_representation_bytes,
            "source_byte_start": draft.source_byte_start,
            "source_byte_end": draft.source_byte_end,
            "excerpt_sha256": draft.excerpt_sha256,
            "excerpt_bytes": draft.excerpt_bytes,
            "partial_excerpt_affirmed": True,
            "rights_policy_id": "antiek-substack-private-use-v1",
            "rights_policy_sha256": SUBSTACK_PRIVATE_USE_POLICY_SHA256,
            "issued_at_ms": draft.issued_at_ms,
            "not_before_ms": draft.not_before_ms,
            "expires_at_ms": draft.expires_at_ms,
            "nonce": draft.nonce,
        },
        key_id=pinned_key_id,
        signing_key=pinned_signing_key,
    )
    store_substack_authorization(
        store,
        owner_id=owner_id,
        authorization=authorization,
        verification_keys=verification_keys,
        now_ms=confirmed_at_ms,
    )
    receipt = create_substack_excerpt_receipt(
        authorization,
        verification_keys=verification_keys,
        owner_id=owner_id,
        now_ms=confirmed_at_ms,
        source_representation_sha256=draft.source_representation_sha256,
        source_representation_bytes=draft.source_representation_bytes,
        source_byte_start=draft.source_byte_start,
        text=draft.selection_text,
    )
    store_substack_excerpt_receipt(
        store,
        owner_id=owner_id,
        receipt=receipt,
        authorization_id=authorization.authorization_id,
        verification_keys=verification_keys,
        now_ms=confirmed_at_ms,
    )
    material: dict[str, object] = {
        "schema_version": 1,
        "review_id": draft.review_id,
        "review_preview_sha256": draft.review_preview_sha256,
        "collective_unit_id": draft.collective_unit_id,
        "collective_preview_sha256": draft.collective_preview_sha256,
        "ref_id": draft.ref_id,
        "authorization_id": authorization.authorization_id,
        "authorization_sha256": authorization.authorization_sha256,
        "receipt_id": receipt.receipt_id,
        "receipt_sha256": receipt.receipt_sha256,
        "excerpt_sha256": receipt.excerpt_sha256,
        "excerpt_bytes": receipt.excerpt_bytes,
        "source_byte_start": receipt.source_byte_start,
        "source_byte_end": receipt.source_byte_end,
        "expires_at_ms": authorization.expires_at_ms,
        "content_class": "personal_reading",
        "rights_tier": "not_applicable",
        "rights_use": "operator_authorized_excerpt",
        "provider_constraints_sha256": SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
        "requires_manifest_v2": True,
        "publication_execution_enabled": False,
        "state": "confirmed_owner_private_authority_review",
    }
    digest = substack_review_overlay_sha256(material)
    overlay = ConfirmedSubstackReviewOverlay.model_validate(
        {**material, "overlay_id": "csubrev_" + digest[:24], "overlay_sha256": digest}
    )

    def persist(current: dict[str, object] | None) -> dict[str, object]:
        if current is not None:
            existing = ConfirmedSubstackReviewOverlay.model_validate(current.get("overlay"))
            if existing != overlay:
                raise ValueError("Substack review overlay identity conflicts")
            return current
        return {
            "document_type": "confirmed_substack_review_overlay",
            "overlay_sha256": overlay.overlay_sha256,
            "overlay": overlay.model_dump(mode="json"),
        }

    store.mutate_owned_document(overlay.overlay_id, owner_id, persist)

    def bind_overlay(current: dict[str, object] | None) -> dict[str, object]:
        if (
            current is None
            or current.get("request_sha256") != request_sha256
            or current.get("signing_key_id") != pinned_key_id
            or current.get("state") != "claimed"
        ):
            raise ValueError("Substack confirmation requires reconciliation")
        existing = current.get("overlay_id")
        if existing is not None and existing != overlay.overlay_id:
            raise ValueError("Substack confirmation requires reconciliation")
        return {**current, "overlay_id": overlay.overlay_id}

    store.mutate_owned_document(confirm_id, owner_id, bind_overlay)

    def finalize_index(current: dict[str, object] | None) -> dict[str, object]:
        if current is None:
            raise ValueError("Substack review index requires reconciliation")
        overlay_ids, reservation_ids = _validated_review_index_lists(
            current,
            collective_unit_id=draft.collective_unit_id,
            collective_preview_sha256=draft.collective_preview_sha256,
        )
        if overlay.overlay_id in overlay_ids:
            if confirm_id not in reservation_ids:
                return current
            return {
                **current,
                "reservation_ids": [value for value in reservation_ids if value != confirm_id],
            }
        if confirm_id not in reservation_ids:
            raise ValueError("Substack review index requires reconciliation")
        return {
            **current,
            "overlay_ids": sorted([*overlay_ids, overlay.overlay_id]),
            "reservation_ids": [value for value in reservation_ids if value != confirm_id],
        }

    store.mutate_owned_document(index_id, owner_id, finalize_index)

    def settle(current: dict[str, object] | None) -> dict[str, object]:
        if (
            current is None
            or current.get("request_sha256") != request_sha256
            or current.get("signing_key_id") != pinned_key_id
        ):
            raise ValueError("Substack confirmation requires reconciliation")
        if current.get("state") == "applied":
            if current.get("overlay_id") != overlay.overlay_id:
                raise ValueError("Substack confirmation requires reconciliation")
            return current
        if current.get("state") != "claimed":
            raise ValueError("Substack confirmation requires reconciliation")
        return {**current, "state": "applied", "overlay_id": overlay.overlay_id}

    store.mutate_owned_document(confirm_id, owner_id, settle)
    return overlay


def get_substack_excerpt_review(
    store: EngagementStore, *, owner_id: str, review_id: str
) -> SubstackExcerptReviewDraft | None:
    if re.fullmatch(r"sureview_[0-9a-f]{24}", review_id) is None:
        return None
    row = store.get_owned_document(review_id, owner_id)
    if row is None or row.get("document_type") != "substack_excerpt_review_draft":
        return None
    draft = SubstackExcerptReviewDraft.model_validate(row.get("draft"))
    if draft.review_id != review_id or row.get("request_sha256") != draft.request_sha256:
        raise ValueError("Substack review draft requires reconciliation")
    return draft


def reconcile_pending_substack_reviews(
    store: EngagementStore,
    *,
    owner_id: str,
    collective_unit_id: str,
    collective_preview_sha256: str,
    active_key_id: str,
    signing_key: bytes,
    verification_keys: Mapping[str, bytes],
    now_ms: int,
) -> tuple[ConfirmedSubstackReviewOverlay, ...]:
    """Finish previously confirmed reservations without browser-held retry state."""

    index_id = "csubidx_" + collective_unit_id.removeprefix("cunit_")
    index = store.get_owned_document(index_id, owner_id)
    if index is None:
        return ()
    _overlay_ids, reservation_ids = _validated_review_index_lists(
        index,
        collective_unit_id=collective_unit_id,
        collective_preview_sha256=collective_preview_sha256,
    )
    repaired: list[ConfirmedSubstackReviewOverlay] = []
    for confirmation_id in reservation_ids:
        confirmation = store.get_owned_document(confirmation_id, owner_id)
        if (
            confirmation is None
            or confirmation.get("document_type") != "substack_excerpt_review_confirmation"
            or confirmation.get("state") != "claimed"
            or confirmation.get("collective_unit_id") != collective_unit_id
            or confirmation.get("collective_preview_sha256") != collective_preview_sha256
        ):
            raise ValueError("Substack reservation requires reconciliation")
        review_id = confirmation.get("review_id")
        review_preview = confirmation.get("review_preview_sha256")
        recovery_key = confirmation.get("recovery_idempotency_key")
        if (
            not isinstance(review_id, str)
            or not isinstance(review_preview, str)
            or not isinstance(recovery_key, str)
            or _logical_id("substack_review_confirm_", owner_id, recovery_key) != confirmation_id
        ):
            raise ValueError("Substack reservation requires reconciliation")
        repaired.append(
            confirm_substack_excerpt_review(
                store,
                owner_id=owner_id,
                review_id=review_id,
                expected_review_preview_sha256=review_preview,
                idempotency_key=recovery_key,
                key_id=active_key_id,
                signing_key=signing_key,
                verification_keys=verification_keys,
                now_ms=now_ms,
            )
        )
    return tuple(repaired)


def pending_substack_review_count(
    store: EngagementStore,
    *,
    owner_id: str,
    collective_unit_id: str,
    collective_preview_sha256: str,
) -> int:
    index_id = "csubidx_" + collective_unit_id.removeprefix("cunit_")
    index = store.get_owned_document(index_id, owner_id)
    if index is None:
        return 0
    _overlay_ids, reservation_ids = _validated_review_index_lists(
        index,
        collective_unit_id=collective_unit_id,
        collective_preview_sha256=collective_preview_sha256,
    )
    return len(reservation_ids)


def list_confirmed_substack_reviews(
    store: EngagementStore,
    *,
    owner_id: str,
    collective_unit_id: str,
    collective_preview_sha256: str,
) -> tuple[ConfirmedSubstackReviewOverlay, ...]:
    index_id = "csubidx_" + collective_unit_id.removeprefix("cunit_")
    row = store.get_owned_document(index_id, owner_id)
    if row is None:
        return ()
    overlay_ids, _reservation_ids = _validated_review_index_lists(
        row,
        collective_unit_id=collective_unit_id,
        collective_preview_sha256=collective_preview_sha256,
    )
    overlays: list[ConfirmedSubstackReviewOverlay] = []
    for overlay_id in overlay_ids:
        overlay_row = store.get_owned_document(overlay_id, owner_id)
        if (
            overlay_row is None
            or overlay_row.get("document_type") != "confirmed_substack_review_overlay"
        ):
            raise ValueError("Substack review overlay is unavailable")
        overlay = ConfirmedSubstackReviewOverlay.model_validate(overlay_row.get("overlay"))
        if (
            overlay.overlay_id != overlay_id
            or overlay_row.get("overlay_sha256") != overlay.overlay_sha256
            or overlay.collective_unit_id != collective_unit_id
            or overlay.collective_preview_sha256 != collective_preview_sha256
        ):
            raise ValueError("Substack review overlay binding conflicts")
        overlays.append(overlay)
    return tuple(sorted(overlays, key=lambda item: (item.ref_id, item.overlay_id)))


def review_draft_projection(draft: SubstackExcerptReviewDraft) -> dict[str, object]:
    return {
        "schema_version": 1,
        "review_id": draft.review_id,
        "review_preview_sha256": draft.review_preview_sha256,
        "collective_unit_id": draft.collective_unit_id,
        "collective_preview_sha256": draft.collective_preview_sha256,
        "ref_id": draft.ref_id,
        "canonical_url": draft.canonical_url,
        "selection_text": draft.selection_text,
        "excerpt_sha256": draft.excerpt_sha256,
        "excerpt_bytes": draft.excerpt_bytes,
        "source_byte_start": draft.source_byte_start,
        "source_byte_end": draft.source_byte_end,
        "expires_at_ms": draft.expires_at_ms,
        "representation_evidence": "owner_attestation_unverified",
        "content_class": "personal_reading",
        "rights_tier": "not_applicable",
        "rights_use": "operator_authorized_excerpt",
        "provider_constraints_sha256": SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
        "publication_execution_enabled": False,
        "state": draft.state,
    }


__all__ = [
    "ConfirmedSubstackReviewOverlay",
    "SubstackExcerptReviewDraft",
    "claim_substack_excerpt_review",
    "confirm_substack_excerpt_review",
    "get_substack_excerpt_review",
    "list_confirmed_substack_reviews",
    "pending_substack_review_count",
    "reconcile_pending_substack_reviews",
    "review_draft_projection",
    "substack_review_overlay_sha256",
    "substack_review_preview_sha256",
]
