"""Tests for the typed event schema (substrate/schemas/events.py) and its
write integration via substrate/event_log/events.py.

What this file proves:

1. Every typed payload variant round-trips through model_dump_json →
   model_validate_json with the discriminator preserving variant identity.
2. The discriminator rejects a mismatched (envelope action_type, payload
   variant) pair at construction time.
3. The wrestling-loop validator enforces document_id on the 16 wrestling
   action types whose semantics depend on a source document.
4. Non-wrestling typed events (DispatchCall, ContextPackAssembled,
   CrossDocQuestionAnswered) do NOT require document_id.
5. emit_typed writes a row that round-trips back to the same typed
   variant via Event.model_validate.
6. Timestamps serialize with the legacy 'Z' suffix.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

# Make the project root importable without a separate conftest.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from substrate.constants import CONFIDENCE_LEVELS  # noqa: E402
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    WRESTLING_ACTION_TYPES,
    ActionType,
    ArtifactGeneratedPayload,
    ArtifactInteractedPayload,
    Claim,
    ClaimChallengeRaisedPayload,
    ClaimGroundingCheckFailedPayload,
    ClaimGroundingCheckPassedPayload,
    ContextLayer,
    ContextPackAssembledPayload,
    CrossDocQuestionAnsweredPayload,
    DispatchCallPayload,
    DistillationDeliveredPayload,
    DistillationRequestedPayload,
    DocumentLoadedPayload,
    DocumentRegionSelectedPayload,
    Event,
    NoteCompressedDocWrittenPayload,
    NoteEmergedPayload,
    NoteRefinedPayload,
    QuestionEscalatedToResearchPayload,
    QuestionIdentifiedPayload,
    QuestionResolvedByDocPayload,
    UserAcceptDistillationPayload,
    UserEditDistillationPayload,
    UserRejectDistillationPayload,
)

# ---------------------------------------------------------------------------
# Helpers — one valid instance per variant.
# ---------------------------------------------------------------------------


def _now_naive() -> datetime:
    """Naive UTC datetime; the field_serializer appends 'Z'."""
    return datetime(2026, 5, 16, 12, 0, 0)


def _make_payload(at: ActionType):
    """Return a valid payload instance for the given action_type. Centralized
    so the round-trip test, the discriminator-mismatch test, and the
    document_id test all use the same set of constructors.
    """
    if at == ActionType.DISPATCH_CALL:
        return DispatchCallPayload(
            provider="openai-compat", model="deepseek-flash-v4", tier="flash",
            target_role="decomposer", input_tokens=1200, output_tokens=350,
            cost_usd=0.0042, latency_ms=890, prompt_hash="sha256:abc",
        )
    if at == ActionType.CONTEXT_PACK_ASSEMBLED:
        return ContextPackAssembledPayload(
            target_role="synthesizer", target_tokens=64000, actual_tokens=58210,
            layers=[ContextLayer(kind="session", source="cur", tokens=8000)],
            budget_overrun=False, truncation_strategy_applied="smart",
        )
    if at == ActionType.DOCUMENT_LOADED:
        return DocumentLoadedPayload(
            media_type="pdf",
            content_hash="sha:doc", size_bytes=100, title="p.pdf", page_count=4,
            source_uri="file:///tmp/p.pdf",
        )
    if at == ActionType.DOCUMENT_REGION_SELECTED:
        return DocumentRegionSelectedPayload(
            region_id="r-1", page=2, char_start=100, char_end=240,
            bbox=(10.0, 20.0, 200.0, 60.0), text_excerpt="...",
        )
    if at == ActionType.DISTILLATION_REQUESTED:
        return DistillationRequestedPayload(
            region_id="r-1", user_prompt="distill this", target_token_count=400,
        )
    if at == ActionType.DISTILLATION_DELIVERED:
        return DistillationDeliveredPayload(
            request_event_id="evt-parent",
            claims=[
                Claim(
                    claim_id="c-1", text="X correlates with Y",
                    confidence="moderate", attribution_region_ids=["r-1", "r-2"],
                ),
                Claim(
                    claim_id="c-2", text="No directional causation has been shown",
                    confidence="high", attribution_region_ids=["r-3"], node_id="node-42",
                ),
            ],
            rendered_text="X correlates with Y; no causation shown.",
            rendered_text_hash="sha:rt",
            token_count=380,
        )
    if at == ActionType.CLAIM_CHALLENGE_RAISED:
        return ClaimChallengeRaisedPayload(
            challenged_claim_id="c-1",
            claim_text="X causes Y", anchor_region_id="r-1", user_question="really?",
        )
    if at == ActionType.CLAIM_GROUNDING_CHECK_PASSED:
        return ClaimGroundingCheckPassedPayload(
            claim_id="c-1",
            claim_text="X causes Y", located_region_id="r-1", confidence=0.92,
        )
    if at == ActionType.CLAIM_GROUNDING_CHECK_FAILED:
        return ClaimGroundingCheckFailedPayload(
            claim_id="c-1",
            claim_text="X causes Y", reason="absent_from_source",
            searched_regions=["r-1", "r-2"],
        )
    if at == ActionType.NOTE_EMERGED:
        return NoteEmergedPayload(
            note_id="n-1", note_text="X correlates with Y but not proven causal",
            source_event_ids=["e1", "e2"], node_id="node-77",
        )
    if at == ActionType.NOTE_REFINED:
        return NoteRefinedPayload(
            note_id="n-1", previous_text="a", new_text="b",
            refinement_reason="user clarified scope",
        )
    if at == ActionType.NOTE_COMPRESSED_DOC_WRITTEN:
        return NoteCompressedDocWrittenPayload(
            output_path="/tmp/notes/doc-1.md", note_count=12, byte_size=4096,
        )
    if at == ActionType.QUESTION_IDENTIFIED:
        return QuestionIdentifiedPayload(
            question_id="q-1", question_text="is causality directional?",
            anchor_region_id="r-1",
        )
    if at == ActionType.QUESTION_ESCALATED_TO_RESEARCH:
        return QuestionEscalatedToResearchPayload(
            question_id="q-1", child_investigation_id="inv-child-1",
        )
    if at == ActionType.QUESTION_RESOLVED_BY_DOC:
        return QuestionResolvedByDocPayload(
            question_id="q-1", answer_note_id="n-5",
        )
    if at == ActionType.CROSS_DOC_QUESTION_ANSWERED:
        return CrossDocQuestionAnsweredPayload(
            question_id="q-1", question_document_id="doc-A",
            answer_document_id="doc-B", answer_note_id="n-99",
        )
    if at == ActionType.USER_ACCEPT_DISTILLATION:
        return UserAcceptDistillationPayload(distillation_event_id="evt-d")
    if at == ActionType.USER_REJECT_DISTILLATION:
        return UserRejectDistillationPayload(
            distillation_event_id="evt-d", reason="hallucinated a citation",
        )
    if at == ActionType.USER_EDIT_DISTILLATION:
        return UserEditDistillationPayload(
            distillation_event_id="evt-d",
            edited_content="X correlates strongly with Y (no causation).",
            original_content_hash="sha:orig", edited_content_hash="sha:edit",
        )
    if at == ActionType.ARTIFACT_GENERATED:
        return ArtifactGeneratedPayload(
            artifact_id="art-1", artifact_kind="comparison_grid",
            intent="show four candidate framings of the causality question",
            generating_role="note_taker",
            artifact_path="~/.antiek/artifacts/abc123.html",
            content_hash="sha:html", size_bytes=12000,
            source_event_ids=["evt-d-1", "evt-d-2", "evt-d-3", "evt-d-4"],
        )
    if at == ActionType.ARTIFACT_INTERACTED:
        return ArtifactInteractedPayload(
            artifact_id="art-1", interaction_kind="opened",
        )
    raise ValueError(f"no factory registered for {at!r}")


TYPED_ACTION_TYPES_LIST = [
    ActionType.DISPATCH_CALL,
    ActionType.CONTEXT_PACK_ASSEMBLED,
    ActionType.DOCUMENT_LOADED,
    ActionType.DOCUMENT_REGION_SELECTED,
    ActionType.DISTILLATION_REQUESTED,
    ActionType.DISTILLATION_DELIVERED,
    ActionType.CLAIM_CHALLENGE_RAISED,
    ActionType.CLAIM_GROUNDING_CHECK_PASSED,
    ActionType.CLAIM_GROUNDING_CHECK_FAILED,
    ActionType.NOTE_EMERGED,
    ActionType.NOTE_REFINED,
    ActionType.NOTE_COMPRESSED_DOC_WRITTEN,
    ActionType.QUESTION_IDENTIFIED,
    ActionType.QUESTION_ESCALATED_TO_RESEARCH,
    ActionType.QUESTION_RESOLVED_BY_DOC,
    ActionType.CROSS_DOC_QUESTION_ANSWERED,
    ActionType.USER_ACCEPT_DISTILLATION,
    ActionType.USER_REJECT_DISTILLATION,
    ActionType.USER_EDIT_DISTILLATION,
    ActionType.ARTIFACT_GENERATED,
    ActionType.ARTIFACT_INTERACTED,
]


def _build_event(at: ActionType, *, document_id: str | None = None) -> Event:
    payload = _make_payload(at)
    return Event(
        event_id=f"evt-{at.value}",
        investigation_id="inv-1",
        action_type=at,
        payload=payload,
        param_version="0.1.0",
        emitted_at=_now_naive(),
        document_id=document_id,
    )


# ---------------------------------------------------------------------------
# 1. Round-trip every typed variant.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("at", TYPED_ACTION_TYPES_LIST, ids=lambda a: a.value)
def test_payload_roundtrip(at: ActionType):
    # Wrestling variants need a document_id to construct.
    doc = "doc-1" if at.value in WRESTLING_ACTION_TYPES else None
    original = _build_event(at, document_id=doc)
    raw = original.model_dump_json()
    rebuilt = Event.model_validate_json(raw)
    assert type(rebuilt.payload) is type(original.payload), (
        f"variant identity lost across round-trip for {at.value}: "
        f"got {type(rebuilt.payload).__name__}"
    )
    # Top-level action_type must equal payload.action_type after round-trip.
    top = rebuilt.action_type.value if hasattr(rebuilt.action_type, "value") else rebuilt.action_type
    payload_at = rebuilt.payload.action_type
    payload_at = payload_at.value if hasattr(payload_at, "value") else payload_at
    assert top == payload_at == at.value


# ---------------------------------------------------------------------------
# 2. Discriminator rejects a mismatched (envelope action_type, payload) pair.
# ---------------------------------------------------------------------------


def test_discriminator_rejects_mismatched_pair():
    # Envelope claims DOCUMENT_LOADED but payload is a DispatchCallPayload.
    with pytest.raises(ValidationError):
        Event(
            event_id="evt-x",
            investigation_id="inv-1",
            action_type=ActionType.DOCUMENT_LOADED,
            payload=DispatchCallPayload(
                provider="p", model="m", tier="flash", target_role="r",
                input_tokens=1, output_tokens=1, cost_usd=0.0, latency_ms=1,
                prompt_hash="h",
            ),
            param_version="0.1.0",
            emitted_at=_now_naive(),
            document_id="doc-1",
        )


# ---------------------------------------------------------------------------
# 3. Wrestling-loop validator enforces document_id on the envelope.
# ---------------------------------------------------------------------------


WRESTLING_VARIANTS = [a for a in TYPED_ACTION_TYPES_LIST if a.value in WRESTLING_ACTION_TYPES]
NON_WRESTLING_VARIANTS = [a for a in TYPED_ACTION_TYPES_LIST if a.value not in WRESTLING_ACTION_TYPES]


@pytest.mark.parametrize("at", WRESTLING_VARIANTS, ids=lambda a: a.value)
def test_wrestling_requires_document_id(at: ActionType):
    with pytest.raises(ValidationError, match="document_id"):
        _build_event(at, document_id=None)


@pytest.mark.parametrize("at", NON_WRESTLING_VARIANTS, ids=lambda a: a.value)
def test_non_wrestling_does_not_require_document_id(at: ActionType):
    # Should construct without raising — non-wrestling types are document-agnostic.
    e = _build_event(at, document_id=None)
    assert e.document_id is None


def test_cross_doc_question_answered_does_not_require_envelope_document_id():
    # CROSS_DOC_QUESTION_ANSWERED carries BOTH document ids in the payload;
    # the envelope's document_id is intentionally left null.
    e = _build_event(ActionType.CROSS_DOC_QUESTION_ANSWERED, document_id=None)
    assert e.payload.question_document_id == "doc-A"
    assert e.payload.answer_document_id == "doc-B"


# ---------------------------------------------------------------------------
# 4. Timestamp serializes with the legacy 'Z' suffix.
# ---------------------------------------------------------------------------


def test_emitted_at_serializes_with_z_suffix():
    e = _build_event(ActionType.DISPATCH_CALL)
    raw = e.model_dump(mode="json")
    assert raw["emitted_at"].endswith("Z"), raw["emitted_at"]
    assert "+00:00" not in raw["emitted_at"]


def test_emitted_at_serializes_aware_datetime_as_z():
    # tz-aware UTC datetime should also serialize as 'Z'.
    aware = datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)
    payload = _make_payload(ActionType.DISPATCH_CALL)
    e = Event(
        event_id="evt-aware", investigation_id="inv-1",
        action_type=ActionType.DISPATCH_CALL, payload=payload,
        param_version="0.1.0", emitted_at=aware,
    )
    raw = e.model_dump(mode="json")
    assert raw["emitted_at"].endswith("Z")


# ---------------------------------------------------------------------------
# 5. emit_typed end-to-end: write → read → variant identity preserved.
# ---------------------------------------------------------------------------


def test_emit_typed_roundtrip_through_jsonl(tmp_path, monkeypatch):
    events_dir = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))

    emit_typed(
        "rt-1",
        DispatchCallPayload(
            provider="p", model="m", tier="flash", target_role="decomposer",
            input_tokens=10, output_tokens=20, cost_usd=0.01, latency_ms=100,
            prompt_hash="sha",
        ),
    )
    emit_typed(
        "rt-1",
        DocumentLoadedPayload(media_type="pdf", content_hash="sha", size_bytes=10),
        document_id="doc-1",
    )
    rows = trajectory("rt-1")
    assert len(rows) == 2
    # Read-side reconstruction back through Event to confirm variant survives.
    for row in rows:
        rebuilt = Event.model_validate(row)
        if row["action_type"] == "dispatch.call":
            assert isinstance(rebuilt.payload, DispatchCallPayload)
        else:
            assert isinstance(rebuilt.payload, DocumentLoadedPayload)
            assert rebuilt.document_id == "doc-1"


def test_emit_typed_raises_when_wrestling_event_missing_document_id(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "ev"))
    with pytest.raises(ValidationError):
        emit_typed(
            "rt-2",
            DocumentLoadedPayload(content_hash="sha", size_bytes=10),
        )


def test_emit_typed_idempotent_event_id_appends_once(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    payload = DispatchCallPayload(
        provider="p",
        model="m",
        tier="flash",
        target_role="decomposer",
        input_tokens=1,
        output_tokens=1,
        cost_usd=0.0,
        latency_ms=1,
        prompt_hash="sha",
    )
    for _ in range(2):
        assert emit_typed(
            "rt-idempotent",
            payload,
            strict_write=True,
            event_id="evt-deterministic",
            idempotent=True,
        ) == "evt-deterministic"
    assert len(trajectory("rt-idempotent")) == 1


# ---------------------------------------------------------------------------
# 6. Sanity: every wrestling action_type declared in ActionType has both a
# payload factory AND a membership in WRESTLING_ACTION_TYPES. Catches
# additions that forget one of the two sides.
# ---------------------------------------------------------------------------


def test_every_wrestling_action_type_has_a_payload_factory():
    for at in TYPED_ACTION_TYPES_LIST:
        if at.value in WRESTLING_ACTION_TYPES:
            # Factory raises ValueError if no constructor is registered.
            _make_payload(at)


# ---------------------------------------------------------------------------
# 7. Read-through-pass invariants
# ---------------------------------------------------------------------------


def test_distillation_delivered_carries_structured_claims():
    """Layer 1 of architecture_notes §13: a distillation is a list of typed
    Claims plus a rendered text, never an opaque blob."""
    p = _make_payload(ActionType.DISTILLATION_DELIVERED)
    assert isinstance(p.claims, list) and len(p.claims) >= 1
    for c in p.claims:
        assert isinstance(c, Claim)
        assert c.claim_id and c.text
        assert c.confidence in CONFIDENCE_LEVELS
    assert p.rendered_text  # the prose rendering
    assert p.rendered_text_hash  # for integrity / dedup


def test_claim_confidence_levels_match_constants():
    """Claim.confidence must use the same vocabulary as
    ``substrate.constants.CONFIDENCE_LEVELS``. If one drifts from the
    other, downstream backtests stratify against an inconsistent set."""
    # The schema-side Literal accepts the constants-side tuple values.
    for level in CONFIDENCE_LEVELS:
        Claim(claim_id="c", text="t", confidence=level, attribution_region_ids=[])
    # Unknown value rejected.
    with pytest.raises(ValidationError):
        Claim(claim_id="c", text="t", confidence="medium", attribution_region_ids=[])  # type: ignore[arg-type]


def test_document_loaded_media_type_is_required():
    """Read-through fix: no silent 'pdf' default for pasted text events."""
    with pytest.raises(ValidationError):
        DocumentLoadedPayload(content_hash="sha", size_bytes=10)  # type: ignore[call-arg]


def test_claim_references_appear_on_challenge_and_grounding():
    """Read-through fix: challenge / grounding-check events reference a
    structured Claim by id (Optional, for externally-supplied claims)."""
    chal = _make_payload(ActionType.CLAIM_CHALLENGE_RAISED)
    assert chal.challenged_claim_id == "c-1"
    passed = _make_payload(ActionType.CLAIM_GROUNDING_CHECK_PASSED)
    assert passed.claim_id == "c-1"
    failed = _make_payload(ActionType.CLAIM_GROUNDING_CHECK_FAILED)
    assert failed.claim_id == "c-1"


def test_user_edit_distillation_carries_edited_content():
    """Read-through fix: trajectory replay needs the edited text, not just
    a hash."""
    p = _make_payload(ActionType.USER_EDIT_DISTILLATION)
    assert p.edited_content
    assert p.original_content_hash and p.edited_content_hash


def test_artifact_events_do_not_require_document_id():
    """Artifacts can be document-scoped or project-scoped; the envelope's
    document_id is genuinely optional for them (architecture_notes §13.3)."""
    e = _build_event(ActionType.ARTIFACT_GENERATED, document_id=None)
    assert e.document_id is None
    e = _build_event(ActionType.ARTIFACT_INTERACTED, document_id=None)
    assert e.document_id is None


def test_artifact_action_types_are_not_in_wrestling_set():
    """Artifact events must NOT be in WRESTLING_ACTION_TYPES; otherwise
    the project-scoped artifact case breaks (no document_id available)."""
    assert ActionType.ARTIFACT_GENERATED.value not in WRESTLING_ACTION_TYPES
    assert ActionType.ARTIFACT_INTERACTED.value not in WRESTLING_ACTION_TYPES
