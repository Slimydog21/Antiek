from __future__ import annotations

import pytest
from pydantic import ValidationError

from substrate.midnight_oil.private_provider_envelope_v2 import (
    PreparedOwnerPrivateEnvelopeV2,
    build_prepared_owner_private_envelope_v2,
    prepared_owner_private_envelope_v2_sha256,
)
from substrate.midnight_oil.private_provider_receipt_v5 import (
    build_owner_private_source_receipt_v5,
)
from substrate.midnight_oil.private_provider_request_core_v2 import (
    PreparedOwnerPrivateRequestCoreV2,
    build_owner_private_planner_request_core_v2,
    build_owner_private_request_core_v2,
    owner_private_request_core_v2_sha256,
    signed_owner_private_planner_prompt_authority_v2,
)
from tests.test_midnight_oil_private_dispatch_boundary import (
    _case as _dispatch_case,
)
from tests.test_midnight_oil_private_dispatch_boundary import (
    _prepare,
)
from tests.test_midnight_oil_publication_receipt_v5 import (
    _matching_capability_v2,
    _public,
    _registry,
)

_PROMPT_PRIVATE = bytes(value ^ 0xA5 for value in range(32))
_PROMPT_KEY_ID = "owner-private-planner-prompt-fixture"


def _case() -> tuple[PreparedOwnerPrivateRequestCoreV2, PreparedOwnerPrivateEnvelopeV2]:
    prepared, _composition = _prepare()
    capability = _matching_capability_v2()
    registry = _registry(capability)
    core = build_owner_private_request_core_v2(
        prepared_v1=prepared,
        capability_sha256=capability.capability_sha256,
        registry=registry,
        now_ms=2_002,
    )
    receipt = build_owner_private_source_receipt_v5(
        source=prepared.source_receipts[0],
        request_core=core,
        capability_sha256=capability.capability_sha256,
        registry=registry,
        now_ms=2_002,
    )
    return core, build_prepared_owner_private_envelope_v2(
        request_core=core, receipts=(receipt,)
    )


def test_request_core_and_envelope_are_distinct_content_addressed_nonconferring() -> None:
    core, envelope = _case()
    assert core.request_core_sha256 == owner_private_request_core_v2_sha256(core)
    assert envelope.envelope_sha256 == prepared_owner_private_envelope_v2_sha256(
        envelope
    )
    assert envelope.request_core_v2_sha256 == core.request_core_sha256
    assert envelope.receipt_v5_roster[0].ordinal == 1
    assert core.route_source_evidence_confers_request_authority is False
    assert envelope.confers_execution_authority is False
    assert envelope.production_consumer_enabled is False


@pytest.mark.parametrize(
    "field",
    (
        "provider_effect_key",
        "output_schema",
        "provider_capability_v2_sha256",
        "output_policy_v2_sha256",
        "provider_request_bytes",
        "request_core_sha256",
    ),
)
def test_request_core_substitution_mutations_reject(field: str) -> None:
    core, _envelope = _case()
    raw = core.model_dump(mode="python")
    raw[field] = b"{}" if field == "provider_request_bytes" else "0" * 64
    with pytest.raises((ValidationError, ValueError)):
        PreparedOwnerPrivateRequestCoreV2.model_validate(raw)


def test_envelope_rejects_core_or_receipt_roster_substitution() -> None:
    core, envelope = _case()
    raw = envelope.model_dump(mode="python")
    raw["request_core_v2_sha256"] = "0" * 64
    with pytest.raises((ValidationError, ValueError)):
        PreparedOwnerPrivateEnvelopeV2.model_validate(raw)
    with pytest.raises(ValueError, match="count conflicts"):
        build_prepared_owner_private_envelope_v2(request_core=core, receipts=())


def test_core_and_envelope_repr_do_not_expose_private_text() -> None:
    core, envelope = _case()
    canary = core.private_sources[0].text
    assert canary not in repr(core)
    assert canary not in repr(envelope)
    assert "redacted=True" in repr(core)
    assert "redacted=True" in repr(envelope)


def test_core_builder_rejects_forged_structural_descriptor_and_request_hash() -> None:
    prepared, _composition = _prepare()
    capability = _matching_capability_v2()
    registry = _registry(capability)
    forged_descriptor = prepared.descriptor.model_copy(update={"provider_id": "evil"})
    forged = prepared.model_copy(update={"descriptor": forged_descriptor})
    with pytest.raises(ValueError, match="authority conflicts"):
        build_owner_private_request_core_v2(
            prepared_v1=forged,
            capability_sha256=capability.capability_sha256,
            registry=registry,
            now_ms=2_002,
        )
    forged_hash = prepared.model_copy(update={"provider_request_sha256": "0" * 64})
    with pytest.raises(ValueError, match="authority conflicts"):
        build_owner_private_request_core_v2(
            prepared_v1=forged_hash,
            capability_sha256=capability.capability_sha256,
            registry=registry,
            now_ms=2_002,
        )


def test_v5_and_envelope_revalidate_model_copy_identities() -> None:
    prepared, _composition = _prepare()
    capability = _matching_capability_v2()
    registry = _registry(capability)
    core = build_owner_private_request_core_v2(
        prepared_v1=prepared,
        capability_sha256=capability.capability_sha256,
        registry=registry,
        now_ms=2_002,
    )
    forged_core = core.model_copy(update={"request_core_sha256": "0" * 64})
    with pytest.raises(ValueError, match="authority is unavailable"):
        build_owner_private_source_receipt_v5(
            source=prepared.source_receipts[0],
            request_core=forged_core,
            capability_sha256=capability.capability_sha256,
            registry=registry,
            now_ms=2_002,
        )
    receipt = build_owner_private_source_receipt_v5(
        source=prepared.source_receipts[0],
        request_core=core,
        capability_sha256=capability.capability_sha256,
        registry=registry,
        now_ms=2_002,
    )
    forged_receipt = receipt.model_copy(update={"checker_sha256": "0" * 64})
    with pytest.raises(ValueError, match="authority is unavailable"):
        build_prepared_owner_private_envelope_v2(
            request_core=core, receipts=(forged_receipt,)
        )


def test_zero_source_planner_core_and_empty_envelope_are_constructible() -> None:
    harness, _reader, _composition, descriptor = _dispatch_case()
    capability = _matching_capability_v2()
    registry = _registry(capability)
    planner = harness.stage_plan.stages[0]
    assert planner.kind == "planner"
    prompt = signed_owner_private_planner_prompt_authority_v2(
        owner_scope_sha256=harness.owner_scope_sha256,
        operation_id=harness.operation_id,
        job_id=harness.job_id,
        execution_id=harness.execution_id,
        swarm_plan_sha256=harness.swarm_plan.plan_hash,
        stage_plan_sha256=harness.stage_plan.plan_hash,
        selected_stage_key=planner.stage_key,
        goal_index=planner.goal_index,
        goal="Establish the strongest supported private claim.",
        instruction="Plan the owner question without publication sources.",
        question="What should this private investigation establish?",
        context="Owner-approved fixture context.",
        key_id=_PROMPT_KEY_ID,
        signing_key=_PROMPT_PRIVATE,
    )
    core = build_owner_private_planner_request_core_v2(
        prompt_authority=prompt,
        prompt_authority_verification_keys={
            _PROMPT_KEY_ID: _public(_PROMPT_PRIVATE)
        },
        swarm_plan=harness.swarm_plan,
        stage_plan=harness.stage_plan,
        descriptor=descriptor,
        capability_sha256=capability.capability_sha256,
        registry=registry,
        required_until_ms=harness.required_until_ms,
        now_ms=2_002,
    )
    assert core.router_role == "planner"
    assert core.private_sources == ()
    assert core.publication_manifest_sha256 is None
    envelope = build_prepared_owner_private_envelope_v2(
        request_core=core, receipts=()
    )
    assert envelope.receipt_v5_roster == ()
    substituted = prompt.model_copy(update={"question": "UNRELATED SUBSTITUTE B"})
    with pytest.raises(ValueError, match="authority is unavailable"):
        build_owner_private_planner_request_core_v2(
            prompt_authority=substituted,
            prompt_authority_verification_keys={
                _PROMPT_KEY_ID: _public(_PROMPT_PRIVATE)
            },
            swarm_plan=harness.swarm_plan,
            stage_plan=harness.stage_plan,
            descriptor=descriptor,
            capability_sha256=capability.capability_sha256,
            registry=registry,
            required_until_ms=harness.required_until_ms,
            now_ms=2_002,
        )
