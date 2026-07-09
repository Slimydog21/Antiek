"""Midnight Oil env-gated live step injector (residual bs)."""

from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.midnight_oil import (  # noqa: E402
    ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV,
    approve_price_ceiling,
    clear_midnight_oil_live_step,
    configure_midnight_oil_live_step,
    create_with_recommended_ceiling,
    live_step_enabled,
    resolve_worker_step_fn,
    run_job_offline,
)
from substrate.midnight_oil.ceiling import ModelPricing  # noqa: E402
from substrate.midnight_oil.job import InMemoryJobStore  # noqa: E402
from substrate.midnight_oil.worker import WorkerStepResult  # noqa: E402


def _approved_job(store: InMemoryJobStore):
    created = create_with_recommended_ceiling(
        ("Goal live",),
        30,
        store=store,
        pricing=ModelPricing("m", 1.0, 3.0),
    )
    approve_price_ceiling(
        created.job.job_id, store=store, use_recommended=True
    )
    return created.job.job_id


def test_live_step_default_off():
    os.environ.pop(ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV, None)
    clear_midnight_oil_live_step()
    assert live_step_enabled() is False
    _fn, used = resolve_worker_step_fn()
    assert used is False


def test_env_alone_does_not_go_live_without_injector():
    os.environ[ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV] = "1"
    clear_midnight_oil_live_step()
    try:
        assert live_step_enabled() is True
        _fn, used = resolve_worker_step_fn()
        assert used is False  # no injector → stay offline
    finally:
        os.environ.pop(ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV, None)


def test_live_injector_requires_env_and_fn():
    store = InMemoryJobStore()
    job_id = _approved_job(store)
    calls: list[str] = []

    def live_fn(job):
        calls.append(job.job_id)
        idx = len(job.spawn_ids)
        return WorkerStepResult(
            spent_usd=0.02,
            spawn_id=f"spn_live_{idx}",
            output_text="Live injected step",
            insights=("live insight",),
            questions=("live question?",),
            done=True,
        )

    os.environ[ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV] = "1"
    configure_midnight_oil_live_step(live_fn)
    try:
        out = run_job_offline(job_id, store=store)
        assert out["offline"] is False
        assert out["live_step"] is True
        assert out["view_format"] == "html"
        assert calls  # injector was used
        assert out["spawn_ids"]
    finally:
        clear_midnight_oil_live_step()
        os.environ.pop(ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV, None)


def test_force_offline_ignores_live_config():
    store = InMemoryJobStore()
    job_id = _approved_job(store)

    def live_fn(job):
        raise AssertionError("must not be called when force_offline")

    os.environ[ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV] = "1"
    configure_midnight_oil_live_step(live_fn)
    try:
        out = run_job_offline(job_id, store=store, force_offline=True)
        assert out["offline"] is True
        assert out["live_step"] is False
        assert out["status"] == "complete"
    finally:
        clear_midnight_oil_live_step()
        os.environ.pop(ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV, None)


def test_injector_without_env_stays_offline():
    store = InMemoryJobStore()
    job_id = _approved_job(store)
    calls: list[str] = []

    def live_fn(job):
        calls.append("x")
        return WorkerStepResult(spent_usd=0.01, done=True)

    os.environ.pop(ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV, None)
    configure_midnight_oil_live_step(live_fn)
    try:
        out = run_job_offline(job_id, store=store)
        assert out["offline"] is True
        assert out["live_step"] is False
        assert calls == []
    finally:
        clear_midnight_oil_live_step()
