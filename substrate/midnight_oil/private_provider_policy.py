"""Pure, non-executable authority types for owner-private provider processing.

Nothing in this module performs I/O or is consumed by prepare, consent, worker,
deposit, graph, or export paths.  It freezes the capability and monotonic output
taint domains those consumers must eventually recompute before mixed execution
can be enabled.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .stages import StageOutputSchema
from .substack_authorization import (
    MAX_SUBSTACK_EXCERPT_BYTES,
    SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
)

MAX_PRIVATE_PROVIDER_CAPABILITY_BYTES = 64_000
MAX_PRIVATE_PROVIDER_CAPABILITIES = 8
MAX_PRIVATE_PROVIDER_LIFETIME_MS = 31 * 24 * 60 * 60 * 1000
MAX_PRIVATE_PROVIDER_EVIDENCE_AGE_MS = 7 * 24 * 60 * 60 * 1000
MAX_PRIVATE_PROVIDER_REVOCATIONS = 256
MAX_PRIVATE_PROVIDER_REVOCATION_REFERENCE_AGE_MS = 5 * 60 * 1000
_CAPABILITY_DOMAIN = b"antiek.midnight-oil.private-provider-capability.v1\x00"
_SIGNATURE_DOMAIN = b"antiek.midnight-oil.private-provider-capability-signature.v1\x00"
_REVOCATION_DOMAIN = b"antiek.midnight-oil.private-provider-revocations.v1\x00"
_REVOCATION_SIGNATURE_DOMAIN = (
    b"antiek.midnight-oil.private-provider-revocations-signature.v1\x00"
)
_TAINT_DOMAIN = b"antiek.midnight-oil.owner-private-output-taint.v1\x00"
_SINK_POLICY_DOMAIN = b"antiek.midnight-oil.owner-private-output-sink-policy.v1\x00"

OwnerPrivateRole = Literal["gatherer", "verifier", "synthesizer"]
OwnerPrivateStageKind = Literal["gather", "verifier", "synthesizer"]
OwnerPrivateSink = Literal[
    "owner_stage_checkpoint",
    "owner_job_evidence",
    "owner_engagement_document",
    "owner_spawn",
    "owner_twin",
    "authenticated_owner_html",
    "owner_private_graph",
    "owner_private_prompt_context",
]

_FUTURE_CANDIDATE_SINKS: tuple[str, ...] = (
    "authenticated_owner_html",
    "owner_engagement_document",
    "owner_job_evidence",
    "owner_private_graph",
    "owner_private_prompt_context",
    "owner_spawn",
    "owner_stage_checkpoint",
    "owner_twin",
)
_FORBIDDEN_SINKS: tuple[str, ...] = (
    "ads",
    "analytics_payload",
    "attribution",
    "benchmark_content_dataset",
    "cache",
    "cross_owner_merge",
    "error_payload",
    "federation",
    "general_depth_graph",
    "log_payload",
    "marketplace",
    "monetization",
    "portable_export",
    "public_retrieval",
    "public_serve",
    "public_share",
    "shared_graph",
    "training_rl",
    "webhook",
)
_SINK_POLICY_MATERIAL = {
    "schema_version": 1,
    "policy_id": "antiek-owner-private-provider-output-v1",
    "content_class": "personal_reading",
    "future_candidate_sinks": _FUTURE_CANDIDATE_SINKS,
    "forbidden_sinks": _FORBIDDEN_SINKS,
    "unknown_sink": "deny",
    "declassification": "not_authorized",
    "verbatim_compliance": "unavailable_policy_v1_denies_every_sink",
    "overlap_checker_contract_sha256": None,
}
OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256 = hashlib.sha256(
    _SINK_POLICY_DOMAIN
    + json.dumps(
        _SINK_POLICY_MATERIAL,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
).hexdigest()


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class PrivateProviderProcessingCapabilityV1(_Closed):
    """Operator-admitted exact route/model configuration; never execution authority."""

    schema_version: Literal[1] = 1
    capability_id: str = Field(pattern=r"^ppcap_[0-9a-f]{24}$")
    purpose: Literal["midnight_oil_owner_private_substack_research"]
    provider_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    model_id: str = Field(pattern=r"^[A-Za-z0-9._:/-]{1,256}$")
    route_key: str = Field(min_length=3, max_length=385)
    api_mode: Literal["responses_no_store", "messages_no_store"]
    processing_region: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    endpoint_origin_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    account_project_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dispatch_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowed_router_roles: tuple[OwnerPrivateRole, ...] = Field(min_length=1, max_length=3)
    source_kind: Literal["substack"] = "substack"
    acquisition_mode: Literal["owner_supplied_local_excerpt"] = (
        "owner_supplied_local_excerpt"
    )
    input_content_class: Literal["personal_reading"] = "personal_reading"
    max_private_input_bytes: int = Field(ge=1, le=MAX_SUBSTACK_EXCERPT_BYTES)
    max_output_bytes: int = Field(ge=1, le=10_000_000)
    provider_constraints_id: Literal["antiek-substack-provider-constraints-v1"] = (
        "antiek-substack-provider-constraints-v1"
    )
    provider_constraints_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_allowed: Literal[False] = False
    provider_logging_allowed: Literal[False] = False
    request_storage_allowed: Literal[False] = False
    response_storage_allowed: Literal[False] = False
    provider_cache_allowed: Literal[False] = False
    provider_tool_network_allowed: Literal[False] = False
    router_fallback_allowed: Literal[False] = False
    retention_mode: Literal["zero_data_retention_configured"] = (
        "zero_data_retention_configured"
    )
    evidence_posture: Literal["operator_admitted_pinned_evidence"] = (
        "operator_admitted_pinned_evidence"
    )
    evidence_kind: Literal["provider_contract_and_account_configuration"] = (
        "provider_contract_and_account_configuration"
    )
    evidence_ref: str = Field(min_length=1, max_length=2_048)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_observed_at_ms: int = Field(ge=0)
    output_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    revocation_registry_id: Literal["antiek-private-provider-revocations-v1"] = (
        "antiek-private-provider-revocations-v1"
    )
    revocation_epoch: int = Field(ge=0)
    issued_at_ms: int = Field(ge=0)
    not_before_ms: int = Field(ge=0)
    expires_at_ms: int = Field(gt=0)
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    capability_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confers_execution_authority: Literal[False] = False
    live_reverification_required: Literal[True] = True

    @model_validator(mode="after")
    def _canonical(self) -> PrivateProviderProcessingCapabilityV1:
        if self.route_key != f"{self.provider_id}/{self.model_id}":
            raise ValueError("private provider route identity conflicts")
        canonical_roles = tuple(sorted(self.allowed_router_roles))
        if self.allowed_router_roles != canonical_roles or len(set(canonical_roles)) != len(
            canonical_roles
        ):
            raise ValueError("private provider roles must be sorted and unique")
        if self.provider_constraints_sha256 != SUBSTACK_PROVIDER_CONSTRAINTS_SHA256:
            raise ValueError("private provider constraints conflict")
        if self.output_policy_sha256 != OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256:
            raise ValueError("private provider output policy conflicts")
        if any(
            ord(character) < 0x21 or ord(character) > 0x7E
            for character in self.evidence_ref
        ):
            raise ValueError("private provider evidence reference is not canonical ASCII")
        if not self.evidence_ref.startswith(("https://", "urn:")):
            raise ValueError("private provider evidence must be HTTPS or URN")
        if self.evidence_ref.startswith("https://"):
            parsed = urlsplit(self.evidence_ref)
            if (
                not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("private provider evidence reference is not secret-safe")
        elif self.evidence_ref.count(":") < 2:
            raise ValueError("private provider evidence URN is incomplete")
        if not (
            self.evidence_observed_at_ms <= self.issued_at_ms
            and self.issued_at_ms - self.evidence_observed_at_ms
            <= MAX_PRIVATE_PROVIDER_EVIDENCE_AGE_MS
        ):
            raise ValueError("private provider evidence is not fresh at issuance")
        if not self.issued_at_ms <= self.not_before_ms < self.expires_at_ms:
            raise ValueError("private provider validity interval conflicts")
        if self.expires_at_ms - self.not_before_ms > MAX_PRIVATE_PROVIDER_LIFETIME_MS:
            raise ValueError("private provider capability lifetime exceeds rotation bound")
        digest = private_provider_capability_sha256(self)
        if self.capability_sha256 != digest or self.capability_id != "ppcap_" + digest[:24]:
            raise ValueError("private provider capability identity conflicts")
        return self


class PrivateProviderRevocationSnapshotV1(_Closed):
    """Signed reference snapshot; it does not prove current-head or monotonicity."""

    schema_version: Literal[1] = 1
    registry_id: Literal["antiek-private-provider-revocations-v1"] = (
        "antiek-private-provider-revocations-v1"
    )
    epoch: int = Field(ge=0)
    issued_at_ms: int = Field(ge=0)
    revoked_capability_sha256s: tuple[str, ...] = Field(
        max_length=MAX_PRIVATE_PROVIDER_REVOCATIONS
    )
    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _canonical(self) -> PrivateProviderRevocationSnapshotV1:
        values = self.revoked_capability_sha256s
        if values != tuple(sorted(values)) or len(set(values)) != len(values):
            raise ValueError("private provider revocations must be sorted and unique")
        if any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in values
        ):
            raise ValueError("private provider revocation identity is invalid")
        if self.snapshot_sha256 != private_provider_revocation_snapshot_sha256(self):
            raise ValueError("private provider revocation snapshot identity conflicts")
        return self


class OwnerPrivateOutputTaintV1(_Closed):
    """Monotonic provenance policy for one private-derived stage output."""

    schema_version: Literal[1] = 1
    policy_id: Literal["antiek-owner-private-provider-output-v1"] = (
        "antiek-owner-private-provider-output-v1"
    )
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    classification: Literal["owner_private_substack_derived"] = (
        "owner_private_substack_derived"
    )
    content_class: Literal["personal_reading"] = "personal_reading"
    owner_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collective_unit_id: str = Field(pattern=r"^cunit_[0-9a-f]{24}$")
    collective_preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_capability_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_constraints_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stage_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    stage_kind: OwnerPrivateStageKind
    output_schema: StageOutputSchema
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    private_source_receipt_ids: tuple[str, ...] = Field(max_length=64)
    upstream_taint_sha256s: tuple[str, ...] = Field(max_length=100)
    compliance_state: Literal["policy_bound_verbatim_check_pending"] = (
        "policy_bound_verbatim_check_pending"
    )
    declassification_authorized: Literal[False] = False
    public_serving_authorized: Literal[False] = False
    portable_export_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    confers_execution_authority: Literal[False] = False
    taint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _canonical(self) -> OwnerPrivateOutputTaintV1:
        if self.policy_sha256 != OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256:
            raise ValueError("owner-private output policy conflicts")
        if self.provider_constraints_sha256 != SUBSTACK_PROVIDER_CONSTRAINTS_SHA256:
            raise ValueError("owner-private provider constraints conflict")
        if self.output_schema != f"midnight-oil.{self.stage_kind}-output/v1":
            raise ValueError("owner-private output schema conflicts with stage kind")
        for values, label in (
            (self.private_source_receipt_ids, "source receipts"),
            (self.upstream_taint_sha256s, "upstream taints"),
        ):
            if values != tuple(sorted(values)) or len(set(values)) != len(values):
                raise ValueError(f"owner-private {label} must be sorted and unique")
            if any(len(value) != 64 or any(c not in "0123456789abcdef" for c in value) for value in values):
                raise ValueError(f"owner-private {label} identities are invalid")
        if not self.private_source_receipt_ids and not self.upstream_taint_sha256s:
            raise ValueError("owner-private output taint requires private lineage")
        if self.taint_sha256 != owner_private_output_taint_sha256(self):
            raise ValueError("owner-private output taint identity conflicts")
        return self


def _canonical_material(value: BaseModel | Mapping[str, object], omitted: set[str]) -> bytes:
    raw = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    material = {key: item for key, item in raw.items() if key not in omitted}
    return json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def private_provider_capability_sha256(
    capability: PrivateProviderProcessingCapabilityV1 | Mapping[str, object],
) -> str:
    return hashlib.sha256(
        _CAPABILITY_DOMAIN
        + _canonical_material(
            capability, {"capability_id", "capability_sha256", "signature_sha256"}
        )
    ).hexdigest()


def private_provider_capability_signature(
    capability_sha256: str, *, signing_key: bytes
) -> str:
    if len(signing_key) < 32:
        raise ValueError("private provider signing key must be at least 256 bits")
    return hmac.digest(
        signing_key, _SIGNATURE_DOMAIN + capability_sha256.encode("ascii"), "sha256"
    ).hex()


def private_provider_revocation_snapshot_sha256(
    snapshot: PrivateProviderRevocationSnapshotV1 | Mapping[str, object],
) -> str:
    return hashlib.sha256(
        _REVOCATION_DOMAIN
        + _canonical_material(snapshot, {"snapshot_sha256", "signature_sha256"})
    ).hexdigest()


def private_provider_revocation_snapshot_signature(
    snapshot_sha256: str, *, signing_key: bytes
) -> str:
    if len(signing_key) < 32:
        raise ValueError("private provider revocation signing key must be at least 256 bits")
    return hmac.digest(
        signing_key,
        _REVOCATION_SIGNATURE_DOMAIN + snapshot_sha256.encode("ascii"),
        "sha256",
    ).hex()


def signed_private_provider_revocation_snapshot(
    *,
    epoch: int,
    issued_at_ms: int,
    revoked_capability_sha256s: Sequence[str] = (),
    key_id: str,
    signing_key: bytes,
) -> PrivateProviderRevocationSnapshotV1:
    material: dict[str, object] = {
        "schema_version": 1,
        "registry_id": "antiek-private-provider-revocations-v1",
        "epoch": epoch,
        "issued_at_ms": issued_at_ms,
        "revoked_capability_sha256s": tuple(sorted(revoked_capability_sha256s)),
        "key_id": key_id,
    }
    digest = private_provider_revocation_snapshot_sha256(material)
    return PrivateProviderRevocationSnapshotV1.model_validate(
        {
            **material,
            "snapshot_sha256": digest,
            "signature_sha256": private_provider_revocation_snapshot_signature(
                digest, signing_key=signing_key
            ),
        }
    )


def verify_private_provider_revocation_snapshot(
    snapshot: PrivateProviderRevocationSnapshotV1,
    *,
    verification_keys: Mapping[str, bytes],
) -> None:
    digest = private_provider_revocation_snapshot_sha256(snapshot)
    if not hmac.compare_digest(digest, snapshot.snapshot_sha256):
        raise ValueError("private provider revocation snapshot is unavailable")
    key = verification_keys.get(snapshot.key_id)
    if key is None:
        raise ValueError("private provider revocation snapshot is unavailable")
    expected = private_provider_revocation_snapshot_signature(
        snapshot.snapshot_sha256, signing_key=key
    )
    if not hmac.compare_digest(expected, snapshot.signature_sha256):
        raise ValueError("private provider revocation snapshot is unavailable")


def signed_private_provider_capability(
    material: Mapping[str, object], *, key_id: str, signing_key: bytes
) -> PrivateProviderProcessingCapabilityV1:
    raw = {
        "schema_version": 1,
        "source_kind": "substack",
        "acquisition_mode": "owner_supplied_local_excerpt",
        "input_content_class": "personal_reading",
        "provider_constraints_id": "antiek-substack-provider-constraints-v1",
        "training_allowed": False,
        "provider_logging_allowed": False,
        "request_storage_allowed": False,
        "response_storage_allowed": False,
        "provider_cache_allowed": False,
        "provider_tool_network_allowed": False,
        "router_fallback_allowed": False,
        "retention_mode": "zero_data_retention_configured",
        "evidence_posture": "operator_admitted_pinned_evidence",
        "evidence_kind": "provider_contract_and_account_configuration",
        "output_policy_sha256": OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
        "revocation_registry_id": "antiek-private-provider-revocations-v1",
        "confers_execution_authority": False,
        "live_reverification_required": True,
        **material,
        "key_id": key_id,
    }
    digest = private_provider_capability_sha256(raw)
    return PrivateProviderProcessingCapabilityV1.model_validate(
        {
            **raw,
            "capability_id": "ppcap_" + digest[:24],
            "capability_sha256": digest,
            "signature_sha256": private_provider_capability_signature(
                digest, signing_key=signing_key
            ),
        }
    )


def verify_private_provider_capability(
    capability: PrivateProviderProcessingCapabilityV1,
    *,
    verification_keys: Mapping[str, bytes],
) -> None:
    digest = private_provider_capability_sha256(capability)
    if (
        not hmac.compare_digest(digest, capability.capability_sha256)
        or capability.capability_id != "ppcap_" + digest[:24]
    ):
        raise ValueError("private provider capability is unavailable")
    key = verification_keys.get(capability.key_id)
    if key is None:
        raise ValueError("private provider capability is unavailable")
    expected = private_provider_capability_signature(
        capability.capability_sha256, signing_key=key
    )
    if not hmac.compare_digest(expected, capability.signature_sha256):
        raise ValueError("private provider capability is unavailable")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("private provider capability contains duplicate JSON keys")
        out[key] = value
    return out


def parse_private_provider_capability_json(raw: str) -> PrivateProviderProcessingCapabilityV1:
    if type(raw) is not str or not raw or len(raw.encode()) > MAX_PRIVATE_PROVIDER_CAPABILITY_BYTES:
        raise ValueError("private provider capability JSON is invalid")
    try:
        payload = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("private provider capability JSON is invalid") from exc
    if type(payload) is not dict:
        raise ValueError("private provider capability JSON is invalid")
    if type(payload.get("allowed_router_roles")) is list:
        payload = {**payload, "allowed_router_roles": tuple(payload["allowed_router_roles"])}
    return PrivateProviderProcessingCapabilityV1.model_validate(payload)


class PrivateProviderCapabilityReferenceRegistry:
    """Pure snapshot matcher; it is not a live loader or execution authority."""

    def __init__(
        self,
        capabilities: Iterable[PrivateProviderProcessingCapabilityV1],
        *,
        verification_keys: Mapping[str, bytes],
        revocation_snapshot: PrivateProviderRevocationSnapshotV1,
    ) -> None:
        rows = tuple(capabilities)
        if len(rows) > MAX_PRIVATE_PROVIDER_CAPABILITIES:
            raise ValueError("private provider capability registry exceeds bound")
        verify_private_provider_revocation_snapshot(
            revocation_snapshot, verification_keys=verification_keys
        )
        by_hash: dict[str, PrivateProviderProcessingCapabilityV1] = {}
        for row in rows:
            verify_private_provider_capability(row, verification_keys=verification_keys)
            if row.revocation_registry_id != revocation_snapshot.registry_id:
                raise ValueError("private provider revocation registry conflicts")
            if row.revocation_epoch > revocation_snapshot.epoch:
                raise ValueError("private provider revocation registry is stale")
            if row.capability_sha256 in by_hash:
                raise ValueError("private provider capability registry contains duplicates")
            by_hash[row.capability_sha256] = row
        self._by_hash = by_hash
        self._revoked = frozenset(revocation_snapshot.revoked_capability_sha256s)
        self._revocation_snapshot_issued_at_ms = revocation_snapshot.issued_at_ms
        self.revocation_snapshot_sha256 = revocation_snapshot.snapshot_sha256

    def require_reference_match(
        self,
        *,
        capability_sha256: str,
        provider_id: str,
        model_id: str,
        route_key: str,
        router_role: OwnerPrivateRole,
        private_input_bytes: int,
        now_ms: int,
        required_until_ms: int,
    ) -> PrivateProviderProcessingCapabilityV1:
        row = self._by_hash.get(capability_sha256)
        if (
            row is None
            or capability_sha256 in self._revoked
            or row.provider_id != provider_id
            or row.model_id != model_id
            or row.route_key != route_key
            or router_role not in row.allowed_router_roles
            or type(private_input_bytes) is not int
            or isinstance(private_input_bytes, bool)
            or private_input_bytes < 1
            or private_input_bytes > row.max_private_input_bytes
            or type(now_ms) is not int
            or isinstance(now_ms, bool)
            or self._revocation_snapshot_issued_at_ms > now_ms
            or now_ms - self._revocation_snapshot_issued_at_ms
            > MAX_PRIVATE_PROVIDER_REVOCATION_REFERENCE_AGE_MS
            or type(required_until_ms) is not int
            or isinstance(required_until_ms, bool)
            or now_ms < row.not_before_ms
            or now_ms >= row.expires_at_ms
            or required_until_ms >= row.expires_at_ms
            or required_until_ms < now_ms
        ):
            raise ValueError("private provider capability is unavailable")
        return row


def owner_private_output_taint_sha256(
    taint: OwnerPrivateOutputTaintV1 | Mapping[str, object],
) -> str:
    return hashlib.sha256(
        _TAINT_DOMAIN + _canonical_material(taint, {"taint_sha256"})
    ).hexdigest()


def build_unverified_owner_private_output_taint(
    *,
    owner_scope_sha256: str,
    collective_unit_id: str,
    collective_preview_sha256: str,
    publication_manifest_sha256: str,
    provider_capability_sha256: str,
    stage_key: str,
    stage_kind: OwnerPrivateStageKind,
    output_schema: StageOutputSchema,
    output_sha256: str,
    private_source_receipt_ids: Sequence[str] = (),
    upstream_taints: Sequence[OwnerPrivateOutputTaintV1] = (),
) -> OwnerPrivateOutputTaintV1:
    for upstream in upstream_taints:
        if not hmac.compare_digest(
            owner_private_output_taint_sha256(upstream), upstream.taint_sha256
        ):
            raise ValueError("owner-private upstream taint identity conflicts")
        if (
            upstream.owner_scope_sha256 != owner_scope_sha256
            or upstream.collective_unit_id != collective_unit_id
            or upstream.collective_preview_sha256 != collective_preview_sha256
            or upstream.publication_manifest_sha256 != publication_manifest_sha256
            or upstream.provider_constraints_sha256 != SUBSTACK_PROVIDER_CONSTRAINTS_SHA256
        ):
            raise ValueError("owner-private upstream taint conflicts")
    material: dict[str, object] = {
        "schema_version": 1,
        "policy_id": "antiek-owner-private-provider-output-v1",
        "policy_sha256": OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
        "classification": "owner_private_substack_derived",
        "content_class": "personal_reading",
        "owner_scope_sha256": owner_scope_sha256,
        "collective_unit_id": collective_unit_id,
        "collective_preview_sha256": collective_preview_sha256,
        "publication_manifest_sha256": publication_manifest_sha256,
        "provider_capability_sha256": provider_capability_sha256,
        "provider_constraints_sha256": SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
        "stage_key": stage_key,
        "stage_kind": stage_kind,
        "output_schema": output_schema,
        "output_sha256": output_sha256,
        "private_source_receipt_ids": tuple(sorted(private_source_receipt_ids)),
        "upstream_taint_sha256s": tuple(sorted(row.taint_sha256 for row in upstream_taints)),
        "compliance_state": "policy_bound_verbatim_check_pending",
        "declassification_authorized": False,
        "public_serving_authorized": False,
        "portable_export_authorized": False,
        "training_authorized": False,
        "confers_execution_authority": False,
    }
    digest = owner_private_output_taint_sha256(material)
    return OwnerPrivateOutputTaintV1.model_validate({**material, "taint_sha256": digest})


def owner_private_sink_currently_authorized(
    taint: OwnerPrivateOutputTaintV1,
    *,
    sink: str,
    owner_scope_sha256: str,
    content_class: str,
    policy_tag: str | None = None,
) -> bool:
    # V1 taints are policy commitments, not compliance receipts.  Persisting
    # generated bytes remains unavailable until a separately trusted checker
    # binds a passing receipt to this exact output and taint hash.
    if taint.compliance_state == "policy_bound_verbatim_check_pending":
        return False
    if (
        sink not in _FUTURE_CANDIDATE_SINKS
        or owner_scope_sha256 != taint.owner_scope_sha256
        or content_class != "personal_reading"
    ):
        return False
    if sink == "owner_private_graph":
        return policy_tag in {"private_research", "operator_only"}
    return policy_tag in {None, "private_research", "operator_only"}


__all__ = [
    "MAX_PRIVATE_PROVIDER_CAPABILITIES",
    "MAX_PRIVATE_PROVIDER_CAPABILITY_BYTES",
    "MAX_PRIVATE_PROVIDER_EVIDENCE_AGE_MS",
    "MAX_PRIVATE_PROVIDER_LIFETIME_MS",
    "MAX_PRIVATE_PROVIDER_REVOCATIONS",
    "MAX_PRIVATE_PROVIDER_REVOCATION_REFERENCE_AGE_MS",
    "OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256",
    "OwnerPrivateOutputTaintV1",
    "PrivateProviderCapabilityReferenceRegistry",
    "PrivateProviderProcessingCapabilityV1",
    "PrivateProviderRevocationSnapshotV1",
    "build_unverified_owner_private_output_taint",
    "owner_private_output_taint_sha256",
    "owner_private_sink_currently_authorized",
    "parse_private_provider_capability_json",
    "private_provider_capability_sha256",
    "private_provider_capability_signature",
    "private_provider_revocation_snapshot_sha256",
    "private_provider_revocation_snapshot_signature",
    "signed_private_provider_capability",
    "signed_private_provider_revocation_snapshot",
    "verify_private_provider_capability",
    "verify_private_provider_revocation_snapshot",
]
