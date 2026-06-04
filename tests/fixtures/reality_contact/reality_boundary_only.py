"""Fixture: imports a CORE subsystem, mocks ONLY a boundary (httpx + clock).

The orchestrator is imported (claims to cover it) but the only thing mocked is
network egress (httpx) and the clock (time.sleep) — both legitimate boundary
seams. Verdict must be `reality`: the real orchestrator core runs.
"""

from unittest.mock import patch

from orchestration.loop_one import orchestrator  # noqa: F401


@patch("httpx.AsyncClient.send")
def test_orchestrator_with_only_boundary_mocked(mock_send, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    assert orchestrator is not None
