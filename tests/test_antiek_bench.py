"""Real-path tests for Antiek-bench core (package C).

Offline suite run, ≥2 task classes, rewrite propose without activate,
approve/promote gate, HTML summary content properties.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.antiek_bench import (  # noqa: E402
    InMemoryBenchStore,
    SuiteRegistry,
    active_suite,
    approve_and_promote,
    default_core_suite,
    project_run_html,
    propose_suite_delta,
    register_suite,
    run_suite,
)
from substrate.antiek_bench.run import keyword_stub_provider  # noqa: E402


@pytest.fixture
def registry() -> SuiteRegistry:
    reg = SuiteRegistry()
    register_suite(default_core_suite(), registry=reg, make_active=True)
    return reg


@pytest.fixture
def store() -> InMemoryBenchStore:
    return InMemoryBenchStore()


def test_core_suite_has_two_task_classes(registry):
    suite = active_suite(registry=registry)
    classes = set(suite.task_classes())
    assert "distill" in classes
    assert "synthesize" in classes
    assert len(suite.items) >= 4


def test_run_suite_offline_records_week_and_scores(registry, store):
    result = run_suite(
        model_id="glm-5.2",
        week_id="2026-W28",
        store=store,
        registry=registry,
        provider_fn=keyword_stub_provider("glm-5.2", quality=0.9),
    )
    assert result.week_id == "2026-W28"
    assert result.suite_version == "suite-v1"
    assert result.model_id == "glm-5.2"
    assert result.run_id.startswith("brun_")
    assert len(result.scores) == len(active_suite(registry=registry).items)
    assert 0.0 <= result.mean_score <= 1.0
    assert "distill" in result.by_task_class
    assert "synthesize" in result.by_task_class
    # Persisted
    row = store.get_run(result.run_id)
    assert row is not None
    assert row["week_id"] == "2026-W28"
    assert row["suite_version"] == "suite-v1"
    assert isinstance(row["scores"], list) and len(row["scores"]) >= 2


def test_run_suite_differentiates_models(registry, store):
    high = run_suite(
        model_id="strong",
        week_id="2026-W28",
        store=store,
        registry=registry,
        provider_fn=keyword_stub_provider("strong", quality=1.0),
    )
    low = run_suite(
        model_id="weak",
        week_id="2026-W28",
        store=store,
        registry=registry,
        provider_fn=keyword_stub_provider("weak", quality=0.1),
    )
    assert high.mean_score >= low.mean_score
    assert high.run_id != low.run_id


def test_propose_does_not_change_active_suite(registry, store):
    before = active_suite(registry=registry).suite_version
    prop = propose_suite_delta(
        [
            {
                "task_class": "distill",
                "outcome": "failed",
                "prompt_hint": "Distill failed case about long-context retrieval collapse",
            },
            {"task_class": "synthesize", "outcome": "worked"},
        ],
        store=store,
        registry=registry,
    )
    assert prop.status == "proposed"
    assert prop.proposal_id.startswith("prop_")
    assert prop.added_item_ids  # failed event produced an item
    # Active unchanged without approve
    assert active_suite(registry=registry).suite_version == before
    assert prop.proposed_suite_version != before


def test_reject_keeps_active_unchanged(registry, store):
    before = active_suite(registry=registry).suite_version
    prop = propose_suite_delta(
        [{"task_class": "wrestle", "outcome": "failed", "prompt_hint": "Wrestle with citation conflicts"}],
        store=store,
        registry=registry,
    )
    still = approve_and_promote(
        prop.proposal_id, store=store, registry=registry, approve=False
    )
    assert still.suite_version == before
    row = store.get_proposal(prop.proposal_id)
    assert row is not None
    assert row["status"] == "rejected"


def test_approve_promotes_new_suite_version(registry, store):
    before = active_suite(registry=registry).suite_version
    prop = propose_suite_delta(
        [
            {
                "task_class": "book_qa",
                "outcome": "failed",
                "prompt_hint": "Answer a passage question about Pride and Prejudice themes",
            }
        ],
        store=store,
        registry=registry,
    )
    promoted = approve_and_promote(
        prop.proposal_id, store=store, registry=registry, approve=True
    )
    assert promoted.suite_version == prop.proposed_suite_version
    assert active_suite(registry=registry).suite_version == prop.proposed_suite_version
    assert active_suite(registry=registry).suite_version != before
    # New suite has the usage item
    ids = {i.item_id for i in active_suite(registry=registry).items}
    assert any(x in ids for x in prop.added_item_ids)


def test_project_run_html_has_scores_and_not_pdf(registry, store):
    result = run_suite(
        model_id="composer-2.5",
        week_id="2026-W28",
        store=store,
        registry=registry,
        provider_fn=keyword_stub_provider("composer-2.5", quality=0.85),
    )
    html = project_run_html(result.run_id, store=store)
    assert "Antiek-bench" in html or "suite-v1" in html
    assert "suite-v1" in html
    assert "composer-2.5" in html
    assert "distill" in html
    assert "synthesize" in html
    assert not html.lstrip().lower().startswith("%pdf")
    assert "score" in html.lower() or "0." in html


def test_run_requires_provider(registry, store):
    with pytest.raises(ValueError, match="provider"):
        run_suite(
            model_id="missing",
            week_id="2026-W28",
            store=store,
            registry=registry,
        )
