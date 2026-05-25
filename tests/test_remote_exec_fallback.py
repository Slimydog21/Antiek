"""SPR-02 M6 — runner factory + automatic fallback to host-local.

The steelman, honored (rigor #2): host-local is the automatic fallback for
both the *disabled* case and the *provider-unavailable* case. The call site
stays runner-agnostic — it asks the factory for a ``ResearchRunner`` and never
branches on type. Gates:

  * disabled (no env, no explicit) → ``HostLocalRunner``, no warning (it is
    the documented default);
  * enabled + provider available (fake) → ``RemoteResearchRunner``;
  * enabled + provider unavailable (fake ``probe`` raises) → ``HostLocalRunner``
    **plus exactly one WARNING log line** — not a crash, not a silent swallow.

All via fakes; no SDK, no credentials, no network.
"""

from __future__ import annotations

import logging

from runtime.remote_exec import RemoteResearchRunner, build_research_runner, remote_exec_enabled
from runtime.remote_exec.factory import ENABLE_ENV
from runtime.research_runner import HostLocalRunner, make_demo_loop
from tests.remote_exec_fakes import FakeProvider, UnavailableProvider


def test_disabled_selects_host_local_no_warning(monkeypatch, caplog):
    monkeypatch.delenv(ENABLE_ENV, raising=False)
    with caplog.at_level(logging.WARNING, logger="antiek.remote_exec"):
        runner = build_research_runner(loop_fn=make_demo_loop(steps=1))
    assert isinstance(runner, HostLocalRunner)
    # the default is silent — host-local is the sanctioned baseline
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_explicit_disabled_overrides_env(monkeypatch):
    monkeypatch.setenv(ENABLE_ENV, "1")
    runner = build_research_runner(loop_fn=make_demo_loop(steps=1),
                                   enabled=False, provider=FakeProvider())
    assert isinstance(runner, HostLocalRunner)


def test_enabled_and_available_selects_remote(monkeypatch):
    monkeypatch.setenv(ENABLE_ENV, "1")
    runner = build_research_runner(loop_fn=make_demo_loop(steps=1),
                                   provider=FakeProvider())
    assert isinstance(runner, RemoteResearchRunner)


def test_enabled_via_env_flag(monkeypatch):
    monkeypatch.setenv(ENABLE_ENV, "true")
    assert remote_exec_enabled() is True
    monkeypatch.setenv(ENABLE_ENV, "0")
    assert remote_exec_enabled() is False
    monkeypatch.delenv(ENABLE_ENV, raising=False)
    assert remote_exec_enabled() is False
    # explicit config wins over env
    monkeypatch.setenv(ENABLE_ENV, "0")
    assert remote_exec_enabled(explicit=True) is True


def test_unavailable_provider_falls_back_with_one_log_line(monkeypatch, caplog):
    monkeypatch.setenv(ENABLE_ENV, "1")
    with caplog.at_level(logging.WARNING, logger="antiek.remote_exec"):
        runner = build_research_runner(loop_fn=make_demo_loop(steps=1),
                                       provider=UnavailableProvider())
    # fell back to host-local — not a crash
    assert isinstance(runner, HostLocalRunner)
    # exactly one WARNING line, naming the fallback
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1
    assert "falling back to" in warnings[0].getMessage()
    assert "host-local" in warnings[0].getMessage().lower()


def test_unavailable_via_provider_factory(monkeypatch, caplog):
    # The factory probes a provider built lazily from a factory callable.
    monkeypatch.setenv(ENABLE_ENV, "1")
    with caplog.at_level(logging.WARNING, logger="antiek.remote_exec"):
        runner = build_research_runner(
            loop_fn=make_demo_loop(steps=1),
            provider_factory=lambda: UnavailableProvider(),
        )
    assert isinstance(runner, HostLocalRunner)
    assert len([r for r in caplog.records if r.levelno >= logging.WARNING]) == 1


def test_shared_budget_threaded_through_both_runners(monkeypatch):
    # The factory passes the same BudgetManager to whichever runner it picks,
    # so the aggregate cap is shared regardless of fallback.
    from runtime.research_runner import BudgetManager
    monkeypatch.setenv(ENABLE_ENV, "1")
    b = BudgetManager(aggregate_cap_usd=2.5)
    remote = build_research_runner(loop_fn=make_demo_loop(steps=1),
                                   provider=FakeProvider(), budget=b)
    assert remote.budget is b
    fallback = build_research_runner(loop_fn=make_demo_loop(steps=1),
                                     provider=UnavailableProvider(), budget=b)
    assert fallback.budget is b


async def test_factory_result_is_drivable_through_protocol(monkeypatch):
    # The whole point: the caller drives the factory's result through the
    # protocol without knowing which runner it got. Exercise both.
    import os
    import tempfile
    monkeypatch.setenv(ENABLE_ENV, "1")
    ev = os.path.join(tempfile.mkdtemp(), "events")
    os.makedirs(ev, exist_ok=True)
    from runtime.research_runner import BudgetCap, ResearchPlan, RunState

    for provider in (FakeProvider(steps=1), UnavailableProvider()):
        runner = build_research_runner(loop_fn=make_demo_loop(steps=1),
                                       provider=provider, events_dir=ev)
        plan = ResearchPlan(investigation_id="inv-x", sub_question="q?",
                            budget=BudgetCap(cost_usd=1.0))
        h = await runner.start("inv-x", plan)
        events = [e async for e in runner.stream(h)]
        assert events[-1].state in (RunState.DONE, RunState.STOPPED)
