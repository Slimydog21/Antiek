"""Run the usability keystone probe. It exists; nothing ran it.

`docs/decisions/usability-keystone.md` declared "INSTALLED (the probe IS the
definition) + verify-live WIRED" and cited this file as the self-test. This
file did not exist. Neither did the ansible verify-live task, the
`antiek_keystone_verify_live` variable, or the runbook — see the corrected
Status line in that record.

The PROBE, however, is real:
`tools/reachability/probes/usability_keystone.py` composes the five legs —
login, start a research, watch it compound, read the result, §9 attribution
intact — through the real `create_app()` factory. Its docstring states why it
exists: "The product shipped DEAD in prod precisely because every BRICK was
green while the JOURNEY was broken."

That is exactly what running it proved. On first execution it failed at
`app.py:3018` with

    ConnectionException: Can't open a connection to same database file with
    a different configuration than existing connections

because `get_chunk` used a raw `duckdb.connect(db_path, read_only=True)`
instead of `connect_read`. `db_lock.py:921` says not to do that, and gives
this precise reason: DuckDB refuses a read-only handle when the process
already holds the same file read-write, which under `--workers 1` is the
normal state. The handler caught only `IOException`, so it surfaced as a 500.

Every per-brick test passed while that journey was broken. The probe caught
it on its first run in the tree's history.
"""

from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch: pytest.MonkeyPatch) -> None:
    tmp = tempfile.mkdtemp(prefix="usability-keystone-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmp, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmp, "events"))


def test_usability_keystone_journey_is_reachable() -> None:
    from tools.reachability.probes import usability_keystone

    result = usability_keystone._probe()
    assert result.ok, (
        "the five-leg usability journey is broken: "
        f"{getattr(result, 'reason', '')!r} "
        f"(failure_mode={getattr(result, 'failure_mode', None)!r}). "
        "Each leg is a distinct observable outcome and the probe stops at the "
        "first failure, so the reason names the leg."
    )


def test_probe_reports_a_leg_rather_than_a_bare_failure() -> None:
    """Guard the guard.

    A probe that could only answer "failed" would satisfy the test above
    while telling nobody which leg broke. Assert the structured fields the
    probe promises are actually populated.
    """
    from tools.reachability.probes import usability_keystone

    result = usability_keystone._probe()
    assert hasattr(result, "ok")
    assert hasattr(result, "failure_mode")
    assert result.failure_mode, "probe returned an empty failure_mode"


def test_chunk_read_survives_an_open_write_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The deterministic form of what the probe hit.

    The probe's failure was STATE-dependent: it needed a read-write handle
    already open in the process. A fresh isolated DB has none, so a test that
    merely runs the probe passes whether or not the bug is present — I wrote
    that test first and its mutation proved it vacuous.

    This reproduces the condition directly: hold a read-write handle, as
    uvicorn does under `--workers 1`, then read a chunk. With raw
    `duckdb.connect(read_only=True)` that raises ConnectionException — which
    the handler does NOT catch, so it escapes as a 500.
    """
    import duckdb
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app
    from substrate.graph import default_db_path, ensure_initialized

    ensure_initialized(default_db_path())
    write_handle = duckdb.connect(default_db_path())   # the uvicorn steady state
    try:
        client = TestClient(create_app(register_wrestling=False), raise_server_exceptions=False)
        resp = client.get("/chunks/no-such-chunk")
        assert resp.status_code != 500, (
            "GET /chunks/{id} returned 500 while a read-write handle was open. "
            "A raw duckdb.connect(read_only=True) raises ConnectionException "
            "in that state; use connect_read (db_lock.py:921)."
        )
    finally:
        write_handle.close()
