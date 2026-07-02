#!/usr/bin/env python3
"""Validate the Read activation dogfood log.

This is NOT a product-completion shortcut. ``specs/activation/golden-path.md``
states the activation rule: Read closes only after 10 distinct operator sessions
are logged, with live-provider coverage, citation tracing, a non-Library entry
point, at least 20 minutes of reading per valid session, and concrete follow-ups
for every failure or irritation.

The tool makes that rule executable over a JSONL log so future agents cannot
convert "CI is green" into "Read is done". It never records sessions itself and
never judges answer quality; the operator's log remains the source of truth. A
mechanically complete log must end with an operator ``verdict``: ``ACTIVATE``,
``REPAIR``, or ``ROLL BACK CLAIM``. ``REPAIR`` must also list concrete
``blocking_issue_ids``.

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
      "verdict": "ACTIVATE",
      "steps": {
        "1": {
          "status": "pass",
          "visible_content_note": "visible heading/table/math/figure note"
        },
        "2": {
          "status": "pass",
          "selected_text": "highlighted passage text",
          "menu_labels": ["Ask", "Investigate", "Trace source"]
        },
        "3": {
          "status": "pass",
          "first_answer": "first provider answer"
        },
        "4": {
          "status": "pass",
          "investigation_id": "child investigation/session id"
        },
        "5": {"status": "pass"},
        "6": {"status": "pass", "return_context_note": "scroll/context survived note"},
        "7": {"status": "pass", "operator_note": "free-form reading note"}
      }
    }

Failures or irritations must include a concrete ``followup_issue`` on the step
or in the session-level ``issues`` list.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

REQUIRED_SESSION_FIELDS: tuple[str, ...] = (
    "session_id",
    "date",
    "build_sha",
    "url",
    "operator",
    "document_id",
    "entry_door",
    "provider_status",
    "live_provider_ai",
    "citation_traced",
    "minutes_reading",
    "steps",
)
REQUIRED_BOOLEAN_FIELDS: tuple[str, ...] = ("live_provider_ai", "citation_traced")
REQUIRED_STEPS: tuple[str, ...] = tuple(str(i) for i in range(1, 8))
NON_LIBRARY_ENTRY_DOORS: frozenset[str] = frozenset(
    {
        "search",
        "command_palette",
        "drw_citation",
        "write_trace",
        "write_trace_to_source",
        "citation",
        "deep_research_workspace",
        "unified_search",
    }
)
ALLOWED_STEP_STATUSES: frozenset[str] = frozenset({"pass", "fail", "inert"})
ALLOWED_FINAL_VERDICTS: tuple[str, ...] = (
    "ACTIVATE",
    "REPAIR",
    "ROLL BACK CLAIM",
)


@dataclass(frozen=True)
class DogfoodReport:
    total_sessions: int
    valid_sessions: int
    live_provider_sessions: int
    citation_trace_sessions: int
    non_library_sessions: int
    final_verdict: str | None
    closure_ready: bool
    failures: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_sessions": self.total_sessions,
            "valid_sessions": self.valid_sessions,
            "live_provider_sessions": self.live_provider_sessions,
            "citation_trace_sessions": self.citation_trace_sessions,
            "non_library_sessions": self.non_library_sessions,
            "final_verdict": self.final_verdict,
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
        session_id = _required_text(record.get("session_id")) or f"<record-{index}>"
        prefix = f"{session_id}: "

        if session_id in seen_session_ids:
            failures.append(prefix + "duplicate session_id")
            continue
        seen_session_ids.add(session_id)

        missing = _missing_required_fields(record)
        if missing:
            failures.append(prefix + "missing required fields: " + ", ".join(missing))
        field_format_failures = _field_format_failures(prefix, record)
        failures.extend(field_format_failures)
        invalid_boolean_fields = _invalid_boolean_fields(record)
        for field in invalid_boolean_fields:
            failures.append(prefix + f"{field} must be a boolean")

        steps = record.get("steps")
        if not isinstance(steps, dict):
            failures.append(prefix + "steps must be an object keyed by '1'..'7'")
            continue

        missing_steps = [step for step in REQUIRED_STEPS if step not in steps]
        if missing_steps:
            failures.append(prefix + "missing golden-path steps: " + ", ".join(missing_steps))

        step_failures = _step_followup_failures(prefix, steps)
        failures.extend(step_failures)
        step_status_failures = _step_status_failures(prefix, steps)
        failures.extend(step_status_failures)
        reader_open_evidence_failures = _reader_open_evidence_failures(prefix, steps)
        failures.extend(reader_open_evidence_failures)
        selection_evidence_failures = _selection_evidence_failures(prefix, steps)
        failures.extend(selection_evidence_failures)
        return_context_evidence_failures = _return_context_evidence_failures(prefix, steps)
        failures.extend(return_context_evidence_failures)
        reading_work_evidence_failures = _reading_work_evidence_failures(prefix, steps)
        failures.extend(reading_work_evidence_failures)
        inert_provider_evidence_failures = _inert_provider_evidence_failures(prefix, steps)
        failures.extend(inert_provider_evidence_failures)
        provider_status_failures = _provider_status_failures(prefix, record)
        failures.extend(provider_status_failures)
        live_provider_evidence_failures = _live_provider_evidence_failures(prefix, record, steps)
        failures.extend(live_provider_evidence_failures)
        citation_evidence_failures = _citation_evidence_failures(prefix, record, steps)
        failures.extend(citation_evidence_failures)

        issue_failures: list[str] = []
        for issue_index, issue in enumerate(record.get("issues") or [], start=1):
            if not isinstance(issue, dict):
                issue_failures.append(prefix + f"issues[{issue_index}] must be an object")
                continue
            if not str(issue.get("followup_issue") or "").strip():
                issue_failures.append(
                    prefix + f"issues[{issue_index}] lacks concrete followup_issue"
                )
        failures.extend(issue_failures)

        minutes_reading = record.get("minutes_reading")
        if not _has_minimum_reading_time(minutes_reading):
            failures.append(prefix + "minutes_reading must be at least 20")

        session_is_valid = (
            _session_core_steps_pass(steps)
            and not missing
            and not field_format_failures
            and not invalid_boolean_fields
            and not missing_steps
            and not step_failures
            and not step_status_failures
            and not reader_open_evidence_failures
            and not selection_evidence_failures
            and not return_context_evidence_failures
            and not reading_work_evidence_failures
            and not inert_provider_evidence_failures
            and not provider_status_failures
            and not live_provider_evidence_failures
            and not citation_evidence_failures
            and not issue_failures
            and _has_minimum_reading_time(minutes_reading)
        )
        if session_is_valid:
            valid_session_ids.add(session_id)

        live_provider_passed = _session_live_provider_passed(record, steps)
        if session_is_valid and live_provider_passed:
            live_provider_sessions.add(session_id)
        elif record.get("live_provider_ai") is True and not live_provider_passed:
            failures.append(
                prefix
                + "live_provider_ai=true requires provider-backed steps 3 and 4 to pass"
            )
        citation_traced = _session_citation_traced(record, steps)
        if session_is_valid and citation_traced:
            citation_trace_sessions.add(session_id)
        elif (
            record.get("citation_traced") is True
            and not citation_traced
            and _step_status(steps.get("5")) != "pass"
        ):
            failures.append(prefix + "citation_traced=true requires step 5 to pass")

        if (
            session_is_valid
            and _entry_door_token(record.get("entry_door")) in NON_LIBRARY_ENTRY_DOORS
        ):
            non_library_sessions.add(session_id)

    closure_failures = _closure_failures(
        valid_session_ids=valid_session_ids,
        live_provider_sessions=live_provider_sessions,
        citation_trace_sessions=citation_trace_sessions,
        non_library_sessions=non_library_sessions,
    )
    failures.extend(closure_failures)
    final_verdict = _final_verdict(records)
    if not closure_failures:
        failures.extend(_final_verdict_failures(final_verdict, records))

    return DogfoodReport(
        total_sessions=len(records),
        valid_sessions=len(valid_session_ids),
        live_provider_sessions=len(live_provider_sessions),
        citation_trace_sessions=len(citation_trace_sessions),
        non_library_sessions=len(non_library_sessions),
        final_verdict=final_verdict,
        closure_ready=not failures,
        failures=tuple(failures),
    )


def session_template(kind: str) -> dict[str, Any]:
    """Return one JSONL-safe seed record for an operator-authored dogfood note."""
    if kind not in {"inert", "live", "live-citation"}:
        raise ValueError("template kind must be one of: inert, live, live-citation")

    live = kind in {"live", "live-citation"}
    citation = kind == "live-citation"
    steps: dict[str, dict[str, Any]] = {
        "1": {
            "status": "pass",
            "visible_content_note": "Visible heading/table/math/figure or structured blocks.",
        },
        "2": {
            "status": "pass",
            "selected_text": "Exact selected passage text.",
            "menu_labels": ["Ask", "Investigate", "Trace source"],
        },
        "3": {"status": "pass" if live else "inert"},
        "4": {"status": "pass" if live else "inert"},
        "5": {"status": "pass"},
        "6": {
            "status": "pass",
            "return_context_note": "Back/return preserved enough context to keep reading.",
        },
        "7": {
            "status": "pass",
            "operator_note": "Read for 20+ minutes; note dead ends or friction here.",
        },
    }
    if live:
        steps["3"]["first_answer"] = "First useful provider-backed answer."
        steps["4"]["investigation_id"] = "child-investigation-id"
    else:
        steps["3"]["exact_no_key_copy"] = (
            "Dialogue requires provider activation keys."
        )
        steps["4"]["exact_no_key_copy"] = (
            "Research spin-out requires provider activation keys."
        )
    if citation:
        steps["5"].update(
            {
                "source_document_id": "source-doc-1",
                "chunk_id": "chunk-1",
                "result_url": "https://antiek.ai/read/source-doc-1?chunk=chunk-1",
            }
        )

    return {
        "session_id": "2026-06-30-operator-001",
        "date": "2026-06-30",
        "build_sha": "abc123",
        "url": "https://antiek.ai/read/doc-1",
        "operator": "Operator",
        "document_id": "doc-1",
        "entry_door": "library" if not citation else "command_palette",
        "provider_status": "ready" if live else "absent",
        "live_provider_ai": live,
        "citation_traced": citation,
        "minutes_reading": 22,
        "steps": steps,
    }


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


def _reader_open_evidence_failures(prefix: str, steps: dict[Any, Any]) -> list[str]:
    step = steps.get("1")
    if not isinstance(step, dict) or _step_status(step) != "pass":
        return []

    screenshot_ref = (
        _required_text(step.get("screenshot"))
        or _required_text(step.get("screenshot_url"))
        or _required_text(step.get("screenshot_path"))
    )
    visible_note = (
        _required_text(step.get("visible_content_note"))
        or _required_text(step.get("structured_content_note"))
        or _required_text(step.get("render_note"))
    )
    if not screenshot_ref and not visible_note:
        return [
            prefix
            + "step 1 requires screenshot reference or visible_content_note"
        ]
    return []


def _selection_evidence_failures(prefix: str, steps: dict[Any, Any]) -> list[str]:
    step = steps.get("2")
    if not isinstance(step, dict) or _step_status(step) != "pass":
        return []

    failures: list[str] = []
    selected_text = _required_text(step.get("selected_text"))
    menu_labels = step.get("menu_labels", step.get("action_menu_labels"))
    if not selected_text:
        failures.append(prefix + "step 2 requires selected_text")
    if not _has_non_empty_string_list(menu_labels):
        failures.append(prefix + "step 2 requires menu_labels")
    return failures


def _return_context_evidence_failures(prefix: str, steps: dict[Any, Any]) -> list[str]:
    step = steps.get("6")
    if not isinstance(step, dict) or _step_status(step) != "pass":
        return []

    context_note = (
        _required_text(step.get("return_context_note"))
        or _required_text(step.get("context_note"))
        or _required_text(step.get("scroll_context_note"))
    )
    if not context_note:
        return [prefix + "step 6 requires return_context_note"]
    return []


def _reading_work_evidence_failures(prefix: str, steps: dict[Any, Any]) -> list[str]:
    step = steps.get("7")
    if not isinstance(step, dict) or _step_status(step) != "pass":
        return []

    operator_note = _required_text(step.get("operator_note")) or _required_text(
        step.get("reading_note")
    )
    if not operator_note:
        return [prefix + "step 7 requires operator_note"]
    return []


def _inert_provider_evidence_failures(prefix: str, steps: dict[Any, Any]) -> list[str]:
    failures: list[str] = []
    for step_id in ("3", "4"):
        step = steps.get(step_id)
        if not isinstance(step, dict) or _step_status(step) != "inert":
            continue
        if not _activation_boundary_copy(step):
            failures.append(
                prefix
                + f"inert provider step {step_id} requires exact no-key boundary copy"
            )
    return failures


def _activation_boundary_copy(step: dict[str, Any]) -> str:
    return (
        _required_text(step.get("exact_no_key_copy"))
        or _required_text(step.get("no_key_copy"))
        or _required_text(step.get("activation_boundary_copy"))
        or _required_text(step.get("boundary_copy"))
    )


def _has_non_empty_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def _provider_status(record: dict[str, Any]) -> str:
    return str(record.get("provider_status") or "").strip().lower()


def _provider_status_failures(prefix: str, record: dict[str, Any]) -> list[str]:
    if record.get("live_provider_ai") is True and _provider_status(record) != "ready":
        return [prefix + "live_provider_ai=true requires provider_status=ready"]
    return []


def _entry_door_token(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


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
        if field in REQUIRED_BOOLEAN_FIELDS:
            if field not in record:
                missing.append(field)
            continue
        if not _required_text(record.get(field)):
            missing.append(field)
    return missing


def _field_format_failures(prefix: str, record: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if _required_text(record.get("date")) and not _is_iso_date(record.get("date")):
        failures.append(prefix + "date must be YYYY-MM-DD")
    if _required_text(record.get("build_sha")) and not _is_git_sha(record.get("build_sha")):
        failures.append(prefix + "build_sha must be a 6-40 character git SHA")
    if _required_text(record.get("url")) and not _is_http_url(record.get("url")):
        failures.append(prefix + "url must be an http(s) URL")
    return failures


def _is_iso_date(value: Any) -> bool:
    text = _required_text(value)
    try:
        parsed = dt.date.fromisoformat(text)
    except ValueError:
        return False
    return parsed.isoformat() == text


def _is_git_sha(value: Any) -> bool:
    text = _required_text(value)
    return 6 <= len(text) <= 40 and all(ch in "0123456789abcdefABCDEF" for ch in text)


def _is_http_url(value: Any) -> bool:
    parsed = urlparse(_required_text(value))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _required_text(value: Any) -> str:
    return str(value or "").strip()


def _invalid_boolean_fields(record: dict[str, Any]) -> list[str]:
    return [
        field
        for field in REQUIRED_BOOLEAN_FIELDS
        if field in record and not isinstance(record.get(field), bool)
    ]


def _session_live_provider_passed(record: dict[str, Any], steps: dict[Any, Any]) -> bool:
    if record.get("live_provider_ai") is not True:
        return False
    return (
        _step_status(steps.get("3")) == "pass"
        and _step_status(steps.get("4")) == "pass"
        and not _live_provider_evidence_failures("", record, steps)
    )


def _live_provider_evidence_failures(
    prefix: str,
    record: dict[str, Any],
    steps: dict[Any, Any],
) -> list[str]:
    if record.get("live_provider_ai") is not True:
        return []
    if _step_status(steps.get("3")) != "pass" or _step_status(steps.get("4")) != "pass":
        return []

    failures: list[str] = []
    step_3 = steps.get("3")
    step_4 = steps.get("4")
    first_answer = (
        _required_text(step_3.get("first_answer"))
        if isinstance(step_3, dict)
        else ""
    )
    research_id = ""
    if isinstance(step_4, dict):
        research_id = (
            _required_text(step_4.get("investigation_id"))
            or _required_text(step_4.get("session_id"))
        )
    if not first_answer:
        failures.append(prefix + "live provider step 3 requires first_answer")
    if not research_id:
        failures.append(prefix + "live provider step 4 requires investigation_id or session_id")
    return failures


def _session_citation_traced(record: dict[str, Any], steps: dict[Any, Any]) -> bool:
    if record.get("citation_traced") is not True:
        return False
    return (
        _step_status(steps.get("5")) == "pass"
        and not _citation_evidence_failures("", record, steps)
    )


def _citation_evidence_failures(
    prefix: str,
    record: dict[str, Any],
    steps: dict[Any, Any],
) -> list[str]:
    if record.get("citation_traced") is not True:
        return []
    step = steps.get("5")
    if not isinstance(step, dict) or _step_status(step) != "pass":
        return []

    failures: list[str] = []
    source_document_id = _required_text(step.get("source_document_id"))
    anchor = _required_text(step.get("chunk_id")) or _required_text(step.get("anchor"))
    result_url = _required_text(step.get("result_url"))
    if not source_document_id:
        failures.append(prefix + "citation step 5 requires source_document_id")
    if not anchor:
        failures.append(prefix + "citation step 5 requires chunk_id or anchor")
    if not result_url:
        failures.append(prefix + "citation step 5 requires result_url")
    elif not _is_http_url(result_url):
        failures.append(prefix + "citation step 5 result_url must be an http(s) URL")
    else:
        result_target = _reader_document_from_url(result_url)
        if source_document_id and result_target != source_document_id:
            failures.append(
                prefix
                + "citation step 5 result_url must open /read/{source_document_id}"
            )
        if anchor and not _url_carries_anchor(result_url, anchor):
            failures.append(
                prefix
                + "citation step 5 result_url must include the recorded chunk_id or anchor"
            )
    return failures


def _reader_document_from_url(value: str) -> str | None:
    parsed = urlparse(value)
    marker = "/read/"
    if marker not in parsed.path:
        return None
    suffix = parsed.path.split(marker, 1)[1]
    if not suffix:
        return None
    return unquote(suffix.split("/", 1)[0])


def _url_carries_anchor(value: str, anchor: str) -> bool:
    parsed = urlparse(value)
    wanted = anchor.strip()
    if not wanted:
        return False
    query_values: list[str] = []
    for values in parse_qs(parsed.query, keep_blank_values=True).values():
        query_values.extend(values)
    haystack = "\n".join([*query_values, parsed.fragment])
    return wanted in unquote(haystack)


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


def _final_verdict(records: list[dict[str, Any]]) -> str | None:
    if not records:
        return None
    raw_verdict = _required_text(records[-1].get("verdict"))
    if not raw_verdict:
        return None
    normalized = raw_verdict.replace("_", " ").replace("-", " ").upper()
    normalized = " ".join(normalized.split())
    for verdict in ALLOWED_FINAL_VERDICTS:
        if normalized == verdict:
            return verdict
    return raw_verdict


def _final_verdict_failures(
    final_verdict: str | None, records: list[dict[str, Any]]
) -> list[str]:
    allowed = ", ".join(ALLOWED_FINAL_VERDICTS)
    if final_verdict is None:
        return [f"final verdict required once closure evidence passes: {allowed}"]
    if final_verdict not in ALLOWED_FINAL_VERDICTS:
        return [f"final verdict must be one of: {allowed}"]
    if final_verdict == "REPAIR":
        repair_failures = _blocking_issue_id_failures(records[-1])
        if repair_failures:
            return repair_failures
    if final_verdict != "ACTIVATE":
        return [f"closure requires final verdict ACTIVATE; found {final_verdict}"]
    return []


def _blocking_issue_id_failures(record: dict[str, Any]) -> list[str]:
    issue_ids = record.get("blocking_issue_ids")
    if not isinstance(issue_ids, list):
        return ["REPAIR verdict requires blocking_issue_ids to be a list"]
    if any(not isinstance(raw_issue_id, str) for raw_issue_id in issue_ids):
        return ["blocking_issue_ids entries must be non-empty strings"]
    if any(not raw_issue_id.strip() for raw_issue_id in issue_ids):
        return ["blocking_issue_ids entries must be non-empty strings"]
    if not _blocking_issue_ids(record):
        return ["REPAIR verdict requires at least one blocking_issue_ids entry"]
    return []


def _blocking_issue_ids(record: dict[str, Any]) -> tuple[str, ...]:
    issue_ids = record.get("blocking_issue_ids")
    if not isinstance(issue_ids, list):
        return ()
    return tuple(
        issue_id
        for raw_issue_id in issue_ids
        if isinstance(raw_issue_id, str) and (issue_id := raw_issue_id.strip())
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "log",
        nargs="?",
        type=Path,
        help="Read activation dogfood JSONL log",
    )
    parser.add_argument(
        "--template",
        choices=("inert", "live", "live-citation"),
        help=(
            "Print one JSONL-compatible seed session and exit. The operator must "
            "replace the evidence before appending it to the dogfood log."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON instead of human-readable text.",
    )
    args = parser.parse_args(argv)

    if args.template:
        print(json.dumps(session_template(args.template), sort_keys=True))
        return 0

    if args.log is None:
        parser.error("the following arguments are required: log")

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
            f"{report.non_library_sessions} non-library, "
            f"verdict={report.final_verdict or 'missing'}"
        )
        for failure in report.failures:
            print(f"  - {failure}")
    return 0 if report.closure_ready else 1


if __name__ == "__main__":
    sys.exit(main())
