"""Regression tests for init_database_at_path schema fast-path guard."""

from __future__ import annotations

import os
import sys
import tempfile

import duckdb

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)  # noqa: E402

from substrate.graph import schema as schema_mod  # noqa: E402
from substrate.graph.schema import (  # noqa: E402
    _schema_is_present,
    init_database_at_path,
)


def test_schema_is_present_false_before_init():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "absent.duckdb")
        assert _schema_is_present(p) is False


def test_schema_is_present_true_after_init():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "graph.duckdb")
        init_database_at_path(p)
        assert _schema_is_present(p) is True


def test_warm_init_skips_write_lock(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "graph.duckdb")
        init_database_at_path(p)

        def _forbidden(*_a, **_kw):
            raise AssertionError("connect_write must NOT be called on the warm path")

        monkeypatch.setattr(schema_mod, "connect_write", _forbidden)
        assert init_database_at_path(p) is None


def test_cold_init_calls_connect_write(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "graph.duckdb")
        real = schema_mod.connect_write
        called: list[bool] = []

        def tracking(*a, **kw):
            called.append(True)
            return real(*a, **kw)

        monkeypatch.setattr(schema_mod, "connect_write", tracking)
        init_database_at_path(p)
        assert called


def test_init_is_idempotent_after_fast_path():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "graph.duckdb")
        init_database_at_path(p)
        init_database_at_path(p)
        con = duckdb.connect(p, read_only=True)
        try:
            row = con.execute("SELECT count(*) FROM nodes").fetchone()
        finally:
            con.close()
        assert row is not None and row[0] == 0