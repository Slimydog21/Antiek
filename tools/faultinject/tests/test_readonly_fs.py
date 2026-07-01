"""Read-only-FS injector: fires EROFS at the armed path only; inert elsewhere;
deterministic via fail_on_call; teardown restores even on raise."""

from __future__ import annotations

import errno
import logging
import os
import shutil
import tempfile

import pytest

from tools.faultinject import arm, readonly_fs


def test_write_to_target_raises_erofs(tmp_path):
    target = tmp_path / "cache.idx"
    with readonly_fs(target):
        with pytest.raises(OSError) as ei:
            open(target, "w")
        assert ei.value.errno == errno.EROFS
    # Disarmed: the same write now succeeds.
    with open(target, "w") as fh:
        fh.write("ok")
    assert target.read_text() == "ok"


def test_scoped_to_target_other_paths_unaffected(tmp_path):
    target = tmp_path / "cache.idx"
    other = tmp_path / "other.txt"
    existing = tmp_path / "read_me.txt"
    existing.write_text("readable")
    with readonly_fs(target):
        # A different path writes normally while the fault is armed.
        with open(other, "w") as fh:
            fh.write("fine")
        assert other.read_text() == "fine"
        # Reads (even of the target's directory) are untouched — write-only fault.
        assert existing.read_text() == "readable"
        # The armed target still faults on write.
        with pytest.raises(OSError) as ei:
            open(target, "w")
        assert ei.value.errno == errno.EROFS


def test_target_write_via_pathlib_faults(tmp_path):
    # Path.write_text routes through io.open — prove that seam is covered too.
    target = tmp_path / "viapath.idx"
    with readonly_fs(target):
        with pytest.raises(OSError) as ei:
            target.write_text("nope")
        assert ei.value.errno == errno.EROFS


def test_os_replace_to_target_faults(tmp_path):
    target = tmp_path / "final.idx"
    src = tmp_path / "staged.tmp"
    src.write_text("payload")
    with readonly_fs(target):
        with pytest.raises(OSError) as ei:
            os.replace(src, target)
        assert ei.value.errno == errno.EROFS
    # Disarmed: replace works.
    os.replace(src, target)
    assert target.read_text() == "payload"


def test_fail_on_call_survives_first_fails_second(tmp_path):
    target = tmp_path / "cache.idx"
    with readonly_fs(target, fail_on_call=2):
        # Call 1 succeeds.
        with open(target, "w") as fh:
            fh.write("first")
        # Call 2 faults.
        with pytest.raises(OSError) as ei:
            open(target, "w")
        assert ei.value.errno == errno.EROFS
    assert target.read_text() == "first"


def test_teardown_restores_even_when_body_raises(tmp_path):
    target = tmp_path / "cache.idx"

    class Boom(RuntimeError):
        pass

    with pytest.raises(Boom):
        with readonly_fs(target):
            raise Boom()
    # After the exception, the primitive is restored: writing works.
    with open(target, "w") as fh:
        fh.write("restored")
    assert target.read_text() == "restored"


def test_arm_generic_entry_point(tmp_path):
    target = tmp_path / "cache.idx"
    with arm("readonly_fs", target_path=target):
        with pytest.raises(OSError) as ei:
            open(target, "w")
        assert ei.value.errno == errno.EROFS


def test_fires_at_shutil_copy_seam(tmp_path):
    # shutil.copy is the exact write primitive the retriever uses at
    # substrate/graph/retrieval_substrate.py:336 (shutil uses builtins.open),
    # so the injector must fire there — the closest unit-testable seam.
    src = tmp_path / "graph.duckdb"
    src.write_bytes(b"payload")
    dst = tmp_path / "vss_index.duckdb"
    with readonly_fs(dst):
        with pytest.raises(OSError) as ei:
            shutil.copy(src, dst)
        assert ei.value.errno == errno.EROFS


def test_drives_real_retriever_vss_open_seam(tmp_path, monkeypatch, caplog):
    """HTML acceptance line 170: a self-test drives the ACTUAL retriever write
    path under the injector and observes the OSError reaching the call site.

    DuckDbVssSubstrate.open() copies the graph to a scratch dir before building
    an HNSW index (retrieval_substrate.py:333-339). We pin the scratch dir so we
    can arm readonly_fs on the copy target, then assert the injected EROFS
    reaches the shutil.copy call site — where today it is silently swallowed into
    the brute-force fallback (the exact 2026-05-17 class SPR-02 makes fail-loud).
    """
    import substrate.graph.retrieval_substrate as rs

    db = tmp_path / "graph.duckdb"
    import duckdb

    duckdb.connect(str(db)).close()  # a real, readable graph file to copy FROM
    scratch = tmp_path / "vss-scratch"
    scratch.mkdir()
    copy_target = scratch / "vss_index.duckdb"
    # Pin the retriever's internal mkdtemp so copy_target is predictable.
    monkeypatch.setattr(tempfile, "mkdtemp", lambda *a, **k: str(scratch))

    class _StubModel:
        dimension = 8

        def encode(self, xs):  # pragma: no cover - not reached on the copy-fail path
            return [[0.0] * 8 for _ in xs]

    caplog.set_level(logging.WARNING, logger="antiek.retrieval_substrate")
    with readonly_fs(copy_target):
        sub = rs.DuckDbVssSubstrate.open(str(db), model=_StubModel())

    # The injected EROFS reached the real shutil.copy call site: the retriever
    # logged the copy failure and fell back (vss_active False). This documents
    # the silent-swallow SPR-02 will convert into a typed RetrieverInfraError.
    assert "could not copy graph for vss index" in caplog.text
    assert getattr(sub, "vss_active", None) is False


def test_nested_arming_refused_and_outer_recovers(tmp_path):
    # readonly_fs patches process-global primitives, so a second concurrent arm
    # is refused loudly rather than corrupting the shared restore.
    a = tmp_path / "a.idx"
    b = tmp_path / "b.idx"
    with readonly_fs(a):
        with pytest.raises(RuntimeError):
            with readonly_fs(b):
                pass
        # Outer fault is still intact after the refused inner arm.
        with pytest.raises(OSError) as ei:
            open(a, "w")
        assert ei.value.errno == errno.EROFS
    # Outer disarmed cleanly — and a fresh arm works (guard was released).
    with readonly_fs(b):
        with pytest.raises(OSError):
            open(b, "w")
    with open(a, "w") as fh:
        fh.write("ok")
    assert a.read_text() == "ok"
