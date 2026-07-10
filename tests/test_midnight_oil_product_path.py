"""Product path: create → recommended ceiling → approve (residual ad).

Drives shipped product_path + create_job/approve_job. No network.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.midnight_oil import (  # noqa: E402
    approve_price_ceiling,
    create_recommend_and_approve,
    create_with_recommended_ceiling,
    job_summary_html,
    product_result_html,
    recommend_price_ceiling,
)
from substrate.midnight_oil.ceiling import ModelPricing  # noqa: E402
from substrate.midnight_oil.job import InMemoryJobStore  # noqa: E402

GOALS = ("Map residual risks in retrieval-augmented generation.",)
DURATION = 60
PRICING = ModelPricing("test-model", 1.0, 3.0)


def test_create_surfaces_positive_recommended_ceiling():
    store = InMemoryJobStore()
    result = create_with_recommended_ceiling(
        GOALS,
        DURATION,
        store=store,
        model_id="test-model",
        pricing=PRICING,
        fanout_depth=3,
    )
    assert result.view_format == "html"
    assert result.runnable is False
    assert result.job.status == "awaiting_approval"
    assert result.recommended_price_ceiling_usd > 0
    expected = recommend_price_ceiling(
        DURATION, model_id="test-model", pricing=PRICING, fanout_depth=3
    )
    assert result.recommended_price_ceiling_usd == expected
    assert result.job.approved_ceiling_usd is None


def test_approve_at_recommended_runnable():
    store = InMemoryJobStore()
    created = create_with_recommended_ceiling(
        GOALS, DURATION, store=store, pricing=PRICING
    )
    approved = approve_price_ceiling(
        created.job.job_id,
        store=store,
        use_recommended=True,
    )
    assert approved.runnable is True
    assert approved.job.status == "approved"
    assert (
        approved.job.approved_ceiling_usd
        == created.recommended_price_ceiling_usd
    )


def test_approve_below_without_force_fails():
    store = InMemoryJobStore()
    created = create_with_recommended_ceiling(
        GOALS, DURATION, store=store, pricing=PRICING
    )
    with pytest.raises(ValueError, match="below recommended"):
        approve_price_ceiling(
            created.job.job_id,
            created.recommended_price_ceiling_usd * 0.5,
            store=store,
        )


def test_approve_force_below_records():
    store = InMemoryJobStore()
    created = create_with_recommended_ceiling(
        GOALS, DURATION, store=store, pricing=PRICING
    )
    approved = approve_price_ceiling(
        created.job.job_id,
        0.01,
        store=store,
        force_below=True,
    )
    assert approved.job.status == "approved"
    assert approved.job.force_below_recommended is True
    assert "force_below" in approved.job.notes
    assert approved.runnable is True


def test_double_run_same_inputs_stable_ceiling():
    store = InMemoryJobStore()
    kwargs = dict(
        store=store,
        model_id="test-model",
        pricing=PRICING,
        fanout_depth=3,
    )
    a = create_with_recommended_ceiling(GOALS, DURATION, **kwargs)
    b = create_with_recommended_ceiling(GOALS, DURATION, **kwargs)
    assert a.recommended_price_ceiling_usd == b.recommended_price_ceiling_usd
    a2 = approve_price_ceiling(a.job.job_id, store=store, use_recommended=True)
    b2 = approve_price_ceiling(b.job.job_id, store=store, use_recommended=True)
    assert a2.job.approved_ceiling_usd == b2.job.approved_ceiling_usd
    assert a2.job.status == b2.job.status == "approved"


def test_create_recommend_and_approve_convenience():
    store = InMemoryJobStore()
    result = create_recommend_and_approve(
        GOALS,
        DURATION,
        store=store,
        pricing=PRICING,
        use_recommended=True,
    )
    assert result.runnable is True
    assert result.job.status == "approved"
    assert result.view_format == "html"


def test_job_summary_html_not_pdf():
    store = InMemoryJobStore()
    created = create_with_recommended_ceiling(
        GOALS, DURATION, store=store, pricing=PRICING
    )
    html = job_summary_html(created.job)
    assert html.strip()
    assert "application/pdf" not in html.lower()
    assert "Midnight Oil" in html or created.job.job_id in html
    approved = approve_price_ceiling(
        created.job.job_id, store=store, use_recommended=True
    )
    html2 = product_result_html(approved)
    assert "approved" in html2.lower() or "Approved" in html2
