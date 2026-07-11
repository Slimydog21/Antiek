from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import stat
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

import pytest

from substrate.event_log.run_durability_port import RunDurabilityEventLogPort
from substrate.run_durability import (
    Checkpoint,
    CheckpointKind,
    ConcurrentAppendError,
    EventKind,
    FakeDurableRunner,
    TraceError,
    TraceEvent,
)
from substrate.run_durability.trace import GENESIS_HASH

BRIEF: Final = "b" * 64
RUN_ID: Final = "run:durable-1"


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 11, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self.value
        self.value += timedelta(microseconds=1)
        return value


def runner(root: Path, *, run_id: str = RUN_ID) -> FakeDurableRunner:
    return FakeDurableRunner(
        RunDurabilityEventLogPort(root), run_id=run_id, approved_brief_hash=BRIEF, clock=Clock()
    )


def run_dir(root: Path, run_id: str = RUN_ID) -> Path:
    return root / hashlib.sha256(run_id.encode()).hexdigest()


def event(sequence: int = 0, *, run_id: str = RUN_ID) -> TraceEvent:
    previous_hash = GENESIS_HASH
    for index in range(sequence):
        previous_hash = event(index, run_id=run_id).event_hash
    return TraceEvent.create(
        run_id=run_id,
        approved_brief_hash=BRIEF,
        sequence=sequence,
        kind=EventKind.RUN_STARTED if sequence == 0 else EventKind.STEP_RECORDED,
        occurred_at=datetime(2026, 7, 11, tzinfo=UTC) + timedelta(microseconds=sequence),
        data={} if sequence == 0 else {"step_ref": f"step:{sequence}"},
        previous_hash=previous_hash,
    )


def _compete(root: str, raw: bytes, gate: multiprocessing.synchronize.Barrier, out: object) -> None:
    port = RunDurabilityEventLogPort(root)
    item = TraceEvent.from_json(raw)
    gate.wait()
    try:
        port.append(item, expected_sequence=0)
        out.put("won")  # type: ignore[attr-defined]
    except ConcurrentAppendError:
        out.put("lost")  # type: ignore[attr-defined]


def _append_then_exit(root: str, raw: bytes) -> None:
    RunDurabilityEventLogPort(root).append(TraceEvent.from_json(raw), expected_sequence=0)
    os._exit(0)


def test_fake_runner_conformance_reopen_checkpoints_and_canonical_bytes(tmp_path: Path) -> None:
    first = runner(tmp_path / "private")
    first.start()
    for kind in CheckpointKind:
        first.checkpoint(Checkpoint(kind, {"artifact_ref": f"artifact:{kind.value}"}))
    reopened = runner(tmp_path / "private")
    assert reopened.view == first.view
    rows = tuple(reopened.port.read(RUN_ID))
    directory = run_dir(tmp_path / "private")
    assert directory.name != RUN_ID
    assert sorted(path.name for path in directory.iterdir()) == [
        f"{index:020d}.json" for index in range(len(rows))
    ]
    assert [path.read_bytes() for path in sorted(directory.iterdir())] == [
        row.to_json() for row in rows
    ]


def test_fake_runner_completion_is_reconstructed_after_reopen(tmp_path: Path) -> None:
    first = runner(tmp_path / "root")
    first.start()
    first.step("step:one")
    completed = first.complete()
    reopened = runner(tmp_path / "root")
    assert reopened.view == completed
    assert reopened.view is not None and reopened.view.completed
    assert reopened.view.report_ref == completed.report_ref


def test_subprocess_hard_exit_after_append_reopens_exactly(tmp_path: Path) -> None:
    root = tmp_path / "root"
    process = multiprocessing.get_context("spawn").Process(
        target=_append_then_exit, args=(str(root), event().to_json())
    )
    process.start()
    process.join(10)
    assert process.exitcode == 0
    assert tuple(RunDurabilityEventLogPort(root).read(RUN_ID)) == (event(),)


def test_two_processes_preparing_same_sequence_exactly_one_wins(tmp_path: Path) -> None:
    root = tmp_path / "root"
    raw = event().to_json()
    context = multiprocessing.get_context("spawn")
    gate = context.Barrier(2)
    out = context.Queue()
    processes = [
        context.Process(target=_compete, args=(str(root), raw, gate, out)) for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(10)
        assert process.exitcode == 0
    assert sorted([out.get(timeout=2), out.get(timeout=2)]) == ["lost", "won"]
    assert tuple(RunDurabilityEventLogPort(root).read(RUN_ID)) == (event(),)


def test_exact_temp_is_ignored_before_and_after_publication(tmp_path: Path) -> None:
    root = tmp_path / "root"
    port = RunDurabilityEventLogPort(root)
    directory = run_dir(root)
    directory.mkdir(mode=0o700)
    temp = directory / (".eventlog-tmp-00000000000000000000-" + "a" * 64)
    temp.write_bytes(b"{partial")
    temp.chmod(0o600)
    assert port.read(RUN_ID) == ()
    final = directory / "00000000000000000000.json"
    final.write_bytes(event().to_json())
    final.chmod(0o600)
    temp.write_bytes(event().to_json())
    assert tuple(port.read(RUN_ID)) == (event(),)


def test_post_link_crash_alias_is_a_valid_published_event(tmp_path: Path) -> None:
    root = tmp_path / "root"
    port = RunDurabilityEventLogPort(root)
    directory = run_dir(root)
    directory.mkdir(mode=0o700)
    temp = directory / (".eventlog-tmp-00000000000000000000-" + "a" * 64)
    temp.write_bytes(event().to_json())
    temp.chmod(0o600)
    final = directory / "00000000000000000000.json"
    os.link(temp, final)
    assert temp.stat().st_ino == final.stat().st_ino
    assert temp.stat().st_nlink == 2
    assert tuple(port.read(RUN_ID)) == (event(),)


def test_many_proven_post_link_aliases_do_not_exhaust_temp_budget(tmp_path: Path) -> None:
    root = tmp_path / "root"
    port = RunDurabilityEventLogPort(root, max_temp_files=1, max_temp_bytes=1)
    directory = run_dir(root)
    directory.mkdir(mode=0o700)
    items: list[TraceEvent] = []
    previous = GENESIS_HASH
    for sequence in range(33):
        item = TraceEvent.create(
            run_id=RUN_ID,
            approved_brief_hash=BRIEF,
            sequence=sequence,
            kind=EventKind.RUN_STARTED if sequence == 0 else EventKind.STEP_RECORDED,
            occurred_at=datetime(2026, 7, 11, tzinfo=UTC) + timedelta(microseconds=sequence),
            data={} if sequence == 0 else {"step_ref": f"step:{sequence}"},
            previous_hash=previous,
        )
        items.append(item)
        previous = item.event_hash
    expected = tuple(items)
    for item in expected:
        temp = directory / (f".eventlog-tmp-{item.sequence:020d}-" + f"{item.sequence:064x}")
        temp.write_bytes(item.to_json())
        temp.chmod(0o600)
        os.link(temp, directory / f"{item.sequence:020d}.json")
    assert tuple(port.read(RUN_ID)) == expected


def test_run_directory_replacement_is_rejected_by_live_adapter(tmp_path: Path) -> None:
    root = tmp_path / "root"
    port = RunDurabilityEventLogPort(root)
    port.append(event(), expected_sequence=0)
    original = run_dir(root)
    displaced = root / "displaced"
    original.rename(displaced)
    original.mkdir(mode=0o700)
    replacement = original / "00000000000000000000.json"
    replacement.write_bytes(event().to_json())
    replacement.chmod(0o600)
    with pytest.raises(TraceError, match="run directory changed"):
        port.read(RUN_ID)


def test_temp_budget_and_grammar_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    port = RunDurabilityEventLogPort(root, max_temp_files=1, max_temp_bytes=8)
    directory = run_dir(root)
    directory.mkdir(mode=0o700)
    first_temp = directory / (".eventlog-tmp-00000000000000000000-" + "a" * 64)
    first_temp.write_bytes(b"12345678")
    first_temp.chmod(0o600)
    assert port.read(RUN_ID) == ()
    second_temp = directory / (".eventlog-tmp-00000000000000000000-" + "b" * 64)
    second_temp.touch(mode=0o600)
    with pytest.raises(TraceError, match="budget"):
        port.read(RUN_ID)
    for path in directory.iterdir():
        path.unlink()
    (directory / ".eventlog-tmp-bad").touch()
    with pytest.raises(TraceError, match="unexpected"):
        port.read(RUN_ID)


@pytest.mark.parametrize("name", ["00000000000000000001.json", "extra", "000.json"])
def test_gap_alias_and_extra_files_fail(tmp_path: Path, name: str) -> None:
    root = tmp_path / "root"
    port = RunDurabilityEventLogPort(root)
    directory = run_dir(root)
    directory.mkdir(mode=0o700)
    (directory / name).write_bytes(event().to_json())
    with pytest.raises(TraceError):
        port.read(RUN_ID)


def test_corrupt_noncanonical_cross_run_cross_brief_and_fork_fail(tmp_path: Path) -> None:
    mutators: list[Callable[[bytes], bytes]] = [
        lambda raw: b"{",
        lambda raw: json.dumps(json.loads(raw), indent=2).encode(),
        lambda raw: raw.replace(RUN_ID.encode(), b"run:other-01"),
        lambda raw: raw.replace(BRIEF.encode(), ("c" * 64).encode()),
        lambda raw: raw.replace(GENESIS_HASH.encode(), ("1" * 64).encode(), 1),
    ]
    for index, mutate in enumerate(mutators):
        root = tmp_path / str(index)
        port = RunDurabilityEventLogPort(root)
        directory = run_dir(root)
        directory.mkdir(mode=0o700)
        target = directory / "00000000000000000000.json"
        target.write_bytes(mutate(event().to_json()))
        target.chmod(0o600)
        with pytest.raises(TraceError):
            port.read(RUN_ID)


@pytest.mark.parametrize(
    "raw",
    [b"\xff", b'{"run_id":"one","run_id":"two"}'],
)
def test_invalid_utf8_and_duplicate_json_fail_closed(tmp_path: Path, raw: bytes) -> None:
    root = tmp_path / "root"
    RunDurabilityEventLogPort(root)
    directory = run_dir(root)
    directory.mkdir(mode=0o700)
    target = directory / "00000000000000000000.json"
    target.write_bytes(raw)
    target.chmod(0o600)
    with pytest.raises(TraceError):
        RunDurabilityEventLogPort(root).read(RUN_ID)


@pytest.mark.parametrize("entry_kind", ["symlink", "fifo"])
def test_symlink_and_fifo_entries_fail(tmp_path: Path, entry_kind: str) -> None:
    root = tmp_path / "root"
    port = RunDurabilityEventLogPort(root)
    directory = run_dir(root)
    directory.mkdir(mode=0o700)
    target = directory / "00000000000000000000.json"
    if entry_kind == "symlink":
        target.symlink_to(tmp_path / "elsewhere")
    else:
        os.mkfifo(target)
    with pytest.raises(TraceError, match="regular"):
        port.read(RUN_ID)


def test_root_run_permissions_and_path_attacks_fail(tmp_path: Path) -> None:
    root = tmp_path / "root"
    port = RunDurabilityEventLogPort(root)
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    os.chmod(root, 0o755)
    with pytest.raises(TraceError, match="accessible"):
        port.read(RUN_ID)
    os.chmod(root, 0o700)
    runner(root).start()
    os.chmod(run_dir(root), 0o770)
    with pytest.raises(TraceError, match="accessible"):
        port.read(RUN_ID)
    for unsafe in ("../escape", "/absolute", "dot dot", "", "a" * 256):
        with pytest.raises(ValueError):
            port.read(unsafe)


def test_root_and_run_symlinks_are_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    root_link = tmp_path / "root-link"
    root_link.symlink_to(real, target_is_directory=True)
    with pytest.raises(TraceError):
        RunDurabilityEventLogPort(root_link)
    root = tmp_path / "root"
    port = RunDurabilityEventLogPort(root)
    run_dir(root).symlink_to(real, target_is_directory=True)
    with pytest.raises(TraceError):
        port.read(RUN_ID)


def test_committed_modes_hardlinks_and_canonical_filename(tmp_path: Path) -> None:
    root = tmp_path / "root"
    port = RunDurabilityEventLogPort(root)
    port.append(event(), expected_sequence=0)
    target = run_dir(root) / "00000000000000000000.json"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    external = tmp_path / "external"
    os.link(target, external)
    with pytest.raises(TraceError, match="hard link"):
        port.read(RUN_ID)
    external.unlink()
    target.chmod(0o640)
    with pytest.raises(TraceError, match="0600"):
        port.read(RUN_ID)


@pytest.mark.parametrize("expected", [True, -1, 2**200])
def test_malicious_expected_sequence_rejected(tmp_path: Path, expected: int) -> None:
    port = RunDurabilityEventLogPort(tmp_path / "root")
    with pytest.raises(ConcurrentAppendError):
        port.append(event(), expected_sequence=expected)
    assert port.read(RUN_ID) == ()


def test_count_event_and_total_byte_limits(tmp_path: Path) -> None:
    too_small = RunDurabilityEventLogPort(tmp_path / "small", max_event_bytes=10)
    with pytest.raises(TraceError, match="event exceeds"):
        too_small.append(event(), expected_sequence=0)
    count = RunDurabilityEventLogPort(tmp_path / "count", max_events_per_run=1)
    first = event()
    count.append(first, expected_sequence=0)
    second = TraceEvent.create(
        run_id=RUN_ID,
        approved_brief_hash=BRIEF,
        sequence=1,
        kind=EventKind.STEP_RECORDED,
        occurred_at=datetime(2026, 7, 11, 0, 0, 0, 1, tzinfo=UTC),
        data={"step_ref": "step:1"},
        previous_hash=first.event_hash,
    )
    with pytest.raises(TraceError, match="count"):
        count.append(second, expected_sequence=1)
    total = RunDurabilityEventLogPort(
        tmp_path / "bytes",
        max_event_bytes=len(first.to_json()),
        max_run_bytes=len(first.to_json()),
    )
    total.append(first, expected_sequence=0)
    with pytest.raises(TraceError, match="byte"):
        total.append(second, expected_sequence=1)


def test_publication_failure_cleans_temp_and_never_reports_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    port = RunDurabilityEventLogPort(root)

    def fail_link(*args: object, **kwargs: object) -> None:
        raise OSError("injected publication failure")

    monkeypatch.setattr(os, "link", fail_link)
    with pytest.raises(OSError, match="injected"):
        port.append(event(), expected_sequence=0)
    assert port.read(RUN_ID) == ()
    assert list(run_dir(root).iterdir()) == []


def test_short_write_and_file_fsync_failure_leave_no_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    port = RunDurabilityEventLogPort(root)
    real_write = os.write
    calls = 0

    def short_write(fd: int, data: object) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            view = memoryview(data)  # type: ignore[arg-type]
            return real_write(fd, view[: max(1, len(view) // 2)])
        return 0

    monkeypatch.setattr(os, "write", short_write)
    with pytest.raises(OSError, match="short event write"):
        port.append(event(), expected_sequence=0)
    monkeypatch.setattr(os, "write", real_write)
    real_fsync = os.fsync

    def fail_file_fsync(fd: int) -> None:
        if stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("injected file fsync failure")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_file_fsync)
    with pytest.raises(OSError, match="file fsync"):
        port.append(event(), expected_sequence=0)
    assert port.read(RUN_ID) == ()


def test_post_publication_fsync_and_cleanup_failures_never_report_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "fsync"
    port = RunDurabilityEventLogPort(root)
    run_dir(root).mkdir(mode=0o700)
    real_fsync = os.fsync
    directory_syncs = 0

    def fail_publication_sync(fd: int) -> None:
        nonlocal directory_syncs
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            directory_syncs += 1
            if directory_syncs == 1:
                raise OSError("injected publication fsync failure")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_publication_sync)
    with pytest.raises(TraceError, match="publication|published"):
        port.append(event(), expected_sequence=0)
    monkeypatch.setattr(os, "fsync", real_fsync)
    assert tuple(port.read(RUN_ID)) == (event(),)

    cleanup_root = tmp_path / "cleanup"
    cleanup_port = RunDurabilityEventLogPort(cleanup_root)
    real_unlink = os.unlink

    def fail_temp_cleanup(path: object, *args: object, **kwargs: object) -> None:
        if isinstance(path, str) and path.startswith(".eventlog-tmp-"):
            raise OSError("injected cleanup failure")
        real_unlink(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "unlink", fail_temp_cleanup)
    with pytest.raises(TraceError, match="publication|published"):
        cleanup_port.append(event(), expected_sequence=0)


def test_existing_final_is_never_overwritten(tmp_path: Path) -> None:
    root = tmp_path / "root"
    port = RunDurabilityEventLogPort(root)
    original = event()
    port.append(original, expected_sequence=0)
    raw = (run_dir(root) / "00000000000000000000.json").read_bytes()
    with pytest.raises(ConcurrentAppendError):
        port.append(original, expected_sequence=0)
    assert (run_dir(root) / "00000000000000000000.json").read_bytes() == raw


def test_scope_has_no_prohibited_authority_imports() -> None:
    source = Path("substrate/event_log/run_durability_port.py").read_text()
    for prohibited in (
        "substrate.event_log.events",
        "sqlite",
        "duckdb",
        "runtime",
        "orchestration",
        "midnight_oil",
    ):
        assert prohibited not in source.lower()
