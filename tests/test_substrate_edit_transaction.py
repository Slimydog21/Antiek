"""Tests for substrate/edit/transaction -- the no-mid-flight invariant headlines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from substrate.edit import (
    EditTransaction,
    FileNotReserved,
    TransactionAlreadyCommitted,
    TransactionNotEntered,
    declare_edit_validator_seam,
    edit_validator_seam_id,
)
from substrate.hooks import HookContext, HookRegistry
from substrate.observability.burn import BurnRecorder
from substrate.observability.burn_context import (
    BurnContext,
    reset_burn_context,
    set_burn_context,
)


@pytest.fixture(autouse=True)
def _reset_burn():
    BurnRecorder._reset_instances()
    yield
    BurnRecorder._reset_instances()


@pytest.fixture
def registry() -> HookRegistry:
    r = HookRegistry()
    declare_edit_validator_seam(r)
    return r


def test_no_mid_flight_validation(tmp_path: Path, registry: HookRegistry) -> None:
    """Headline invariant. Validator must run exactly ONCE per commit."""
    f = tmp_path / "a.txt"
    f.write_text("AAA BBB CCC")
    call_count = 0
    paths_seen: list[list[Path]] = []

    class _Validator:
        def __call__(self, ctx: HookContext, result: list[str], *, paths: list[Path]) -> list[str]:
            nonlocal call_count
            call_count += 1
            paths_seen.append(list(paths))
            return list(result)

    registry.register_hook(edit_validator_seam_id(), _Validator(), "post", "validator-1")

    with EditTransaction([f], registry=registry) as tx:
        tx.edit(f, "AAA", "111")
        tx.edit(f, "BBB", "222")
        tx.edit(f, "CCC", "333")
        result = tx.commit()

    assert call_count == 1, "validator must run exactly once at commit"
    assert paths_seen == [[f.resolve()]]
    assert result.committed
    assert f.read_text() == "111 222 333"


def test_unreserved_path_raises(tmp_path: Path, registry: HookRegistry) -> None:
    a = tmp_path / "a.txt"
    a.write_text("hello")
    b = tmp_path / "b.txt"
    b.write_text("world")
    with EditTransaction([a], registry=registry) as tx:
        with pytest.raises(FileNotReserved, match="b.txt"):
            tx.edit(b, "world", "WORLD")


def test_edit_before_enter_raises(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x")
    tx = EditTransaction([f])
    with pytest.raises(TransactionNotEntered):
        tx.edit(f, "x", "y")


def test_edit_after_commit_raises(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x")
    with EditTransaction([f]) as tx:
        tx.edit(f, "x", "y")
        tx.commit()
        with pytest.raises(TransactionAlreadyCommitted):
            tx.edit(f, "y", "z")


def test_commit_before_enter_raises(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x")
    tx = EditTransaction([f])
    with pytest.raises(TransactionNotEntered):
        tx.commit()


def test_double_commit_raises(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x")
    with EditTransaction([f]) as tx:
        tx.edit(f, "x", "y")
        tx.commit()
        with pytest.raises(TransactionAlreadyCommitted):
            tx.commit()


def test_old_str_not_found_rolls_back_all_edits(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("AAA")
    b.write_text("BBB")
    with EditTransaction([a, b]) as tx:
        tx.edit(a, "AAA", "111")
        tx.edit(b, "NOT-PRESENT", "won't apply")
        result = tx.commit()
    assert not result.committed
    assert result.rolled_back
    assert result.error == "OldStringNotFound"
    assert a.read_text() == "AAA"
    assert b.read_text() == "BBB"


def test_empty_old_str_rejected(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x")
    with EditTransaction([f]) as tx:
        with pytest.raises(ValueError, match="old_str must not be empty"):
            tx.edit(f, "", "hello")


def test_rollback_restores_unedited_files_to_snapshot(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("AAA")
    b.write_text("BBB")
    with EditTransaction([a, b]) as tx:
        tx.edit(a, "AAA", "111")
        tx.commit()
    assert a.read_text() == "111"
    assert b.read_text() == "BBB"


def test_explicit_rollback_inside_with_block(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("original")
    with EditTransaction([f]) as tx:
        tx.edit(f, "original", "changed")
        r = tx.commit()
        assert r.committed
        assert f.read_text() == "changed"
        tx.rollback()
        assert f.read_text() == "original"


def test_exception_in_with_block_triggers_rollback(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("original")
    with pytest.raises(RuntimeError, match="boom"):
        with EditTransaction([f]) as tx:
            tx.edit(f, "original", "changed")
            raise RuntimeError("boom")
    assert f.read_text() == "original"


def test_first_occurrence_default(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("foo foo foo")
    with EditTransaction([f]) as tx:
        tx.edit(f, "foo", "BAR")
        tx.commit()
    assert f.read_text() == "BAR foo foo"


def test_second_occurrence_explicit(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("foo foo foo")
    with EditTransaction([f]) as tx:
        tx.edit(f, "foo", "BAR", occurrence=2)
        tx.commit()
    assert f.read_text() == "foo BAR foo"


def test_occurrence_beyond_count_fails(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("foo foo")
    with EditTransaction([f]) as tx:
        tx.edit(f, "foo", "BAR", occurrence=5)
        result = tx.commit()
    assert not result.committed
    assert f.read_text() == "foo foo"


def test_occurrence_zero_raises(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x")
    with EditTransaction([f]) as tx:
        with pytest.raises(ValueError, match="occurrence must be >= 1"):
            tx.edit(f, "x", "y", occurrence=0)


def test_amend_after_commit_allows_more_edits(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("aaa bbb")
    with EditTransaction([f]) as tx:
        tx.edit(f, "aaa", "111")
        tx.commit()
        assert f.read_text() == "111 bbb"
        tx.amend()
        tx.edit(f, "bbb", "222")
        tx.commit()
        assert f.read_text() == "111 222"


def test_validators_run_in_priority_order(tmp_path: Path, registry: HookRegistry) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x")
    order: list[str] = []

    class _V:
        def __init__(self, tag: str, errs: list[str]) -> None:
            self.tag = tag
            self.errs = errs

        def __call__(self, ctx: HookContext, result: list[str], *, paths: list[Path]) -> list[str]:
            order.append(self.tag)
            return list(result) + self.errs

    registry.register_hook(edit_validator_seam_id(), _V("late", ["late-err"]), "post", "v-late", priority=10)
    registry.register_hook(edit_validator_seam_id(), _V("early", ["early-err"]), "post", "v-early", priority=1)

    with EditTransaction([f], registry=registry) as tx:
        tx.edit(f, "x", "y")
        r = tx.commit()
    assert order == ["early", "late"]
    assert r.validation_errors == ("early-err", "late-err")


def test_no_validators_means_no_errors(tmp_path: Path, registry: HookRegistry) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x")
    with EditTransaction([f], registry=registry) as tx:
        tx.edit(f, "x", "y")
        r = tx.commit()
    assert r.validation_errors == ()
    assert r.committed


def test_commit_emits_burn_event(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x")
    ctx = BurnContext(session_id="s1", project_root=tmp_path, project_id="p1")
    token = set_burn_context(ctx)
    try:
        with EditTransaction([f]) as tx:
            tx.edit(f, "x", "y")
            tx.commit()
    finally:
        reset_burn_context(token)

    recorder = BurnRecorder.for_project(tmp_path)
    rows = recorder.query("SELECT * FROM burn_events WHERE tool_id='edit_transaction'")
    assert len(rows) == 1
    assert rows[0]["input_tokens"] == 1
    assert rows[0]["output_tokens"] == 1
    assert rows[0]["error"] is None


def test_failed_commit_emits_burn_with_error(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("foo")
    ctx = BurnContext(session_id="s1", project_root=tmp_path)
    token = set_burn_context(ctx)
    try:
        with EditTransaction([f]) as tx:
            tx.edit(f, "NOT-PRESENT", "fail")
            tx.commit()
    finally:
        reset_burn_context(token)

    recorder = BurnRecorder.for_project(tmp_path)
    rows = recorder.query("SELECT * FROM burn_events WHERE tool_id='edit_transaction'")
    assert len(rows) == 1
    assert rows[0]["error"] is not None
    assert "old_str not found" in rows[0]["error"]
