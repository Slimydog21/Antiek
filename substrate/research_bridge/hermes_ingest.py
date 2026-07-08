"""Read-only Hermes research-event ingest bridge.

A *separate* agent harness ("Hermes", at ``~/.hermes``) writes real research
events to ``~/.hermes/research_events/*.jsonl``. This module is a READ-ONLY
adapter that brings those research traces into Antiek's corpus via the LIVE
``ingest_file`` path: it parses the jsonl, groups events by investigation,
renders each investigation into a provenance-carrying markdown document, and
ingests it as an uploaded file (content-addressed → idempotent, provenance
stamped via ``metadata`` / ``ip_holder_id``).

It performs NO model call at ingest time. Distillation — the GLM-5.2 document
note pass over the produced document — is the caller's existing async step
(``distill_ingested_document``) run over *any* ingested document, so the
bridge itself stays network-free, deterministic, and testable without credits.
That also preserves the claude-less footprint: Hermes data is parsed by Antiek's
own GLM-5.2 substrate downstream, never by Hermes's own model.

The Hermes directory is strictly READ-ONLY to this module: it never writes,
creates, or deletes anything there. Malformed input is tolerated and counted
honestly rather than raised.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from runtime.db_lock import LockedConnection
from substrate.research_bridge.ingest_file import FileIngestResult, ingest_file

HERMES_INGEST_VERSION: int = 1
DEFAULT_HERMES_EVENTS_DIR: str = os.path.expanduser("~/.hermes/research_events")
_HERMES_MARKDOWN_CONTENT_TYPE: str = "text/markdown"

# Only these keys are required for a line to represent a usable event.
_REQUIRED_EVENT_KEYS: tuple[str, ...] = ("event_id", "investigation_id")


HermesIngestStatus = Literal["ok", "cache_hit", "error", "skipped_empty"]


@dataclass(frozen=True)
class HermesEventRecord:
    """One parsed line from a Hermes ``research_events/*.jsonl`` file."""

    event_id: str
    investigation_id: str
    synthesis_id: str | None
    phase: str | None
    role: str | None
    action_type: str | None
    emitted_at: str | None
    schema_version: int
    payload: dict[str, Any]


@dataclass(frozen=True)
class HermesInvestigation:
    """All events for one Hermes investigation, chronologically ordered."""

    investigation_id: str
    events: tuple[HermesEventRecord, ...]
    first_emitted_at: str | None
    last_emitted_at: str | None


@dataclass(frozen=True)
class HermesIngestResult:
    """Outcome of ingesting one Hermes investigation.

    ``status`` is the load-bearing field:
      - ``ok``          — a NEW document was written (was_new=True)
      - ``cache_hit``   — content-addressed dedup hit (was_new=False; re-run)
      - ``skipped_empty`` — rendered text was empty; nothing written
      - ``error``       — ingest raised; error_message carries the reason
    """

    investigation_id: str
    document_id: str | None
    status: HermesIngestStatus
    events_count: int
    was_new: bool
    source_label: str
    document_type: str | None
    error_message: str | None = None


@dataclass(frozen=True)
class HermesIngestBatch:
    """Roll-up of an ``ingest_hermes_events`` run over a whole events dir."""

    results: tuple[HermesIngestResult, ...]
    new_count: int
    cache_hit_count: int
    skipped_count: int
    error_count: int
    malformed_lines: int = 0


def parse_hermes_event_line(line: str) -> HermesEventRecord | None:
    """Parse one jsonl line into a ``HermesEventRecord``.

    Returns ``None`` for blank lines, malformed JSON, or a structurally valid
    JSON object missing the required keys (``event_id`` + ``investigation_id``).
    NEVER raises — callers may feed arbitrary directories.
    """
    stripped = line.strip()
    if not stripped:
        return None
    try:
        obj: Any = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    if any(k not in obj for k in _REQUIRED_EVENT_KEYS):
        return None
    event_id = obj["event_id"]
    investigation_id = obj["investigation_id"]
    if not isinstance(event_id, str) or not isinstance(investigation_id, str):
        return None
    if not event_id or not investigation_id:
        return None
    raw_payload = obj.get("payload", {})
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    raw_schema_version = obj.get("schema_version", 0)
    try:
        schema_version = int(raw_schema_version)
    except (TypeError, ValueError):
        schema_version = 0
    return HermesEventRecord(
        event_id=event_id,
        investigation_id=investigation_id,
        synthesis_id=_as_optional_str(obj.get("synthesis_id")),
        phase=_as_optional_str(obj.get("phase")),
        role=_as_optional_str(obj.get("role")),
        action_type=_as_optional_str(obj.get("action_type")),
        emitted_at=_as_optional_str(obj.get("emitted_at")),
        schema_version=schema_version,
        payload=payload,
    )


def _scan_event_lines(
    events_dir: str | Path,
) -> Iterator[tuple[HermesEventRecord | None, bool]]:
    """Yield ``(record, is_malformed)`` per non-blank line under ``events_dir``.

    Exactly one meaningful field is set: a parseable line yields
    ``(HermesEventRecord, False)``; a structurally invalid line yields
    ``(None, True)``. Blank lines are skipped (not malformed). An unreadable
    or byte-corrupted file is skipped wholesale without aborting the sweep —
    ``errors="replace"`` keeps a partially-corrupted file readable so its bad
    bytes surface as malformed lines instead of a fatal ``UnicodeDecodeError``
    (which is a ``ValueError``, not an ``OSError``, and so escapes a narrow
    ``except OSError`` guard).
    """
    root = Path(events_dir)
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*.jsonl")):
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for raw_line in handle:
                    if not raw_line.strip():
                        continue
                    record = parse_hermes_event_line(raw_line)
                    if record is not None:
                        yield record, False
                    else:
                        yield None, True
        except (OSError, UnicodeDecodeError):
            # A single unreadable file must not abort the whole sweep.
            continue


def iter_hermes_events(events_dir: str | Path) -> Iterator[HermesEventRecord]:
    """Yield every parseable event from ``*.jsonl`` under ``events_dir``.

    Thin wrapper over ``_scan_event_lines`` for callers that only want valid
    records. Blank/malformed lines are skipped here; use ``ingest_hermes_events``
    for the batch roll-up that also counts malformed lines honestly. Never
    raises on a missing directory — yields nothing, which is the honest
    posture for a not-yet-populated Hermes.
    """
    for record, _is_malformed in _scan_event_lines(events_dir):
        if record is not None:
            yield record


def group_investigations(
    events: Iterable[HermesEventRecord],
) -> dict[str, HermesInvestigation]:
    """Group events by ``investigation_id`` and order each group chronologically.

    Events with no ``emitted_at`` sort stably after timestamped ones (they keep
    their input order relative to each other). The dict is keyed by
    investigation_id and returned in insertion (first-seen) order.
    """
    buckets: dict[str, list[HermesEventRecord]] = {}
    for event in events:
        buckets.setdefault(event.investigation_id, []).append(event)
    out: dict[str, HermesInvestigation] = {}
    for investigation_id, group in buckets.items():
        ordered = sorted(
            enumerate(group),
            key=lambda pair: (
                pair[1].emitted_at is None,
                pair[1].emitted_at or "",
                pair[0],
            ),
        )
        ordered_events = tuple(record for _, record in ordered)
        timestamps = [e.emitted_at for e in ordered_events if e.emitted_at]
        out[investigation_id] = HermesInvestigation(
            investigation_id=investigation_id,
            events=ordered_events,
            first_emitted_at=timestamps[0] if timestamps else None,
            last_emitted_at=timestamps[-1] if timestamps else None,
        )
    return out


def render_investigation_text(inv: HermesInvestigation) -> str:
    """Render an investigation into a provenance-carrying markdown document.

    The header carries the Hermes investigation_id, event count, and emitted
    range so a human (and the downstream distiller) can see exactly what the
    trace is and where it came from. The body is a chronological event log.
    The output is deterministic: the same investigation always renders to the
    same text, so ``ingest_file``'s content-addressing dedups re-runs.
    """
    header = (
        f"# Hermes research trace — {inv.investigation_id}\n\n"
        f"- events: {len(inv.events)}\n"
        f"- first emitted: {inv.first_emitted_at or 'unknown'}\n"
        f"- last emitted: {inv.last_emitted_at or 'unknown'}\n"
        f"- source: hermes (~/.hermes/research_events)\n"
        f"- ingest version: {HERMES_INGEST_VERSION}\n"
    )
    lines: list[str] = [header, "## Event trace", ""]
    for index, event in enumerate(inv.events, start=1):
        lines.append(f"### {index}. {event.action_type or event.role or 'event'}")
        meta_bits: list[str] = [f"event_id: {event.event_id}"]
        if event.phase:
            meta_bits.append(f"phase: {event.phase}")
        if event.role:
            meta_bits.append(f"role: {event.role}")
        if event.emitted_at:
            meta_bits.append(f"emitted_at: {event.emitted_at}")
        if event.schema_version:
            meta_bits.append(f"schema_version: {event.schema_version}")
        lines.append(" · ".join(meta_bits))
        body = _render_payload(event.payload)
        if body:
            lines.append("")
            lines.append(body)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def ingest_hermes_investigation(
    con: LockedConnection,
    inv: HermesInvestigation,
    *,
    operator_label: str | None = None,
    ip_holder_id: str = "__operator__",
) -> HermesIngestResult:
    """Ingest one Hermes investigation via the live ``ingest_file`` path.

    Idempotent: re-ingesting the same investigation is a content-addressed
    cache hit (``was_new=False`` → ``status='cache_hit'``). Never raises on
    bad input — returns a result with an honest ``status``.
    """
    source_label = f"hermes:{inv.investigation_id}"
    text = render_investigation_text(inv)
    if not text.strip():
        return HermesIngestResult(
            investigation_id=inv.investigation_id,
            document_id=None,
            status="skipped_empty",
            events_count=len(inv.events),
            was_new=False,
            source_label=source_label,
            document_type=None,
        )
    try:
        file_result: FileIngestResult = ingest_file(
            con,
            data=text.encode("utf-8"),
            filename=f"hermes-{inv.investigation_id}.md",
            content_type=_HERMES_MARKDOWN_CONTENT_TYPE,
            investigation_id=inv.investigation_id,
            operator_label=operator_label or source_label,
            ip_holder_id=ip_holder_id,
        )
    except Exception as exc:  # noqa: BLE001 — bridge must not raise out
        return HermesIngestResult(
            investigation_id=inv.investigation_id,
            document_id=None,
            status="error",
            events_count=len(inv.events),
            was_new=False,
            source_label=source_label,
            document_type=None,
            error_message=str(exc),
        )
    return HermesIngestResult(
        investigation_id=inv.investigation_id,
        document_id=file_result.document_id,
        status="ok" if file_result.was_new else "cache_hit",
        events_count=len(inv.events),
        was_new=file_result.was_new,
        source_label=source_label,
        document_type=file_result.document_type,
    )


def ingest_hermes_events(
    con: LockedConnection,
    events_dir: str | Path,
    *,
    limit: int | None = None,
    operator_label: str | None = None,
    ip_holder_id: str = "__operator__",
) -> HermesIngestBatch:
    """Ingest every investigation found under ``events_dir``.

    ``limit`` caps the NUMBER OF INVESTIGATIONS processed (not events).
    Returns a ``HermesIngestBatch`` roll-up. Malformed lines are counted but
    never abort the run. Investigations are processed in stable
    (investigation_id-sorted) order so re-runs are deterministic.
    """
    records: list[HermesEventRecord] = []
    malformed_lines = 0
    for record, is_malformed in _scan_event_lines(events_dir):
        if is_malformed:
            malformed_lines += 1
        elif record is not None:
            records.append(record)
    investigations = group_investigations(records)
    ordered_ids = sorted(investigations)
    if limit is not None and limit >= 0:
        ordered_ids = ordered_ids[:limit]
    results: list[HermesIngestResult] = []
    new_count = cache_hit_count = skipped_count = error_count = 0
    for investigation_id in ordered_ids:
        result = ingest_hermes_investigation(
            con,
            investigations[investigation_id],
            operator_label=operator_label,
            ip_holder_id=ip_holder_id,
        )
        results.append(result)
        if result.status == "ok":
            new_count += 1
        elif result.status == "cache_hit":
            cache_hit_count += 1
        elif result.status == "skipped_empty":
            skipped_count += 1
        elif result.status == "error":
            error_count += 1
    return HermesIngestBatch(
        results=tuple(results),
        new_count=new_count,
        cache_hit_count=cache_hit_count,
        skipped_count=skipped_count,
        error_count=error_count,
        malformed_lines=malformed_lines,
    )


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    return str(value)


def _render_payload(payload: dict[str, Any]) -> str:
    """Render an event payload as a compact, human-readable block.

    Keeps the trace legible for the downstream distiller without dumping
    arbitrarily huge nested structures verbatim.
    """
    if not payload:
        return ""
    try:
        rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        rendered = str(payload)
    return rendered
