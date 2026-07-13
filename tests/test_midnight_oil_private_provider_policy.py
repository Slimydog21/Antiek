from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from substrate.midnight_oil.private_provider_policy import (
    OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
    OwnerPrivateOutputTaintV1,
    PrivateProviderCapabilityReferenceRegistry,
    PrivateProviderProcessingCapabilityV1,
    PrivateProviderRevocationSnapshotV1,
    build_unverified_owner_private_output_taint,
    owner_private_output_taint_sha256,
    owner_private_sink_currently_authorized,
    parse_private_provider_capability_json,
    private_provider_capability_sha256,
    signed_private_provider_capability,
    signed_private_provider_revocation_snapshot,
    verify_private_provider_capability,
)
from substrate.midnight_oil.substack_authorization import (
    SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
)

_CAPABILITY_SIGNING_KEY = bytes(range(32))
_REVOCATION_SIGNING_KEY = bytes(range(32, 64))


def _public_key(private_key: bytes) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(private_key).public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


_CAPABILITY_PUBLIC_KEY = _public_key(_CAPABILITY_SIGNING_KEY)
_REVOCATION_PUBLIC_KEY = _public_key(_REVOCATION_SIGNING_KEY)
_OWNER = "1" * 64
_UNIT = "cunit_" + "2" * 24
_PREVIEW = "3" * 64
_MANIFEST = "4" * 64
_STAGE_GATHER = "a" * 64
_STAGE_VERIFY = "c" * 64


def _material(**changes: object) -> dict[str, object]:
    material: dict[str, object] = {
        "schema_version": 1,
        "purpose": "midnight_oil_owner_private_substack_research",
        "provider_id": "openai-zdr-project",
        "model_id": "gpt-5.5",
        "route_key": "openai-zdr-project/gpt-5.5",
        "api_mode": "responses_no_store",
        "processing_region": "us",
        "endpoint_origin_sha256": "5" * 64,
        "account_project_scope_sha256": "6" * 64,
        "adapter_contract_sha256": "7" * 64,
        "dispatch_config_sha256": "8" * 64,
        "allowed_router_roles": ("gatherer", "synthesizer", "verifier"),
        "source_kind": "substack",
        "acquisition_mode": "owner_supplied_local_excerpt",
        "input_content_class": "personal_reading",
        "max_private_input_bytes": 8_192,
        "max_output_bytes": 1_000_000,
        "provider_constraints_id": "antiek-substack-provider-constraints-v1",
        "provider_constraints_sha256": SUBSTACK_PROVIDER_CONSTRAINTS_SHA256,
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
        "evidence_ref": "urn:test:private-provider-evidence",
        "evidence_sha256": "9" * 64,
        "evidence_observed_at_ms": 900,
        "output_policy_sha256": OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256,
        "revocation_registry_id": "antiek-private-provider-revocations-v1",
        "revocation_epoch": 1,
        "issued_at_ms": 1_000,
        "not_before_ms": 1_000,
        "expires_at_ms": 101_000,
        "confers_execution_authority": False,
        "live_reverification_required": True,
    }
    material.update(changes)
    return material


def _capability(**changes: object) -> PrivateProviderProcessingCapabilityV1:
    return signed_private_provider_capability(
        _material(**changes),
        key_id="private-provider-capability-2026-07",
        signing_key=_CAPABILITY_SIGNING_KEY,
    )


def _root_taint(**changes: object) -> OwnerPrivateOutputTaintV1:
    values: dict[str, object] = {
        "owner_scope_sha256": _OWNER,
        "collective_unit_id": _UNIT,
        "collective_preview_sha256": _PREVIEW,
        "publication_manifest_sha256": _MANIFEST,
        "provider_capability_sha256": _capability().capability_sha256,
        "stage_key": _STAGE_GATHER,
        "stage_kind": "gather",
        "output_schema": "midnight-oil.gather-output/v1",
        "output_sha256": "d" * 64,
        "private_source_receipt_ids": ("b" * 64,),
    }
    values.update(changes)
    return build_unverified_owner_private_output_taint(**values)  # type: ignore[arg-type]


def _revocations(
    *revoked: str, epoch: int = 1
) -> PrivateProviderRevocationSnapshotV1:
    return signed_private_provider_revocation_snapshot(
        epoch=epoch,
        issued_at_ms=1_000,
        revoked_capability_sha256s=revoked,
        key_id="private-provider-revocation-2026-07",
        signing_key=_REVOCATION_SIGNING_KEY,
    )


def test_capability_is_canonical_signed_bounded_and_nonconferring() -> None:
    capability = _capability()
    assert capability.capability_id == "ppcap_" + capability.capability_sha256[:24]
    assert capability.capability_sha256 == private_provider_capability_sha256(capability)
    assert capability.confers_execution_authority is False
    assert capability.live_reverification_required is True
    assert capability.training_allowed is False
    assert capability.provider_logging_allowed is False
    assert capability.router_fallback_allowed is False
    verify_private_provider_capability(
        capability,
        verification_keys={
            "private-provider-capability-2026-07": _CAPABILITY_PUBLIC_KEY
        },
    )
    parsed = parse_private_provider_capability_json(capability.model_dump_json())
    assert parsed == capability


def test_private_policy_domains_have_literal_golden_vectors() -> None:
    capability = _capability()
    snapshot = _revocations()
    root = _root_taint()
    child = build_unverified_owner_private_output_taint(
        owner_scope_sha256=_OWNER,
        collective_unit_id=_UNIT,
        collective_preview_sha256=_PREVIEW,
        publication_manifest_sha256=_MANIFEST,
        provider_capability_sha256=capability.capability_sha256,
        stage_key=_STAGE_VERIFY,
        stage_kind="verifier",
        output_schema="midnight-oil.verifier-output/v1",
        output_sha256="c" * 64,
        upstream_taints=(root,),
    )
    assert OWNER_PRIVATE_OUTPUT_SINK_POLICY_SHA256 == (
        "0c06cace74dd11fc23e081358739ae879955ecc6f1da3688d5820673a83689b1"
    )
    assert capability.capability_sha256 == (
        "0457ba8c0379ffc7497bfdb765c64a05afe136d7c243e67077382912a0bb9585"
    )
    assert snapshot.snapshot_sha256 == (
        "c5c79e08eb1c8994bd1be59f5c8a2c86fa9f9fe5c5c26602c1c3697edbc15c01"
    )
    assert root.taint_sha256 == (
        "472cc50df9afe1013f3f2215114d8aa3c98ed88ce5dc34b8a2daefe9af39979b"
    )
    assert child.taint_sha256 == (
        "51a9e5fe5b75f4bf132c03dcaad253387a41b2b85fff1cf6445fae755367f5b3"
    )


def test_capability_rejects_duplicate_unknown_and_tampered_material() -> None:
    capability = _capability()
    duplicate = capability.model_dump_json().replace(
        '"schema_version":1', '"schema_version":1,"schema_version":1', 1
    )
    with pytest.raises(ValueError, match="duplicate"):
        parse_private_provider_capability_json(duplicate)
    with pytest.raises(ValidationError):
        PrivateProviderProcessingCapabilityV1.model_validate(
            {**capability.model_dump(mode="json"), "ambient_fallback": True}
        )
    with pytest.raises(ValidationError, match="constraints conflict"):
        signed_private_provider_capability(
            _material(provider_constraints_sha256="0" * 64),
            key_id="private-provider-capability-2026-07",
            signing_key=_CAPABILITY_SIGNING_KEY,
        )
    raw = capability.model_dump(mode="json")
    raw["evidence_sha256"] = "0" * 64
    raw["allowed_router_roles"] = tuple(raw["allowed_router_roles"])
    digest = private_provider_capability_sha256(raw)
    forged = PrivateProviderProcessingCapabilityV1.model_validate(
        {
            **raw,
            "capability_id": "ppcap_" + digest[:24],
            "capability_sha256": digest,
        }
    )
    with pytest.raises(ValueError, match="unavailable"):
        verify_private_provider_capability(
            forged,
            verification_keys={
                "private-provider-capability-2026-07": _CAPABILITY_PUBLIC_KEY
            },
        )


def test_verifier_recomputes_material_after_validation_bypass() -> None:
    capability = _capability()
    bypassed = capability.model_copy(update={"provider_id": "evil"})
    with pytest.raises(ValueError, match="unavailable"):
        verify_private_provider_capability(
            bypassed,
            verification_keys={
                "private-provider-capability-2026-07": _CAPABILITY_PUBLIC_KEY
            },
        )


def test_omitted_and_explicit_defaults_have_one_capability_identity() -> None:
    explicit = _material()
    omitted = {
        key: value
        for key, value in explicit.items()
        if key
        not in {
            "schema_version",
            "source_kind",
            "acquisition_mode",
            "input_content_class",
            "provider_constraints_id",
            "training_allowed",
            "provider_logging_allowed",
            "request_storage_allowed",
            "response_storage_allowed",
            "provider_cache_allowed",
            "provider_tool_network_allowed",
            "router_fallback_allowed",
            "retention_mode",
            "evidence_posture",
            "evidence_kind",
            "output_policy_sha256",
            "revocation_registry_id",
            "confers_execution_authority",
            "live_reverification_required",
        }
    }
    assert signed_private_provider_capability(
        explicit,
        key_id="private-provider-capability-2026-07",
        signing_key=_CAPABILITY_SIGNING_KEY,
    ).capability_sha256 == signed_private_provider_capability(
        omitted,
        key_id="private-provider-capability-2026-07",
        signing_key=_CAPABILITY_SIGNING_KEY,
    ).capability_sha256


@pytest.mark.parametrize(
    "evidence_ref",
    (
        "https://user:secret@example.com/evidence",
        "https://example.com/evidence?token=secret",
        "https://example.com/evidence#fragment",
        "urn:incomplete",
        "urn:test:line\nbreak",
    ),
)
def test_evidence_reference_is_secret_safe_and_canonical(evidence_ref: str) -> None:
    with pytest.raises(ValidationError):
        _capability(evidence_ref=evidence_ref)


def test_evidence_must_precede_issuance_and_be_fresh() -> None:
    with pytest.raises(ValidationError, match="not fresh"):
        _capability(evidence_observed_at_ms=1_001)
    with pytest.raises(ValidationError, match="not fresh"):
        _capability(
            evidence_observed_at_ms=0,
            issued_at_ms=604_800_001,
            not_before_ms=604_800_001,
            expires_at_ms=604_900_001,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("route_key", "openai-zdr-project/other"),
        ("allowed_router_roles", ("verifier", "gatherer")),
        ("training_allowed", True),
        ("provider_logging_allowed", True),
        ("router_fallback_allowed", True),
        ("retention_mode", "best_effort"),
        ("output_policy_sha256", "0" * 64),
    ],
)
def test_capability_rejects_route_role_handling_and_policy_drift(
    field: str, value: object
) -> None:
    with pytest.raises((ValidationError, ValueError)):
        _capability(**{field: value})


def test_exact_registry_has_no_selection_or_fallback_and_uses_exclusive_horizon() -> None:
    first = _capability()
    second = _capability(
        model_id="gpt-5.6",
        route_key="openai-zdr-project/gpt-5.6",
        issued_at_ms=2_000,
        not_before_ms=2_000,
        expires_at_ms=102_000,
    )
    registry = PrivateProviderCapabilityReferenceRegistry(
        (first, second),
        capability_verification_keys={
            "private-provider-capability-2026-07": _CAPABILITY_PUBLIC_KEY
        },
        revocation_verification_keys={
            "private-provider-revocation-2026-07": _REVOCATION_PUBLIC_KEY
        },
        revocation_snapshot=_revocations(),
    )
    assert (
        registry.require_reference_match(
            capability_sha256=first.capability_sha256,
            provider_id=first.provider_id,
            model_id=first.model_id,
            route_key=first.route_key,
            router_role="gatherer",
            private_input_bytes=8_192,
            now_ms=1_000,
            required_until_ms=100_999,
        )
        == first
    )
    for changes in (
        {"capability_sha256": "0" * 64},
        {"model_id": second.model_id},
        {"router_role": "planner"},
        {"private_input_bytes": 8_193},
        {"required_until_ms": first.expires_at_ms},
    ):
        args: dict[str, object] = {
            "capability_sha256": first.capability_sha256,
            "provider_id": first.provider_id,
            "model_id": first.model_id,
            "route_key": first.route_key,
            "router_role": "gatherer",
            "private_input_bytes": 8_192,
            "now_ms": 1_000,
            "required_until_ms": 100_999,
        }
        args.update(changes)
        with pytest.raises(ValueError, match="unavailable"):
            registry.require_reference_match(**args)  # type: ignore[arg-type]
    revoked = PrivateProviderCapabilityReferenceRegistry(
        (first,),
        capability_verification_keys={
            "private-provider-capability-2026-07": _CAPABILITY_PUBLIC_KEY
        },
        revocation_verification_keys={
            "private-provider-revocation-2026-07": _REVOCATION_PUBLIC_KEY
        },
        revocation_snapshot=_revocations(first.capability_sha256),
    )
    with pytest.raises(ValueError, match="unavailable"):
        revoked.require_reference_match(
            capability_sha256=first.capability_sha256,
            provider_id=first.provider_id,
            model_id=first.model_id,
            route_key=first.route_key,
            router_role="gatherer",
            private_input_bytes=1,
            now_ms=1_000,
            required_until_ms=1_000,
        )


def test_revocation_snapshot_is_signed_bounded_and_recomputed() -> None:
    first = _capability()
    snapshot = _revocations(first.capability_sha256, epoch=2)
    assert snapshot.revoked_capability_sha256s == (first.capability_sha256,)
    bypassed = snapshot.model_copy(update={"epoch": 1})
    with pytest.raises(ValueError, match="snapshot is unavailable"):
        PrivateProviderCapabilityReferenceRegistry(
            (first,),
            capability_verification_keys={
                "private-provider-capability-2026-07": _CAPABILITY_PUBLIC_KEY
            },
            revocation_verification_keys={
                "private-provider-revocation-2026-07": _REVOCATION_PUBLIC_KEY
            },
            revocation_snapshot=bypassed,
        )
    future_capability = _capability(revocation_epoch=3)
    with pytest.raises(ValueError, match="registry is stale"):
        PrivateProviderCapabilityReferenceRegistry(
            (future_capability,),
            capability_verification_keys={
                "private-provider-capability-2026-07": _CAPABILITY_PUBLIC_KEY
            },
            revocation_verification_keys={
                "private-provider-revocation-2026-07": _REVOCATION_PUBLIC_KEY
            },
            revocation_snapshot=snapshot,
        )


def test_reference_match_rejects_future_or_stale_snapshot() -> None:
    capability = _capability(expires_at_ms=1_000_000)
    registry = PrivateProviderCapabilityReferenceRegistry(
        (capability,),
        capability_verification_keys={
            "private-provider-capability-2026-07": _CAPABILITY_PUBLIC_KEY
        },
        revocation_verification_keys={
            "private-provider-revocation-2026-07": _REVOCATION_PUBLIC_KEY
        },
        revocation_snapshot=_revocations(),
    )
    base = {
        "capability_sha256": capability.capability_sha256,
        "provider_id": capability.provider_id,
        "model_id": capability.model_id,
        "route_key": capability.route_key,
        "router_role": "gatherer",
        "private_input_bytes": 1,
        "required_until_ms": 400_000,
    }
    for now_ms in (999, 301_001):
        with pytest.raises(ValueError, match="unavailable"):
            registry.require_reference_match(now_ms=now_ms, **base)  # type: ignore[arg-type]


def test_root_and_transitive_taint_are_canonical_monotonic_and_nonconferring() -> None:
    root = _root_taint()
    assert root.taint_sha256 == owner_private_output_taint_sha256(root)
    assert root.compliance_state == "policy_bound_verbatim_check_pending"
    assert root.declassification_authorized is False
    assert root.confers_execution_authority is False
    child = build_unverified_owner_private_output_taint(
        owner_scope_sha256=_OWNER,
        collective_unit_id=_UNIT,
        collective_preview_sha256=_PREVIEW,
        publication_manifest_sha256=_MANIFEST,
        provider_capability_sha256=_capability().capability_sha256,
        stage_key=_STAGE_VERIFY,
        stage_kind="verifier",
        output_schema="midnight-oil.verifier-output/v1",
        output_sha256="c" * 64,
        upstream_taints=(root,),
    )
    assert child.upstream_taint_sha256s == (root.taint_sha256,)
    assert child.content_class == "personal_reading"
    with pytest.raises(ValueError, match="upstream taint conflicts"):
        build_unverified_owner_private_output_taint(
            owner_scope_sha256="d" * 64,
            collective_unit_id=_UNIT,
            collective_preview_sha256=_PREVIEW,
            publication_manifest_sha256=_MANIFEST,
            provider_capability_sha256=_capability().capability_sha256,
            stage_key=_STAGE_VERIFY,
            stage_kind="verifier",
            output_schema="midnight-oil.verifier-output/v1",
            output_sha256="c" * 64,
            upstream_taints=(root,),
        )


def test_transitive_taint_recomputes_validation_bypassed_parent() -> None:
    bypassed = _root_taint().model_copy(update={"output_sha256": "0" * 64})
    with pytest.raises(ValueError, match="identity conflicts"):
        build_unverified_owner_private_output_taint(
            owner_scope_sha256=_OWNER,
            collective_unit_id=_UNIT,
            collective_preview_sha256=_PREVIEW,
            publication_manifest_sha256=_MANIFEST,
            provider_capability_sha256=_capability().capability_sha256,
            stage_key=_STAGE_VERIFY,
            stage_kind="verifier",
            output_schema="midnight-oil.verifier-output/v1",
            output_sha256="e" * 64,
            upstream_taints=(bypassed,),
        )


def test_taint_requires_private_lineage_and_never_serializes_content() -> None:
    with pytest.raises(ValidationError, match="requires private lineage"):
        build_unverified_owner_private_output_taint(
            owner_scope_sha256=_OWNER,
            collective_unit_id=_UNIT,
            collective_preview_sha256=_PREVIEW,
            publication_manifest_sha256=_MANIFEST,
            provider_capability_sha256=_capability().capability_sha256,
            stage_key=_STAGE_GATHER,
            stage_kind="gather",
            output_schema="midnight-oil.gather-output/v1",
            output_sha256="a" * 64,
        )
    encoded = json.dumps(_root_taint().model_dump(mode="json"), sort_keys=True)
    forbidden = (
        "selection_text",
        "excerpt_text",
        "output_text",
        "signature_ed25519",
        "authorization_id",
        "receipt_sha256",
        "canonical_url",
    )
    assert all(value not in encoded for value in forbidden)


def test_sink_policy_is_exact_owner_private_and_unknown_deny() -> None:
    taint = _root_taint()
    # A policy-bound taint is not a compliance receipt; every byte sink remains
    # closed until a future trusted overlap checker binds a passing receipt.
    for sink in (
        "owner_stage_checkpoint",
        "owner_job_evidence",
        "owner_engagement_document",
        "owner_spawn",
        "owner_twin",
        "authenticated_owner_html",
    ):
        assert not owner_private_sink_currently_authorized(
            taint,
            sink=sink,
            owner_scope_sha256=_OWNER,
            content_class="personal_reading",
        )
    assert not owner_private_sink_currently_authorized(
        taint,
        sink="owner_private_graph",
        owner_scope_sha256=_OWNER,
        content_class="personal_reading",
        policy_tag="private_research",
    )
    for sink in (
        "general_depth_graph",
        "public_serve",
        "portable_export",
        "training_rl",
        "benchmark_content_dataset",
        "log_payload",
        "future_unknown_sink",
    ):
        assert not owner_private_sink_currently_authorized(
            taint,
            sink=sink,
            owner_scope_sha256=_OWNER,
            content_class="personal_reading",
        )
    assert not owner_private_sink_currently_authorized(
        taint,
        sink="owner_twin",
        owner_scope_sha256="e" * 64,
        content_class="personal_reading",
    )
    assert not owner_private_sink_currently_authorized(
        taint,
        sink="owner_private_graph",
        owner_scope_sha256=_OWNER,
        content_class="personal_reading",
        policy_tag="depth",
    )
