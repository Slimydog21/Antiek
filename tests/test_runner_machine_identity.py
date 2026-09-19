from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from runtime.remote_exec.runner import RemoteResearchRunner
from runtime.research_runner.host_local import HostLocalRunner, make_demo_loop
from runtime.research_runner.protocol import BudgetCap, ResearchPlan
from substrate.investigation_streams import resolve_investigation_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.multi_user.auth import UserClaims


def _claims(subject: str = "acct/opaque-subject") -> UserClaims:
    return UserClaims(
        user_id=subject,
        email=None,
        scopes=frozenset({"private_research"}),
        issued_at="2026-07-14T00:00:00Z",
    )


def _plan(iid: str, parent: str | None = None) -> ResearchPlan:
    return ResearchPlan(
        investigation_id=iid,
        sub_question="test",
        budget=BudgetCap(cost_usd=1.0, max_steps=2),
        parent_investigation_id=parent,
    )


def _allocation(events_dir: Path, claims: UserClaims, iid: str) -> dict[str, Any]:
    resolved = resolve_investigation_stream(
        InvestigationAuthority(claims.user_id, iid, events_dir)
    )
    return json.loads(resolved.allocation_path.read_text())


class _Provider:
    name = "fake"

    async def provision(self, plan: ResearchPlan) -> Any:  # pragma: no cover
        raise AssertionError("conflict must fail before provisioning")


def test_constructors_require_claims() -> None:
    with pytest.raises(TypeError):
        HostLocalRunner(make_demo_loop())
    with pytest.raises(TypeError):
        RemoteResearchRunner(_Provider())


@pytest.mark.asyncio
@pytest.mark.parametrize("remote", [False, True])
async def test_start_rejects_plan_id_mismatch_before_mutation(
    tmp_path: Path, remote: bool
) -> None:
    claims = _claims()
    runner = (
        RemoteResearchRunner(_Provider(), claims=claims, events_dir=str(tmp_path))
        if remote
        else HostLocalRunner(make_demo_loop(steps=0), claims=claims, events_dir=str(tmp_path))
    )
    with pytest.raises(ValueError, match="does not match"):
        await runner.start("nominal", _plan("different"))
    assert runner._states == {}
    assert runner.budget.spent("nominal") == 0.0
    assert not (tmp_path / ".tenancy" / "stream-allocations").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("remote", [False, True])
async def test_root_subject_owns_composite_stream_and_other_subject_is_isolated(
    tmp_path: Path, remote: bool
) -> None:
    claims = _claims()
    runner = (
        RemoteResearchRunner(_Provider(), claims=claims, events_dir=str(tmp_path))
        if remote
        else HostLocalRunner(
            make_demo_loop(steps=0), claims=claims, events_dir=str(tmp_path)
        )
    )
    await runner.start("root", _plan("root"))
    allocation = _allocation(tmp_path, claims, "root")
    expected = InvestigationAuthority(claims.user_id, "root", tmp_path)
    assert allocation["account_digest"] == expected.account_digest
    assert claims.user_id not in json.dumps(allocation)

    conflicting = (
        RemoteResearchRunner(_Provider(), claims=_claims("other"), events_dir=str(tmp_path))
        if remote
        else HostLocalRunner(
            make_demo_loop(steps=0),
            claims=_claims("other"),
            events_dir=str(tmp_path),
        )
    )
    await conflicting.start("root", _plan("root"))
    other = _allocation(tmp_path, _claims("other"), "root")
    assert other["stream_key"] != allocation["stream_key"]
    assert conflicting.budget.spent("root") == 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize("remote", [False, True])
async def test_child_inherits_parent_account_authority(tmp_path: Path, remote: bool) -> None:
    claims = _claims()
    runner = (
        RemoteResearchRunner(_Provider(), claims=claims, events_dir=str(tmp_path))
        if remote
        else HostLocalRunner(
            make_demo_loop(steps=0), claims=claims, events_dir=str(tmp_path)
        )
    )
    await runner.start("parent", _plan("parent"))
    await runner.start("child", _plan("child", "parent"))
    assert _allocation(tmp_path, claims, "child")["account_digest"] == _allocation(
        tmp_path, claims, "parent"
    )["account_digest"]


@pytest.mark.asyncio
@pytest.mark.parametrize("remote", [False, True])
async def test_child_rejects_parent_owned_by_other_claims(
    tmp_path: Path, remote: bool
) -> None:
    owner = HostLocalRunner(
        make_demo_loop(steps=0), claims=_claims("owner"), events_dir=str(tmp_path)
    )
    await owner.start("parent", _plan("parent"))
    foreign = (
        RemoteResearchRunner(_Provider(), claims=_claims("foreign"), events_dir=str(tmp_path))
        if remote
        else HostLocalRunner(
            make_demo_loop(steps=0),
            claims=_claims("foreign"),
            events_dir=str(tmp_path),
        )
    )
    with pytest.raises(RuntimeError):
        await foreign.start("forged-child", _plan("forged-child", "parent"))
    assert foreign._states == {}
    assert not (tmp_path / "forged-child.jsonl").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("remote", [False, True])
async def test_historic_stream_conflict_precedes_all_mutation(
    tmp_path: Path, remote: bool
) -> None:
    (tmp_path / "historic.jsonl").write_text('{"historic":true}\n')
    runner = (
        RemoteResearchRunner(_Provider(), claims=_claims(), events_dir=str(tmp_path))
        if remote
        else HostLocalRunner(
            make_demo_loop(steps=0), claims=_claims(), events_dir=str(tmp_path)
        )
    )
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    with pytest.raises(RuntimeError, match="historic"):
        await runner.start("historic", _plan("historic"))
    assert runner._states == {}
    assert runner.budget.cap("historic") == 0.0
    after = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    # Tenancy creates only its private key/lock infrastructure while checking;
    # the pre-existing event stream remains byte-identical and no lease/event exists.
    assert after[tmp_path / "historic.jsonl"] == before[tmp_path / "historic.jsonl"]
    assert not (tmp_path / ".tenancy" / "legacy-stream-leases").exists()
