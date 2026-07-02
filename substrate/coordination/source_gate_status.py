"""Source onboarding gate — read-only VIEW over ``reports/source_census.json``.

The source gate is the machine-checked stop-rule for onboarding sources after
arXiv. The CLI at ``tools/lint/source_gate.py`` owns the exit code; this module
exposes the same state to Coordination without writing the census or mutating
source state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools.source_census import REFERENCE_SOURCE, evaluate, load_censuses


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def canonical_source_census_path() -> Path:
    return _repo_root() / "reports" / "source_census.json"


def _repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(_repo_root()))
    except ValueError:
        return str(path)


@dataclass(frozen=True)
class SourceGateRow:
    source: str
    blocked: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class SourceGateView:
    source_path: str
    state: str  # missing | invalid | clean | blocked
    reference_source: str
    source_count: int
    blocked_count: int
    rows: tuple[SourceGateRow, ...]
    error: str | None = None


def build_source_gate_view(path: Path | None = None) -> SourceGateView:
    source = path or canonical_source_census_path()
    source_path = _repo_relative(source)
    if not source.exists():
        return SourceGateView(
            source_path=source_path,
            state="missing",
            reference_source=REFERENCE_SOURCE,
            source_count=0,
            blocked_count=0,
            rows=(),
            error=(
                "no source census yet; source_gate is a no-op until the "
                "operator produces reports/source_census.json from the real corpus"
            ),
        )
    try:
        results = evaluate(load_censuses(source))
    except ValueError as exc:
        return SourceGateView(
            source_path=source_path,
            state="invalid",
            reference_source=REFERENCE_SOURCE,
            source_count=0,
            blocked_count=0,
            rows=(),
            error=str(exc),
        )
    rows = tuple(
        SourceGateRow(source=source_name, blocked=bool(failures), failures=tuple(failures))
        for source_name, failures in sorted(results.items())
    )
    blocked_count = sum(1 for row in rows if row.blocked)
    return SourceGateView(
        source_path=source_path,
        state="blocked" if blocked_count else "clean",
        reference_source=REFERENCE_SOURCE,
        source_count=len(rows),
        blocked_count=blocked_count,
        rows=rows,
    )


__all__ = [
    "SourceGateRow",
    "SourceGateView",
    "build_source_gate_view",
    "canonical_source_census_path",
]
