"""Feedback-signal registry with fail-loud validation and a thin CLI."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Final

import yaml

SIGNAL_REGRESSION: Final[str] = "regression"
SIGNAL_CATEGORICAL: Final[str] = "categorical"
SIGNAL_RUBRIC: Final[str] = "rubric"
SIGNAL_ABSENT: Final[str] = "absent"
SIGNAL_TYPES: Final[frozenset[str]] = frozenset(
    {SIGNAL_REGRESSION, SIGNAL_CATEGORICAL, SIGNAL_RUBRIC, SIGNAL_ABSENT}
)

SCORE_LOW: Final[str] = "low"
SCORE_MEDIUM: Final[str] = "medium"
SCORE_HIGH: Final[str] = "high"
SCORE_VALUES: Final[frozenset[str]] = frozenset(
    {SCORE_LOW, SCORE_MEDIUM, SCORE_HIGH}
)

DEFAULT_REGISTRY_PATH: Final[Path] = Path(__file__).with_suffix(".yaml")
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class FeedbackSignalEntry:
    subsystem: str
    signal_type: str
    signal_check_path: str | None
    abundance_score: str
    demand_score: str
    notes: str
    origin: str


def load_registry(path: str | Path = DEFAULT_REGISTRY_PATH) -> tuple[FeedbackSignalEntry, ...]:
    registry_path = Path(path)
    data = _load_yaml_sequence(registry_path)

    seen_subsystems: set[str] = set()
    entries: list[FeedbackSignalEntry] = []
    for index, raw_entry in enumerate(data):
        entry = _entry_from_mapping(raw_entry, f"entry[{index}]")
        _validate_entry(entry, registry_path)
        if entry.subsystem in seen_subsystems:
            raise ValueError(f"duplicate subsystem in feedback registry: {entry.subsystem!r}")
        seen_subsystems.add(entry.subsystem)
        entries.append(entry)

    return tuple(entries)


def check(entry: FeedbackSignalEntry) -> int:
    """Return Yao precondition coverage (0-3): signal + abundant data + demand.

    Only ``"high"`` satisfies a precondition — ``"medium"``/``"low"`` contribute 0.
    Yao's "abundant / singular" language reads as a high-bar threshold; the seed
    and tests are built to this rule (see doctrine D-14). coverage 0 = a
    deprioritization candidate.
    """

    coverage = 0
    if entry.signal_type != SIGNAL_ABSENT:
        coverage += 1
    if entry.abundance_score == SCORE_HIGH:
        coverage += 1
    if entry.demand_score == SCORE_HIGH:
        coverage += 1
    return coverage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect the Antiek feedback-signal registry."
    )
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--list-all", action="store_true", help="List every subsystem.")
    commands.add_argument("--check", metavar="SUBSYSTEM", help="Check one subsystem.")
    commands.add_argument(
        "--deprioritization-candidates",
        action="store_true",
        help="List entries with precondition coverage 0.",
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_REGISTRY_PATH),
        help="Path to feedback_signals.yaml.",
    )
    args = parser.parse_args(argv)

    try:
        entries = load_registry(args.registry)
    except Exception as exc:
        print(f"feedback-signal registry error: {exc}", file=sys.stderr)
        return 1

    if args.list_all:
        for entry in entries:
            print(_summary_line(entry))
        return 0

    if args.check:
        matches = [entry for entry in entries if entry.subsystem == args.check]
        if not matches:
            print(f"feedback-signal subsystem not found: {args.check}", file=sys.stderr)
            return 1
        print(_detail_block(matches[0]))
        return 0

    for entry in entries:
        if check(entry) == 0:
            print(_summary_line(entry))
    return 0


def _summary_line(entry: FeedbackSignalEntry) -> str:
    return (
        f"{entry.subsystem}\t"
        f"{entry.signal_type}\t"
        f"abundance={entry.abundance_score}\t"
        f"demand={entry.demand_score}\t"
        f"coverage={check(entry)}"
    )


def _detail_block(entry: FeedbackSignalEntry) -> str:
    candidate = "yes" if check(entry) == 0 else "no"
    path = entry.signal_check_path if entry.signal_check_path is not None else "absent"
    return "\n".join(
        [
            f"subsystem: {entry.subsystem}",
            f"signal_type: {entry.signal_type}",
            f"signal_check_path: {path}",
            f"abundance_score: {entry.abundance_score}",
            f"demand_score: {entry.demand_score}",
            f"precondition_coverage: {check(entry)}/3",
            f"deprioritization_candidate: {candidate}",
        ]
    )


def _load_yaml_sequence(path: Path) -> list[Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or []
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a YAML sequence")
    return data


def _entry_from_mapping(data: Any, label: str) -> FeedbackSignalEntry:
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a YAML mapping")

    allowed = {field.name for field in fields(FeedbackSignalEntry)}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"{label} has unknown field(s): {', '.join(sorted(unknown))}")
    missing = allowed - set(data)
    if missing:
        raise ValueError(f"{label} missing field(s): {', '.join(sorted(missing))}")

    return FeedbackSignalEntry(**data)


def _validate_entry(entry: FeedbackSignalEntry, registry_path: Path) -> None:
    if not isinstance(entry.subsystem, str) or not entry.subsystem.strip():
        raise ValueError("feedback-signal subsystem must be a non-empty string")
    # Reject leading/trailing whitespace so 'a' and 'a ' can't become two logical
    # entries for one subsystem (the uniqueness rule is exact-string).
    if entry.subsystem != entry.subsystem.strip():
        raise ValueError(
            f"{entry.subsystem!r}: subsystem must not have leading/trailing whitespace"
        )
    if not isinstance(entry.notes, str):
        raise ValueError(f"{entry.subsystem}: notes must be a string")
    if entry.signal_type not in SIGNAL_TYPES:
        raise ValueError(
            f"{entry.subsystem}: signal_type must be one of: "
            f"{', '.join(sorted(SIGNAL_TYPES))}"
        )
    if entry.abundance_score not in SCORE_VALUES:
        raise ValueError(
            f"{entry.subsystem}: abundance_score must be one of: "
            f"{', '.join(sorted(SCORE_VALUES))}"
        )
    if entry.demand_score not in SCORE_VALUES:
        raise ValueError(
            f"{entry.subsystem}: demand_score must be one of: "
            f"{', '.join(sorted(SCORE_VALUES))}"
        )

    path_absent = entry.signal_check_path is None
    signal_absent = entry.signal_type == SIGNAL_ABSENT
    if path_absent != signal_absent:
        raise ValueError(
            f"{entry.subsystem}: signal_check_path must be None iff "
            "signal_type is absent"
        )

    if entry.signal_check_path is not None:
        if not isinstance(entry.signal_check_path, str) or not entry.signal_check_path.strip():
            raise ValueError(
                f"{entry.subsystem}: signal_check_path must be a non-empty string "
                "when signal_type is present"
            )
        signal_path = _resolve_repo_path(entry.signal_check_path)
        if not _is_relative_to(signal_path.resolve(), _REPO_ROOT):
            raise ValueError(
                f"{entry.subsystem}: signal_check_path must resolve inside the repo: "
                f"{entry.signal_check_path!r}"
            )
        # Tightened from exists() to is_file(): a signal_check_path is a runnable
        # check artifact, so a directory (which satisfies a literal "exists") is
        # not a valid mechanical signal. Deliberate strengthening beyond the HTML's
        # "path-exists" wording — flagged in the handoff.
        if not signal_path.is_file():
            raise ValueError(
                f"{entry.subsystem}: signal_check_path must be an existing FILE "
                f"(a runnable check artifact, not a directory): "
                f"{entry.signal_check_path!r} (registry {registry_path})"
            )

    if (entry.abundance_score == SCORE_HIGH or entry.demand_score == SCORE_HIGH) and (
        not isinstance(entry.notes, str) or not entry.notes.strip()
    ):
        raise ValueError(
            f"{entry.subsystem}: notes is required when abundance_score or "
            "demand_score is high"
        )
    if not isinstance(entry.origin, str) or not entry.origin.strip():
        raise ValueError(f"{entry.subsystem}: origin must be a non-empty string")


def _resolve_repo_path(signal_check_path: str) -> Path:
    path = Path(signal_check_path)
    if path.is_absolute():
        return path
    return _REPO_ROOT / path


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
