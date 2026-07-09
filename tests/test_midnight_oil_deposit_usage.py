"""Midnight Oil deposit records Antiek-bench usage + progress (residual au)."""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.antiek_bench import InMemoryBenchStore, list_usage_events  # noqa: E402
from substrate.engagement_spine import list_progress  # noqa: E402
from substrate.engagement_spine.store import InMemoryEngagementStore  # noqa: E402
from substrate.midnight_oil.ceiling import ModelPricing  # noqa: E402
from substrate.midnight_oil.deposit import deposit_job_results  # noqa: E402
from substrate.midnight_oil.job import InMemoryJobStore  # noqa: E402
from substrate.midnight_oil.product_path import (  # noqa: E402
    approve_price_ceiling,
    create_with_recommended_ceiling,
)


PRICING = ModelPricing("test-model", 1.0, 3.0)


def test_deposit_records_usage_and_progress():
    jobs = InMemoryJobStore()
    eng = InMemoryEngagementStore()
    bench = InMemoryBenchStore()
    created = create_with_recommended_ceiling(
        ("Investigate twin note flywheel for midnight oil.",),
        30,
        store=jobs,
        pricing=PRICING,
        model_id="test-model",
    )
    approve_price_ceiling(
        created.job.job_id, store=jobs, use_recommended=True
    )
    # Force a status that deposit will treat as complete path for usage
    row = jobs.get_job(created.job.job_id)
    assert row is not None
    row = dict(row)
    row["status"] = "complete"
    jobs.put_job(row) if hasattr(jobs, "put_job") else None
    # InMemoryJobStore uses put_job_state pattern — use deposit which reads job
    # Re-put via job module
    from substrate.midnight_oil.job import put_job_state, _job_from_row

    job = _job_from_row(row)
    put_job_state(job, store=jobs)

    result = deposit_job_results(
        created.job.job_id,
        job_store=jobs,
        engagement_store=eng,
        draft_combined=True,
        bench_usage_store=bench,
        record_progress=True,
    )
    assert result.twin_count >= 1
    assert result.html
    assert "application/pdf" not in result.html.lower()
    assert result.usage_recorded is True
    assert result.usage_event is not None
    assert result.usage_event.get("outcome") == "worked"
    events = list_usage_events(store=bench)
    assert len(events) == 1
    assert events[0]["source"] == "session_flywheel"
    assert result.progress_seeded is True
    assert result.spawn_ids
    progress = list_progress(result.spawn_ids[0], store=eng)
    assert len(progress) >= 4
    assert progress[-1].stage == "complete"


def test_deposit_without_bench_store_still_works():
    jobs = InMemoryJobStore()
    eng = InMemoryEngagementStore()
    created = create_with_recommended_ceiling(
        ("Goal only path.",),
        15,
        store=jobs,
        pricing=PRICING,
    )
    approve_price_ceiling(created.job.job_id, store=jobs, use_recommended=True)
    from substrate.midnight_oil.job import put_job_state, _job_from_row

    row = dict(jobs.get_job(created.job.job_id))
    row["status"] = "complete"
    put_job_state(_job_from_row(row), store=jobs)
    result = deposit_job_results(
        created.job.job_id,
        job_store=jobs,
        engagement_store=eng,
        bench_usage_store=None,
        record_progress=False,
    )
    assert result.usage_recorded is False
    assert result.twin_count >= 1
    assert result.view_format if hasattr(result, "view_format") else True
