"""Typed-payload tests for the schema-v4 additions.

Covers:
  - RLMBridgeDecidedPayload (orchestration.rlm.bridge.RLMBridgeDecision
    → typed payload conversion)
  - QualityGateEvaluatedPayload
  - CrossGraphCitationRecordedPayload
  - RevShareDecidedPayload
  - PreferenceObservationRecordedPayload

Each payload is exercised through Pydantic validation + the
discriminated-union TypeAdapter to confirm the action_type discriminator
routes correctly.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import TypeAdapter, ValidationError

from substrate.schemas.events import (
    EVENT_SCHEMA_VERSION,
    TYPED_PAYLOAD_ACTION_TYPES,
    ActionType,
    CrossGraphCitationRecordedPayload,
    Event,
    PreferenceObservationRecordedPayload,
    QualityGateEvaluatedPayload,
    RLMBridgeDecidedPayload,
    RevShareDecidedPayload,
    SkillRulePromotedPayload,
    TypedPayload,
)


def test_schema_version_bumped_past_v4():
    """The Sprint 17-30+ wave bumped to v4; v5 followed with the
    dedicated SKILL_RULE_PROMOTED payload. The test only enforces a
    monotonic floor so future bumps don't require touching this file."""
    assert EVENT_SCHEMA_VERSION >= 4


def test_all_action_types_in_typed_union():
    for at in (
        ActionType.RLM_BRIDGE_DECIDED,
        ActionType.QUALITY_GATE_EVALUATED,
        ActionType.CROSS_GRAPH_CITATION_RECORDED,
        ActionType.REV_SHARE_DECIDED,
        ActionType.PREFERENCE_OBSERVATION_RECORDED,
        ActionType.SKILL_RULE_PROMOTED,
    ):
        assert at.value in TYPED_PAYLOAD_ACTION_TYPES, at


# ── SkillRulePromotedPayload (v5) ─────────────────────────────────


def test_skill_rule_promoted_payload_roundtrips():
    p = SkillRulePromotedPayload(
        rule_id="skill-abc",
        rule_text="Lukin lab papers are tier 1",
        rule_kind="source_tier_rule",
        domain="quantum",
        distinct_user_count=4,
        total_epsilon_consumed=0.05,
        confidence="moderate",
        contributing_user_ids=["u1", "u2", "u3", "u4"],
    )
    from pydantic import TypeAdapter
    adapter = TypeAdapter(TypedPayload)
    re = adapter.validate_python(p.model_dump())
    assert isinstance(re, SkillRulePromotedPayload)
    assert re.distinct_user_count == 4
    assert re.confidence == "moderate"


def test_skill_rule_promoted_payload_caps_epsilon_at_10():
    import pytest as _pytest
    from pydantic import ValidationError as _VE
    with _pytest.raises(_VE):
        SkillRulePromotedPayload(
            rule_id="x",
            rule_text="x",
            rule_kind="x",
            domain="x",
            distinct_user_count=1,
            total_epsilon_consumed=11.0,  # exceeds §16.2 cap
            confidence="low",
        )


# ── RLMBridgeDecidedPayload ─────────────────────────────────────────


def test_rlm_bridge_payload_roundtrip():
    p = RLMBridgeDecidedPayload(
        document_id_ref="doc-1",
        estimated_tokens=128_000,
        threshold_tokens=64_000,
        above_threshold=True,
        ratified=False,
        escalated=False,
        session_id=None,
        reason="deferred_pending_ratification",
    )
    # Discriminator routes via the union.
    adapter = TypeAdapter(TypedPayload)
    re = adapter.validate_python(p.model_dump())
    assert isinstance(re, RLMBridgeDecidedPayload)
    assert re.reason == "deferred_pending_ratification"


def test_rlm_bridge_payload_rejects_bad_reason():
    with pytest.raises(ValidationError):
        RLMBridgeDecidedPayload(
            document_id_ref="d",
            estimated_tokens=1,
            threshold_tokens=1,
            above_threshold=False,
            ratified=False,
            escalated=False,
            reason="not_a_known_reason",  # type: ignore[arg-type]
        )


def test_rlm_bridge_decision_to_payload_normalizes_reason():
    """The free-form 'escalated_to_rlm cap_usd=5.00' decision-reason
    is normalized to the Literal 'escalated_to_rlm' on conversion."""
    from orchestration.rlm.bridge import RLMBridgeDecision

    d = RLMBridgeDecision(
        document_id="doc-X",
        investigation_id="inv-1",
        estimated_tokens=128_000,
        threshold_tokens=64_000,
        above_threshold=True,
        ratified=True,
        escalated=True,
        session_id="rlm-deadbeef",
        reason="escalated_to_rlm cap_usd=5.00",
    )
    p = d.to_typed_payload()
    assert isinstance(p, RLMBridgeDecidedPayload)
    assert p.reason == "escalated_to_rlm"
    assert p.session_id == "rlm-deadbeef"


# ── QualityGateEvaluatedPayload ────────────────────────────────────


def test_quality_gate_payload_constraints():
    """Pydantic constraints: rubric-fraction fields stay in [0, 1]."""
    p = QualityGateEvaluatedPayload(
        target_kind="notebook",
        target_id="nb-1",
        accepted=True,
        verification_passed=True,
        voice_style_passed=True,
        source_tier_passed=True,
        em_dash_density=0.5,
        padding_phrase_count=0,
        sector_vocab_overlap=0.6,
        min_tier_cited=2,
        pct_tier_1_or_2=0.9,
        reasons=[],
    )
    assert p.accepted is True
    # pct_tier_1_or_2 > 1.0 must fail.
    with pytest.raises(ValidationError):
        QualityGateEvaluatedPayload(
            target_kind="notebook",
            target_id="nb-1",
            accepted=True,
            verification_passed=True,
            voice_style_passed=True,
            source_tier_passed=True,
            em_dash_density=0.5,
            padding_phrase_count=0,
            sector_vocab_overlap=0.6,
            min_tier_cited=2,
            pct_tier_1_or_2=1.5,
            reasons=[],
        )


def test_quality_gate_payload_target_kind_literal():
    with pytest.raises(ValidationError):
        QualityGateEvaluatedPayload(
            target_kind="other",  # type: ignore[arg-type]
            target_id="x",
            accepted=False,
            verification_passed=False,
            voice_style_passed=False,
            source_tier_passed=False,
            em_dash_density=0.0,
            padding_phrase_count=0,
            sector_vocab_overlap=0.0,
            min_tier_cited=5,
            pct_tier_1_or_2=0.0,
            reasons=[],
        )


# ── CrossGraphCitationRecordedPayload ──────────────────────────────


def test_cross_graph_citation_payload_same_substrate():
    p = CrossGraphCitationRecordedPayload(
        reference_id="xref-abc",
        referencing_user_id="user-B",
        referencing_investigation_id="inv-1",
        referenced_user_id="user-A",
        referenced_note_id="note-7",
    )
    assert p.federated_substrate_id is None  # default


def test_cross_graph_citation_payload_federation():
    p = CrossGraphCitationRecordedPayload(
        reference_id="xref-fed",
        referencing_user_id="user-B",
        referencing_investigation_id="inv-1",
        referenced_user_id="user-Z",
        referenced_note_id="note-99",
        federated_substrate_id="partner-coop",
    )
    assert p.federated_substrate_id == "partner-coop"


# ── RevShareDecidedPayload ─────────────────────────────────────────


def test_rev_share_payload_kind_literal():
    """Only creator/publisher/platform are valid kinds (mirrors
    RevShareKind in substrate.ad_inventory.payout)."""
    for kind in ("creator", "publisher", "platform"):
        p = RevShareDecidedPayload(
            decision_id="rs-1",
            impression_id="imp-1",
            kind=kind,  # type: ignore[arg-type]
            recipient_ref="user-X",
            amount_usd_cents=100,
        )
        assert p.kind == kind
    with pytest.raises(ValidationError):
        RevShareDecidedPayload(
            decision_id="rs-1",
            impression_id="imp-1",
            kind="other",  # type: ignore[arg-type]
            recipient_ref="user-X",
            amount_usd_cents=100,
        )


def test_rev_share_payload_amount_nonnegative():
    with pytest.raises(ValidationError):
        RevShareDecidedPayload(
            decision_id="rs-1",
            impression_id="imp-1",
            kind="creator",
            recipient_ref="user-X",
            amount_usd_cents=-1,
        )


# ── PreferenceObservationRecordedPayload ──────────────────────────


def test_preference_observation_payload_requires_positive_epsilon():
    with pytest.raises(ValidationError):
        PreferenceObservationRecordedPayload(
            category="cat",
            noisy_value=True,
            per_obs_epsilon=0.0,  # gt=0.0 → must reject
            cumulative_epsilon_spent=0.0,
            category_budget=10.0,
            user_id="__operator__",
        )


def test_preference_observation_payload_carries_budget_state():
    p = PreferenceObservationRecordedPayload(
        category="dispatch_followed",
        noisy_value=True,
        per_obs_epsilon=0.01,
        cumulative_epsilon_spent=0.05,
        category_budget=4.0,
        user_id="__operator__",
    )
    assert p.cumulative_epsilon_spent < p.category_budget


# ── Event-envelope discriminator routing ───────────────────────────


def test_event_envelope_round_trips_new_payload():
    """Full Event envelope round-trips with a v4 payload."""
    e = Event(
        event_id="evt-1",
        investigation_id="inv-1",
        action_type=ActionType.RLM_BRIDGE_DECIDED,
        payload=RLMBridgeDecidedPayload(
            document_id_ref="doc-1",
            estimated_tokens=80_000,
            threshold_tokens=64_000,
            above_threshold=True,
            ratified=False,
            escalated=False,
            reason="deferred_pending_ratification",
        ),
        param_version="test-v0",
        emitted_at=datetime.now(timezone.utc),
    )
    serialized = e.model_dump()
    restored = Event.model_validate(serialized)
    assert isinstance(restored.payload, RLMBridgeDecidedPayload)
    assert restored.payload.reason == "deferred_pending_ratification"
