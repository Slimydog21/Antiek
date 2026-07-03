"""Pytest-only guard: refuse writes that target the operator's real DuckDB file.

DOGFOOD SPR-04 sharpen — the autouse env redirect does not cover tests that
patch ``graph_db_path`` or pass a hardcoded ``~/.antiek/...`` into
``connect_write``. When ``PYTEST_CURRENT_TEST`` is set, every write open is
checked at the ``connect_write`` boundary (resolve-and-compare, same as the
conftest fixture).
"""

from __future__ import annotations

import os


def canonical_real_store_path() -> str:
    """Real operator graph DB, captured before autouse overrides when possible."""
    override = os.environ.get("ANTIEK_CANONICAL_REAL_DUCKDB")
    if override:
        return os.path.realpath(os.path.expanduser(override))
    return os.path.realpath(os.path.expanduser("~/.antiek/research_graph.duckdb"))


def real_operator_graph_db_path() -> str:
    """Alias used by tests/conftest (session canonical real store)."""
    return canonical_real_store_path()


def _guard_active() -> bool:
    return bool(
        os.environ.get("PYTEST_CURRENT_TEST")
        or os.environ.get("ANTIEK_ENFORCE_TEST_STORE_ISOLATION") == "1"
    )


def assert_write_path_not_real_store(db_path: str, *, purpose: str = "") -> None:
    """Called from ``connect_write`` — refuse real-store writes under pytest."""
    if not _guard_active():
        return
    if os.environ.get("ANTIEK_ALLOW_REAL_STORE_WRITE") == "1":
        return
    real = canonical_real_store_path()
    resolved = os.path.realpath(os.path.expanduser(str(db_path)))
    if resolved == real:
        tag = f" ({purpose})" if purpose else ""
        raise RuntimeError(
            "DOGFOOD SPR-04 write guard: connect_write refused the REAL store "
            f"({real}){tag} during pytest. Use a tmp ANTIEK_DUCKDB_PATH, inject "
            "a test connection, or mark @pytest.mark.real_store_read only for "
            "read-only real-store tests."
        )


assert_not_real_store_write = assert_write_path_not_real_store