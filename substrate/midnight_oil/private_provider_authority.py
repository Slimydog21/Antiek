"""Canonical non-conferring carrier for mixed owner-private authority.

This pure boundary resolves signed capability identities from a live registry
without inventing private input bytes, router roles, dispatch eligibility, or
any consent/queue/provider effect.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .private_provider_composition import PrivateProviderComposition
from .private_provider_policy import (
    OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
    PrivateProviderCapabilityReferenceRegistry,
)
from .publication_authority_v2 import (
    ProviderProcessingCapabilityReferenceV2,
    ReviewedPublicationManifestV2,
    SubstackOwnerPrivateExcerptAuthorityV2,
    parse_reviewed_publication_manifest_json,
)
from .substack_authorization import SUBSTACK_PROVIDER_CONSTRAINTS_SHA256

if TYPE_CHECKING:
    from .spend_consent import JobConsentConfig

_AUTHORITY_DOMAIN = b"antiek.midnight-oil.owner-private-publication-authority.v1\x00"
_QUEUE_COMMITMENT_DOMAIN = b"antiek.midnight-oil.owner-private-queue-commitment.v1\x00"
MAX_OWNER_PRIVATE_PROVIDER_SELECTIONS = 8
MAX_OWNER_PRIVATE_AUTHORITY_BYTES = 128_000
MAX_OWNER_PRIVATE_QUEUE_COMMITMENT_BYTES = 16_000


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class PrivateProviderSelectionV1(_Closed):
    capability_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_id: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=256)
    route_key: str = Field(min_length=3, max_length=385)
    allowed_router_roles: tuple[Literal["gatherer", "synthesizer", "verifier"], ...] = (
        Field(min_length=1, max_length=3)
    )
    required_router_roles: tuple[
        Literal["gatherer", "synthesizer", "verifier"], ...
    ] = ("gatherer", "synthesizer", "verifier")
    provider_constraints_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _policy_contract(self) -> PrivateProviderSelectionV1:
        if (
            self.route_key != f"{self.provider_id}/{self.model_id}"
            or self.allowed_router_roles != tuple(sorted(self.allowed_router_roles))
            or len(set(self.allowed_router_roles)) != len(self.allowed_router_roles)
            or self.required_router_roles
            != ("gatherer", "synthesizer", "verifier")
            or not set(self.required_router_roles).issubset(self.allowed_router_roles)
            or self.provider_constraints_sha256
            != SUBSTACK_PROVIDER_CONSTRAINTS_SHA256
            or self.output_policy_sha256 != OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256
        ):
            raise ValueError("owner-private provider selection conflicts")
        return self


class OwnerPrivatePublicationAuthorityV1(_Closed):
    schema_version: Literal[1] = 1
    purpose: Literal["owner_private_authority_propagation_only"] = (
        "owner_private_authority_propagation_only"
    )
    publication_manifest_schema_version: Literal[2] = 2
    publication_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selections: tuple[PrivateProviderSelectionV1, ...] = Field(
        min_length=1, max_length=MAX_OWNER_PRIVATE_PROVIDER_SELECTIONS
    )
    output_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    live_reverification_required: Literal[True] = True
    consent_enabled: Literal[False] = False
    confers_execution_authority: Literal[False] = False

    @model_validator(mode="after")
    def _canonical(self) -> OwnerPrivatePublicationAuthorityV1:
        identities = tuple(row.capability_sha256 for row in self.selections)
        if (
            identities != tuple(sorted(identities))
            or len(set(identities)) != len(identities)
            or self.output_policy_sha256 != OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256
            or self.authority_sha256
            != owner_private_publication_authority_sha256(self)
        ):
            raise ValueError("owner-private publication authority identity conflicts")
        return self


class OwnerPrivateQueueCommitmentV1(_Closed):
    schema_version: Literal[1] = 1
    context_binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_schema_version: Literal[2] = 2
    publication_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner_private_publication_authority_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    private_output_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_enabled: Literal[False] = False
    commitment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _identity(self) -> OwnerPrivateQueueCommitmentV1:
        if (
            self.private_output_policy_sha256
            != OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256
            or self.commitment_sha256 != owner_private_queue_commitment_sha256(self)
        ):
            raise ValueError("owner-private queue commitment identity conflicts")
        return self


def _canonical_material(
    value: BaseModel | Mapping[str, object], omitted: frozenset[str]
) -> bytes:
    raw = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    return json.dumps(
        {key: item for key, item in raw.items() if key not in omitted},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def owner_private_publication_authority_sha256(
    authority: OwnerPrivatePublicationAuthorityV1 | Mapping[str, object],
) -> str:
    return hashlib.sha256(
        _AUTHORITY_DOMAIN
        + _canonical_material(authority, frozenset({"authority_sha256"}))
    ).hexdigest()


def canonical_owner_private_publication_authority_json(
    authority: OwnerPrivatePublicationAuthorityV1,
) -> str:
    """Return the sole durable JSON encoding for owner payload propagation."""

    return json.dumps(
        authority.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def owner_private_queue_commitment_sha256(
    commitment: OwnerPrivateQueueCommitmentV1 | Mapping[str, object],
) -> str:
    return hashlib.sha256(
        _QUEUE_COMMITMENT_DOMAIN
        + _canonical_material(commitment, frozenset({"commitment_sha256"}))
    ).hexdigest()


def build_owner_private_queue_commitment(
    *,
    context_binding_sha256: str,
    manifest: ReviewedPublicationManifestV2,
    authority: OwnerPrivatePublicationAuthorityV1,
) -> OwnerPrivateQueueCommitmentV1:
    if authority.publication_manifest_sha256 != manifest.manifest_sha256:
        raise ValueError("owner-private queue authority conflicts")
    material: dict[str, object] = {
        "schema_version": 1,
        "context_binding_sha256": context_binding_sha256,
        "manifest_schema_version": 2,
        "publication_manifest_sha256": manifest.manifest_sha256,
        "owner_private_publication_authority_sha256": authority.authority_sha256,
        "private_output_policy_sha256": authority.output_policy_sha256,
        "delivery_enabled": False,
    }
    return OwnerPrivateQueueCommitmentV1.model_validate(
        {
            **material,
            "commitment_sha256": owner_private_queue_commitment_sha256(material),
        }
    )


def prospective_owner_private_queue_commitment_from_payload(
    payload: Mapping[str, object],
) -> OwnerPrivateQueueCommitmentV1:
    reopened = owner_private_authority_from_payload(payload)
    context_hash = payload.get("context_binding_sha256")
    if reopened is None or type(context_hash) is not str:
        raise ValueError("owner-private queue commitment authority is incomplete")
    return build_owner_private_queue_commitment(
        context_binding_sha256=context_hash,
        manifest=reopened[0],
        authority=reopened[1],
    )


def recompute_owner_private_consent_config(
    authority: object,
    job: object,
    *,
    stage_plan_hash: str | None = None,
) -> JobConsentConfig:
    """Recompute the shared context-v2/job-config-v6 boundary."""

    from .job import MidnightOilJob
    from .job_store import OwnerJob
    from .session_flywheel import validate_context_binding
    from .spend_consent import JobConsentConfig
    from .swarm_plan import swarm_plan_from_authority

    if not isinstance(authority, OwnerJob) or not isinstance(job, MidnightOilJob):
        raise TypeError("owner-private consent authority is invalid")
    reopened = owner_private_authority_from_payload(authority.payload)
    if reopened is None:
        raise ValueError("owner-private consent authority is unavailable")
    plan = swarm_plan_from_authority(authority)
    if plan is None:
        raise ValueError("owner-private consent requires signed swarm authority")
    payload = authority.payload
    if (
        payload.get("goals") != list(job.goals)
        or payload.get("duration_minutes") != job.duration_minutes
        or payload.get("model_id") != job.model_id
        or payload.get("research_tier") != job.research_tier
        or payload.get("fanout_depth") != job.fanout_depth
        or payload.get("asset_id") != job.asset_id
        or plan.goals_count != len(job.goals)
        or plan.gather_per_goal != job.fanout_depth
    ):
        raise ValueError("owner-private job configuration requires reconciliation")
    for selection in reopened[1].selections:
        if any(
            selection.route_key not in plan.role(role).allowed_routes
            for role in selection.required_router_roles
        ):
            raise ValueError("owner-private swarm topology conflicts")
    validate_context_binding(authority, job)
    return JobConsentConfig(
        job_id=job.job_id,
        goals=job.goals,
        duration_minutes=job.duration_minutes,
        model_id=job.model_id,
        research_tier=job.research_tier,
        fanout_depth=job.fanout_depth,
        asset_id=job.asset_id,
        live_execution_plan_hash=plan.plan_hash,
        stage_plan_hash=stage_plan_hash,
        context_binding_sha256=str(payload["context_binding_sha256"]),
        publication_manifest_sha256=reopened[0].manifest_sha256,
        publication_manifest_schema_version=2,
        owner_private_publication_authority_sha256=reopened[1].authority_sha256,
        private_output_policy_sha256=reopened[1].output_policy_sha256,
    )


def canonical_owner_private_queue_commitment_json(
    commitment: OwnerPrivateQueueCommitmentV1,
) -> str:
    return json.dumps(
        commitment.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def build_owner_private_publication_authority(
    manifest: ReviewedPublicationManifestV2,
    *,
    registry: PrivateProviderCapabilityReferenceRegistry,
    now_ms: int,
    required_until_ms: int,
) -> OwnerPrivatePublicationAuthorityV1:
    references: set[str] = set()
    for row in manifest.sources:
        if not isinstance(row.authority, SubstackOwnerPrivateExcerptAuthorityV2):
            continue
        reference = row.authority.provider_processing_authority
        if not isinstance(reference, ProviderProcessingCapabilityReferenceV2):
            raise ValueError("owner-private provider capability reference is unavailable")
        references.add(reference.capability_sha256)
    if not references:
        raise ValueError("owner-private publication authority requires Substack references")
    selections: list[PrivateProviderSelectionV1] = []
    for digest in sorted(references):
        capability = registry.require_reference_available(
            capability_sha256=digest,
            now_ms=now_ms,
            required_until_ms=required_until_ms,
        )
        selections.append(
            PrivateProviderSelectionV1(
                capability_sha256=capability.capability_sha256,
                provider_id=capability.provider_id,
                model_id=capability.model_id,
                route_key=capability.route_key,
                allowed_router_roles=tuple(sorted(capability.allowed_router_roles)),
                required_router_roles=("gatherer", "synthesizer", "verifier"),
                provider_constraints_sha256=capability.provider_constraints_sha256,
                output_policy_sha256=capability.output_policy_sha256,
            )
        )
    material: dict[str, object] = {
        "schema_version": 1,
        "purpose": "owner_private_authority_propagation_only",
        "publication_manifest_schema_version": 2,
        "publication_manifest_sha256": manifest.manifest_sha256,
        "selections": tuple(row.model_dump(mode="python") for row in selections),
        "output_policy_sha256": OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
        "live_reverification_required": True,
        "consent_enabled": False,
        "confers_execution_authority": False,
    }
    return OwnerPrivatePublicationAuthorityV1.model_validate(
        {
            **material,
            "authority_sha256": owner_private_publication_authority_sha256(material),
        }
    )


@dataclass(frozen=True)
class LivePrivateProviderAuthorityResolver:
    """Validation-only app/worker seam; it exposes no dispatch operation."""

    composition: PrivateProviderComposition = field(repr=False)

    def resolve(
        self,
        manifest: ReviewedPublicationManifestV2,
        *,
        now_ms: int,
        required_until_ms: int,
    ) -> OwnerPrivatePublicationAuthorityV1:
        return build_owner_private_publication_authority(
            manifest,
            registry=self.composition.live_reference_registry(now_ms=now_ms),
            now_ms=now_ms,
            required_until_ms=required_until_ms,
        )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("owner-private authority contains duplicate JSON keys")
        result[key] = value
    return result


def parse_owner_private_publication_authority_json(
    raw: str,
) -> OwnerPrivatePublicationAuthorityV1:
    if (
        type(raw) is not str
        or not raw
        or len(raw.encode()) > MAX_OWNER_PRIVATE_AUTHORITY_BYTES
    ):
        raise ValueError("owner-private authority JSON is invalid")
    try:
        payload = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("owner-private authority JSON is invalid") from exc
    if type(payload) is not dict:
        raise ValueError("owner-private authority JSON is invalid")
    selections = payload.get("selections")
    if type(selections) is list:
        payload = {
            **payload,
            "selections": tuple(
                {
                    **selection,
                    "allowed_router_roles": tuple(selection["allowed_router_roles"]),
                    "required_router_roles": tuple(selection["required_router_roles"]),
                }
                if type(selection) is dict
                and type(selection.get("allowed_router_roles")) is list
                and type(selection.get("required_router_roles")) is list
                else selection
                for selection in selections
            ),
        }
    authority = OwnerPrivatePublicationAuthorityV1.model_validate(payload)
    if raw != canonical_owner_private_publication_authority_json(authority):
        raise ValueError("owner-private authority JSON is not canonical")
    return authority


def parse_owner_private_queue_commitment_json(
    raw: str,
) -> OwnerPrivateQueueCommitmentV1:
    if (
        type(raw) is not str
        or not raw
        or len(raw.encode()) > MAX_OWNER_PRIVATE_QUEUE_COMMITMENT_BYTES
    ):
        raise ValueError("owner-private queue commitment JSON is invalid")
    try:
        payload = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("owner-private queue commitment JSON is invalid") from exc
    if type(payload) is not dict:
        raise ValueError("owner-private queue commitment JSON is invalid")
    commitment = OwnerPrivateQueueCommitmentV1.model_validate(payload)
    if raw != canonical_owner_private_queue_commitment_json(commitment):
        raise ValueError("owner-private queue commitment JSON is not canonical")
    return commitment


def owner_private_authority_from_payload(
    payload: Mapping[str, object],
) -> tuple[ReviewedPublicationManifestV2, OwnerPrivatePublicationAuthorityV1] | None:
    """Reopen one complete v2 owner tuple; absence is legacy, partial is fatal."""

    names = (
        "publication_manifest_schema_version",
        "publication_manifest_sha256",
        "publication_manifest_json",
        "owner_private_publication_authority_json",
        "owner_private_publication_authority_sha256",
        "private_output_policy_sha256",
        "context_binding_schema_version",
        "owner_private_execution_state",
        "context_binding_sha256",
        "execution_id",
        "collective_unit_id",
        "collective_preview_sha256",
        "floating_session_id",
        "floating_spawn_id",
        "context_parent_asset_id",
    )
    private_markers = (
        "publication_manifest_schema_version",
        "owner_private_publication_authority_json",
        "owner_private_publication_authority_sha256",
        "private_output_policy_sha256",
        "owner_private_execution_state",
        "context_binding_schema_version",
    )
    if not any(name in payload for name in private_markers):
        return None
    values = tuple(payload.get(name) for name in names)
    if any(name not in payload for name in names) or any(value is None for value in values):
        raise ValueError("owner-private payload authority is incomplete")
    if (
        type(values[0]) is not int
        or values[0] != 2
        or type(values[1]) is not str
        or type(values[2]) is not str
        or type(values[3]) is not str
        or type(values[4]) is not str
        or type(values[5]) is not str
        or type(values[6]) is not int
        or values[6] != 2
        or values[7] != "propagated_disabled"
        or any(
            name in payload
            for name in (
                "publication_preflight_ready",
                "publication_capability_sha256",
                "publication_capability_id",
                "publication_capability_expires_at_ms",
            )
        )
    ):
        raise ValueError("owner-private payload authority conflicts")
    manifest = parse_reviewed_publication_manifest_json(values[2])
    if not isinstance(manifest, ReviewedPublicationManifestV2):
        raise ValueError("owner-private payload requires manifest v2")
    authority = parse_owner_private_publication_authority_json(values[3])
    if (
        manifest.manifest_sha256 != values[1]
        or authority.authority_sha256 != values[4]
        or authority.publication_manifest_sha256 != manifest.manifest_sha256
        or authority.output_policy_sha256 != values[5]
        or values[5] != OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256
    ):
        raise ValueError("owner-private payload authority identity conflicts")
    return manifest, authority


__all__ = [
    "MAX_OWNER_PRIVATE_AUTHORITY_BYTES",
    "MAX_OWNER_PRIVATE_QUEUE_COMMITMENT_BYTES",
    "MAX_OWNER_PRIVATE_PROVIDER_SELECTIONS",
    "LivePrivateProviderAuthorityResolver",
    "OwnerPrivatePublicationAuthorityV1",
    "OwnerPrivateQueueCommitmentV1",
    "PrivateProviderSelectionV1",
    "build_owner_private_publication_authority",
    "build_owner_private_queue_commitment",
    "canonical_owner_private_publication_authority_json",
    "canonical_owner_private_queue_commitment_json",
    "owner_private_publication_authority_sha256",
    "owner_private_queue_commitment_sha256",
    "owner_private_authority_from_payload",
    "parse_owner_private_publication_authority_json",
    "parse_owner_private_queue_commitment_json",
    "prospective_owner_private_queue_commitment_from_payload",
    "recompute_owner_private_consent_config",
]
