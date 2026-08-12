"""Tests for tools.arxiv_verify — the arXiv acquisition health verifier.

NO live network: endpoint checks are mocked via urllib monkeypatching.
State-file checks use tmp_path; DuckDB checks use a per-test tmp DB.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
from pathlib import Path

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from tools.arxiv_verify import (
    Check,
    Verdict,
    _check_coverage,
    _check_census_json,
    _check_endpoint_health,
    _check_rate_governor,
    _check_sync_state,
    run_checks,
)


# ── Fixtures ──

@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """Point all state files at tmp_path so tests never touch real state."""
    monkeypatch.setenv("ANTIEK_ARXIV_THROTTLE_PATH", str(tmp_path / "throttle.json"))
    monkeypatch.setenv("ANTIEK_ARXIV_OAI_STATE_PATH", str(tmp_path / "harvest.json"))
    monkeypatch.setenv("ANTIEK_ARXIV_OAI_SYNC_PATH", str(tmp_path / "sync.json"))
    monkeypatch.setenv("ANTIEK_ARXIV_GOVERNOR_LOCK_PATH", str(tmp_path / "gov.lock"))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "antiek.duckdb"))
    monkeypatch.setenv("ANTIEK_STATE_DIR", str(tmp_path))
    return tmp_path


# ── Endpoint health ──

def test_endpoint_health_passes_on_valid_identify(tmp_path, monkeypatch):
    """A valid OAI-PMH Identify response should pass."""
    identify_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
  <responseDate>2026-08-12T00:00:00Z</responseDate>
  <Identify>
    <repositoryName>arXiv OAI-PMH</repositoryName>
    <baseURL>https://oaipmh.arxiv.org/oai</baseURL>
    <protocolVersion>2.0</protocolVersion>
  </Identify>
</OAI-PMH>"""

    class FakeResponse:
        def __init__(self, data):
            self._data = data
        def read(self):
            return self._data
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    def fake_urlopen(req, timeout=None):
        return FakeResponse(identify_xml)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = _check_endpoint_health("https://oaipmh.arxiv.org/oai")
    assert result.passed
    assert "arXiv OAI-PMH" in result.detail


def test_endpoint_health_fails_on_http_error(monkeypatch):
    """A 403/503 should fail."""
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(str(req.full_url), 403, "Forbidden", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = _check_endpoint_health("https://oaipmh.arxiv.org/oai")
    assert not result.passed
    assert "403" in result.detail


def test_endpoint_health_fails_on_timeout(monkeypatch):
    """A timeout should fail."""
    def fake_urlopen(req, timeout=None):
        raise TimeoutError("connection timed out")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = _check_endpoint_health("https://oaipmh.arxiv.org/oai")
    assert not result.passed
    assert "timed out" in result.detail.lower()


# ── Rate governor ──

def test_rate_governor_passes_when_spacing_adequate(tmp_path):
    """MIN_REQUEST_SPACING_S >= 3.0 should pass."""
    result = _check_rate_governor()
    assert result.passed
    assert "spacing=" in result.detail


def test_rate_governor_reports_banned_state(tmp_path):
    """A banned_until timestamp in the future should still pass (governor is
    doing its job) but report the ban in detail."""
    path = Path(os.environ["ANTIEK_ARXIV_THROTTLE_PATH"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "last_request_at": time.time() - 10,
        "banned_until": time.time() + 1800,
    }))
    result = _check_rate_governor()
    assert result.passed  # governor is working correctly
    assert "BANNED" in result.detail


# ── Sync state ──

def test_sync_state_passes_when_absent(tmp_path):
    """No checkpoint files = first run; should pass."""
    result = _check_sync_state()
    assert result.passed
    assert "absent" in result.detail


def test_sync_state_passes_with_valid_checkpoint(tmp_path):
    """A valid checkpoint with datestamp should pass."""
    path = Path(os.environ["ANTIEK_ARXIV_OAI_SYNC_PATH"])
    path.write_text(json.dumps({
        "last_successful_datestamp": "2024-06-15",
        "last_harvested_at": "2026-08-12T04:20:00+00:00",
    }))
    result = _check_sync_state()
    assert result.passed
    assert "sync_hwm=2024-06-15" in result.detail


def test_sync_state_fails_with_null_datestamp(tmp_path):
    """Checkpoint exists but datestamp is null = incomplete run."""
    path = Path(os.environ["ANTIEK_ARXIV_OAI_SYNC_PATH"])
    path.write_text(json.dumps({
        "last_successful_datestamp": None,
        "last_harvested_at": "2026-08-12T04:20:00+00:00",
    }))
    result = _check_sync_state()
    assert not result.passed
    assert "null" in result.detail.lower()


def test_sync_state_reports_pending_harvest_cursor(tmp_path):
    """A harvest cursor with a pending token = interrupted harvest."""
    path = Path(os.environ["ANTIEK_ARXIV_OAI_STATE_PATH"])
    path.write_text(json.dumps({
        "resumption_token": "SOME_TOKEN_123",
        "last_datestamp": "2024-06-10",
    }))
    result = _check_sync_state()
    assert result.passed  # not a failure, just info
    assert "pending token" in result.detail


# ── Census JSON ──

def test_census_json_passes_when_absent(tmp_path):
    """No census file = not a failure."""
    result = _check_census_json()
    assert result.passed
    assert "not present" in result.detail


def test_census_json_passes_with_valid_data(tmp_path):
    """Valid census data should pass."""
    census_dir = Path(os.environ["ANTIEK_STATE_DIR"]) / "reports"
    census_dir.mkdir(parents=True, exist_ok=True)
    (census_dir / "arxiv_oai_census.json").write_text(json.dumps({
        "total": 2500000,
        "t1": 500000,
        "t2": 200000,
        "t3": 1800000,
        "harvested_at": "2026-08-12T04:30:00+00:00",
        "high_water_datestamp": "2024-06-15",
    }))
    result = _check_census_json()
    assert result.passed
    assert "total=2500000" in result.detail


def test_census_json_fails_with_missing_keys(tmp_path):
    """Missing required keys should fail."""
    census_dir = Path(os.environ["ANTIEK_STATE_DIR"]) / "reports"
    census_dir.mkdir(parents=True, exist_ok=True)
    (census_dir / "arxiv_oai_census.json").write_text(json.dumps({
        "total": 2500000,
    }))
    result = _check_census_json()
    assert not result.passed
    assert "missing" in result.detail.lower()


# ── Coverage ──

def test_coverage_passes_when_no_db(tmp_path):
    """No DuckDB file should pass (skipped)."""
    result = _check_coverage(str(tmp_path / "nonexistent.duckdb"))
    assert result.passed
    assert "not present" in result.detail


def test_coverage_passes_with_arxiv_docs(tmp_path):
    """A DuckDB with arXiv documents should pass and report count."""
    db_path = str(tmp_path / "antiek.duckdb")
    import duckdb
    con = duckdb.connect(db_path)
    con.execute("""
        CREATE TABLE documents (
            document_id VARCHAR,
            title VARCHAR,
            content_class VARCHAR,
            metadata VARCHAR
        )
    """)
    con.execute(
        "INSERT INTO documents VALUES ('doc-arxiv-2401.0001', 'Test Paper', 'restricted_pending_opt_in', '{}')"
    )
    con.execute(
        "INSERT INTO documents VALUES ('doc-arxiv-2401.0002', 'Another Paper', 'restricted_pending_opt_in', '{}')"
    )
    con.execute(
        "INSERT INTO documents VALUES ('doc-other-123', 'Non-arxiv', 'public_domain', '{}')"
    )
    con.close()
    result = _check_coverage(db_path)
    assert result.passed
    assert "2" in result.detail
    assert result.value == 2


# ── Full verdict ──

def test_run_checks_produces_verdict(tmp_path, monkeypatch):
    """run_checks should produce a structured Verdict."""
    # Mock the endpoint check to avoid network
    def fake_urlopen(req, timeout=None):
        class FakeResp:
            def read(self):
                return b'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><Identify><repositoryName>Test</repositoryName></Identify></OAI-PMH>'
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    v = run_checks(base_url="https://oaipmh.arxiv.org/oai", db_path=None)
    assert isinstance(v, Verdict)
    assert v.ok
    assert v.timestamp
    assert len(v.checks) == 5
    d = v.to_dict()
    assert d["ok"] is True
    assert isinstance(d["checks"], list)


def test_verdict_fails_when_endpoint_down(tmp_path, monkeypatch):
    """If endpoint is down, verdict should fail."""
    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    v = run_checks(base_url="https://oaipmh.arxiv.org/oai", db_path=None)
    assert not v.ok
    assert any(not c.passed and c.name == "endpoint_health" for c in v.checks)


# ── CLI --help ──

def test_cli_help(capsys):
    """--help should not raise."""
    from tools.arxiv_verify import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
