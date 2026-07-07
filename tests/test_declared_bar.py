"""Tests for tools.lints.declared_bar (SPR-03 — enforce the declared bar).

These tests NEVER invoke ruff/mypy as subprocesses: ``run_ruff`` /
``run_mypy`` are monkeypatched so the suite is fast and deterministic and
stays green in a pytest-only environment. Parsing is tested against
captured tool output strings.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from tools.lints import declared_bar as db
from tools.lints.declared_bar import (
    DECLARED_MYPY_TARGETS,
    RuffViolation,
    main,
    parse_ruff_json,
    ruff_violation_to_key,
)
from tools.lints.mypy_strict_baseline import MypyError

REPO_ROOT = Path(__file__).resolve().parents[1]


# ----- ruff JSON parsing -------------------------------------------------

def _ruff_record(path: str, row: int, col: int, code: str) -> dict[str, object]:
    return {
        "filename": str(REPO_ROOT / path),
        "location": {"row": row, "column": col},
        "code": code,
    }


def test_parse_ruff_json_relativizes_paths() -> None:
    out = json.dumps([_ruff_record("substrate/x.py", 10, 4, "F401")])
    vs = parse_ruff_json(out, repo_root=REPO_ROOT)
    assert len(vs) == 1
    assert vs[0].path == "substrate/x.py"
    assert vs[0].line == 10 and vs[0].col == 4 and vs[0].code == "F401"


def test_parse_ruff_json_empty_returns_empty() -> None:
    assert parse_ruff_json("", repo_root=REPO_ROOT) == []
    assert parse_ruff_json("[]", repo_root=REPO_ROOT) == []


def test_parse_ruff_json_bad_json_returns_empty() -> None:
    # A ruff banner before JSON would break json.loads — parse defensively.
    assert parse_ruff_json("warning: x\n[", repo_root=REPO_ROOT) == []


def test_parse_ruff_json_missing_code_falls_back() -> None:
    rec = {"filename": str(REPO_ROOT / "a.py"), "location": {"row": 1, "column": 1}}
    vs = parse_ruff_json(json.dumps([rec]), repo_root=REPO_ROOT)
    assert vs[0].code == "no-code"


def test_ruff_violation_to_key_prefix_and_identity() -> None:
    k = ruff_violation_to_key(RuffViolation("a.py", 1, 2, "UP045"))
    assert k.kind == "ruff:UP045"
    assert (k.path, k.line, k.col) == ("a.py", 1, 2)


def test_ruff_violation_to_key_distinguishes_codes() -> None:
    k1 = ruff_violation_to_key(RuffViolation("a.py", 1, 0, "F401"))
    k2 = ruff_violation_to_key(RuffViolation("a.py", 1, 0, "I001"))
    assert k1 != k2


# ----- declared scope guard ---------------------------------------------

def test_mypy_targets_match_wheel_packages() -> None:
    """The mypy declared scope must equal the pyproject wheel-package list,
    so the gate never silently narrows below the declared package surface
    (and never drifts above it). This is the scope contract for G1/G5."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    wheel_pkgs = data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert set(DECLARED_MYPY_TARGETS) == set(wheel_pkgs)


# ----- capture / enforce round trips (runner mocked) --------------------

def _fake_ruff() -> list[RuffViolation]:
    return [
        RuffViolation("substrate/a.py", 10, 4, "F401"),
        RuffViolation("interfaces/b.py", 20, 1, "UP045"),
    ]


def _fake_mypy() -> list[MypyError]:
    return [
        MypyError(path="substrate/a.py", line=10, col=0,
                  code="no-untyped-def", message="x"),
        MypyError(path="runtime/c.py", line=5, col=0,
                  code="arg-type", message="y"),
    ]


def test_capture_ruff_writes_dated_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "run_ruff", lambda: _fake_ruff())
    baseline = tmp_path / "ruff.json"
    assert main(["capture", "ruff", "--baseline-file", str(baseline)]) == 0
    data = json.loads(baseline.read_text())
    assert data["lint"] == "declared_bar_ruff"
    assert data["generated_at"]  # date recorded
    kinds = {v["kind"] for v in data["violations"]}
    assert kinds == {"ruff:F401", "ruff:UP045"}


def test_capture_dedupes_identical_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dup = RuffViolation("substrate/a.py", 10, 4, "F401")
    monkeypatch.setattr(db, "run_ruff", lambda: [dup, RuffViolation("substrate/a.py", 10, 4, "F401")])
    baseline = tmp_path / "ruff.json"
    main(["capture", "ruff", "--baseline-file", str(baseline)])
    data = json.loads(baseline.read_text())
    assert len(data["violations"]) == 1


def test_enforce_ruff_green_after_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "run_ruff", lambda: _fake_ruff())
    baseline = tmp_path / "ruff.json"
    main(["capture", "ruff", "--baseline-file", str(baseline)])
    assert main(["enforce", "ruff", "--baseline-file", str(baseline)]) == 0


def test_enforce_ruff_reds_on_new_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(db, "run_ruff", lambda: _fake_ruff())
    baseline = tmp_path / "ruff.json"
    main(["capture", "ruff", "--baseline-file", str(baseline)])

    def _with_new() -> list[RuffViolation]:
        return _fake_ruff() + [RuffViolation("processing/new.py", 1, 1, "B904")]

    monkeypatch.setattr(db, "run_ruff", _with_new)
    rc = main(["enforce", "ruff", "--baseline-file", str(baseline)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "processing/new.py:1:1: NEW ruff:B904" in out


def test_enforce_mypy_reds_on_new_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "run_mypy", lambda: _fake_mypy())
    baseline = tmp_path / "mypy.json"
    main(["capture", "mypy", "--baseline-file", str(baseline)])

    def _with_new() -> list[MypyError]:
        return _fake_mypy() + [
            MypyError(path="roles/new.py", line=9, col=0,
                      code="assignment", message="z"),
        ]

    monkeypatch.setattr(db, "run_mypy", _with_new)
    assert main(["enforce", "mypy", "--baseline-file", str(baseline)]) == 1


def test_enforce_check_stale_flags_fixed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(db, "run_ruff", lambda: _fake_ruff())
    baseline = tmp_path / "ruff.json"
    main(["capture", "ruff", "--baseline-file", str(baseline)])
    # One violation fixed → stale entry surfaces, exit non-zero.
    monkeypatch.setattr(db, "run_ruff", lambda: _fake_ruff()[:1])
    rc = main(["enforce", "ruff", "--baseline-file", str(baseline),
               "--check-stale"])
    assert rc == 1
    assert "stale baseline" in capsys.readouterr().err


def test_enforce_missing_baseline_returns_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "run_ruff", lambda: _fake_ruff())
    assert main(["enforce", "ruff",
                 "--baseline-file", str(tmp_path / "absent.json")]) == 2


def test_capture_handles_tool_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom() -> list[RuffViolation]:
        raise RuntimeError("ruff not found")

    monkeypatch.setattr(db, "run_ruff", _boom)
    assert main(["capture", "ruff",
                 "--baseline-file", str(tmp_path / "b.json")]) == 2


# ----- the committed baselines are real + green -------------------------

def test_committed_baselines_exist_and_are_dated() -> None:
    for name in ("declared_ruff.json", "declared_mypy.json"):
        p = REPO_ROOT / "tools/lints/baselines" / name
        assert p.exists(), f"{name} missing"
        data = json.loads(p.read_text())
        assert data["schema_version"] == 1
        assert data["generated_at"], f"{name} has no generation date"
        assert isinstance(data["violations"], list)


# ----- content-keyed matching: line-shift defect fix --------------------


def _write_src(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_enrich_preserves_grandfathered_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``enrich`` only ADDS snippet fields; (path,line,col,kind), lint,
    schema_version and generated_at are byte-identical before/after. This is
    the proof it is NOT a re-mint."""
    _write_src(tmp_path / "substrate" / "a.py", ["import os", "x = 1"])
    baseline = tmp_path / "mypy.json"
    raw = {
        "schema_version": 1,
        "lint": "declared_bar_mypy",
        "generated_at": "2026-06-02T00:00:00+00:00",
        "violations": [
            {"path": "substrate/a.py", "line": 2, "col": 0, "kind": "mypy:arg-type"}
        ],
    }
    baseline.write_text(json.dumps(raw))
    monkeypatch.chdir(tmp_path)
    assert db.main(["enrich", "mypy", "--baseline-file", str(baseline)]) == 0
    after = json.loads(baseline.read_text())
    assert after["generated_at"] == raw["generated_at"]
    assert after["lint"] == raw["lint"]
    assert after["schema_version"] == 1
    assert after["violations"][0]["snippet"] == "x = 1"
    assert {
        (v["path"], v["line"], v["col"], v["kind"]) for v in after["violations"]
    } == {("substrate/a.py", 2, 0, "mypy:arg-type")}


def test_enforce_mypy_line_shift_is_not_new(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end model of the defect + fix: capture an offense, then insert a
    line above it so mypy reports it one line lower on identical source. With
    content-keyed matching the shifted offense is NOT new (previously: RED)."""
    src = tmp_path / "substrate" / "a.py"
    _write_src(src, ["import os", "x = 1", "y = bad_call()"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        db,
        "run_mypy",
        lambda: [MypyError(path="substrate/a.py", line=3, col=0,
                           code="arg-type", message="x")],
    )
    baseline = tmp_path / "mypy.json"
    assert db.main(["capture", "mypy", "--baseline-file", str(baseline)]) == 0

    # Mid-file insertion shifts the offense from line 3 to line 4 (identical text).
    _write_src(src, ["import os", "x = 1", "# inserted", "y = bad_call()"])
    monkeypatch.setattr(
        db,
        "run_mypy",
        lambda: [MypyError(path="substrate/a.py", line=4, col=0,
                           code="arg-type", message="x")],
    )
    assert db.main(["enforce", "mypy", "--baseline-file", str(baseline)]) == 0


def test_enforce_mypy_genuine_new_still_reds_with_snippets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The no-mask guarantee, end-to-end: with snippets active, a NEW offense
    on a source line the baseline has never seen still reds the gate."""
    src = tmp_path / "substrate" / "a.py"
    _write_src(src, ["import os", "x = 1", "y = bad_call()"])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        db,
        "run_mypy",
        lambda: [MypyError(path="substrate/a.py", line=3, col=0,
                           code="arg-type", message="x")],
    )
    baseline = tmp_path / "mypy.json"
    db.main(["capture", "mypy", "--baseline-file", str(baseline)])

    _write_src(src, ["import os", "x = 1", "y = bad_call()", "z = brand_new_bug()"])
    monkeypatch.setattr(
        db,
        "run_mypy",
        lambda: [
            MypyError(path="substrate/a.py", line=3, col=0, code="arg-type", message="x"),
            MypyError(path="substrate/a.py", line=4, col=0, code="arg-type", message="z"),
        ],
    )
    assert db.main(["enforce", "mypy", "--baseline-file", str(baseline)]) == 1
    assert "substrate/a.py:4:0: NEW mypy:arg-type" in capsys.readouterr().out
