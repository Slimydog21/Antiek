"""Durable Antiek-bench usage store (residual aj).

ANTIEK_BENCH_USAGE_DIR / explicit root → FileBenchStore; reopen preserves events.
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api.engagement_routes import (  # noqa: E402
    get_bench_usage_store,
    reset_bench_usage_store,
)
from interfaces.research.api.settings_budget import (  # noqa: E402
    register_settings_budget_routes,
)
from substrate.antiek_bench import (  # noqa: E402
    ANTIEK_BENCH_USAGE_DIR_ENV,
    FileBenchStore,
    InMemoryBenchStore,
    list_usage_events,
    record_usage_event,
    resolve_usage_store,
    settings_usage_summary_payload,
    weekly_usage_summary,
)
from substrate.antiek_bench.usage_bridge import UsageEvent  # noqa: E402


def test_resolve_usage_store_memory_by_default(monkeypatch):
    monkeypatch.delenv(ANTIEK_BENCH_USAGE_DIR_ENV, raising=False)
    store = resolve_usage_store(create_if_missing=True)
    assert isinstance(store, InMemoryBenchStore)
    assert resolve_usage_store(create_if_missing=False) is None


def test_resolve_usage_store_file_from_root(tmp_path):
    root = tmp_path / "bench-usage"
    store = resolve_usage_store(root=root, create_if_missing=True)
    assert isinstance(store, FileBenchStore)
    assert root.is_dir()


def test_record_reopen_preserves_usage_events(tmp_path):
    root = tmp_path / "durable-usage"
    store1 = resolve_usage_store(root=root)
    assert store1 is not None
    record_usage_event(
        UsageEvent(task_class="wrestle", outcome="worked", prompt_hint="durable-a"),
        store=store1,
    )
    record_usage_event(
        UsageEvent(task_class="book_qa", outcome="failed", prompt_hint="durable-b"),
        store=store1,
    )
    s1 = weekly_usage_summary(store=store1)
    assert s1["event_count"] == 2
    assert s1["view_format"] == "html"

    # Simulated process restart: new FileBenchStore on same root
    store2 = resolve_usage_store(root=root)
    assert store2 is not None
    assert store2 is not store1
    events = list_usage_events(store=store2)
    assert len(events) == 2
    s2 = weekly_usage_summary(store=store2)
    assert s2["event_count"] == s1["event_count"]
    assert s2["by_task_class"] == s1["by_task_class"]
    payload = settings_usage_summary_payload(store=store2, include_html=True)
    assert payload["event_count"] == 2
    assert payload["view_format"] == "html"
    assert payload["html"]
    assert "application/pdf" not in payload["html"].lower()


def test_double_run_record_reopen_stable(tmp_path):
    root = tmp_path / "double-run"
    for _ in range(2):
        store = resolve_usage_store(root=root)
        assert store is not None
        # First pass records; second pass reopens and sees same base count
        existing = list_usage_events(store=store)
        if not existing:
            record_usage_event(
                UsageEvent(task_class="distill", outcome="worked"),
                store=store,
            )
        summary = weekly_usage_summary(store=store)
        assert summary["event_count"] >= 1
        assert summary["by_task_class"]["distill"]["worked"] >= 1
    # After two resolve cycles, still one event (not duplicated by double-run)
    final = resolve_usage_store(root=root)
    assert final is not None
    assert weekly_usage_summary(store=final)["event_count"] == 1


def test_env_var_wires_file_store(tmp_path, monkeypatch):
    monkeypatch.setenv(ANTIEK_BENCH_USAGE_DIR_ENV, str(tmp_path / "env-usage"))
    reset_bench_usage_store()  # clear process cache
    store = get_bench_usage_store(create_if_missing=True)
    assert isinstance(store, FileBenchStore)
    record_usage_event(
        UsageEvent(task_class="synthesize", outcome="worked"),
        store=store,
    )
    # Fresh resolve via env
    reset_bench_usage_store()
    store2 = get_bench_usage_store(create_if_missing=True)
    assert isinstance(store2, FileBenchStore)
    assert weekly_usage_summary(store=store2)["event_count"] == 1


def test_settings_api_reads_durable_store(tmp_path, monkeypatch):
    root = tmp_path / "api-usage"
    monkeypatch.setenv(ANTIEK_BENCH_USAGE_DIR_ENV, str(root))
    reset_bench_usage_store()
    store = get_bench_usage_store(create_if_missing=True)
    record_usage_event(
        UsageEvent(task_class="wrestle", outcome="worked"),
        store=store,
    )

    app = FastAPI()
    register_settings_budget_routes(app)
    # No app.state store — should fall back to engagement get_bench_usage_store
    client = TestClient(app)
    r1 = client.get("/settings/antiek-bench/usage-summary")
    assert r1.status_code == 200
    assert r1.json()["event_count"] == 1
    assert r1.json()["view_format"] == "html"
    r2 = client.get("/settings/antiek-bench/usage-summary")
    assert r2.json()["event_count"] == r1.json()["event_count"]
    assert r2.json()["by_task_class"] == r1.json()["by_task_class"]
