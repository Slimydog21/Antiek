"""Read-only Hermes research-event ingest bridge (hardened trust boundary).

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

Trust boundary (load-bearing — codex adversarial review of #351):
  1. The Hermes directory is strictly READ-ONLY: never write/create/delete.
  2. ``events_dir`` MUST resolve under an allowed root (default:
     ``~/.hermes/research_events``, plus optional ``ANTIEK_HERMES_EVENTS_DIR``
     and explicit ``allowed_roots`` for hermetic tests). Symlink escape is
     rejected per-file.
  3. Event payloads are rendered with size caps and secret-key redaction so a
     Hermes trace cannot dump credentials into the production corpus.

Malformed input is tolerated and counted honestly rather than raised.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from runtime.db_lock import LockedConnection
from substrate.research_bridge.ingest_file import FileIngestResult, ingest_file

HERMES_INGEST_VERSION: int = 2
DEFAULT_HERMES_EVENTS_DIR: str = os.path.expanduser("~/.hermes/research_events")
_HERMES_MARKDOWN_CONTENT_TYPE: str = "text/markdown"

# Only these keys are required for a line to represent a usable event.
_REQUIRED_EVENT_KEYS: tuple[str, ...] = ("event_id", "investigation_id")

# Payload render budget — keeps corpus text bounded and legible.
_MAX_PAYLOAD_VALUE_CHARS: int = 4_096
_MAX_PAYLOAD_RENDER_CHARS: int = 8_192
_MAX_PAYLOAD_DEPTH: int = 3
_MAX_PAYLOAD_KEYS: int = 64
_MAX_PAYLOAD_LIST_ITEMS: int = 32
# Non-payload JSONL fields also land in corpus text / filenames — cap them.
_MAX_META_FIELD_CHARS: int = 256
_MAX_INVESTIGATION_ID_CHARS: int = 128
_MAX_EVENT_ID_CHARS: int = 128
# Sweep resource budget (hostile/huge Hermes dirs must not unbound memory).
_MAX_LINES_SCANNED: int = 50_000
_MAX_EVENTS_RETAINED: int = 20_000
_MAX_LINE_CHARS: int = 64_000

# Key-name patterns treated as secret-bearing (case-insensitive substring).
_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|secret|"
    r"authorization|auth[_-]?header|bearer|cookie|private[_-]?key|credentials?|"
    r"client[_-]?secret|session[_-]?token)",
    re.IGNORECASE,
)

# Secret-shaped *values* (metadata fields, free-form strings) — not only key names.
_SECRET_VALUE_RE = re.compile(
    r"(?i)("
    r"sk-[A-Za-z0-9_\-]{10,}"  # OpenAI-style / generic secret keys
    r"|Bearer\s+[A-Za-z0-9\-._~+/]+=*"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AIza[0-9A-Za-z\-_]{20,}"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"  # JWT-shaped
    r")"
)

HermesIngestStatus = Literal["ok", "cache_hit", "error", "skipped_empty"]


class HermesEventsDirError(ValueError):
    """Raised when ``events_dir`` escapes the allowed Hermes root(s)."""


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


def default_allowed_roots() -> tuple[Path, ...]:
    """Resolved roots the bridge may read from.

    Always includes the default Hermes events dir. If
    ``ANTIEK_HERMES_EVENTS_DIR`` is set, that path is also allowed (operator
    override for non-default Hermes homes). Roots that do not yet exist are
    still listed (so a first-run empty install is not an error) but resolved
    as absolute expanded paths.
    """
    roots: list[Path] = [Path(DEFAULT_HERMES_EVENTS_DIR).expanduser()]
    env_root = os.environ.get("ANTIEK_HERMES_EVENTS_DIR")
    if env_root:
        roots.append(Path(env_root).expanduser())
    return tuple(_normalize_root(r) for r in roots)


def _normalize_root(root: Path) -> Path:
    """Absolute path for a root; prefer realpath when the path exists."""
    expanded = root.expanduser()
    if expanded.exists():
        return expanded.resolve()
    return expanded.absolute()


def resolve_allowed_events_dir(
    events_dir: str | Path,
    *,
    allowed_roots: Sequence[Path] | None = None,
) -> Path:
    """Resolve ``events_dir`` and enforce the allowed-root trust boundary.

    Raises ``HermesEventsDirError`` if the directory is outside every allowed
    root (after resolving symlinks when the path exists). A missing directory
    is allowed *if* its absolute (non-resolved) path still sits under an
    allowed root — callers then get an empty sweep rather than a hard fail.
    """
    roots = tuple(_normalize_root(Path(r)) for r in (allowed_roots if allowed_roots is not None else default_allowed_roots()))
    if not roots:
        raise HermesEventsDirError("no allowed Hermes events roots configured")
    candidate = Path(events_dir).expanduser()
    # resolve(strict=False) canonicalizes existing parents (macOS /var → /private/var)
    # even when the leaf does not yet exist, so allowed-root membership is honest.
    resolved = candidate.resolve(strict=False)
    for root in roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    raise HermesEventsDirError(
        f"events_dir {resolved!s} is outside allowed Hermes roots: "
        + ", ".join(str(r) for r in roots)
    )


def _is_under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


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
        event_id=_cap_meta(event_id, _MAX_EVENT_ID_CHARS),
        investigation_id=_cap_meta(investigation_id, _MAX_INVESTIGATION_ID_CHARS),
        synthesis_id=_cap_meta_opt(obj.get("synthesis_id")),
        phase=_cap_meta_opt(obj.get("phase")),
        role=_cap_meta_opt(obj.get("role")),
        action_type=_cap_meta_opt(obj.get("action_type")),
        emitted_at=_cap_meta_opt(obj.get("emitted_at")),
        schema_version=schema_version,
        payload=payload,
    )


def _scan_event_lines(
    events_dir: str | Path,
    *,
    allowed_roots: Sequence[Path] | None = None,
) -> Iterator[tuple[HermesEventRecord | None, bool]]:
    """Yield ``(record, is_malformed)`` per non-blank line under ``events_dir``.

    Enforces the allowed-root boundary on the directory and on every file
    discovered via ``rglob`` (rejects symlink escape). An unreadable or
    byte-corrupted file is skipped wholesale without aborting the sweep.
    """
    root = resolve_allowed_events_dir(events_dir, allowed_roots=allowed_roots)
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*.jsonl")):
        # Per-file trust check: a symlink under root pointing outside is rejected.
        if not _is_under_root(path, root):
            continue
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for raw_line in handle:
                    if not raw_line.strip():
                        continue
                    if len(raw_line) > _MAX_LINE_CHARS:
                        yield None, True
                        continue
                    record = parse_hermes_event_line(raw_line)
                    if record is not None:
                        yield record, False
                    else:
                        yield None, True
        except (OSError, UnicodeDecodeError):
            # A single unreadable file must not abort the whole sweep.
            continue


def iter_hermes_events(
    events_dir: str | Path,
    *,
    allowed_roots: Sequence[Path] | None = None,
) -> Iterator[HermesEventRecord]:
    """Yield every parseable event from ``*.jsonl`` under ``events_dir``."""
    for record, _is_malformed in _scan_event_lines(
        events_dir, allowed_roots=allowed_roots
    ):
        if record is not None:
            yield record


def group_investigations(
    events: Iterable[HermesEventRecord],
) -> dict[str, HermesInvestigation]:
    """Group events by ``investigation_id`` and order each group chronologically."""
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

    Deterministic: the same investigation always renders to the same text so
    ``ingest_file``'s content-addressing dedups re-runs. Payloads are rendered
    via :func:`_render_payload` (size-capped + secret-key redacted).
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
            filename=f"hermes-{_safe_filename_id(inv.investigation_id)}.md",
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
    allowed_roots: Sequence[Path] | None = None,
) -> HermesIngestBatch:
    """Ingest every investigation found under ``events_dir``.

    ``events_dir`` must resolve under an allowed Hermes root (see
    :func:`resolve_allowed_events_dir`). ``limit`` caps the NUMBER OF
    INVESTIGATIONS processed (not events). Malformed lines are counted but
    never abort the run.
    """
    # Fail closed on path escape before any file I/O.
    resolve_allowed_events_dir(events_dir, allowed_roots=allowed_roots)

    records: list[HermesEventRecord] = []
    malformed_lines = 0
    for lines_scanned, (record, is_malformed) in enumerate(
        _scan_event_lines(events_dir, allowed_roots=allowed_roots),
        start=1,
    ):
        if lines_scanned > _MAX_LINES_SCANNED:
            break
        if is_malformed:
            malformed_lines += 1
        elif record is not None:
            records.append(record)
            if len(records) >= _MAX_EVENTS_RETAINED:
                break
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


def _safe_filename_id(investigation_id: str) -> str:
    """Filesystem-safe, length-capped investigation id for ingest filenames."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", investigation_id)
    cleaned = cleaned.strip("._-") or "unknown"
    limit = _MAX_INVESTIGATION_ID_CHARS
    if len(cleaned) > limit:
        return cleaned[: max(0, limit - 1)] + "…"
    return cleaned


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    return str(value)


def _cap_meta(value: str, limit: int) -> str:
    """Cap a metadata string; secret-shaped values become redacted."""
    if _looks_like_secret_value(value) or _is_secret_key(value):
        return "[redacted]"
    return _truncate(value, limit)


def _cap_meta_opt(value: Any) -> str | None:
    s = _as_optional_str(value)
    if s is None:
        return None
    return _cap_meta(s, _MAX_META_FIELD_CHARS)


def _is_secret_key(key: str) -> bool:
    return _SECRET_KEY_RE.search(key) is not None


def _looks_like_secret_value(value: str) -> bool:
    """True when a free-form string looks like a credential, not prose."""
    if not value or len(value) < 12:
        return False
    return _SECRET_VALUE_RE.search(value) is not None


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _sanitize_payload_value(
    value: Any,
    *,
    depth: int,
    budget: list[int],
) -> Any:
    """Return a JSON-safe, size-capped, secret-redacted view of ``value``.

    ``budget`` is a one-element list of remaining *nodes* we may visit. When it
    hits zero we stop walking (real resource cap, not just output truncation).
    """
    if budget[0] <= 0:
        return "[truncated:budget]"
    budget[0] -= 1
    if depth > _MAX_PAYLOAD_DEPTH:
        return "[truncated:depth]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if _looks_like_secret_value(value):
            return "[redacted]"
        return _truncate(value, _MAX_PAYLOAD_VALUE_CHARS)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for index, (raw_key, raw_val) in enumerate(value.items()):
            if index >= _MAX_PAYLOAD_KEYS or budget[0] <= 0:
                out["…"] = "[truncated:keys]"
                break
            key = _truncate(str(raw_key), _MAX_META_FIELD_CHARS)
            if _is_secret_key(key):
                out[key] = "[redacted]"
            else:
                out[key] = _sanitize_payload_value(
                    raw_val, depth=depth + 1, budget=budget
                )
        return out
    if isinstance(value, (list, tuple)):
        items: list[Any] = []
        for index, item in enumerate(value):
            if index >= _MAX_PAYLOAD_LIST_ITEMS or budget[0] <= 0:
                items.append("[truncated:list]")
                break
            items.append(
                _sanitize_payload_value(item, depth=depth + 1, budget=budget)
            )
        return items
    return _truncate(str(value), _MAX_PAYLOAD_VALUE_CHARS)


def _render_payload(payload: dict[str, Any]) -> str:
    """Render an event payload as a compact, redacted, human-readable block."""
    if not payload:
        return ""
    # Node budget ≈ keys*depth headroom; stops hostile mega-objects early.
    budget = [512]
    sanitized = _sanitize_payload_value(payload, depth=0, budget=budget)
    try:
        rendered = json.dumps(
            sanitized, ensure_ascii=False, sort_keys=True, default=str
        )
    except (TypeError, ValueError):
        rendered = _truncate(str(sanitized), _MAX_PAYLOAD_RENDER_CHARS)
    return _truncate(rendered, _MAX_PAYLOAD_RENDER_CHARS)
