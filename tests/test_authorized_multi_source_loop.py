from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from runtime.research_runner.authorized_gather import GatherProviderResult
from runtime.research_runner.budget import BudgetManager
from runtime.research_runner.gather_launch_plan import AuthorizedGatherLaunchPlan
from runtime.research_runner.gather_plan import GatherSource, GatherSourcePlan
from runtime.research_runner.host_local import (
    LoopContext,
    make_authorized_multi_source_gather_loop,
)
from runtime.research_runner.protocol import BudgetCap, ResearchPlan
from substrate.graph import ensure_initialized
from substrate.investigation_tenancy import InvestigationAuthority


@dataclass
class Provider:
    source: GatherSource
    result: GatherProviderResult | None = None
    error: Exception | None = None
    calls: int = 0

    def execute(self, **kwargs: object) -> GatherProviderResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def _authority() -> InvestigationAuthority:
    return InvestigationAuthority("acct", "root", Path("/tmp/antiek-multi-loop"))


def _launch() -> AuthorizedGatherLaunchPlan:
    sources = tuple(
        GatherSourcePlan(source, 1, 10 if source is GatherSource.EXA else 0, "v1")
        for source in GatherSource
    )
    return AuthorizedGatherLaunchPlan.reviewed(
        _authority(),
        legal_policy_snapshot_sha256="a" * 64,
        leaf_queries=("question",),
        sources=sources,
    )


def _providers(*, unknown: bool = False) -> dict[GatherSource, Provider]:
    return {
        source: Provider(
            source,
            error=RuntimeError("ambiguous") if unknown and source is GatherSource.EXA else None,
            result=(
                None
                if unknown and source is GatherSource.EXA
                else GatherProviderResult((f"doc-{source.value}",), 10 if source is GatherSource.EXA else 0)
            ),
        )
        for source in GatherSource
    }


def _patch_policy(
    monkeypatch: pytest.MonkeyPatch,
    released: list[str],
    reports: list[object] | None = None,
) -> None:
    monkeypatch.setattr(
        "substrate.legal_gate.policy_store.account_policy_authority",
        lambda authority: object(),
    )
    monkeypatch.setattr(
        "substrate.legal_gate.readiness.claim_policy_dispatch_lease",
        lambda *args, **kwargs: ("lease-1", object()),
    )
    monkeypatch.setattr(
        "substrate.legal_gate.readiness.require_policy_snapshot", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "substrate.legal_gate.readiness.release_policy_dispatch_lease",
        lambda *args, **kwargs: released.append(str(kwargs["lease_id"])),
    )
    monkeypatch.setattr("substrate.event_log.log_event_authorized", lambda *args, **kwargs: "evt-1")
    monkeypatch.setattr("substrate.event_log.trajectory_authorized", lambda *args: [])
    monkeypatch.setattr(
        "substrate.event_log.emit_typed_authorized_strict",
        lambda _authority, payload, **_kwargs: (
            reports.append(payload) if reports is not None else None
        )
        or "evt-report",
    )


def _collect(loop: object) -> list[object]:
    budget = BudgetManager(aggregate_cap_usd=1)
    budget.register("session-x-leaf-0", 1)
    ctx = LoopContext(
        ResearchPlan("session-x-leaf-0", "question", budget=BudgetCap(cost_usd=1)), budget
    )

    async def run() -> list[object]:
        return [event async for event in loop(ctx)]  # type: ignore[operator]

    return asyncio.run(run())


def test_loop_materializes_leaf_executes_ordered_sources_and_releases_safe_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = str(tmp_path / "gather.duckdb")
    ensure_initialized(db)
    released: list[str] = []
    reports: list[object] = []
    _patch_policy(monkeypatch, released, reports)
    providers = _providers()
    loop = make_authorized_multi_source_gather_loop(
        launch_plan=_launch(),
        authority=_authority(),
        feed_urls=("https://writer.example/feed",),
        db_path=db,
        providers_override=providers,
    )
    events = _collect(loop)

    assert [providers[source].calls for source in GatherSource] == [1, 1, 1, 1]
    assert released == ["lease-1"]
    assert len(reports) == 1
    assert reports[0].evidence_complete is True
    assert reports[0].unknown_outcome is False
    assert [event.data["source"] for event in events if event.kind == "step"] == [
        source.value for source in GatherSource
    ]
    assert len([event for event in events if event.kind == "note"]) == 4


def test_safe_lease_is_released_before_first_result_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = str(tmp_path / "gather.duckdb")
    ensure_initialized(db)
    released: list[str] = []
    reports: list[object] = []
    _patch_policy(monkeypatch, released, reports)
    loop = make_authorized_multi_source_gather_loop(
        launch_plan=_launch(),
        authority=_authority(),
        feed_urls=("https://writer.example/feed",),
        db_path=db,
        providers_override=_providers(),
    )
    budget = BudgetManager(aggregate_cap_usd=1)
    budget.register("session-x-leaf-0", 1)
    ctx = LoopContext(
        ResearchPlan("session-x-leaf-0", "question", budget=BudgetCap(cost_usd=1)), budget
    )

    async def consume_one_result() -> None:
        stream = loop(ctx)
        assert (await anext(stream)).kind == "plan"
        assert (await anext(stream)).kind == "step"
        assert released == ["lease-1"]
        await stream.aclose()

    asyncio.run(consume_one_result())


def test_completed_replay_uses_durable_receipts_without_provider_redispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = str(tmp_path / "gather.duckdb")
    ensure_initialized(db)
    released: list[str] = []
    reports: list[object] = []
    _patch_policy(monkeypatch, released, reports)
    providers = _providers()
    loop = make_authorized_multi_source_gather_loop(
        launch_plan=_launch(),
        authority=_authority(),
        feed_urls=("https://writer.example/feed",),
        db_path=db,
        providers_override=providers,
    )

    _collect(loop)
    _collect(loop)

    assert [providers[source].calls for source in GatherSource] == [1, 1, 1, 1]
    assert released == ["lease-1", "lease-1"]


def test_unknown_outcome_stops_sources_and_retains_policy_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = str(tmp_path / "gather.duckdb")
    ensure_initialized(db)
    released: list[str] = []
    reports: list[object] = []
    _patch_policy(monkeypatch, released, reports)
    providers = _providers(unknown=True)
    loop = make_authorized_multi_source_gather_loop(
        launch_plan=_launch(),
        authority=_authority(),
        feed_urls=("https://writer.example/feed",),
        db_path=db,
        providers_override=providers,
    )
    with pytest.raises(RuntimeError, match="requires reconciliation"):
        _collect(loop)
    assert [providers[source].calls for source in GatherSource] == [1, 0, 0, 0]
    assert released == []
    assert len(reports) == 1
    assert reports[0].unknown_outcome is True


def test_query_drift_fails_before_lease_or_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claimed: list[bool] = []
    monkeypatch.setattr(
        "substrate.legal_gate.readiness.claim_policy_dispatch_lease",
        lambda *args, **kwargs: claimed.append(True),
    )
    providers = _providers()
    loop = make_authorized_multi_source_gather_loop(
        launch_plan=_launch(),
        authority=_authority(),
        feed_urls=("https://writer.example/feed",),
        db_path=str(tmp_path / "gather.duckdb"),
        providers_override=providers,
    )
    budget = BudgetManager(aggregate_cap_usd=1)
    budget.register("session-x-leaf-0", 1)
    ctx = LoopContext(ResearchPlan("session-x-leaf-0", "changed"), budget)

    async def run() -> None:
        async for _event in loop(ctx):
            pass

    with pytest.raises(ValueError, match="query differs"):
        asyncio.run(run())
    assert claimed == []
    assert all(provider.calls == 0 for provider in providers.values())
