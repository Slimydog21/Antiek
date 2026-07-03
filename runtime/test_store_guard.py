"""Test-run guard: block writes to the operator DuckDB store during pytest.

DOGFOOD SPR-04. Production code must not import from ``tests/``; this module
lives under ``runtime/`` and is invoked from ``connect_write`` when the autouse
conftest fixture sets ``ANTIEK_ENFORCE_TEST_STORE_ISOLATION=1``.
"""

from __future__ import annotations

import os


def real_operator_graph_db_path() -> str:
    return os.path.realpath(os.path.expanduser("~/.antiek/research_graph.duckdb"))


def assert_write_path_not_real_store(db_path: str, *, site: str = "connect_write") -> None:
    """Fail closed when pytest isolation is active and ``db_path`` is the real store."""
    if os.environ.get("ANTIEK_ENFORCE_TEST_STORE_ISOLATION") != "1":
        return
    real = real_operator_graph_db_path()
    resolved = os.path.realpath(os.path.expanduser(str(db_path)))
    if resolved == real:
        raise AssertionError(
            "DOGFOOD SPR-04 isolation guard: "
            f"{site} targeted the REAL store ({real}) — a substrate leak. "
            "Use a tmp ANTIEK_DUCKDB_PATH, or mark @pytest.mark.real_store_read "
            "only for intentional read-only real-store tests."
        )