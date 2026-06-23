"""Tests for tools.lints.cli_with_baseline — the runner that wraps
the two substrate lints with baseline-mode support.

End-to-end: capture-then-enforce on fixture files. Verifies that
(a) capture writes the right violations, (b) enforce against the
fresh baseline returns 0 (everything grandfathered), (c) enforce
against an empty baseline flags everything as NEW.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.lints.baseline import SCHEMA_VERSION, BaselineSchema, ViolationKey
from tools.lints.cli_with_baseline import (
    LINT_REGISTRY,
    _build_parser,
    main,
)

FIXTURE_RAISE = (
    Path(__file__).parent / "fixtures" / "lints" / "raise_violation_sample.py"
)
FIXTURE_BYPASS = (
    Path(__file__).parent / "fixtures" / "lints" / "bypass_sample.py"
)


# ---------------------------------------------------------------------- #
# Registry + parser shape                                                #
# ---------------------------------------------------------------------- #


def test_registry_has_both_lints() -> None:
    assert "no_raise" in LINT_REGISTRY
    assert "bypass" in LINT_REGISTRY


def test_parser_supports_capture_and_enforce() -> None:
    parser = _build_parser()
    args = parser.parse_args([
        "capture", "no_raise",
        "--paths", "x.py",
        "--baseline-file", "/tmp/b.json",
    ])
    assert args.mode == "capture" and args.lint == "no_raise"

    args = parser.parse_args([
        "enforce", "bypass",
        "--paths", "x.py", "y.py",
        "--baseline-file", "/tmp/b.json",
        "--check-stale",
    ])
    assert args.mode == "enforce" and args.lint == "bypass"
    assert args.check_stale is True
    assert args.paths == ["x.py", "y.py"]


def test_parser_rejects_unknown_lint() -> None:
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "capture", "made-up-lint",
            "--paths", "x.py",
            "--baseline-file", "/tmp/b.json",
        ])


def test_parser_requires_paths_and_baseline_file() -> None:
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["capture", "no_raise"])


# ---------------------------------------------------------------------- #
# Capture: writes baseline with right violation set                      #
# ---------------------------------------------------------------------- #


def test_capture_no_raise_writes_baseline(tmp_path: Path) -> None:
    baseline_file = tmp_path / "no_raise_baseline.json"
    rc = main([
        "capture", "no_raise",
        "--paths", str(FIXTURE_RAISE),
        "--baseline-file", str(baseline_file),
    ])
    assert rc == 0
    assert baseline_file.exists()
    data = json.loads(baseline_file.read_text())
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["lint"] == "no_raise_in_substrate_writers"
    # The fixture has 2 violations (CustomDomainError + UnstableThing)
    assert len(data["violations"]) == 2
    kinds = {v["kind"] for v in data["violations"]}
    assert "raise:CustomDomainError" in kinds
    assert "raise:UnstableThing" in kinds


def test_capture_bypass_writes_baseline(tmp_path: Path) -> None:
    baseline_file = tmp_path / "bypass_baseline.json"
    rc = main([
        "capture", "bypass",
        "--paths", str(FIXTURE_BYPASS),
        "--baseline-file", str(baseline_file),
    ])
    assert rc == 0
    data = json.loads(baseline_file.read_text())
    kinds = {v["kind"] for v in data["violations"]}
    # Fixture has 3 unannotated bypass calls (2 functions with one each,
    # plus the second-call in escape_then_unannotated_violation)
    assert any("bypass:duckdb.connect" in k for k in kinds)
    assert any("bypass:requests.get" in k for k in kinds)


# ---------------------------------------------------------------------- #
# Enforce-after-capture: zero new violations                             #
# ---------------------------------------------------------------------- #


def test_enforce_after_capture_returns_zero(tmp_path: Path) -> None:
    """The integration property: capture then immediately enforce.
    Every current violation is in the baseline, so no NEW violations."""
    baseline_file = tmp_path / "b.json"
    rc_capture = main([
        "capture", "no_raise",
        "--paths", str(FIXTURE_RAISE),
        "--baseline-file", str(baseline_file),
    ])
    assert rc_capture == 0

    rc_enforce = main([
        "enforce", "no_raise",
        "--paths", str(FIXTURE_RAISE),
        "--baseline-file", str(baseline_file),
    ])
    assert rc_enforce == 0


# ---------------------------------------------------------------------- #
# Enforce against empty baseline: every violation is NEW                 #
# ---------------------------------------------------------------------- #


def test_enforce_against_empty_baseline_flags_all(tmp_path: Path) -> None:
    empty = tmp_path / "empty.json"
    # Manually write an empty baseline
    schema = BaselineSchema(
        schema_version=SCHEMA_VERSION,
        lint="no_raise_in_substrate_writers",
        generated_at="",
        violations=[],
    )
    empty.write_text(json.dumps(schema.to_json()))

    rc = main([
        "enforce", "no_raise",
        "--paths", str(FIXTURE_RAISE),
        "--baseline-file", str(empty),
    ])
    assert rc == 1  # everything is NEW


# ---------------------------------------------------------------------- #
# Enforce with stale entries                                             #
# ---------------------------------------------------------------------- #


def test_enforce_check_stale_flags_fixed_entries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Baseline references a violation that's NOT in the fixture file.
    With --check-stale, the runner should flag it."""
    baseline_file = tmp_path / "stale.json"
    schema = BaselineSchema(
        schema_version=SCHEMA_VERSION,
        lint="no_raise_in_substrate_writers",
        generated_at="",
        violations=[
            # A real violation from the fixture
            ViolationKey(
                path=str(FIXTURE_RAISE),
                line=15,  # matches writes_with_violation
                col=4,
                kind="raise:CustomDomainError",
            ),
            # A bogus entry that's NOT in the fixture
            ViolationKey(
                path=str(FIXTURE_RAISE),
                line=999,
                col=0,
                kind="raise:NoLongerHere",
            ),
        ],
    )
    baseline_file.write_text(json.dumps(schema.to_json()))

    rc = main([
        "enforce", "no_raise",
        "--paths", str(FIXTURE_RAISE),
        "--baseline-file", str(baseline_file),
        "--check-stale",
    ])
    # Stale entry exists → rc=1
    assert rc == 1
    captured = capsys.readouterr()
    assert "stale baseline" in captured.err
    assert "NoLongerHere" in captured.err


def test_enforce_missing_baseline_file_returns_2(tmp_path: Path) -> None:
    rc = main([
        "enforce", "no_raise",
        "--paths", str(FIXTURE_RAISE),
        "--baseline-file", str(tmp_path / "does_not_exist.json"),
    ])
    assert rc == 2


# ---------------------------------------------------------------------- #
# Determinism: re-capture produces same violation set                    #
# ---------------------------------------------------------------------- #


def test_recapture_produces_same_violation_set(tmp_path: Path) -> None:
    b1 = tmp_path / "b1.json"
    b2 = tmp_path / "b2.json"
    main(["capture", "no_raise", "--paths", str(FIXTURE_RAISE),
          "--baseline-file", str(b1)])
    main(["capture", "no_raise", "--paths", str(FIXTURE_RAISE),
          "--baseline-file", str(b2)])
    d1 = json.loads(b1.read_text())
    d2 = json.loads(b2.read_text())
    # Violations array byte-identical (timestamp may differ)
    assert d1["violations"] == d2["violations"]
