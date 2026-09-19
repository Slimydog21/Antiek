from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from substrate.dispatch.research_quote import build_research_route_manifest
from substrate.dispatch.router import DispatchConfig, TierConfig, TierPricing
from substrate.event_log import (
    IdempotencyConflict,
    ResearchBudgetExceeded,
    ResearchBudgetLedgerInvalid,
    accept_research_delegation_authorized,
    append_event_once_authorized,
    mark_research_delegation_issued_authorized,
    prepare_typed_event,
    release_research_delegation_authorized,
    research_delegation_snapshot_authorized,
    reserve_research_delegation_authorized,
    settle_research_delegation_authorized,
    trajectory_authorized_append_order,
)
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas import (
    InvestigationFailedPayload,
    InvestigationStartRequestedPayload,
    ResearchDelegationAcceptedPayload,
    ResearchDelegationIssuedPayload,
    ResearchDelegationReleasedPayload,
    ResearchDelegationReservedPayload,
    ResearchDelegationSettledPayload,
    ResearchQuotedRoute,
)


def _pricing() -> TierPricing:
    return TierPricing(
        input_per_mtok=1.0,
        output_per_mtok=2.0,
        cached_input_per_mtok=0.1,
        currency="USD",
        billing_unit="per_million_tokens",
        source_url="https://provider.example/pricing",
        verified_at="2026-01-01T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
    )


def _manifest():
    route = TierConfig("pro", "provider", "model", 100, 0.2, 1000, _pricing())
    return build_research_route_manifest(
        DispatchConfig(role_tiers={"decomposer": "pro"}, tiers={"pro": route})
    )


def _root(tmp_path: Path, *, account: str = "alice", chase_ceiling: float = 2.0):
    authority = InvestigationAuthority(account, "inv-root", tmp_path)
    initialize_composite_stream(authority)
    manifest = _manifest()
    start = prepare_typed_event(
        authority.investigation_id,
        InvestigationStartRequestedPayload(
            question="Root question",
            chase_mode="depth",
            chase_value=3,
            chase_budget_usd=chase_ceiling,
            approved_run_ceiling_usd=1.0,
            research_quote_id="a" * 64,
            research_quote_payload_sha256="b" * 64,
            research_route_manifest_fingerprint=manifest.fingerprint,
            research_quote_expires_at_ms=4_102_444_800_000,
            research_route_manifest=tuple(
                ResearchQuotedRoute(**row.__dict__) for row in manifest.routes
            ),
        ),
        event_id="evt-root-start",
    )
    append_event_once_authorized(authority, start)
    return authority, start, manifest


def _reservation(*, amount: float = 1.5, suffix: str = "1"):
    operation = suffix * 64
    return ResearchDelegationReservedPayload(
        delegation_id=("d" if suffix == "1" else "e") * 64,
        operation_sha256=operation,
        root_investigation_id="inv-root",
        root_quote_id="a" * 64,
        parent_investigation_id="inv-root",
        parent_quote_id="a" * 64,
        child_investigation_id=f"inv-child-{suffix}",
        generation=1,
        delegated_ceiling_usd=amount,
        route_manifest_fingerprint=_manifest().fingerprint,
    )


def _event_sha256(event) -> str:
    encoded = json.dumps(
        event.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _issue_accept(tmp_path: Path, root: InvestigationAuthority, reservation_event, held):
    issued, _ = mark_research_delegation_issued_authorized(
        root,
        ResearchDelegationIssuedPayload(
            delegation_id=held.delegation_id,
            reservation_event_id=reservation_event.event_id,
            quote_id="c" * 64,
            quote_payload_sha256="f" * 64,
            quote_expires_at_ms=4_102_444_800_000,
        ),
    )
    child = InvestigationAuthority("alice", held.child_investigation_id, tmp_path)
    initialize_composite_stream(child)
    manifest = _manifest()
    child_start = prepare_typed_event(
        child.investigation_id,
        InvestigationStartRequestedPayload(
            question="Child question",
            parent_investigation_id="inv-root",
            spawn_context="Child question",
            chase_mode="depth",
            chase_value=3,
            chase_budget_usd=2.0,
            approved_run_ceiling_usd=held.delegated_ceiling_usd,
            research_quote_id="c" * 64,
            research_quote_payload_sha256="f" * 64,
            research_route_manifest_fingerprint=manifest.fingerprint,
            research_quote_expires_at_ms=4_102_444_800_000,
            research_route_manifest=tuple(
                ResearchQuotedRoute(**row.__dict__) for row in manifest.routes
            ),
            research_delegated_from_quote_id="a" * 64,
            research_delegation_id=held.delegation_id,
            research_root_investigation_id="inv-root",
            research_root_quote_id="a" * 64,
            research_delegation_generation=1,
        ),
        event_id="evt-child-start",
    )
    append_event_once_authorized(child, child_start)
    accepted, _ = accept_research_delegation_authorized(
        root,
        ResearchDelegationAcceptedPayload(
            delegation_id=held.delegation_id,
            reservation_event_id=reservation_event.event_id,
            issued_event_id=issued.event_id,
            child_investigation_id=child.investigation_id,
            child_start_event_id=child_start.event_id,
            child_start_sha256=_event_sha256(child_start),
        ),
        child_authority=child,
        child_start_event=child_start,
    )
    return child, child_start, issued, accepted


def test_reserve_issue_accept_settle_replays_and_returns_unused_capacity(tmp_path):
    root, _, _ = _root(tmp_path)
    held = _reservation()
    reservation, snapshot = reserve_research_delegation_authorized(root, held)
    replay, replay_snapshot = reserve_research_delegation_authorized(root, held)
    assert replay.event_id == reservation.event_id
    assert replay_snapshot == snapshot
    assert float(snapshot.outstanding_usd) == 1.5

    child, _, issued, accepted = _issue_accept(tmp_path, root, reservation, held)
    assert issued.parent_event_id == reservation.event_id
    assert accepted.parent_event_id == issued.event_id
    terminal = prepare_typed_event(
        child.investigation_id,
        InvestigationFailedPayload(phase=1, reason="done"),
        event_id="evt-child-terminal",
    )
    append_event_once_authorized(child, terminal)
    settled, final = settle_research_delegation_authorized(
        root,
        ResearchDelegationSettledPayload(
            delegation_id=held.delegation_id,
            reservation_event_id=reservation.event_id,
            accepted_event_id=accepted.event_id,
            child_terminal_event_id=terminal.event_id,
            actual_cost_usd=0.0,
        ),
        child_authority=child,
        child_terminal_event=terminal,
    )
    replay_settle, replay_final = settle_research_delegation_authorized(
        root,
        ResearchDelegationSettledPayload(
            delegation_id=held.delegation_id,
            reservation_event_id=reservation.event_id,
            accepted_event_id=accepted.event_id,
            child_terminal_event_id=terminal.event_id,
            actual_cost_usd=0.0,
        ),
        child_authority=child,
        child_terminal_event=terminal,
    )
    assert replay_settle.event_id == settled.event_id
    assert replay_final == final
    assert float(final.delegated_spend_usd) == 0.0
    assert float(final.outstanding_usd) == 0.0
    assert float(final.remaining_usd) == 2.0


def test_release_is_only_legal_before_issue(tmp_path):
    root, _, _ = _root(tmp_path)
    held = _reservation()
    reservation, _ = reserve_research_delegation_authorized(root, held)
    _, released = release_research_delegation_authorized(
        root,
        ResearchDelegationReleasedPayload(
            delegation_id=held.delegation_id,
            reservation_event_id=reservation.event_id,
            reason="quote_not_issued",
        ),
    )
    assert float(released.remaining_usd) == 2.0

    second = held.model_copy(
        update={"delegation_id": "e" * 64, "operation_sha256": "2" * 64}
    )
    second_event, _ = reserve_research_delegation_authorized(root, second)
    mark_research_delegation_issued_authorized(
        root,
        ResearchDelegationIssuedPayload(
            delegation_id=second.delegation_id,
            reservation_event_id=second_event.event_id,
            quote_id="c" * 64,
            quote_payload_sha256="f" * 64,
            quote_expires_at_ms=4_102_444_800_000,
        ),
    )
    with pytest.raises(ResearchBudgetLedgerInvalid, match="cannot be released"):
        release_research_delegation_authorized(
            root,
            ResearchDelegationReleasedPayload(
                delegation_id=second.delegation_id,
                reservation_event_id=second_event.event_id,
                reason="quote_not_issued",
            ),
        )


def test_concurrent_distinct_reservations_conserve_root_ceiling(tmp_path):
    root, _, _ = _root(tmp_path, chase_ceiling=1.0)
    requests = [_reservation(amount=0.75, suffix="1"), _reservation(amount=0.75, suffix="2")]

    def reserve(payload):
        return reserve_research_delegation_authorized(root, payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(reserve, payload) for payload in requests]
    outcomes = []
    for future in futures:
        try:
            outcomes.append(future.result())
        except ResearchBudgetExceeded:
            outcomes.append("denied")
    assert sum(outcome == "denied" for outcome in outcomes) == 1
    snapshot = research_delegation_snapshot_authorized(root)
    assert float(snapshot.outstanding_usd) == 0.75
    assert float(snapshot.remaining_usd) == 0.25


def test_cross_process_reservations_share_the_root_fcntl_boundary(tmp_path):
    root, _, _ = _root(tmp_path, chase_ceiling=1.0)
    requests = [_reservation(amount=0.75, suffix="1"), _reservation(amount=0.75, suffix="2")]
    script = """
import json, pathlib, sys, time
from substrate.event_log import ResearchBudgetExceeded, reserve_research_delegation_authorized
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas import ResearchDelegationReservedPayload
root, marker, peer, raw = sys.argv[1:]
pathlib.Path(marker).touch()
deadline = time.monotonic() + 10
while not pathlib.Path(peer).exists():
    if time.monotonic() > deadline: raise RuntimeError('process barrier timeout')
    time.sleep(0.01)
authority = InvestigationAuthority('alice', 'inv-root', pathlib.Path(root))
try:
    event, _ = reserve_research_delegation_authorized(
        authority, ResearchDelegationReservedPayload.model_validate(json.loads(raw))
    )
    print(event.event_id)
except ResearchBudgetExceeded:
    print('denied')
"""
    markers = [tmp_path / "ready-1", tmp_path / "ready-2"]
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(tmp_path),
                str(markers[index]),
                str(markers[1 - index]),
                json.dumps(payload.model_dump(mode="json")),
            ],
            cwd=Path(__file__).parents[1],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for index, payload in enumerate(requests)
    ]
    outcomes = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        outcomes.append(stdout.strip())
    assert outcomes.count("denied") == 1
    snapshot = research_delegation_snapshot_authorized(root)
    assert float(snapshot.outstanding_usd) == 0.75


def test_changed_replay_cross_account_and_forged_child_receipts_fail(tmp_path):
    root, _, _ = _root(tmp_path)
    held = _reservation()
    reservation, _ = reserve_research_delegation_authorized(root, held)
    with pytest.raises(IdempotencyConflict):
        reserve_research_delegation_authorized(
            root, held.model_copy(update={"delegated_ceiling_usd": 1.4})
        )
    foreign = InvestigationAuthority("bob", "inv-root", tmp_path)
    with pytest.raises(Exception):
        research_delegation_snapshot_authorized(foreign)

    child, child_start, issued, _ = _issue_accept(tmp_path, root, reservation, held)
    forged = child_start.model_copy(update={"event_id": "evt-forged"})
    with pytest.raises(ResearchBudgetLedgerInvalid, match="immutable child start"):
        accept_research_delegation_authorized(
            root,
            ResearchDelegationAcceptedPayload(
                delegation_id=held.delegation_id,
                reservation_event_id=reservation.event_id,
                issued_event_id=issued.event_id,
                child_investigation_id=child.investigation_id,
                child_start_event_id=forged.event_id,
                child_start_sha256=_event_sha256(forged),
            ),
            child_authority=child,
            child_start_event=forged,
        )
    bob_child = InvestigationAuthority("bob", child.investigation_id, tmp_path)
    initialize_composite_stream(bob_child)
    bob_start = child_start.model_copy(
        update={"event_id": "evt-bob-child-start"}
    )
    append_event_once_authorized(bob_child, bob_start)
    with pytest.raises(ResearchBudgetLedgerInvalid, match="immutable child start"):
        accept_research_delegation_authorized(
            root,
            ResearchDelegationAcceptedPayload(
                delegation_id=held.delegation_id,
                reservation_event_id=reservation.event_id,
                issued_event_id=issued.event_id,
                child_investigation_id=bob_child.investigation_id,
                child_start_event_id=bob_start.event_id,
                child_start_sha256=_event_sha256(bob_start),
            ),
            child_authority=bob_child,
            child_start_event=bob_start,
        )
    rows = trajectory_authorized_append_order(root)
    assert [row["action_type"] for row in rows].count("research.delegation_accepted") == 1
