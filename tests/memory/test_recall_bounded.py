"""The recall scan is bounded, and bounding it did not move the answer.

Two properties are under test and they pull against each other, which is why
both are here:

* **Bounded.** ``recall_memory`` must not materialise an owner's whole memory
  into Python to rank eight rows out of it. The assertion is on the *candidate
  cap*, not on the clock — a wall-clock-only test would go green on a machine
  that is merely fast and would flake on a machine that is merely busy, so it
  would measure nothing. The clock assertion here is a loose sanity check that
  rides along; the cap assertion is the gate.
* **Unmoved.** For any owner whose memory fits inside the cap the returned list
  must equal what the pre-cap implementation returned, element for element.
  ``_reference_recall_memory`` below is a verbatim copy of that implementation
  as it stood at ``origin/main`` ``9cd7692ab``, including its own private copy
  of the salience key, so this test pins the old answer rather than asking the
  new code to agree with itself.

The bounded test deliberately gives its lexical matches the *oldest*
``valid_from`` in the fixture. A cap that only pushed recency into SQL would
drop them outside the 200-row window and the match assertion would red; only a
cap that also pushes the lexical prefilter down keeps them.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from runtime.db_lock import LockedConnection, connect_write
from substrate.graph.schema import init_database_at_path
from substrate.memory import MemoryItem, list_memory, recall_memory
from substrate.memory._text import lexical_tokens
from substrate.memory.recall import RECALL_CANDIDATE_CAP

_OWNER = "user-bounded"
_OTHER_OWNER = "user-other"
_NOISE_ROWS = 10_000
_MATCH_TOKEN = "kakapo"

# The noise is recent; the three lexical matches are from 1999. Recency alone
# cannot pull them into a 200-row window out of 10,000.
_NOISE_EPOCH = datetime(2026, 1, 1, 0, 0)
_MATCH_EPOCH = datetime(1999, 3, 1, 0, 0)


# ---------------------------------------------------------------------------
# Pre-change implementation, copied verbatim from origin/main 9cd7692ab
# (substrate/memory/recall.py). Do not refactor it to share code with the
# module under test: its whole value is that it cannot drift with it.
# ---------------------------------------------------------------------------


def _reference_recall_memory(
    con: LockedConnection,
    owner_user_id: str,
    *,
    query: str | None = None,
    limit: int = 8,
) -> list[MemoryItem]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    if query is not None and not isinstance(query, str):
        raise TypeError("query must be a string or None")

    query_tokens = frozenset(lexical_tokens(query or ""))
    items = list_memory(con, owner_user_id)
    ranked = sorted(items, key=lambda item: (item.memory_id, item.edge_id))
    ranked.sort(
        key=lambda item: _reference_salience_key(item, query_tokens=query_tokens),
        reverse=True,
    )
    return ranked[:limit]


def _reference_salience_key(
    item: MemoryItem, *, query_tokens: frozenset[str]
) -> tuple[
    int,
    int,
    tuple[int, int, int, int, int, int, int],
    tuple[int, int, int, int, int, int, int],
]:
    item_tokens = frozenset(lexical_tokens(item.subject, item.predicate, item.object))
    overlap = len(item_tokens & query_tokens)
    specificity = -len(item_tokens - query_tokens) if overlap else 0
    return (
        overlap,
        specificity,
        _reference_date_key(item.valid_from),
        _reference_date_key(item.created_at),
    )


def _reference_date_key(value: datetime) -> tuple[int, int, int, int, int, int, int]:
    normalized = (
        value if value.tzinfo is None else value.astimezone(UTC).replace(tzinfo=None)
    )
    return (
        normalized.year,
        normalized.month,
        normalized.day,
        normalized.hour,
        normalized.minute,
        normalized.second,
        normalized.microsecond,
    )


# ---------------------------------------------------------------------------
# Row-count instrumentation
# ---------------------------------------------------------------------------


class _CountingResult:
    """Forwards a DuckDB result while recording how many rows Python takes."""

    def __init__(self, result: Any, counter: _RowCounter) -> None:
        self._result = result
        self._counter = counter

    def fetchall(self) -> list[Any]:
        rows = self._result.fetchall()
        self._counter.record(len(rows))
        return rows

    def __getattr__(self, name: str) -> Any:
        return getattr(self._result, name)


class _RowCounter:
    """Total and per-statement row counts pulled out of DuckDB into Python."""

    def __init__(self) -> None:
        self.total = 0
        self.largest = 0

    def record(self, count: int) -> None:
        self.total += count
        self.largest = max(self.largest, count)


def _instrument(con: LockedConnection) -> _RowCounter:
    """Count rows crossing the DuckDB boundary for the rest of this test.

    Patched on the instance, not the class, so it dies with the connection and
    cannot leak into a sibling test.
    """
    counter = _RowCounter()
    original = con.execute

    def counting_execute(
        sql: str, parameters: Sequence[Any] | None = None
    ) -> Any:
        return _CountingResult(original(sql, parameters), counter)

    con.execute = counting_execute  # type: ignore[method-assign]
    return counter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _memory_metadata(*, subject: str, predicate: str, object: str, ref: str) -> str:
    return json.dumps(
        {
            "schema": "antiek.account-memory.v1",
            "subject": subject,
            "predicate": predicate,
            "object": object,
            "provenance": {"event_id": ref, "source_tier": 1},
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _seed(
    con: LockedConnection,
    rows: Sequence[tuple[str, str, str, str, datetime]],
) -> None:
    """Bulk-insert memory triples as the graph projection stores them.

    Rows are written straight into ``nodes``/``edges`` rather than through
    ``write_memory_item`` because ten thousand transactional writes would turn
    a read-path test into a minutes-long write benchmark. The shapes match what
    ``write_memory_item`` produces for the columns ``list_memory`` reads.
    """
    subjects = {(owner, subject) for owner, subject, _, _, _ in rows}
    con.execute("BEGIN")
    try:
        con.executemany(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, "
            "metadata, owner_user_id) VALUES (?, ?, 'entity', 'depth', ?, ?)",
            [
                (
                    f"seed-subject-{owner}-{subject}",
                    subject,
                    '{"schema":"antiek.account-memory.v1","role":"subject"}',
                    owner,
                )
                for owner, subject in sorted(subjects)
            ],
        )
        con.executemany(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, "
            "metadata, owner_user_id) VALUES (?, ?, 'memory', 'depth', ?, ?)",
            [
                (
                    f"seed-memory-{ref}",
                    object,
                    _memory_metadata(
                        subject=subject, predicate=predicate, object=object, ref=ref
                    ),
                    owner,
                )
                for owner, subject, predicate, object, _ in rows
                for ref in [_ref(owner, subject, predicate, object)]
            ],
        )
        con.executemany(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "source_tier, extraction_confidence, extracted_at, valid_from, "
            "graph_scope, owner_user_id) "
            "VALUES (?, ?, ?, ?, 1, 1.0, ?, ?, 'depth', ?)",
            [
                (
                    f"seed-edge-{_ref(owner, subject, predicate, object)}",
                    f"seed-subject-{owner}-{subject}",
                    f"seed-memory-{_ref(owner, subject, predicate, object)}",
                    predicate,
                    valid_from,
                    valid_from,
                    owner,
                )
                for owner, subject, predicate, object, valid_from in rows
            ],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def _ref(owner: str, subject: str, predicate: str, object: str) -> str:
    return f"{owner}--{subject}--{predicate}--{object}"


def _large_rows() -> list[tuple[str, str, str, str, datetime]]:
    rows: list[tuple[str, str, str, str, datetime]] = [
        (
            _OWNER,
            f"topic-{index % 10:02d}",
            f"prefers-{index % 7}",
            f"noise value {index:05d}",
            _NOISE_EPOCH + timedelta(minutes=index),
        )
        for index in range(_NOISE_ROWS)
    ]
    rows.extend(
        (
            _OWNER,
            "conservation",
            "notes",
            f"{_MATCH_TOKEN} roost site {index}",
            _MATCH_EPOCH + timedelta(minutes=index),
        )
        for index in range(3)
    )
    # A second owner's rows must never appear; owner scoping is not this task's
    # subject but a cap that leaked across owners would be a worse bug than the
    # scan it replaces.
    rows.extend(
        (
            _OTHER_OWNER,
            "conservation",
            "notes",
            f"{_MATCH_TOKEN} other owner {index}",
            _MATCH_EPOCH + timedelta(minutes=index),
        )
        for index in range(5)
    )
    return rows


@pytest.fixture(scope="module")
def large_db(tmp_path_factory: pytest.TempPathFactory) -> str:
    db_path = str(tmp_path_factory.mktemp("recall-bounded") / "large.duckdb")
    init_database_at_path(db_path)
    con = connect_write(db_path, purpose="test-recall-bounded-seed")
    try:
        _seed(con, _large_rows())
    finally:
        con.close()
    return db_path


@pytest.fixture
def large_con(large_db: str) -> LockedConnection:
    con = connect_write(large_db, purpose="test-recall-bounded")
    try:
        yield con
    finally:
        con.close()


@pytest.fixture
def small_con(tmp_path: Path) -> LockedConnection:
    db_path = str(tmp_path / "small.duckdb")
    init_database_at_path(db_path)
    con = connect_write(db_path, purpose="test-recall-small")
    try:
        _seed(con, _small_rows())
        yield con
    finally:
        con.close()


def _small_rows() -> list[tuple[str, str, str, str, datetime]]:
    """Twenty rows, deliberately awkward: only five distinct timestamps so the
    identity tie-break actually decides the order, and heavily overlapping
    vocabulary so several rows land on the same lexical score."""
    vocabulary = [
        "prefers the vim editor",
        "prefers the emacs editor",
        "reads long form essays",
        "reads short technical notes",
        "writes in the morning",
        "writes long editor macros",
        "uses a standing desk",
        "uses vim keybindings everywhere",
        "avoids meetings before noon",
        "avoids long email threads",
    ]
    rows: list[tuple[str, str, str, str, datetime]] = []
    for index in range(20):
        rows.append(
            (
                _OWNER,
                f"operator-{index % 4}",
                f"habit-{index % 3}",
                f"{vocabulary[index % len(vocabulary)]} {index:02d}",
                datetime(2026, 5, 1, 9, 0) + timedelta(days=index % 5),
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_recall_materialises_at_most_the_candidate_cap(
    large_con: LockedConnection,
) -> None:
    """Ten thousand memories, at most ``RECALL_CANDIDATE_CAP`` rows in Python."""
    assert (
        large_con.execute(
            "SELECT count(*) FROM edges WHERE owner_user_id = ?", [_OWNER]
        ).fetchone()[0]
        == _NOISE_ROWS + 3
    )

    counter = _instrument(large_con)
    started = time.monotonic()
    items = recall_memory(large_con, _OWNER, query=_MATCH_TOKEN)
    elapsed = time.monotonic() - started

    assert counter.largest <= RECALL_CANDIDATE_CAP, (
        f"one statement handed {counter.largest} rows to Python; the cap is "
        f"{RECALL_CANDIDATE_CAP}"
    )
    assert counter.total <= RECALL_CANDIDATE_CAP, (
        f"recall materialised {counter.total} rows against a "
        f"{RECALL_CANDIDATE_CAP}-row cap"
    )
    assert len(items) == 8
    # Loose, and loose on purpose: the gate above is the cap, this only catches
    # an implementation that is bounded on paper and pathological in practice.
    assert elapsed < 10.0


def test_recall_keeps_old_lexical_matches_inside_the_cap(
    large_con: LockedConnection,
) -> None:
    """The prefilter, not recency, is what pulls the answer into the window."""
    items = recall_memory(large_con, _OWNER, query=_MATCH_TOKEN)

    matched = [item for item in items if _MATCH_TOKEN in item.object]
    assert len(matched) == 3, (
        "the three 1999 matches are the oldest rows in a 10,003-row owner; a "
        "recency-only cap loses them"
    )
    assert [item.object for item in items[:3]] == [item.object for item in matched]
    assert all(item.owner_user_id == _OWNER for item in items)


def test_recall_matches_the_pre_change_implementation_on_a_small_fixture(
    small_con: LockedConnection,
) -> None:
    """Twenty rows sit under the cap, so the answer must not have moved."""
    assert (
        small_con.execute(
            "SELECT count(*) FROM edges WHERE owner_user_id = ?", [_OWNER]
        ).fetchone()[0]
        == 20
    )

    queries = [
        None,
        "",
        "   ",
        "editor",
        "vim editor",
        "long",
        "writes long editor macros",
        "nothing here matches anything",
    ]
    for query in queries:
        for limit in (1, 8, 20, 50):
            expected = _reference_recall_memory(
                small_con, _OWNER, query=query, limit=limit
            )
            actual = recall_memory(small_con, _OWNER, query=query, limit=limit)
            assert actual == expected, f"query={query!r} limit={limit}"
            assert [item.edge_id for item in actual] == [
                item.edge_id for item in expected
            ], f"order moved for query={query!r} limit={limit}"


def test_list_memory_lexical_rank_ranks_without_filtering(
    small_con: LockedConnection,
) -> None:
    """``lexical_rank`` reorders candidates; it never drops one."""
    unranked = list_memory(small_con, _OWNER)
    ranked = list_memory(small_con, _OWNER, lexical_rank=["vim"])

    assert {item.edge_id for item in ranked} == {item.edge_id for item in unranked}
    assert len(ranked) == len(unranked) == 20
    assert "vim" in ranked[0].object

    bounded = list_memory(small_con, _OWNER, lexical_rank=["vim"], limit=2)
    assert len(bounded) == 2
    assert all("vim" in item.object for item in bounded)
