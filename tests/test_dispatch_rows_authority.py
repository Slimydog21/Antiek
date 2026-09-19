from datetime import UTC, datetime, timedelta

from runtime.weekly_report import iter_window_events
from substrate.analytics.dispatch_rows import iter_dispatch_call_rows
from substrate.coordination.cost_view import Workflow, build_cost_view
from substrate.event_log import emit_typed_authorized, log_event_authorized
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.schemas import DispatchCallPayload


def test_dispatch_analytics_isolates_same_display_id_by_account(tmp_path):
    for account_id, provider in (("alice", "openai"), ("bob", "anthropic")):
        authority = InvestigationAuthority(account_id, "inv-shared", tmp_path)
        initialize_composite_stream(authority)
        log_event_authorized(
            authority,
            "dispatch.call",
            payload={
                "target_role": "evidence_retriever",
                "provider": provider,
                "model": f"{provider}-model",
                "tier": "fast",
                "input_tokens": 10,
                "output_tokens": 5,
                "cost_usd": 0.01,
                "latency_ms": 20,
            },
        )

    alice = list(
        iter_dispatch_call_rows(
            authority=InvestigationAuthority("alice", "__analytics__", tmp_path)
        )
    )
    bob = list(
        iter_dispatch_call_rows(
            authority=InvestigationAuthority("bob", "__analytics__", tmp_path)
        )
    )
    assert [row["provider"] for row in alice] == ["openai"]
    assert [row["provider"] for row in bob] == ["anthropic"]
    global_rows = list(
        iter_dispatch_call_rows(
            authority=InvestigationAuthority("__operator__", "__analytics__", tmp_path),
            global_scope=True,
        )
    )
    assert [row["provider"] for row in global_rows] == ["openai", "anthropic"]


def test_dispatch_analytics_filter_cannot_select_foreign_stream(tmp_path):
    authority = InvestigationAuthority("bob", "inv-bob", tmp_path)
    initialize_composite_stream(authority)
    log_event_authorized(
        authority,
        "dispatch.call",
        payload={"provider": "anthropic", "model": "m", "tier": "fast"},
    )

    rows = list(
        iter_dispatch_call_rows(
            authority=InvestigationAuthority("alice", "__analytics__", tmp_path),
            investigation_ids=["inv-bob"],
        )
    )
    assert rows == []


def test_cost_view_uses_the_same_account_authority_boundary(tmp_path):
    for account_id, cost in (("alice", 0.25), ("bob", 9.0)):
        authority = InvestigationAuthority(account_id, "inv-shared", tmp_path)
        initialize_composite_stream(authority)
        log_event_authorized(
            authority,
            "dispatch.call",
            payload={
                "target_role": "evidence_retriever",
                "provider": "openai",
                "model": "m",
                "tier": "fast",
                "cost_usd": cost,
            },
        )

    view = build_cost_view(
        authority=InvestigationAuthority("alice", "__cost_view__", tmp_path)
    )
    assert view.workflow(Workflow.RESEARCH).raw_cost_usd == 0.25
    assert view.aggregate_raw_cost_usd == 0.25
    global_view = build_cost_view(
        authority=InvestigationAuthority("__operator__", "__cost_view__", tmp_path),
        global_scope=True,
    )
    assert global_view.aggregate_raw_cost_usd == 9.25


def test_cost_view_refuses_implicit_global_scan():
    try:
        build_cost_view()
    except ValueError as exc:
        assert "explicit authority" in str(exc)
    else:
        raise AssertionError("implicit global cost scan must fail closed")


def test_weekly_report_global_domain_preserves_same_display_accounts(tmp_path):
    for account_id, provider in (("alice", "openai"), ("bob", "anthropic")):
        authority = InvestigationAuthority(account_id, "inv-shared", tmp_path)
        initialize_composite_stream(authority)
        emit_typed_authorized(
            authority,
            DispatchCallPayload(
                provider=provider,
                model="m",
                tier="flash",
                target_role="decomposer",
                input_tokens=1,
                output_tokens=1,
                cost_usd=0.01,
                latency_ms=1,
                prompt_hash=f"hash-{account_id}",
            ),
        )
    now = datetime.now(UTC)
    rows = list(
        iter_window_events(
            now - timedelta(minutes=1),
            now + timedelta(minutes=1),
            authority=InvestigationAuthority("__operator__", "__weekly__", tmp_path),
            global_scope=True,
        )
    )
    assert sorted(event.payload.provider for event in rows) == ["anthropic", "openai"]
