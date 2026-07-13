"""Test-only issuers for Cycle 33A private paid-effect admission fixtures."""

from __future__ import annotations

import os
import sqlite3
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Literal, Never

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from substrate.midnight_oil.private_paid_effect_admission import (
    FixtureAdmissionCandidateV1,
    FixtureSourceReceiptPairV1,
    PrivatePaidEffectAdmissionFixtureStoreV1,
    SignedFixtureAuthorityPairV1,
    signed_fixture_authority_pair_v1_sha256,
)

PAIR_KEY_ID = "fixture-paid-key"
PAIR_PRIVATE_KEY = bytes.fromhex("51" * 32)
PAIR_SIGNATURE_DOMAIN = b"antiek.midnight-oil.private-paid-effect-fixture-signature.v1\x00"
OWNER_PATH_DISCRIMINATOR = "opspd1_" + "a1" * 32
STORE_ID = "mopstore1_" + "b2" * 32
KEY_VERSION = "moakv1_test-fixture-v1"
CAPABILITY_REGISTRY_ID = "capability.fixture.registry"
SOURCE_REGISTRY_ID = "source.fixture.registry"
CAPABILITY_HEAD_0 = "11" * 32
CAPABILITY_HEAD_1 = "22" * 32
SOURCE_HEAD_0 = "33" * 32
SOURCE_HEAD_1 = "44" * 32
DATA_KEY = bytes(range(32))


def public_key(private_key: bytes = PAIR_PRIVATE_KEY) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(private_key).public_key().public_bytes_raw()


def fixture_pair_verification_keys() -> dict[str, bytes]:
    return {PAIR_KEY_ID: public_key()}


def _sign_pair_hash(pair_sha256: str, private_key: bytes = PAIR_PRIVATE_KEY) -> str:
    return (
        Ed25519PrivateKey.from_private_bytes(private_key)
        .sign(PAIR_SIGNATURE_DOMAIN + bytes.fromhex(pair_sha256))
        .hex()
    )


def signed_fixture_pair(
    *,
    revision: int,
    previous_pair_sha256: str,
    issued_at_ms: int,
    capability_head_sha256: str = CAPABILITY_HEAD_0,
    capability_epoch: int = 0,
    source_head_sha256: str = SOURCE_HEAD_0,
    source_epoch: int = 0,
    owner_path_discriminator: str = OWNER_PATH_DISCRIMINATOR,
    capability_registry_id: str = CAPABILITY_REGISTRY_ID,
    source_registry_id: str = SOURCE_REGISTRY_ID,
    key_id: str = PAIR_KEY_ID,
) -> SignedFixtureAuthorityPairV1:
    material: dict[str, object] = {
        "schema_version": 1,
        "owner_path_discriminator": owner_path_discriminator,
        "revision": revision,
        "previous_pair_sha256": previous_pair_sha256,
        "issued_at_ms": issued_at_ms,
        "capability_registry_id": capability_registry_id,
        "capability_head_sha256": capability_head_sha256,
        "capability_epoch": capability_epoch,
        "source_registry_id": source_registry_id,
        "source_head_sha256": source_head_sha256,
        "source_epoch": source_epoch,
        "key_id": key_id,
        "issuer_role": "private_paid_effect_fixture_authority_issuer",
        "key_purpose": "private_paid_effect_fixture_authority_v1",
        "signature_scheme": "ed25519",
        "confers_execution_authority": False,
        "confers_checkpoint_authority": False,
        "confers_sink_authority": False,
        "confers_transition_authority": False,
        "production_consumer_enabled": False,
        "fixture_authority_only": True,
        "live_authority_verified": False,
        "user_accounting_effect": False,
        "transport_reachable": False,
    }
    pair_hash = signed_fixture_authority_pair_v1_sha256(material)
    return SignedFixtureAuthorityPairV1.model_validate(
        {
            **material,
            "pair_sha256": pair_hash,
            "signature_ed25519": _sign_pair_hash(pair_hash),
        }
    )


def genesis_pair(*, issued_at_ms: int = 1_000) -> SignedFixtureAuthorityPairV1:
    return signed_fixture_pair(
        revision=0,
        previous_pair_sha256="0" * 64,
        issued_at_ms=issued_at_ms,
    )


def successor_pair(
    current: SignedFixtureAuthorityPairV1,
    *,
    issued_at_ms: int | None = None,
    capability_head_sha256: str | None = None,
    source_head_sha256: str | None = None,
) -> SignedFixtureAuthorityPairV1:
    next_cap_head = CAPABILITY_HEAD_1 if capability_head_sha256 is None else capability_head_sha256
    next_source_head = (
        current.source_head_sha256 if source_head_sha256 is None else source_head_sha256
    )
    return signed_fixture_pair(
        revision=current.revision + 1,
        previous_pair_sha256=current.pair_sha256,
        issued_at_ms=current.issued_at_ms + 1 if issued_at_ms is None else issued_at_ms,
        capability_head_sha256=next_cap_head,
        capability_epoch=current.capability_epoch
        + (1 if next_cap_head != current.capability_head_sha256 else 0),
        source_head_sha256=next_source_head,
        source_epoch=current.source_epoch
        + (1 if next_source_head != current.source_head_sha256 else 0),
    )


class OpaqueOwnerPathAuthority:
    __slots__ = ()

    def __repr__(self) -> str:
        return "OpaqueOwnerPathAuthority(redacted=True)"

    def __reduce__(self) -> Never:
        raise TypeError("owner path authority is process-local")


class _ClearingKeyContext(AbstractContextManager[bytearray]):
    def __init__(self, provider: ClearingFixtureKeyProvider, key: bytes) -> None:
        self._provider = provider
        self._key = key
        self._opened: bytearray | None = None

    def __enter__(self) -> bytearray:
        opened = bytearray(self._key)
        self._opened = opened
        self._provider.opened_buffers.append(opened)
        return opened

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        opened = self._opened
        if opened is not None:
            opened[:] = b"\x00" * len(opened)
            self._provider.cleared_snapshots.append(bytes(opened))
        self._opened = None


@dataclass(slots=True)
class ClearingFixtureKeyProvider:
    expected_authority: object
    keys: dict[str, bytes] = field(default_factory=lambda: {KEY_VERSION: DATA_KEY})
    calls: list[tuple[int, str, str, str]] = field(default_factory=list)
    opened_buffers: list[bytearray] = field(default_factory=list)
    cleared_snapshots: list[bytes] = field(default_factory=list)

    def open_aes256gcm_key(
        self,
        *,
        owner_path_authority: object,
        owner_path_discriminator: str,
        store_id: str,
        key_version: str,
    ) -> AbstractContextManager[bytearray]:
        self.calls.append(
            (id(owner_path_authority), owner_path_discriminator, store_id, key_version)
        )
        key = self.keys.get(key_version)
        if (
            owner_path_authority is not self.expected_authority
            or owner_path_discriminator != OWNER_PATH_DISCRIMINATOR
            or store_id != STORE_ID
            or key is None
        ):
            raise ValueError("fixture key unavailable")
        return _ClearingKeyContext(self, key)

    def assert_all_opened_keys_cleared(self) -> None:
        assert self.opened_buffers
        assert all(buffer == bytearray(32) for buffer in self.opened_buffers)
        assert all(snapshot == b"\x00" * 32 for snapshot in self.cleared_snapshots)


@dataclass(frozen=True, slots=True)
class PrivatePaidEffectAdmissionFixtureCase:
    authority: OpaqueOwnerPathAuthority
    key_provider: ClearingFixtureKeyProvider
    store: PrivatePaidEffectAdmissionFixtureStoreV1
    genesis: SignedFixtureAuthorityPairV1


class CrashAfterAdmissionInsertFixtureStoreV1(PrivatePaidEffectAdmissionFixtureStoreV1):
    """Test-only process terminator after INSERT and before outer COMMIT."""

    __slots__ = ()

    def _seal_admission(
        self,
        connection: sqlite3.Connection,
        candidate: FixtureAdmissionCandidateV1,
        now_ms: int,
    ) -> dict[str, str]:
        super()._seal_admission(connection, candidate, now_ms)
        os._exit(79)


def fixture_store_case(root: Path) -> PrivatePaidEffectAdmissionFixtureCase:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    authority = OpaqueOwnerPathAuthority()
    key_provider = ClearingFixtureKeyProvider(authority)
    genesis = genesis_pair()
    store = PrivatePaidEffectAdmissionFixtureStoreV1(
        root / "paid-effect-fixture.sqlite3",
        owner_path_authority=authority,
        owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
        store_id=STORE_ID,
        key_version=KEY_VERSION,
        fixture_authority_verification_keys=fixture_pair_verification_keys(),
        key_provider=key_provider,
    )
    return PrivatePaidEffectAdmissionFixtureCase(
        authority=authority,
        key_provider=key_provider,
        store=store,
        genesis=genesis,
    )


def admission_candidate(
    *,
    logical_effect_key: str,
    hold_id: str,
    projected_max_cents: int,
    authority: SignedFixtureAuthorityPairV1,
    router_role: Literal["planner", "gatherer", "verifier", "synthesizer"] = "gatherer",
    source_receipt_pairs: tuple[FixtureSourceReceiptPairV1, ...] | None = None,
) -> FixtureAdmissionCandidateV1:
    receipts = (
        (FixtureSourceReceiptPairV1(receipt_id="opsr5_" + "ee" * 12, receipt_sha256="ff" * 32),)
        if source_receipt_pairs is None and router_role != "planner"
        else (() if source_receipt_pairs is None else source_receipt_pairs)
    )
    return FixtureAdmissionCandidateV1(
        owner_path_discriminator=OWNER_PATH_DISCRIMINATOR,
        logical_effect_key=logical_effect_key,
        hold_id=hold_id,
        projected_max_cents=projected_max_cents,
        authority_revision=authority.revision,
        fixture_pair_sha256=authority.pair_sha256,
        capability_registry_id=authority.capability_registry_id,
        capability_head_sha256=authority.capability_head_sha256,
        capability_epoch=authority.capability_epoch,
        source_registry_id=authority.source_registry_id,
        source_head_sha256=authority.source_head_sha256,
        source_epoch=authority.source_epoch,
        operation_id="op:fixture/1",
        job_id="job:fixture/1",
        execution_id="exec:fixture/1",
        stage_id="stage:fixture/1",
        queue_operation_id="queue:fixture/1",
        queue_cursor="cursor:fixture/1",
        worker_id="worker:fixture/1",
        provider="provider.fixture",
        model="model.fixture",
        route="route.fixture",
        account_scope="acct.fixture",
        project_scope="proj.fixture",
        api_mode="fixture",
        processing_region="local",
        output_schema="fixture.output.v1",
        router_role=router_role,
        consent_receipt_sha256="55" * 32,
        consent_config_sha256="66" * 32,
        policy_v4_sha256="77" * 32,
        capability_v4_sha256="88" * 32,
        core_v4_sha256="99" * 32,
        receipt_v7_sha256="aa" * 32,
        envelope_v4_sha256="bb" * 32,
        request_material_sha256="cc" * 32,
        owner_job_state_version=1,
        lease_generation=1,
        lease_exclusive_until_ms=10_000,
        source_revision=1,
        approved_ceiling_cents=projected_max_cents,
        source_selector="opsbs1_" + "dd" * 32,
        source_receipt_pairs=receipts,
        provider_scoped_idempotency_key="idem-fixture-1",
        maximum_output_bytes=4096,
    )


__all__ = [
    "CAPABILITY_HEAD_0",
    "CAPABILITY_HEAD_1",
    "KEY_VERSION",
    "OWNER_PATH_DISCRIMINATOR",
    "SOURCE_HEAD_0",
    "SOURCE_HEAD_1",
    "STORE_ID",
    "ClearingFixtureKeyProvider",
    "CrashAfterAdmissionInsertFixtureStoreV1",
    "OpaqueOwnerPathAuthority",
    "PrivatePaidEffectAdmissionFixtureCase",
    "admission_candidate",
    "fixture_pair_verification_keys",
    "fixture_store_case",
    "genesis_pair",
    "signed_fixture_pair",
    "successor_pair",
]
