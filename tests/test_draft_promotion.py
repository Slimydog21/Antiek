"""Tests for substrate/merge_lifecycle/draft_promotion.py — ask #3d."""

from __future__ import annotations

import pytest

from substrate.merge_lifecycle.draft_promotion import (
    DraftLifecycle,
    DraftPromotionError,
    DraftRef,
    LifecycleEvent,
    OperatorConsent,
    _redact_token,
    create_lifecycle,
    discard,
    mark_for_review,
    promote,
    supersede,
)


def _draft(did="d1", parent="asset-7", h="hash-abc", v=1):
    return DraftRef(draft_id=did, parent_asset_id=parent, content_hash=h, draft_version=v)


def _consent(op="operator-1", token="tok-xyz", at="2026-07-12T20:00:00Z"):
    return OperatorConsent(operator_id=op, consent_token=token, promoted_at=at)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


def test_create_starts_in_draft():
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    assert lc.state == "draft"
    assert lc.is_terminal is False
    assert lc.is_promoted is False
    assert len(lc.history) == 1
    assert lc.history[0].action == "created"


def test_create_rejects_empty_fields():
    with pytest.raises(DraftPromotionError):
        create_lifecycle(DraftRef("", "p", "h"), actor="op", at="t")
    with pytest.raises(DraftPromotionError):
        create_lifecycle(DraftRef("d", "p", "  "), actor="op", at="t")
    with pytest.raises(DraftPromotionError):
        create_lifecycle(_draft(), actor="  ", at="t")


# ---------------------------------------------------------------------------
# mark_for_review
# ---------------------------------------------------------------------------


def test_mark_for_review_from_draft():
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    lc2 = mark_for_review(lc, actor="op", at="t1", reason="checking")
    assert lc2.state == "under_review"
    assert lc.state == "draft"  # original unchanged (immutable)
    assert len(lc2.history) == 2


def test_mark_for_review_rejects_non_draft():
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    lc = mark_for_review(lc, actor="op", at="t1")
    with pytest.raises(DraftPromotionError):
        mark_for_review(lc, actor="op", at="t2")  # already under_review


# ---------------------------------------------------------------------------
# promote — the irreversible terminal
# ---------------------------------------------------------------------------


def test_promote_from_draft():
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    lc = promote(lc, consent=_consent(), content_hash="hash-abc", at="t1")
    assert lc.state == "promoted"
    assert lc.is_promoted is True
    assert lc.is_terminal is True
    assert lc.promoted_by is not None
    assert lc.promoted_by.operator_id == "operator-1"


def test_promote_from_under_review():
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    lc = mark_for_review(lc, actor="op", at="t1")
    lc = promote(lc, consent=_consent(), content_hash="hash-abc", at="t2")
    assert lc.state == "promoted"


def test_promote_rejects_wrong_hash():
    lc = create_lifecycle(_draft(h="hash-abc"), actor="op", at="t0")
    with pytest.raises(DraftPromotionError, match="content_hash mismatch"):
        promote(lc, consent=_consent(), content_hash="DIFFERENT", at="t1")


def test_promote_rejects_missing_consent():
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    with pytest.raises(DraftPromotionError):
        promote(lc, consent=_consent(op="  "), content_hash="hash-abc", at="t1")
    with pytest.raises(DraftPromotionError):
        promote(lc, consent=_consent(token="  "), content_hash="hash-abc", at="t1")


def test_promote_is_terminal_no_further_actions():
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    lc = promote(lc, consent=_consent(), content_hash="hash-abc", at="t1")
    # cannot promote again, discard, mark, or supersede a promoted draft
    with pytest.raises(DraftPromotionError):
        promote(lc, consent=_consent(), content_hash="hash-abc", at="t2")
    with pytest.raises(DraftPromotionError):
        discard(lc, actor="op", at="t2")
    with pytest.raises(DraftPromotionError):
        mark_for_review(lc, actor="op", at="t2")
    with pytest.raises(DraftPromotionError):
        supersede(lc, successor_draft_id="d2", actor="op", at="t2")


# ---------------------------------------------------------------------------
# discard — terminal, parent untouched
# ---------------------------------------------------------------------------


def test_discard_from_draft():
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    lc = discard(lc, actor="op", at="t1", reason="wrong direction")
    assert lc.state == "discarded"
    assert lc.is_terminal is True
    assert lc.is_promoted is False


def test_discard_from_under_review():
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    lc = mark_for_review(lc, actor="op", at="t1")
    lc = discard(lc, actor="op", at="t2")
    assert lc.state == "discarded"


def test_discard_is_terminal():
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    lc = discard(lc, actor="op", at="t1")
    with pytest.raises(DraftPromotionError):
        promote(lc, consent=_consent(), content_hash="hash-abc", at="t2")
    with pytest.raises(DraftPromotionError):
        discard(lc, actor="op", at="t2")


# ---------------------------------------------------------------------------
# supersede — newer draft replaces
# ---------------------------------------------------------------------------


def test_supersede_records_successor():
    lc = create_lifecycle(_draft(did="d1"), actor="op", at="t0")
    lc = supersede(lc, successor_draft_id="d2", actor="op", at="t1", reason="newer draft")
    assert lc.state == "superseded"
    assert lc.superseded_by == "d2"
    assert lc.is_terminal is True


def test_supersede_rejects_empty_successor():
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    with pytest.raises(DraftPromotionError):
        supersede(lc, successor_draft_id="  ", actor="op", at="t1")


def test_supersede_is_terminal():
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    lc = supersede(lc, successor_draft_id="d2", actor="op", at="t1")
    with pytest.raises(DraftPromotionError):
        promote(lc, consent=_consent(), content_hash="hash-abc", at="t2")


# ---------------------------------------------------------------------------
# immutability + append-only history
# ---------------------------------------------------------------------------


def test_transitions_return_new_instance():
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    lc2 = mark_for_review(lc, actor="op", at="t1")
    assert lc is not lc2
    assert lc.state == "draft"
    assert lc2.state == "under_review"


def test_history_is_append_only():
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    lc = mark_for_review(lc, actor="op", at="t1", reason="r1")
    lc = promote(lc, consent=_consent(), content_hash="hash-abc", at="t2", reason="approved")
    actions = [e.action for e in lc.history]
    assert actions == ["created", "marked_for_review", "promoted"]
    # earlier events unchanged
    assert lc.history[0].action == "created"
    assert lc.history[1].reason == "r1"


def test_history_event_carries_actor_and_reason():
    lc = create_lifecycle(_draft(), actor="alice", at="t0")
    lc = discard(lc, actor="bob", at="t1", reason="superseded by better approach")
    last = lc.history[-1]
    assert isinstance(last, LifecycleEvent)
    assert last.actor == "bob"
    assert last.reason == "superseded by better approach"


# ---------------------------------------------------------------------------
# purity + determinism
# ---------------------------------------------------------------------------


def test_lifecycle_is_frozen_value():
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    assert isinstance(lc, DraftLifecycle)
    assert isinstance(lc.history, tuple)


def test_promote_records_token_hash_not_raw_secret_in_audit():
    # Security: the append-only audit log must NEVER store the raw consent token.
    # It stores a hash (proves identity, redactable-safe).
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    lc = promote(lc, consent=_consent(token="secret-tok"), content_hash="hash-abc", at="t1")
    promote_event = [e for e in lc.history if e.action == "promoted"][0]
    assert "secret-tok" not in promote_event.detail  # raw secret never in audit
    assert "token_hash=sha256:" in promote_event.detail  # hash IS recorded
    # the hash is deterministic (same token -> same hash)
    assert _redact_token("secret-tok") in promote_event.detail



def test_promote_promoted_by_carries_no_raw_secret():
    # Security keystone: promoted_by is part of the PERSISTED lifecycle value (the
    # docstring states callers persist the lifecycle between actions). The raw
    # consent token must never survive on it — only the redacted hash, consistent
    # with the history detail. Otherwise a serializer/backup/log dump leaks the
    # credential even though the audit log looks safe.
    lc = create_lifecycle(_draft(), actor="op", at="t0")
    lc = promote(lc, consent=_consent(token="secret-tok"), content_hash="hash-abc", at="t1")
    assert lc.promoted_by is not None
    assert "secret-tok" not in lc.promoted_by.consent_token  # raw secret never persisted
    assert lc.promoted_by.consent_token.startswith("sha256:")  # redacted, like history
    # identity preserved (operator_id is identity, not a secret — stays cleartext)
    assert lc.promoted_by.operator_id == "operator-1"
    # the promoted_by token matches the history hash (one true redaction source)
    promote_event = [e for e in lc.history if e.action == "promoted"][0]
    assert lc.promoted_by.consent_token in promote_event.detail
