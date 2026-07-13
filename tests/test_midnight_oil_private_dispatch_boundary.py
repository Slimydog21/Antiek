from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import cast

import pytest
from pydantic import ValidationError

from acquisition.substack.midnight_oil import StoredAuthorizedSubstackExcerptReader
from substrate.midnight_oil.private_provider_authority import (
    build_owner_private_publication_authority,
)
from substrate.midnight_oil.private_provider_composition import PrivateProviderComposition
from substrate.midnight_oil.private_provider_dispatch import (
    OwnerPrivateDispatchHarnessAuthorityV1,
    OwnerPrivateExactTransportDescriptorV1,
    OwnerPrivatePublicationSourceReceiptV4,
    PreparedOwnerPrivateDispatchV1,
    owner_private_source_receipt_v4_sha256,
    private_input_commitment,
    validate_exact_private_dispatch,
)
from substrate.midnight_oil.private_provider_policy import (
    PrivateProviderCapabilityReferenceRegistry,
    PrivateProviderProcessingCapabilityV1,
)
from substrate.midnight_oil.publication_authority_v2 import (
    ReviewedPublicationAuthorityRowV2,
    SubstackOwnerPrivateExcerptAuthorityV2,
    arxiv_authority_row_v2,
    build_reviewed_publication_manifest_v2,
)
from substrate.midnight_oil.publication_sources import ReviewedPublicationSource
from substrate.midnight_oil.stages import StagePlan, stage_plan_hash
from substrate.midnight_oil.swarm_plan import (
    RoleDispatchPlan,
    SwarmLivePlan,
    build_stage_plan,
    role_dispatch_plan_hash,
    swarm_live_plan_hash,
)
from tests.support.owner_private_dispatch import (
    PrivateTransportResponseFixture,
    invoke_test_transport_once,
)
from tests.test_midnight_oil_private_excerpt_reader import _KEY, _KEY_ID, _fixture
from tests.test_midnight_oil_private_provider_authority import _capability, _registry
from tests.test_midnight_oil_publication_authority_v2 import (
    _arxiv_source,
)
from tests.test_midnight_oil_publication_authority_v2 import (
    _capability as _publication_capability,
)


@dataclass
class _LiveComposition:
    registry: PrivateProviderCapabilityReferenceRegistry
    reloads: int = 0

    def live_reference_registry(
        self, *, now_ms: int
    ) -> PrivateProviderCapabilityReferenceRegistry:
        assert now_ms >= 1_000
        self.reloads += 1
        return self.registry


def _private_capability() -> PrivateProviderProcessingCapabilityV1:
    return cast(PrivateProviderProcessingCapabilityV1, _capability())  # type: ignore[no-untyped-call]


def _swarm(route: str, *, goals_count: int = 1) -> SwarmLivePlan:
    roles = tuple(
        RoleDispatchPlan(
            role=role,  # type: ignore[arg-type]
            allowed_routes=(route,),
            projected_max_cents=1,
            dispatch_config_sha256="4" * 64,
            max_input_tokens=1_024,
            max_prompt_bytes=16_384,
            max_output_tokens=256,
            plan_hash=role_dispatch_plan_hash(
                role=role,
                allowed_routes=(route,),
                projected_max_cents=1,
                dispatch_config_sha256="4" * 64,
                max_input_tokens=1_024,
                max_prompt_bytes=16_384,
                max_output_tokens=256,
            ),
        )
        for role in ("planner", "gatherer", "verifier", "synthesizer")
    )
    material = {
        "goals_count": goals_count,
        "gather_per_goal": 1,
        "source_policy": ("operator_corpus",),
        "roles": roles,
        "projected_total_cents": 4 * goals_count,
    }
    return SwarmLivePlan.model_validate(
        {**material, "plan_hash": swarm_live_plan_hash(**material)}
    )


def _case() -> tuple[
    OwnerPrivateDispatchHarnessAuthorityV1,
    StoredAuthorizedSubstackExcerptReader,
    _LiveComposition,
    OwnerPrivateExactTransportDescriptorV1,
]:
    store, authority, _exact = _fixture()
    capability = _private_capability()
    authority = authority.model_copy(
        update={
            "provider_processing_authority": authority.provider_processing_authority.model_copy(
                update={"capability_sha256": capability.capability_sha256}
            )
        }
    )
    source = ReviewedPublicationSource(
        ref_id=authority.ref_id,
        kind="substack",
        canonical_url=authority.canonical_url,
        external_id=authority.external_id,
        acquisition_mode="substack_bounded_excerpt",
        rights_use="operator_authorized_excerpt",
        max_excerpt_bytes=8_192,
    )
    manifest = build_reviewed_publication_manifest_v2(
        collective_unit_id=authority.collective_unit_id,
        collective_preview_sha256=authority.collective_preview_sha256,
        sources=(ReviewedPublicationAuthorityRowV2(source=source, authority=authority),),
    )
    registry = _registry()
    carrier = build_owner_private_publication_authority(
        manifest, registry=registry, now_ms=2_002, required_until_ms=3_000
    )
    swarm = _swarm(capability.route_key)
    stages = build_stage_plan(
        swarm,
        operation_id="operation-private-1",
        job_id="job-private-1",
        approved_ceiling_cents=swarm.projected_total_cents,
    )
    selected = next(stage for stage in stages.stages if stage.router_role == "gatherer")
    harness = OwnerPrivateDispatchHarnessAuthorityV1(
        owner_scope_sha256=authority.owner_scope_sha256,
        operation_id=stages.operation_id,
        job_id=stages.job_id,
        execution_id="execution-private-1",
        required_until_ms=3_000,
        manifest=manifest,
        carrier=carrier,
        swarm_plan=swarm,
        stage_plan=stages,
        selected_stage_key=selected.stage_key,
    )
    descriptor = OwnerPrivateExactTransportDescriptorV1(
        provider_id=capability.provider_id,
        model_id=capability.model_id,
        route_key=capability.route_key,
        api_mode=capability.api_mode,
        processing_region=capability.processing_region,
        endpoint_origin_sha256=capability.endpoint_origin_sha256,
        account_project_scope_sha256=capability.account_project_scope_sha256,
        adapter_contract_sha256=capability.adapter_contract_sha256,
        dispatch_config_sha256=capability.dispatch_config_sha256,
    )
    return (
        harness,
        StoredAuthorizedSubstackExcerptReader(
            store=store, verification_keys={_KEY_ID: _KEY}
        ),
        _LiveComposition(registry),
        descriptor,
    )


def _prepare(
    *, question: str = "What is the strongest supported claim?"
) -> tuple[PreparedOwnerPrivateDispatchV1, _LiveComposition]:
    harness, reader, composition, descriptor = _case()
    prepared = validate_exact_private_dispatch(
        harness=harness,
        owner_id="alice",
        reader=reader,
        composition=cast(PrivateProviderComposition, composition),
        descriptor=descriptor,
        instruction="Assess only the supplied private excerpts.",
        question=question,
        now_ms=2_002,
    )
    return prepared, composition


def _multi_case(
    *, text_one: str = "First private source — ألف", text_two: str = "Second private source — باء"
) -> tuple[
    OwnerPrivateDispatchHarnessAuthorityV1,
    StoredAuthorizedSubstackExcerptReader,
    _LiveComposition,
    OwnerPrivateExactTransportDescriptorV1,
]:
    from substrate.engagement_spine.store import InMemoryEngagementStore

    store = InMemoryEngagementStore()
    _store, first, _ = _fixture(
        store=store,
        suffix="0001",
        external_id="aone.substack.com/p/private-one",
        text=text_one,
    )
    _store, second, _ = _fixture(
        store=store,
        suffix="0002",
        external_id="ztwo.substack.com/p/private-two",
        text=text_two,
    )
    capability = _private_capability()

    def promoted(
        authority: SubstackOwnerPrivateExcerptAuthorityV2,
    ) -> SubstackOwnerPrivateExcerptAuthorityV2:
        return authority.model_copy(
            update={
                "provider_processing_authority": authority.provider_processing_authority.model_copy(
                    update={"capability_sha256": capability.capability_sha256}
                )
            }
        )

    first = promoted(first)
    second = promoted(second)

    def row(
        authority: SubstackOwnerPrivateExcerptAuthorityV2,
    ) -> ReviewedPublicationAuthorityRowV2:
        return ReviewedPublicationAuthorityRowV2(
            source=ReviewedPublicationSource(
                ref_id=authority.ref_id,
                kind="substack",
                canonical_url=authority.canonical_url,
                external_id=authority.external_id,
                acquisition_mode="substack_bounded_excerpt",
                rights_use="operator_authorized_excerpt",
                max_excerpt_bytes=8_192,
            ),
            authority=authority,
        )

    manifest = build_reviewed_publication_manifest_v2(
        collective_unit_id=first.collective_unit_id,
        collective_preview_sha256=first.collective_preview_sha256,
        sources=(
            row(second),
            arxiv_authority_row_v2(
                _arxiv_source(),
                capability=_publication_capability(),  # type: ignore[no-untyped-call]
            ),
            row(first),
        ),
    )
    registry = _registry()
    carrier = build_owner_private_publication_authority(
        manifest, registry=registry, now_ms=2_002, required_until_ms=3_000
    )
    swarm = _swarm(capability.route_key)
    stages = build_stage_plan(
        swarm,
        operation_id="operation-private-multi",
        job_id="job-private-multi",
        approved_ceiling_cents=swarm.projected_total_cents,
    )
    selected = next(stage for stage in stages.stages if stage.router_role == "gatherer")
    return (
        OwnerPrivateDispatchHarnessAuthorityV1(
            owner_scope_sha256=first.owner_scope_sha256,
            operation_id=stages.operation_id,
            job_id=stages.job_id,
            execution_id="execution-private-multi",
            required_until_ms=3_000,
            manifest=manifest,
            carrier=carrier,
            swarm_plan=swarm,
            stage_plan=stages,
            selected_stage_key=selected.stage_key,
        ),
        StoredAuthorizedSubstackExcerptReader(
            store=store, verification_keys={_KEY_ID: _KEY}
        ),
        _LiveComposition(registry),
        OwnerPrivateExactTransportDescriptorV1(
            provider_id=capability.provider_id,
            model_id=capability.model_id,
            route_key=capability.route_key,
            api_mode=capability.api_mode,
            processing_region=capability.processing_region,
            endpoint_origin_sha256=capability.endpoint_origin_sha256,
            account_project_scope_sha256=capability.account_project_scope_sha256,
            adapter_contract_sha256=capability.adapter_contract_sha256,
            dispatch_config_sha256=capability.dispatch_config_sha256,
        ),
    )


def test_validation_returns_inert_exact_request_and_v4_lineage() -> None:
    prepared, composition = _prepare()
    assert composition.reloads == 1
    assert prepared.confers_execution_authority is False
    assert prepared.private_input_bytes > 0
    assert len(prepared.source_receipts) == 1
    receipt = prepared.source_receipts[0]
    assert receipt.schema_version == 4
    assert receipt.confers_execution_authority is False
    assert receipt.source_acquisition_network_egress is False
    assert receipt.provider_request_sha256 == prepared.provider_request_sha256
    assert b"private-source-0001" in prepared.provider_request_bytes
    for forbidden in (
        receipt.ref_id,
        receipt.source_receipt_id,
        receipt.authorization_id,
        receipt.overlay_id,
    ):
        assert forbidden.encode() not in prepared.provider_request_bytes


def test_private_input_framing_has_literal_multibyte_golden_vector() -> None:
    harness, reader, _composition, _descriptor = _case()
    authority = harness.manifest.sources[0].authority
    assert isinstance(authority, SubstackOwnerPrivateExcerptAuthorityV2)
    excerpt = reader.read(
        owner_id="alice", authority=authority, now_ms=2_002, required_until_ms=3_000
    )
    digest, count = private_input_commitment((excerpt,))
    assert count == len(excerpt.exact_bytes)
    assert digest == "353e5b103dd4910f6977de849286cc3aca9d4ee86e94694f89b89b741cfdd5cd"


@pytest.mark.parametrize(
    "field",
    (
        "provider_id",
        "model_id",
        "route_key",
        "processing_region",
        "endpoint_origin_sha256",
        "account_project_scope_sha256",
        "adapter_contract_sha256",
        "dispatch_config_sha256",
    ),
)
def test_descriptor_substitution_fails_before_an_envelope(field: str) -> None:
    harness, reader, composition, descriptor = _case()
    raw = descriptor.model_dump(mode="python")
    raw[field] = "f" * 64 if field.endswith("sha256") else "changed"
    changed = OwnerPrivateExactTransportDescriptorV1.model_validate(raw)
    with pytest.raises(ValueError):
        validate_exact_private_dispatch(
            harness=harness,
            owner_id="alice",
            reader=reader,
            composition=cast(PrivateProviderComposition, composition),
            descriptor=changed,
            instruction="Assess only the supplied private excerpts.",
            question="What is the strongest supported claim?",
            now_ms=2_002,
        )


def test_test_only_wrapper_calls_one_spy_and_rejects_tool_shapes() -> None:
    prepared, _composition = _prepare()
    calls: list[bytes] = []

    def spy(request: bytes) -> PrivateTransportResponseFixture:
        calls.append(request)
        return PrivateTransportResponseFixture(
            provider_id=prepared.descriptor.provider_id,
            model_id=prepared.descriptor.model_id,
            route_key=prepared.descriptor.route_key,
            output_text="Bounded analysis",
        )

    assert invoke_test_transport_once(prepared, spy).output_text == "Bounded analysis"
    assert calls == [prepared.provider_request_bytes]
    with pytest.raises(ValidationError):
        PrivateTransportResponseFixture.model_validate(
            {
                "provider_id": prepared.descriptor.provider_id,
                "model_id": prepared.descriptor.model_id,
                "route_key": prepared.descriptor.route_key,
                "finish_reason": "tool_use",
                "output_text": "bad",
                "route_index": 0,
                "retry_index": 0,
                "fallback_index": 0,
                "tool_calls": [],
            }
        )


def test_test_only_wrapper_revalidates_constructed_response() -> None:
    prepared, _composition = _prepare()

    def spy(_request: bytes) -> PrivateTransportResponseFixture:
        return PrivateTransportResponseFixture.model_construct(
            provider_id=prepared.descriptor.provider_id,
            model_id=prepared.descriptor.model_id,
            route_key=prepared.descriptor.route_key,
            finish_reason="tool_use",
            output_text="must reject",
            route_index=0,
            retry_index=0,
            fallback_index=0,
        )

    with pytest.raises(ValueError, match="response is invalid"):
        invoke_test_transport_once(prepared, spy)


def test_prepared_envelope_repr_omits_private_request_bytes() -> None:
    canary = "UNIQUE_PREPARED_REPR_CANARY_4cd8"
    prepared, _composition = _prepare(question=canary)
    rendered = repr(prepared)
    assert canary not in rendered
    assert "Exact multibyte research" not in rendered


def _forge_request_texts(
    prepared: PreparedOwnerPrivateDispatchV1, texts: tuple[str, ...]
) -> PreparedOwnerPrivateDispatchV1:
    request = json.loads(prepared.provider_request_bytes)
    assert isinstance(request, dict)
    sources = request["private_sources"]
    assert isinstance(sources, list) and len(sources) == len(texts)
    for source, text in zip(sources, texts, strict=True):
        assert isinstance(source, dict)
        source["text"] = text
    request_bytes = json.dumps(
        request, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    request_hash = hashlib.sha256(
        b"antiek.midnight-oil.provider-request.v1\x00" + request_bytes
    ).hexdigest()
    receipts: list[OwnerPrivatePublicationSourceReceiptV4] = []
    for receipt in prepared.source_receipts:
        raw = receipt.model_dump(mode="python")
        raw["provider_request_sha256"] = request_hash
        digest = owner_private_source_receipt_v4_sha256(raw)
        raw["receipt_sha256"] = digest
        raw["receipt_id"] = "opsr4_" + digest[:24]
        receipts.append(OwnerPrivatePublicationSourceReceiptV4.model_validate(raw))
    return prepared.model_copy(
        update={
            "provider_request_bytes": request_bytes,
            "provider_request_sha256": request_hash,
            "source_receipts": tuple(receipts),
        }
    )


def test_test_wrapper_rejects_self_hashed_substituted_private_text_before_spy() -> None:
    prepared, _composition = _prepare()
    forged = _forge_request_texts(prepared, ("UNAUTHORIZED REPLACEMENT",))
    calls: list[bytes] = []

    def spy(request: bytes) -> PrivateTransportResponseFixture:
        calls.append(request)
        raise AssertionError("spy must remain unreachable")

    with pytest.raises(ValueError, match="envelope is invalid"):
        invoke_test_transport_once(forged, spy)
    assert calls == []


def test_test_wrapper_rejects_self_hashed_multi_source_swap_before_spy() -> None:
    harness, reader, composition, descriptor = _multi_case()
    prepared = validate_exact_private_dispatch(
        harness=harness,
        owner_id="alice",
        reader=reader,
        composition=cast(PrivateProviderComposition, composition),
        descriptor=descriptor,
        instruction="Compare the exact private sources.",
        question="Where do they agree?",
        now_ms=2_002,
    )
    request = json.loads(prepared.provider_request_bytes)
    texts = tuple(source["text"] for source in request["private_sources"])
    forged = _forge_request_texts(prepared, tuple(reversed(texts)))
    calls: list[bytes] = []

    def spy(request_bytes: bytes) -> PrivateTransportResponseFixture:
        calls.append(request_bytes)
        raise AssertionError("spy must remain unreachable")

    with pytest.raises(ValueError, match="envelope is invalid"):
        invoke_test_transport_once(forged, spy)
    assert calls == []


def test_harness_requires_complete_swarm_stage_topology() -> None:
    harness, _reader, _composition, descriptor = _case()
    swarm = _swarm(descriptor.route_key, goals_count=2)
    complete = build_stage_plan(
        swarm,
        operation_id=harness.operation_id,
        job_id=harness.job_id,
        approved_ceiling_cents=swarm.projected_total_cents,
    )
    first_goal = complete.stages[:4]
    partial = StagePlan(
        operation_id=complete.operation_id,
        job_id=complete.job_id,
        approved_ceiling_cents=complete.approved_ceiling_cents,
        stages=first_goal,
        plan_hash=stage_plan_hash(
            operation_id=complete.operation_id,
            job_id=complete.job_id,
            approved_ceiling_cents=complete.approved_ceiling_cents,
            stages=first_goal,
        ),
    )
    raw = harness.model_dump(mode="python")
    raw.update(
        swarm_plan=swarm,
        stage_plan=partial,
        selected_stage_key=next(
            row.stage_key for row in partial.stages if row.router_role == "gatherer"
        ),
    )
    with pytest.raises(ValidationError):
        OwnerPrivateDispatchHarnessAuthorityV1.model_validate(raw)


def test_v4_unknown_fields_and_identity_mutation_reject() -> None:
    prepared, _composition = _prepare()
    raw = prepared.source_receipts[0].model_dump(mode="python")
    raw["unknown"] = True
    with pytest.raises(ValidationError):
        OwnerPrivatePublicationSourceReceiptV4.model_validate(raw)
    changed = prepared.source_receipts[0].model_copy(update={"job_id": "other-job"})
    with pytest.raises(ValueError, match="identity conflicts"):
        OwnerPrivatePublicationSourceReceiptV4.model_validate(
            changed.model_dump(mode="python")
        )


def test_private_request_validation_errors_are_content_free() -> None:
    harness, reader, composition, descriptor = _case()
    canary = "UNIQUE_PRIVATE_CANARY_91f4"
    with pytest.raises(ValueError) as raised:
        validate_exact_private_dispatch(
            harness=harness,
            owner_id="alice",
            reader=reader,
            composition=cast(PrivateProviderComposition, composition),
            descriptor=descriptor,
            instruction=f"before {canary}\x00 after",
            question="bounded question",
            now_ms=2_002,
        )
    assert canary not in str(raised.value)
    assert canary not in repr(raised.value)


def test_test_wrapper_revalidates_mixed_envelopes_before_spy() -> None:
    first, _composition = _prepare(question="first exact question")
    second, _composition = _prepare(question="second exact question")
    mixed = first.model_copy(update={"source_receipts": second.source_receipts})
    calls: list[bytes] = []

    def spy(request: bytes) -> PrivateTransportResponseFixture:
        calls.append(request)
        return PrivateTransportResponseFixture(
            provider_id=first.descriptor.provider_id,
            model_id=first.descriptor.model_id,
            route_key=first.descriptor.route_key,
            output_text="should not run",
        )

    with pytest.raises(ValueError, match="envelope is invalid"):
        invoke_test_transport_once(mixed, spy)
    assert calls == []


def test_mixed_manifest_uses_complete_canonical_private_subset_only() -> None:
    harness, reader, composition, descriptor = _multi_case()
    prepared = validate_exact_private_dispatch(
        harness=harness,
        owner_id="alice",
        reader=reader,
        composition=cast(PrivateProviderComposition, composition),
        descriptor=descriptor,
        instruction="Compare the exact private sources.",
        question="Where do they agree?",
        now_ms=2_002,
    )
    assert len(prepared.source_receipts) == 2
    assert tuple(row.private_source_ordinal for row in prepared.source_receipts) == (1, 2)
    assert b"private-source-0001" in prepared.provider_request_bytes
    assert b"private-source-0002" in prepared.provider_request_bytes
    assert b"1706.03762" not in prepared.provider_request_bytes
    assert prepared.private_input_bytes == len("First private source — ألف".encode()) + len(
        "Second private source — باء".encode()
    )


def test_aggregate_private_byte_cap_is_exact() -> None:
    harness, reader, composition, descriptor = _multi_case(
        text_one="a" * 4_096, text_two="b" * 4_096
    )
    exact = validate_exact_private_dispatch(
        harness=harness,
        owner_id="alice",
        reader=reader,
        composition=cast(PrivateProviderComposition, composition),
        descriptor=descriptor,
        instruction="Compare.",
        question="Answer.",
        now_ms=2_002,
    )
    assert exact.private_input_bytes == 8_192

    harness, reader, composition, descriptor = _multi_case(
        text_one="a" * 4_096, text_two="b" * 4_097
    )
    with pytest.raises(ValueError, match="validation failed"):
        validate_exact_private_dispatch(
            harness=harness,
            owner_id="alice",
            reader=reader,
            composition=cast(PrivateProviderComposition, composition),
            descriptor=descriptor,
            instruction="Compare.",
            question="Answer.",
            now_ms=2_002,
        )
