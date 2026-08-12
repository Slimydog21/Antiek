from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from interfaces.research.api import research_owner_dispatch as subject
from interfaces.research.api.owner_byot_dispatch import OwnerByotOutcomeUnknown
from interfaces.research.api.settings_models_admin import UserModelChoice
from substrate.dispatch.base import NormalizedUsage
from substrate.dispatch.router import DispatchResult


@pytest.mark.parametrize("role", subject.PAID_LOOP_ONE_ROLES)
def test_every_paid_role_uses_deterministic_owner_child_operation(monkeypatch, role):
    calls: list[dict[str, object]] = []
    result = DispatchResult(
        text="ok", usage=NormalizedUsage(1, 1), cost_usd=0.0, latency_ms=1,
        provider="owner-provider", model="owner-model", tier="exact",
        finish_reason="stop", fallback_chain_index=0, event_id="evt-1",
    )

    def fake(**kwargs):
        calls.append(kwargs)
        return result, Mock()

    monkeypatch.setattr(subject, "dispatch_talk_to_book_byot", fake)
    choice = UserModelChoice(authority="user_model", provider_id="owner-provider", model_id="owner-model")
    manifest = subject.ResearchOwnerManifest(
        Mock(), "owner-1", "inv-1", "launch-1",
        {paid: choice for paid in subject.PAID_LOOP_ONE_ROLES},
    )
    token = subject.install_manifest(manifest)
    try:
        first = subject.dispatch_loop_one("same prompt", role, investigation_id="inv-1")
        second = subject.dispatch_loop_one("same prompt", role, investigation_id="inv-1")
    finally:
        subject.reset_manifest(token)

    assert first is result and second is result
    assert calls[0]["logical_operation_id"] == calls[1]["logical_operation_id"]
    assert str(calls[0]["logical_operation_id"]).startswith(f"launch-1:{role}:")
    assert calls[0]["role"] == role
    assert calls[0]["action"] == f"research.loop_one.{role}"


def test_no_manifest_preserves_legacy_dispatch_seam():
    assert subject.dispatch_loop_one("prompt", "decomposer", investigation_id="legacy") is None


def test_semantic_identity_distinguishes_duplicate_question_ordinals(monkeypatch):
    ids: list[str] = []
    result = DispatchResult(
        text="ok", usage=NormalizedUsage(0, 0), cost_usd=0, latency_ms=0,
        provider="p", model="m", tier="owner", finish_reason="stop",
        fallback_chain_index=0, event_id="e",
    )
    monkeypatch.setattr(subject, "dispatch_talk_to_book_byot", lambda **kw: (ids.append(kw["logical_operation_id"]) or result, Mock()))
    choice = UserModelChoice(authority="user_model", provider_id="p", model_id="m")
    token = subject.install_manifest(subject.ResearchOwnerManifest(
        Mock(), "owner", "inv", "op", {r: choice for r in subject.PAID_LOOP_ONE_ROLES},
    ))
    try:
        subject.dispatch_loop_one("same", "evidence_retriever", investigation_id="inv", semantic_call_id="phase2:0:abc")
        subject.dispatch_loop_one("same", "evidence_retriever", investigation_id="inv", semantic_call_id="phase2:1:abc")
    finally:
        subject.reset_manifest(token)
    assert ids[0] != ids[1]


def test_claim_is_concurrent_and_state_progress_is_cas(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTIEK_OWNER_LAUNCH_DB", str(tmp_path / "claims.sqlite3"))
    args = dict(operation_id="op", owner_user_id="owner", launch_digest="digest", investigation_id="inv")
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(lambda _: subject.claim_owner_launch(**args), range(8)))
    assert {row[0] for row in rows} == {"inv"}
    assert sum(not row[1] for row in rows) == 1
    assert subject.owner_launch_state("op") == "claimed"
    subject.advance_owner_launch("op", "claimed", "appended")
    subject.advance_owner_launch("op", "appended", "broadcast")
    assert subject.owner_launch_state("op") == "broadcast"


def test_unknown_owner_outcome_crosses_role_boundary_without_ambient_fallback(monkeypatch):
    def unknown(**kwargs):
        raise OwnerByotOutcomeUnknown("owner_byot_outcome_unknown")

    monkeypatch.setattr(subject, "dispatch_talk_to_book_byot", unknown)
    choice = UserModelChoice(authority="user_model", provider_id="p", model_id="m")
    token = subject.install_manifest(subject.ResearchOwnerManifest(
        Mock(), "owner", "inv", "op", {r: choice for r in subject.PAID_LOOP_ONE_ROLES},
    ))
    try:
        with pytest.raises(OwnerByotOutcomeUnknown, match="owner_byot_outcome_unknown"):
            subject.dispatch_loop_one(
                "prompt", "decomposer", investigation_id="inv", semantic_call_id="phase1",
            )
    finally:
        subject.reset_manifest(token)
