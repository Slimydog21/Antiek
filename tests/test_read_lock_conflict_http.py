"""Cross-process DuckDB read-open conflicts must surface as 503, never 500.

Reproduces the measured production state (read-open audit, 2026-10-01):
another PROCESS holds the DuckDB file via a plain ``duckdb.connect(path)``
— no application flock, exactly what an unflocked substrate or an operator
CLI does — while the API tries to open it read-only through
``runtime.db_lock.connect_read``. Before the typed-error fix the raw
``duckdb.IOException`` escaped every route as an uncaught HTTP 500
(6,793 x 500 / 24h on the busiest path); after it, the ONE app-level
``ReadLockTimeout`` handler maps the conflict to 503 + ``Retry-After`` for
every route without per-route edits.

Three representative routes from three different modules: the measured
ad-impressions path, the books corpus path, and the library catalog path.
``raise_server_exceptions=False`` keeps the test on the HTTP contract: an
unhandled exception must be OBSERVED as a 500 response, not raised.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

# (method, url, json-body) triples — one route per module under test.
# ad_impressions.py post_select_ad is the audited busiest path; books.py
# list_books and library.py list_library are plain GET readers.
ROUTES_UNDER_TEST = (
    ("POST", "/ad-inventory/select", {}),
    ("GET", "/books", None),
    ("GET", "/library", None),
)

_HOLDER_CODE = """
import sys
import time

import duckdb

con = duckdb.connect(sys.argv[1])  # plain RW open: holds the file lock
print("held", flush=True)
time.sleep(300)
"""


@pytest.fixture()
def held_db(monkeypatch: pytest.MonkeyPatch):
    """A fully initialized DB whose file is held by ANOTHER PROCESS."""
    tmpdir = tempfile.mkdtemp(prefix="antiek-read-lock-503-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    # Scrub operator-auth env so the middleware runs in its CI shape
    # (enforcement bypassed, default local operator identity). An operator
    # shell that exports ANTIEK_OPERATOR_TOKEN would otherwise 401 every
    # request before the DB is ever opened.
    for var in (
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_OPERATOR_EMAIL",
        "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
    ):
        monkeypatch.delenv(var, raising=False)

    from runtime.db_lock import flush_warm_writers
    from substrate.graph import ensure_initialized

    ensure_initialized(db_path)
    # Park the warm RW handle from init so the subprocess can take the file.
    flush_warm_writers(db_path)

    holder = subprocess.Popen(
        [sys.executable, "-c", _HOLDER_CODE, db_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # The holder announces itself only after duckdb.connect succeeded,
        # so the cross-process lock conflict is guaranteed from here on.
        assert holder.stdout is not None
        announced = holder.stdout.readline().strip()
        assert announced == "held", f"holder subprocess failed: {announced!r}"
        yield db_path
    finally:
        holder.terminate()
        try:
            holder.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover — defensive
            holder.kill()
            holder.wait(timeout=10)
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_read_lock_conflict_is_503_with_retry_after(held_db: str) -> None:
    """A subprocess-held DuckDB file must 503 every read route, never 500."""
    from interfaces.research.api.app import create_app

    client = TestClient(
        create_app(register_wrestling=False, register_providers=False),
        raise_server_exceptions=False,
    )
    for method, url, body in ROUTES_UNDER_TEST:
        response = client.request(method, url, json=body)
        assert response.status_code != 500, (
            f"{method} {url} returned 500 under a cross-process read-lock "
            "conflict — the raw duckdb.IOException escaped the route"
        )
        assert response.status_code == 503, (
            f"{method} {url} returned {response.status_code}; the app-level "
            "ReadLockTimeout handler must own this conflict"
        )
        retry_after = response.headers.get("Retry-After")
        assert retry_after is not None and retry_after.isdigit(), (
            f"{method} {url} 503 is missing an integer Retry-After header"
        )
