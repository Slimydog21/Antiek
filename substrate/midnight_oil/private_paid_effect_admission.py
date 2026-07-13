"""Fixture-only private paid-effect admission boundary.

This module is deliberately transport-free. It stores only a synthetic signed
authority pair, inert exposure markers, and encrypted fixture admission
evidence. It is not production paid-call authority.
"""

from __future__ import annotations

import ast
import hashlib
import hmac
import inspect
import json
import os
import re
import secrets
import sqlite3
import stat
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager, closing, suppress
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Protocol, cast

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_I63 = 2**63 - 1
MAX_CENTS = 1_000_000_000
MAX_MARKERS = 1_024
MAX_ADMISSIONS = 1_024
MAX_OPEN_MARKERS = 64
MARKER_TTL_MS = 300_000
MAX_PAIR_DOCUMENT_BYTES = 65_536
MAX_ADMISSION_PLAINTEXT_BYTES = 1_048_576
MAX_ADMISSION_CIPHERTEXT_BYTES = 1_048_592
MAX_DB_PAGES = 65_536
NONCE_COLLISION_RETRIES = 8
MAX_FIXTURE_VERIFICATION_KEYS = 16

_PAIR_DOMAIN = b"antiek.midnight-oil.private-paid-effect-fixture-pair.v1\x00"
_PAIR_SIGNATURE_DOMAIN = b"antiek.midnight-oil.private-paid-effect-fixture-signature.v1\x00"
_AEAD_DOMAIN = b"antiek.midnight-oil.private-paid-effect-fixture-aead.v1\x00"
_SOURCE_DOMAIN = b"antiek.midnight-oil.private-paid-effect-admission-semantic-source.v1\x00"

_HEX64 = re.compile(r"[0-9a-f]{64}")
_OWNER_PATH = re.compile(r"opspd1_[0-9a-f]{64}")
_REGISTRY_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")
_KEY_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")
_SAFE_ASSERTION_ID = re.compile(r"[A-Za-z0-9._:@/-]{1,128}")
_PRINTABLE_NON_WS = re.compile(r"[!-~]{1,256}")
_STORE_ID = re.compile(r"mopstore1_[0-9a-f]{64}")
_EFFECT_ID = re.compile(r"mopeffect1_[0-9a-f]{64}")
_HOLD_ID = re.compile(r"mophold1_[0-9a-f]{64}")
_ADMISSION_ID = re.compile(r"moadmit1_[0-9a-f]{64}")
_KEY_VERSION = re.compile(r"moakv1_[A-Za-z0-9._-]{1,64}")
_SOURCE_SELECTOR = re.compile(r"opsbs1_[0-9a-f]{64}")

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS private_paid_effect_fixture_schema (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    store_id TEXT NOT NULL
)
"""
_AUTHORITY_DDL = """
CREATE TABLE IF NOT EXISTS private_paid_effect_fixture_authority_current (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    owner_path_discriminator TEXT NOT NULL,
    revision INTEGER NOT NULL,
    capability_registry_id TEXT NOT NULL,
    capability_head_sha256 TEXT NOT NULL,
    capability_epoch INTEGER NOT NULL,
    source_registry_id TEXT NOT NULL,
    source_head_sha256 TEXT NOT NULL,
    source_epoch INTEGER NOT NULL,
    pair_sha256 TEXT NOT NULL,
    issued_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    document_json TEXT NOT NULL
)
"""
_MARKERS_DDL = """
CREATE TABLE IF NOT EXISTS private_paid_effect_fixture_exposure_markers (
    logical_effect_key TEXT PRIMARY KEY,
    hold_id TEXT NOT NULL UNIQUE,
    owner_path_discriminator TEXT NOT NULL,
    projected_max_cents INTEGER NOT NULL CHECK (
        projected_max_cents >= 1 AND projected_max_cents <= 1000000000
    ),
    exposure_state TEXT NOT NULL CHECK (exposure_state IN ('open','released')),
    created_at_ms INTEGER NOT NULL,
    released_at_ms INTEGER,
    CHECK (
        (exposure_state = 'open' AND released_at_ms IS NULL)
        OR (exposure_state = 'released' AND released_at_ms IS NOT NULL
            AND released_at_ms >= created_at_ms)
    ),
    UNIQUE (logical_effect_key, hold_id)
)
"""
_ADMISSIONS_DDL = """
CREATE TABLE IF NOT EXISTS private_paid_effect_fixture_admissions (
    admission_id TEXT PRIMARY KEY,
    logical_effect_key TEXT NOT NULL UNIQUE,
    hold_id TEXT NOT NULL UNIQUE,
    owner_path_discriminator TEXT NOT NULL,
    fixture_pair_sha256 TEXT NOT NULL,
    authority_revision INTEGER NOT NULL,
    projected_max_cents INTEGER NOT NULL CHECK (
        projected_max_cents >= 1 AND projected_max_cents <= 1000000000
    ),
    categorical_state TEXT NOT NULL CHECK (categorical_state = 'admission_committed'),
    created_at_ms INTEGER NOT NULL,
    aead_suite TEXT NOT NULL CHECK (aead_suite = 'aes-256-gcm'),
    key_version TEXT NOT NULL,
    nonce_length INTEGER NOT NULL CHECK (nonce_length = 12),
    nonce BLOB NOT NULL CHECK (length(nonce) = 12),
    ciphertext_schema TEXT NOT NULL
        CHECK (ciphertext_schema = 'private_paid_effect_admission_fixture_v1_json'),
    ciphertext_type TEXT NOT NULL CHECK (ciphertext_type = 'application/json'),
    ciphertext_length INTEGER NOT NULL
        CHECK (ciphertext_length >= 16 AND ciphertext_length <= 1048592),
    ciphertext BLOB NOT NULL,
    CHECK (ciphertext_length = length(ciphertext)),
    UNIQUE (logical_effect_key, hold_id),
    UNIQUE (owner_path_discriminator, key_version, nonce),
    FOREIGN KEY (logical_effect_key, hold_id)
        REFERENCES private_paid_effect_fixture_exposure_markers(logical_effect_key, hold_id)
)
"""
_EXPECTED_TABLES = {
    "private_paid_effect_fixture_schema",
    "private_paid_effect_fixture_authority_current",
    "private_paid_effect_fixture_exposure_markers",
    "private_paid_effect_fixture_admissions",
}

_ADMISSION_ROW_SELECT = (
    "SELECT a.admission_id,a.logical_effect_key,a.hold_id,a.owner_path_discriminator,"
    "a.fixture_pair_sha256,a.authority_revision,a.projected_max_cents,a.categorical_state,"
    "a.created_at_ms,a.aead_suite,a.key_version,a.nonce_length,a.nonce,"
    "a.ciphertext_schema,a.ciphertext_type,a.ciphertext_length,a.ciphertext,"
    "m.logical_effect_key,m.hold_id,m.owner_path_discriminator,m.projected_max_cents,"
    "m.exposure_state,m.created_at_ms,m.released_at_ms "
    "FROM private_paid_effect_fixture_admissions a "
    "JOIN private_paid_effect_fixture_exposure_markers m "
    "ON m.logical_effect_key=a.logical_effect_key AND m.hold_id=a.hold_id "
)


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)

    def __repr_args__(self) -> list[tuple[str | None, object]]:
        return [("redacted", True)]


class PrivatePaidEffectAdmissionFixtureRejected(ValueError):
    def __init__(self) -> None:
        super().__init__("private paid-effect admission fixture rejected")

    def __repr__(self) -> str:
        return "PrivatePaidEffectAdmissionFixtureRejected()"


class SignedFixtureAuthorityPairV1(_Closed):
    schema_version: Literal[1] = 1
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    revision: int = Field(ge=0, le=MAX_I63)
    previous_pair_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    issued_at_ms: int = Field(ge=0, le=MAX_I63)
    capability_registry_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    capability_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_epoch: int = Field(ge=0, le=MAX_I63)
    source_registry_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    source_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_epoch: int = Field(ge=0, le=MAX_I63)
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    issuer_role: Literal["private_paid_effect_fixture_authority_issuer"] = (
        "private_paid_effect_fixture_authority_issuer"
    )
    key_purpose: Literal["private_paid_effect_fixture_authority_v1"] = (
        "private_paid_effect_fixture_authority_v1"
    )
    signature_scheme: Literal["ed25519"] = "ed25519"
    pair_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature_ed25519: str = Field(pattern=r"^[0-9a-f]{128}$")
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False
    fixture_authority_only: Literal[True] = True
    live_authority_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> SignedFixtureAuthorityPairV1:
        if (
            self.pair_sha256 != signed_fixture_authority_pair_v1_sha256(self)
            or (self.revision == 0) != (self.previous_pair_sha256 == "0" * 64)
            or (self.revision == 0 and (self.capability_epoch != 0 or self.source_epoch != 0))
        ):
            raise ValueError("fixture authority pair conflicts")
        return self


class FixtureSourceReceiptPairV1(_Closed):
    receipt_id: str = Field(pattern=r"^opsr5_[0-9a-f]{24}$")
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class FixtureAdmissionCandidateV1(_Closed):
    schema_version: Literal[1] = 1
    owner_path_discriminator: str = Field(pattern=r"^opspd1_[0-9a-f]{64}$")
    logical_effect_key: str = Field(pattern=r"^mopeffect1_[0-9a-f]{64}$")
    hold_id: str = Field(pattern=r"^mophold1_[0-9a-f]{64}$")
    projected_max_cents: int = Field(ge=1, le=MAX_CENTS)
    authority_revision: int = Field(ge=0, le=MAX_I63)
    fixture_pair_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_registry_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    capability_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_epoch: int = Field(ge=0, le=MAX_I63)
    source_registry_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    source_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_epoch: int = Field(ge=0, le=MAX_I63)
    operation_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    job_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    execution_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    stage_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    queue_operation_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    queue_cursor: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    worker_id: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    provider: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    model: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    route: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    account_scope: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    project_scope: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    api_mode: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    processing_region: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    output_schema: str = Field(pattern=r"^[A-Za-z0-9._:@/-]{1,128}$")
    router_role: Literal["planner", "gatherer", "verifier", "synthesizer"]
    consent_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    consent_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_v4_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_v4_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    core_v4_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_v7_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    envelope_v4_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_material_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner_job_state_version: int = Field(ge=0, le=MAX_I63)
    lease_generation: int = Field(ge=0, le=MAX_I63)
    lease_exclusive_until_ms: int = Field(ge=0, le=MAX_I63)
    source_revision: int = Field(ge=0, le=MAX_I63)
    approved_ceiling_cents: int = Field(ge=1, le=MAX_CENTS)
    source_selector: str = Field(pattern=r"^opsbs1_[0-9a-f]{64}$")
    source_receipt_pairs: tuple[FixtureSourceReceiptPairV1, ...] = Field(max_length=8)
    provider_scoped_idempotency_key: str = Field(pattern=r"^[!-~]{1,256}$")
    maximum_output_bytes: int = Field(ge=1, le=67_108_864)
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False
    fixture_authority_only: Literal[True] = True
    live_authority_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False

    @model_validator(mode="after")
    def _exact_members(self) -> FixtureAdmissionCandidateV1:
        if any(type(row) is not FixtureSourceReceiptPairV1 for row in self.source_receipt_pairs):
            raise ValueError("fixture source receipt pair conflicts")
        if (self.router_role == "planner") != (len(self.source_receipt_pairs) == 0):
            raise ValueError("fixture router receipt cardinality conflicts")
        return self


class _AdmissionPlaintextV1(_Closed):
    schema_version: Literal[1] = 1
    admitted_at_ms: int = Field(ge=0, le=MAX_I63)
    candidate: FixtureAdmissionCandidateV1


class _AuthenticatedAdmissionV1(_Closed):
    admission_id: str = Field(pattern=r"^moadmit1_[0-9a-f]{64}$")
    candidate: FixtureAdmissionCandidateV1
    created_at_ms: int = Field(ge=0, le=MAX_I63)
    exposure_state: Literal["open", "released"]
    released_at_ms: int | None = Field(default=None, ge=0, le=MAX_I63)


class FixtureAuthorityPairResultV1(_Closed):
    applied: bool
    pair_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    revision: int = Field(ge=0, le=MAX_I63)
    capability_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False
    fixture_authority_only: Literal[True] = True
    live_authority_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False


class FixtureExposureMarkerV1(_Closed):
    logical_effect_key: str = Field(pattern=r"^mopeffect1_[0-9a-f]{64}$")
    hold_id: str = Field(pattern=r"^mophold1_[0-9a-f]{64}$")
    projected_max_cents: int = Field(ge=1, le=MAX_CENTS)
    exposure_state: Literal["open"] = "open"
    created_at_ms: int = Field(ge=0, le=MAX_I63)
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False
    fixture_authority_only: Literal[True] = True
    live_authority_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False


class PrivatePaidEffectAdmissionFixtureEvidenceV1(_Closed):
    replayed: bool
    admission_id: str = Field(pattern=r"^moadmit1_[0-9a-f]{64}$")
    logical_effect_key: str = Field(pattern=r"^mopeffect1_[0-9a-f]{64}$")
    hold_id: str = Field(pattern=r"^mophold1_[0-9a-f]{64}$")
    historical_fixture_pair_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    historical_authority_revision: int = Field(ge=0, le=MAX_I63)
    created_at_ms: int = Field(ge=0, le=MAX_I63)
    exposure_state: Literal["open", "released"]
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False
    fixture_authority_only: Literal[True] = True
    live_authority_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False


class FixtureExposureReleaseV1(_Closed):
    applied: bool
    admission_id: str = Field(pattern=r"^moadmit1_[0-9a-f]{64}$")
    logical_effect_key: str = Field(pattern=r"^mopeffect1_[0-9a-f]{64}$")
    hold_id: str = Field(pattern=r"^mophold1_[0-9a-f]{64}$")
    exposure_state: Literal["released"] = "released"
    released_at_ms: int = Field(ge=0, le=MAX_I63)
    confers_execution_authority: Literal[False] = False
    confers_checkpoint_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False
    fixture_authority_only: Literal[True] = True
    live_authority_verified: Literal[False] = False
    user_accounting_effect: Literal[False] = False
    transport_reachable: Literal[False] = False


class PrivatePaidEffectAdmissionFixtureKeyProviderV1(Protocol):
    def open_aes256gcm_key(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        store_id: str,
        key_version: str,
    ) -> AbstractContextManager[bytearray]: ...


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _canonical_model_json(model: BaseModel) -> bytes:
    return _canonical_json(model.model_dump(mode="json"))


def _material(value: BaseModel | Mapping[str, object], omitted: frozenset[str]) -> bytes:
    raw = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    return _canonical_json({key: item for key, item in raw.items() if key not in omitted})


def signed_fixture_authority_pair_v1_sha256(
    pair: SignedFixtureAuthorityPairV1 | Mapping[str, object],
) -> str:
    return hashlib.sha256(
        _PAIR_DOMAIN + _material(pair, frozenset({"pair_sha256", "signature_ed25519"}))
    ).hexdigest()


def _reject_duplicates(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def parse_signed_fixture_authority_pair_v1_json(value: bytes) -> SignedFixtureAuthorityPairV1:
    try:
        if type(value) is not bytes or not value or len(value) > MAX_PAIR_DOCUMENT_BYTES:
            raise ValueError
        json.loads(value.decode("utf-8"), object_pairs_hook=_reject_duplicates)
        pair = SignedFixtureAuthorityPairV1.model_validate_json(value)
        if not hmac.compare_digest(_canonical_model_json(pair), value):
            raise ValueError
        return pair
    except Exception:
        raise PrivatePaidEffectAdmissionFixtureRejected() from None


def verify_signed_fixture_authority_pair_v1(
    pair: SignedFixtureAuthorityPairV1, *, verification_keys: Mapping[str, bytes]
) -> None:
    try:
        if type(pair) is not SignedFixtureAuthorityPairV1:
            raise ValueError
        canonical = SignedFixtureAuthorityPairV1.model_validate(pair.model_dump(mode="python"))
        if canonical != pair:
            raise ValueError
        keys = _copy_keyring(verification_keys)
        key = keys.get(pair.key_id)
        if key is None:
            raise ValueError
        Ed25519PublicKey.from_public_bytes(key).verify(
            bytes.fromhex(pair.signature_ed25519),
            _PAIR_SIGNATURE_DOMAIN + bytes.fromhex(pair.pair_sha256),
        )
    except Exception:
        raise PrivatePaidEffectAdmissionFixtureRejected() from None


def _copy_keyring(value: Mapping[str, bytes]) -> dict[str, bytes]:
    copied: dict[str, bytes] = {}
    try:
        for index, (key_id, key) in enumerate(value.items()):
            if (
                index >= MAX_FIXTURE_VERIFICATION_KEYS
                or type(key_id) is not str
                or _KEY_ID.fullmatch(key_id) is None
                or type(key) is not bytes
                or len(key) != 32
                or key_id in copied
                or key in copied.values()
            ):
                raise ValueError
            copied[key_id] = bytes(key)
    except Exception:
        raise PrivatePaidEffectAdmissionFixtureRejected() from None
    return copied


def _valid_i63(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool) and 0 <= value <= MAX_I63


def _require_admission_size_bounds(plaintext_length: int, ciphertext_length: int) -> None:
    if (
        type(plaintext_length) is not int
        or isinstance(plaintext_length, bool)
        or type(ciphertext_length) is not int
        or isinstance(ciphertext_length, bool)
        or not 1 <= plaintext_length <= MAX_ADMISSION_PLAINTEXT_BYTES
        or ciphertext_length != plaintext_length + 16
        or not 17 <= ciphertext_length <= MAX_ADMISSION_CIPHERTEXT_BYTES
    ):
        raise ValueError


def _compact_sql(value: str) -> str:
    compact: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(value):
        character = value[index]
        if quote is not None:
            compact.append(character)
            if character == quote:
                if index + 1 < len(value) and value[index + 1] == quote:
                    compact.append(value[index + 1])
                    index += 1
                else:
                    quote = None
        elif character in {"'", '"'}:
            quote = character
            compact.append(character)
        elif not character.isspace():
            compact.append(character.lower())
        index += 1
    return "".join(compact).replace("ifnotexists", "")


def _aad(metadata: Mapping[str, object]) -> bytes:
    return _AEAD_DOMAIN + _canonical_json(dict(metadata))


def _admission_metadata(
    *,
    store_id: str,
    owner_path_discriminator: str,
    logical_effect_key: str,
    hold_id: str,
    admission_id: str,
    authority_revision: int,
    fixture_pair_sha256: str,
    projected_max_cents: int,
    created_at_ms: int,
    key_version: str,
    ciphertext_length: int,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "store_id": store_id,
        "owner_path_discriminator": owner_path_discriminator,
        "logical_effect_key": logical_effect_key,
        "hold_id": hold_id,
        "admission_id": admission_id,
        "authority_revision": authority_revision,
        "fixture_pair_sha256": fixture_pair_sha256,
        "projected_max_cents": projected_max_cents,
        "categorical_state": "admission_committed",
        "created_at_ms": created_at_ms,
        "aead_suite": "aes-256-gcm",
        "key_version": key_version,
        "nonce_length": 12,
        "ciphertext_schema": "private_paid_effect_admission_fixture_v1_json",
        "ciphertext_type": "application/json",
        "ciphertext_length": ciphertext_length,
    }


class PrivatePaidEffectAdmissionFixtureStoreV1:
    """One-owner, fixture-only admission store with no transport authority."""

    __slots__ = (
        "_key_provider",
        "_keyring",
        "_owner_path_authority",
        "_sealed",
        "key_version",
        "owner_path_discriminator",
        "path",
        "store_id",
    )

    def __init__(
        self,
        path: str | Path,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        store_id: str,
        key_version: str,
        fixture_authority_verification_keys: Mapping[str, bytes],
        key_provider: PrivatePaidEffectAdmissionFixtureKeyProviderV1,
    ) -> None:
        object.__setattr__(self, "_sealed", False)
        try:
            if (
                type(owner_path_discriminator) is not str
                or _OWNER_PATH.fullmatch(owner_path_discriminator) is None
                or type(key_version) is not str
                or _KEY_VERSION.fullmatch(key_version) is None
            ):
                raise ValueError
            if type(store_id) is not str or _STORE_ID.fullmatch(store_id) is None:
                raise ValueError
            self.owner_path_discriminator = owner_path_discriminator
            self.store_id = store_id
            self.key_version = key_version
            self._owner_path_authority = owner_path_authority
            self._key_provider = key_provider
            self._keyring = MappingProxyType(_copy_keyring(fixture_authority_verification_keys))
            self._configure_path(path)
            self._initialize_schema()
            object.__setattr__(self, "_sealed", True)
        except Exception:
            raise PrivatePaidEffectAdmissionFixtureRejected() from None

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("private paid-effect fixture store is immutable")
        object.__setattr__(self, name, value)

    def _configure_path(self, path: str | Path) -> None:
        if type(path) not in {str, type(Path())}:
            raise ValueError
        raw = os.fspath(path)
        if not raw.strip() or raw == ":memory:":
            raise ValueError
        supplied = Path(raw).absolute()
        self._reject_symlinked_ancestors(supplied)
        canonical = supplied.resolve(strict=False)
        canonical.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._validate_secure_durable_path(canonical, require_exists=False)
        self.path = canonical

    @staticmethod
    def _reject_symlinked_ancestors(path: Path) -> None:
        for component in (path, *path.parents):
            if component.is_symlink():
                raise ValueError

    @classmethod
    def _validate_secure_durable_path(cls, path: Path, *, require_exists: bool) -> None:
        cls._reject_symlinked_ancestors(path)
        uid = os.getuid()
        parent_stat = path.parent.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(parent_stat.st_mode)
            or parent_stat.st_uid != uid
            or stat.S_IMODE(parent_stat.st_mode) != 0o700
        ):
            raise ValueError
        if not path.exists():
            if require_exists:
                raise ValueError
            return
        file_stat = path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_uid != uid
            or stat.S_IMODE(file_stat.st_mode) != 0o600
            or file_stat.st_nlink != 1
        ):
            raise ValueError

    def _connect(self, *, validate_schema: bool = True) -> sqlite3.Connection:
        self._validate_path(require_exists=validate_schema)
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")
            connection.execute("PRAGMA temp_store=MEMORY")
            connection.execute("PRAGMA page_size=4096")
            connection.execute(f"PRAGMA max_page_count={MAX_DB_PAGES}")
            self._chmod_sidecars()
            if validate_schema:
                self._validate_schema(connection)
                self._require_current_authority_valid_if_present(connection)
            return connection
        except Exception:
            connection.close()
            raise

    def _validate_path(self, *, require_exists: bool) -> None:
        self._validate_secure_durable_path(self.path, require_exists=require_exists)

    def _chmod_sidecars(self) -> None:
        self._chmod_sidecars_for(self.path)

    @staticmethod
    def _chmod_sidecars_for(path: Path) -> None:
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(path) + suffix)
            if sidecar.exists():
                os.chmod(sidecar, 0o600)

    def _initialize_schema(self) -> None:
        existing = self.path.exists() and self.path.stat().st_size > 0
        with closing(self._connect(validate_schema=False)) as connection:
            if existing:
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                }
                if tables != _EXPECTED_TABLES:
                    raise ValueError
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(_SCHEMA_DDL)
                connection.execute(_AUTHORITY_DDL)
                connection.execute(_MARKERS_DDL)
                connection.execute(_ADMISSIONS_DDL)
                row = connection.execute(
                    "SELECT store_id FROM private_paid_effect_fixture_schema WHERE singleton=1"
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO private_paid_effect_fixture_schema "
                        "(singleton,schema_version,store_id) VALUES (1,1,?)",
                        (self.store_id,),
                    )
                elif row != (self.store_id,):
                    raise ValueError
                self._validate_schema(connection)
                self._require_current_authority_valid_if_present(connection)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        os.chmod(self.path, 0o600)
        self._chmod_sidecars()

    def _validate_schema(self, connection: sqlite3.Connection) -> None:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        extra = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('view','trigger')"
        ).fetchone()
        extra_indexes = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name NOT LIKE 'sqlite_autoindex_%'"
        ).fetchall()
        schema = connection.execute(
            "SELECT singleton,schema_version,store_id FROM private_paid_effect_fixture_schema"
        ).fetchall()
        if (
            tables != _EXPECTED_TABLES
            or extra != (0,)
            or extra_indexes
            or schema != [(1, 1, self.store_id)]
        ):
            raise ValueError
        expected_sql = {
            "private_paid_effect_fixture_schema": _SCHEMA_DDL,
            "private_paid_effect_fixture_authority_current": _AUTHORITY_DDL,
            "private_paid_effect_fixture_exposure_markers": _MARKERS_DDL,
            "private_paid_effect_fixture_admissions": _ADMISSIONS_DDL,
        }
        for table, ddl in expected_sql.items():
            stored = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if stored is None or _compact_sql(str(stored[0])) != _compact_sql(ddl):
                raise ValueError
        expected_unique = {
            "private_paid_effect_fixture_exposure_markers": {
                ("logical_effect_key",),
                ("hold_id",),
                ("logical_effect_key", "hold_id"),
            },
            "private_paid_effect_fixture_admissions": {
                ("admission_id",),
                ("logical_effect_key",),
                ("hold_id",),
                ("logical_effect_key", "hold_id"),
                ("owner_path_discriminator", "key_version", "nonce"),
            },
        }
        for table, expected in expected_unique.items():
            actual = {
                tuple(
                    str(column[2])
                    for column in connection.execute(
                        f"PRAGMA index_info('{str(index[1])}')"
                    ).fetchall()
                )
                for index in connection.execute(f"PRAGMA index_list('{table}')").fetchall()
                if int(index[2]) == 1
            }
            if actual != expected:
                raise ValueError
        fk = connection.execute(
            "PRAGMA foreign_key_list('private_paid_effect_fixture_admissions')"
        ).fetchall()
        if len(fk) != 2 or {(str(row[2]), str(row[3]), str(row[4])) for row in fk} != {
            (
                "private_paid_effect_fixture_exposure_markers",
                "logical_effect_key",
                "logical_effect_key",
            ),
            ("private_paid_effect_fixture_exposure_markers", "hold_id", "hold_id"),
        }:
            raise ValueError
        settings = {
            "busy_timeout": int(connection.execute("PRAGMA busy_timeout").fetchone()[0]),
            "foreign_keys": int(connection.execute("PRAGMA foreign_keys").fetchone()[0]),
            "journal_mode_wal": int(
                str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"
            ),
            "page_size": int(connection.execute("PRAGMA page_size").fetchone()[0]),
            "max_page_count": int(connection.execute("PRAGMA max_page_count").fetchone()[0]),
            "synchronous": int(connection.execute("PRAGMA synchronous").fetchone()[0]),
            "temp_store": int(connection.execute("PRAGMA temp_store").fetchone()[0]),
        }
        if settings != {
            "busy_timeout": 30_000,
            "foreign_keys": 1,
            "journal_mode_wal": 1,
            "page_size": 4096,
            "max_page_count": MAX_DB_PAGES,
            "synchronous": 2,
            "temp_store": 2,
        }:
            raise ValueError

    def _require_current_authority_valid_if_present(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT owner_path_discriminator,revision,capability_registry_id,"
            "capability_head_sha256,capability_epoch,source_registry_id,source_head_sha256,"
            "source_epoch,pair_sha256,issued_at_ms,updated_at_ms,document_json "
            "FROM private_paid_effect_fixture_authority_current"
        ).fetchall()
        if len(rows) > 1:
            raise ValueError
        if rows:
            self._decode_authority_row(rows[0])

    def _decode_authority_row(self, row: Sequence[object]) -> SignedFixtureAuthorityPairV1:
        if len(row) != 12:
            raise ValueError
        pair = parse_signed_fixture_authority_pair_v1_json(str(row[11]).encode())
        verify_signed_fixture_authority_pair_v1(pair, verification_keys=self._keyring)
        if (
            pair.owner_path_discriminator != self.owner_path_discriminator
            or row[0] != pair.owner_path_discriminator
            or row[1] != pair.revision
            or row[2] != pair.capability_registry_id
            or row[3] != pair.capability_head_sha256
            or row[4] != pair.capability_epoch
            or row[5] != pair.source_registry_id
            or row[6] != pair.source_head_sha256
            or row[7] != pair.source_epoch
            or row[8] != pair.pair_sha256
            or row[9] != pair.issued_at_ms
            or not _valid_i63(row[10])
        ):
            raise ValueError
        return pair

    def initialize_fixture_authority_pair(
        self, *, signed_fixture_pair: SignedFixtureAuthorityPairV1, now_ms: int
    ) -> FixtureAuthorityPairResultV1:
        try:
            self._require_pair_shape(signed_fixture_pair, now_ms)
            if signed_fixture_pair.revision != 0:
                raise ValueError
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    row = connection.execute(
                        "SELECT owner_path_discriminator,revision,capability_registry_id,"
                        "capability_head_sha256,capability_epoch,source_registry_id,"
                        "source_head_sha256,source_epoch,pair_sha256,issued_at_ms,"
                        "updated_at_ms,document_json "
                        "FROM private_paid_effect_fixture_authority_current WHERE singleton=1"
                    ).fetchone()
                    if row is None:
                        self._require_issuance_window(signed_fixture_pair, now_ms)
                        self._insert_authority(connection, signed_fixture_pair, now_ms)
                        applied = True
                        current = signed_fixture_pair
                    else:
                        current = self._decode_authority_row(row)
                        if current != signed_fixture_pair:
                            raise ValueError
                        applied = False
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
            return self._pair_result(applied=applied, pair=current)
        except Exception:
            raise PrivatePaidEffectAdmissionFixtureRejected() from None

    def compare_and_set_fixture_authority_pair(
        self,
        *,
        expected_revision: int,
        expected_capability_head: str,
        expected_source_head: str,
        signed_fixture_pair: SignedFixtureAuthorityPairV1,
        now_ms: int,
    ) -> FixtureAuthorityPairResultV1:
        try:
            if (
                not _valid_i63(expected_revision)
                or type(expected_capability_head) is not str
                or _HEX64.fullmatch(expected_capability_head) is None
                or type(expected_source_head) is not str
                or _HEX64.fullmatch(expected_source_head) is None
            ):
                raise ValueError
            self._require_pair_shape(signed_fixture_pair, now_ms)
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    row = connection.execute(
                        "SELECT owner_path_discriminator,revision,capability_registry_id,"
                        "capability_head_sha256,capability_epoch,source_registry_id,"
                        "source_head_sha256,source_epoch,pair_sha256,issued_at_ms,"
                        "updated_at_ms,document_json "
                        "FROM private_paid_effect_fixture_authority_current WHERE singleton=1"
                    ).fetchone()
                    if row is None:
                        raise ValueError
                    current = self._decode_authority_row(row)
                    updated_at = int(row[10])
                    if now_ms < updated_at:
                        raise ValueError
                    if (
                        current.revision != expected_revision
                        or not hmac.compare_digest(
                            current.capability_head_sha256, expected_capability_head
                        )
                        or not hmac.compare_digest(current.source_head_sha256, expected_source_head)
                    ):
                        raise ValueError
                    if current == signed_fixture_pair:
                        applied = False
                        next_pair = current
                    else:
                        self._require_issuance_window(signed_fixture_pair, now_ms)
                        self._validate_successor(current, signed_fixture_pair)
                        self._replace_authority(connection, signed_fixture_pair, now_ms)
                        applied = True
                        next_pair = signed_fixture_pair
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
            return self._pair_result(applied=applied, pair=next_pair)
        except Exception:
            raise PrivatePaidEffectAdmissionFixtureRejected() from None

    def reserve_fixture_exposure(
        self, *, projected_max_cents: int, now_ms: int
    ) -> FixtureExposureMarkerV1:
        try:
            if (
                type(projected_max_cents) is not int
                or isinstance(projected_max_cents, bool)
                or not 1 <= projected_max_cents <= MAX_CENTS
                or not _valid_i63(now_ms)
            ):
                raise ValueError
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    authority_updated_at_ms = self._current_authority_updated_at_ms(connection)
                    if now_ms < authority_updated_at_ms:
                        raise ValueError
                    self._reap_expired_open_markers(connection, now_ms)
                    counts = connection.execute(
                        "SELECT "
                        "(SELECT COUNT(*) FROM private_paid_effect_fixture_exposure_markers),"
                        "(SELECT COUNT(*) FROM private_paid_effect_fixture_exposure_markers "
                        " WHERE exposure_state='open'),"
                        "(SELECT COUNT(*) FROM private_paid_effect_fixture_admissions)"
                    ).fetchone()
                    if counts is None or counts[0] >= MAX_MARKERS or counts[1] >= MAX_OPEN_MARKERS:
                        raise ValueError
                    marker = self._fresh_marker(connection, projected_max_cents, now_ms)
                    connection.execute(
                        "INSERT INTO private_paid_effect_fixture_exposure_markers "
                        "(logical_effect_key,hold_id,owner_path_discriminator,projected_max_cents,"
                        "exposure_state,created_at_ms,released_at_ms) VALUES (?,?,?,?,?,?,NULL)",
                        (
                            marker.logical_effect_key,
                            marker.hold_id,
                            self.owner_path_discriminator,
                            projected_max_cents,
                            "open",
                            now_ms,
                        ),
                    )
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
            return marker
        except Exception:
            raise PrivatePaidEffectAdmissionFixtureRejected() from None

    def admit_fixture_effect(
        self,
        *,
        expected_authority_revision: int,
        expected_capability_head: str,
        expected_source_head: str,
        hold_id: str,
        candidate: FixtureAdmissionCandidateV1,
        now_ms: int,
    ) -> PrivatePaidEffectAdmissionFixtureEvidenceV1:
        try:
            self._require_admission_args(
                expected_authority_revision,
                expected_capability_head,
                expected_source_head,
                hold_id,
                candidate,
                now_ms,
            )
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    existing = connection.execute(
                        _ADMISSION_ROW_SELECT + "WHERE a.hold_id=? AND a.logical_effect_key=?",
                        (hold_id, candidate.logical_effect_key),
                    ).fetchone()
                    if existing is not None:
                        self._current_authority(connection)
                        return self._replay_admission(
                            connection,
                            existing,
                            candidate,
                            expected_authority_revision=expected_authority_revision,
                            expected_capability_head=expected_capability_head,
                            expected_source_head=expected_source_head,
                        )
                    authority = self._current_authority(connection)
                    authority_updated_at_ms = self._current_authority_updated_at_ms(connection)
                    if (
                        now_ms < authority_updated_at_ms
                        or authority.revision != expected_authority_revision
                        or not hmac.compare_digest(
                            authority.capability_head_sha256, expected_capability_head
                        )
                        or not hmac.compare_digest(
                            authority.source_head_sha256, expected_source_head
                        )
                    ):
                        raise ValueError
                    marker = connection.execute(
                        "SELECT logical_effect_key,hold_id,owner_path_discriminator,"
                        "projected_max_cents,exposure_state,created_at_ms,released_at_ms "
                        "FROM private_paid_effect_fixture_exposure_markers "
                        "WHERE logical_effect_key=? AND hold_id=?",
                        (candidate.logical_effect_key, hold_id),
                    ).fetchone()
                    if (
                        marker is None
                        or marker[2] != self.owner_path_discriminator
                        or marker[3] != candidate.projected_max_cents
                        or marker[4] != "open"
                        or not int(marker[5]) <= now_ms <= int(marker[5]) + MARKER_TTL_MS
                    ):
                        raise ValueError
                    self._validate_candidate_joins(candidate, authority, hold_id)
                    row = self._seal_admission(connection, candidate, now_ms)
                    counts = connection.execute(
                        "SELECT COUNT(*) FROM private_paid_effect_fixture_admissions"
                    ).fetchone()
                    if counts is None or counts[0] > MAX_ADMISSIONS:
                        raise ValueError
                    connection.execute("COMMIT")
                    return PrivatePaidEffectAdmissionFixtureEvidenceV1(
                        replayed=False,
                        admission_id=row["admission_id"],
                        logical_effect_key=candidate.logical_effect_key,
                        hold_id=hold_id,
                        historical_fixture_pair_sha256=candidate.fixture_pair_sha256,
                        historical_authority_revision=candidate.authority_revision,
                        created_at_ms=now_ms,
                        exposure_state="open",
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except Exception:
            raise PrivatePaidEffectAdmissionFixtureRejected() from None

    def release_fixture_unreachable_transport(
        self, *, admission_id: str, hold_id: str, now_ms: int
    ) -> FixtureExposureReleaseV1:
        try:
            if (
                type(admission_id) is not str
                or _ADMISSION_ID.fullmatch(admission_id) is None
                or type(hold_id) is not str
                or _HOLD_ID.fullmatch(hold_id) is None
                or not _valid_i63(now_ms)
            ):
                raise ValueError
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    row = connection.execute(
                        _ADMISSION_ROW_SELECT + "WHERE a.admission_id=? AND a.hold_id=?",
                        (admission_id, hold_id),
                    ).fetchone()
                    if row is None:
                        raise ValueError
                    authenticated = self._authenticate_admission_row(row)
                    authority_updated_at_ms = self._current_authority_updated_at_ms(connection)
                    if authenticated.exposure_state == "released":
                        if authenticated.released_at_ms is None:
                            raise ValueError
                        released_at_ms = authenticated.released_at_ms
                        applied = False
                    elif authenticated.exposure_state == "open":
                        if now_ms < authority_updated_at_ms or now_ms < authenticated.created_at_ms:
                            raise ValueError
                        connection.execute(
                            "UPDATE private_paid_effect_fixture_exposure_markers "
                            "SET exposure_state='released', released_at_ms=? "
                            "WHERE logical_effect_key=? AND hold_id=? AND exposure_state='open'",
                            (now_ms, authenticated.candidate.logical_effect_key, hold_id),
                        )
                        released_at_ms = now_ms
                        applied = True
                    else:
                        raise ValueError
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
            return FixtureExposureReleaseV1(
                applied=applied,
                admission_id=admission_id,
                logical_effect_key=authenticated.candidate.logical_effect_key,
                hold_id=hold_id,
                released_at_ms=released_at_ms,
            )
        except Exception:
            raise PrivatePaidEffectAdmissionFixtureRejected() from None

    def backup_to(self, destination: str | Path) -> None:
        destination_path: Path | None = None
        destination_created = False
        try:
            if type(destination) not in {str, type(Path())}:
                raise ValueError
            raw = os.fspath(destination)
            if not raw.strip() or raw == ":memory:":
                raise ValueError
            supplied = Path(raw).absolute()
            self._reject_symlinked_ancestors(supplied)
            destination_path = supplied.resolve(strict=False)
            if destination_path == self.path or destination_path.exists():
                raise ValueError
            self._validate_secure_durable_path(destination_path, require_exists=False)
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(destination_path, flags, 0o600)
            destination_created = True
            try:
                os.fchmod(descriptor, 0o600)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self._validate_secure_durable_path(destination_path, require_exists=True)
            with (
                closing(self._connect()) as source,
                closing(
                    sqlite3.connect(destination_path, timeout=30, isolation_level=None)
                ) as target,
            ):
                target.execute("PRAGMA journal_mode=WAL")
                target.execute("PRAGMA synchronous=FULL")
                target.execute("PRAGMA foreign_keys=ON")
                target.execute("PRAGMA busy_timeout=30000")
                target.execute("PRAGMA temp_store=MEMORY")
                target.execute("PRAGMA page_size=4096")
                target.execute(f"PRAGMA max_page_count={MAX_DB_PAGES}")
                self._chmod_sidecars_for(destination_path)
                source.backup(target)
                self._chmod_sidecars_for(destination_path)
                self._validate_schema(target)
                self._require_current_authority_valid_if_present(target)
                target.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._validate_secure_durable_path(destination_path, require_exists=True)
            durable_descriptor = os.open(destination_path, os.O_RDONLY)
            try:
                os.fsync(durable_descriptor)
            finally:
                os.close(durable_descriptor)
            parent_descriptor = os.open(destination_path.parent, os.O_RDONLY)
            try:
                os.fsync(parent_descriptor)
            finally:
                os.close(parent_descriptor)
        except Exception:
            if destination_path is not None and destination_created:
                for suffix in ("-wal", "-shm", "-journal", ""):
                    candidate = Path(str(destination_path) + suffix)
                    with suppress(Exception):
                        candidate.unlink(missing_ok=True)
            raise PrivatePaidEffectAdmissionFixtureRejected() from None

    def _require_pair_shape(self, pair: SignedFixtureAuthorityPairV1, now_ms: int) -> None:
        if (
            type(pair) is not SignedFixtureAuthorityPairV1
            or pair.owner_path_discriminator != self.owner_path_discriminator
            or not _valid_i63(now_ms)
        ):
            raise ValueError
        verify_signed_fixture_authority_pair_v1(pair, verification_keys=self._keyring)

    @staticmethod
    def _require_issuance_window(pair: SignedFixtureAuthorityPairV1, now_ms: int) -> None:
        if pair.issued_at_ms - 60_000 > now_ms or now_ms - pair.issued_at_ms > MARKER_TTL_MS:
            raise ValueError

    @staticmethod
    def _validate_successor(
        current: SignedFixtureAuthorityPairV1, successor: SignedFixtureAuthorityPairV1
    ) -> None:
        cap_changed = successor.capability_head_sha256 != current.capability_head_sha256
        source_changed = successor.source_head_sha256 != current.source_head_sha256
        if (
            successor.owner_path_discriminator != current.owner_path_discriminator
            or successor.capability_registry_id != current.capability_registry_id
            or successor.source_registry_id != current.source_registry_id
            or successor.revision != current.revision + 1
            or not hmac.compare_digest(successor.previous_pair_sha256, current.pair_sha256)
            or successor.issued_at_ms <= current.issued_at_ms
            or not (cap_changed or source_changed)
            or successor.capability_epoch
            != (current.capability_epoch + 1 if cap_changed else current.capability_epoch)
            or successor.source_epoch
            != (current.source_epoch + 1 if source_changed else current.source_epoch)
        ):
            raise ValueError

    @staticmethod
    def _pair_result(
        *, applied: bool, pair: SignedFixtureAuthorityPairV1
    ) -> FixtureAuthorityPairResultV1:
        return FixtureAuthorityPairResultV1(
            applied=applied,
            pair_sha256=pair.pair_sha256,
            revision=pair.revision,
            capability_head_sha256=pair.capability_head_sha256,
            source_head_sha256=pair.source_head_sha256,
        )

    @staticmethod
    def _insert_authority(
        connection: sqlite3.Connection, pair: SignedFixtureAuthorityPairV1, now_ms: int
    ) -> None:
        connection.execute(
            "INSERT INTO private_paid_effect_fixture_authority_current "
            "(singleton,owner_path_discriminator,revision,capability_registry_id,"
            "capability_head_sha256,capability_epoch,source_registry_id,source_head_sha256,"
            "source_epoch,pair_sha256,issued_at_ms,updated_at_ms,document_json) "
            "VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                pair.owner_path_discriminator,
                pair.revision,
                pair.capability_registry_id,
                pair.capability_head_sha256,
                pair.capability_epoch,
                pair.source_registry_id,
                pair.source_head_sha256,
                pair.source_epoch,
                pair.pair_sha256,
                pair.issued_at_ms,
                now_ms,
                _canonical_model_json(pair).decode(),
            ),
        )

    @staticmethod
    def _replace_authority(
        connection: sqlite3.Connection, pair: SignedFixtureAuthorityPairV1, now_ms: int
    ) -> None:
        connection.execute("DELETE FROM private_paid_effect_fixture_authority_current")
        PrivatePaidEffectAdmissionFixtureStoreV1._insert_authority(connection, pair, now_ms)

    def _current_authority(self, connection: sqlite3.Connection) -> SignedFixtureAuthorityPairV1:
        row = connection.execute(
            "SELECT owner_path_discriminator,revision,capability_registry_id,"
            "capability_head_sha256,capability_epoch,source_registry_id,source_head_sha256,"
            "source_epoch,pair_sha256,issued_at_ms,updated_at_ms,document_json "
            "FROM private_paid_effect_fixture_authority_current WHERE singleton=1"
        ).fetchone()
        if row is None:
            raise ValueError
        return self._decode_authority_row(row)

    def _current_authority_updated_at_ms(self, connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT owner_path_discriminator,revision,capability_registry_id,"
            "capability_head_sha256,capability_epoch,source_registry_id,source_head_sha256,"
            "source_epoch,pair_sha256,issued_at_ms,updated_at_ms,document_json "
            "FROM private_paid_effect_fixture_authority_current WHERE singleton=1"
        ).fetchone()
        if row is None:
            raise ValueError
        self._decode_authority_row(row)
        updated_at_ms = row[10]
        if not _valid_i63(updated_at_ms):
            raise ValueError
        return int(updated_at_ms)

    @staticmethod
    def _reap_expired_open_markers(connection: sqlite3.Connection, now_ms: int) -> None:
        connection.execute(
            "DELETE FROM private_paid_effect_fixture_exposure_markers "
            "WHERE exposure_state='open' AND created_at_ms + ? < ? "
            "AND logical_effect_key NOT IN ("
            "SELECT logical_effect_key FROM private_paid_effect_fixture_admissions)",
            (MARKER_TTL_MS, now_ms),
        )

    def _fresh_marker(
        self, connection: sqlite3.Connection, projected_max_cents: int, now_ms: int
    ) -> FixtureExposureMarkerV1:
        for _ in range(8):
            effect_key = "mopeffect1_" + secrets.token_hex(32)
            hold_id = "mophold1_" + secrets.token_hex(32)
            exists = connection.execute(
                "SELECT 1 FROM private_paid_effect_fixture_exposure_markers "
                "WHERE logical_effect_key=? OR hold_id=?",
                (effect_key, hold_id),
            ).fetchone()
            if exists is None:
                return FixtureExposureMarkerV1(
                    logical_effect_key=effect_key,
                    hold_id=hold_id,
                    projected_max_cents=projected_max_cents,
                    created_at_ms=now_ms,
                )
        raise ValueError

    @staticmethod
    def _require_admission_args(
        expected_authority_revision: int,
        expected_capability_head: str,
        expected_source_head: str,
        hold_id: str,
        candidate: FixtureAdmissionCandidateV1,
        now_ms: int,
    ) -> None:
        if (
            not _valid_i63(expected_authority_revision)
            or type(expected_capability_head) is not str
            or _HEX64.fullmatch(expected_capability_head) is None
            or type(expected_source_head) is not str
            or _HEX64.fullmatch(expected_source_head) is None
            or type(hold_id) is not str
            or _HOLD_ID.fullmatch(hold_id) is None
            or type(candidate) is not FixtureAdmissionCandidateV1
            or not _valid_i63(now_ms)
        ):
            raise ValueError
        canonical = FixtureAdmissionCandidateV1.model_validate(candidate.model_dump(mode="python"))
        if canonical != candidate:
            raise ValueError

    def _validate_candidate_joins(
        self,
        candidate: FixtureAdmissionCandidateV1,
        authority: SignedFixtureAuthorityPairV1,
        hold_id: str,
    ) -> None:
        if (
            candidate.owner_path_discriminator != self.owner_path_discriminator
            or candidate.hold_id != hold_id
            or candidate.authority_revision != authority.revision
            or candidate.fixture_pair_sha256 != authority.pair_sha256
            or candidate.capability_registry_id != authority.capability_registry_id
            or candidate.capability_head_sha256 != authority.capability_head_sha256
            or candidate.capability_epoch != authority.capability_epoch
            or candidate.source_registry_id != authority.source_registry_id
            or candidate.source_head_sha256 != authority.source_head_sha256
            or candidate.source_epoch != authority.source_epoch
        ):
            raise ValueError

    def _open_key(self) -> AbstractContextManager[bytearray]:
        return self._key_provider.open_aes256gcm_key(
            owner_path_authority=self._owner_path_authority,
            owner_path_discriminator=self.owner_path_discriminator,
            store_id=self.store_id,
            key_version=self.key_version,
        )

    def _seal_admission(
        self, connection: sqlite3.Connection, candidate: FixtureAdmissionCandidateV1, now_ms: int
    ) -> dict[str, str]:
        plaintext_buffer = bytearray(
            _canonical_model_json(
                _AdmissionPlaintextV1(schema_version=1, admitted_at_ms=now_ms, candidate=candidate)
            )
        )
        try:
            admission_id = self._fresh_admission_id(connection)
            ciphertext_length = len(plaintext_buffer) + 16
            _require_admission_size_bounds(len(plaintext_buffer), ciphertext_length)
            metadata = _admission_metadata(
                store_id=self.store_id,
                owner_path_discriminator=self.owner_path_discriminator,
                logical_effect_key=candidate.logical_effect_key,
                hold_id=candidate.hold_id,
                admission_id=admission_id,
                authority_revision=candidate.authority_revision,
                fixture_pair_sha256=candidate.fixture_pair_sha256,
                projected_max_cents=candidate.projected_max_cents,
                created_at_ms=now_ms,
                key_version=self.key_version,
                ciphertext_length=ciphertext_length,
            )
            nonce = self._fresh_nonce(connection)
            with self._open_key() as key:
                try:
                    if type(key) is not bytearray or len(key) != 32:
                        raise ValueError
                    ciphertext = AESGCM(bytes(key)).encrypt(
                        nonce, bytes(plaintext_buffer), _aad(metadata)
                    )
                finally:
                    if isinstance(key, bytearray):
                        key[:] = b"\x00" * len(key)
            if len(ciphertext) != ciphertext_length:
                raise ValueError
            connection.execute(
                "INSERT INTO private_paid_effect_fixture_admissions "
                "(admission_id,logical_effect_key,hold_id,owner_path_discriminator,"
                "fixture_pair_sha256,authority_revision,projected_max_cents,"
                "categorical_state,created_at_ms,"
                "aead_suite,key_version,nonce_length,nonce,ciphertext_schema,ciphertext_type,"
                "ciphertext_length,ciphertext) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    admission_id,
                    candidate.logical_effect_key,
                    candidate.hold_id,
                    self.owner_path_discriminator,
                    candidate.fixture_pair_sha256,
                    candidate.authority_revision,
                    candidate.projected_max_cents,
                    "admission_committed",
                    now_ms,
                    "aes-256-gcm",
                    self.key_version,
                    12,
                    nonce,
                    "private_paid_effect_admission_fixture_v1_json",
                    "application/json",
                    ciphertext_length,
                    ciphertext,
                ),
            )
            return {"admission_id": admission_id}
        finally:
            plaintext_buffer[:] = b"\x00" * len(plaintext_buffer)

    @staticmethod
    def _fresh_admission_id(connection: sqlite3.Connection) -> str:
        for _ in range(8):
            admission_id = "moadmit1_" + secrets.token_hex(32)
            if (
                connection.execute(
                    "SELECT 1 FROM private_paid_effect_fixture_admissions WHERE admission_id=?",
                    (admission_id,),
                ).fetchone()
                is None
            ):
                return admission_id
        raise ValueError

    def _fresh_nonce(self, connection: sqlite3.Connection) -> bytes:
        used = {
            bytes(row[0])
            for row in connection.execute(
                "SELECT nonce FROM private_paid_effect_fixture_admissions "
                "WHERE owner_path_discriminator=? AND key_version=?",
                (self.owner_path_discriminator, self.key_version),
            ).fetchall()
        }
        for _ in range(NONCE_COLLISION_RETRIES):
            nonce = secrets.token_bytes(12)
            if nonce not in used:
                return nonce
        raise ValueError

    def _replay_admission(
        self,
        connection: sqlite3.Connection,
        row: Sequence[object],
        candidate: FixtureAdmissionCandidateV1,
        *,
        expected_authority_revision: int,
        expected_capability_head: str,
        expected_source_head: str,
    ) -> PrivatePaidEffectAdmissionFixtureEvidenceV1:
        authenticated = self._authenticate_admission_row(row)
        stored_candidate = authenticated.candidate
        if (
            expected_authority_revision != stored_candidate.authority_revision
            or not hmac.compare_digest(
                expected_capability_head, stored_candidate.capability_head_sha256
            )
            or not hmac.compare_digest(expected_source_head, stored_candidate.source_head_sha256)
            or not hmac.compare_digest(
                _canonical_model_json(stored_candidate), _canonical_model_json(candidate)
            )
        ):
            raise ValueError
        connection.execute("COMMIT")
        return PrivatePaidEffectAdmissionFixtureEvidenceV1(
            replayed=True,
            admission_id=authenticated.admission_id,
            logical_effect_key=stored_candidate.logical_effect_key,
            hold_id=stored_candidate.hold_id,
            historical_fixture_pair_sha256=stored_candidate.fixture_pair_sha256,
            historical_authority_revision=stored_candidate.authority_revision,
            created_at_ms=authenticated.created_at_ms,
            exposure_state=authenticated.exposure_state,
        )

    def _authenticate_admission_row(self, row: Sequence[object]) -> _AuthenticatedAdmissionV1:
        if len(row) != 24:
            raise ValueError
        (
            admission_id_value,
            effect_key_value,
            hold_id_value,
            owner_path_discriminator_value,
            fixture_pair_sha256_value,
            authority_revision_value,
            projected_cents_value,
            categorical_state_value,
            created_at_value,
            aead_suite_value,
            key_version_value,
            nonce_length_value,
            nonce_value,
            ciphertext_schema_value,
            ciphertext_type_value,
            ciphertext_length_value,
            ciphertext_value,
            marker_effect_key_value,
            marker_hold_id_value,
            marker_owner_value,
            marker_projected_cents_value,
            exposure_state_value,
            marker_created_at_value,
            released_at_value,
        ) = row
        if (
            type(admission_id_value) is not str
            or _ADMISSION_ID.fullmatch(admission_id_value) is None
            or type(effect_key_value) is not str
            or _EFFECT_ID.fullmatch(effect_key_value) is None
            or type(hold_id_value) is not str
            or _HOLD_ID.fullmatch(hold_id_value) is None
            or owner_path_discriminator_value != self.owner_path_discriminator
            or type(fixture_pair_sha256_value) is not str
            or _HEX64.fullmatch(fixture_pair_sha256_value) is None
            or not _valid_i63(authority_revision_value)
            or type(projected_cents_value) is not int
            or isinstance(projected_cents_value, bool)
            or not 1 <= projected_cents_value <= MAX_CENTS
            or categorical_state_value != "admission_committed"
            or not _valid_i63(created_at_value)
            or aead_suite_value != "aes-256-gcm"
            or key_version_value != self.key_version
            or nonce_length_value != 12
            or type(nonce_value) is not bytes
            or len(nonce_value) != 12
            or ciphertext_schema_value != "private_paid_effect_admission_fixture_v1_json"
            or ciphertext_type_value != "application/json"
            or type(ciphertext_length_value) is not int
            or isinstance(ciphertext_length_value, bool)
            or type(ciphertext_value) is not bytes
            or not 16 <= ciphertext_length_value <= MAX_ADMISSION_CIPHERTEXT_BYTES
            or ciphertext_length_value != len(ciphertext_value)
            or marker_effect_key_value != effect_key_value
            or marker_hold_id_value != hold_id_value
            or marker_owner_value != owner_path_discriminator_value
            or marker_projected_cents_value != projected_cents_value
            or type(exposure_state_value) is not str
            or exposure_state_value not in {"open", "released"}
            or not _valid_i63(marker_created_at_value)
            or (exposure_state_value == "open" and released_at_value is not None)
            or (exposure_state_value == "released" and not _valid_i63(released_at_value))
        ):
            raise ValueError
        authority_revision = cast(int, authority_revision_value)
        created_at_ms = cast(int, created_at_value)
        marker_created_at_ms = cast(int, marker_created_at_value)
        released_at_ms = cast(int | None, released_at_value)
        if marker_created_at_ms > created_at_ms or (
            released_at_ms is not None and released_at_ms < max(marker_created_at_ms, created_at_ms)
        ):
            raise ValueError
        exposure_state: Literal["open", "released"] = (
            "open" if exposure_state_value == "open" else "released"
        )
        metadata = _admission_metadata(
            store_id=self.store_id,
            owner_path_discriminator=self.owner_path_discriminator,
            logical_effect_key=effect_key_value,
            hold_id=hold_id_value,
            admission_id=admission_id_value,
            authority_revision=authority_revision,
            fixture_pair_sha256=fixture_pair_sha256_value,
            projected_max_cents=projected_cents_value,
            created_at_ms=created_at_ms,
            key_version=key_version_value,
            ciphertext_length=ciphertext_length_value,
        )
        with self._open_key() as key:
            try:
                if type(key) is not bytearray or len(key) != 32:
                    raise ValueError
                plaintext = AESGCM(bytes(key)).decrypt(
                    nonce_value, ciphertext_value, _aad(metadata)
                )
            finally:
                if isinstance(key, bytearray):
                    key[:] = b"\x00" * len(key)
        try:
            json.loads(plaintext.decode(), object_pairs_hook=_reject_duplicates)
            stored = _AdmissionPlaintextV1.model_validate_json(plaintext)
        except Exception:
            raise ValueError from None
        _require_admission_size_bounds(len(plaintext), ciphertext_length_value)
        if (
            not hmac.compare_digest(_canonical_model_json(stored), plaintext)
            or stored.admitted_at_ms != created_at_ms
            or stored.candidate.fixture_pair_sha256 != fixture_pair_sha256_value
            or stored.candidate.owner_path_discriminator != owner_path_discriminator_value
            or stored.candidate.logical_effect_key != effect_key_value
            or stored.candidate.hold_id != hold_id_value
            or stored.candidate.authority_revision != authority_revision
            or stored.candidate.projected_max_cents != projected_cents_value
        ):
            raise ValueError
        return _AuthenticatedAdmissionV1(
            admission_id=admission_id_value,
            candidate=stored.candidate,
            created_at_ms=created_at_ms,
            exposure_state=exposure_state,
            released_at_ms=released_at_ms,
        )


def private_paid_effect_admission_module_source_sha256() -> str:
    """Attest this module AST while excluding its two independently pinned identities."""
    tree = ast.parse(Path(__file__).read_bytes(), filename=__file__)
    identity_replacements = {
        "PRIVATE_PAID_EFFECT_ADMISSION_MODULE_SOURCE_SHA256": (
            "<self-semantic-module-source-sha256>"
        ),
        "PRIVATE_PAID_EFFECT_ADMISSION_CYCLE33_CONTRACT_SHA256": (
            "<independent-cycle33-contract-sha256>"
        ),
    }
    assignments = {name: 0 for name in identity_replacements}
    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id in identity_replacements
        ):
            name = statement.targets[0].id
            value = statement.value
            if (
                not isinstance(value, ast.Constant)
                or type(value.value) is not str
                or len(value.value) != 64
                or any(character not in "0123456789abcdef" for character in value.value)
            ):
                raise RuntimeError("private paid-effect admission source identity conflicts")
            assignments[name] += 1
            statement.value = ast.Constant(value=identity_replacements[name])
    stores = {
        name: sum(
            isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == name
            for node in ast.walk(tree)
        )
        for name in identity_replacements
    }
    if any(assignments[name] != 1 or stores[name] != 1 for name in identity_replacements):
        raise RuntimeError("private paid-effect admission source assignment conflicts")
    material = ast.dump(tree, annotate_fields=True, include_attributes=False).encode()
    return hashlib.sha256(_SOURCE_DOMAIN + material).hexdigest()


PRIVATE_PAID_EFFECT_ADMISSION_MODULE_SOURCE_SHA256 = (
    "71c0690bd0548e7f5b6dab0d8fd7d4f0bf02aa24b0c30f5083a0f3cef6ed101a"
)


def require_private_paid_effect_admission_module_source() -> None:
    if not hmac.compare_digest(
        private_paid_effect_admission_module_source_sha256(),
        PRIVATE_PAID_EFFECT_ADMISSION_MODULE_SOURCE_SHA256,
    ):
        raise RuntimeError("private paid-effect admission implementation conflicts")


_CYCLE33_CONTRACT_DOMAIN = b"antiek.midnight-oil.private-paid-effect-admission-contract.v1\x00"
_CYCLE33_PUBLIC_API_SIGNATURES = (
    "PrivatePaidEffectAdmissionFixtureStoreV1.__init__"
    "(self, path: 'str | Path', *, owner_path_authority: 'object', "
    "owner_path_discriminator: 'str', store_id: 'str', key_version: 'str', "
    "fixture_authority_verification_keys: 'Mapping[str, bytes]', "
    "key_provider: 'PrivatePaidEffectAdmissionFixtureKeyProviderV1') -> 'None'",
    "PrivatePaidEffectAdmissionFixtureStoreV1.initialize_fixture_authority_pair"
    "(self, *, signed_fixture_pair: 'SignedFixtureAuthorityPairV1', now_ms: 'int') "
    "-> 'FixtureAuthorityPairResultV1'",
    "PrivatePaidEffectAdmissionFixtureStoreV1.compare_and_set_fixture_authority_pair"
    "(self, *, expected_revision: 'int', expected_capability_head: 'str', "
    "expected_source_head: 'str', signed_fixture_pair: 'SignedFixtureAuthorityPairV1', "
    "now_ms: 'int') -> 'FixtureAuthorityPairResultV1'",
    "PrivatePaidEffectAdmissionFixtureStoreV1.reserve_fixture_exposure"
    "(self, *, projected_max_cents: 'int', now_ms: 'int') "
    "-> 'FixtureExposureMarkerV1'",
    "PrivatePaidEffectAdmissionFixtureStoreV1.admit_fixture_effect"
    "(self, *, expected_authority_revision: 'int', expected_capability_head: 'str', "
    "expected_source_head: 'str', hold_id: 'str', "
    "candidate: 'FixtureAdmissionCandidateV1', now_ms: 'int') "
    "-> 'PrivatePaidEffectAdmissionFixtureEvidenceV1'",
    "PrivatePaidEffectAdmissionFixtureStoreV1.release_fixture_unreachable_transport"
    "(self, *, admission_id: 'str', hold_id: 'str', now_ms: 'int') "
    "-> 'FixtureExposureReleaseV1'",
    "PrivatePaidEffectAdmissionFixtureStoreV1.backup_to(self, destination: 'str | Path') -> 'None'",
    "parse_signed_fixture_authority_pair_v1_json(value: 'bytes') -> 'SignedFixtureAuthorityPairV1'",
    "verify_signed_fixture_authority_pair_v1"
    "(pair: 'SignedFixtureAuthorityPairV1', *, "
    "verification_keys: 'Mapping[str, bytes]') -> 'None'",
    "signed_fixture_authority_pair_v1_sha256"
    "(pair: 'SignedFixtureAuthorityPairV1 | Mapping[str, object]') -> 'str'",
)
_CYCLE33_ADMISSION_FRAMING_FIELDS = (
    "admission_id",
    "logical_effect_key",
    "hold_id",
    "owner_path_discriminator",
    "fixture_pair_sha256",
    "authority_revision",
    "projected_max_cents",
    "categorical_state",
    "created_at_ms",
    "aead_suite",
    "key_version",
    "nonce_length",
    "nonce",
    "ciphertext_schema",
    "ciphertext_type",
    "ciphertext_length",
    "ciphertext",
)
_CYCLE33_PUBLIC_EXPORTS = (
    "PRIVATE_PAID_EFFECT_ADMISSION_CYCLE33_CONTRACT_SHA256",
    "FixtureAdmissionCandidateV1",
    "FixtureAuthorityPairResultV1",
    "FixtureExposureMarkerV1",
    "FixtureExposureReleaseV1",
    "FixtureSourceReceiptPairV1",
    "MARKER_TTL_MS",
    "NONCE_COLLISION_RETRIES",
    "PRIVATE_PAID_EFFECT_ADMISSION_MODULE_SOURCE_SHA256",
    "PrivatePaidEffectAdmissionFixtureEvidenceV1",
    "PrivatePaidEffectAdmissionFixtureKeyProviderV1",
    "PrivatePaidEffectAdmissionFixtureRejected",
    "PrivatePaidEffectAdmissionFixtureStoreV1",
    "PrivatePaidEffectAdmissionCycle33ContractV1",
    "SignedFixtureAuthorityPairV1",
    "build_private_paid_effect_admission_cycle33_contract_v1",
    "parse_signed_fixture_authority_pair_v1_json",
    "private_paid_effect_admission_module_source_sha256",
    "require_private_paid_effect_admission_module_source",
    "require_private_paid_effect_admission_cycle33_contract",
    "signed_fixture_authority_pair_v1_sha256",
    "verify_signed_fixture_authority_pair_v1",
)


def _cycle33_runtime_api_signatures() -> tuple[str, ...]:
    store = PrivatePaidEffectAdmissionFixtureStoreV1
    callables = (
        ("PrivatePaidEffectAdmissionFixtureStoreV1.__init__", store.__init__),
        (
            "PrivatePaidEffectAdmissionFixtureStoreV1.initialize_fixture_authority_pair",
            store.initialize_fixture_authority_pair,
        ),
        (
            "PrivatePaidEffectAdmissionFixtureStoreV1.compare_and_set_fixture_authority_pair",
            store.compare_and_set_fixture_authority_pair,
        ),
        (
            "PrivatePaidEffectAdmissionFixtureStoreV1.reserve_fixture_exposure",
            store.reserve_fixture_exposure,
        ),
        (
            "PrivatePaidEffectAdmissionFixtureStoreV1.admit_fixture_effect",
            store.admit_fixture_effect,
        ),
        (
            "PrivatePaidEffectAdmissionFixtureStoreV1.release_fixture_unreachable_transport",
            store.release_fixture_unreachable_transport,
        ),
        ("PrivatePaidEffectAdmissionFixtureStoreV1.backup_to", store.backup_to),
        (
            "parse_signed_fixture_authority_pair_v1_json",
            parse_signed_fixture_authority_pair_v1_json,
        ),
        (
            "verify_signed_fixture_authority_pair_v1",
            verify_signed_fixture_authority_pair_v1,
        ),
        (
            "signed_fixture_authority_pair_v1_sha256",
            signed_fixture_authority_pair_v1_sha256,
        ),
    )
    return tuple(name + str(inspect.signature(value)) for name, value in callables)


def _cycle33_contract_material() -> dict[str, object]:
    ddl = (_SCHEMA_DDL, _AUTHORITY_DDL, _MARKERS_DDL, _ADMISSIONS_DDL)
    return {
        "schema_version": 1,
        "contract_id": "antiek-private-paid-effect-admission-cycle33-v1",
        "public_api_signatures": _CYCLE33_PUBLIC_API_SIGNATURES,
        "public_exports": _CYCLE33_PUBLIC_EXPORTS,
        "public_result_types": (
            "FixtureAuthorityPairResultV1",
            "FixtureExposureMarkerV1",
            "PrivatePaidEffectAdmissionFixtureEvidenceV1",
            "FixtureExposureReleaseV1",
        ),
        "tables": tuple(sorted(_EXPECTED_TABLES)),
        "schema_ddl_sha256": hashlib.sha256(_canonical_json(ddl)).hexdigest(),
        "admission_framing_fields": _CYCLE33_ADMISSION_FRAMING_FIELDS,
        "model_field_inventory": tuple(
            f"{model.__name__}:{','.join(model.model_fields)}"
            for model in (
                SignedFixtureAuthorityPairV1,
                FixtureSourceReceiptPairV1,
                FixtureAdmissionCandidateV1,
                FixtureAuthorityPairResultV1,
                FixtureExposureMarkerV1,
                PrivatePaidEffectAdmissionFixtureEvidenceV1,
                FixtureExposureReleaseV1,
            )
        ),
        "domains_hex": (
            _PAIR_DOMAIN.hex(),
            _PAIR_SIGNATURE_DOMAIN.hex(),
            _AEAD_DOMAIN.hex(),
            _SOURCE_DOMAIN.hex(),
        ),
        "bounds": (
            f"max_open_markers={MAX_OPEN_MARKERS}",
            f"max_markers={MAX_MARKERS}",
            f"max_admissions={MAX_ADMISSIONS}",
            "max_receipt_pairs=8",
            f"max_verification_keys={MAX_FIXTURE_VERIFICATION_KEYS}",
            f"nonce_collision_retries={NONCE_COLLISION_RETRIES}",
            f"max_db_pages={MAX_DB_PAGES}",
            "db_page_bytes=4096",
            f"max_plaintext_bytes={MAX_ADMISSION_PLAINTEXT_BYTES}",
            f"max_ciphertext_bytes={MAX_ADMISSION_CIPHERTEXT_BYTES}",
        ),
        "boundary_literals": (
            "fixture_authority_only=true",
            "live_authority_verified=false",
            "user_accounting_effect=false",
            "transport_reachable=false",
            "confers_execution_authority=false",
            "confers_checkpoint_authority=false",
            "confers_sink_authority=false",
            "confers_transition_authority=false",
            "production_consumer_enabled=false",
        ),
        "module_source_sha256": PRIVATE_PAID_EFFECT_ADMISSION_MODULE_SOURCE_SHA256,
    }


def _cycle33_contract_sha256(material: Mapping[str, object]) -> str:
    return hashlib.sha256(_CYCLE33_CONTRACT_DOMAIN + _canonical_json(material)).hexdigest()


class PrivatePaidEffectAdmissionCycle33ContractV1(_Closed):
    schema_version: Literal[1] = 1
    contract_id: Literal["antiek-private-paid-effect-admission-cycle33-v1"] = (
        "antiek-private-paid-effect-admission-cycle33-v1"
    )
    public_api_signatures: tuple[str, ...]
    public_exports: tuple[str, ...]
    public_result_types: tuple[str, ...]
    tables: tuple[str, ...]
    schema_ddl_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    admission_framing_fields: tuple[str, ...]
    model_field_inventory: tuple[str, ...]
    domains_hex: tuple[str, ...]
    bounds: tuple[str, ...]
    boundary_literals: tuple[str, ...]
    module_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _exact_contract(self) -> PrivatePaidEffectAdmissionCycle33ContractV1:
        material = _cycle33_contract_material()
        if self.model_dump(
            mode="python", exclude={"contract_sha256"}
        ) != material or self.contract_sha256 != _cycle33_contract_sha256(material):
            raise ValueError("private paid-effect admission contract conflicts")
        return self


PRIVATE_PAID_EFFECT_ADMISSION_CYCLE33_CONTRACT_SHA256 = (
    "6da8daafe21e1ff320751750bcb67da159dab248938cfa8e4812a9d828f7106f"
)


def build_private_paid_effect_admission_cycle33_contract_v1() -> (
    PrivatePaidEffectAdmissionCycle33ContractV1
):
    if _cycle33_runtime_api_signatures() != _CYCLE33_PUBLIC_API_SIGNATURES:
        raise RuntimeError("private paid-effect admission API contract conflicts")
    material = _cycle33_contract_material()
    return PrivatePaidEffectAdmissionCycle33ContractV1.model_validate(
        {
            **material,
            "contract_sha256": PRIVATE_PAID_EFFECT_ADMISSION_CYCLE33_CONTRACT_SHA256,
        }
    )


def require_private_paid_effect_admission_cycle33_contract() -> None:
    contract = build_private_paid_effect_admission_cycle33_contract_v1()
    if not hmac.compare_digest(
        contract.contract_sha256,
        PRIVATE_PAID_EFFECT_ADMISSION_CYCLE33_CONTRACT_SHA256,
    ) or not hmac.compare_digest(
        contract.module_source_sha256,
        private_paid_effect_admission_module_source_sha256(),
    ):
        raise RuntimeError("private paid-effect admission contract identity conflicts")


__all__ = list(_CYCLE33_PUBLIC_EXPORTS)
