"""Tests for tools/reclassify_personal_reading.py against a synthetic DuckDB.

Seeds a corpus that mixes:
  * offending third-party rows ingested BEFORE the lane existed — a web_article,
    a video_transcript and a social_thread stamped ``user_owned`` (servable);
    one web_article stamped ``public_domain`` (a different servable class) to
    exercise the "sweep moves ALL servable third-party rows, not only
    user_owned" breadth (rigor #1);
  * a GENUINE operator upload — a real ``book`` on ``user_owned`` WITH a
    license_basis — that must survive the sweep untouched (M4) AND keep the
    post-sweep run_audit() green.

Asserts: dry-run writes nothing; --apply moves only the offending rows to
personal_reading and stamps the reversibility record; idempotency (second apply
sweeps 0, timestamp stable); rollback restores the pre-sweep content_class
exactly; the genuine upload is never touched; run_audit().ok is True post-sweep
and zero third-party-on-servable rows remain. No prod DB, no live network — a
temp DuckDB seeded through the same single-writer connect_write lock the
substrate uses.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from runtime.db_lock import connect_read, connect_write  # noqa: E402
from substrate.constants import (  # noqa: E402
    PERSONAL_READING_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
    THIRD_PARTY_DOCUMENT_TYPES,
)
from substrate.graph.schema import init_database  # noqa: E402
from tools import reclassify_personal_reading as rcl  # noqa: E402


@pytest.fixture(autouse=True)
def _disable_events(monkeypatch):
    """Disable event emission for every test in THIS module so the sweep never
    touches ~/.antiek/research_events. Scoped via monkeypatch (NOT a
    process-global os.environ mutation at import) so it is torn down after each
    test and can NEVER leak into co-collected test modules. The dedicated event
    test re-enables events into an isolated temp home with its own monkeypatch,
    which runs after this autouse fixture and wins."""
    monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "1")


# (document_id, document_type, content_class, source_uri, is_offending)
_OFFENDING = "OFFENDING"
_GENUINE = "GENUINE"

_SEED_ROWS = [
    # Offending: third-party types stuck on a servable class (the leak).
    ("doc-web-1", "web_article", "user_owned",
     "https://paulgraham.com/essay.html", _OFFENDING),
    ("doc-yt-1", "video_transcript", "user_owned",
     "https://www.youtube.com/watch?v=abc", _OFFENDING),
    ("doc-tw-1", "social_thread", "user_owned",
     "https://x.com/user/status/1", _OFFENDING),
    # Offending on a DIFFERENT servable class — proves the sweep moves ALL
    # servable third-party rows, not only user_owned ones (rigor #1 breadth).
    ("doc-web-2", "web_article", "public_domain",
     "https://example.org/old.html", _OFFENDING),
    # Genuine operator upload: a real book on user_owned. document_type is NOT
    # third-party, so it is structurally excluded from the sweep. Carries a
    # license_basis so the post-sweep run_audit() stays green.
    ("doc-book-1", "book", "user_owned",
     "file:///uploads/my-manuscript.pdf", _GENUINE),
]


@pytest.fixture
def seeded_db():
    """A synthetic graph DB seeded with the offending + genuine rows. Returns the
    db_path. The offending rows are inserted via RAW INSERT (not insert_document)
    so they reproduce the pre-lane state: a third-party row that landed on a
    servable class before the deny-by-default guard existed."""
    tmp = tempfile.mkdtemp(prefix="antiek-reclassify-")
    db_path = os.path.join(tmp, "graph.duckdb")
    con = connect_write(db_path, purpose="reclassify-test-init")
    try:
        init_database(con)
        for document_id, document_type, content_class, source_uri, _kind in _SEED_ROWS:
            con.execute(
                "INSERT INTO documents (document_id, source_uri, source_tier, "
                "document_type, content_class, raw_text) VALUES (?, ?, 2, ?, ?, ?)",
                [
                    document_id, source_uri, document_type, content_class,
                    # A non-empty, non-HTML body so the corpus audit's
                    # extraction-quality check (orthogonal to this sprint) is
                    # satisfied — keeps the post-sweep run_audit() verdict a clean
                    # signal of the content_class concern only.
                    f"Plain-text body for {document_id}. " * 4,
                ],
            )
        # The genuine book needs a license_basis so the corpus audit's
        # servable-basis check stays green both before and after the sweep.
        con.execute(
            "INSERT INTO book_assets (document_id, license_basis) VALUES "
            "(?, ?)",
            ["doc-book-1", "Operator-authored manuscript (Write workflow)"],
        )
    finally:
        con.close()
    return db_path


def _rows(db_path):
    """document_id -> (content_class, metadata_dict)."""
    con = connect_read(db_path)
    try:
        out = {}
        for doc_id, cc, meta in con.execute(
            "SELECT document_id, content_class, metadata FROM documents"
        ).fetchall():
            out[doc_id] = (cc, json.loads(meta) if meta else {})
        return out
    finally:
        con.close()


def _classes(db_path):
    return {doc_id: cc for doc_id, (cc, _m) in _rows(db_path).items()}


def _offending_ids():
    return [r[0] for r in _SEED_ROWS if r[4] == _OFFENDING]


def _count_third_party_on_servable(db_path):
    """The independent post-sweep assertion: third-party docs still on a servable
    class. Built from the SAME constants the tool uses, never a literal list."""
    con = connect_read(db_path)
    try:
        dt_ph = ", ".join("?" for _ in THIRD_PARTY_DOCUMENT_TYPES)
        cc_ph = ", ".join("?" for _ in SERVABLE_CONTENT_CLASSES)
        (n,) = con.execute(
            f"SELECT COUNT(*) FROM documents WHERE document_type IN ({dt_ph}) "
            f"AND content_class IN ({cc_ph})",
            sorted(THIRD_PARTY_DOCUMENT_TYPES) + sorted(SERVABLE_CONTENT_CLASSES),
        ).fetchone()
        return n
    finally:
        con.close()


# ---------------------------------------------------------------------------
# M1 — dry-run discovery writes nothing
# ---------------------------------------------------------------------------


def test_dry_run_reports_offending_and_writes_nothing(seeded_db):
    before = _rows(seeded_db)
    plan = rcl.run(seeded_db, apply=False)
    # 4 offending (3 user_owned third-party + 1 public_domain web_article); the
    # genuine book is excluded by document_type.
    assert plan.total_offending == 4
    by_type = dict(plan.by_document_type)
    assert by_type == {"web_article": 2, "video_transcript": 1, "social_thread": 1}
    assert "book" not in by_type
    # By-domain breakdown derived from source_uri.
    domains = dict(plan.by_source_domain)
    assert domains.get("paulgraham.com") == 1
    assert domains.get("www.youtube.com") == 1
    # Dry run wrote nothing — content_class AND metadata unchanged for every row.
    assert _rows(seeded_db) == before


def test_dry_run_count_matches_independent_query(seeded_db):
    plan = rcl.run(seeded_db, apply=False)
    assert plan.total_offending == _count_third_party_on_servable(seeded_db)


# ---------------------------------------------------------------------------
# M2 — the sweep + prior-class persistence
# ---------------------------------------------------------------------------


def test_apply_moves_offending_to_personal_reading(seeded_db):
    rcl.run(seeded_db, apply=True)
    after = _classes(seeded_db)
    for doc_id in _offending_ids():
        assert after[doc_id] == PERSONAL_READING_CONTENT_CLASS, doc_id


def test_apply_persists_prior_class_for_reversibility(seeded_db):
    before = _classes(seeded_db)
    rcl.run(seeded_db, apply=True)
    rows = _rows(seeded_db)
    for doc_id in _offending_ids():
        _cc, meta = rows[doc_id]
        assert meta[rcl.PRIOR_CLASS_KEY] == before[doc_id]
        assert meta[rcl.SWEPT_AT_KEY].endswith("Z")
    # doc-web-2 specifically restores to public_domain, not user_owned — the
    # breadth claim is honest (rigor #1).
    assert rows["doc-web-2"][1][rcl.PRIOR_CLASS_KEY] == "public_domain"


def test_apply_routes_through_gate_helper_not_raw_update(seeded_db, monkeypatch):
    """Every content_class mutation must go through update_document_gate_columns
    (the DuckDB-1.5.2-safe path), never a raw UPDATE."""
    import substrate.graph.ops as ops

    calls = []
    real = ops.update_document_gate_columns

    def _spy(con, document_id, **kwargs):
        calls.append((document_id, kwargs))
        return real(con, document_id, **kwargs)

    monkeypatch.setattr(rcl, "update_document_gate_columns", _spy)
    rcl.run(seeded_db, apply=True)
    swept = {c[0] for c in calls}
    assert swept == set(_offending_ids())
    for _doc_id, kwargs in calls:
        assert kwargs["content_class"] == PERSONAL_READING_CONTENT_CLASS
        assert kwargs["set_content_class"] is True


# ---------------------------------------------------------------------------
# M2/rigor#3 — idempotency
# ---------------------------------------------------------------------------


def test_second_apply_is_idempotent_noop(seeded_db):
    plan1 = rcl.run(seeded_db, apply=True)
    assert plan1.total_offending == 4
    stamps_after_first = {
        doc_id: meta[rcl.SWEPT_AT_KEY]
        for doc_id, (_cc, meta) in _rows(seeded_db).items()
        if rcl.SWEPT_AT_KEY in meta
    }
    plan2 = rcl.run(seeded_db, apply=True)
    # Second run selects zero offending rows (swept rows are off the servable set).
    assert plan2.total_offending == 0
    # No re-stamp: the swept_at timestamps are byte-identical across the two runs.
    stamps_after_second = {
        doc_id: meta[rcl.SWEPT_AT_KEY]
        for doc_id, (_cc, meta) in _rows(seeded_db).items()
        if rcl.SWEPT_AT_KEY in meta
    }
    assert stamps_after_second == stamps_after_first


def test_partial_crash_does_not_double_stamp(seeded_db):
    """A row already on personal_reading WITH a prior-class stamp must not be
    re-stamped if it somehow re-enters the sweep set. We simulate the guard
    directly: re-running _apply over a row that already carries the key leaves
    the original stamp intact."""
    # First sweep stamps everything.
    rcl.run(seeded_db, apply=True)
    rows = _rows(seeded_db)
    doc_id = _offending_ids()[0]
    original_stamp = rows[doc_id][1][rcl.SWEPT_AT_KEY]
    original_prior = rows[doc_id][1][rcl.PRIOR_CLASS_KEY]
    # Force the row back to a servable class WITHOUT clearing the metadata key —
    # the partial-crash shape (moved-then-reverted, stamp left behind).
    with connect_write(seeded_db, purpose="reclassify-test-crash") as con:
        rcl.update_document_gate_columns(
            con, doc_id, content_class="user_owned", set_content_class=True
        )
    # Re-apply: the row is offending again, but its prior-class key is present,
    # so the stamp must be preserved (not overwritten with user_owned).
    rcl.run(seeded_db, apply=True)
    rows2 = _rows(seeded_db)
    assert rows2[doc_id][0] == PERSONAL_READING_CONTENT_CLASS
    assert rows2[doc_id][1][rcl.PRIOR_CLASS_KEY] == original_prior  # not corrupted
    assert rows2[doc_id][1][rcl.SWEPT_AT_KEY] == original_stamp     # not re-stamped


# ---------------------------------------------------------------------------
# M3 — rollback + post-sweep audit
# ---------------------------------------------------------------------------


def test_rollback_restores_pre_sweep_content_class(seeded_db):
    pre = _classes(seeded_db)
    rcl.run(seeded_db, apply=True)
    rcl.run(seeded_db, rollback=True)
    post = _rows(seeded_db)
    # content_class is byte-for-byte equal to the pre-sweep state for every row.
    assert {d: cc for d, (cc, _m) in post.items()} == pre
    # reclassify_* keys are gone from every row.
    for doc_id, (_cc, meta) in post.items():
        assert rcl.PRIOR_CLASS_KEY not in meta
        assert rcl.SWEPT_AT_KEY not in meta


def test_rollback_then_reapply_round_trips(seeded_db):
    pre = _classes(seeded_db)
    rcl.run(seeded_db, apply=True)
    rcl.run(seeded_db, rollback=True)
    assert _classes(seeded_db) == pre
    # Re-apply cleanly re-stamps.
    rcl.run(seeded_db, apply=True)
    after = _classes(seeded_db)
    for doc_id in _offending_ids():
        assert after[doc_id] == PERSONAL_READING_CONTENT_CLASS


def test_post_sweep_audit_clean_and_zero_third_party_servable(seeded_db):
    from substrate.corpus_audit import run_audit

    # Pre-sweep: third-party rows sit on a servable class.
    assert _count_third_party_on_servable(seeded_db) == 4
    rcl.run(seeded_db, apply=True)
    # The independent post-sweep assertion: zero third-party docs on a servable
    # class (computed from the constants, not by counting what we swept).
    assert _count_third_party_on_servable(seeded_db) == 0
    # And the corpus audit verdict, reported verbatim.
    result = run_audit(seeded_db)
    assert result.ok is True, result.to_dict()


def test_sweep_emits_typed_event(seeded_db, tmp_path, monkeypatch):
    """The sweep emits exactly one corpus.reclassify_personal_reading event whose
    payload carries the operation + rows + by_document_type — the only audit
    trail of when/how-many on a real run."""
    from substrate.event_log.events import trajectory

    # Re-enable events into an isolated temp home so we can read the trajectory
    # back without touching ~/.antiek.
    monkeypatch.delenv("ANTIEK_EVENTS_DISABLED", raising=False)
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.delenv("ANTIEK_RESEARCH_EVENTS_DIR", raising=False)

    rcl.run(seeded_db, apply=True)
    events = trajectory("corpus-reclassify-personal-reading")
    sweep_events = [
        e for e in events if e.get("action_type") == rcl.SWEEP_ACTION_TYPE
    ]
    assert len(sweep_events) == 1
    payload = sweep_events[0]["payload"]
    assert payload["operation"] == "apply"
    assert payload["rows"] == 4
    by_type = {dt: n for dt, n in payload["by_document_type"]}
    assert by_type == {"web_article": 2, "video_transcript": 1, "social_thread": 1}


# ---------------------------------------------------------------------------
# M4 — genuine operator content is untouched
# ---------------------------------------------------------------------------


def test_genuine_user_owned_upload_untouched(seeded_db):
    rcl.run(seeded_db, apply=True)
    rows = _rows(seeded_db)
    cc, meta = rows["doc-book-1"]
    # Still user_owned; no reclassify_* metadata key.
    assert cc == "user_owned"
    assert rcl.PRIOR_CLASS_KEY not in meta
    assert rcl.SWEPT_AT_KEY not in meta


def test_genuine_row_excluded_from_dry_run_count(seeded_db):
    plan = rcl.run(seeded_db, apply=False)
    # The genuine book is not in the offending count (report + mutation read the
    # same WHERE clause — one source of truth).
    assert "book" not in dict(plan.by_document_type)
    assert plan.total_offending == 4


# ---------------------------------------------------------------------------
# CLI surface + prod guard
# ---------------------------------------------------------------------------


def test_cli_dry_run_then_apply(seeded_db, capsys):
    rc = rcl.main(["--db-path", seeded_db])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    # Still on the original class after a dry-run.
    assert _classes(seeded_db)["doc-web-1"] == "user_owned"

    rc = rcl.main(["--db-path", seeded_db, "--apply"])
    assert rc == 0
    assert "APPLIED" in capsys.readouterr().out
    assert _classes(seeded_db)["doc-web-1"] == PERSONAL_READING_CONTENT_CLASS


def test_cli_rollback(seeded_db, capsys):
    pre = _classes(seeded_db)
    rcl.main(["--db-path", seeded_db, "--apply"])
    capsys.readouterr()
    rc = rcl.main(["--db-path", seeded_db, "--rollback"])
    assert rc == 0
    assert "rollback" in capsys.readouterr().out.lower()
    assert _classes(seeded_db) == pre


def test_cli_rejects_prod_db(capsys):
    from substrate.graph import default_db_path

    rc = rcl.main(["--db-path", default_db_path(), "--apply"])
    assert rc == 2
    assert "prod" in capsys.readouterr().err.lower()


def test_cli_apply_and_rollback_mutually_exclusive(seeded_db):
    with pytest.raises(SystemExit):
        rcl.main(["--db-path", seeded_db, "--apply", "--rollback"])
