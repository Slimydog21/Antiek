from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import pytest

from runtime.research_runner.authorized_gather import (
    GatherAuthorityDenied,
    GatherOutcomeUnknown,
    GatherProviderResult,
    execute_authorized_gather_call,
)
from runtime.research_runner.authorized_gather_sql import (
    DuckDBAuthorizedGatherAuthority,
    ensure_authorized_gather_schema,
)
from runtime.research_runner.gather_plan import AuthorizedGatherPlan, GatherSource, GatherSourcePlan
from substrate.graph.schema import init_database_at_path
from substrate.investigation_tenancy import InvestigationAuthority


def _authority(root: Path, account: str = "acct-1") -> InvestigationAuthority:
    return InvestigationAuthority(account, "inv-1", root)


def _plan(authority: InvestigationAuthority) -> AuthorizedGatherPlan:
    return AuthorizedGatherPlan.reviewed(
        authority,
        legal_policy_snapshot_sha256="a" * 64,
        aggregate_max_results=2,
        aggregate_max_cost_usd="0.05",
        sources=(
            GatherSourcePlan.reviewed(
                source=GatherSource.EXA,
                max_results=2,
                max_cost_usd="0.05",
                policy_version="exa-v1",
            ),
        ),
    )


@dataclass
class Provider:
    result: GatherProviderResult = GatherProviderResult(("doc-1",), 20_001, 7, "receipt")
    error: BaseException | None = None
    source: GatherSource = GatherSource.EXA
    calls: list[str] = field(default_factory=list)

    def execute(self, **kwargs: object) -> GatherProviderResult:
        self.calls.append(str(kwargs["idempotency_key"]))
        if self.error is not None:
            raise self.error
        return self.result


def _execute(
    *,
    plan: AuthorizedGatherPlan,
    authority: InvestigationAuthority,
    store: DuckDBAuthorizedGatherAuthority,
    provider: Provider,
    key: str = "call-1",
) -> GatherProviderResult:
    return execute_authorized_gather_call(
        plan=plan,
        expected_plan_fingerprint=plan.fingerprint,
        authority=authority,
        source=GatherSource.EXA,
        query="fault tolerant quantum computing",
        idempotency_key=key,
        provider=provider,
        validate_policy_snapshot=lambda authority, snapshot: None,
        budget=store,
        receipts=store,
    )


@pytest.fixture
def durable(tmp_path: Path) -> tuple[str, InvestigationAuthority, AuthorizedGatherPlan]:
    db_path = str(tmp_path / "graph.duckdb")
    ensure_authorized_gather_schema(db_path)
    authority = _authority(tmp_path)
    return db_path, authority, _plan(authority)


def test_success_survives_restart_and_replays_without_dispatch(durable) -> None:
    db_path, authority, plan = durable
    first_store = DuckDBAuthorizedGatherAuthority(db_path, authority)
    first_provider = Provider()
    first = _execute(plan=plan, authority=authority, store=first_store, provider=first_provider)

    reopened = DuckDBAuthorizedGatherAuthority(db_path, authority)
    replay_provider = Provider()
    replay = _execute(plan=plan, authority=authority, store=reopened, provider=replay_provider)

    assert replay == first
    assert first_provider.calls == ["call-1"]
    assert replay_provider.calls == []
    con = duckdb.connect(db_path, read_only=True)
    try:
        assert con.execute(
            "SELECT spent_cost_micros, settled_results, held_cost_micros, held_results "
            "FROM authorized_gather_plans"
        ).fetchone() == (20_001, 1, 0, 0)
    finally:
        con.close()


def test_ambiguous_outcome_survives_restart_and_suppresses_redispatch(durable) -> None:
    db_path, authority, plan = durable
    provider = Provider(error=TimeoutError("outcome unknown"))
    with pytest.raises(TimeoutError):
        _execute(
            plan=plan,
            authority=authority,
            store=DuckDBAuthorizedGatherAuthority(db_path, authority),
            provider=provider,
        )

    retry = Provider()
    with pytest.raises(GatherOutcomeUnknown):
        _execute(
            plan=plan,
            authority=authority,
            store=DuckDBAuthorizedGatherAuthority(db_path, authority),
            provider=retry,
        )
    assert retry.calls == []
    con = duckdb.connect(db_path, read_only=True)
    try:
        assert con.execute(
            "SELECT state FROM authorized_gather_call_receipts"
        ).fetchone() == ("unknown",)
        assert con.execute(
            "SELECT held_cost_micros, held_results FROM authorized_gather_plans"
        ).fetchone() == (50_000, 2)
    finally:
        con.close()


def test_distinct_keys_cannot_escape_durable_aggregate_after_restart(durable) -> None:
    db_path, authority, plan = durable
    _execute(
        plan=plan,
        authority=authority,
        store=DuckDBAuthorizedGatherAuthority(db_path, authority),
        provider=Provider(),
        key="call-1",
    )
    second = Provider()
    with pytest.raises(GatherAuthorityDenied, match="aggregate gather cost"):
        _execute(
            plan=plan,
            authority=authority,
            store=DuckDBAuthorizedGatherAuthority(db_path, authority),
            provider=second,
            key="call-2",
        )
    assert second.calls == []
    con = duckdb.connect(db_path, read_only=True)
    try:
        assert con.execute(
            "SELECT call_id FROM authorized_gather_call_receipts ORDER BY call_id"
        ).fetchall() == [("call-1",)]
    finally:
        con.close()


def test_same_call_id_is_isolated_by_account_scope(durable, tmp_path: Path) -> None:
    db_path, alice, alice_plan = durable
    bob = _authority(tmp_path, "acct-2")
    bob_plan = _plan(bob)
    _execute(
        plan=alice_plan,
        authority=alice,
        store=DuckDBAuthorizedGatherAuthority(db_path, alice),
        provider=Provider(GatherProviderResult(("doc-alice",), 1)),
    )
    _execute(
        plan=bob_plan,
        authority=bob,
        store=DuckDBAuthorizedGatherAuthority(db_path, bob),
        provider=Provider(GatherProviderResult(("doc-bob",), 2)),
    )
    con = duckdb.connect(db_path, read_only=True)
    try:
        assert con.execute(
            "SELECT count(*), sum(spent_cost_micros) FROM authorized_gather_plans"
        ).fetchone() == (2, 3)
    finally:
        con.close()


def test_malformed_terminal_result_fails_closed_without_dispatch(durable) -> None:
    db_path, authority, plan = durable
    store = DuckDBAuthorizedGatherAuthority(db_path, authority)
    _execute(plan=plan, authority=authority, store=store, provider=Provider())
    con = duckdb.connect(db_path)
    try:
        con.execute(
            "UPDATE authorized_gather_call_receipts SET result_json = '{\"document_ids\":[]}'"
        )
    finally:
        con.close()
    retry = Provider()
    with pytest.raises(GatherAuthorityDenied, match="malformed"):
        _execute(
            plan=plan,
            authority=authority,
            store=DuckDBAuthorizedGatherAuthority(db_path, authority),
            provider=retry,
        )
    assert retry.calls == []


def test_canonical_graph_initialization_installs_authority_tables(tmp_path: Path) -> None:
    db_path = str(tmp_path / "canonical.duckdb")
    init_database_at_path(db_path)
    con = duckdb.connect(db_path, read_only=True)
    try:
        assert con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name LIKE "
            "'authorized_gather_%' ORDER BY table_name"
        ).fetchall() == [
            ("authorized_gather_call_receipts",),
            ("authorized_gather_plans",),
            ("authorized_gather_reservations",),
        ]
    finally:
        con.close()


def test_concurrent_distinct_calls_cannot_overreserve_one_plan(durable) -> None:
    db_path, authority, plan = durable

    def run(key: str) -> str:
        try:
            _execute(
                plan=plan,
                authority=authority,
                store=DuckDBAuthorizedGatherAuthority(db_path, authority),
                provider=Provider(GatherProviderResult((f"doc-{key}",), 1)),
                key=key,
            )
        except GatherAuthorityDenied:
            return "denied"
        return "succeeded"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(run, ("one", "two")))

    assert outcomes == ["denied", "succeeded"]
    con = duckdb.connect(db_path, read_only=True)
    try:
        assert con.execute(
            "SELECT count(*), sum(spent_cost_micros), sum(held_cost_micros) "
            "FROM authorized_gather_plans"
        ).fetchone() == (1, 1, 0)
    finally:
        con.close()


def test_undercounted_plan_counter_fails_conservation_before_dispatch(durable) -> None:
    db_path, authority, plan = durable
    with pytest.raises(TimeoutError):
        _execute(
            plan=plan,
            authority=authority,
            store=DuckDBAuthorizedGatherAuthority(db_path, authority),
            provider=Provider(error=TimeoutError("unknown")),
            key="first",
        )
    con = duckdb.connect(db_path)
    try:
        con.execute("UPDATE authorized_gather_plans SET held_cost_micros = 0")
    finally:
        con.close()
    attacker = Provider()
    with pytest.raises(GatherAuthorityDenied, match="fail conservation"):
        _execute(
            plan=plan,
            authority=authority,
            store=DuckDBAuthorizedGatherAuthority(db_path, authority),
            provider=attacker,
            key="second",
        )
    assert attacker.calls == []


def test_missing_plan_rolls_back_settlement_and_preserves_held_reservation(durable) -> None:
    db_path, authority, plan = durable
    store = DuckDBAuthorizedGatherAuthority(db_path, authority)
    store.bind_plan(
        plan_fingerprint=plan.fingerprint,
        investigation_id=authority.investigation_id,
        aggregate_max_cost_micros=plan.aggregate_max_cost_micros,
        aggregate_max_results=plan.aggregate_max_results,
    )
    reservation_id = store.reserve_micros(
        plan_fingerprint=plan.fingerprint,
        investigation_id=authority.investigation_id,
        projected_cost_micros=50_000,
        projected_results=2,
    )
    con = duckdb.connect(db_path)
    try:
        con.execute("DELETE FROM authorized_gather_plans")
    finally:
        con.close()
    with pytest.raises(GatherAuthorityDenied, match="not bound"):
        store.settle_micros(
            reservation_id,
            actual_cost_micros=1,
            actual_results=1,
            tokens=1,
        )
    con = duckdb.connect(db_path, read_only=True)
    try:
        assert con.execute(
            "SELECT state, actual_cost_micros FROM authorized_gather_reservations"
        ).fetchone() == ("held", None)
    finally:
        con.close()
