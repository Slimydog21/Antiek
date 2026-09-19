from __future__ import annotations

import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import pytest

from substrate.dispatch.research_quote import build_research_route_manifest
from substrate.dispatch.router import DispatchConfig
from substrate.event_log import (
    IdempotencyConflict,
    ResearchBudgetExceeded,
    ResearchBudgetLedgerInvalid,
    append_event_once_authorized,
    prepare_typed_event,
    release_research_call_authorized,
    research_call_dispatch_event_id,
    reserve_research_call_authorized,
    seal_investigation_authorized,
    settle_research_call_authorized,
    trajectory_authorized,
)
from substrate.investigation_streams import resolve_investigation_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas import (
    DispatchCallPayload,
    InvestigationStartRequestedPayload,
    ResearchCallReleasedPayload,
    ResearchCallReservedPayload,
    ResearchCallSettledPayload,
    ResearchQuotedRoute,
)


def _accepted_manifest():
    config = DispatchConfig._from_dict(
        {
            "role_tiers": {"decomposer": "flash"},
            "tier_defaults": {"flash": {"max_tokens": 100}},
            "tiers": {
                "flash": {
                    "provider": "provider",
                    "model": "model",
                    "pricing": {
                        "input_per_mtok": 1.0,
                        "output_per_mtok": 2.0,
                        "cached_input_per_mtok": 0.1,
                        "currency": "USD",
                        "billing_unit": "per_million_tokens",
                        "source_url": "https://provider.example/pricing",
                        "verified_at": "2026-01-01T00:00:00Z",
                        "expires_at": "2099-01-01T00:00:00Z",
                    },
                }
            },
        }
    )
    return build_research_route_manifest(config)


def _start(authority: InvestigationAuthority, ceiling: float | None = 1.0) -> str:
    manifest = _accepted_manifest()
    event = prepare_typed_event(
        authority.investigation_id,
        InvestigationStartRequestedPayload(
            question="What is true?",
            approved_run_ceiling_usd=ceiling,
            research_quote_id="a" * 64,
            research_quote_payload_sha256="b" * 64,
            research_route_manifest_fingerprint=manifest.fingerprint,
            research_quote_expires_at_ms=4_102_444_800_000,
            research_route_manifest=tuple(
                ResearchQuotedRoute(**row.__dict__) for row in manifest.routes
            ),
        ),
        event_id=f"evt-start-{authority.account_digest[:12]}",
    )
    return append_event_once_authorized(authority, event)


def _reservation(
    suffix: str,
    *,
    projected: float,
    parent_event_id: str,
) -> ResearchCallReservedPayload:
    digit = "1" if suffix == "one" else "2"
    manifest = _accepted_manifest()
    return ResearchCallReservedPayload(
        reservation_id=f"res-{suffix}",
        request_sha256=digit * 64,
        target_role="decomposer",
        tier="flash",
        provider="provider",
        model="model",
        route_tier_name="flash",
        fallback_chain_index=0,
        prompt_hash=f"sha256:{digit * 12}",
        max_tokens=100,
        temperature=0.2,
        context_budget_tokens=32000,
        projected_max_cost_usd=projected,
        provider_idempotency_key_sha256=("a" if suffix == "one" else "b") * 64,
        parent_request_event_id=parent_event_id,
        research_quote_id="a" * 64,
        research_route_manifest_fingerprint=manifest.fingerprint,
        pricing_fingerprint=manifest.routes[0].pricing_fingerprint,
    )


def _reserve(
    authority: InvestigationAuthority, payload: ResearchCallReservedPayload
):
    return reserve_research_call_authorized(
        authority, payload, role="decomposer", policy_id="provider/model"
    )


def _process_reserve(root: str, payload_row: dict[str, object]) -> str:
    authority = InvestigationAuthority("alice", "inv-process", Path(root))
    payload = ResearchCallReservedPayload.model_validate(payload_row)
    try:
        return _reserve(authority, payload)[0].event_id
    except ResearchBudgetExceeded:
        return "denied"


def test_reservation_exact_replay_and_changed_command_conflict(tmp_path):
    authority = InvestigationAuthority("alice", "inv-budget", tmp_path)
    start_id = _start(authority)
    payload = _reservation("one", projected=0.4, parent_event_id=start_id)

    first, first_balance = _reserve(authority, payload)
    replay, replay_balance = _reserve(authority, payload)

    assert replay.event_id == first.event_id
    assert replay_balance == first_balance
    assert first_balance.outstanding_usd == first_balance.ceiling_usd * 2 / 5
    assert [
        row["action_type"]
        for row in trajectory_authorized(authority)
    ].count("research.call_reserved") == 1

    changed = payload.model_copy(update={"max_tokens": 101})
    with pytest.raises(ResearchBudgetLedgerInvalid, match="accepted research quote"):
        _reserve(authority, changed)


@pytest.mark.parametrize(
    ("update", "role", "policy_id"),
    [
        ({"research_quote_id": "c" * 64}, "decomposer", "provider/model"),
        (
            {"research_route_manifest_fingerprint": "c" * 64},
            "decomposer",
            "provider/model",
        ),
        ({"pricing_fingerprint": "c" * 64}, "decomposer", "provider/model"),
        ({"fallback_chain_index": 1}, "decomposer", "provider/model"),
        ({"max_tokens": 101}, "decomposer", "provider/model"),
        ({"provider": "substitute"}, "decomposer", "substitute/model"),
        ({"model": "substitute"}, "decomposer", "provider/substitute"),
    ],
)
def test_reservation_must_match_every_accepted_quote_dimension(
    tmp_path, update, role, policy_id
):
    authority = InvestigationAuthority("alice", "inv-quote-route", tmp_path)
    start_id = _start(authority)
    payload = _reservation("one", projected=0.1, parent_event_id=start_id)
    with pytest.raises(ResearchBudgetLedgerInvalid, match="accepted research quote"):
        reserve_research_call_authorized(
            authority,
            payload.model_copy(update=update),
            role=role,
            policy_id=policy_id,
        )


def test_concurrent_holds_cannot_overspend_one_ceiling(tmp_path):
    authority = InvestigationAuthority("alice", "inv-concurrent", tmp_path)
    start_id = _start(authority, 1.0)
    payloads = [
        _reservation("one", projected=0.6, parent_event_id=start_id),
        _reservation("two", projected=0.6, parent_event_id=start_id),
    ]

    def attempt(payload: ResearchCallReservedPayload) -> str:
        try:
            return _reserve(authority, payload)[0].event_id
        except ResearchBudgetExceeded:
            return "denied"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, payloads))

    assert outcomes.count("denied") == 1
    rows = trajectory_authorized(authority)
    assert sum(row["action_type"] == "research.call_reserved" for row in rows) == 1


def test_cross_process_holds_use_the_same_fcntl_ceiling_boundary(tmp_path):
    authority = InvestigationAuthority("alice", "inv-process", tmp_path)
    start_id = _start(authority, 1.0)
    payloads = [
        _reservation("one", projected=0.6, parent_event_id=start_id),
        _reservation("two", projected=0.6, parent_event_id=start_id),
    ]
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=2, mp_context=context) as executor:
        outcomes = list(
            executor.map(
                _process_reserve,
                [str(tmp_path), str(tmp_path)],
                [payload.model_dump(mode="json") for payload in payloads],
            )
        )
    assert outcomes.count("denied") == 1
    assert sum(
        row["action_type"] == "research.call_reserved"
        for row in trajectory_authorized(authority)
    ) == 1


@pytest.mark.parametrize("ceiling", [None])
def test_reservation_fails_closed_without_explicit_launch_ceiling(tmp_path, ceiling):
    authority = InvestigationAuthority("alice", "inv-no-consent", tmp_path)
    start_id = _start(authority, ceiling)
    with pytest.raises(ResearchBudgetLedgerInvalid, match="no explicit"):
        _reserve(
            authority,
            _reservation("one", projected=0.1, parent_event_id=start_id),
        )


def test_release_restores_hold_and_settlement_uses_actual_dispatch_cost(tmp_path):
    authority = InvestigationAuthority("alice", "inv-terminal", tmp_path)
    start_id = _start(authority, 1.0)
    first_payload = _reservation("one", projected=0.6, parent_event_id=start_id)
    first_event, _ = _reserve(authority, first_payload)
    released, release_balance = release_research_call_authorized(
        authority,
        ResearchCallReleasedPayload(
            reservation_id=first_payload.reservation_id,
            reservation_event_id=first_event.event_id,
            request_sha256=first_payload.request_sha256,
            reason="provider_call_not_attempted",
            error_sha256="e" * 64,
        ),
        role="decomposer",
        policy_id="provider/model",
    )
    replay, replay_balance = release_research_call_authorized(
        authority,
        released.payload,
        role="decomposer",
        policy_id="provider/model",
    )
    assert replay.event_id == released.event_id
    assert replay_balance == release_balance
    assert release_balance.outstanding_usd == 0

    second_payload = _reservation("two", projected=0.8, parent_event_id=start_id)
    second_event, _ = _reserve(authority, second_payload)
    dispatch = prepare_typed_event(
        authority.investigation_id,
        DispatchCallPayload(
            provider="provider",
            model="model",
            tier="flash",
            target_role="decomposer",
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.25,
            latency_ms=1,
            fallback_chain_index=0,
            prompt_hash=second_payload.prompt_hash,
        ),
        event_id=research_call_dispatch_event_id(second_event.event_id),
        parent_event_id=start_id,
    )
    append_event_once_authorized(authority, dispatch)
    settlement = ResearchCallSettledPayload(
        reservation_id=second_payload.reservation_id,
        reservation_event_id=second_event.event_id,
        request_sha256=second_payload.request_sha256,
        dispatch_call_event_id=dispatch.event_id,
        actual_cost_usd=0.25,
        exceeded_reservation=False,
    )
    settled, settled_balance = settle_research_call_authorized(
        authority,
        settlement,
        role="decomposer",
        policy_id="provider/model",
    )
    settled_replay, replayed_balance = settle_research_call_authorized(
        authority,
        settlement,
        role="decomposer",
        policy_id="provider/model",
    )
    assert settled_replay.event_id == settled.event_id
    assert replayed_balance == settled_balance
    assert str(settled_balance.settled_usd) == "0.25"
    assert settled_balance.outstanding_usd == 0
    assert str(settled_balance.remaining_usd) == "0.75"


def test_settlement_rejects_dispatch_substitution_and_terminal_conflict(tmp_path):
    authority = InvestigationAuthority("alice", "inv-substitution", tmp_path)
    start_id = _start(authority)
    reservation = _reservation("one", projected=0.5, parent_event_id=start_id)
    reservation_event, _ = _reserve(authority, reservation)
    wrong_dispatch = prepare_typed_event(
        authority.investigation_id,
        DispatchCallPayload(
            provider="other-provider",
            model="model",
            tier="flash",
            target_role="decomposer",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.1,
            latency_ms=1,
            prompt_hash=reservation.prompt_hash,
        ),
        event_id=research_call_dispatch_event_id(reservation_event.event_id),
        parent_event_id=start_id,
    )
    append_event_once_authorized(authority, wrong_dispatch)
    with pytest.raises(ResearchBudgetLedgerInvalid, match="bindings conflict"):
        settle_research_call_authorized(
            authority,
            ResearchCallSettledPayload(
                reservation_id=reservation.reservation_id,
                reservation_event_id=reservation_event.event_id,
                request_sha256=reservation.request_sha256,
                dispatch_call_event_id=wrong_dispatch.event_id,
                actual_cost_usd=0.1,
            ),
            role="decomposer",
            policy_id="provider/model",
        )

    release_research_call_authorized(
        authority,
        ResearchCallReleasedPayload(
            reservation_id=reservation.reservation_id,
            reservation_event_id=reservation_event.event_id,
            request_sha256=reservation.request_sha256,
            reason="provider_unregistered",
        ),
        role="decomposer",
        policy_id="provider/model",
    )
    with pytest.raises(IdempotencyConflict, match="another terminal"):
        release_research_call_authorized(
            authority,
            ResearchCallReleasedPayload(
                reservation_id=reservation.reservation_id,
                reservation_event_id=reservation_event.event_id,
                request_sha256=reservation.request_sha256,
                reason="circuit_open",
            ),
            role="decomposer",
            policy_id="provider/model",
        )


def test_malformed_duplicate_reservation_fails_closed(tmp_path):
    authority = InvestigationAuthority("alice", "inv-malformed", tmp_path)
    start_id = _start(authority)
    payload = _reservation("one", projected=0.2, parent_event_id=start_id)
    event, _ = _reserve(authority, payload)
    duplicate = event.model_copy(update={"event_id": "evt-hostile-duplicate"})
    path = resolve_investigation_stream(authority).jsonl_path
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(duplicate.model_dump(mode="json")) + "\n")

    with pytest.raises(ResearchBudgetLedgerInvalid, match="duplicate"):
        _reserve(
            authority,
            _reservation("two", projected=0.2, parent_event_id=start_id),
        )


def test_same_display_investigation_budget_is_account_isolated(tmp_path):
    alice = InvestigationAuthority("alice", "shared", tmp_path)
    bob = InvestigationAuthority("bob", "shared", tmp_path)
    alice_start = _start(alice, 0.3)
    bob_start = _start(bob, 1.0)
    _reserve(alice, _reservation("one", projected=0.3, parent_event_id=alice_start))

    with pytest.raises(ResearchBudgetExceeded):
        _reserve(
            alice,
            _reservation("two", projected=0.1, parent_event_id=alice_start),
        )
    _, bob_balance = _reserve(
        bob, _reservation("one", projected=0.8, parent_event_id=bob_start)
    )
    assert str(bob_balance.remaining_usd) == "0.2"
    assert resolve_investigation_stream(alice).jsonl_path != resolve_investigation_stream(
        bob
    ).jsonl_path


def test_provider_overrun_is_recorded_and_exhausts_future_capacity(tmp_path):
    authority = InvestigationAuthority("alice", "inv-overrun", tmp_path)
    start_id = _start(authority, 0.7)
    reservation = _reservation("one", projected=0.5, parent_event_id=start_id)
    reservation_event, _ = _reserve(authority, reservation)
    dispatch = prepare_typed_event(
        authority.investigation_id,
        DispatchCallPayload(
            provider="provider",
            model="model",
            tier="flash",
            target_role="decomposer",
            input_tokens=100,
            output_tokens=100,
            cost_usd=0.6,
            latency_ms=1,
            prompt_hash=reservation.prompt_hash,
        ),
        event_id=research_call_dispatch_event_id(reservation_event.event_id),
        parent_event_id=start_id,
    )
    append_event_once_authorized(authority, dispatch)
    receipt, balance = settle_research_call_authorized(
        authority,
        ResearchCallSettledPayload(
            reservation_id=reservation.reservation_id,
            reservation_event_id=reservation_event.event_id,
            request_sha256=reservation.request_sha256,
            dispatch_call_event_id=dispatch.event_id,
            actual_cost_usd=0.6,
            exceeded_reservation=True,
        ),
        role="decomposer",
        policy_id="provider/model",
    )
    assert receipt.payload.exceeded_reservation is True
    assert str(balance.remaining_usd) == "0.1"
    with pytest.raises(ResearchBudgetExceeded):
        _reserve(
            authority,
            _reservation("two", projected=0.2, parent_event_id=start_id),
        )


def test_terminal_transition_reads_sealed_prefix_and_writes_live_tail(tmp_path):
    authority = InvestigationAuthority("alice", "inv-sealed", tmp_path)
    start_id = _start(authority, 1.0)
    reservation = _reservation("one", projected=0.4, parent_event_id=start_id)
    reservation_event, _ = _reserve(authority, reservation)
    if seal_investigation_authorized(authority) is None:
        pytest.skip("pyarrow is required for sealed-prefix coverage")

    _, balance = release_research_call_authorized(
        authority,
        ResearchCallReleasedPayload(
            reservation_id=reservation.reservation_id,
            reservation_event_id=reservation_event.event_id,
            request_sha256=reservation.request_sha256,
            reason="circuit_open",
        ),
        role="decomposer",
        policy_id="provider/model",
    )
    assert balance.outstanding_usd == 0
    _, after = _reserve(
        authority,
        _reservation("two", projected=0.9, parent_event_id=start_id),
    )
    assert str(after.remaining_usd) == "0.1"
    assert [row["action_type"] for row in trajectory_authorized(authority)] == [
        "investigation.start_requested",
        "research.call_reserved",
        "research.call_released",
        "research.call_reserved",
    ]


def test_settlement_cannot_retroactively_authorize_a_pre_reservation_call(tmp_path):
    authority = InvestigationAuthority("alice", "inv-retroactive", tmp_path)
    start_id = _start(authority, 1.0)
    reservation = _reservation("one", projected=0.5, parent_event_id=start_id)
    paid_before_hold = prepare_typed_event(
        authority.investigation_id,
        DispatchCallPayload(
            provider=reservation.provider,
            model=reservation.model,
            tier=reservation.tier,
            target_role=reservation.target_role,
            input_tokens=10,
            output_tokens=10,
            cost_usd=0.1,
            latency_ms=1,
            fallback_chain_index=reservation.fallback_chain_index,
            prompt_hash=reservation.prompt_hash,
        ),
        event_id="evt-paid-before-hold",
        parent_event_id=start_id,
    )
    append_event_once_authorized(authority, paid_before_hold)
    reservation_event, _ = _reserve(authority, reservation)

    with pytest.raises(ResearchBudgetLedgerInvalid, match="post-reservation"):
        settle_research_call_authorized(
            authority,
            ResearchCallSettledPayload(
                reservation_id=reservation.reservation_id,
                reservation_event_id=reservation_event.event_id,
                request_sha256=reservation.request_sha256,
                dispatch_call_event_id=paid_before_hold.event_id,
                actual_cost_usd=0.1,
            ),
            role="decomposer",
            policy_id="provider/model",
        )
    _, released_balance = release_research_call_authorized(
        authority,
        ResearchCallReleasedPayload(
            reservation_id=reservation.reservation_id,
            reservation_event_id=reservation_event.event_id,
            request_sha256=reservation.request_sha256,
            reason="provider_call_not_attempted",
        ),
        role="decomposer",
        policy_id="provider/model",
    )
    assert released_balance.outstanding_usd == 0


def test_one_dispatch_receipt_cannot_settle_two_reservations(tmp_path):
    authority = InvestigationAuthority("alice", "inv-double-settle", tmp_path)
    start_id = _start(authority, 1.0)
    first = _reservation("one", projected=0.3, parent_event_id=start_id)
    second = _reservation("two", projected=0.3, parent_event_id=start_id).model_copy(
        update={"prompt_hash": first.prompt_hash}
    )
    first_event, _ = _reserve(authority, first)
    second_event, _ = _reserve(authority, second)
    dispatch = prepare_typed_event(
        authority.investigation_id,
        DispatchCallPayload(
            provider=first.provider,
            model=first.model,
            tier=first.tier,
            target_role=first.target_role,
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.1,
            latency_ms=1,
            fallback_chain_index=0,
            prompt_hash=first.prompt_hash,
        ),
        event_id=research_call_dispatch_event_id(first_event.event_id),
        parent_event_id=start_id,
    )
    append_event_once_authorized(authority, dispatch)
    settle_research_call_authorized(
        authority,
        ResearchCallSettledPayload(
            reservation_id=first.reservation_id,
            reservation_event_id=first_event.event_id,
            request_sha256=first.request_sha256,
            dispatch_call_event_id=dispatch.event_id,
            actual_cost_usd=0.1,
        ),
        role="decomposer",
        policy_id="provider/model",
    )
    with pytest.raises(ResearchBudgetLedgerInvalid, match="bindings conflict"):
        settle_research_call_authorized(
            authority,
            ResearchCallSettledPayload(
                reservation_id=second.reservation_id,
                reservation_event_id=second_event.event_id,
                request_sha256=second.request_sha256,
                dispatch_call_event_id=dispatch.event_id,
                actual_cost_usd=0.1,
            ),
            role="decomposer",
            policy_id="provider/model",
        )


@pytest.mark.parametrize(
    "reason",
    [
        "provider_unregistered",
        "circuit_open",
        "route_disallowed",
        "provider_call_not_attempted",
    ],
)
def test_recorded_dispatch_cannot_be_released_as_unattempted(tmp_path, reason):
    authority = InvestigationAuthority("alice", f"inv-release-{reason}", tmp_path)
    start_id = _start(authority)
    reservation = _reservation("one", projected=0.2, parent_event_id=start_id)
    reservation_event, _ = _reserve(authority, reservation)
    dispatch = prepare_typed_event(
        authority.investigation_id,
        DispatchCallPayload(
            provider=reservation.provider,
            model=reservation.model,
            tier=reservation.tier,
            target_role=reservation.target_role,
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.01,
            latency_ms=1,
            fallback_chain_index=reservation.fallback_chain_index,
            prompt_hash=reservation.prompt_hash,
        ),
        event_id=research_call_dispatch_event_id(reservation_event.event_id),
        parent_event_id=start_id,
    )
    append_event_once_authorized(authority, dispatch)
    with pytest.raises(ResearchBudgetLedgerInvalid, match="cannot be released"):
        release_research_call_authorized(
            authority,
            ResearchCallReleasedPayload(
                reservation_id=reservation.reservation_id,
                reservation_event_id=reservation_event.event_id,
                request_sha256=reservation.request_sha256,
                reason=reason,
            ),
            role="decomposer",
            policy_id="provider/model",
        )


def test_replay_binds_role_and_policy_envelope(tmp_path):
    authority = InvestigationAuthority("alice", "inv-envelope", tmp_path)
    start_id = _start(authority)
    reservation = _reservation("one", projected=0.2, parent_event_id=start_id)
    reservation_event, _ = _reserve(authority, reservation)
    for role, policy_id in (
        ("synthesizer", "provider/model"),
        ("decomposer", "changed/model"),
    ):
        with pytest.raises(ResearchBudgetLedgerInvalid, match="reserved route"):
            reserve_research_call_authorized(
                authority,
                reservation,
                role=role,
                policy_id=policy_id,
            )
    release = ResearchCallReleasedPayload(
        reservation_id=reservation.reservation_id,
        reservation_event_id=reservation_event.event_id,
        request_sha256=reservation.request_sha256,
        reason="provider_unregistered",
    )
    release_research_call_authorized(
        authority,
        release,
        role="decomposer",
        policy_id="provider/model",
    )
    with pytest.raises(ResearchBudgetLedgerInvalid, match="reserved route"):
        release_research_call_authorized(
            authority,
            release,
            role="decomposer",
            policy_id="changed/model",
        )

    settled_authority = InvestigationAuthority("alice", "inv-settle-envelope", tmp_path)
    settled_start = _start(settled_authority)
    settled_reservation = _reservation(
        "two", projected=0.2, parent_event_id=settled_start
    )
    settled_reservation_event, _ = _reserve(
        settled_authority, settled_reservation
    )
    dispatch = prepare_typed_event(
        settled_authority.investigation_id,
        DispatchCallPayload(
            provider=settled_reservation.provider,
            model=settled_reservation.model,
            tier=settled_reservation.tier,
            target_role=settled_reservation.target_role,
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.1,
            latency_ms=1,
            fallback_chain_index=settled_reservation.fallback_chain_index,
            prompt_hash=settled_reservation.prompt_hash,
        ),
        event_id=research_call_dispatch_event_id(
            settled_reservation_event.event_id
        ),
        parent_event_id=settled_start,
    )
    append_event_once_authorized(settled_authority, dispatch)
    settlement = ResearchCallSettledPayload(
        reservation_id=settled_reservation.reservation_id,
        reservation_event_id=settled_reservation_event.event_id,
        request_sha256=settled_reservation.request_sha256,
        dispatch_call_event_id=dispatch.event_id,
        actual_cost_usd=0.1,
    )
    settle_research_call_authorized(
        settled_authority,
        settlement,
        role="decomposer",
        policy_id="provider/model",
    )
    for role, policy_id in (
        ("synthesizer", "provider/model"),
        ("decomposer", "changed/model"),
    ):
        with pytest.raises(ResearchBudgetLedgerInvalid, match="reserved route"):
            settle_research_call_authorized(
                settled_authority,
                settlement,
                role=role,
                policy_id=policy_id,
            )


def test_unknown_terminal_and_duplicate_start_make_ledger_unusable(tmp_path):
    unknown = InvestigationAuthority("alice", "inv-unknown-terminal", tmp_path)
    unknown_start = _start(unknown)
    orphan = prepare_typed_event(
        unknown.investigation_id,
        ResearchCallReleasedPayload(
            reservation_id="res-missing",
            reservation_event_id="evt-missing",
            request_sha256="f" * 64,
            reason="route_disallowed",
        ),
    )
    append_event_once_authorized(unknown, orphan)
    with pytest.raises(ResearchBudgetLedgerInvalid, match="unknown reservation"):
        _reserve(
            unknown,
            _reservation("one", projected=0.1, parent_event_id=unknown_start),
        )

    duplicate = InvestigationAuthority("alice", "inv-duplicate-start", tmp_path)
    duplicate_start = _start(duplicate)
    duplicate_manifest = _accepted_manifest()
    append_event_once_authorized(
        duplicate,
        prepare_typed_event(
            duplicate.investigation_id,
                InvestigationStartRequestedPayload(
                    question="A conflicting second start",
                    approved_run_ceiling_usd=1.0,
                    research_quote_id="c" * 64,
                    research_quote_payload_sha256="d" * 64,
                    research_route_manifest_fingerprint=(
                        duplicate_manifest.fingerprint
                    ),
                    research_quote_expires_at_ms=4_102_444_800_000,
                    research_route_manifest=tuple(
                        ResearchQuotedRoute(**row.__dict__)
                        for row in duplicate_manifest.routes
                    ),
                ),
            event_id="evt-second-start",
        ),
    )
    with pytest.raises(ResearchBudgetLedgerInvalid, match="exactly one"):
        _reserve(
            duplicate,
            _reservation("one", projected=0.1, parent_event_id=duplicate_start),
        )


def test_settlement_requires_existing_dispatch_and_exact_cost(tmp_path):
    authority = InvestigationAuthority("alice", "inv-dispatch-proof", tmp_path)
    start_id = _start(authority)
    reservation = _reservation("one", projected=0.3, parent_event_id=start_id)
    reservation_event, _ = _reserve(authority, reservation)
    missing = ResearchCallSettledPayload(
        reservation_id=reservation.reservation_id,
        reservation_event_id=reservation_event.event_id,
        request_sha256=reservation.request_sha256,
        dispatch_call_event_id="evt-not-there",
        actual_cost_usd=0.1,
    )
    with pytest.raises(ResearchBudgetLedgerInvalid, match="missing"):
        settle_research_call_authorized(
            authority,
            missing,
            role="decomposer",
            policy_id="provider/model",
        )
    dispatch = prepare_typed_event(
        authority.investigation_id,
        DispatchCallPayload(
            provider=reservation.provider,
            model=reservation.model,
            tier=reservation.tier,
            target_role=reservation.target_role,
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.2,
            latency_ms=1,
            fallback_chain_index=reservation.fallback_chain_index,
            prompt_hash=reservation.prompt_hash,
        ),
        event_id=research_call_dispatch_event_id(reservation_event.event_id),
        parent_event_id=start_id,
    )
    append_event_once_authorized(authority, dispatch)
    with pytest.raises(ResearchBudgetLedgerInvalid, match="cost disagrees"):
        settle_research_call_authorized(
            authority,
            missing.model_copy(
                update={"dispatch_call_event_id": dispatch.event_id}
            ),
            role="decomposer",
            policy_id="provider/model",
        )
