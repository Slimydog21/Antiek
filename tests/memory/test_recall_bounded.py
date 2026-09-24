"""SPR-11 T5: recall reads a bounded candidate set; the ranking does not change.

``recall_memory`` sits on every thought-partner turn under the writer lock and
used to list the owner's entire current memory, sort it in Python and slice to
eight. The lexical prefilter and the recency order now live in the store's
query, so at most ``RECALL_CANDIDATE_CAP`` rows reach Python. The gate here is
the cap, asserted on the rows actually materialised; the wall-clock bound is
secondary because a timing-only test is a flaky non-gate.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import substrate.memory.recall as recall_module
from runtime.db_lock import LockedConnection, connect_write
from substrate.graph.schema import init_database_at_path
from substrate.memory import MemoryItem, list_memory, recall_memory, write_memory_item
from substrate.memory._text import lexical_tokens
from substrate.memory.recall import RECALL_CANDIDATE_CAP, _salience_key

_SCHEMA = "antiek.account-memory.v1"


@pytest.fixture
def memory_con(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LockedConnection:
    db_path = str(tmp_path / "recall-bounded.duckdb")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    init_database_at_path(db_path)
    con = connect_write(db_path, purpose="test-recall-bounded")
    try:
        yield con
    finally:
        con.close()


def _seed_bulk(
    con: LockedConnection, *, owner: str, count: int, objects: dict[int, str]
) -> None:
    """Insert ``count`` current memories for ``owner`` straight into nodes/edges.

    This is the exact shape ``list_memory``'s SELECT reads (a subject node, a
    ``memory`` node whose metadata carries the provenance, an owner-scoped edge).
    It bypasses ``write_memory_item`` because ten thousand writes through the
    transactional chokepoint take minutes and the query under test does not
    care how the rows got there; it is generated set-wise in SQL because
    DuckDB's ``executemany`` is per-row and took thirty seconds. Row ``i`` is
    valid from ``base + i`` minutes, so a higher index is newer, and its object
    is ``routine entry i`` unless ``objects`` overrides it.
    """
    subject_node = f"seed-subject-{owner}"
    con.execute(
        "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata, "
        "owner_user_id) VALUES (?, ?, 'entity', 'depth', ?, ?)",
        [subject_node, "operator", json.dumps({"schema": _SCHEMA, "role": "subject"}), owner],
    )
    con.execute(
        "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata, "
        "owner_user_id) "
        "SELECT 'seed-memory-' || ? || '-' || i, 'routine entry ' || i, 'memory', 'depth', "
        "'{\"schema\":\"' || ? || '\",\"subject\":\"operator\",\"predicate\":\"p' || i "
        "|| '\",\"object\":\"routine entry ' || i || '\",\"provenance\":{\"event_id\":"
        "\"seed-event-' || i || '\"}}', ? "
        "FROM range(?) t(i)",
        [owner, _SCHEMA, owner, count],
    )
    for index, obj in objects.items():
        metadata = {
            "schema": _SCHEMA,
            "subject": "operator",
            "predicate": f"p{index}",
            "object": obj,
            "provenance": {"event_id": f"seed-event-{index}"},
        }
        con.execute(
            "UPDATE nodes SET canonical_label = ?, metadata = ? WHERE node_id = ?",
            [obj, json.dumps(metadata), f"seed-memory-{owner}-{index}"],
        )
    con.execute(
        "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, source_tier, "
        "extraction_confidence, extracted_at, valid_from, graph_scope, metadata, owner_user_id) "
        "SELECT 'seed-edge-' || ? || '-' || i, ?, 'seed-memory-' || ? || '-' || i, 'p' || i, "
        "1, 1.0, TIMESTAMP '2026-01-01' + to_minutes(i::INTEGER), "
        "TIMESTAMP '2026-01-01' + to_minutes(i::INTEGER), 'depth', ?, ? "
        "FROM range(?) t(i)",
        [owner, subject_node, owner, json.dumps({"schema": _SCHEMA}), owner, count],
    )


def _count_materialised(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Record how many rows each store call hands back to recall."""
    seen: list[int] = []
    real = recall_module.list_memory

    def counting(*args: object, **kwargs: object) -> list[MemoryItem]:
        rows = real(*args, **kwargs)
        seen.append(len(rows))
        return rows

    monkeypatch.setattr(recall_module, "list_memory", counting)
    return seen


def test_recall_over_ten_thousand_memories_materialises_at_most_the_cap(
    memory_con: LockedConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = "owner-heavy"
    # The three lexical hits are the three OLDEST rows: a recency-only bound
    # would cut them, so their presence proves the prefilter runs in SQL.
    hits = {0: "quantum bakery ledger", 1: "quantum bakery notes", 2: "quantum bakery audit"}
    _seed_bulk(memory_con, owner=owner, count=10_000, objects=hits)
    assert memory_con.execute(
        "SELECT count(*) FROM edges WHERE owner_user_id = ?", [owner]
    ).fetchone()[0] == 10_000
    seen = _count_materialised(monkeypatch)

    started = time.monotonic()
    result = recall_memory(memory_con, owner, query="quantum bakery")
    elapsed = time.monotonic() - started

    assert seen == [RECALL_CANDIDATE_CAP], seen
    assert RECALL_CANDIDATE_CAP < 10_000
    assert elapsed < 5.0, elapsed
    assert len(result) == 8
    assert [item.object for item in result[:3]] == [
        "quantum bakery audit",
        "quantum bakery notes",
        "quantum bakery ledger",
    ]
    assert [item.object for item in result[3:]] == [
        f"routine entry {index}" for index in range(9_999, 9_994, -1)
    ]

    # A blank query is recency only, and still bounded.
    blank = recall_memory(memory_con, owner, query="")
    assert seen[-1] == RECALL_CANDIDATE_CAP
    assert [item.object for item in blank] == [
        f"routine entry {index}" for index in range(9_999, 9_991, -1)
    ]


def _pre_change_recall(
    con: LockedConnection, owner: str, *, query: str | None, limit: int = 8
) -> list[MemoryItem]:
    """The implementation before this task, verbatim: full owner list, Python sort."""
    query_tokens = frozenset(lexical_tokens(query or ""))
    items = list_memory(con, owner)
    ranked = sorted(items, key=lambda item: (item.memory_id, item.edge_id))
    ranked.sort(key=lambda item: _salience_key(item, query_tokens=query_tokens), reverse=True)
    return ranked[:limit]


def test_bounded_recall_is_identical_to_the_pre_change_ranking_on_twenty_rows(
    memory_con: LockedConnection,
) -> None:
    owner = "owner-small"
    objects = [
        "vim with a dark theme", "emacs", "berlin", "vim", "tea over coffee",
        "berlin in the winter", "python", "rust", "a standing desk", "vim keybindings",
        "the 09:30 train", "no meetings before ten", "duckdb", "berlin", "vim",
        "postgres", "markdown notes", "a quiet office", "coffee", "vim and emacs",
    ]
    for index, obj in enumerate(objects):
        write_memory_item(
            memory_con,
            owner_user_id=owner,
            subject="operator",
            predicate=f"fact_{index}",
            object=obj,
            provenance={"event_id": f"event-{index}", "source_tier": 1},
            valid_from=datetime(2026, 8, 1, 9, 0) + timedelta(hours=index % 7),
        )
    assert len(list_memory(memory_con, owner)) == 20

    for query in ("vim", "berlin winter", "coffee", "", None, "nothing here matches", "vim emacs"):
        assert recall_memory(memory_con, owner, query=query) == _pre_change_recall(
            memory_con, owner, query=query
        ), query
    assert recall_memory(memory_con, owner, query="vim", limit=3) == _pre_change_recall(
        memory_con, owner, query="vim", limit=3
    )


def test_salient_tokens_order_hits_first_without_filtering(
    memory_con: LockedConnection,
) -> None:
    owner = "owner-order"
    _seed_bulk(
        memory_con,
        owner=owner,
        count=6,
        objects={0: "Quantum ledger", 3: "100% quantum", 4: "value_1000"},
    )
    plain = list_memory(memory_con, owner)
    assert [item.object for item in plain] == [
        "routine entry 5", "value_1000", "100% quantum", "routine entry 2",
        "routine entry 1", "Quantum ledger",
    ]

    ordered = list_memory(memory_con, owner, salient_tokens=["quantum"])
    # Same set, hits first (newest hit first), then the rest newest first.
    assert {item.edge_id for item in ordered} == {item.edge_id for item in plain}
    assert [item.object for item in ordered] == [
        "100% quantum", "Quantum ledger", "routine entry 5", "value_1000",
        "routine entry 2", "routine entry 1",
    ]
    # With a limit the hits survive even though they are not the newest rows.
    assert [item.object for item in list_memory(memory_con, owner, salient_tokens=["quantum"], limit=2)] == [
        "100% quantum", "Quantum ledger",
    ]
    # LIKE metacharacters are literal: "100%" is not a wildcard and "_1" is not "any-char 1".
    assert [item.object for item in list_memory(memory_con, owner, salient_tokens=["100%"], limit=1)] == [
        "100% quantum",
    ]
    assert [item.object for item in list_memory(memory_con, owner, salient_tokens=["e_1"], limit=1)] == [
        "value_1000",
    ]


def test_recall_limit_above_the_cap_is_still_honoured(memory_con: LockedConnection) -> None:
    owner = "owner-wide"
    _seed_bulk(memory_con, owner=owner, count=RECALL_CANDIDATE_CAP + 50, objects={})
    result = recall_memory(memory_con, owner, query="", limit=RECALL_CANDIDATE_CAP + 20)
    assert len(result) == RECALL_CANDIDATE_CAP + 20
