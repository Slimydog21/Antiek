"""Proven /health backup_freshness: honest False when missing/stale, True when fresh."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api import create_app  # noqa: E402
from interfaces.research.api.app import _probe_backup_freshness  # noqa: E402


def _client() -> TestClient:
    return TestClient(
        create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    )


def _write_marker(path: Path, completed_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "completed_at": completed_at,
                "archive": "antiek-test.tar.gz",
                "remote": "r2:antiek-backups/nightly/antiek-test.tar.gz",
                "sha256": "0" * 64,
                "counts": {
                    "documents": 1,
                    "chunks": 1,
                    "nodes": 1,
                },
                "script_version": "backup.sh/test",
            }
        )
    )


def test_health_backup_fresh_false_and_200_on_missing_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_BACKUP_MARKER", str(tmp_path / "absent" / "backup_freshness.json"))
    r = _client().get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["backup_fresh"] is False
    assert body["backup_completed_at"] is None
    assert "STALE" in body["backup_reason"] or "no marker" in body["backup_reason"]


def test_health_backup_fresh_true_on_fresh_marker(tmp_path, monkeypatch):
    marker = tmp_path / "backup_freshness.json"
    now = datetime.now(UTC)
    _write_marker(marker, now.isoformat().replace("+00:00", "Z"))
    monkeypatch.setenv("ANTIEK_BACKUP_MARKER", str(marker))
    body = _client().get("/health").json()
    assert body["backup_fresh"] is True
    assert body["backup_completed_at"] is not None
    assert body["backup_age_hours"] is not None
    assert body["backup_age_hours"] < 1.0
    assert body["backup_marker_path"] == str(marker)


def test_health_backup_fresh_false_on_stale_marker(tmp_path, monkeypatch):
    marker = tmp_path / "backup_freshness.json"
    stale = datetime.now(UTC) - timedelta(hours=48)
    _write_marker(marker, stale.isoformat().replace("+00:00", "Z"))
    monkeypatch.setenv("ANTIEK_BACKUP_MARKER", str(marker))
    body = _client().get("/health").json()
    assert body["backup_fresh"] is False
    assert body["backup_age_hours"] is not None
    assert body["backup_age_hours"] > 26.0


def test_probe_backup_freshness_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_BACKUP_MARKER", str(tmp_path / "nope.json"))
    result = _probe_backup_freshness()
    assert result["backup_fresh"] is False
    assert result["backup_reason"]


def test_health_response_model_declares_backup_fields():
    from interfaces.research.api.app import HealthResponse

    for field in (
        "backup_fresh",
        "backup_completed_at",
        "backup_age_hours",
        "backup_marker_path",
        "backup_reason",
    ):
        assert field in HealthResponse.model_fields
    blank = HealthResponse(
        status="ok",
        param_version="0",
        schema_version=0,
        subscriber_count=0,
    )
    assert blank.backup_fresh is False
