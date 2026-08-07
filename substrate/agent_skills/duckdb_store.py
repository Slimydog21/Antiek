"""Skill 1 of 3 — ``duckdb_store``: ephemeral DuckDB store for mined data.

A research agent mines quantitative data and needs somewhere typed to put
it. This skill gives it a fresh, EPHEMERAL, IN-MEMORY DuckDB database —
create tables, insert rows, query back — returning structured, typed
rows. "Typed" here means a frozen ``QueryResult`` with declared column
names and tuple rows, not raw driver objects; the caller (or the agent's
kernel) can index ``columns`` and ``rows`` without touching DuckDB's
driver surface.

WHY IN-MEMORY, NEVER THE CORPUS DB: Antiek's DuckDB single-writer
invariant is absolute (``runtime/db_lock.py``; CLAUDE.md invariant 1 —
one writer process, ``--workers 1``). A skill that handed a research
agent a writer handle to the corpus graph would be a second-writer
violation waiting to happen. ``duckdb.connect()`` with no path creates a
database that exists only in memory and dies with the connection — it
cannot collide with the corpus DB, cannot be pointed at
``ANTIEK_DUCKDB_PATH`` by accident, and needs no file cleanup. An agent
that needs persistence past the store's lifetime exports the data it
mined (a later lane); the store itself is deliberately disposable.

BOUNDED BY CONTRACT: ``max_rows`` caps how many rows ``run_sql`` returns
(default 10,000 — the same ceiling the kernel-skills spec uses) and is
reported via ``QueryResult.truncated`` rather than silently truncating.
Parameters bind through DuckDB's native ``?`` placeholders, so mined
values containing quotes or semicolons cannot alter the query — the data
being mined is untrusted, and string-interpolated SQL would be a
miniature injection surface.

THE DRIVER'S ``Count`` CONVENTION IS SURFACED, NOT NORMALIZED AWAY:
DuckDB answers ``CREATE``/``INSERT``/``DELETE``/``UPDATE`` with a
pseudo-result whose single column is named ``Count`` — ``()`` rows for
DDL, ``((n,),)`` with the affected-row count for DML. ``run_sql``
returns that as-is: no heuristic strips it (a genuine
``SELECT Count FROM t`` is indistinguishable from the pseudo-result by
name alone), and the affected count is real information — an agent that
inserts mined rows can check how many landed.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Literal

import duckdb
from duckdb import DuckDBPyConnection

from substrate.agent_skills.manifest import SkillManifest

__all__ = ["DuckDBStore", "QueryResult", "close", "create_store", "run_sql"]


@dataclass(frozen=True)
class QueryResult:
    """Structured result of one ``run_sql`` call.

    Attributes
    ----------
    columns:
        Column names in result order. DDL/DML statements (``CREATE``,
        ``INSERT``, ``UPDATE``, ``DELETE``) come back with DuckDB's
        single ``Count`` pseudo-column: ``()`` rows for DDL, one
        ``(n,)`` row with the affected-row count for DML. Surfaced
        as-is — see the module docstring for why.
    rows:
        One tuple per row, values in ``columns`` order. Values are the
        driver's native Python objects (int/float/str/datetime/...).
    row_count:
        ``len(rows)``; convenience for the caller.
    truncated:
        True iff the result was capped at ``max_rows`` and more rows
        exist. Never silently truncate: the caller decides what to do.
    """

    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    row_count: int
    truncated: bool = False

    def as_dicts(self) -> tuple[dict[str, object], ...]:
        """Rows as column-name-keyed dicts, in result order."""
        return tuple(dict(zip(self.columns, row, strict=True)) for row in self.rows)


class DuckDBStore:
    """An open ephemeral DuckDB database.

    Created via :func:`create_store`; closed via :func:`close` (or
    ``store.close()``), which is idempotent. All SQL goes through
    :func:`run_sql`. The underlying connection is deliberately in-memory
    (see module docstring) and the class exposes no write-to-path
    surface at all — there is no ``connect(path)`` variant on purpose.
    """

    def __init__(self) -> None:
        self._con: DuckDBPyConnection | None = duckdb.connect()
        self._closed = False

    @property
    def is_closed(self) -> bool:
        """True once :meth:`close` has been called."""
        return self._closed

    def run_sql(
        self,
        query: str,
        *,
        params: tuple[object, ...] = (),
        max_rows: int = 10_000,
    ) -> QueryResult:
        """Execute ``query`` against this store. See :func:`run_sql`."""
        return run_sql(self, query, params=params, max_rows=max_rows)

    def close(self) -> None:
        """Close the connection; idempotent. Closing a closed store is a
        no-op, so teardown paths can call it unconditionally."""
        if not self._closed:
            assert self._con is not None
            self._con.close()
            self._con = None
            self._closed = True

    def __enter__(self) -> DuckDBStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        self.close()
        return False


def create_store() -> DuckDBStore:
    """Open a fresh ephemeral in-memory DuckDB store.

    No path, no file, no corpus access: the database exists only for the
    lifetime of the returned :class:`DuckDBStore` and vanishes on
    :func:`close`. Safe to call from any agent context — it cannot touch
    the single-writer corpus DB by construction.
    """
    return DuckDBStore()


def run_sql(
    store: DuckDBStore,
    query: str,
    *,
    params: tuple[object, ...] = (),
    max_rows: int = 10_000,
) -> QueryResult:
    """Run ``query`` on ``store`` and return structured rows.

    Parameters
    ----------
    store:
        An open store from :func:`create_store`.
    query:
        SQL to execute. Supports DuckDB's native ``?`` placeholders for
        bound parameters (preferred for any value that came from mined
        data — never interpolate untrusted values into the SQL string).
    params:
        Bound parameter values, in placeholder order.
    max_rows:
        Cap on returned rows; when the result exceeds it,
        ``QueryResult.truncated`` is True and the caller decides (raise,
        aggregate, page). Must be >= 1.

    Returns
    -------
    QueryResult
        Column names + rows for ``SELECT``; DuckDB's ``Count``
        pseudo-result for DDL/DML (``()`` rows for DDL, ``(n,)``
        affected count for DML) — surfaced, never normalized away.
        ``QueryResult.truncated`` reports a ``max_rows`` cap honestly.

    Raises
    ------
    ValueError
        If ``store`` is closed or ``max_rows`` < 1.
    duckdb.Error
        If ``query`` is invalid (propagated, loud — never swallowed).
    """
    if store.is_closed:
        raise ValueError("duckdb_store: store is closed")
    if max_rows < 1:
        raise ValueError(f"duckdb_store: max_rows must be >= 1, got {max_rows}")
    con = store._con
    assert con is not None  # is_closed guard above
    result = con.execute(query, list(params))
    description = result.description
    columns = tuple(str(d[0]) for d in description) if description else ()
    rows: list[tuple[object, ...]] = [tuple(r) for r in result.fetchmany(max_rows + 1)]
    truncated = len(rows) > max_rows
    if truncated:
        rows = rows[:max_rows]
    return QueryResult(
        columns=columns,
        rows=tuple(rows),
        row_count=len(rows),
        truncated=truncated,
    )


def close(store: DuckDBStore) -> None:
    """Close ``store`` (idempotent). Also available as ``store.close()``."""
    store.close()


MANIFEST = SkillManifest(
    name="duckdb_store",
    summary="Create an ephemeral in-memory DuckDB store, run SQL, get typed rows back.",
    description=(
        "Mining surface for quantitative data: create tables, insert rows, query — "
        "all through one bound, max_rows-capped runner. The store is in-memory and "
        "disposable by design: it never touches the corpus DuckDB, so the "
        "single-writer invariant is preserved regardless of what the agent does."
    ),
    entrypoint=create_store,
    functions=("create_store", "run_sql", "close"),
    parameters=(),
    returns=(
        "create_store -> DuckDBStore (open in-memory DB). run_sql -> QueryResult with "
        "columns: tuple[str, ...], rows: tuple[tuple[object, ...], ...], row_count, "
        "truncated, plus as_dicts()."
    ),
    safety=(
        "Ephemeral + in-memory: no path argument exists, so the store cannot collide "
        "with ANTIEK_DUCKDB_PATH or the corpus DB (single-writer invariant).",
        "max_rows caps result size and is reported via QueryResult.truncated, never "
        "silently dropped.",
        "SQL parameters bind through DuckDB placeholders; mined (untrusted) values "
        "must go through params, never string interpolation.",
    ),
    examples=(
        "store = create_store()",
        "run_sql(store, 'CREATE TABLE prices (sku VARCHAR, amount DOUBLE)')",
        "run_sql(store, 'INSERT INTO prices VALUES (?, ?)', params=('A1', 12.5))",
        "q = run_sql(store, 'SELECT sku, amount FROM prices ORDER BY amount DESC')",
        "q.columns; q.rows[0]; q.as_dicts()",
    ),
)
