"""Tests for tools.antiek_cli.check.

Covers StageResult flags, parser shape, the skip behaviors of runners
whose backing files/dirs are missing, _run's tool-not-found fallback,
and the all-subcommand orchestration semantics. Mocks the underlying
runners — does not exercise real subprocesses.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tools.antiek_cli.check import (
    ALL_ORDER,
    DEFAULT_SCOPE,
    RUNNERS,
    StageResult,
    _build_parser,
    _run,
    _run_all,
    main,
    run_invariants,
    run_props,
)


def test_stage_pass_flags() -> None:
    r = StageResult(name="t", rc=0, elapsed_s=0.5)
    assert r.is_pass and not r.is_fail and not r.is_skip


def test_stage_fail_flags() -> None:
    r = StageResult(name="t", rc=1, elapsed_s=0.5)
    assert r.is_fail and not r.is_pass


def test_stage_skip_flags() -> None:
    r = StageResult(name="t", rc=-1, elapsed_s=0.0, skipped_reason="x")
    assert r.is_skip and not r.is_pass and not r.is_fail


def test_format_pass() -> None:
    s = StageResult("lint", 0, 0.42).format_report_line()
    assert "lint" in s and "PASS" in s and "0.42s" in s


def test_format_fail() -> None:
    s = StageResult("types", 2, 1.10).format_report_line()
    assert "FAIL" in s


def test_format_skip() -> None:
    s = StageResult("props", -1, 0.0, skipped_reason="no dir").format_report_line()
    assert "SKIP" in s and "no dir" in s


def test_parser_subcommands() -> None:
    parser = _build_parser()
    for name in (*RUNNERS.keys(), "all"):
        args = parser.parse_args([name])
        assert args.cmd == name


def test_parser_default_scope() -> None:
    args = _build_parser().parse_args(["lint"])
    assert args.scope == DEFAULT_SCOPE


def test_parser_scope_override() -> None:
    args = _build_parser().parse_args(["types", "--scope", "substrate/x.py"])
    assert args.scope == "substrate/x.py"


def test_parser_strict() -> None:
    args = _build_parser().parse_args(["types", "--strict"])
    assert args.strict is True


def test_parser_all_continue_on_error() -> None:
    args = _build_parser().parse_args(["all", "--continue-on-error"])
    assert args.continue_on_error is True


def test_parser_requires_subcommand() -> None:
    with pytest.raises(SystemExit):
        _build_parser().parse_args([])


def test_run_invariants_skip_when_module_missing(tmp_path: Path) -> None:
    with patch("tools.antiek_cli.check.PROJECT_ROOT", tmp_path):
        r = run_invariants(scope="substrate/")
    assert r.is_skip


def test_run_props_skip_when_dir_missing(tmp_path: Path) -> None:
    with patch("tools.antiek_cli.check.PROJECT_ROOT", tmp_path):
        r = run_props(scope="substrate/")
    assert r.is_skip


def test_run_tool_not_found_rc_127() -> None:
    r = _run("missing", ["/nonexistent/binary/that/cannot/be/found"])
    assert r.rc == 127
    assert r.skipped_reason is not None


def test_run_all_all_pass(capsys) -> None:  # type: ignore[no-untyped-def]
    fake_pass = StageResult("x", 0, 0.1)
    fake = {n: (lambda s, strict=False, fp=fake_pass: fp) for n in ALL_ORDER}
    with patch.dict("tools.antiek_cli.check.RUNNERS", fake, clear=False):
        rc = _run_all("substrate/", False, False)
    assert rc == 0
    assert "overall PASS" in capsys.readouterr().out


def test_run_all_stops_on_first_fail() -> None:
    seen: list[str] = []

    def runner_for(name: str, fail: bool):  # type: ignore[no-untyped-def]
        def r(scope: str, strict: bool = False) -> StageResult:
            seen.append(name)
            return StageResult(name, 1 if fail else 0, 0.0)
        return r

    fake = {n: runner_for(n, n == "lint") for n in ALL_ORDER}
    with patch.dict("tools.antiek_cli.check.RUNNERS", fake, clear=False):
        rc = _run_all("substrate/", False, False)
    assert rc == 1
    assert seen == ["lint"]


def test_run_all_continue_on_error_runs_every_stage() -> None:
    seen: list[str] = []

    def runner_for(name: str, fail: bool):  # type: ignore[no-untyped-def]
        def r(scope: str, strict: bool = False) -> StageResult:
            seen.append(name)
            return StageResult(name, 1 if fail else 0, 0.0)
        return r

    fake = {n: runner_for(n, n == "lint") for n in ALL_ORDER}
    with patch.dict("tools.antiek_cli.check.RUNNERS", fake, clear=False):
        rc = _run_all("substrate/", False, True)
    assert rc == 1
    assert seen == list(ALL_ORDER)


def test_run_all_skip_is_not_a_fail(capsys) -> None:  # type: ignore[no-untyped-def]
    fake = {
        "lint": lambda s, strict=False: StageResult("lint", 0, 0.0),
        "types": lambda s, strict=False: StageResult("types", 0, 0.0),
        "tests": lambda s, strict=False: StageResult("tests", 0, 0.0),
        "doctest": lambda s, strict=False: StageResult("doctest", 0, 0.0),
        "props": lambda s, strict=False: StageResult("props", -1, 0.0,
                                                     skipped_reason="x"),
        "invariants": lambda s, strict=False: StageResult("invariants", 0, 0.0),
    }
    with patch.dict("tools.antiek_cli.check.RUNNERS", fake, clear=False):
        rc = _run_all("substrate/", False, False)
    assert rc == 0
    assert "1 skip" in capsys.readouterr().out


def test_main_returns_runner_rc() -> None:
    fake = lambda s, strict=False: StageResult("lint", 0, 0.0)  # noqa: E731
    with patch.dict("tools.antiek_cli.check.RUNNERS", {"lint": fake}, clear=False):
        assert main(["lint"]) == 0


def test_main_returns_fail_rc() -> None:
    fake = lambda s, strict=False: StageResult("lint", 2, 0.0)  # noqa: E731
    with patch.dict("tools.antiek_cli.check.RUNNERS", {"lint": fake}, clear=False):
        assert main(["lint"]) == 2


def test_main_skip_returns_zero() -> None:
    fake = lambda s, strict=False: StageResult(  # noqa: E731
        "props", -1, 0.0, skipped_reason="x")
    with patch.dict("tools.antiek_cli.check.RUNNERS", {"props": fake}, clear=False):
        assert main(["props"]) == 0
