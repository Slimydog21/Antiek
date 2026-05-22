"""Tests for deliverables publication overlay + reward_deep worker."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import duckdb
import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """Set up the DB required by the reward_deep join.

    There was a SPR-08 schema collision: substrate/graph/schema.py and
    services/notebooks/migrations/0001 both declared ``notebook_blocks``
    with INCOMPATIBLE shapes. The 2026-05-22 rename moved SPR-08's
    table to ``per_doc_notebook_blocks``; the collision is gone, this
    fixture no longer needs the DROP hack.
    """
    p = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", p)
    from substrate.graph import ensure_initialized
    ensure_initialized(p)
    from substrate.behavior.schema import init_behavior_schema_at_path
    init_behavior_schema_at_path(p)
    from substrate.notebooks.deliverables import init_deliverables_schema_at_path
    init_deliverables_schema_at_path(p)
    from services.notebooks.schema import init_notebooks_schema_at_path
    init_notebooks_schema_at_path(p)
    return p


def _insert_behavior_event(
    db_path: str, *, event_id: str, user_id: str,
):
    with duckdb.connect(db_path) as con:
        con.execute(
            "INSERT INTO behavior_events "
            "(event_id, user_id, session_id, event_type, "
            " timestamp_utc, state, action, consent_version) "
            "VALUES (?, ?, ?, ?, ?, '{}', '{}', 1)",
            [
                event_id, user_id, "test-session", "highlight_created",
                datetime.now(timezone.utc),
            ],
        )


def _insert_deliverable(
    db_path: str, *, deliverable_id: str, owner_user_id: str = "__operator__",
    deliverable_kind: str = "general_essay", status: str = "draft",
):
    """Insert via the graph schema directly. Sprint 19's surface will
    use ``substrate/graph/ops.insert_deliverable`` instead."""
    with duckdb.connect(db_path) as con:
        con.execute(
            "INSERT INTO deliverables "
            "(deliverable_id, title, deliverable_kind, owner_user_id, status) "
            "VALUES (?, ?, ?, ?, ?)",
            [deliverable_id, "Test", deliverable_kind, owner_user_id, status],
        )


def _insert_notebook_with_block(
    db_path: str, *, notebook_id: str, block_id: str, user_id: str,
    document_id: str, source_event_ids: list[str],
):
    import json as _json
    with duckdb.connect(db_path) as con:
        con.execute(
            "INSERT INTO notebook_documents "
            "(notebook_id, user_id, document_id, title, content_json, "
            " format_version) VALUES (?, ?, ?, NULL, '{}', 1)",
            [notebook_id, user_id, document_id],
        )
        con.execute(
            "INSERT INTO per_doc_notebook_blocks "
            "(block_id, notebook_id, block_type, source_event_ids, "
            " content_json, position, document_id) "
            "VALUES (?, ?, 'highlight_card', ?, '{}', 1.0, ?)",
            [block_id, notebook_id, _json.dumps(source_event_ids), document_id],
        )


def test_publication_overlay_persists(db_path):
    from substrate.notebooks.deliverables import mark_published, load_deliverable
    _insert_deliverable(db_path, deliverable_id="del-1")
    pub = mark_published(
        "del-1", publication_uri="https://example.com/essay", db_path=db_path,
    )
    assert pub.is_published is True
    assert pub.publication_uri == "https://example.com/essay"
    # status remains 'draft' — publication is orthogonal to workflow.
    assert pub.status == "draft"
    # Roundtrip via fresh load.
    loaded = load_deliverable("del-1", db_path=db_path)
    assert loaded is not None and loaded.is_published is True


def test_mark_unpublished_clears(db_path):
    from substrate.notebooks.deliverables import mark_published, mark_unpublished
    _insert_deliverable(db_path, deliverable_id="del-u")
    mark_published("del-u", publication_uri="https://x", db_path=db_path)
    cleared = mark_unpublished("del-u", db_path=db_path)
    assert cleared.is_published is False
    assert cleared.publication_uri is None


def test_cite_notebook_is_idempotent(db_path):
    from substrate.notebooks.deliverables import (
        cite_notebook, find_published_deliverables_citing_notebook,
    )
    _insert_deliverable(db_path, deliverable_id="del-c")
    cite_notebook(deliverable_id="del-c", notebook_id="nb-1", db_path=db_path)
    cite_notebook(deliverable_id="del-c", notebook_id="nb-1", db_path=db_path)
    # Unpublished — query returns empty.
    rows = find_published_deliverables_citing_notebook("nb-1", db_path=db_path)
    assert rows == []


def test_reward_deep_runs_when_dependencies_present_no_data(db_path):
    from substrate.behavior.workers.reward_deep import run_reward_deep_backfill
    result = run_reward_deep_backfill(db_path=db_path)
    assert result.status == "ran"
    assert result.rows_updated == 0


def test_reward_deep_propagates_through_full_chain(db_path):
    from substrate.notebooks.deliverables import (
        mark_published, cite_notebook,
    )
    from substrate.behavior.workers.reward_deep import run_reward_deep_backfill

    _insert_behavior_event(db_path, event_id="evt-1", user_id="__operator__")
    _insert_notebook_with_block(
        db_path,
        notebook_id="nb-1", block_id="blk-1",
        user_id="__operator__", document_id="doc-1",
        source_event_ids=["evt-1"],
    )
    _insert_deliverable(db_path, deliverable_id="del-p")
    mark_published("del-p", publication_uri="https://x/y", db_path=db_path)
    cite_notebook(deliverable_id="del-p", notebook_id="nb-1", db_path=db_path)

    result = run_reward_deep_backfill(db_path=db_path)
    assert result.status == "ran"

    with duckdb.connect(db_path) as con:
        row = con.execute(
            "SELECT reward_proxy_deep FROM behavior_events WHERE event_id='evt-1'"
        ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert float(row[0]) == 1.0


def test_reward_deep_skips_unpublished(db_path):
    """A cited but unpublished deliverable does NOT propagate reward_deep."""
    from substrate.notebooks.deliverables import cite_notebook
    from substrate.behavior.workers.reward_deep import run_reward_deep_backfill

    _insert_behavior_event(db_path, event_id="evt-u", user_id="__operator__")
    _insert_notebook_with_block(
        db_path, notebook_id="nb-u", block_id="blk-u",
        user_id="__operator__", document_id="doc-u",
        source_event_ids=["evt-u"],
    )
    _insert_deliverable(db_path, deliverable_id="del-unpub")
    cite_notebook(deliverable_id="del-unpub", notebook_id="nb-u", db_path=db_path)
    # Deliberately do NOT mark_published.

    run_reward_deep_backfill(db_path=db_path)

    with duckdb.connect(db_path) as con:
        row = con.execute(
            "SELECT reward_proxy_deep FROM behavior_events WHERE event_id='evt-u'"
        ).fetchone()
    assert row[0] is None or float(row[0]) == 0.0


def test_reward_deep_idempotent_on_rerun(db_path):
    from substrate.notebooks.deliverables import mark_published, cite_notebook
    from substrate.behavior.workers.reward_deep import run_reward_deep_backfill

    _insert_behavior_event(db_path, event_id="evt-i", user_id="__operator__")
    _insert_notebook_with_block(
        db_path, notebook_id="nb-i", block_id="blk-i",
        user_id="__operator__", document_id="doc-i",
        source_event_ids=["evt-i"],
    )
    _insert_deliverable(db_path, deliverable_id="del-i")
    mark_published("del-i", publication_uri="https://x", db_path=db_path)
    cite_notebook(deliverable_id="del-i", notebook_id="nb-i", db_path=db_path)

    r1 = run_reward_deep_backfill(db_path=db_path)
    r2 = run_reward_deep_backfill(db_path=db_path)
    assert r1.status == r2.status == "ran"
