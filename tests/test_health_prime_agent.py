"""SPR-01 Task 6: the Prime lane is visible in ``/health``.

Prod ``/health`` exposed DuckDB, turbopuffer and provider readiness and said
nothing about Prime or RLM, so an operator could "activate" the lane and have
it silently do nothing — the failure mode that produced BUILT_NOT_CONNECTED.
These tests pin four fields: ``prime_agent_enabled``, ``rlm_ratified``,
``prime_agent_binary_present`` (resolve only, never spawn — a missing binary
must read ``false``, not raise) and ``prime_agent_invocations_attempted``.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

_PRIME_FIELDS = (
    "prime_agent_enabled",
    "rlm_ratified",
    "prime_agent_binary_present",
    "prime_agent_invocations_attempted",
)


def _app(tmp_path, monkeypatch):
    from interfaces.research.api.app import create_app
    from substrate.graph.schema import init_database_at_path

    db_path = tmp_path / "graph.duckdb"
    init_database_at_path(str(db_path))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db_path))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    return create_app(register_wrestling=False, register_providers=False, cors_origins=[])


def _prime_subset(body: dict) -> dict:
    return {key: body.get(key, "<absent>") for key in _PRIME_FIELDS}


def test_health_reports_the_prime_lane_with_no_binary_installed(tmp_path, monkeypatch):
    """No flags, no binary: every boolean false, the counter an int, nothing raised."""
    monkeypatch.delenv("ANTIEK_PRIME_AGENT_RLM_ENABLED", raising=False)
    monkeypatch.delenv("ANTIEK_RLM_RATIFIED", raising=False)
    # An absolute path that does not exist, so the developer's PATH cannot
    # make this pass by accident.
    monkeypatch.setenv("ANTIEK_PRIME_AGENT_BIN", str(tmp_path / "no-such-prime-agent"))

    body = TestClient(_app(tmp_path, monkeypatch)).get("/health").json()
    subset = _prime_subset(body)
    print("prime subset:", json.dumps(subset))
    print("registered_providers:", body["registered_providers"])

    assert subset["prime_agent_binary_present"] is False
    assert subset["prime_agent_enabled"] is False
    assert subset["rlm_ratified"] is False
    assert isinstance(subset["prime_agent_invocations_attempted"], int)
    assert "prime_agent" not in body["registered_providers"]


def test_health_lists_prime_agent_once_the_flag_registers_it(tmp_path, monkeypatch):
    """Task 4's registration must surface through the same app.state channel
    the startup pass uses, and the flag fields must read true."""
    from substrate.dispatch.providers.bootstrap import register_default_providers
    from substrate.dispatch.router import reset_provider_registry

    monkeypatch.setenv("ANTIEK_PRIME_AGENT_RLM_ENABLED", "1")
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    monkeypatch.setenv("ANTIEK_PRIME_AGENT_BIN", str(tmp_path / "no-such-prime-agent"))

    app = _app(tmp_path, monkeypatch)
    reset_provider_registry()
    try:
        # What create_app(register_providers=True) does, minus the .env load
        # that would pull the operator's real keys into a unit test.
        app.state.registered_providers = register_default_providers(quiet=True)
        body = TestClient(app).get("/health").json()
    finally:
        reset_provider_registry()

    subset = _prime_subset(body)
    print("prime subset:", json.dumps(subset))
    print("registered_providers:", body["registered_providers"])

    assert "prime_agent" in body["registered_providers"]
    assert subset["prime_agent_enabled"] is True
    assert subset["rlm_ratified"] is True
    assert subset["prime_agent_binary_present"] is False


def test_health_reports_a_present_binary_without_spawning_it(tmp_path, monkeypatch):
    """Presence is a resolve, not a run: a stand-in that logs every exec must
    stay unexecuted across the /health call."""
    witness = tmp_path / "witness.log"
    binary = tmp_path / "prime-agent"
    binary.write_text(f"#!/bin/sh\necho ran >> '{witness}'\necho prime-agent 0.9.4\n")
    binary.chmod(0o700)
    monkeypatch.setenv("ANTIEK_PRIME_AGENT_BIN", str(binary))

    body = TestClient(_app(tmp_path, monkeypatch)).get("/health").json()

    assert body["prime_agent_binary_present"] is True
    assert not witness.exists(), "/health spawned the binary"


def test_health_counts_prime_invocations_attempted(tmp_path, monkeypatch):
    """Every backend run() that reaches the spawn path bumps the counter, whether
    or not a binary resolves; /health reads the process-wide count."""
    from orchestration.rlm.prime_agent_backend import (
        PrimeAgentRequest,
        PrimeAgentRLMBackend,
        PrimeAgentTerminalState,
    )

    client = TestClient(_app(tmp_path, monkeypatch))
    before = client.get("/health").json()["prime_agent_invocations_attempted"]

    backend = PrimeAgentRLMBackend(
        enabled=True, executable="absent-prime", cwd=tmp_path, environ={}
    )
    for i in range(2):
        outcome = backend.run(
            PrimeAgentRequest(prompt="p", workflow="health-test", request_id=f"r{i}")
        )
        assert outcome.receipt.state is PrimeAgentTerminalState.UNAVAILABLE
    # A disabled backend never reaches the spawn path and must not count.
    PrimeAgentRLMBackend(enabled=False, cwd=tmp_path, environ={}).run(
        PrimeAgentRequest(prompt="p", workflow="health-test", request_id="off")
    )

    after = client.get("/health").json()["prime_agent_invocations_attempted"]
    print(f"prime_agent_invocations_attempted: {before} -> {after}")
    assert after == before + 2
