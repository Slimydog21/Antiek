#!/usr/bin/env python3
"""Deterministic event-log bisector for bad or empty synthesis runs."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from substrate.schemas.events import ActionType
from tools.eventlog_query import _payload, _safe_trajectory

Cause = Literal["DATA", "CODE", "DISPATCH", "INCONCLUSIVE"]

# SPR-01 chunk_count semantics: 0 means retrieval ran and returned nothing;
# None means unknown/pre-SPR-01/unavailable. The floor for usable retrieval is 1.
CHUNK_FLOOR = 1
SYNTHESIS_MIN_CHARS = 10


@dataclass(frozen=True)
class Verdict:
    cause: Cause
    reason: str
    evidence: list[dict[str, Any]]


def _evidence(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": row.get("event_id"),
        "action_type": row.get("action_type"),
    }


def _provider_model(row: dict[str, Any] | None) -> str:
    if row is None:
        return "unknown/unknown"
    payload = _payload(row)
    return f"{payload.get('provider') or 'unknown'}/{payload.get('model') or 'unknown'}"


def _is_synthesis_validation_failure(row: dict[str, Any]) -> bool:
    if row.get("action_type") != ActionType.ROLE_VALIDATION_FAILED.value:
        return False
    payload = _payload(row)
    values = [
        row.get("role"),
        payload.get("role"),
        payload.get("target_role"),
        payload.get("stage"),
        payload.get("action_type"),
    ]
    return any(isinstance(value, str) and "synth" in value.lower() for value in values)


def _synthesis_text(payload: dict[str, Any]) -> str | None:
    for key in ("synthesis", "text", "content", "output", "answer"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return None


def _is_empty_synthesis(row: dict[str, Any]) -> bool:
    if row.get("action_type") != ActionType.SYNTHESIZE_DELIVERED.value:
        return False
    text = _synthesis_text(_payload(row))
    # A ``synthesize.delivered`` event whose synthesis text is MISSING (None)
    # is a structurally-broken synthesis — the exact CODE failure this tool
    # localizes — so treat a missing field as empty, not as "nothing to judge".
    # (Guarded above to SYNTHESIZE_DELIVERED, so non-synthesis events never match.)
    return text is None or len(text.strip()) < SYNTHESIS_MIN_CHARS


def _chunk_count(row: dict[str, Any]) -> int | None:
    value = _payload(row).get("chunk_count")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None


def _missing_event_names(rows: list[dict[str, Any]]) -> list[str]:
    action_types = {row.get("action_type") for row in rows}
    missing: list[str] = []
    if ActionType.EVIDENCE_RETRIEVE_DELIVERED.value not in action_types:
        missing.append(ActionType.EVIDENCE_RETRIEVE_DELIVERED.value)
    if ActionType.DISPATCH_CALL.value not in action_types:
        missing.append(ActionType.DISPATCH_CALL.value)
    has_synthesis_outcome = (
        ActionType.SYNTHESIZE_DELIVERED.value in action_types
        or any(_is_synthesis_validation_failure(row) for row in rows)
    )
    if ActionType.SYNTHESIZE_REQUESTED.value in action_types and ActionType.SYNTHESIZE_DELIVERED.value not in action_types:
        missing.append(ActionType.SYNTHESIZE_DELIVERED.value)
    elif not has_synthesis_outcome:
        missing.append(f"{ActionType.SYNTHESIZE_DELIVERED.value} or {ActionType.ROLE_VALIDATION_FAILED.value}")
    if not (
        ActionType.INVESTIGATION_COMPLETED.value in action_types
        or ActionType.INVESTIGATION_FAILED.value in action_types
    ):
        missing.append(f"{ActionType.INVESTIGATION_COMPLETED.value} or {ActionType.INVESTIGATION_FAILED.value}")
    return missing


def bisect(investigation_id: str, events_dir: str | None = None) -> Verdict:
    rows = [row for row in _safe_trajectory(investigation_id, events_dir) if isinstance(row, dict)]
    if not rows:
        return Verdict(
            "INCONCLUSIVE",
            "missing event log rows; cannot find evidence.retrieve.delivered, dispatch.call, or synthesize.delivered",
            [],
        )

    dispatch_by_event_id = {
        str(row["event_id"]): row
        for row in rows
        if row.get("action_type") == ActionType.DISPATCH_CALL.value and row.get("event_id") is not None
    }

    # Branch order is load-bearing: a provider/dispatch failure can explain
    # every downstream symptom, so check it before DATA, then CODE.
    dispatch_failures: list[dict[str, Any]] = []
    dispatch_failure_context: list[str] = []
    for row in rows:
        action_type = row.get("action_type")
        if action_type == ActionType.DISPATCH_CALL.value and _payload(row).get("finish_reason") == "error":
            dispatch_failures.append(row)
            dispatch_failure_context.append(_provider_model(row))
        elif action_type == ActionType.ROLE_CALL_FAILED.value:
            dispatch_failures.append(row)
            parent = dispatch_by_event_id.get(str(row.get("parent_event_id")))
            dispatch_failure_context.append(_provider_model(parent))

    if dispatch_failures:
        providers = ", ".join(sorted(set(dispatch_failure_context))) or "unknown/unknown"
        return Verdict(
            "DISPATCH",
            f"provider dispatch failed for {providers}",
            [_evidence(row) for row in dispatch_failures],
        )

    retrieval_rows = [
        row for row in rows if row.get("action_type") == ActionType.EVIDENCE_RETRIEVE_DELIVERED.value
    ]
    empty_retrieval = [
        row for row in retrieval_rows if (_chunk_count(row) is not None and _chunk_count(row) < CHUNK_FLOOR)
    ]
    if empty_retrieval:
        return Verdict(
            "DATA",
            f"retrieval returned fewer than {CHUNK_FLOOR} chunks",
            [_evidence(row) for row in empty_retrieval],
        )

    successful_retrieval = [
        row for row in retrieval_rows if (_chunk_count(row) is not None and _chunk_count(row) >= CHUNK_FLOOR)
    ]
    successful_dispatch = [
        row
        for row in rows
        if row.get("action_type") == ActionType.DISPATCH_CALL.value
        and _payload(row).get("finish_reason") != "error"
    ]
    empty_synthesis = [row for row in rows if _is_empty_synthesis(row)]
    synthesis_validation_failures = [row for row in rows if _is_synthesis_validation_failure(row)]

    if successful_retrieval and successful_dispatch and (empty_synthesis or synthesis_validation_failures):
        return Verdict(
            "CODE",
            "retrieval and dispatch succeeded, but synthesis delivered empty/short output or failed validation",
            [
                *[_evidence(row) for row in successful_retrieval],
                *[_evidence(row) for row in successful_dispatch],
                *[_evidence(row) for row in empty_synthesis],
                *[_evidence(row) for row in synthesis_validation_failures],
            ],
        )

    missing = _missing_event_names(rows)
    if missing:
        return Verdict(
            "INCONCLUSIVE",
            "missing events needed to decide: " + ", ".join(missing),
            [],
        )
    return Verdict(
        "INCONCLUSIVE",
        "no DATA, CODE, or DISPATCH failure signal found in the event log",
        [],
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events-dir", default=None)
    parser.add_argument("--investigation-id", required=True)
    parser.add_argument("--json", action="store_true", help="Emit verdict as JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    verdict = bisect(args.investigation_id, events_dir=args.events_dir)
    if args.json:
        print(json.dumps(asdict(verdict), indent=2, sort_keys=True))
    else:
        print(f"CAUSE: {verdict.cause}")
        print(f"REASON: {verdict.reason}")
        print("EVIDENCE:")
        if verdict.evidence:
            for item in verdict.evidence:
                print(f"- {item.get('event_id')} {item.get('action_type')}")
        else:
            print("- none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
