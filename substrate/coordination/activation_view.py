"""Read activation status view over the dogfood JSONL log.

This is a read-only companion to ``tools.activation.read_dogfood``. The CLI
remains the closure authority; this module only turns the same report into a
small dashboard shape so Coordination can show whether activation evidence is
missing, incomplete, invalid, or ready.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tools.activation.read_dogfood import DogfoodReport, load_jsonl, validate_sessions


ActivationEvidenceState = Literal["not_started", "incomplete", "invalid_log", "ready"]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_read_dogfood_log_path() -> Path:
    """Canonical operator-authored Read dogfood log location."""
    return _repo_root() / "reports" / "read-dogfood.jsonl"


@dataclass(frozen=True)
class ReadActivationView:
    source_path: str
    state: ActivationEvidenceState
    total_sessions: int
    valid_sessions: int
    invalid_session_count: int
    live_provider_sessions: int
    citation_trace_sessions: int
    non_library_sessions: int
    final_verdict: str | None
    closure_ready: bool
    remaining_requirements: dict[str, int]
    failures: tuple[str, ...]


def _empty_report() -> DogfoodReport:
    return validate_sessions([])


def _state_for_report(report: DogfoodReport) -> ActivationEvidenceState:
    if report.closure_ready:
        return "ready"
    if report.total_sessions == 0:
        return "not_started"
    return "incomplete"


def build_read_activation_view(path: Path | None = None) -> ReadActivationView:
    """Read and validate the Read dogfood log.

    Missing log files are not errors: they honestly mean no operator dogfood
    evidence has been recorded yet. Malformed JSONL is surfaced as ``invalid_log``
    with the parser error in ``failures``.
    """
    log_path = path or default_read_dogfood_log_path()
    try:
        report = validate_sessions(load_jsonl(log_path)) if log_path.exists() else _empty_report()
        state = _state_for_report(report)
        failures = report.failures
    except (OSError, ValueError) as exc:
        report = _empty_report()
        state = "invalid_log"
        failures = (str(exc),)

    return ReadActivationView(
        source_path=str(log_path),
        state=state,
        total_sessions=report.total_sessions,
        valid_sessions=report.valid_sessions,
        invalid_session_count=len(report.invalid_sessions),
        live_provider_sessions=report.live_provider_sessions,
        citation_trace_sessions=report.citation_trace_sessions,
        non_library_sessions=report.non_library_sessions,
        final_verdict=report.final_verdict,
        closure_ready=report.closure_ready and state == "ready",
        remaining_requirements=report.remaining_requirements(),
        failures=failures,
    )
