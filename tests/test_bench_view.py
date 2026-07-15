from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.settings_budget import register_settings_budget_routes


def _client() -> TestClient:
    app = FastAPI()
    register_settings_budget_routes(app)
    return TestClient(app)


def _report_payload(*, generated_at: datetime | None = None) -> dict:
    generated = generated_at or datetime.now(UTC)
    iso = generated.isocalendar()
    return {
        "schema_version": "antiek.model-bench.v1",
        "week_id": f"{iso.year}-W{iso.week:02d}",
        "generated_at": generated.isoformat(),
        "measurements": [
            {
                "task": "reading",
                "tier": "pro",
                "provider": "zai",
                "model": "glm",
                "score": 0.91,
                "samples": 12,
            }
        ],
    }


def test_weekly_benchmark_reads_validated_server_report(tmp_path, monkeypatch) -> None:
    report = tmp_path / "bench.json"
    report.write_text(
        json.dumps(_report_payload()),
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTIEK_BENCH_REPORT_PATH", str(report))
    body = _client().get("/settings/antiek-bench/weekly").json()
    assert body["authority"] == "advisory"
    assert body["status"] == "measured"
    assert body["week_id"].startswith(str(datetime.now(UTC).year))
    assert body["measurements"][0]["score"] == 0.91


def test_weekly_benchmark_rejects_bool_empty_and_mismatched_week(
    tmp_path, monkeypatch
) -> None:
    report = tmp_path / "bench.json"
    monkeypatch.setenv("ANTIEK_BENCH_REPORT_PATH", str(report))
    invalid_payloads = []
    for field in ("score", "samples"):
        payload = _report_payload()
        payload["measurements"][0][field] = True
        invalid_payloads.append(payload)
    empty = _report_payload()
    empty["measurements"] = []
    invalid_payloads.append(empty)
    wrong_week = _report_payload()
    wrong_week["week_id"] = "2025-W01"
    invalid_payloads.append(wrong_week)

    for payload in invalid_payloads:
        report.write_text(json.dumps(payload), encoding="utf-8")
        body = _client().get("/settings/antiek-bench/weekly").json()
        assert body["status"] == "unavailable"
        assert body["measurements"] == []


def test_weekly_benchmark_never_accepts_injected_records(monkeypatch) -> None:
    monkeypatch.delenv("ANTIEK_BENCH_REPORT_PATH", raising=False)
    client = _client()
    response = client.post(
        "/settings/antiek-bench/weekly",
        json={"records": [{"task": "reading", "model": "fake", "score": 1}]},
    )
    assert response.status_code == 405
    body = client.get("/settings/antiek-bench/weekly").json()
    assert body["status"] == "unavailable"
    assert body["measurements"] == []
