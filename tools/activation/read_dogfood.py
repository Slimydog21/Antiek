#!/usr/bin/env python3
"""Validate the Read activation dogfood log.

This is NOT a product-completion shortcut. ``specs/activation/golden-path.md``
states the activation rule: Read closes only after 10 distinct operator sessions
are logged, with live-provider coverage, citation tracing, a non-Library entry
point, at least 20 minutes of reading per valid session, and concrete follow-ups
for every failure or irritation.

The tool makes that rule executable over a JSONL log so future agents cannot
convert "CI is green" into "Read is done". It never records sessions itself and
never judges answer quality; the operator's log remains the source of truth.

JSONL record shape (one object per session)::

    {
      "session_id": "2026-06-30-faisal-001",
      "date": "2026-06-30",
      "build_sha": "abc123",
      "url": "https://...",
      "operator": "Faisal",
      "document_id": "doc-...",
      "entry_door": "library",
      "provider_status": "ready",
      "live_provider_ai": true,
      "citation_traced": true,
      "minutes_reading": 22,
      "steps": {
        "1": {"status": "pass"},
        "2": {"status": "pass"},
        "3": {"status": "pass"},
        "4": {"status": "pass"},
        "5": {"status": "pass"},
        "6": {"status": "pass"},
        "7": {"status": "pass"}
      }
    }

Failures or irritations must include a concrete ``followup_issue`` on the step
or in the session-level ``issues`` list.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_SESSION_FIELDS: tuple[str, ...] = (
    "session_id",
    "date",
    "build_sha",
    "url",
    "operator",
    "document_id",
    "entry_door",
    "provider_status",
    "minutes_reading",
    "steps",
)
REQUIRED_STEPS: tuple[str, ...] = tuple(str(i) for i in range(1, 8))
NON_LIBRARY_ENTRY_DOORS: frozenset[str] = frozenset(
    {
        "search",
        "command_palette",
        "drw_citation",
        "write_trace",
        "citation",
        "deep_research_workspace",
        "unified_search",
    }
)
ALLOWED_STEP_STATUSES: frozenset[str] = frozenset({"pass", "fail", "inert"})


@dataclass(frozen=True)
class DogfoodReport:
    total_sessions: int
    valid_sessions: int
    live_provider_sessions: int
    citation_trace_sessions: int
    non_library_sessions: int
    closure_ready: bool
    failures: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_sessions": self.total_sessions,
            "valid_sessions": self.valid_sessions,
            "live_provider_sessions": self.live_provider_sessions,
            "citation_trace_sessions": self.citation_trace_sessions,
            "non_library_sessions": self.non_library_sessions,
            "closure_ready": self.closure_ready,
            "failures": list(self.failures),
        }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{lineno}: session record must be a JSON object")
        records.append(payload)
    return records


def validate_sessions(records: list[dict[str, Any]]) -> DogfoodReport:
    failures: list[str] = []
    seen_session_ids: set[str] = set()
    valid_session_ids: set[str] = set()
    live_provider_sessions: set[str] = set()
    citation_trace_sessions: set[str] = set()
    non_library_sessions: set[str] = set()

    for index, record in enumerate(records, start=1):
        session_id = str(record.get("session_id") or f"<record-{index}>")
        prefix = f"{session_id}: "

        if session_id in seen_session_ids:
            failures.append(prefix + "duplicate session_id")
            continue
        seen_session_ids.add(session_id)

        missing = _missing_required_fields(record)
        if missing:
            failures.append(prefix + "missing required fields: " + ", ".join(missing))

        steps = record.get("steps")
        if not isinstance(steps, dict):
            failures.append(prefix + "steps must be an object keyed by '1'..'7'")
            continue

        missing_steps = [step for step in REQUIRED_STEPS if step not in steps]
        if missing_steps:
            failures.append(prefix + "missing golden-path steps: " + ", ".join(missing_steps))

        step_failures = _step_followup_failures(prefix, steps)
        failures.extend(step_failures)
        failures.extend(_step_status_failures(prefix, steps))

        for issue_index, issue in enumerate(record.get("issues") or [], start=1):
            if not isinstance(issue, dict):
                failures.append(prefix + f"issues[{issue_index}] must be an object")
                continue
            if not str(issue.get("followup_issue") or "").strip():
                failures.append(
                    prefix + f"issues[{issue_index}] lacks concrete followup_issue"
                )

        minutes_reading = record.get("minutes_reading")
        if not _has_minimum_reading_time(minutes_reading):
            failures.append(prefix + "minutes_reading must be at least 20")

        if (
            _session_core_steps_pass(steps)
            and not missing
            and _has_minimum_reading_time(minutes_reading)
        ):
            valid_session_ids.add(session_id)

        if _session_live_provider_passed(record, steps):
            live_provider_sessions.add(session_id)
        elif bool(record.get("live_provider_ai")):
            failures.append(
                prefix
                + "live_provider_ai=true requires provider-backed steps 3 and 4 to pass"
            )
        if bool(record.get("live_provider_ai")) and _provider_status(record) != "ready":
            failures.append(prefix + "live_provider_ai=true requires provider_status=ready")

        if bool(record.get("citation_traced")) or _step_status(steps.get("5")) == "pass":
            citation_trace_sessions.add(session_id)

        if str(record.get("entry_door", "")).strip() in NON_LIBRARY_ENTRY_DOORS:
            non_library_sessions.add(session_id)

    closure_failures = _closure_failures(
        valid_session_ids=valid_session_ids,
        live_provider_sessions=live_provider_sessions,
        citation_trace_sessions=citation_trace_sessions,
        non_library_sessions=non_library_sessions,
    )
    failures.extend(closure_failures)

    return DogfoodReport(
        total_sessions=len(records),
        valid_sessions=len(valid_session_ids),
        live_provider_sessions=len(live_provider_sessions),
        citation_trace_sessions=len(citation_trace_sessions),
        non_library_sessions=len(non_library_sessions),
        closure_ready=not failures,
        failures=tuple(failures),
    )


def _step_followup_failures(prefix: str, steps: dict[Any, Any]) -> list[str]:
    failures: list[str] = []
    for step_id, raw_step in sorted(steps.items(), key=lambda item: str(item[0])):
        if not isinstance(raw_step, dict):
            failures.append(prefix + f"step {step_id} must be an object")
            continue
        status = _step_status(raw_step)
        irritation = str(raw_step.get("irritation") or "").strip()
        if status == "fail" or irritation:
            followup = str(raw_step.get("followup_issue") or "").strip()
            if not followup:
                failures.append(
                    prefix
                    + f"step {step_id} has failure/irritation without followup_issue"
                )
    return failures


def _step_status_failures(prefix: str, steps: dict[Any, Any]) -> list[str]:
    failures: list[str] = []
    for step_id, raw_step in sorted(steps.items(), key=lambda item: str(item[0])):
        if not isinstance(raw_step, dict):
            continue
        status = _step_status(raw_step)
        if status not in ALLOWED_STEP_STATUSES:
            failures.append(
                prefix
                + f"step {step_id} status must be one of "
                + ", ".join(sorted(ALLOWED_STEP_STATUSES))
            )
            continue
        if status == "inert" and str(step_id) not in {"3", "4"}:
            failures.append(prefix + f"step {step_id} cannot be inert")
    return failures


def _step_status(raw_step: Any) -> str:
    if not isinstance(raw_step, dict):
        return ""
    return str(raw_step.get("status") or "").strip().lower()


def _provider_status(record: dict[str, Any]) -> str:
    return str(record.get("provider_status") or "").strip().lower()


def _session_core_steps_pass(steps: dict[Any, Any]) -> bool:
    # Steps 3-4 can be live-provider passes or honestly inert before provider
    # activation. Closure still requires >=5 live-provider sessions separately.
    for step in ("1", "2", "5", "6", "7"):
        if _step_status(steps.get(step)) != "pass":
            return False
    return all(_step_status(steps.get(step)) in {"pass", "inert"} for step in ("3", "4"))


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_SESSION_FIELDS:
        if field == "minutes_reading":
            if field not in record:
                missing.append(field)
            continue
        if not record.get(field):
            missing.append(field)
    return missing


def _session_live_provider_passed(record: dict[str, Any], steps: dict[Any, Any]) -> bool:
    if not bool(record.get("live_provider_ai")):
        return False
    return _step_status(steps.get("3")) == "pass" and _step_status(steps.get("4")) == "pass"


def _has_minimum_reading_time(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value >= 20
    if isinstance(value, str):
        try:
            return float(value.strip()) >= 20
        except ValueError:
            return False
    return False


def _closure_failures(
    *,
    valid_session_ids: set[str],
    live_provider_sessions: set[str],
    citation_trace_sessions: set[str],
    non_library_sessions: set[str],
) -> list[str]:
    failures: list[str] = []
    if len(valid_session_ids) < 10:
        failures.append(
            f"closure requires >=10 valid sessions; found {len(valid_session_ids)}"
        )
    if len(valid_session_ids & live_provider_sessions) < 5:
        failures.append(
            "closure requires >=5 valid sessions with live_provider_ai=true; "
            f"found {len(valid_session_ids & live_provider_sessions)}"
        )
    if len(valid_session_ids & citation_trace_sessions) < 3:
        failures.append(
            "closure requires >=3 valid sessions with citation/source tracing; "
            f"found {len(valid_session_ids & citation_trace_sessions)}"
        )
    if len(valid_session_ids & non_library_sessions) < 1:
        failures.append(
            "closure requires >=1 valid session from a non-Library door "
            f"({', '.join(sorted(NON_LIBRARY_ENTRY_DOORS))}); found 0"
        )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="Read activation dogfood JSONL log")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON instead of human-readable text.",
    )
    args = parser.parse_args(argv)

    try:
        report = validate_sessions(load_jsonl(args.log))
    except (OSError, ValueError) as exc:
        print(f"read-dogfood: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print(
            "read-dogfood: "
            f"{report.valid_sessions}/{report.total_sessions} valid sessions, "
            f"{report.live_provider_sessions} live-provider, "
            f"{report.citation_trace_sessions} citation-traced, "
            f"{report.non_library_sessions} non-library"
        )
        for failure in report.failures:
            print(f"  - {failure}")
    return 0 if report.closure_ready else 1


if __name__ == "__main__":
    sys.exit(main())
