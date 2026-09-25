"""Crash and restore behavior for the DB-authoritative arXiv bulk cursor."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from runtime.db_lock import connect_read
from substrate.graph.schema import load_arxiv_bulk_progress
from tools.arxiv_bulk_resume import whole_run_lock
from tools.arxiv_oai_sync import (
    SyncCheckpoint,
    main,
    read_checkpoint,
    run_bulk_sync,
    run_sync,
    write_checkpoint,
)


class _NoTail:
    def harvest(self, **_kwargs):
        raise AssertionError("bulk-only test must not fetch OAI")


def _record(arxiv_id: str, day: str) -> dict:
    return {
        "id": arxiv_id, "title": f"Title {arxiv_id}", "abstract": "Abstract",
        "categories": "cs.LG", "license": "https://creativecommons.org/licenses/by/4.0/",
        "authors_parsed": [["Researcher", "A", ""]],
        "versions": [{"version": "v1", "created": "Mon, 1 Jan 2024 10:00:00 GMT"}],
        "update_date": day,
    }


def _run(tmp_path, snapshot: Path, *, batch_size: int = 1):
    return run_bulk_sync(
        harvester=_NoTail(), mode="backfill", oai_tail=False,
        sync_state_path=str(tmp_path / "sync.json"), bulk_snapshot_path=str(snapshot),
        db_path=str(tmp_path / "graph.duckdb"), persist_batch_size=batch_size,
        lock_yield_seconds=0,
    )


def _progress(tmp_path):
    with connect_read(str(tmp_path / "graph.duckdb")) as con:
        return load_arxiv_bulk_progress(con)


def test_committed_line_cursor_resumes_after_crash_and_skips_are_counted(tmp_path, monkeypatch):
    first = (json.dumps(_record("a", "2024-01-01")) + "\n").encode()
    last = json.dumps(_record("b", "2024-01-02")).encode()
    snapshot = tmp_path / "snap.json"
    snapshot.write_bytes(first + b"not JSON\n" + last)  # final line has no LF
    import tools.arxiv_oai_sync as sync

    real = sync.commit_bulk_slice
    called = 0

    def die_after_commit(*args, **kwargs):
        nonlocal called
        result = real(*args, **kwargs)
        called += 1
        if called == 1:
            raise RuntimeError("process died after a committed slice")
        return result

    monkeypatch.setattr(sync, "commit_bulk_slice", die_after_commit)
    with pytest.raises(RuntimeError, match="after a committed slice"):
        _run(tmp_path, snapshot)
    partial = _progress(tmp_path)
    assert partial is not None
    assert partial["phase"] == "bulk"
    assert partial["next_byte_offset"] == len(first)
    assert partial["physical_line_count"] == 1
    assert partial["bulk_t1_events"] == 1
    assert not (tmp_path / "sync.json").exists()

    monkeypatch.setattr(sync, "commit_bulk_slice", real)
    result = _run(tmp_path, snapshot)
    assert result.census.t1 == 2
    assert result.census.total == 2
    assert result.new_datestamp == "2024-01-02"
    done = _progress(tmp_path)
    assert done is not None
    assert done["phase"] == "complete"
    assert done["next_byte_offset"] == snapshot.stat().st_size
    assert done["physical_line_count"] == 3
    assert done["selected_record_count"] == 2
    assert done["completed_generation_id"] == partial["generation_id"]
    assert read_checkpoint(str(tmp_path / "sync.json")).last_successful_datestamp == "2024-01-02"
    with connect_read(str(tmp_path / "graph.duckdb")) as con:
        assert con.execute("SELECT count(*) FROM documents WHERE document_id LIKE 'doc-arxiv-%'").fetchone()[0] == 2


def test_document_and_cursor_roll_back_together_before_slice_commit(tmp_path, monkeypatch):
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(json.dumps(_record("a", "2024-01-01")) + "\n")
    import tools.arxiv_bulk_resume as resume

    real = resume.persist_oai_record

    def die_inside_transaction(con, record):
        real(con, record)
        raise RuntimeError("before commit")

    monkeypatch.setattr(resume, "persist_oai_record", die_inside_transaction)
    with pytest.raises(RuntimeError, match="before commit"):
        _run(tmp_path, snapshot)
    row = _progress(tmp_path)
    assert row is not None
    assert row["next_byte_offset"] == 0
    assert row["selected_record_count"] == 0
    with connect_read(str(tmp_path / "graph.duckdb")) as con:
        assert con.execute("SELECT count(*) FROM documents WHERE document_id LIKE 'doc-arxiv-%'").fetchone()[0] == 0


def test_same_size_changed_snapshot_refuses_incomplete_resume(tmp_path, monkeypatch):
    snapshot = tmp_path / "snap.json"
    first = json.dumps(_record("a", "2024-01-01")) + "\n"
    second = json.dumps(_record("b", "2024-01-02")) + "\n"
    snapshot.write_text(first + second)
    import tools.arxiv_oai_sync as sync

    real = sync.commit_bulk_slice

    def die_after_commit(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("interrupted")

    monkeypatch.setattr(sync, "commit_bulk_slice", die_after_commit)
    with pytest.raises(RuntimeError, match="interrupted"):
        _run(tmp_path, snapshot)
    monkeypatch.setattr(sync, "commit_bulk_slice", real)
    before = _progress(tmp_path)
    assert before is not None
    original_stat = snapshot.stat()
    changed = snapshot.read_text().replace('"Title b"', '"Title c"')
    assert len(changed) == len(first + second)
    snapshot.write_text(changed)
    os.utime(snapshot, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    with pytest.raises(ValueError, match="source or window mismatch"):
        _run(tmp_path, snapshot)
    assert _progress(tmp_path)["next_byte_offset"] == before["next_byte_offset"]


def test_identical_snapshot_at_new_path_resumes_same_generation(tmp_path, monkeypatch):
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(
        json.dumps(_record("a", "2024-01-01")) + "\n"
        + json.dumps(_record("b", "2024-01-02")) + "\n"
    )
    import tools.arxiv_oai_sync as sync

    real = sync.commit_bulk_slice

    def die_after_commit(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("interrupted")

    monkeypatch.setattr(sync, "commit_bulk_slice", die_after_commit)
    with pytest.raises(RuntimeError, match="interrupted"):
        _run(tmp_path, snapshot)
    monkeypatch.setattr(sync, "commit_bulk_slice", real)
    partial = _progress(tmp_path)
    assert partial is not None
    moved = tmp_path / "moved.json"
    shutil.copy2(snapshot, moved)
    result = _run(tmp_path, moved)
    done = _progress(tmp_path)
    assert done is not None
    assert result.census.total == 2
    assert done["completed_generation_id"] == partial["generation_id"]


def test_cli_force_download_refuses_to_replace_incomplete_bound_snapshot(tmp_path, monkeypatch):
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(
        json.dumps(_record("a", "2024-01-01")) + "\n"
        + json.dumps(_record("b", "2024-01-02")) + "\n"
    )
    import tools.arxiv_oai_sync as sync

    real = sync.commit_bulk_slice

    def die_after_commit(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("interrupted")

    monkeypatch.setattr(sync, "commit_bulk_slice", die_after_commit)
    with pytest.raises(RuntimeError, match="interrupted"):
        _run(tmp_path, snapshot)
    monkeypatch.setattr(sync, "commit_bulk_slice", real)
    before_bytes = snapshot.read_bytes()
    before_cursor = _progress(tmp_path)
    assert before_cursor is not None and before_cursor["phase"] == "bulk"

    def forbidden_download(**_kwargs):
        raise AssertionError("forced download must be rejected before acquisition")

    monkeypatch.setattr(sync, "ensure_bulk_snapshot", forbidden_download)
    assert sync.main([
        "backfill", "--bulk", "--bulk-force-download", "--bulk-snapshot", str(snapshot),
        "--db-path", str(tmp_path / "graph.duckdb"),
    ]) == 1
    assert snapshot.read_bytes() == before_bytes
    assert _progress(tmp_path)["next_byte_offset"] == before_cursor["next_byte_offset"]


def test_restored_db_overrules_newer_json_mirror(tmp_path):
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(json.dumps(_record("a", "2024-01-01")) + "\n")
    _run(tmp_path, snapshot)
    backup = tmp_path / "old-db-copy.duckdb"
    shutil.copy2(tmp_path / "graph.duckdb", backup)
    snapshot.write_text(json.dumps(_record("b", "2024-02-01")) + "\n")
    _run(tmp_path, snapshot)
    assert read_checkpoint(str(tmp_path / "sync.json")).last_successful_datestamp == "2024-02-01"
    shutil.copy2(backup, tmp_path / "graph.duckdb")
    result = _run(tmp_path, snapshot)
    assert result.previous_datestamp == "2024-01-01"
    assert result.new_datestamp == "2024-02-01"


def test_whole_run_lock_is_stable_and_rejects_another_process(tmp_path):
    db_path = str(tmp_path / "graph.duckdb")
    script = (
        "import sys,time\nfrom tools.arxiv_bulk_resume import whole_run_lock\n"
        "with whole_run_lock(sys.argv[1]):\n print('held',flush=True)\n time.sleep(20)\n"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", script, db_path], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "held"
        with (
            pytest.raises(RuntimeError, match="already active.*pid="),
            whole_run_lock(db_path),
        ):
            pass
    finally:
        child.terminate()
        child.wait(timeout=5)
    with whole_run_lock(db_path):
        assert Path(db_path + ".arxiv_bulk_run.lock").exists()


def test_sigterm_after_committed_slice_resumes_in_new_process(tmp_path):
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(
        json.dumps(_record("first", "2024-01-01")) + "\n"
        + json.dumps(_record("second", "2024-01-02")) + "\n"
    )
    script = """
import os, signal, sys
import tools.arxiv_oai_sync as sync
real = sync.commit_bulk_slice
def stop_after_commit(*args, **kwargs):
    real(*args, **kwargs)
    os.kill(os.getpid(), signal.SIGTERM)
sync.commit_bulk_slice = stop_after_commit
sync.run_bulk_sync(
    harvester=None, mode='backfill', oai_tail=False,
    sync_state_path=sys.argv[1], bulk_snapshot_path=sys.argv[2],
    db_path=sys.argv[3], persist_batch_size=1, lock_yield_seconds=0,
)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "sync.json"),
         str(snapshot), str(tmp_path / "graph.duckdb")],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
             "ANTIEK_WRITE_KEEPALIVE_S": "0"},
        capture_output=True, text=True, timeout=25,
    )
    assert child.returncode == -15, child.stderr
    partial = _progress(tmp_path)
    assert partial is not None
    assert 0 < partial["next_byte_offset"] < snapshot.stat().st_size
    result = _run(tmp_path, snapshot)
    assert result.census.total == 2
    done = _progress(tmp_path)
    assert done is not None
    assert done["phase"] == "complete"
    assert done["next_byte_offset"] == snapshot.stat().st_size


def test_json_only_high_water_requires_explicit_full_replay(tmp_path):
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(json.dumps(_record("a", "2024-01-01")) + "\n")
    sync_path = str(tmp_path / "sync.json")
    write_checkpoint(sync_path, SyncCheckpoint(last_successful_datestamp="2023-12-31"))
    with pytest.raises(ValueError, match="operator must select"):
        _run(tmp_path, snapshot)
    result = run_bulk_sync(
        harvester=_NoTail(), mode="backfill", oai_tail=False,
        sync_state_path=sync_path, bulk_snapshot_path=str(snapshot),
        db_path=str(tmp_path / "graph.duckdb"), replay_from_zero=True,
        lock_yield_seconds=0,
    )
    assert result.previous_datestamp is None
    assert result.census.total == 1


def test_incomplete_tail_refuses_changed_tail_mode_and_legacy_reset(tmp_path):
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(json.dumps(_record("a", "2024-01-01")) + "\n")

    class _FailTail:
        def harvest(self, **_kwargs):
            raise RuntimeError("tail failed")

    with pytest.raises(RuntimeError, match="tail failed"):
        run_bulk_sync(
            harvester=_FailTail(), mode="backfill", oai_tail=True,
            sync_state_path=str(tmp_path / "sync.json"), bulk_snapshot_path=str(snapshot),
            db_path=str(tmp_path / "graph.duckdb"), lock_yield_seconds=0,
        )
    progress = _progress(tmp_path)
    assert progress is not None and progress["phase"] == "tail"
    with pytest.raises(ValueError, match="source or window mismatch"):
        _run(tmp_path, snapshot)
    with pytest.raises(ValueError, match="cannot discard an incomplete DB cursor"):
        run_bulk_sync(
            harvester=_FailTail(), mode="backfill", oai_tail=True,
            sync_state_path=str(tmp_path / "sync.json"), bulk_snapshot_path=str(snapshot),
            db_path=str(tmp_path / "graph.duckdb"), resume=False,
        )
    with pytest.raises(ValueError, match="pure OAI cannot run"):
        run_sync(
            harvester=_FailTail(), mode="incremental",
            sync_state_path=str(tmp_path / "sync.json"),
            db_path=str(tmp_path / "graph.duckdb"), resume=False,
        )
    assert main(["incremental", "--reset-state", "--db-path", str(tmp_path / "graph.duckdb")]) == 2
    assert _progress(tmp_path)["phase"] == "tail"


def test_compressed_snapshot_is_not_a_seekable_cursor_source(tmp_path):
    snapshot = tmp_path / "snap.json.gz"
    snapshot.write_bytes(b"\x1f\x8b" + b"not actual gzip")
    with pytest.raises(ValueError, match="plain JSONL"):
        _run(tmp_path, snapshot)


def test_legacy_invalid_datestamp_keeps_record_but_not_high_water(tmp_path):
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(
        json.dumps(_record("bad-date", "2024-99-99")) + "\n"
        + json.dumps(_record("valid", "2024-01-02")) + "\n"
    )
    result = _run(tmp_path, snapshot)
    assert result.census.total == 2
    assert result.new_datestamp == "2024-01-02"
    progress = _progress(tmp_path)
    assert progress is not None
    assert progress["selected_record_count"] == 2
    assert progress["bulk_t1_events"] == 2
    with connect_read(str(tmp_path / "graph.duckdb")) as con:
        assert con.execute("SELECT count(*) FROM documents WHERE document_id LIKE 'doc-arxiv-%'").fetchone()[0] == 2


@pytest.mark.parametrize("count", [200, 201])
def test_exact_batch_and_partial_batch_reach_verified_eof(tmp_path, count):
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(
        "".join(
            json.dumps(_record(f"{number:04d}", "2024-01-01")) + "\n"
            for number in range(count)
        )
    )
    result = _run(tmp_path, snapshot, batch_size=200)
    progress = _progress(tmp_path)
    assert progress is not None
    assert result.census.total == count
    assert progress["physical_line_count"] == count
    assert progress["selected_record_count"] == count
    assert progress["next_byte_offset"] == snapshot.stat().st_size


def test_elapsed_lock_attempt_releases_writer_between_lines(tmp_path, monkeypatch):
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(
        json.dumps(_record("a", "2024-01-01")) + "\n"
        + json.dumps(_record("b", "2024-01-02")) + "\n"
    )
    import tools.arxiv_bulk_resume as resume

    real = resume.connect_write
    slice_leases = 0

    def count_leases(*args, **kwargs):
        nonlocal slice_leases
        if kwargs.get("purpose") == "arxiv_bulk_slice":
            slice_leases += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(resume, "connect_write", count_leases)
    result = run_bulk_sync(
        harvester=_NoTail(), mode="backfill", oai_tail=False,
        sync_state_path=str(tmp_path / "sync.json"), bulk_snapshot_path=str(snapshot),
        db_path=str(tmp_path / "graph.duckdb"), persist_batch_size=2,
        max_lock_seconds=0.000001, lock_yield_seconds=0,
    )
    assert result.census.total == 2
    assert slice_leases >= 2
