"""Owner-private authority for bounded, manually selected Substack excerpts.

This module intentionally has no network seam.  A reviewed post identity,
subscription access, and permission to send selected text to a model are three
different facts.  The owner attests to the third fact through an authenticated
surface; the server signs the closed artifact.  Antiek stores only the selected
bytes and the owner's explicitly unverified representation/range attestation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from collections.abc import Callable, Mapping
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.engagement_spine.store import EngagementStore

MAX_SUBSTACK_EXCERPT_BYTES = 8_192
MAX_SUBSTACK_AUTHORIZATION_JSON_BYTES = 64_000
MAX_SUBSTACK_AUTHORIZATION_LIFETIME_MS = 31 * 24 * 60 * 60 * 1_000
SUBSTACK_PRIVATE_USE_POLICY_SHA256 = hashlib.sha256(
    b"antiek.substack-private-use.v1\x00"
    b"owner-selected-excerpt:owner-private-model-context:"
    b"no-redistribution:no-training:no-publication"
).hexdigest()
SUBSTACK_PROVIDER_CONSTRAINTS_SHA256 = hashlib.sha256(
    b"antiek.substack-provider-constraints.v1\x00"
    b"separate-compatible-provider-capability-required:"
    b"no-training:no-retention:no-provider-logging"
).hexdigest()

_AUTHORIZATION_DOMAIN = b"antiek.midnight-oil.substack-use-authorization.v1\x00"
_SIGNATURE_DOMAIN = b"antiek.midnight-oil.substack-use-signature.v1\x00"
_RECEIPT_DOMAIN = b"antiek.midnight-oil.substack-excerpt-receipt.v1\x00"
_OWNER_SCOPE_DOMAIN = b"antiek.midnight-oil.owner-scope.v1\x00"
_TENANT_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_SLUG_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,198}[a-z0-9])?")
_MARKUP_RE = re.compile(r"<\s*/?\s*[A-Za-z][^>]*>")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]\n]*\]")
_AUTHORIZATION_ID_RE = re.compile(r"sua_[0-9a-f]{24}")
_RECEIPT_ID_RE = re.compile(r"suer_[0-9a-f]{24}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def owner_scope_sha256(owner_id: str) -> str:
    owner = owner_id.strip()
    if not owner:
        raise ValueError("owner id is required")
    return hashlib.sha256(_OWNER_SCOPE_DOMAIN + owner.encode("utf-8")).hexdigest()


def canonical_substack_post(canonical_url: str, external_id: str) -> tuple[str, str]:
    """Return exact tenant and slug, rejecting generic or ambiguous URLs."""
    if not canonical_url.isascii() or not external_id.isascii():
        raise ValueError("Substack post identity must be ASCII")
    try:
        parsed = urlsplit(canonical_url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Substack post URL is invalid") from exc
    host = parsed.hostname or ""
    labels = host.split(".")
    path_parts = parsed.path.split("/")
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.query
        or parsed.fragment
        or len(labels) != 3
        or labels[1:] != ["substack", "com"]
        or _TENANT_RE.fullmatch(labels[0]) is None
        or len(path_parts) != 3
        or path_parts[1] != "p"
        or _SLUG_RE.fullmatch(path_parts[2]) is None
    ):
        raise ValueError("Substack v1 requires an exact tenant post URL")
    expected_url = f"https://{host}/p/{path_parts[2]}"
    expected_external_id = f"{host}/p/{path_parts[2]}"
    if canonical_url != expected_url or external_id != expected_external_id:
        raise ValueError("Substack post identity is not canonical")
    return labels[0], path_parts[2]


class SubstackUseAuthorization(_Closed):
    """Signed authorization for one excerpt in one immutable collective preview."""

    schema_version: Literal[1] = 1
    authorization_id: str = Field(pattern=r"^sua_[0-9a-f]{24}$")
    owner_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collective_unit_id: str = Field(pattern=r"^cunit_[0-9a-f]{24}$")
    collective_preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ref_id: str = Field(pattern=r"^sref_[0-9a-f]{16}$")
    canonical_url: str = Field(min_length=1, max_length=2_048)
    external_id: str = Field(min_length=1, max_length=1_024)
    origin: Literal["owner_selected_excerpt_v1"]
    use_scope: Literal["owner_private_model_context"]
    owner_affirms_provider_processing: Literal[True]
    provider_processing_scope: Literal["requires_compatible_provider_capability"]
    provider_constraints_id: Literal["antiek-substack-provider-constraints-v1"]
    provider_constraints_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    redistribution_authorized: Literal[False]
    training_authorized: Literal[False]
    publication_authorized: Literal[False]
    one_excerpt_only: Literal[True]
    max_excerpt_bytes: int = Field(ge=256, le=MAX_SUBSTACK_EXCERPT_BYTES)
    representation_evidence: Literal["owner_attestation_unverified"]
    source_representation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_representation_bytes: int = Field(ge=1, le=100_000_000)
    source_byte_start: int = Field(ge=0)
    source_byte_end: int = Field(gt=0)
    excerpt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    excerpt_bytes: int = Field(ge=1, le=MAX_SUBSTACK_EXCERPT_BYTES)
    partial_excerpt_affirmed: Literal[True]
    rights_policy_id: Literal["antiek-substack-private-use-v1"]
    rights_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    issued_at_ms: int = Field(ge=0)
    not_before_ms: int = Field(ge=0)
    expires_at_ms: int = Field(gt=0)
    nonce: str = Field(pattern=r"^[0-9a-f]{32}$")
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    authorization_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _canonical_contract(self) -> SubstackUseAuthorization:
        canonical_substack_post(self.canonical_url, self.external_id)
        expected_ref_id = (
            "sref_"
            + hashlib.sha256(f"substack:substack:{self.external_id}".encode()).hexdigest()[:16]
        )
        if self.ref_id != expected_ref_id:
            raise ValueError("Substack authorization ref id conflicts")
        if self.rights_policy_sha256 != SUBSTACK_PRIVATE_USE_POLICY_SHA256:
            raise ValueError("Substack authorization rights policy conflicts")
        if self.provider_constraints_sha256 != SUBSTACK_PROVIDER_CONSTRAINTS_SHA256:
            raise ValueError("Substack provider constraints conflict")
        if (
            self.excerpt_bytes > self.max_excerpt_bytes
            or self.source_byte_end <= self.source_byte_start
            or self.source_byte_end > self.source_representation_bytes
            or self.source_byte_end - self.source_byte_start != self.excerpt_bytes
            or (
                self.source_byte_start == 0
                and self.source_byte_end == self.source_representation_bytes
            )
        ):
            raise ValueError("Substack authorization excerpt commitment conflicts")
        if not self.issued_at_ms <= self.not_before_ms < self.expires_at_ms:
            raise ValueError("Substack authorization validity interval is invalid")
        if self.expires_at_ms - self.not_before_ms > MAX_SUBSTACK_AUTHORIZATION_LIFETIME_MS:
            raise ValueError("Substack authorization lifetime exceeds the bound")
        if self.authorization_sha256 != substack_authorization_sha256(self):
            raise ValueError("Substack authorization hash conflicts")
        return self


def _canonical_material(value: Mapping[str, object], *, omitted: frozenset[str]) -> bytes:
    material = {key: item for key, item in value.items() if key not in omitted}
    return json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def substack_authorization_sha256(
    authorization: SubstackUseAuthorization | Mapping[str, object],
) -> str:
    raw = (
        authorization.model_dump(mode="json")
        if isinstance(authorization, SubstackUseAuthorization)
        else authorization
    )
    return hashlib.sha256(
        _AUTHORIZATION_DOMAIN
        + _canonical_material(raw, omitted=frozenset({"authorization_sha256", "signature_sha256"}))
    ).hexdigest()


def substack_authorization_signature(authorization_sha256: str, *, signing_key: bytes) -> str:
    if len(signing_key) < 32:
        raise ValueError("Substack authorization signing key must be at least 256 bits")
    return hmac.digest(
        signing_key,
        _SIGNATURE_DOMAIN + authorization_sha256.encode("ascii"),
        "sha256",
    ).hex()


def signed_substack_authorization(
    material: Mapping[str, object], *, key_id: str, signing_key: bytes
) -> SubstackUseAuthorization:
    raw = {**material, "key_id": key_id}
    digest = substack_authorization_sha256(raw)
    return SubstackUseAuthorization.model_validate(
        {
            **raw,
            "authorization_sha256": digest,
            "signature_sha256": substack_authorization_signature(digest, signing_key=signing_key),
        }
    )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("Substack authorization contains duplicate JSON keys")
        out[key] = value
    return out


def parse_substack_authorization_json(payload: bytes) -> SubstackUseAuthorization:
    """Parse a serialized authority without allowing JSON key shadowing."""
    if not payload or len(payload) > MAX_SUBSTACK_AUTHORIZATION_JSON_BYTES:
        raise ValueError("Substack authorization JSON is outside the size contract")
    try:
        raw = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Substack authorization JSON is invalid") from exc
    return SubstackUseAuthorization.model_validate(raw)


def verify_substack_authorization(
    authorization: SubstackUseAuthorization,
    *,
    verification_keys: Mapping[str, bytes],
    owner_id: str,
    now_ms: int,
    required_until_ms: int | None = None,
    collective_unit_id: str | None = None,
    collective_preview_sha256: str | None = None,
    ref_id: str | None = None,
) -> None:
    _validate_time(now_ms, field="now_ms")
    if required_until_ms is not None:
        _validate_time(required_until_ms, field="required_until_ms")
    key = verification_keys.get(authorization.key_id)
    if key is None:
        raise ValueError("Substack authorization signing key is unknown")
    expected = substack_authorization_signature(authorization.authorization_sha256, signing_key=key)
    if not hmac.compare_digest(authorization.signature_sha256, expected):
        raise ValueError("Substack authorization signature is invalid")
    if not hmac.compare_digest(authorization.owner_scope_sha256, owner_scope_sha256(owner_id)):
        raise ValueError("Substack authorization is unavailable")
    if not authorization.not_before_ms <= now_ms < authorization.expires_at_ms:
        raise ValueError("Substack authorization is not active")
    horizon = now_ms if required_until_ms is None else required_until_ms
    if horizon < now_ms or horizon >= authorization.expires_at_ms:
        raise ValueError("Substack authorization does not cover the required horizon")
    expected_bindings = (
        (collective_unit_id, authorization.collective_unit_id),
        (collective_preview_sha256, authorization.collective_preview_sha256),
        (ref_id, authorization.ref_id),
    )
    if any(
        expected_value is not None and expected_value != actual
        for expected_value, actual in expected_bindings
    ):
        raise ValueError("Substack authorization binding conflicts")


class SubstackExcerptReceipt(_Closed):
    """Content-addressed receipt for only the selected UTF-8 bytes."""

    schema_version: Literal[1] = 1
    receipt_id: str = Field(pattern=r"^suer_[0-9a-f]{24}$")
    authorization_id: str = Field(pattern=r"^sua_[0-9a-f]{24}$")
    authorization_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collective_unit_id: str = Field(pattern=r"^cunit_[0-9a-f]{24}$")
    collective_preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ref_id: str = Field(pattern=r"^sref_[0-9a-f]{16}$")
    canonical_url: str = Field(min_length=1, max_length=2_048)
    external_id: str = Field(min_length=1, max_length=1_024)
    canonicalization: Literal["utf8-plain-v1"]
    representation_evidence: Literal["owner_attestation_unverified"]
    source_representation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_representation_bytes: int = Field(ge=1, le=100_000_000)
    source_byte_start: int = Field(ge=0)
    source_byte_end: int = Field(gt=0)
    partial_excerpt_affirmed: Literal[True]
    text: str = Field(min_length=1, max_length=MAX_SUBSTACK_EXCERPT_BYTES)
    excerpt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    excerpt_bytes: int = Field(ge=1, le=MAX_SUBSTACK_EXCERPT_BYTES)
    content_class: Literal["personal_reading"]
    rights_tier: Literal["not_applicable"]
    rights_use: Literal["operator_authorized_excerpt"]
    injected_at_ms: int = Field(ge=0)
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _canonical_contract(self) -> SubstackExcerptReceipt:
        canonical_substack_post(self.canonical_url, self.external_id)
        try:
            encoded = self.text.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("Substack excerpt is not valid UTF-8") from exc
        if unicodedata.normalize("NFC", self.text) != self.text or "\r" in self.text:
            raise ValueError("Substack excerpt is not canonical UTF-8 plain text")
        if any(
            unicodedata.category(char).startswith("C") and char not in "\n\t" for char in self.text
        ):
            raise ValueError("Substack excerpt contains forbidden control text")
        if _MARKUP_RE.search(self.text):
            raise ValueError("Substack excerpt contains markup")
        if _MARKDOWN_IMAGE_RE.search(self.text):
            raise ValueError("Substack excerpt contains Markdown image syntax")
        if (
            self.excerpt_bytes != len(encoded)
            or self.excerpt_sha256 != hashlib.sha256(encoded).hexdigest()
        ):
            raise ValueError("Substack excerpt bytes conflict")
        if (
            self.source_byte_end <= self.source_byte_start
            or self.source_byte_end > self.source_representation_bytes
            or self.source_byte_end - self.source_byte_start != self.excerpt_bytes
            or (
                self.source_byte_start == 0
                and self.source_byte_end == self.source_representation_bytes
            )
        ):
            raise ValueError("Substack excerpt source range conflicts")
        expected_hash = substack_excerpt_receipt_sha256(self)
        if self.receipt_sha256 != expected_hash:
            raise ValueError("Substack excerpt receipt hash conflicts")
        if self.receipt_id != "suer_" + expected_hash[:24]:
            raise ValueError("Substack excerpt receipt id conflicts")
        return self


def substack_excerpt_receipt_sha256(
    receipt: SubstackExcerptReceipt | Mapping[str, object],
) -> str:
    raw = (
        receipt.model_dump(mode="json") if isinstance(receipt, SubstackExcerptReceipt) else receipt
    )
    return hashlib.sha256(
        _RECEIPT_DOMAIN
        + _canonical_material(raw, omitted=frozenset({"receipt_id", "receipt_sha256"}))
    ).hexdigest()


def create_substack_excerpt_receipt(
    authorization: SubstackUseAuthorization,
    *,
    verification_keys: Mapping[str, bytes],
    owner_id: str,
    now_ms: int,
    source_representation_sha256: str,
    source_representation_bytes: int,
    source_byte_start: int,
    text: str,
) -> SubstackExcerptReceipt:
    verify_substack_authorization(
        authorization,
        verification_keys=verification_keys,
        owner_id=owner_id,
        now_ms=now_ms,
    )
    encoded = text.encode("utf-8")
    if len(encoded) > authorization.max_excerpt_bytes:
        raise ValueError("Substack excerpt exceeds its authorization")
    excerpt_sha256 = hashlib.sha256(encoded).hexdigest()
    source_byte_end = source_byte_start + len(encoded)
    if (
        source_representation_sha256 != authorization.source_representation_sha256
        or source_representation_bytes != authorization.source_representation_bytes
        or source_byte_start != authorization.source_byte_start
        or source_byte_end != authorization.source_byte_end
        or excerpt_sha256 != authorization.excerpt_sha256
        or len(encoded) != authorization.excerpt_bytes
    ):
        raise ValueError("Substack excerpt conflicts with its signed commitment")
    material: dict[str, object] = {
        "schema_version": 1,
        "authorization_id": authorization.authorization_id,
        "authorization_sha256": authorization.authorization_sha256,
        "owner_scope_sha256": authorization.owner_scope_sha256,
        "collective_unit_id": authorization.collective_unit_id,
        "collective_preview_sha256": authorization.collective_preview_sha256,
        "ref_id": authorization.ref_id,
        "canonical_url": authorization.canonical_url,
        "external_id": authorization.external_id,
        "canonicalization": "utf8-plain-v1",
        "representation_evidence": "owner_attestation_unverified",
        "source_representation_sha256": source_representation_sha256,
        "source_representation_bytes": source_representation_bytes,
        "source_byte_start": source_byte_start,
        "source_byte_end": source_byte_end,
        "partial_excerpt_affirmed": True,
        "text": text,
        "excerpt_sha256": excerpt_sha256,
        "excerpt_bytes": len(encoded),
        "content_class": "personal_reading",
        "rights_tier": "not_applicable",
        "rights_use": "operator_authorized_excerpt",
        # Receipt identity must be reconstructible after a crash between the
        # authorization-row CAS and receipt projection.
        "injected_at_ms": authorization.not_before_ms,
    }
    digest = substack_excerpt_receipt_sha256(material)
    return SubstackExcerptReceipt.model_validate(
        {**material, "receipt_id": "suer_" + digest[:24], "receipt_sha256": digest}
    )


def store_substack_authorization(
    store: EngagementStore,
    *,
    owner_id: str,
    authorization: SubstackUseAuthorization,
    verification_keys: Mapping[str, bytes],
    now_ms: int,
) -> dict[str, object]:
    verify_substack_authorization(
        authorization,
        verification_keys=verification_keys,
        owner_id=owner_id,
        now_ms=now_ms,
    )
    logical_id = "suauth_" + authorization.authorization_id.removeprefix("sua_")

    def claim(current: dict[str, object] | None) -> dict[str, object]:
        if current is not None:
            stored = _authorization_from_row(
                current,
                authorization_id=authorization.authorization_id,
                authorization_sha256=authorization.authorization_sha256,
            )
            verify_substack_authorization(
                stored,
                verification_keys=verification_keys,
                owner_id=owner_id,
                now_ms=now_ms,
            )
            return current
        return {
            "document_type": "midnight_oil_substack_authorization",
            "authorization_sha256": authorization.authorization_sha256,
            "authorization": authorization.model_dump(mode="json"),
            "state": "active",
        }

    return store.mutate_owned_document(logical_id, owner_id, claim)


def revoke_substack_authorization(
    store: EngagementStore,
    *,
    owner_id: str,
    authorization_id: str,
    expected_authorization_sha256: str,
    clock_ms: Callable[[], int],
) -> dict[str, object]:
    _validate_stored_identity(
        authorization_id=authorization_id,
        authorization_sha256=expected_authorization_sha256,
    )
    revoked_at_ms = clock_ms()
    _validate_time(revoked_at_ms, field="revoked_at_ms")
    logical_id = "suauth_" + authorization_id.removeprefix("sua_")

    def revoke(current: dict[str, object] | None) -> dict[str, object]:
        if current is None:
            raise ValueError("Substack authorization is unavailable")
        authorization = _authorization_from_row(
            current,
            authorization_id=authorization_id,
            authorization_sha256=expected_authorization_sha256,
        )
        if current.get("state") == "revoked":
            return current
        if revoked_at_ms < authorization.issued_at_ms:
            raise ValueError("Substack revocation time is invalid")
        if current.get("state") != "active":
            raise ValueError("Substack authorization state requires reconciliation")
        return {**current, "state": "revoked", "revoked_at_ms": revoked_at_ms}

    return store.mutate_owned_document(logical_id, owner_id, revoke)


def require_active_stored_substack_authorization(
    store: EngagementStore,
    *,
    owner_id: str,
    authorization_id: str,
    expected_authorization_sha256: str,
    verification_keys: Mapping[str, bytes],
    now_ms: int,
) -> SubstackUseAuthorization:
    _validate_stored_identity(
        authorization_id=authorization_id,
        authorization_sha256=expected_authorization_sha256,
    )
    logical_id = "suauth_" + authorization_id.removeprefix("sua_")
    row = store.get_owned_document(logical_id, owner_id)
    if (
        row is None
        or row.get("state") != "active"
        or row.get("authorization_sha256") != expected_authorization_sha256
    ):
        raise ValueError("Substack authorization is unavailable")
    authorization = _authorization_from_row(
        row,
        authorization_id=authorization_id,
        authorization_sha256=expected_authorization_sha256,
    )
    verify_substack_authorization(
        authorization,
        verification_keys=verification_keys,
        owner_id=owner_id,
        now_ms=now_ms,
    )
    return authorization


def require_active_stored_substack_excerpt(
    store: EngagementStore,
    *,
    owner_id: str,
    authorization_id: str,
    expected_authorization_sha256: str,
    receipt_id: str,
    expected_receipt_sha256: str,
    verification_keys: Mapping[str, bytes],
    now_ms: int,
) -> tuple[SubstackUseAuthorization, SubstackExcerptReceipt]:
    """Recheck live use authority and exact local bytes as one reader boundary."""
    authorization = require_active_stored_substack_authorization(
        store,
        owner_id=owner_id,
        authorization_id=authorization_id,
        expected_authorization_sha256=expected_authorization_sha256,
        verification_keys=verification_keys,
        now_ms=now_ms,
    )
    if (
        _RECEIPT_ID_RE.fullmatch(receipt_id) is None
        or _SHA256_RE.fullmatch(expected_receipt_sha256) is None
    ):
        raise ValueError("Substack excerpt receipt identity is invalid")
    authorization_logical_id = "suauth_" + authorization_id.removeprefix("sua_")
    logical_id = "suexcerpt_" + receipt_id.removeprefix("suer_")
    row = store.get_owned_document(logical_id, owner_id)
    if row is None or row.get("receipt_sha256") != expected_receipt_sha256:
        raise ValueError("Substack excerpt receipt is unavailable")
    receipt = _receipt_from_row(row, receipt_id=receipt_id, receipt_sha256=expected_receipt_sha256)
    if (
        not hmac.compare_digest(receipt.authorization_sha256, authorization.authorization_sha256)
        or receipt.authorization_id != authorization.authorization_id
        or receipt.owner_scope_sha256 != authorization.owner_scope_sha256
        or receipt.collective_unit_id != authorization.collective_unit_id
        or receipt.collective_preview_sha256 != authorization.collective_preview_sha256
        or receipt.ref_id != authorization.ref_id
        or receipt.canonical_url != authorization.canonical_url
        or receipt.external_id != authorization.external_id
        or receipt.source_representation_sha256 != authorization.source_representation_sha256
        or receipt.source_representation_bytes != authorization.source_representation_bytes
        or receipt.source_byte_start != authorization.source_byte_start
        or receipt.source_byte_end != authorization.source_byte_end
        or receipt.excerpt_sha256 != authorization.excerpt_sha256
        or receipt.excerpt_bytes != authorization.excerpt_bytes
        or receipt.injected_at_ms != authorization.not_before_ms
    ):
        raise ValueError("Substack excerpt receipt binding conflicts")

    def final_live_barrier(current: dict[str, object] | None) -> dict[str, object]:
        if (
            current is None
            or current.get("state") != "active"
            or current.get("claimed_receipt_id") != receipt_id
            or current.get("claimed_receipt_sha256") != expected_receipt_sha256
        ):
            raise ValueError("Substack authorization is unavailable")
        stored = _authorization_from_row(
            current,
            authorization_id=authorization_id,
            authorization_sha256=expected_authorization_sha256,
        )
        verify_substack_authorization(
            stored,
            verification_keys=verification_keys,
            owner_id=owner_id,
            now_ms=now_ms,
        )
        return current

    store.mutate_owned_document(authorization_logical_id, owner_id, final_live_barrier)
    return authorization, receipt


def _validate_stored_identity(*, authorization_id: str, authorization_sha256: str) -> None:
    if (
        _AUTHORIZATION_ID_RE.fullmatch(authorization_id) is None
        or _SHA256_RE.fullmatch(authorization_sha256) is None
    ):
        raise ValueError("Substack authorization identity is invalid")


def _validate_time(value: int, *, field: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"Substack {field} is invalid")


def _authorization_from_row(
    row: Mapping[str, object], *, authorization_id: str, authorization_sha256: str
) -> SubstackUseAuthorization:
    if (
        row.get("document_type") != "midnight_oil_substack_authorization"
        or row.get("authorization_sha256") != authorization_sha256
    ):
        raise ValueError("Substack authorization is unavailable")
    authorization = SubstackUseAuthorization.model_validate(row.get("authorization"))
    if authorization.authorization_id != authorization_id or not hmac.compare_digest(
        authorization.authorization_sha256, authorization_sha256
    ):
        raise ValueError("Substack authorization durable binding conflicts")
    return authorization


def _receipt_from_row(
    row: Mapping[str, object], *, receipt_id: str, receipt_sha256: str
) -> SubstackExcerptReceipt:
    if (
        row.get("document_type") != "midnight_oil_substack_excerpt_receipt"
        or row.get("receipt_sha256") != receipt_sha256
    ):
        raise ValueError("Substack excerpt receipt is unavailable")
    receipt = SubstackExcerptReceipt.model_validate(row.get("receipt"))
    if receipt.receipt_id != receipt_id or not hmac.compare_digest(
        receipt.receipt_sha256, receipt_sha256
    ):
        raise ValueError("Substack excerpt receipt durable binding conflicts")
    return receipt


def store_substack_excerpt_receipt(
    store: EngagementStore,
    *,
    owner_id: str,
    receipt: SubstackExcerptReceipt,
    authorization_id: str,
    verification_keys: Mapping[str, bytes],
    now_ms: int,
) -> dict[str, object]:
    authorization = require_active_stored_substack_authorization(
        store,
        owner_id=owner_id,
        authorization_id=authorization_id,
        expected_authorization_sha256=receipt.authorization_sha256,
        verification_keys=verification_keys,
        now_ms=now_ms,
    )
    if (
        receipt.authorization_id != authorization.authorization_id
        or receipt.owner_scope_sha256 != authorization.owner_scope_sha256
        or receipt.collective_unit_id != authorization.collective_unit_id
        or receipt.collective_preview_sha256 != authorization.collective_preview_sha256
        or receipt.ref_id != authorization.ref_id
        or receipt.canonical_url != authorization.canonical_url
        or receipt.external_id != authorization.external_id
        or receipt.source_representation_sha256 != authorization.source_representation_sha256
        or receipt.source_representation_bytes != authorization.source_representation_bytes
        or receipt.source_byte_start != authorization.source_byte_start
        or receipt.source_byte_end != authorization.source_byte_end
        or receipt.excerpt_sha256 != authorization.excerpt_sha256
        or receipt.excerpt_bytes != authorization.excerpt_bytes
        or receipt.injected_at_ms != authorization.not_before_ms
    ):
        raise ValueError("Substack excerpt receipt binding conflicts")
    authorization_logical_id = "suauth_" + authorization_id.removeprefix("sua_")

    def claim_one_receipt(current: dict[str, object] | None) -> dict[str, object]:
        if current is None or current.get("state") != "active":
            raise ValueError("Substack authorization is unavailable")
        stored = _authorization_from_row(
            current,
            authorization_id=authorization_id,
            authorization_sha256=authorization.authorization_sha256,
        )
        verify_substack_authorization(
            stored,
            verification_keys=verification_keys,
            owner_id=owner_id,
            now_ms=now_ms,
        )
        claimed = (
            current.get("claimed_receipt_id"),
            current.get("claimed_receipt_sha256"),
        )
        requested = (receipt.receipt_id, receipt.receipt_sha256)
        if claimed == (None, None):
            return {
                **current,
                "claimed_receipt_id": receipt.receipt_id,
                "claimed_receipt_sha256": receipt.receipt_sha256,
            }
        if claimed != requested:
            raise ValueError("Substack authorization already claimed a different excerpt receipt")
        return current

    store.mutate_owned_document(authorization_logical_id, owner_id, claim_one_receipt)
    logical_id = "suexcerpt_" + receipt.receipt_id.removeprefix("suer_")

    def claim(current: dict[str, object] | None) -> dict[str, object]:
        if current is not None:
            _receipt_from_row(
                current,
                receipt_id=receipt.receipt_id,
                receipt_sha256=receipt.receipt_sha256,
            )
            return current
        return {
            "document_type": "midnight_oil_substack_excerpt_receipt",
            "receipt_sha256": receipt.receipt_sha256,
            "receipt": receipt.model_dump(mode="json"),
        }

    return store.mutate_owned_document(logical_id, owner_id, claim)


__all__ = [
    "MAX_SUBSTACK_AUTHORIZATION_LIFETIME_MS",
    "MAX_SUBSTACK_AUTHORIZATION_JSON_BYTES",
    "MAX_SUBSTACK_EXCERPT_BYTES",
    "SUBSTACK_PROVIDER_CONSTRAINTS_SHA256",
    "SUBSTACK_PRIVATE_USE_POLICY_SHA256",
    "SubstackExcerptReceipt",
    "SubstackUseAuthorization",
    "canonical_substack_post",
    "create_substack_excerpt_receipt",
    "owner_scope_sha256",
    "parse_substack_authorization_json",
    "require_active_stored_substack_authorization",
    "require_active_stored_substack_excerpt",
    "revoke_substack_authorization",
    "signed_substack_authorization",
    "store_substack_authorization",
    "store_substack_excerpt_receipt",
    "substack_authorization_sha256",
    "substack_authorization_signature",
    "substack_excerpt_receipt_sha256",
    "verify_substack_authorization",
]
