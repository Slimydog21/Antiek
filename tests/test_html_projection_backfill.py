from __future__ import annotations

import fcntl
import hashlib
import io
import json
from pathlib import Path

import duckdb
import pytest
from pypdf import PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from runtime.db_lock import connect_read, connect_write
from substrate.reading.projection import ProjectionStore
from substrate.reading.projection.backfill import (
    _claim,
    apply_backfill,
    backfill_projections,
    dry_run_backfill,
    plan_backfill,
    queued_contract,
    run_projection_backfill,
)
from substrate.reading.projection.pipeline import finalize_projection, prepare_projection
from substrate.reading.projection.source_catalog import ProjectionSourceCatalog


def _pdf(text: str | None = "A deterministic projection") -> bytes:
    if text is None:
        output = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.write(output)
        return output.getvalue()
    output = io.BytesIO()
    document = canvas.Canvas(output, pagesize=letter, invariant=True)
    document.drawString(72, 720, text)
    document.showPage()
    document.save()
    return output.getvalue()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _environment(tmp_path: Path) -> tuple[Path, Path, Path]:
    db = tmp_path / "catalog.duckdb"
    sources = tmp_path / "source-objects"
    html = tmp_path / "html-objects"
    sources.mkdir()
    html.mkdir()
    with connect_write(str(db), purpose="test.seed") as con:
        con.execute(
            "CREATE TABLE documents(document_id TEXT, document_type TEXT, raw_text TEXT, metadata JSON)"
        )
    return db, sources, html


def _add(
    db: Path,
    sources: Path,
    document_id: str,
    data: bytes,
    *,
    write: bool = True,
    sha256: str | None = None,
) -> None:
    key = f"pdf/{document_id}.pdf"
    if write:
        path = sources / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    metadata = {
        "html_projection_source": {
            "source_asset_id": f"asset-{document_id}",
            "object_key": key,
            "sha256": sha256 or hashlib.sha256(data).hexdigest(),
            "byte_size": len(data),
            "media_type": "application/pdf",
        }
    }
    with connect_write(str(db), purpose="test.add") as con:
        con.execute(
            "INSERT INTO documents VALUES (?, 'pdf', '', ?)",
            [document_id, json.dumps(metadata)],
        )


def _candidate(db: Path, sources: Path, document_id: str = "valid"):
    with connect_read(str(db)) as con:
        records = ProjectionSourceCatalog(con, sources).list()
    return next(record for record in records if record.document_id == document_id)


def _item_row(db: Path) -> tuple:
    with connect_read(str(db)) as con:
        return con.execute(
            "SELECT status,attempt_count,lease_owner,lease_expires_at,error_code,object_key "
            "FROM html_projection_backfill_items"
        ).fetchone()


def test_dry_run_is_byte_exact_read_only_deterministic_and_complete(tmp_path: Path) -> None:
    db, sources, html = _environment(tmp_path)
    _add(db, sources, "z-invalid", b"not pdf")
    _add(db, sources, "a-valid", _pdf("valid"))
    _add(db, sources, "m-ocr", _pdf(None))
    _add(db, sources, "u-missing", b"missing", write=False)
    Path(f"{db}.write.lock").unlink()
    before_digest = _digest(db)
    with duckdb.connect(str(db), read_only=True) as con:
        before_tables = con.execute("SHOW TABLES").fetchall()
        before_rows = con.execute("SELECT * FROM documents ORDER BY document_id").fetchall()
    before_manifest = sorted(str(p.relative_to(html)) for p in html.rglob("*"))
    assert not Path(f"{db}.write.lock").exists()

    first = plan_backfill(db_path=db, source_object_root=sources, html_object_root=html)
    second = plan_backfill(db_path=db, source_object_root=sources, html_object_root=html)

    assert first.canonical_json_bytes() == second.canonical_json_bytes()
    assert _digest(db) == before_digest
    with duckdb.connect(str(db), read_only=True) as con:
        assert con.execute("SHOW TABLES").fetchall() == before_tables
        assert con.execute("SELECT * FROM documents ORDER BY document_id").fetchall() == before_rows
    assert sorted(str(p.relative_to(html)) for p in html.rglob("*")) == before_manifest
    assert not Path(f"{db}.write.lock").exists()
    assert [item.projection_id for item in first.items] == sorted(
        item.projection_id for item in first.items
    )
    assert (
        first.candidates,
        first.would_convert,
        first.ocr_required,
        first.conversion_failed,
        first.unresolved,
    ) == (3, 1, 1, 1, 1)
    assert first.unresolved_reasons[0].reason_code == "missing_source_bytes"
    assert first.rollback_scope.automatic is False


def test_apply_valid_persists_hashed_object_and_replays_after_reopen(tmp_path: Path) -> None:
    db, sources, html = _environment(tmp_path)
    _add(db, sources, "valid", _pdf())
    first = apply_backfill(
        db_path=db, source_object_root=sources, html_object_root=html, clock=lambda: 10.0
    )
    item = first.items[0]
    object_path = html.joinpath(*item.object_key.split("/"))
    assert item.outcome == "ready" and object_path.exists()
    with connect_read(str(db)) as con:
        projection = ProjectionStore(con).load(item.projection_id)
    assert projection.status == "ready"
    assert projection.hosted_html_sha256 == _digest(object_path)
    assert _item_row(db) == ("ready", 1, None, None, None, item.object_key)

    replay = apply_backfill(
        db_path=db, source_object_root=sources, html_object_root=html, clock=lambda: 20.0
    )
    assert replay.items[0].outcome == "already_ready"
    assert _item_row(db)[1] == 1


def test_invalid_sibling_does_not_block_valid_and_ocr_is_terminal(tmp_path: Path) -> None:
    db, sources, html = _environment(tmp_path)
    _add(db, sources, "bad", b"invalid pdf")
    _add(db, sources, "good", _pdf("good"))
    _add(db, sources, "ocr", _pdf(None))
    report = apply_backfill(
        db_path=db, source_object_root=sources, html_object_root=html, clock=lambda: 1.0
    )
    assert {item.document_id: item.outcome for item in report.items} == {
        "bad": "failed",
        "good": "ready",
        "ocr": "ocr_required",
    }


def test_live_lease_excludes_then_expired_lease_reclaims(tmp_path: Path) -> None:
    db, sources, html = _environment(tmp_path)
    _add(db, sources, "valid", _pdf())
    report = plan_backfill(db_path=db, source_object_root=sources, html_object_root=html)
    candidate = _candidate(db, sources)
    from substrate.reading.projection.backfill import _ensure_and_seed

    _ensure_and_seed(str(db), report.plan_id, ((candidate, queued_contract(candidate)),))
    projection_id = report.items[0].projection_id
    first = _claim(str(db), report.plan_id, projection_id, "one", 10.0, 5.0)
    assert first is not None
    assert _claim(str(db), report.plan_id, projection_id, "two", 14.0, 5.0) is None
    second = _claim(str(db), report.plan_id, projection_id, "two", 15.0, 5.0)
    assert second is not None and second.owner == "two"
    assert _item_row(db)[1] == 2


def test_public_entrypoints_preserve_plan_and_apply_modes(tmp_path: Path) -> None:
    db, sources, html = _environment(tmp_path)
    _add(db, sources, "valid", _pdf())
    paths = {
        "db_path": db,
        "source_object_root": sources,
        "html_object_root": html,
    }

    assert dry_run_backfill(**paths).dry_run is True
    assert plan_backfill(**paths).dry_run is True
    assert run_projection_backfill(**paths).dry_run is True
    assert backfill_projections(**paths).dry_run is True
    assert apply_backfill(**paths, clock=lambda: 1.0).dry_run is False


def test_stale_worker_cannot_publish_or_overwrite_reclaimed_item(tmp_path: Path) -> None:
    db, sources, html = _environment(tmp_path)
    data = _pdf()
    _add(db, sources, "valid", data)

    def reclaim(queued, source):
        with connect_read(str(db)) as con:
            run_id = con.execute("SELECT run_id FROM html_projection_backfill_runs").fetchone()[0]
        assert _claim(str(db), run_id, queued.projection_id, "new-owner", 2.0, 10.0)
        return prepare_projection(queued, source)

    report = apply_backfill(
        db_path=db,
        source_object_root=sources,
        html_object_root=html,
        worker_id="stale",
        clock=lambda: 0.0,
        lease_seconds=1.0,
        prepare=reclaim,
    )
    assert report.items[0].outcome == "processing"
    published = list(html.rglob("*.html"))
    assert len(published) == 1
    candidate = _candidate(db, sources)
    prepared = prepare_projection(queued_contract(candidate), data)
    assert prepared.html_bytes is not None
    assert published[0].read_bytes() == prepared.html_bytes
    with connect_read(str(db)) as con:
        assert "html_projections" not in {row[0] for row in con.execute("SHOW TABLES").fetchall()}
    assert _item_row(db)[2] == "new-owner"


def test_source_and_prepare_failures_terminalize_with_owned_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, sources, html = _environment(tmp_path)
    _add(db, sources, "valid", _pdf())
    source_path = _candidate(db, sources).source_path
    original = Path.read_bytes

    def fail_source(path: Path) -> bytes:
        if path == source_path:
            raise OSError("injected source failure")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", fail_source)
    source_report = apply_backfill(
        db_path=db,
        source_object_root=sources,
        html_object_root=html,
        clock=lambda: 1.0,
    )
    assert source_report.items[0].error_code == "source_read_failed"
    monkeypatch.setattr(Path, "read_bytes", original)

    def fail_prepare(*_args):
        raise RuntimeError("injected prepare failure")

    prepare_report = apply_backfill(
        db_path=db,
        source_object_root=sources,
        html_object_root=html,
        clock=lambda: 2.0,
        prepare=fail_prepare,
    )
    assert prepare_report.items[0].error_code == "conversion_failed"
    assert _item_row(db)[:5] == ("failed", 2, None, None, "conversion_failed")


@pytest.mark.parametrize("conflict", [False, True])
def test_prepublished_object_is_adopted_only_when_hash_matches(
    tmp_path: Path,
    conflict: bool,
) -> None:
    db, sources, html = _environment(tmp_path)
    data = _pdf()
    _add(db, sources, "valid", data)
    candidate = _candidate(db, sources)
    queued = queued_contract(candidate)
    prepared = prepare_projection(queued, data)
    assert prepared.html_bytes is not None
    path = html / "html-projections" / f"{queued.projection_id}.html"
    path.parent.mkdir()
    path.write_bytes(b"conflict" if conflict else prepared.html_bytes)
    report = apply_backfill(
        db_path=db, source_object_root=sources, html_object_root=html, clock=lambda: 1.0
    )
    assert report.items[0].outcome == ("failed" if conflict else "ready")
    assert report.items[0].error_code == ("object_hash_conflict" if conflict else None)


def test_prepare_runs_without_write_lock_and_report_has_exact_rollback_scope(
    tmp_path: Path,
) -> None:
    db, sources, html = _environment(tmp_path)
    data = _pdf()
    _add(db, sources, "valid", data)

    def inspect_lock(queued, source):
        with Path(f"{db}.write.lock").open("a+") as fd:
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        with connect_write(str(db), purpose="test.prepare.concurrent") as con:
            con.execute("SELECT 1")
        return prepare_projection(queued, source)

    report = apply_backfill(
        db_path=db,
        source_object_root=sources,
        html_object_root=html,
        clock=lambda: 1.0,
        prepare=inspect_lock,
    )
    item = report.items[0]
    assert report.rollback_scope.run_id == report.plan_id
    assert report.rollback_scope.item_rows == (item.projection_id,)
    assert report.rollback_scope.object_keys == (item.object_key,)


def test_existing_ready_projection_is_adopted_without_attempt(tmp_path: Path) -> None:
    db, sources, html = _environment(tmp_path)
    data = _pdf()
    _add(db, sources, "valid", data)
    candidate = _candidate(db, sources)
    queued = queued_contract(candidate)
    prepared = prepare_projection(queued, data)
    key = f"html-projections/{queued.projection_id}.html"
    finalized = finalize_projection(prepared, key)
    with connect_write(str(db), purpose="test.ready") as con:
        store = ProjectionStore(con)
        from substrate.reading.projection.pipeline import persist_prepared_projection

        persist_prepared_projection(store, queued, finalized)
    report = apply_backfill(db_path=db, source_object_root=sources, html_object_root=html)
    assert report.items[0].outcome == "already_ready"
    assert _item_row(db)[1] == 0


@pytest.mark.parametrize(
    ("worker", "seconds", "clock", "message"),
    [
        ("", 1.0, lambda: 0.0, "worker_id"),
        ("ok", 0.0, lambda: 0.0, "lease_seconds"),
        ("ok", float("inf"), lambda: 0.0, "lease_seconds"),
        ("ok", 1.0, lambda: float("nan"), "clock"),
    ],
)
def test_worker_lease_and_clock_validation(tmp_path: Path, worker, seconds, clock, message) -> None:
    db, sources, html = _environment(tmp_path)
    _add(db, sources, "valid", _pdf())
    with pytest.raises(ValueError, match=message):
        apply_backfill(
            db_path=db,
            source_object_root=sources,
            html_object_root=html,
            worker_id=worker,
            lease_seconds=seconds,
            clock=clock,
        )
