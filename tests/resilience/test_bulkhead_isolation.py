"""nygard SPR-05 — bulkhead isolation at --workers 1.

The single-writer funnel (runtime/db_lock) serializes every graph write. The
bulkhead invariant: one investigation's seam fault must NOT stall the funnel or
its siblings. Because ``connect_write`` releases its flock on EVERY exit path
(LockedConnection.__exit__ try/finally), an investigation that faults mid-write
frees the funnel immediately, so a sibling investigation's write still completes.

These prove that property directly — including when the fault is a real injected
seam fault (SPR-01's provider_fault) raised while investigation A holds the lock.
"""

from __future__ import annotations

import pytest

from runtime.db_lock import connect_read, connect_write, is_locked


def test_investigation_fault_releases_funnel_so_sibling_writes(tmp_path):
    db = str(tmp_path / "graph.duckdb")

    class _InvestigationAFault(RuntimeError):
        pass

    # Investigation A acquires the write lock, starts a write, then faults.
    with (
        pytest.raises(_InvestigationAFault),
        connect_write(db, timeout_s=5, purpose="investigation-A") as con_a,
    ):
        con_a.execute("CREATE TABLE IF NOT EXISTS t (x INTEGER)")
        raise _InvestigationAFault("A seam fault mid-write")

    # A's fault released the funnel — no orphaned lock.
    assert is_locked(db) is False

    # Investigation B (the sibling) writes successfully afterwards.
    with connect_write(db, timeout_s=5, purpose="investigation-B") as con_b:
        con_b.execute("INSERT INTO t VALUES (1)")

    con = connect_read(db)
    try:
        assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 1
    finally:
        con.close()


def test_injected_seam_fault_in_A_does_not_stall_sibling_B(tmp_path):
    """A real injected seam fault (SPR-01 provider_fault) raised while
    investigation A holds the write lock still releases the funnel for B."""
    from substrate.dispatch.base import ProviderError
    from substrate.dispatch.router import (
        register_provider,
        reset_provider_registry,
    )
    from tools.faultinject import provider_fault

    reset_provider_registry()

    class _Stub:
        name = "seam"

        def call(self, *, model, prompt, max_tokens, temperature):
            return {"ok": True}

        def normalize_usage(self, raw_usage):
            from substrate.dispatch.base import NormalizedUsage

            return NormalizedUsage(input_tokens=0, output_tokens=0)

    register_provider(_Stub())
    db = str(tmp_path / "graph.duckdb")
    try:
        with (
            pytest.raises(ProviderError),
            connect_write(db, timeout_s=5, purpose="investigation-A") as con_a,
        ):
            con_a.execute("CREATE TABLE IF NOT EXISTS t (x INTEGER)")
            # A dispatches during its write; the provider faults (503).
            with provider_fault(kind="503", provider="seam"):
                from substrate.dispatch.router import get_provider

                get_provider("seam").call(
                    model="m", prompt="p", max_tokens=8, temperature=0.0
                )
        # The seam fault propagated out of A's write block; the funnel is free.
        assert is_locked(db) is False
        with connect_write(db, timeout_s=5, purpose="investigation-B") as con_b:
            con_b.execute("INSERT INTO t VALUES (1)")
        con = connect_read(db)
        try:
            assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 1
        finally:
            con.close()
    finally:
        reset_provider_registry()
