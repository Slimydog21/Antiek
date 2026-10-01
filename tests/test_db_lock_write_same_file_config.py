"""A retry exhausted on the same-file/different-config error must be retryable.

`_connect_write_after_process_gate` retries TWO transient open failures until
its deadline: the external DuckDB file lock (`_external_duckdb_lock_conflict`)
and DuckDB's "same database file with a different configuration" rejection
(`_SAME_FILE_DIFFERENT_CONFIG`). The deadline handler translated only the
first, so an exhausted same-file retry re-raised the raw
`duckdb.ConnectionException`.

Callers catch `WriteLockTimeout` and map it to a retryable 503 with
`Retry-After` -- `interfaces/research/api/ad_routes.py` does exactly that for
`POST /api/ad/frame-telemetry`. A raw `ConnectionException` matches none of
those handlers and becomes a 500.

Measured on the live box 2026-10-01, release 4fc53a43b, over 60 minutes: 464
requests to that route, 169 of them 500, every one ending in

    _duckdb.ConnectionException: Connection Error: Can't open a connection to
    same database file with a different configuration than existing connections

The second test is the negative control: a non-retryable open error must still
propagate unchanged, because the fix widens which errors become
`WriteLockTimeout`.
"""

from __future__ import annotations

import duckdb
import pytest

from runtime import db_lock
from runtime.db_lock import WriteLockTimeout, connect_write


def _always(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    def open_failing(
        _path: str, *args: object, **kwargs: object
    ) -> duckdb.DuckDBPyConnection:
        raise error

    monkeypatch.setattr(duckdb, "connect", open_failing)


def test_exhausted_same_file_config_retry_is_a_writelocktimeout(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The retry condition that was not translated."""
    _always(
        monkeypatch,
        duckdb.ConnectionException(
            f"Connection Error: {db_lock._SAME_FILE_DIFFERENT_CONFIG}"
        ),
    )
    with pytest.raises(WriteLockTimeout):
        connect_write(
            str(tmp_path / "same-file.duckdb"),
            timeout_s=0.05,
            poll_interval_s=0.01,
            purpose="test:same-file-config",
        )


def test_unrelated_open_error_still_propagates_raw(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: widening the translation must not swallow this."""
    _always(monkeypatch, duckdb.ConnectionException("unrelated open failure"))
    with pytest.raises(duckdb.ConnectionException, match="unrelated open failure"):
        connect_write(
            str(tmp_path / "unrelated.duckdb"),
            timeout_s=0.05,
            poll_interval_s=0.01,
            purpose="test:unrelated",
        )
