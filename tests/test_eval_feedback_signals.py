from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from substrate.eval.feedback_signals import FeedbackSignalEntry, check, load_registry

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_REGISTRY = REPO_ROOT / "substrate/eval/feedback_signals.yaml"


def test_seed_registry_loads_cleanly() -> None:
    entries = load_registry(SEED_REGISTRY)

    assert [entry.subsystem for entry in entries] == [
        "orchestration/phase_log",
        "substrate/synthesis_rubric",
        "roles/cascade_planner",
        "substrate/voice_style",
    ]
    assert {entry.signal_type for entry in entries} == {
        "regression",
        "rubric",
        "categorical",
        "absent",
    }


def test_load_registry_rejects_duplicate_subsystem(tmp_path: Path) -> None:
    registry = [
        _entry_dict(subsystem="roles/cascade_planner"),
        _entry_dict(subsystem="roles/cascade_planner", signal_type="rubric"),
    ]

    with pytest.raises(ValueError, match="duplicate subsystem"):
        load_registry(_write_registry(tmp_path, registry))


def test_load_registry_rejects_bad_signal_type(tmp_path: Path) -> None:
    registry = [_entry_dict(signal_type="vibes")]

    with pytest.raises(ValueError, match="signal_type must be one of"):
        load_registry(_write_registry(tmp_path, registry))


def test_load_registry_rejects_bad_abundance_score(tmp_path: Path) -> None:
    registry = [_entry_dict(abundance_score="plenty")]

    with pytest.raises(ValueError, match="abundance_score must be one of"):
        load_registry(_write_registry(tmp_path, registry))


def test_load_registry_rejects_bad_demand_score(tmp_path: Path) -> None:
    registry = [_entry_dict(demand_score="urgent")]

    with pytest.raises(ValueError, match="demand_score must be one of"):
        load_registry(_write_registry(tmp_path, registry))


def test_load_registry_rejects_absent_signal_with_path(tmp_path: Path) -> None:
    registry = [
        _entry_dict(
            signal_type="absent",
            signal_check_path="roles/cascade_planner/tree_contract.py",
            abundance_score="low",
            demand_score="low",
            notes="",
        )
    ]

    with pytest.raises(ValueError, match="None iff"):
        load_registry(_write_registry(tmp_path, registry))


def test_load_registry_rejects_present_signal_without_path(tmp_path: Path) -> None:
    registry = [_entry_dict(signal_type="rubric", signal_check_path=None)]

    with pytest.raises(ValueError, match="None iff"):
        load_registry(_write_registry(tmp_path, registry))


def test_load_registry_rejects_nonexistent_signal_check_path(tmp_path: Path) -> None:
    registry = [_entry_dict(signal_check_path="does/not/exist.py")]

    with pytest.raises(ValueError, match="must be an existing FILE"):
        load_registry(_write_registry(tmp_path, registry))


def test_load_registry_rejects_directory_signal_check_path(tmp_path: Path) -> None:
    # A directory satisfies a literal "exists" but is not a runnable check
    # artifact — the loader tightens path-exists to is_file().
    registry = [_entry_dict(signal_check_path="roles")]

    with pytest.raises(ValueError, match="must be an existing FILE"):
        load_registry(_write_registry(tmp_path, registry))


def test_load_registry_rejects_path_outside_repo(tmp_path: Path) -> None:
    # The repo-confinement guard blocks a registry entry from pointing at a
    # check artifact outside the repo (path traversal) — a security-relevant
    # validation that must not regress silently.
    registry = [_entry_dict(signal_check_path="/var/empty/outside_repo.py")]

    with pytest.raises(ValueError, match="must resolve inside the repo"):
        load_registry(_write_registry(tmp_path, registry))


def test_load_registry_rejects_whitespace_subsystem(tmp_path: Path) -> None:
    registry = [_entry_dict(subsystem="roles/cascade_planner ")]

    with pytest.raises(ValueError, match="leading/trailing whitespace"):
        load_registry(_write_registry(tmp_path, registry))


def test_load_registry_rejects_non_string_notes(tmp_path: Path) -> None:
    # notes is type-checked unconditionally, not only under the high-score defense.
    registry = [_entry_dict(abundance_score="low", demand_score="low", notes=5)]

    with pytest.raises(ValueError, match="notes must be a string"):
        load_registry(_write_registry(tmp_path, registry))


def test_load_registry_rejects_high_score_without_notes(tmp_path: Path) -> None:
    registry = [_entry_dict(abundance_score="high", demand_score="medium", notes="")]

    with pytest.raises(ValueError, match="notes is required"):
        load_registry(_write_registry(tmp_path, registry))


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (
            FeedbackSignalEntry(
                subsystem="coverage/zero",
                signal_type="absent",
                signal_check_path=None,
                abundance_score="low",
                demand_score="low",
                notes="",
                origin="test",
            ),
            0,
        ),
        (
            FeedbackSignalEntry(
                subsystem="coverage/one",
                signal_type="rubric",
                signal_check_path="substrate/synthesis_rubric/scorer.py",
                abundance_score="medium",
                demand_score="low",
                notes="",
                origin="test",
            ),
            1,
        ),
        (
            FeedbackSignalEntry(
                subsystem="coverage/two",
                signal_type="categorical",
                signal_check_path="roles/cascade_planner/tree_contract.py",
                abundance_score="high",
                demand_score="medium",
                notes="high abundance",
                origin="test",
            ),
            2,
        ),
        (
            FeedbackSignalEntry(
                subsystem="coverage/three",
                signal_type="regression",
                signal_check_path="orchestration/phase_log/log.py",
                abundance_score="high",
                demand_score="high",
                notes="high abundance and demand",
                origin="test",
            ),
            3,
        ),
    ],
)
def test_check_computes_precondition_coverage_0_to_3(
    entry: FeedbackSignalEntry, expected: int
) -> None:
    assert check(entry) == expected


def test_cli_list_all() -> None:
    result = _run_cli("--list-all")

    assert result.returncode == 0
    assert "orchestration/phase_log\tregression\tabundance=high\tdemand=high\tcoverage=3" in result.stdout
    assert "substrate/voice_style\tabsent\tabundance=low\tdemand=low\tcoverage=0" in result.stdout
    assert result.stderr == ""


def test_cli_check_known_subsystem() -> None:
    result = _run_cli("--check", "substrate/synthesis_rubric")

    assert result.returncode == 0
    assert "subsystem: substrate/synthesis_rubric" in result.stdout
    assert "precondition_coverage: 2/3" in result.stdout
    assert "deprioritization_candidate: no" in result.stdout
    assert result.stderr == ""


def test_cli_check_unknown_subsystem_exits_nonzero() -> None:
    result = _run_cli("--check", "missing")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "feedback-signal subsystem not found: missing" in result.stderr


def test_cli_deprioritization_candidates() -> None:
    result = _run_cli("--deprioritization-candidates")

    assert result.returncode == 0
    assert result.stdout == "substrate/voice_style\tabsent\tabundance=low\tdemand=low\tcoverage=0\n"
    assert result.stderr == ""


def test_cli_malformed_registry_exits_one(tmp_path: Path) -> None:
    # The CLI's load-failure path (broad except → exit 1) is exercised by
    # pointing --registry at a registry that fails validation (duplicate subsystem).
    bad = _write_registry(
        tmp_path,
        [
            _entry_dict(subsystem="roles/cascade_planner"),
            _entry_dict(subsystem="roles/cascade_planner", signal_type="rubric"),
        ],
    )
    result = subprocess.run(
        [sys.executable, "-m", "substrate.eval.feedback_signals", "--registry", str(bad), "--list-all"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "feedback-signal registry error:" in result.stderr


def _entry_dict(**overrides: object) -> dict[str, object]:
    entry = FeedbackSignalEntry(
        subsystem="roles/cascade_planner",
        signal_type="categorical",
        signal_check_path="roles/cascade_planner/tree_contract.py",
        abundance_score="medium",
        demand_score="medium",
        notes="",
        origin="test",
    )
    return replace(entry, **overrides).__dict__


def _write_registry(tmp_path: Path, entries: list[dict[str, object]]) -> Path:
    registry = tmp_path / "feedback_signals.yaml"
    lines: list[str] = []
    for entry in entries:
        lines.append("-")
        for key, value in entry.items():
            rendered = "null" if value is None else repr(value)
            lines.append(f"  {key}: {rendered}")
    registry.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return registry


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "substrate.eval.feedback_signals",
            "--registry",
            str(SEED_REGISTRY),
            *args,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
