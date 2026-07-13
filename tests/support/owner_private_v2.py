"""Central fixture authority graph for owner-private V2 adapter tests.

Only tests import this module.  It deliberately builds the complete V1 -> V2 ->
V5 -> envelope graph so adapter tests do not assemble partially trusted rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, cast

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from substrate.midnight_oil.live_roles import (
    SynthesizerOutput,
    VerifierOutput,
    canonical_role_output,
)
from substrate.midnight_oil.private_provider_capability_v2 import (
    PrivateProviderCapabilityV2ReferenceRegistry,
    PrivateProviderProcessingCapabilityV2,
    signed_private_provider_capability_v2,
)
from substrate.midnight_oil.private_provider_composition import (
    PrivateProviderComposition,
    signed_private_provider_revocation_head,
)
from substrate.midnight_oil.private_provider_dispatch import (
    PreparedOwnerPrivateDispatchV1,
    validate_exact_private_dispatch,
)
from substrate.midnight_oil.private_provider_envelope_v2 import (
    PreparedOwnerPrivateEnvelopeV2,
    build_prepared_owner_private_envelope_v2,
)
from substrate.midnight_oil.private_provider_policy import (
    signed_private_provider_revocation_snapshot,
)
from substrate.midnight_oil.private_provider_receipt_v5 import (
    OwnerPrivatePublicationSourceReceiptV5,
    build_owner_private_source_receipt_v5,
)
from substrate.midnight_oil.private_provider_request_core_v2 import (
    PreparedOwnerPrivateRequestCoreV2,
    build_owner_private_planner_request_core_v2,
    build_owner_private_request_core_v2,
    signed_owner_private_planner_prompt_authority_v2,
)
from tests.test_midnight_oil_private_dispatch_boundary import (
    _case as _dispatch_case,
)
from tests.test_midnight_oil_private_dispatch_boundary import (
    _multi_case as _dispatch_multi_case,
)
from tests.test_midnight_oil_private_dispatch_boundary import (
    _prepare as _dispatch_prepare,
)
from tests.test_midnight_oil_private_dispatch_boundary import _private_capability
from tests.test_midnight_oil_private_provider_authority import (
    _CAP_KEY_ID,
    _CAP_PRIVATE,
    _REV_KEY_ID,
    _REV_PRIVATE,
)

NOW_MS = 2_002
REQUIRED_UNTIL_MS = 3_000
PRIVATE_CANARY = "OWNER_PRIVATE_ADAPTER_CANARY_7f31"

_V2_PRIVATE = bytes(value ^ 0x55 for value in range(32))
_V2_KEY_ID = "private-capability-v2-issuer"
_PROMPT_PRIVATE = bytes(value ^ 0xA5 for value in range(32))
_PROMPT_KEY_ID = "owner-private-planner-prompt-fixture"


def public_key(private: bytes) -> bytes:
    return (
        Ed25519PrivateKey.from_private_bytes(private)
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )


def matching_capability_v2(
    *, expires_at_ms: int = 100_000
) -> PrivateProviderProcessingCapabilityV2:
    return signed_private_provider_capability_v2(
        route_evidence=_private_capability(),
        max_output_bytes=500_000,
        revocation_epoch=2,
        issued_at_ms=1_000,
        not_before_ms=1_000,
        expires_at_ms=expires_at_ms,
        key_id=_V2_KEY_ID,
        signing_key=_V2_PRIVATE,
    )


def capability_registry(
    capability: PrivateProviderProcessingCapabilityV2,
    *,
    revoked: tuple[str, ...] = (),
) -> PrivateProviderCapabilityV2ReferenceRegistry:
    snapshot = signed_private_provider_revocation_snapshot(
        epoch=2,
        issued_at_ms=2_000,
        revoked_capability_sha256s=revoked,
        key_id=_REV_KEY_ID,
        signing_key=_REV_PRIVATE,
    )
    head = signed_private_provider_revocation_head(
        snapshot=snapshot,
        previous_head_sha256="f" * 64,
        key_id=_REV_KEY_ID,
        signing_key=_REV_PRIVATE,
    )
    return PrivateProviderCapabilityV2ReferenceRegistry(
        (capability,),
        capability_v2_verification_keys={_V2_KEY_ID: public_key(_V2_PRIVATE)},
        route_evidence_verification_keys={_CAP_KEY_ID: public_key(_CAP_PRIVATE)},
        revocation_verification_keys={_REV_KEY_ID: public_key(_REV_PRIVATE)},
        trusted_floor_sha256=head.head_sha256,
        current_head_chain=(head,),
    )


@dataclass(frozen=True)
class OwnerPrivateV2Case:
    prepared_v1: PreparedOwnerPrivateDispatchV1 | None
    capability: PrivateProviderProcessingCapabilityV2
    registry: PrivateProviderCapabilityV2ReferenceRegistry
    core: PreparedOwnerPrivateRequestCoreV2
    receipts: tuple[OwnerPrivatePublicationSourceReceiptV5, ...]
    envelope: PreparedOwnerPrivateEnvelopeV2

    @property
    def source_texts(self) -> tuple[str, ...]:
        return tuple(source.text for source in self.core.private_sources)


def _complete_case(prepared: PreparedOwnerPrivateDispatchV1) -> OwnerPrivateV2Case:
    capability = matching_capability_v2()
    registry = capability_registry(capability)
    core = build_owner_private_request_core_v2(
        prepared_v1=prepared,
        capability_sha256=capability.capability_sha256,
        registry=registry,
        now_ms=NOW_MS,
    )
    receipts = tuple(
        build_owner_private_source_receipt_v5(
            source=source,
            request_core=core,
            capability_sha256=capability.capability_sha256,
            registry=registry,
            now_ms=NOW_MS,
        )
        for source in prepared.source_receipts
    )
    envelope = build_prepared_owner_private_envelope_v2(request_core=core, receipts=receipts)
    return OwnerPrivateV2Case(prepared, capability, registry, core, receipts, envelope)


def owner_private_v2_case(
    *,
    canary: bool = False,
    role: Literal["gatherer", "verifier", "synthesizer"] = "gatherer",
) -> OwnerPrivateV2Case:
    question = PRIVATE_CANARY if canary else "What is the strongest supported claim?"
    if role == "gatherer":
        prepared, _composition = _dispatch_prepare(question=question)
    else:
        harness, reader, composition, descriptor = _dispatch_case()
        selected = next(
            stage for stage in harness.stage_plan.stages if stage.router_role == role
        )
        prepared = validate_exact_private_dispatch(
            harness=harness.model_copy(
                update={"selected_stage_key": selected.stage_key}
            ),
            owner_id="alice",
            reader=reader,
            composition=cast(PrivateProviderComposition, composition),
            descriptor=descriptor,
            instruction="Assess only the supplied private excerpts.",
            question=question,
            now_ms=NOW_MS,
        )
    return _complete_case(prepared)


def owner_private_v2_multi_case() -> OwnerPrivateV2Case:
    harness, reader, composition, descriptor = _dispatch_multi_case()
    prepared = validate_exact_private_dispatch(
        harness=harness,
        owner_id="alice",
        reader=reader,
        composition=cast(PrivateProviderComposition, composition),
        descriptor=descriptor,
        instruction="Compare the exact private sources.",
        question="Where do they agree?",
        now_ms=NOW_MS,
    )
    return _complete_case(prepared)


def owner_private_v2_planner_case() -> OwnerPrivateV2Case:
    harness, _reader, _composition, descriptor = _dispatch_case()
    capability = matching_capability_v2()
    registry = capability_registry(capability)
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
        prompt_authority_verification_keys={_PROMPT_KEY_ID: public_key(_PROMPT_PRIVATE)},
        swarm_plan=harness.swarm_plan,
        stage_plan=harness.stage_plan,
        descriptor=descriptor,
        capability_sha256=capability.capability_sha256,
        registry=registry,
        required_until_ms=harness.required_until_ms,
        now_ms=NOW_MS,
    )
    envelope = build_prepared_owner_private_envelope_v2(request_core=core, receipts=())
    return OwnerPrivateV2Case(None, capability, registry, core, (), envelope)


def gatherer_output_bytes(*, claim: str = "Independent bounded conclusion.") -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "role": "gatherer",
            "question_id": "q-1",
            "evidence": [
                {
                    "evidence_id": "ev-0123456789abcdef",
                    "source_receipt_id": "test-receipt",
                    "document_id": "test-document",
                    "chunk_id": "test-chunk",
                    "excerpt_sha256": "a" * 64,
                    "claim": claim,
                    "relevance": "Directly relevant to the bounded question.",
                    "limitations": [],
                }
            ],
            "search_limitations": [],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def planner_output_bytes() -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "role": "planner",
            "research_frame": "Bounded owner-private planning frame.",
            "questions": [
                {
                    "question_id": "q-1",
                    "question": "What evidence would resolve the claim?",
                    "inclusion_criteria": ["Direct evidence"],
                    "exclusion_criteria": [],
                    "expected_evidence_types": ["Primary source"],
                    "falsifiers": ["Contradictory primary evidence"],
                }
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def verifier_output_bytes() -> bytes:
    return canonical_role_output(
        VerifierOutput.model_validate_json(
            json.dumps({
                "schema_version": 1,
                "role": "verifier",
                "findings": [
                    {
                        "finding_id": "vf-0123456789abcdef",
                        "proposition_id": "prop-0123456789abcdef",
                        "question_id": "q-1",
                        "claim": "The bounded claim was assessed.",
                        "status": "supported",
                        "evidence_ids": ["ev-0123456789abcdef"],
                        "rationale": "The cited evidence supports the disposition.",
                        "missing_evidence": [],
                    }
                ],
                "evidence_dispositions": [
                    {
                        "evidence_id": "ev-0123456789abcdef",
                        "question_id": "q-1",
                        "disposition": "considered_support",
                        "rationale": "Explicitly assessed.",
                    }
                ],
            })
        )
    )


def synthesizer_output_bytes() -> bytes:
    return canonical_role_output(
        SynthesizerOutput.model_validate_json(
            json.dumps({
                "schema_version": 1,
                "role": "synthesizer",
                "claims": [
                    {
                        "claim_id": "cl-0123456789abcdef",
                        "proposition_id": "prop-0123456789abcdef",
                        "text": "The bounded claim was assessed.",
                        "finding_id": "vf-0123456789abcdef",
                        "evidence_ids": ["ev-0123456789abcdef"],
                        "confidence": "low",
                    }
                ],
                "summary_claim_ids": ["cl-0123456789abcdef"],
                "addressed_contradictions": [],
                "addressed_gaps": [],
                "limitations": ["Operator corpus only"],
                "open_questions": ["Would external evidence change the result?"],
            })
        )
    )


__all__ = [
    "NOW_MS",
    "PRIVATE_CANARY",
    "OwnerPrivateV2Case",
    "capability_registry",
    "gatherer_output_bytes",
    "matching_capability_v2",
    "owner_private_v2_case",
    "owner_private_v2_multi_case",
    "owner_private_v2_planner_case",
    "planner_output_bytes",
    "synthesizer_output_bytes",
    "verifier_output_bytes",
]
