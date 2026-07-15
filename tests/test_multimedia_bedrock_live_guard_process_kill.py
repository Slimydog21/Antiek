from __future__ import annotations

import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.helpers.live_guard_process_kill_child import _identity

_CHILD = Path(__file__).parent / "helpers" / "live_guard_process_kill_child.py"
_JOURNAL_EXPECTATIONS = {
    "after_command_insert": "absent",
    "after_attempt_insert": "absent",
    "before_intent_commit": "absent",
    "after_intent_commit": "in_progress",
    "after_completion_insert": "in_progress",
    "before_completion_commit": "in_progress",
    "after_completion_commit": "completed",
}
_ACQUISITION_STAGES = (
    "after_intent_commit",
    "before_initial_scp_describe",
    "before_initial_scp_targets",
    "before_initial_rcp_describe",
    "before_initial_rcp_targets",
    "before_attestation",
    "before_qualification",
    "before_final_scp_describe",
    "before_final_scp_targets",
    "before_final_rcp_describe",
    "before_final_rcp_targets",
    "before_revocation",
    "before_revocation_verify",
    "after_completion_insert",
    "before_completion_commit",
    "after_completion_commit",
)


def _private(path: Path) -> Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _environment() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(Path(__file__).parents[1]),
    }


def _child_command(mode: str, root: Path, *extra: str) -> list[str]:
    return [sys.executable, str(_CHILD), mode, "--root", str(root), *extra]


def _kill_at_checkpoint(
    *, mode: str, stage: str, root: Path, control: Path
) -> dict[str, object]:
    process = subprocess.Popen(
        _child_command(
            mode,
            root,
            "--control-root",
            str(control),
            "--stage",
            stage,
        ),
        cwd=Path(__file__).parents[1],
        env=_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    marker = control / "checkpoint.json"
    ready = control / "checkpoint.ready.json"
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and not ready.exists() and process.poll() is None:
        time.sleep(0.01)
    if not ready.exists():
        stdout, stderr = process.communicate(timeout=2)
        pytest.fail(
            f"checkpoint {mode}:{stage} was not reached; rc={process.returncode}; "
            f"stdout={stdout!r}; stderr={stderr!r}"
        )
    ready_payload, _ = _read_marker(ready)
    payload, marker_raw = _read_marker(marker)
    assert ready_payload == {
        "checkpoint": stage,
        "marker_digest": hashlib.sha256(marker_raw).hexdigest(),
        "pid": process.pid,
        "schema_version": 1,
    }
    expected_attempt_id = _identity()[2].attempt_id
    assert payload == {
        "attempt_id": expected_attempt_id,
        "checkpoint": stage,
        "command_id": "lgc_" + "b" * 32,
        "mode": mode,
        "pid": process.pid,
        "receipt_digest": payload["receipt_digest"],
        "schema_version": 1,
    }
    process.kill()
    stdout, stderr = process.communicate(timeout=4)
    assert stdout == ""
    assert stderr == ""
    assert process.returncode == -signal.SIGKILL
    return payload


def _read_marker(
    marker: Path, *, after_open: Callable[[], None] | None = None
) -> tuple[dict[str, object], bytes]:
    descriptor = os.open(marker, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(descriptor)
        assert stat.S_ISREG(metadata.st_mode)
        assert metadata.st_uid == os.getuid()
        assert metadata.st_nlink == 1
        assert stat.S_IMODE(metadata.st_mode) == 0o600
        raw = os.read(descriptor, 4097)
        assert len(raw) <= 4096
        assert os.read(descriptor, 1) == b""
        if after_open is not None:
            after_open()
        reopened = marker.stat(follow_symlinks=False)
        assert (reopened.st_dev, reopened.st_ino) == (metadata.st_dev, metadata.st_ino)
    finally:
        os.close(descriptor)
    value = json.loads(raw.decode("ascii"))
    assert type(value) is dict
    assert json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii") == raw
    return value, raw


def _run_json(mode: str, root: Path) -> dict[str, object]:
    result = subprocess.run(
        _child_command(mode, root),
        cwd=Path(__file__).parents[1],
        env=_environment(),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    value = json.loads(result.stdout)
    assert type(value) is dict
    return value


def _snapshot_tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.mark.parametrize(("stage", "expected"), _JOURNAL_EXPECTATIONS.items())
def test_real_sigkill_journal_matrix_reopens_exact_state(
    tmp_path: Path, stage: str, expected: str
) -> None:
    root = _private(tmp_path / "journal")
    control = _private(tmp_path / "control")
    payload = _kill_at_checkpoint(mode="journal", stage=stage, root=root, control=control)
    inspected = _run_json("inspect", root)
    assert inspected["status"] == expected
    assert inspected["production_eligible"] is False
    if expected == "absent":
        assert (
            inspected["command_count"],
            inspected["attempt_count"],
            inspected["completion_count"],
        ) == (0, 0, 0)
    elif expected == "in_progress":
        assert (inspected["command_count"], inspected["attempt_count"]) == (1, 1)
        assert inspected["completion_count"] == 0
        recovered = _run_json("recover", root)
        assert recovered["recovery"] == "completed"
        assert recovered["attempt_id"] == inspected["attempt_id"]
        assert recovered["completed_at"] == "2026-07-15T01:00:30Z"
        assert recovered["trusted_start"] == "2026-07-15T01:00:00Z"
        assert recovered["revocation_observed_at"] == "2026-07-15T01:00:30Z"
        assert recovered["external_call_count"] == 11
        assert _run_json("inspect", root)["status"] == "completed"
    else:
        assert (
            inspected["command_count"],
            inspected["attempt_count"],
            inspected["completion_count"],
        ) == (1, 1, 1)
        assert inspected["receipt_digest"] == payload["receipt_digest"]
        assert _run_json("recover", root) == {
            "external_call_count": 0,
            "recovery": "historical",
        }


@pytest.mark.parametrize("stage", _ACQUISITION_STAGES)
def test_real_sigkill_acquisition_matrix_recovers_or_classifies_history(
    tmp_path: Path, stage: str
) -> None:
    root = _private(tmp_path / "journal")
    control = _private(tmp_path / "control")
    payload = _kill_at_checkpoint(mode="acquire", stage=stage, root=root, control=control)
    inspected = _run_json("inspect", root)
    if stage == "after_completion_commit":
        assert (
            inspected["command_count"],
            inspected["attempt_count"],
            inspected["completion_count"],
        ) == (1, 1, 1)
        assert inspected["status"] == "completed"
        assert inspected["receipt_digest"] == payload["receipt_digest"]
        assert _run_json("recover", root) == {
            "external_call_count": 0,
            "recovery": "historical",
        }
    else:
        assert (
            inspected["command_count"],
            inspected["attempt_count"],
            inspected["completion_count"],
        ) == (1, 1, 0)
        assert inspected["status"] == "in_progress"
        recovered = _run_json("recover", root)
        assert recovered["recovery"] == "completed"
        assert recovered["attempt_id"] == inspected["attempt_id"]
        assert recovered["completed_at"] == "2026-07-15T01:00:30Z"
        assert recovered["trusted_start"] == "2026-07-15T01:00:00Z"
        assert recovered["revocation_observed_at"] == "2026-07-15T01:00:30Z"
        assert recovered["external_call_count"] == 11
        final = _run_json("inspect", root)
        assert final["status"] == "completed"
        assert final["completion_count"] == 1


def test_unsupported_checkpoint_exits_without_marker_or_journal_rows(tmp_path: Path) -> None:
    root = _private(tmp_path / "journal")
    control = _private(tmp_path / "control")
    result = subprocess.run(
        _child_command(
            "journal",
            root,
            "--control-root",
            str(control),
            "--stage",
            "not-allowed",
        ),
        cwd=Path(__file__).parents[1],
        env=_environment(),
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "controlled child failure: ValueError\n"
    assert not (control / "checkpoint.json").exists()
    assert not (control / "checkpoint.ready.json").exists()
    assert not (root / "live-guard-acquisition.sqlite3").exists()


@pytest.mark.parametrize("kind", ["file", "symlink", "hardlink"])
def test_existing_or_unsafe_marker_fails_without_blocking(tmp_path: Path, kind: str) -> None:
    root = _private(tmp_path / "journal")
    control = _private(tmp_path / "control")
    marker = control / "checkpoint.json"
    target = control / "target"
    target.write_text("stale", encoding="ascii")
    target.chmod(0o600)
    if kind == "file":
        os.replace(target, marker)
    elif kind == "symlink":
        marker.symlink_to(target)
    else:
        os.link(target, marker)
    result = subprocess.run(
        _child_command(
            "journal",
            root,
            "--control-root",
            str(control),
            "--stage",
            "after_command_insert",
        ),
        cwd=Path(__file__).parents[1],
        env=_environment(),
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "controlled child failure: LiveGuardJournalError\n"
    assert not (control / "checkpoint.ready.json").exists()
    inspected = _run_json("inspect", root)
    assert inspected["status"] == "absent"


def test_marker_reader_rejects_permissive_mode_and_path_replacement(tmp_path: Path) -> None:
    control = _private(tmp_path / "control")
    marker = control / "checkpoint.json"
    raw = b'{"schema_version":1}'
    marker.write_bytes(raw)
    marker.chmod(0o644)
    with pytest.raises(AssertionError):
        _read_marker(marker)
    marker.chmod(0o600)
    replacement = control / "replacement"
    replacement.write_bytes(raw)
    replacement.chmod(0o600)
    with pytest.raises(AssertionError):
        _read_marker(marker, after_open=lambda: os.replace(replacement, marker))


def test_repeated_fresh_inspection_is_byte_preserving(tmp_path: Path) -> None:
    root = _private(tmp_path / "journal")
    control = _private(tmp_path / "control")
    _kill_at_checkpoint(
        mode="acquire", stage="after_intent_commit", root=root, control=control
    )
    before = _snapshot_tree(root)
    first = _run_json("inspect", root)
    middle = _snapshot_tree(root)
    second = _run_json("inspect", root)
    after = _snapshot_tree(root)
    assert first == second
    assert before == middle == after


def test_production_modules_do_not_import_process_kill_helper() -> None:
    substrate = Path(__file__).parents[1] / "substrate"
    needle = "live_guard_process_kill_child"
    assert all(needle not in path.read_text("utf-8") for path in substrate.rglob("*.py"))
