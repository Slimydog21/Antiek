"""Complete test-only PolicyV3/CapabilityV3 authority fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from substrate.midnight_oil.private_output_policy_v3 import (
    OwnerPrivateOutputPolicyV3,
    build_owner_private_output_policy_v3,
)
from substrate.midnight_oil.private_provider_capability_v3 import (
    PrivateProviderCapabilityV3CurrentResolver,
    PrivateProviderProcessingCapabilityV3,
    signed_private_provider_capability_v3,
)
from substrate.midnight_oil.private_provider_composition import (
    DurablePrivateProviderRevocationHeadStore,
    PrivateProviderRevocationHeadV1,
    signed_private_provider_revocation_head,
)
from substrate.midnight_oil.private_provider_policy import (
    signed_private_provider_revocation_snapshot,
)
from tests.support import owner_private_v2 as v2
from tests.support.owner_private_v2 import OwnerPrivateV2Case
from tests.test_midnight_oil_private_provider_authority import (
    _CAP_KEY_ID,
    _CAP_PRIVATE,
    _REV_KEY_ID,
    _REV_PRIVATE,
)

NOW_MS = v2.NOW_MS
REQUIRED_UNTIL_MS = v2.REQUIRED_UNTIL_MS
V3_KEY_ID = "private-capability-v3-issuer"
V3_PRIVATE = bytes(value ^ 0xC3 for value in range(32))


@dataclass(frozen=True)
class OwnerPrivateV3Case:
    v2: OwnerPrivateV2Case
    policy: OwnerPrivateOutputPolicyV3
    capability: PrivateProviderProcessingCapabilityV3
    store: DurablePrivateProviderRevocationHeadStore
    floor: PrivateProviderRevocationHeadV1
    resolver: PrivateProviderCapabilityV3CurrentResolver


def revocation_head(
    *,
    epoch: int,
    issued_at_ms: int,
    previous_head_sha256: str,
    revoked: tuple[str, ...] = (),
) -> PrivateProviderRevocationHeadV1:
    snapshot = signed_private_provider_revocation_snapshot(
        epoch=epoch,
        issued_at_ms=issued_at_ms,
        revoked_capability_sha256s=revoked,
        key_id=_REV_KEY_ID,
        signing_key=_REV_PRIVATE,
    )
    return signed_private_provider_revocation_head(
        snapshot=snapshot,
        previous_head_sha256=previous_head_sha256,
        key_id=_REV_KEY_ID,
        signing_key=_REV_PRIVATE,
    )


def capability_v3(
    case_v2: OwnerPrivateV2Case | None = None,
    *,
    key_id: str = V3_KEY_ID,
    signing_key: bytes = V3_PRIVATE,
    issued_at_ms: int = 2_001,
    not_before_ms: int = 2_001,
    expires_at_ms: int = 90_000,
    revocation_epoch: int = 2,
) -> PrivateProviderProcessingCapabilityV3:
    case = case_v2 or v2.owner_private_v2_case()
    return signed_private_provider_capability_v3(
        route_evidence=case.capability,
        max_private_input_bytes=case.capability.route_evidence.max_private_input_bytes,
        max_output_bytes=case.capability.max_output_bytes,
        revocation_epoch=revocation_epoch,
        issued_at_ms=issued_at_ms,
        not_before_ms=not_before_ms,
        expires_at_ms=expires_at_ms,
        key_id=key_id,
        signing_key=signing_key,
    )


def owner_private_v3_case(
    root: Path,
    *,
    revoked: tuple[str, ...] = (),
    role: str = "gatherer",
) -> OwnerPrivateV3Case:
    case_v2 = v2.owner_private_v2_case(role=role)  # type: ignore[arg-type]
    policy = build_owner_private_output_policy_v3()
    capability = capability_v3(case_v2)
    floor = revocation_head(
        epoch=2,
        issued_at_ms=2_000,
        previous_head_sha256="f" * 64,
        revoked=revoked,
    )
    store = DurablePrivateProviderRevocationHeadStore(
        root / "revocations.sqlite3",
        verification_keys={_REV_KEY_ID: v2.public_key(_REV_PRIVATE)},
        trusted_floor_sha256=floor.head_sha256,
    )
    store.admit_trusted_floor(floor)
    resolver = PrivateProviderCapabilityV3CurrentResolver(
        (capability,),
        capability_v3_verification_keys={V3_KEY_ID: v2.public_key(V3_PRIVATE)},
        capability_v2_verification_keys={v2._V2_KEY_ID: v2.public_key(v2._V2_PRIVATE)},
        capability_v1_verification_keys={_CAP_KEY_ID: v2.public_key(_CAP_PRIVATE)},
        revocation_verification_keys={_REV_KEY_ID: v2.public_key(_REV_PRIVATE)},
        revocation_store=store,
    )
    return OwnerPrivateV3Case(case_v2, policy, capability, store, floor, resolver)


__all__ = [
    "NOW_MS",
    "REQUIRED_UNTIL_MS",
    "V3_KEY_ID",
    "V3_PRIVATE",
    "OwnerPrivateV3Case",
    "capability_v3",
    "owner_private_v3_case",
    "revocation_head",
]
