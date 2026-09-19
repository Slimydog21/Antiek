from __future__ import annotations

from pathlib import Path

import pytest

from substrate.engagement_spine import (
    HighlightSelection,
    attach_source_references,
    complete_spawn,
    spawn_from_highlight,
)
from substrate.engagement_spine.authority import (
    EngagementAuthority,
    operator_engagement_authority,
)
from substrate.engagement_spine.collective_council import (
    CouncilMemberRequest,
    approve_council_plan,
    create_council_preflight,
    get_council_plan,
)
from substrate.engagement_spine.store import (
    FileEngagementStore,
    InMemoryEngagementStore,
    authorized_store,
)


def _member(store, asset: str = "paper", *, evidence: bool = True):
    spawn = spawn_from_highlight(
        HighlightSelection(
            asset_id=asset,
            selection_text=f"Evidence passage for {asset}",
            region_id=f"region-{asset}",
        ),
        store=store,
    )
    if evidence:
        attach_source_references(spawn.spawn_id, ["arxiv:1706.03762"], store=store)
    complete_spawn(
        spawn.spawn_id,
        store=store,
        output_text=f"Completed evidence analysis for {asset}.",
    )
    return CouncilMemberRequest(
        spawn_id=spawn.spawn_id,
        role=f"critic-{asset}",
        model_id="test/model",
        projected_max_cents=125,
    )


def _preflight(store, members):
    return create_council_preflight(
        store=store,
        collective_id="col-reviewed",
        shared_prompt="Compare the evidence and preserve minority findings.",
        members=members,
        synthesizer_model_id="test/synthesizer",
        synthesizer_projected_max_cents=200,
        approved_ceiling_cents=sum(m.projected_max_cents for m in members) + 200,
    )


def test_preflight_freezes_evidence_and_approval_is_explicit() -> None:
    base = InMemoryEngagementStore()
    store = authorized_store(base, EngagementAuthority("alice"))
    member = _member(store)

    plan = _preflight(store, [member])
    assert plan.state == "preflight"
    assert plan.approval_receipt_id is None
    assert plan.members[0].evidence_sha256
    assert '"output_text":"Completed evidence analysis' in plan.members[0].evidence_json
    assert plan.approved_ceiling_cents == 325

    approved = approve_council_plan(
        plan.plan_id,
        store=store,
        expected_input_sha256=plan.input_sha256,
        approved_ceiling_cents=325,
    )
    assert approved.state == "approved"
    assert approved.approval_receipt_id
    assert approved.input_sha256 == plan.input_sha256


@pytest.mark.parametrize("fault", ["duplicate", "incomplete", "missing_evidence", "over_budget"])
def test_invalid_preflight_writes_no_plan(fault: str) -> None:
    base = InMemoryEngagementStore()
    store = authorized_store(base, EngagementAuthority("alice"))
    first = _member(store, "first", evidence=fault != "missing_evidence")
    members = [first]
    if fault == "duplicate":
        members.append(first)
    elif fault == "incomplete":
        spawn = spawn_from_highlight(
            HighlightSelection(asset_id="pending", selection_text="pending"),
            store=store,
        )
        members = [
            CouncilMemberRequest(spawn.spawn_id, "pending", "test/model", 10)
        ]
    before = set(base._docs)
    kwargs = {
        "store": store,
        "collective_id": "col-invalid",
        "shared_prompt": "Analyze this evidence.",
        "members": members,
        "synthesizer_model_id": "test/synth",
        "synthesizer_projected_max_cents": 50,
        "approved_ceiling_cents": sum(m.projected_max_cents for m in members) + 50,
    }
    if fault == "over_budget":
        kwargs["approved_ceiling_cents"] -= 1
    with pytest.raises((ValueError, KeyError)):
        create_council_preflight(**kwargs)
    assert set(base._docs) == before


def test_foreign_member_is_absent_and_owner_ids_do_not_collide() -> None:
    base = InMemoryEngagementStore()
    alice = authorized_store(base, EngagementAuthority("alice"))
    bob = authorized_store(base, EngagementAuthority("bob"))
    alice_member = _member(alice)
    alice_plan = _preflight(alice, [alice_member])

    with pytest.raises(KeyError, match="council member not found"):
        _preflight(bob, [alice_member])
    bob_member = _member(bob)
    bob_plan = _preflight(bob, [bob_member])
    assert alice_plan.plan_id != bob_plan.plan_id
    assert bob.get_document(alice_plan.plan_id) is None


def test_tampered_plan_cannot_be_approved() -> None:
    base = InMemoryEngagementStore()
    store = authorized_store(base, EngagementAuthority("alice"))
    plan = _preflight(store, [_member(store)])
    stored = next(row for row in base._docs.values() if row.get("kind") == "council_plan")
    stored["shared_prompt"] = "tampered"
    with pytest.raises(ValueError, match="integrity"):
        approve_council_plan(
            plan.plan_id,
            store=store,
            expected_input_sha256=plan.input_sha256,
            approved_ceiling_cents=plan.approved_ceiling_cents,
        )


def test_file_store_restart_preserves_approved_plan(tmp_path: Path) -> None:
    authority = EngagementAuthority("alice")
    store = authorized_store(FileEngagementStore(tmp_path), authority)
    plan = _preflight(store, [_member(store)])
    approve_council_plan(
        plan.plan_id,
        store=store,
        expected_input_sha256=plan.input_sha256,
        approved_ceiling_cents=plan.approved_ceiling_cents,
    )
    reopened = authorized_store(FileEngagementStore(tmp_path), authority)
    assert get_council_plan(plan.plan_id, store=reopened).state == "approved"


def test_unauthenticated_local_store_cannot_create_live_council() -> None:
    store = authorized_store(InMemoryEngagementStore(), operator_engagement_authority())
    with pytest.raises(PermissionError, match="unauthenticated local"):
        _preflight(store, [])
