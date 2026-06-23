"""Tests for the unified ``antiek`` CLI entrypoint (substrate/cli/__main__.py)
plus hooks + compact + queue subcommand dispatchers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# The pi-execution substrate primitives (substrate.conversation / harness /
# the unified CLI subcommands built on them) are an experimental branch NOT
# merged into the four-workflow product. Skip cleanly when absent rather than
# erroring collection (CI runs the full suite). Runs in full once pi-execution
# merges.
pytest.importorskip("substrate.conversation")

from substrate.harness.fork import create_fork

from substrate.cli import __main__ as unified
from substrate.cli.compact import main as compact_main
from substrate.cli.hooks import main as hooks_main


def test_no_args_prints_usage_and_returns_zero(capsys: pytest.CaptureFixture) -> None:
    rc = unified.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "antiek <subcommand>" in out
    for sub in unified.SUBCOMMANDS:
        assert sub in out


def test_unknown_subcommand_returns_nonzero(capsys: pytest.CaptureFixture) -> None:
    rc = unified.main(["nosuch"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "unknown subcommand" in err


def test_help_flag_prints_usage(capsys: pytest.CaptureFixture) -> None:
    rc = unified.main(["--help"])
    assert rc == 0
    assert "antiek <subcommand>" in capsys.readouterr().out


def test_dispatcher_routes_to_harness_status(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = unified.main(["harness", "--project-root", str(tmp_path), "status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "forks (" in out
    assert "snapshots (" in out


def test_dispatcher_routes_to_lint(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    target = tmp_path / "substrate" / "agent" / "bad.py"
    target.parent.mkdir(parents=True)
    target.write_text("def _inject_thing():\n    pass\n")
    rc = unified.main(["lint", str(tmp_path / "substrate"), "--root", str(tmp_path), "--severity", "high"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "_inject_thing" in out


def test_hooks_list_with_no_extensions(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = hooks_main(["--project-root", str(tmp_path), "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "extensions (0)" in out
    assert "declared seams" in out


def test_hooks_list_shows_loaded_fork(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    create_fork("my_fork", tmp_path)
    rc = hooks_main(["--project-root", str(tmp_path), "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "project:my_fork" in out
    assert "[loaded]" in out


def test_hooks_disable_writes_marker(tmp_path: Path) -> None:
    create_fork("doomed", tmp_path)
    rc = hooks_main(["--project-root", str(tmp_path), "disable", "project:doomed"])
    assert rc == 0
    assert (tmp_path / "antiek_extensions" / "doomed" / ".disabled").exists()


def test_hooks_enable_removes_marker(tmp_path: Path) -> None:
    create_fork("revived", tmp_path)
    marker = tmp_path / "antiek_extensions" / "revived" / ".disabled"
    marker.touch()
    rc = hooks_main(["--project-root", str(tmp_path), "enable", "project:revived"])
    assert rc == 0
    assert not marker.exists()


def test_hooks_disable_unknown_extension_fails_clean(tmp_path: Path) -> None:
    rc = hooks_main(["--project-root", str(tmp_path), "disable", "project:nope"])
    assert rc == 2


def test_hooks_disable_bad_scope_format_fails(tmp_path: Path) -> None:
    rc = hooks_main(["--project-root", str(tmp_path), "disable", "no-colon"])
    assert rc == 2


def test_hooks_inspect_loaded_extension(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    create_fork("inspectme", tmp_path)
    rc = hooks_main(["--project-root", str(tmp_path), "inspect", "project:inspectme"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "project:inspectme" in out
    assert "status:" in out


def _seed_active_session(project_root: Path, session_id: str, n_events: int) -> None:
    from substrate.conversation.event import Event
    from substrate.conversation.event_log import EventLog

    log = EventLog(session_id, project_root, fsync_on_append=False)
    for i in range(1, n_events + 1):
        log.append(
            Event(
                position=i,
                ts=f"2026-05-24T00:00:0{i % 10}+00:00",
                kind="user_message",
                payload={"text": f"msg-{i} " * 20},
            )
        )
    active = project_root / ".antiek" / "active_session_id"
    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_text(session_id)


def test_compact_status_against_active_session(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _seed_active_session(tmp_path, "sess-1", n_events=5)
    rc = compact_main(
        ["--project-root", str(tmp_path), "--context-window", "1000", "status", "--json"]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["session"] == "sess-1"
    assert data["events"] == 5
    assert data["current_tokens"] > 0


def test_compact_status_without_active_session_fails(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = compact_main(["--project-root", str(tmp_path), "status"])
    assert rc == 2
    assert "no active session" in capsys.readouterr().err


def test_compact_run_strict_returns_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _seed_active_session(tmp_path, "sess-strict", n_events=10)
    rc = compact_main(
        [
            "--project-root", str(tmp_path),
            "--context-window", "10",
            "run", "--policy", "strict",
        ]
    )
    assert rc == 3
    err = capsys.readouterr().err
    assert "STRICT raised" in err


def test_compact_run_lossy_creates_branch(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _seed_active_session(tmp_path, "sess-lossy", n_events=20)
    rc = compact_main(
        [
            "--project-root", str(tmp_path),
            "--context-window", "10",
            "run", "--policy", "lossy", "--json",
        ]
    )
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["pre_compaction_branch"] is not None
    assert data["n_summarized"] > 0
