from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from substrate.midnight_oil.private_provider_capability_v2 import (
    private_provider_capability_v2_signature,
)
from substrate.midnight_oil.private_provider_capability_v3 import (
    _CAPABILITY_V3_DOMAIN,
    _MODULE_SOURCE_V3_DOMAIN,
    _RESOLVER_CONTRACT_V1_DOMAIN,
    _SIGNATURE_V3_DOMAIN,
    PRIVATE_PROVIDER_CAPABILITY_V3_CURRENT_RESOLVER_CONTRACT_SHA256,
    PRIVATE_PROVIDER_CAPABILITY_V3_MODULE_SOURCE_SHA256,
    PrivateProviderCapabilityV3CurrentResolver,
    PrivateProviderCapabilityV3ResolutionRejected,
    PrivateProviderProcessingCapabilityV3,
    ResolvedPrivateProviderCapabilityV3,
    private_provider_capability_v3_module_source_sha256,
    private_provider_capability_v3_resolution_witness_sha256,
    private_provider_capability_v3_sha256,
    require_private_provider_capability_v3_module_source,
    verify_private_provider_capability_v3,
)
from substrate.midnight_oil.private_provider_composition import (
    DurablePrivateProviderRevocationHeadStore,
    InvalidPrivateProviderRevocationStore,
)
from tests.support import owner_private_v2 as v2
from tests.support.owner_private_v3 import (
    NOW_MS,
    REQUIRED_UNTIL_MS,
    V3_KEY_ID,
    V3_PRIVATE,
    capability_v3,
    owner_private_v3_case,
    revocation_head,
)
from tests.test_midnight_oil_private_provider_authority import (
    _CAP_KEY_ID,
    _CAP_PRIVATE,
    _REV_KEY_ID,
    _REV_PRIVATE,
)


def _keyrings() -> tuple[dict[str, bytes], dict[str, bytes], dict[str, bytes], dict[str, bytes]]:
    return (
        {V3_KEY_ID: v2.public_key(V3_PRIVATE)},
        {v2._V2_KEY_ID: v2.public_key(v2._V2_PRIVATE)},
        {_CAP_KEY_ID: v2.public_key(_CAP_PRIVATE)},
        {_REV_KEY_ID: v2.public_key(_REV_PRIVATE)},
    )


def _resolver(
    capability: PrivateProviderProcessingCapabilityV3,
    store: DurablePrivateProviderRevocationHeadStore,
    *,
    rings: tuple[dict[str, bytes], dict[str, bytes], dict[str, bytes], dict[str, bytes]]
    | None = None,
) -> PrivateProviderCapabilityV3CurrentResolver:
    v3_keys, v2_keys, v1_keys, revocation_keys = rings or _keyrings()
    return PrivateProviderCapabilityV3CurrentResolver(
        (capability,),
        capability_v3_verification_keys=v3_keys,
        capability_v2_verification_keys=v2_keys,
        capability_v1_verification_keys=v1_keys,
        revocation_verification_keys=revocation_keys,
        revocation_store=store,
    )


def test_capability_v3_signature_self_hash_nested_chain_and_domains() -> None:
    capability = capability_v3()
    v3_keys, v2_keys, v1_keys, _revocation = _keyrings()
    assert PRIVATE_PROVIDER_CAPABILITY_V3_MODULE_SOURCE_SHA256 == (
        "7bca6c2a5531d27f6097df200ed24ae8d2b63ad3792567465f2c9dd0189d6d7c"
    )
    assert PRIVATE_PROVIDER_CAPABILITY_V3_CURRENT_RESOLVER_CONTRACT_SHA256 == (
        "662eea6e32db95fcee1ba45f68959a89c8765076d423dfe606c3d6faf69cad1e"
    )
    assert _CAPABILITY_V3_DOMAIN == b"antiek.midnight-oil.private-provider-capability.v3\x00"
    assert _SIGNATURE_V3_DOMAIN == (
        b"antiek.midnight-oil.private-provider-capability-signature.v3\x00"
    )
    assert _MODULE_SOURCE_V3_DOMAIN.endswith(b"semantic-source.v1\x00")
    assert _RESOLVER_CONTRACT_V1_DOMAIN.endswith(b"current-resolver.v1\x00")
    assert capability.capability_id == "ppcap3_" + capability.capability_sha256[:24]
    assert capability.capability_sha256 == private_provider_capability_v3_sha256(capability)
    assert capability.route_evidence_sha256 == capability.route_evidence.capability_sha256
    verify_private_provider_capability_v3(
        capability,
        capability_v3_verification_keys=v3_keys,
        capability_v2_verification_keys=v2_keys,
        capability_v1_verification_keys=v1_keys,
    )
    for field in (
        "request_core_v3_authorized",
        "receipt_v6_authorized",
        "provider_execution_authorized",
        "checkpoint_authorized",
        "transition_authorized",
        "confers_execution_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
    ):
        assert getattr(capability, field) is False


@pytest.mark.parametrize(
    "field",
    (
        "route_evidence_sha256",
        "output_policy_v3_sha256",
        "source_adapter_contract_sha256",
        "source_adapter_implementation_sha256",
        "source_adapter_source_set_sha256",
        "checker_v2_contract_sha256",
        "checker_v2_sha256",
        "checker_v2_corpus_sha256",
        "current_resolver_contract_sha256",
        "capability_sha256",
    ),
)
def test_capability_v3_identity_mutations_reject(field: str) -> None:
    raw = capability_v3().model_dump(mode="python")
    raw[field] = "0" * 64
    with pytest.raises((ValidationError, ValueError)):
        PrivateProviderProcessingCapabilityV3.model_validate(raw)


@pytest.mark.parametrize(
    "field",
    (
        "request_core_v3_authorized",
        "receipt_v6_authorized",
        "provider_execution_authorized",
        "checkpoint_authorized",
        "transition_authorized",
        "confers_transition_authority",
        "confers_execution_authority",
        "confers_sink_authority",
        "production_consumer_enabled",
    ),
)
def test_capability_v3_authority_mutations_reject(field: str) -> None:
    raw = capability_v3().model_dump(mode="python")
    raw[field] = True
    with pytest.raises(ValidationError):
        PrivateProviderProcessingCapabilityV3.model_validate(raw)


def test_capability_v3_role_set_is_exact_and_ordered() -> None:
    raw = capability_v3().model_dump(mode="python")
    raw["allowed_router_roles"] = tuple(reversed(raw["allowed_router_roles"]))
    with pytest.raises((ValidationError, ValueError)):
        PrivateProviderProcessingCapabilityV3.model_validate(raw)


def test_cross_domain_signature_key_purpose_and_nested_forgery_reject() -> None:
    capability = capability_v3()
    v3_keys, v2_keys, v1_keys, _revocation = _keyrings()
    wrong_domain = capability.model_copy(
        update={
            "signature_ed25519": private_provider_capability_v2_signature(
                capability.capability_sha256, signing_key=V3_PRIVATE
            )
        }
    )
    forged_nested = capability.model_copy(
        update={
            "route_evidence": capability.route_evidence.model_copy(
                update={"signature_ed25519": "0" * 128}
            )
        }
    )
    for row in (wrong_domain, forged_nested):
        with pytest.raises(ValueError, match="unavailable"):
            verify_private_provider_capability_v3(
                row,
                capability_v3_verification_keys=v3_keys,
                capability_v2_verification_keys=v2_keys,
                capability_v1_verification_keys=v1_keys,
            )
    raw = capability.model_dump(mode="python")
    raw["key_purpose"] = "owner_private_provider_capability_v2"
    with pytest.raises(ValidationError):
        PrivateProviderProcessingCapabilityV3.model_validate(raw)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("issued_at_ms", 999),
        ("not_before_ms", 100_000),
        ("expires_at_ms", 100_001),
        ("revocation_epoch", 1),
    ),
)
def test_capability_v3_timing_and_horizon_construction_bounds_reject(
    field: str, value: int
) -> None:
    kwargs = {
        "issued_at_ms": 2_001,
        "not_before_ms": 2_001,
        "expires_at_ms": 90_000,
        "revocation_epoch": 2,
    }
    kwargs[field] = value
    with pytest.raises((ValidationError, ValueError)):
        capability_v3(
            issued_at_ms=kwargs["issued_at_ms"],
            not_before_ms=kwargs["not_before_ms"],
            expires_at_ms=kwargs["expires_at_ms"],
            revocation_epoch=kwargs["revocation_epoch"],
        )


def test_durable_current_happy_path_and_exact_witness(tmp_path: Path) -> None:
    case = owner_private_v3_case(tmp_path)
    resolved = case.resolver.resolve_current(
        capability_id=case.capability.capability_id,
        capability_sha256=case.capability.capability_sha256,
        now_ms=NOW_MS,
        required_until_ms=REQUIRED_UNTIL_MS,
    )
    assert type(resolved) is ResolvedPrivateProviderCapabilityV3
    witness = resolved.witness
    assert witness.resolver_contract_sha256 == (
        PRIVATE_PROVIDER_CAPABILITY_V3_CURRENT_RESOLVER_CONTRACT_SHA256
    )
    assert witness.capability_v3_sha256 == case.capability.capability_sha256
    assert witness.capability_v2_sha256 == case.v2.capability.capability_sha256
    assert witness.capability_v1_sha256 == (case.v2.capability.route_evidence.capability_sha256)
    assert witness.current_head_sha256 == case.floor.head_sha256
    assert witness.trusted_floor_sha256 == case.floor.head_sha256
    assert witness.current_epoch == case.floor.epoch
    assert witness.current_snapshot_sha256 == case.floor.snapshot.snapshot_sha256
    assert witness.current_head_issued_at_ms == case.floor.issued_at_ms
    assert witness.checked_at_ms == NOW_MS
    assert witness.required_until_ms == REQUIRED_UNTIL_MS
    assert witness.available is True
    assert witness.single_resolution_evidence is True
    assert witness.witness_id == "ppcw3_" + witness.witness_sha256[:24]
    assert witness.witness_sha256 == (
        private_provider_capability_v3_resolution_witness_sha256(witness)
    )
    for value in (resolved, witness, resolved.capability):
        assert "redacted=True" in repr(value)
    for field in (
        "portable_transition_authority",
        "confers_execution_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
    ):
        assert getattr(witness, field) is False
    for field in (
        "confers_execution_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
    ):
        assert getattr(resolved, field) is False


@pytest.mark.parametrize("revoked_level", ("v3", "v2", "v1"))
def test_revocation_union_rejects_every_nested_capability(
    tmp_path: Path, revoked_level: str
) -> None:
    preview = capability_v3()
    digests = {
        "v3": preview.capability_sha256,
        "v2": preview.route_evidence.capability_sha256,
        "v1": preview.route_evidence.route_evidence.capability_sha256,
    }
    case = owner_private_v3_case(tmp_path, revoked=(digests[revoked_level],))
    with pytest.raises(PrivateProviderCapabilityV3ResolutionRejected):
        case.resolver.resolve_current(
            capability_id=case.capability.capability_id,
            capability_sha256=case.capability.capability_sha256,
            now_ms=NOW_MS,
            required_until_ms=REQUIRED_UNTIL_MS,
        )


def test_resolve_current_rereads_durable_state_every_call(tmp_path: Path) -> None:
    case = owner_private_v3_case(tmp_path)

    def resolve() -> ResolvedPrivateProviderCapabilityV3:
        return case.resolver.resolve_current(
            capability_id=case.capability.capability_id,
            capability_sha256=case.capability.capability_sha256,
            now_ms=NOW_MS,
            required_until_ms=REQUIRED_UNTIL_MS,
        )

    assert resolve().witness.current_epoch == 2
    successor = revocation_head(
        epoch=3,
        issued_at_ms=2_001,
        previous_head_sha256=case.floor.head_sha256,
        revoked=(case.capability.capability_sha256,),
    )
    outcome = case.store.compare_and_set(
        expected_head_sha256=case.floor.head_sha256,
        next_head=successor,
        now_ms=NOW_MS,
    )
    assert outcome.applied is True
    with pytest.raises(PrivateProviderCapabilityV3ResolutionRejected):
        resolve()


def test_wrong_floor_key_fork_stale_future_and_horizon_reject(tmp_path: Path) -> None:
    case = owner_private_v3_case(tmp_path / "valid")
    wrong_floor = DurablePrivateProviderRevocationHeadStore(
        tmp_path / "wrong-floor.sqlite3",
        verification_keys={_REV_KEY_ID: v2.public_key(_REV_PRIVATE)},
        trusted_floor_sha256="0" * 64,
    )
    with pytest.raises(ValueError, match="floor conflicts"):
        wrong_floor.admit_trusted_floor(case.floor)
    wrong_key = DurablePrivateProviderRevocationHeadStore(
        tmp_path / "wrong-key.sqlite3",
        verification_keys={_REV_KEY_ID: v2.public_key(V3_PRIVATE)},
        trusted_floor_sha256=case.floor.head_sha256,
    )
    with pytest.raises(ValueError):
        wrong_key.admit_trusted_floor(case.floor)
    first = revocation_head(
        epoch=3,
        issued_at_ms=2_001,
        previous_head_sha256=case.floor.head_sha256,
    )
    fork = revocation_head(
        epoch=3,
        issued_at_ms=2_002,
        previous_head_sha256=case.floor.head_sha256,
    )
    assert case.store.compare_and_set(
        expected_head_sha256=case.floor.head_sha256, next_head=first, now_ms=NOW_MS
    ).applied
    assert not case.store.compare_and_set(
        expected_head_sha256=case.floor.head_sha256, next_head=fork, now_ms=NOW_MS
    ).applied
    for now_ms, required_until_ms in (
        (case.capability.expires_at_ms, case.capability.expires_at_ms),
        (NOW_MS, case.capability.expires_at_ms),
        (NOW_MS - 2, NOW_MS),
        (302_002, 302_002),
    ):
        with pytest.raises(PrivateProviderCapabilityV3ResolutionRejected):
            case.resolver.resolve_current(
                capability_id=case.capability.capability_id,
                capability_sha256=case.capability.capability_sha256,
                now_ms=now_ms,
                required_until_ms=required_until_ms,
            )
    reanchored = DurablePrivateProviderRevocationHeadStore(
        case.store.path,
        verification_keys={_REV_KEY_ID: v2.public_key(_REV_PRIVATE)},
        trusted_floor_sha256=first.head_sha256,
    )
    reanchored.admit_trusted_floor(first)
    rolled_back = DurablePrivateProviderRevocationHeadStore(
        case.store.path,
        verification_keys={_REV_KEY_ID: v2.public_key(_REV_PRIVATE)},
        trusted_floor_sha256=case.floor.head_sha256,
    )
    with pytest.raises(InvalidPrivateProviderRevocationStore, match="not in current history"):
        rolled_back.admit_trusted_floor(case.floor)


@pytest.mark.parametrize("reuse", ("id", "bytes"))
@pytest.mark.parametrize("other_ring", (1, 2, 3))
def test_v3_v2_v1_revocation_key_separation_rejects(
    tmp_path: Path, reuse: str, other_ring: int
) -> None:
    case = owner_private_v3_case(tmp_path / "base")
    rings = list(_keyrings())
    other_key_id, other_public_key = next(iter(rings[other_ring].items()))
    if reuse == "id":
        rings[0] = {other_key_id: v2.public_key(V3_PRIVATE)}
    else:
        rings[0] = {V3_KEY_ID: other_public_key}
    with pytest.raises(ValueError, match="purpose reuse conflicts"):
        _resolver(case.capability, case.store, rings=tuple(rings))  # type: ignore[arg-type]


def test_keyring_cardinality_and_key_id_bounds(tmp_path: Path) -> None:
    case = owner_private_v3_case(tmp_path)
    rings = list(_keyrings())
    bounded_v3 = dict(rings[0])
    bounded_v3.update({f"v3-extra-{index}": bytes([index]) * 32 for index in range(1, 8)})
    rings[0] = bounded_v3
    _resolver(case.capability, case.store, rings=tuple(rings))  # type: ignore[arg-type]

    too_many_v3 = dict(bounded_v3)
    too_many_v3["v3-extra-8"] = bytes([8]) * 32
    rings[0] = too_many_v3
    with pytest.raises(ValueError, match="keyring bound conflicts"):
        _resolver(case.capability, case.store, rings=tuple(rings))  # type: ignore[arg-type]

    rings = list(_keyrings())
    rings[0] = {"invalid key id": v2.public_key(V3_PRIVATE)}
    with pytest.raises(ValueError, match="keyring conflicts"):
        _resolver(case.capability, case.store, rings=tuple(rings))  # type: ignore[arg-type]


def test_subclass_proxy_coercion_transition_and_opaque_errors_reject(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    case = owner_private_v3_case(tmp_path)

    class CapabilitySubclass(PrivateProviderProcessingCapabilityV3):
        pass

    subclass = CapabilitySubclass.model_validate(case.capability.model_dump(mode="python"))
    with pytest.raises(ValueError, match="row conflicts"):
        _resolver(subclass, case.store)
    with pytest.raises(ValueError, match="durable store conflicts"):
        PrivateProviderCapabilityV3CurrentResolver(
            (case.capability,),
            capability_v3_verification_keys=_keyrings()[0],
            capability_v2_verification_keys=_keyrings()[1],
            capability_v1_verification_keys=_keyrings()[2],
            revocation_verification_keys=_keyrings()[3],
            revocation_store=object(),  # type: ignore[arg-type]
        )
    canary = "PRIVATE_V3_RESOLUTION_CANARY_82d9"
    with pytest.raises(PrivateProviderCapabilityV3ResolutionRejected) as raised:
        case.resolver.resolve_current(
            capability_id=canary,
            capability_sha256=case.capability.capability_sha256,
            now_ms=NOW_MS,
            required_until_ms=REQUIRED_UNTIL_MS,
        )
    assert canary not in str(raised.value) + repr(raised.value) + caplog.text
    assert raised.value.__cause__ is None
    resolved = case.resolver.resolve_current(
        capability_id=case.capability.capability_id,
        capability_sha256=case.capability.capability_sha256,
        now_ms=NOW_MS,
        required_until_ms=REQUIRED_UNTIL_MS,
    )
    with pytest.raises((AttributeError, TypeError, ValueError)):
        case.store.compare_and_set(
            expected_head_sha256=case.floor.head_sha256,
            next_head=resolved.witness,  # type: ignore[arg-type]
            now_ms=NOW_MS,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("capability_id", b"not-a-string"),
        ("capability_sha256", bytearray(b"not-a-string")),
        ("now_ms", True),
        ("required_until_ms", "3000"),
    ),
)
def test_resolver_rejects_input_coercion_opaquely(
    tmp_path: Path, field: str, value: object
) -> None:
    case = owner_private_v3_case(tmp_path)
    capability_id: object = case.capability.capability_id
    capability_sha256: object = case.capability.capability_sha256
    now_ms: object = NOW_MS
    required_until_ms: object = REQUIRED_UNTIL_MS
    if field == "capability_id":
        capability_id = value
    elif field == "capability_sha256":
        capability_sha256 = value
    elif field == "now_ms":
        now_ms = value
    else:
        required_until_ms = value
    with pytest.raises(PrivateProviderCapabilityV3ResolutionRejected) as raised:
        case.resolver.resolve_current(
            capability_id=cast(str, capability_id),
            capability_sha256=cast(str, capability_sha256),
            now_ms=cast(int, now_ms),
            required_until_ms=cast(int, required_until_ms),
        )
    assert str(value) not in str(raised.value)


@pytest.mark.parametrize(
    ("capability_id", "capability_sha256"),
    (
        ("x" * 1_000_000, "0" * 64),
        ("ppcap3_" + "0" * 24, "x" * 1_000_000),
        ("ppcap3_" + "z" * 24, "0" * 64),
        ("ppcap3_" + "0" * 24, "Z" * 64),
    ),
)
def test_malformed_identifiers_reject_before_durable_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capability_id: str,
    capability_sha256: str,
) -> None:
    case = owner_private_v3_case(tmp_path)

    def unexpected_current(*_args: object, **_kwargs: object) -> object:
        pytest.fail("durable audit must not run for malformed identifiers")

    monkeypatch.setattr(DurablePrivateProviderRevocationHeadStore, "current", unexpected_current)
    with pytest.raises(PrivateProviderCapabilityV3ResolutionRejected):
        case.resolver.resolve_current(
            capability_id=capability_id,
            capability_sha256=capability_sha256,
            now_ms=NOW_MS,
            required_until_ms=REQUIRED_UNTIL_MS,
        )


def test_semantic_source_attestation_drift_and_resolve_no_source_file_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert private_provider_capability_v3_module_source_sha256() == (
        PRIVATE_PROVIDER_CAPABILITY_V3_MODULE_SOURCE_SHA256
    )
    require_private_provider_capability_v3_module_source()
    original = Path.read_bytes

    def drift(path: Path) -> bytes:
        return original(path) + b"\nCAPABILITY_V3_DRIFT = True\n"

    monkeypatch.setattr(Path, "read_bytes", drift)
    with pytest.raises(RuntimeError, match="implementation conflicts"):
        require_private_provider_capability_v3_module_source()
    monkeypatch.setattr(Path, "read_bytes", lambda _path: pytest.fail("source file I/O"))
    case = owner_private_v3_case(tmp_path)
    case.resolver.resolve_current(
        capability_id=case.capability.capability_id,
        capability_sha256=case.capability.capability_sha256,
        now_ms=NOW_MS,
        required_until_ms=REQUIRED_UNTIL_MS,
    )
