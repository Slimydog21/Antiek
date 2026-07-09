"""Residual (hy): Midnight Oil live-step status — offline-honest default."""

from __future__ import annotations

from substrate.midnight_oil import (
    clear_midnight_oil_live_step,
    configure_midnight_oil_live_step,
    live_step_status_payload,
)
from substrate.midnight_oil.worker import WorkerStepResult


def setup_function() -> None:
    clear_midnight_oil_live_step()


def teardown_function() -> None:
    clear_midnight_oil_live_step()


def test_live_step_status_offline_default() -> None:
    payload = live_step_status_payload(environ={})
    assert payload["view_format"] == "html"
    assert payload["product_panel"] == "midnight_oil_live_step_status"
    assert payload["offline_honest"] is True
    assert payload["live_env"] is False
    assert payload["injector_installed"] is False


def test_live_step_status_dual_gate_live() -> None:
    configure_midnight_oil_live_step(
        lambda job: WorkerStepResult(
            job_id=job.job_id,
            spawn_id=None,
            spent_usd=0.0,
            done=True,
            note="test",
        )
    )
    payload = live_step_status_payload(
        environ={"ANTIEK_MIDNIGHT_OIL_LIVE_STEP": "1"}
    )
    assert payload["live_env"] is True
    assert payload["injector_installed"] is True
    assert payload["offline_honest"] is False
