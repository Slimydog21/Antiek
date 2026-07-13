"""Signed, non-conferring CapabilityV3 and durable current-head resolution."""

from __future__ import annotations

import ast
import hashlib
import hmac
import json
import re
from collections.abc import Iterable, Mapping
from itertools import islice
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .private_output_checker_v2 import (
    PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256,
    PRIVATE_OUTPUT_CHECKER_V2_SHA256,
    PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256,
)
from .private_output_policy_v3 import OWNER_PRIVATE_OUTPUT_POLICY_V3_SHA256
from .private_output_source_adapter_v1 import (
    PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256,
    PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256,
    PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_SOURCE_SET_SHA256,
)
from .private_provider_capability_v2 import (
    PrivateProviderProcessingCapabilityV2,
    private_provider_capability_v2_sha256,
    verify_private_provider_capability_v2,
)
from .private_provider_composition import DurablePrivateProviderRevocationHeadStore
from .private_provider_policy import (
    MAX_PRIVATE_PROVIDER_CAPABILITIES,
    MAX_PRIVATE_PROVIDER_REVOCATION_REFERENCE_AGE_MS,
    private_provider_capability_sha256,
)

_CAPABILITY_V3_DOMAIN = b"antiek.midnight-oil.private-provider-capability.v3\x00"
_SIGNATURE_V3_DOMAIN = (
    b"antiek.midnight-oil.private-provider-capability-signature.v3\x00"
)
_MODULE_SOURCE_V3_DOMAIN = (
    b"antiek.midnight-oil.private-provider-capability-v3-semantic-source.v1\x00"
)
_RESOLVER_CONTRACT_V1_DOMAIN = (
    b"antiek.midnight-oil.private-provider-capability-v3-current-resolver.v1\x00"
)
_RESOLUTION_WITNESS_V1_DOMAIN = (
    b"antiek.midnight-oil.private-provider-capability-v3-resolution-witness.v1\x00"
)
_HEX64 = r"^[0-9a-f]{64}$"
_KEY_ID = r"^[A-Za-z0-9._-]{1,128}$"
_ROLES = ("gatherer", "planner", "synthesizer", "verifier")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + _canonical_json(value)).hexdigest()


def _same(first: str, second: str) -> bool:
    return hmac.compare_digest(first, second)


class _Closed(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, hide_input_in_errors=True
    )

    def __repr_args__(self) -> list[tuple[str | None, object]]:
        return [("redacted", True)]


class PrivateProviderProcessingCapabilityV3(_Closed):
    schema_version: Literal[3] = 3
    capability_id: str = Field(pattern=r"^ppcap3_[0-9a-f]{24}$")
    purpose: Literal["midnight_oil_owner_private_research_v3"] = (
        "midnight_oil_owner_private_research_v3"
    )
    route_evidence_kind: Literal["signed_capability_v2_nonconferring"] = (
        "signed_capability_v2_nonconferring"
    )
    route_evidence: PrivateProviderProcessingCapabilityV2
    route_evidence_sha256: str = Field(pattern=_HEX64)
    output_policy_v3_sha256: str = Field(pattern=_HEX64)
    source_adapter_contract_sha256: str = Field(pattern=_HEX64)
    source_adapter_implementation_sha256: str = Field(pattern=_HEX64)
    source_adapter_source_set_sha256: str = Field(pattern=_HEX64)
    checker_v2_contract_sha256: str = Field(pattern=_HEX64)
    checker_v2_sha256: str = Field(pattern=_HEX64)
    checker_v2_corpus_sha256: str = Field(pattern=_HEX64)
    current_resolver_contract_sha256: str = Field(pattern=_HEX64)
    allowed_router_roles: tuple[
        Literal["gatherer", "planner", "synthesizer", "verifier"], ...
    ] = Field(min_length=4, max_length=4)
    planner_source_rule: Literal["exactly_zero_publication_sources"] = (
        "exactly_zero_publication_sources"
    )
    non_planner_source_rule: Literal["one_to_eight_receipt_v5_sources"] = (
        "one_to_eight_receipt_v5_sources"
    )
    max_private_input_bytes: int = Field(ge=1, le=32_000)
    max_output_bytes: int = Field(ge=1, le=1_000_000)
    revocation_registry_id: Literal["antiek-private-provider-revocations-v1"] = (
        "antiek-private-provider-revocations-v1"
    )
    revocation_epoch: int = Field(ge=0)
    issued_at_ms: int = Field(ge=0)
    not_before_ms: int = Field(ge=0)
    expires_at_ms: int = Field(gt=0)
    key_id: str = Field(pattern=_KEY_ID)
    issuer_role: Literal["private_provider_capability_issuer"] = (
        "private_provider_capability_issuer"
    )
    key_purpose: Literal["owner_private_provider_capability_v3"] = (
        "owner_private_provider_capability_v3"
    )
    signature_scheme: Literal["ed25519"] = "ed25519"
    capability_sha256: str = Field(pattern=_HEX64)
    signature_ed25519: str = Field(pattern=r"^[0-9a-f]{128}$")
    request_core_v3_authorized: Literal[False] = False
    receipt_v6_authorized: Literal[False] = False
    provider_execution_authorized: Literal[False] = False
    checkpoint_authorized: Literal[False] = False
    transition_authorized: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    live_reverification_required: Literal[True] = True
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> PrivateProviderProcessingCapabilityV3:
        evidence = self.route_evidence
        if (
            not _same(
                self.route_evidence_sha256,
                private_provider_capability_v2_sha256(evidence),
            )
            or not _same(self.route_evidence_sha256, evidence.capability_sha256)
            or self.output_policy_v3_sha256 != OWNER_PRIVATE_OUTPUT_POLICY_V3_SHA256
            or self.source_adapter_contract_sha256
            != PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256
            or self.source_adapter_implementation_sha256
            != PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256
            or self.source_adapter_source_set_sha256
            != PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_SOURCE_SET_SHA256
            or self.checker_v2_contract_sha256
            != PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256
            or self.checker_v2_sha256 != PRIVATE_OUTPUT_CHECKER_V2_SHA256
            or self.checker_v2_corpus_sha256
            != PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256
            or self.current_resolver_contract_sha256
            != PRIVATE_PROVIDER_CAPABILITY_V3_CURRENT_RESOLVER_CONTRACT_SHA256
            or self.allowed_router_roles != _ROLES
            or self.max_private_input_bytes > evidence.route_evidence.max_private_input_bytes
            or self.max_output_bytes > evidence.max_output_bytes
            or self.revocation_registry_id != evidence.revocation_registry_id
            or self.revocation_epoch < evidence.revocation_epoch
            or not (
                evidence.not_before_ms
                <= self.issued_at_ms
                <= self.not_before_ms
                < self.expires_at_ms
                <= evidence.expires_at_ms
            )
        ):
            raise ValueError("private provider capability v3 contract conflicts")
        digest = private_provider_capability_v3_sha256(self)
        if not _same(self.capability_sha256, digest) or self.capability_id != (
            "ppcap3_" + digest[:24]
        ):
            raise ValueError("private provider capability v3 identity conflicts")
        return self


def _capability_material(
    capability: PrivateProviderProcessingCapabilityV3 | Mapping[str, object],
) -> dict[str, object]:
    raw = (
        capability.model_dump(mode="json")
        if isinstance(capability, BaseModel)
        else dict(capability)
    )
    return {
        key: value
        for key, value in raw.items()
        if key not in {"capability_id", "capability_sha256", "signature_ed25519"}
    }


def private_provider_capability_v3_sha256(
    capability: PrivateProviderProcessingCapabilityV3 | Mapping[str, object],
) -> str:
    return _digest(_CAPABILITY_V3_DOMAIN, _capability_material(capability))


def private_provider_capability_v3_signature(
    capability_sha256: str, *, signing_key: bytes
) -> str:
    if type(signing_key) is not bytes or len(signing_key) != 32:
        raise ValueError("private provider v3 Ed25519 signing key must be 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(signing_key).sign(
        _SIGNATURE_V3_DOMAIN + capability_sha256.encode("ascii")
    ).hex()


def signed_private_provider_capability_v3(
    *,
    route_evidence: PrivateProviderProcessingCapabilityV2,
    max_private_input_bytes: int,
    max_output_bytes: int,
    revocation_epoch: int,
    issued_at_ms: int,
    not_before_ms: int,
    expires_at_ms: int,
    key_id: str,
    signing_key: bytes,
) -> PrivateProviderProcessingCapabilityV3:
    material: dict[str, object] = {
        "schema_version": 3,
        "purpose": "midnight_oil_owner_private_research_v3",
        "route_evidence_kind": "signed_capability_v2_nonconferring",
        "route_evidence": route_evidence.model_dump(mode="python"),
        "route_evidence_sha256": route_evidence.capability_sha256,
        "output_policy_v3_sha256": OWNER_PRIVATE_OUTPUT_POLICY_V3_SHA256,
        "source_adapter_contract_sha256": PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_CONTRACT_SHA256,
        "source_adapter_implementation_sha256": (
            PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_IMPLEMENTATION_SHA256
        ),
        "source_adapter_source_set_sha256": (
            PRIVATE_OUTPUT_SOURCE_ADAPTER_V1_SOURCE_SET_SHA256
        ),
        "checker_v2_contract_sha256": PRIVATE_OUTPUT_CHECKER_CONTRACT_V2_SHA256,
        "checker_v2_sha256": PRIVATE_OUTPUT_CHECKER_V2_SHA256,
        "checker_v2_corpus_sha256": PRIVATE_OUTPUT_EXECUTABLE_CORPUS_V2_SHA256,
        "current_resolver_contract_sha256": (
            PRIVATE_PROVIDER_CAPABILITY_V3_CURRENT_RESOLVER_CONTRACT_SHA256
        ),
        "allowed_router_roles": _ROLES,
        "planner_source_rule": "exactly_zero_publication_sources",
        "non_planner_source_rule": "one_to_eight_receipt_v5_sources",
        "max_private_input_bytes": max_private_input_bytes,
        "max_output_bytes": max_output_bytes,
        "revocation_registry_id": "antiek-private-provider-revocations-v1",
        "revocation_epoch": revocation_epoch,
        "issued_at_ms": issued_at_ms,
        "not_before_ms": not_before_ms,
        "expires_at_ms": expires_at_ms,
        "key_id": key_id,
        "issuer_role": "private_provider_capability_issuer",
        "key_purpose": "owner_private_provider_capability_v3",
        "signature_scheme": "ed25519",
        "request_core_v3_authorized": False,
        "receipt_v6_authorized": False,
        "provider_execution_authorized": False,
        "checkpoint_authorized": False,
        "transition_authorized": False,
        "confers_transition_authority": False,
        "confers_execution_authority": False,
        "confers_sink_authority": False,
        "live_reverification_required": True,
        "production_consumer_enabled": False,
    }
    digest = private_provider_capability_v3_sha256(material)
    return PrivateProviderProcessingCapabilityV3.model_validate(
        {
            **material,
            "capability_id": "ppcap3_" + digest[:24],
            "capability_sha256": digest,
            "signature_ed25519": private_provider_capability_v3_signature(
                digest, signing_key=signing_key
            ),
        }
    )


def verify_private_provider_capability_v3(
    capability: PrivateProviderProcessingCapabilityV3,
    *,
    capability_v3_verification_keys: Mapping[str, bytes],
    capability_v2_verification_keys: Mapping[str, bytes],
    capability_v1_verification_keys: Mapping[str, bytes],
) -> None:
    key = capability_v3_verification_keys.get(capability.key_id)
    try:
        if type(capability) is not PrivateProviderProcessingCapabilityV3:
            raise ValueError
        verify_private_provider_capability_v2(
            capability.route_evidence,
            verification_keys=capability_v2_verification_keys,
            route_evidence_verification_keys=capability_v1_verification_keys,
        )
        digest = private_provider_capability_v3_sha256(capability)
        if key is None or type(key) is not bytes or len(key) != 32:
            raise ValueError
        if not _same(digest, capability.capability_sha256):
            raise ValueError
        Ed25519PublicKey.from_public_bytes(key).verify(
            bytes.fromhex(capability.signature_ed25519),
            _SIGNATURE_V3_DOMAIN + digest.encode("ascii"),
        )
    except (InvalidSignature, TypeError, ValueError):
        raise ValueError("private provider capability v3 is unavailable") from None


def private_provider_capability_v3_module_source_sha256() -> str:
    """Attest this module AST while excluding only its self identity literal."""
    tree = ast.parse(Path(__file__).read_bytes(), filename=__file__)
    name = "PRIVATE_PROVIDER_CAPABILITY_V3_MODULE_SOURCE_SHA256"
    assignments = 0
    for statement in tree.body:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == name
        ):
            value = statement.value
            if (
                not isinstance(value, ast.Constant)
                or type(value.value) is not str
                or len(value.value) != 64
                or any(character not in "0123456789abcdef" for character in value.value)
            ):
                raise RuntimeError("private provider capability v3 source identity conflicts")
            assignments += 1
            statement.value = ast.Constant(value="<self-semantic-module-source-sha256>")
    stores = sum(
        isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Store)
        and node.id == name
        for node in ast.walk(tree)
    )
    if assignments != 1 or stores != 1:
        raise RuntimeError("private provider capability v3 source assignment conflicts")
    material = ast.dump(tree, annotate_fields=True, include_attributes=False).encode("utf-8")
    return hashlib.sha256(_MODULE_SOURCE_V3_DOMAIN + material).hexdigest()


PRIVATE_PROVIDER_CAPABILITY_V3_MODULE_SOURCE_SHA256 = (
    "7bca6c2a5531d27f6097df200ed24ae8d2b63ad3792567465f2c9dd0189d6d7c"
)


def require_private_provider_capability_v3_module_source() -> None:
    if not _same(
        private_provider_capability_v3_module_source_sha256(),
        PRIVATE_PROVIDER_CAPABILITY_V3_MODULE_SOURCE_SHA256,
    ):
        raise RuntimeError("private provider capability v3 implementation conflicts")


_RESOLVER_CONTRACT_MATERIAL_V1 = {
    "schema_version": 1,
    "resolver_id": "antiek-private-provider-capability-v3-current-resolver-v1",
    "implementation_sha256": PRIVATE_PROVIDER_CAPABILITY_V3_MODULE_SOURCE_SHA256,
    "durable_store_operation": "current(now_ms)_full_chain_audit_once_per_resolution",
    "signature_verification": "recursive_v3_v2_v1_every_resolution",
    "revocation_union": "v3_v2_v1_capability_sha256",
    "head_rules": "trusted_floor_registry_epoch_freshness_horizon",
    "key_separation": "v3_v2_v1_revocation_ids_and_public_bytes_disjoint",
    "resolver_inputs": "exact_capability_id_and_sha256_now_ms_required_until_ms",
    "witness_domain": _RESOLUTION_WITNESS_V1_DOMAIN.decode("ascii"),
    "witness_schema_version": 1,
    "witness_fields": (
        "schema_version",
        "witness_id",
        "witness_sha256",
        "resolver_contract_sha256",
        "capability_v3_sha256",
        "capability_v2_sha256",
        "capability_v1_sha256",
        "current_head_sha256",
        "trusted_floor_sha256",
        "current_epoch",
        "current_snapshot_sha256",
        "current_head_issued_at_ms",
        "checked_at_ms",
        "required_until_ms",
        "available",
        "single_resolution_evidence",
        "portable_transition_authority",
        "confers_execution_authority",
        "confers_sink_authority",
        "confers_transition_authority",
        "production_consumer_enabled",
    ),
    "witness_scope": "single_resolution_nonportable_nontransition_evidence",
    "confers_execution_authority": False,
    "confers_sink_authority": False,
    "confers_transition_authority": False,
    "production_consumer_enabled": False,
}
PRIVATE_PROVIDER_CAPABILITY_V3_CURRENT_RESOLVER_CONTRACT_SHA256 = _digest(
    _RESOLVER_CONTRACT_V1_DOMAIN, _RESOLVER_CONTRACT_MATERIAL_V1
)


def private_provider_capability_v3_resolution_witness_sha256(
    witness: PrivateProviderCapabilityV3ResolutionWitness | Mapping[str, object],
) -> str:
    raw = witness.model_dump(mode="json") if isinstance(witness, BaseModel) else dict(witness)
    material = {
        key: value for key, value in raw.items() if key not in {"witness_id", "witness_sha256"}
    }
    return _digest(_RESOLUTION_WITNESS_V1_DOMAIN, material)


class PrivateProviderCapabilityV3ResolutionWitness(_Closed):
    schema_version: Literal[1] = 1
    witness_id: str = Field(pattern=r"^ppcw3_[0-9a-f]{24}$")
    witness_sha256: str = Field(pattern=_HEX64)
    resolver_contract_sha256: str = Field(pattern=_HEX64)
    capability_v3_sha256: str = Field(pattern=_HEX64)
    capability_v2_sha256: str = Field(pattern=_HEX64)
    capability_v1_sha256: str = Field(pattern=_HEX64)
    current_head_sha256: str = Field(pattern=_HEX64)
    trusted_floor_sha256: str = Field(pattern=_HEX64)
    current_epoch: int = Field(ge=0)
    current_snapshot_sha256: str = Field(pattern=_HEX64)
    current_head_issued_at_ms: int = Field(ge=0)
    checked_at_ms: int = Field(ge=0)
    required_until_ms: int = Field(ge=0)
    available: Literal[True] = True
    single_resolution_evidence: Literal[True] = True
    portable_transition_authority: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> PrivateProviderCapabilityV3ResolutionWitness:
        digest = private_provider_capability_v3_resolution_witness_sha256(self)
        if (
            self.resolver_contract_sha256
            != PRIVATE_PROVIDER_CAPABILITY_V3_CURRENT_RESOLVER_CONTRACT_SHA256
            or self.required_until_ms < self.checked_at_ms
            or self.witness_sha256 != digest
            or self.witness_id != "ppcw3_" + digest[:24]
        ):
            raise ValueError("private provider capability v3 witness conflicts")
        return self


class ResolvedPrivateProviderCapabilityV3(_Closed):
    capability: PrivateProviderProcessingCapabilityV3 = Field(repr=False)
    witness: PrivateProviderCapabilityV3ResolutionWitness = Field(repr=False)
    confers_execution_authority: Literal[False] = False
    confers_sink_authority: Literal[False] = False
    confers_transition_authority: Literal[False] = False
    production_consumer_enabled: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> ResolvedPrivateProviderCapabilityV3:
        if (
            self.witness.capability_v3_sha256 != self.capability.capability_sha256
            or self.witness.capability_v2_sha256
            != self.capability.route_evidence.capability_sha256
            or self.witness.capability_v1_sha256
            != self.capability.route_evidence.route_evidence.capability_sha256
        ):
            raise ValueError("private provider capability v3 resolution conflicts")
        return self


class PrivateProviderCapabilityV3ResolutionRejected(ValueError):
    def __init__(self) -> None:
        super().__init__("private provider capability v3 resolution rejected")

    def __repr__(self) -> str:
        return "PrivateProviderCapabilityV3ResolutionRejected()"


def _copied_keyring(values: Mapping[str, bytes]) -> Mapping[str, bytes]:
    copied: dict[str, bytes] = {}
    items = tuple(islice(values.items(), MAX_PRIVATE_PROVIDER_CAPABILITIES + 1))
    if len(items) > MAX_PRIVATE_PROVIDER_CAPABILITIES:
        raise ValueError("private provider capability v3 keyring bound conflicts")
    for key_id, public_key in items:
        if (
            type(key_id) is not str
            or re.fullmatch(_KEY_ID, key_id) is None
            or type(public_key) is not bytes
            or len(public_key) != 32
        ):
            raise ValueError("private provider capability v3 keyring conflicts")
        copied[key_id] = bytes(public_key)
    return MappingProxyType(copied)


class PrivateProviderCapabilityV3CurrentResolver:
    """Exact-class owner of immutable inputs and one durable audit per resolution."""

    _rows: Mapping[str, PrivateProviderProcessingCapabilityV3]
    _v3_keys: Mapping[str, bytes]
    _v2_keys: Mapping[str, bytes]
    _v1_keys: Mapping[str, bytes]
    _revocation_keys: Mapping[str, bytes]
    _store: DurablePrivateProviderRevocationHeadStore
    _store_path: Path
    _trusted_floor_sha256: str
    _sealed: bool

    __slots__ = (
        "_rows",
        "_v3_keys",
        "_v2_keys",
        "_v1_keys",
        "_revocation_keys",
        "_store",
        "_store_path",
        "_trusted_floor_sha256",
        "_sealed",
    )

    def __init__(
        self,
        capabilities: Iterable[PrivateProviderProcessingCapabilityV3],
        *,
        capability_v3_verification_keys: Mapping[str, bytes],
        capability_v2_verification_keys: Mapping[str, bytes],
        capability_v1_verification_keys: Mapping[str, bytes],
        revocation_verification_keys: Mapping[str, bytes],
        revocation_store: DurablePrivateProviderRevocationHeadStore,
    ) -> None:
        if type(revocation_store) is not DurablePrivateProviderRevocationHeadStore:
            raise ValueError("private provider capability v3 durable store conflicts")
        v3 = _copied_keyring(capability_v3_verification_keys)
        v2 = _copied_keyring(capability_v2_verification_keys)
        v1 = _copied_keyring(capability_v1_verification_keys)
        revocation = _copied_keyring(revocation_verification_keys)
        keyrings = (v3, v2, v1, revocation)
        all_ids = [key_id for keyring in keyrings for key_id in keyring]
        all_keys = [public_key for keyring in keyrings for public_key in keyring.values()]
        if len(set(all_ids)) != len(all_ids) or len(set(all_keys)) != len(all_keys):
            raise ValueError("private provider capability v3 key purpose reuse conflicts")
        if dict(revocation_store.verification_keys) != dict(revocation):
            raise ValueError("private provider capability v3 store keyring conflicts")
        supplied_rows = tuple(islice(capabilities, MAX_PRIVATE_PROVIDER_CAPABILITIES + 1))
        if len(supplied_rows) > MAX_PRIVATE_PROVIDER_CAPABILITIES:
            raise ValueError("private provider capability v3 row bound conflicts")
        rows: dict[str, PrivateProviderProcessingCapabilityV3] = {}
        for supplied in supplied_rows:
            if type(supplied) is not PrivateProviderProcessingCapabilityV3:
                raise ValueError("private provider capability v3 row conflicts")
            row = PrivateProviderProcessingCapabilityV3.model_validate(
                supplied.model_dump(mode="python")
            )
            verify_private_provider_capability_v3(
                row,
                capability_v3_verification_keys=v3,
                capability_v2_verification_keys=v2,
                capability_v1_verification_keys=v1,
            )
            if row.capability_sha256 in rows:
                raise ValueError("private provider capability v3 duplicate conflicts")
            rows[row.capability_sha256] = row
        object.__setattr__(self, "_rows", MappingProxyType(rows))
        object.__setattr__(self, "_v3_keys", v3)
        object.__setattr__(self, "_v2_keys", v2)
        object.__setattr__(self, "_v1_keys", v1)
        object.__setattr__(self, "_revocation_keys", revocation)
        object.__setattr__(self, "_store", revocation_store)
        object.__setattr__(self, "_store_path", revocation_store.path)
        object.__setattr__(
            self, "_trusted_floor_sha256", revocation_store.trusted_floor_sha256
        )
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("private provider capability v3 resolver is immutable")
        object.__setattr__(self, name, value)

    def _resolve_current(
        self,
        *,
        capability_id: str,
        capability_sha256: str,
        now_ms: int,
        required_until_ms: int,
    ) -> ResolvedPrivateProviderCapabilityV3:
        if (
            type(self) is not PrivateProviderCapabilityV3CurrentResolver
            or type(capability_id) is not str
            or type(capability_sha256) is not str
            or type(now_ms) is not int
            or isinstance(now_ms, bool)
            or type(required_until_ms) is not int
            or isinstance(required_until_ms, bool)
            or re.fullmatch(r"^ppcap3_[0-9a-f]{24}$", capability_id) is None
            or re.fullmatch(_HEX64, capability_sha256) is None
        ):
            raise ValueError("private provider capability v3 resolution input conflicts")
        store = self._store
        if (
            type(store) is not DurablePrivateProviderRevocationHeadStore
            or store.path != self._store_path
            or store.trusted_floor_sha256 != self._trusted_floor_sha256
            or dict(store.verification_keys) != dict(self._revocation_keys)
        ):
            raise ValueError("private provider capability v3 durable store drift conflicts")
        current = DurablePrivateProviderRevocationHeadStore.current(store, now_ms=now_ms)
        row = self._rows.get(capability_sha256)
        if row is None or row.capability_id != capability_id:
            raise ValueError("private provider capability v3 is unavailable")
        verify_private_provider_capability_v3(
            row,
            capability_v3_verification_keys=self._v3_keys,
            capability_v2_verification_keys=self._v2_keys,
            capability_v1_verification_keys=self._v1_keys,
        )
        v2 = row.route_evidence
        v1 = v2.route_evidence
        revoked = frozenset(current.snapshot.revoked_capability_sha256s)
        if (
            current.registry_id != row.revocation_registry_id
            or row.revocation_epoch > current.epoch
            or v2.revocation_epoch > current.epoch
            or v1.revocation_epoch > current.epoch
            or now_ms < row.not_before_ms
            or now_ms >= row.expires_at_ms
            or required_until_ms < now_ms
            or required_until_ms >= row.expires_at_ms
            or now_ms - current.issued_at_ms
            > MAX_PRIVATE_PROVIDER_REVOCATION_REFERENCE_AGE_MS
            or any(
                digest in revoked
                for digest in (
                    row.capability_sha256,
                    v2.capability_sha256,
                    v1.capability_sha256,
                )
            )
            or not _same(
                private_provider_capability_sha256(v1), v1.capability_sha256
            )
        ):
            raise ValueError("private provider capability v3 is unavailable")
        witness_material: dict[str, object] = {
            "schema_version": 1,
            "resolver_contract_sha256": (
                PRIVATE_PROVIDER_CAPABILITY_V3_CURRENT_RESOLVER_CONTRACT_SHA256
            ),
            "capability_v3_sha256": row.capability_sha256,
            "capability_v2_sha256": v2.capability_sha256,
            "capability_v1_sha256": v1.capability_sha256,
            "current_head_sha256": current.head_sha256,
            "trusted_floor_sha256": self._trusted_floor_sha256,
            "current_epoch": current.epoch,
            "current_snapshot_sha256": current.snapshot.snapshot_sha256,
            "current_head_issued_at_ms": current.issued_at_ms,
            "checked_at_ms": now_ms,
            "required_until_ms": required_until_ms,
            "available": True,
            "single_resolution_evidence": True,
            "portable_transition_authority": False,
            "confers_execution_authority": False,
            "confers_sink_authority": False,
            "confers_transition_authority": False,
            "production_consumer_enabled": False,
        }
        witness_sha256 = private_provider_capability_v3_resolution_witness_sha256(
            witness_material
        )
        witness = PrivateProviderCapabilityV3ResolutionWitness.model_validate(
            {
                **witness_material,
                "witness_id": "ppcw3_" + witness_sha256[:24],
                "witness_sha256": witness_sha256,
            }
        )
        return ResolvedPrivateProviderCapabilityV3(capability=row, witness=witness)

    def resolve_current(
        self,
        *,
        capability_id: str,
        capability_sha256: str,
        now_ms: int,
        required_until_ms: int,
    ) -> ResolvedPrivateProviderCapabilityV3:
        """Audit durable current state once and return only non-portable evidence."""
        try:
            return self._resolve_current(
                capability_id=capability_id,
                capability_sha256=capability_sha256,
                now_ms=now_ms,
                required_until_ms=required_until_ms,
            )
        except Exception:
            pass
        raise PrivateProviderCapabilityV3ResolutionRejected() from None


__all__ = [
    "PRIVATE_PROVIDER_CAPABILITY_V3_CURRENT_RESOLVER_CONTRACT_SHA256",
    "PRIVATE_PROVIDER_CAPABILITY_V3_MODULE_SOURCE_SHA256",
    "PrivateProviderCapabilityV3CurrentResolver",
    "PrivateProviderCapabilityV3ResolutionRejected",
    "PrivateProviderCapabilityV3ResolutionWitness",
    "PrivateProviderProcessingCapabilityV3",
    "ResolvedPrivateProviderCapabilityV3",
    "private_provider_capability_v3_module_source_sha256",
    "private_provider_capability_v3_resolution_witness_sha256",
    "private_provider_capability_v3_sha256",
    "private_provider_capability_v3_signature",
    "require_private_provider_capability_v3_module_source",
    "signed_private_provider_capability_v3",
    "verify_private_provider_capability_v3",
]
