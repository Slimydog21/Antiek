from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from interfaces.research.api.midnight_oil_routes import (
    CreateJobBody,
    create_owner_private_job_authority,
)
from substrate.midnight_oil.job_store import OperationState
from substrate.midnight_oil.private_provider_authority import (
    LivePrivateProviderAuthorityResolver,
    build_owner_private_publication_authority,
    build_owner_private_queue_commitment,
    canonical_owner_private_publication_authority_json,
    canonical_owner_private_queue_commitment_json,
    parse_owner_private_publication_authority_json,
    parse_owner_private_queue_commitment_json,
)
from substrate.midnight_oil.private_provider_composition import (
    build_private_provider_composition,
)
from substrate.midnight_oil.private_provider_policy import (
    OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
    PrivateProviderCapabilityReferenceRegistry,
    signed_private_provider_capability,
    signed_private_provider_revocation_snapshot,
)
from substrate.midnight_oil.publication_authority_v2 import (
    ProviderProcessingCapabilityReferenceV2,
    ProviderProcessingUnavailableV2,
    ReviewedPublicationAuthorityRowV2,
    SubstackOwnerPrivateExcerptAuthorityV2,
    build_reviewed_publication_manifest_v2,
)
from substrate.midnight_oil.publication_sources import ReviewedPublicationSource
from substrate.midnight_oil.session_flywheel import context_binding_sha256
from substrate.midnight_oil.substack_authorization import (
    SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
)
from substrate.midnight_oil.swarm_plan import (
    RoleDispatchPlan,
    SwarmLivePlan,
    build_stage_plan,
    role_dispatch_plan_hash,
    swarm_live_plan_hash,
)
from substrate.midnight_oil.worker_cli import _guard_owner_private_authority
from tests.test_midnight_oil_consent_routes import _client, _create
from tests.test_midnight_oil_private_provider_composition import _composition_files

_CAP_PRIVATE = bytes(range(32))
_REV_PRIVATE = bytes(range(32, 64))
_CAP_KEY_ID = "private-capability-issuer"
_REV_KEY_ID = "private-revocation-issuer"
_UNIT = "cunit_" + "1" * 24
_PREVIEW = "2" * 64


def _public(private: bytes) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(private).public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _capability():
    return signed_private_provider_capability(
        {
            "schema_version": 1,
            "purpose": "midnight_oil_owner_private_substack_research",
            "provider_id": "private-provider",
            "model_id": "private-model",
            "route_key": "private-provider/private-model",
            "api_mode": "responses_no_store",
            "processing_region": "us",
            "endpoint_origin_sha256": "1" * 64,
            "account_project_scope_sha256": "2" * 64,
            "adapter_contract_sha256": "3" * 64,
            "dispatch_config_sha256": "4" * 64,
            "allowed_router_roles": ("gatherer", "synthesizer", "verifier"),
            "max_private_input_bytes": 8_192,
            "max_output_bytes": 1_000_000,
            "provider_constraints_sha256": SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
            "evidence_ref": "urn:test:owner-private-authority",
            "evidence_sha256": "5" * 64,
            "evidence_observed_at_ms": 900,
            "output_policy_sha256": OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
            "revocation_epoch": 0,
            "issued_at_ms": 1_000,
            "not_before_ms": 1_000,
            "expires_at_ms": 1_000_000,
        },
        key_id=_CAP_KEY_ID,
        signing_key=_CAP_PRIVATE,
    )


def _registry(*, revoked: tuple[str, ...] = ()):
    capability = _capability()
    snapshot = signed_private_provider_revocation_snapshot(
        epoch=0,
        issued_at_ms=1_000,
        revoked_capability_sha256s=revoked,
        key_id=_REV_KEY_ID,
        signing_key=_REV_PRIVATE,
    )
    return PrivateProviderCapabilityReferenceRegistry(
        (capability,),
        capability_verification_keys={_CAP_KEY_ID: _public(_CAP_PRIVATE)},
        revocation_verification_keys={_REV_KEY_ID: _public(_REV_PRIVATE)},
        revocation_snapshot=snapshot,
    )


def _source() -> ReviewedPublicationSource:
    external_id = "example.substack.com/p/private-note"
    return ReviewedPublicationSource(
        ref_id="sref_"
        + hashlib.sha256(f"substack:substack:{external_id}".encode()).hexdigest()[:16],
        kind="substack",
        canonical_url=f"https://{external_id}",
        external_id=external_id,
        acquisition_mode="substack_bounded_excerpt",
        rights_use="operator_authorized_excerpt",
        max_excerpt_bytes=8_192,
    )


def _manifest(*, available: bool = True, capability_sha256: str | None = None):
    source = _source()
    processing = (
        ProviderProcessingCapabilityReferenceV2(
            capability_sha256=capability_sha256 or _capability().capability_sha256
        )
        if available
        else ProviderProcessingUnavailableV2()
    )
    authority = SubstackOwnerPrivateExcerptAuthorityV2(
        owner_scope_sha256="3" * 64,
        collective_unit_id=_UNIT,
        collective_preview_sha256=_PREVIEW,
        ref_id=source.ref_id,
        canonical_url=source.canonical_url,
        external_id=source.external_id,
        overlay_id="csubrev_" + "4" * 24,
        overlay_sha256="5" * 64,
        authorization_id="sua_" + "6" * 24,
        authorization_sha256="7" * 64,
        receipt_id="suer_" + "8" * 24,
        receipt_sha256="9" * 64,
        source_representation_sha256="a" * 64,
        source_representation_bytes=100,
        source_byte_start=10,
        source_byte_end=20,
        excerpt_sha256="b" * 64,
        excerpt_bytes=10,
        expires_at_ms=2_000_000,
        provider_constraints_sha256=SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
        provider_processing_authority=processing,
    )
    return build_reviewed_publication_manifest_v2(
        collective_unit_id=_UNIT,
        collective_preview_sha256=_PREVIEW,
        sources=(ReviewedPublicationAuthorityRowV2(source=source, authority=authority),),
    )


def _swarm_plan(route: str) -> SwarmLivePlan:
    roles = tuple(
        RoleDispatchPlan(
            role=role,  # type: ignore[arg-type]
            allowed_routes=(route,),
            projected_max_cents=1,
            dispatch_config_sha256="1" * 64,
            max_input_tokens=1_024,
            max_prompt_bytes=4_096,
            max_output_tokens=256,
            plan_hash=role_dispatch_plan_hash(
                role=role,  # type: ignore[arg-type]
                allowed_routes=(route,),
                projected_max_cents=1,
                dispatch_config_sha256="1" * 64,
                max_input_tokens=1_024,
                max_prompt_bytes=4_096,
                max_output_tokens=256,
            ),
        )
        for role in ("planner", "gatherer", "verifier", "synthesizer")
    )
    fields = {
        "goals_count": 1,
        "gather_per_goal": 3,
        "source_policy": ("operator_corpus",),
        "roles": roles,
        "projected_total_cents": 6,
    }
    return SwarmLivePlan(
        **fields,  # type: ignore[arg-type]
        plan_hash=swarm_live_plan_hash(**fields),  # type: ignore[arg-type]
    )


def test_carrier_is_canonical_live_identity_only_and_nonconferring() -> None:
    manifest = _manifest()
    authority = build_owner_private_publication_authority(
        manifest,
        registry=_registry(),
        now_ms=1_000,
        required_until_ms=2_000,
    )
    assert authority.publication_manifest_sha256 == manifest.manifest_sha256
    assert authority.consent_enabled is False
    assert authority.confers_execution_authority is False
    assert authority.live_reverification_required is True
    assert authority.output_policy_sha256 == OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256
    assert len(authority.selections) == 1
    selection = authority.selections[0]
    assert selection.route_key == "private-provider/private-model"
    assert selection.required_router_roles == (
        "gatherer",
        "synthesizer",
        "verifier",
    )
    raw = canonical_owner_private_publication_authority_json(authority)
    assert parse_owner_private_publication_authority_json(raw) == authority


def test_carrier_has_literal_golden_identity() -> None:
    authority = build_owner_private_publication_authority(
        _manifest(),
        registry=_registry(),
        now_ms=1_000,
        required_until_ms=2_000,
    )
    assert authority.authority_sha256 == (
        "84e07dc663c9d6e556a5bc36c2113ce839b8b63ab937b07795dc6c76f8584de1"
    )


def test_prospective_queue_commitment_is_canonical_and_never_deliverable() -> None:
    manifest = _manifest()
    authority = build_owner_private_publication_authority(
        manifest,
        registry=_registry(),
        now_ms=1_000,
        required_until_ms=2_000,
    )
    commitment = build_owner_private_queue_commitment(
        context_binding_sha256="c" * 64,
        manifest=manifest,
        authority=authority,
    )
    assert commitment.delivery_enabled is False
    assert commitment.commitment_sha256 == (
        "ae37f15cfcc3c8361027ea546edeead269a1fcda8e2a438ae9f4377801365240"
    )
    raw = canonical_owner_private_queue_commitment_json(commitment)
    assert parse_owner_private_queue_commitment_json(raw) == commitment
    with pytest.raises(ValueError, match="not canonical"):
        parse_owner_private_queue_commitment_json(" " + raw)
    duplicate = raw.replace('"schema_version":1', '"schema_version":1,"schema_version":1')
    with pytest.raises(ValueError, match="duplicate"):
        parse_owner_private_queue_commitment_json(duplicate)


def test_consent_route_denies_complete_private_carrier_before_issue_or_enqueue(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    client, deps = _client(tmp_path)
    _create(client)
    stored = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert stored is not None
    manifest = _manifest()
    authority = build_owner_private_publication_authority(
        manifest,
        registry=_registry(),
        now_ms=1_000,
        required_until_ms=2_000,
    )
    context_fields = {
        "execution_id": "cexec_" + "d" * 24,
        "collective_unit_id": _UNIT,
        "collective_preview_sha256": _PREVIEW,
        "floating_session_id": "session-private",
        "floating_spawn_id": "spawn-private",
        "context_parent_asset_id": "parent-private",
    }
    context_hash = context_binding_sha256(
        owner_id="alice",
        execution_id=context_fields["execution_id"],
        collective_unit_id=_UNIT,
        collective_preview_sha256=_PREVIEW,
        floating_session_id=context_fields["floating_session_id"],
        floating_spawn_id=context_fields["floating_spawn_id"],
        parent_asset_id=context_fields["context_parent_asset_id"],
        duration_minutes=30,
        model_id="offline-stub",
        research_tier="deep",
        fanout_depth=3,
        publication_manifest_sha256=manifest.manifest_sha256,
        publication_manifest_schema_version=2,
        owner_private_publication_authority_sha256=authority.authority_sha256,
        private_output_policy_sha256=authority.output_policy_sha256,
    )
    payload = {
        **stored.payload,
        **context_fields,
        "context_binding_sha256": context_hash,
        "publication_manifest_schema_version": 2,
        "publication_manifest_sha256": manifest.manifest_sha256,
        "publication_manifest_json": manifest.model_dump_json(),
        "owner_private_publication_authority_json": (
            canonical_owner_private_publication_authority_json(authority)
        ),
        "owner_private_publication_authority_sha256": authority.authority_sha256,
        "private_output_policy_sha256": authority.output_policy_sha256,
        "context_binding_schema_version": 2,
        "owner_private_execution_state": "propagated_disabled",
    }
    for name in (
        "publication_preflight_ready",
        "publication_capability_sha256",
        "publication_capability_id",
        "publication_capability_expires_at_ms",
    ):
        payload.pop(name, None)
    assert deps.owner_jobs.delete_uninitialized_job(
        owner_user_id="alice", job_id="job-owned"
    )
    deps.owner_jobs.put_job(replace(stored, payload=payload))
    denied = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"use_recommended": True},
    )
    assert denied.status_code == 409
    assert denied.json() == {"detail": "owner-private execution remains disabled"}
    assert denied.headers["cache-control"] == "no-store"
    reopened = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert reopened is not None and reopened.operation_state.value == "none"
    assert deps.operation_queue is not None
    assert deps.operation_queue.next_claimable(now_ms=1_000_000) is None


def test_partial_private_marker_cannot_downgrade_into_legacy_consent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    client, deps = _client(tmp_path)
    _create(client)
    stored = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert stored is not None
    assert deps.owner_jobs.delete_uninitialized_job(
        owner_user_id="alice", job_id="job-owned"
    )
    deps.owner_jobs.put_job(
        replace(
            stored,
            payload={**stored.payload, "context_binding_schema_version": 2},
        )
    )
    denied = client.post(
        "/midnight-oil/jobs/job-owned/spend-consent",
        headers={"x-test-user": "alice"},
        json={"use_recommended": True},
    )
    assert denied.status_code == 409
    assert denied.json() == {"detail": "stored job configuration is invalid"}
    reopened = deps.owner_jobs.get_job(owner_user_id="alice", job_id="job-owned")
    assert reopened is not None and reopened.operation_state.value == "none"


def test_internal_persistence_entry_replays_and_reopens_complete_v2(
    tmp_path: Path,
) -> None:
    (tmp_path / "api").mkdir()
    _, deps = _client(tmp_path / "api")
    (tmp_path / "private").mkdir()
    environment, capability, _ = _composition_files(tmp_path / "private")
    composition = build_private_provider_composition(
        state_dir=tmp_path / "private" / "state",
        environ=environment,
        now_ms=1_000,
    )
    assert composition is not None
    route = capability.route_key
    wired = replace(deps, live_plan_resolver=lambda _job: _swarm_plan(route))
    manifest = _manifest(capability_sha256=capability.capability_sha256)
    body = CreateJobBody(
        goals=["Ground the owner-private source"],
        duration_minutes=1,
        model_id=capability.model_id,
        fanout_depth=3,
        research_tier="deep",
        live=True,
    )
    kwargs = {
        "deps": wired,
        "owner": "alice",
        "body": body,
        "job_id": "private-job-001",
        "asset_id": "private-asset-001",
        "execution_id": "cexec_" + "e" * 24,
        "collective_unit_id": _UNIT,
        "collective_preview_sha256": _PREVIEW,
        "floating_session_id": "private-session",
        "floating_spawn_id": "private-spawn",
        "parent_asset_id": "private-parent",
        "manifest": manifest,
        "private_authority_resolver": LivePrivateProviderAuthorityResolver(composition),
        "now_ms": 1_000,
    }
    first = create_owner_private_job_authority(**kwargs)  # type: ignore[arg-type]
    second = create_owner_private_job_authority(**kwargs)  # type: ignore[arg-type]
    assert first == second
    reopened = wired.owner_jobs.get_job(owner_user_id="alice", job_id="private-job-001")
    assert reopened is not None
    assert reopened.payload["context_binding_schema_version"] == 2
    assert reopened.payload["owner_private_execution_state"] == "propagated_disabled"
    for forbidden in (
        "publication_preflight_ready",
        "publication_capability_sha256",
        "publication_capability_id",
        "publication_capability_expires_at_ms",
    ):
        assert forbidden not in reopened.payload
    stage_plan = build_stage_plan(
        _swarm_plan(route),
        operation_id="private-operation-001",
        job_id=reopened.job_id,
        approved_ceiling_cents=10,
    )
    substituted = replace(
        reopened,
        approved_ceiling_cents=10,
        consent_config_hash="f" * 64,
        consent_stage_plan_hash=stage_plan.plan_hash,
        operation_id=stage_plan.operation_id,
        operation_state=OperationState.QUEUED,
    )
    runtime = SimpleNamespace(
        config=SimpleNamespace(worker_lease_ms=1_000),
        stores=SimpleNamespace(
            jobs=SimpleNamespace(
                get_job=lambda job_id: wired.jobs.get_job(job_id),
                get_stage_plan=lambda _job_id: stage_plan,
            )
        ),
        private_provider_composition=composition,
    )
    with pytest.raises(ValueError, match="consent configuration requires reconciliation"):
        _guard_owner_private_authority(runtime, substituted, 1_000)  # type: ignore[arg-type]


def test_unavailable_unknown_revoked_stale_and_short_horizon_fail_closed() -> None:
    with pytest.raises(ValueError, match="reference is unavailable"):
        build_owner_private_publication_authority(
            _manifest(available=False),
            registry=_registry(),
            now_ms=1_000,
            required_until_ms=2_000,
        )
    capability_hash = _capability().capability_sha256
    with pytest.raises(ValueError, match="capability is unavailable"):
        build_owner_private_publication_authority(
            _manifest(),
            registry=_registry(revoked=(capability_hash,)),
            now_ms=1_000,
            required_until_ms=2_000,
        )
    with pytest.raises(ValueError, match="capability is unavailable"):
        build_owner_private_publication_authority(
            _manifest(),
            registry=_registry(),
            now_ms=301_001,
            required_until_ms=301_001,
        )
    with pytest.raises(ValueError, match="capability is unavailable"):
        build_owner_private_publication_authority(
            _manifest(),
            registry=_registry(),
            now_ms=1_000,
            required_until_ms=1_000_000,
        )


def test_parser_rejects_duplicate_noncanonical_and_substituted_material() -> None:
    authority = build_owner_private_publication_authority(
        _manifest(),
        registry=_registry(),
        now_ms=1_000,
        required_until_ms=2_000,
    )
    raw = canonical_owner_private_publication_authority_json(authority)
    duplicate = raw.replace('"schema_version":1', '"schema_version":1,"schema_version":1')
    with pytest.raises(ValueError, match="duplicate"):
        parse_owner_private_publication_authority_json(duplicate)
    with pytest.raises(ValueError, match="not canonical"):
        parse_owner_private_publication_authority_json(" " + raw)
    payload = authority.model_dump(mode="json")
    payload["selections"][0]["provider_id"] = "substituted-provider"
    payload["selections"] = tuple(payload["selections"])
    with pytest.raises(ValidationError):
        type(authority).model_validate(payload)


def test_required_roles_cannot_exceed_signed_capability_roles() -> None:
    payload = _capability().model_dump(mode="json")
    payload["allowed_router_roles"] = ("gatherer", "verifier")
    for name in (
        "capability_id",
        "capability_sha256",
        "signature_ed25519",
        "issuer_role",
        "signature_scheme",
        "confers_execution_authority",
        "live_reverification_required",
        "training_allowed",
        "provider_logging_allowed",
        "request_storage_allowed",
        "response_storage_allowed",
        "provider_cache_allowed",
        "provider_tool_network_allowed",
        "router_fallback_allowed",
        "retention_mode",
    ):
        payload.pop(name, None)
    limited = signed_private_provider_capability(
        payload, key_id=_CAP_KEY_ID, signing_key=_CAP_PRIVATE
    )
    snapshot = signed_private_provider_revocation_snapshot(
        epoch=0,
        issued_at_ms=1_000,
        key_id=_REV_KEY_ID,
        signing_key=_REV_PRIVATE,
    )
    registry = PrivateProviderCapabilityReferenceRegistry(
        (limited,),
        capability_verification_keys={_CAP_KEY_ID: _public(_CAP_PRIVATE)},
        revocation_verification_keys={_REV_KEY_ID: _public(_REV_PRIVATE)},
        revocation_snapshot=snapshot,
    )
    manifest_payload = _manifest().model_dump(mode="json")
    manifest_payload["sources"][0]["authority"]["provider_processing_authority"][
        "capability_sha256"
    ] = limited.capability_sha256
    manifest_payload["sources"] = tuple(manifest_payload["sources"])
    manifest_payload.pop("manifest_sha256")
    source_row = ReviewedPublicationAuthorityRowV2.model_validate(
        manifest_payload["sources"][0]
    )
    manifest = build_reviewed_publication_manifest_v2(
        collective_unit_id=_UNIT,
        collective_preview_sha256=_PREVIEW,
        sources=(source_row,),
    )
    with pytest.raises(ValidationError, match="selection conflicts"):
        build_owner_private_publication_authority(
            manifest,
            registry=registry,
            now_ms=1_000,
            required_until_ms=2_000,
        )
