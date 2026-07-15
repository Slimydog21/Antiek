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


def test_weekly_benchmark_reads_validated_server_report(tmp_path, monkeypatch) -> None:
    report = tmp_path / "bench.json"
    report.write_text(
        json.dumps(
            {
                "schema_version": "antiek.model-bench.v1",
                "generated_at": datetime.now(UTC).isoformat(),
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
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTIEK_BENCH_REPORT_PATH", str(report))
    body = _client().get("/settings/antiek-bench/weekly").json()
    assert body["authority"] == "advisory"
    assert body["status"] == "measured"
    assert body["week_id"].startswith(str(datetime.now(UTC).year))
    assert body["measurements"][0]["score"] == 0.91


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
