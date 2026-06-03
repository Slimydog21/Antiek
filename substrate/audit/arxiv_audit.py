"""Append-only arXiv fetch→serve→accrue→takedown audit (SPR-09 M4).

A dedicated, append-only DuckDB audit table keyed by ``arxiv_id`` that
reconstructs a single paper's full compliance lifecycle. A ToS-compliance query
("show me everything that happened to arxiv:2401.00001") is answered from ONE
``trace(con, arxiv_id)`` call: when we FETCHED its PDF, when we SERVED its body
(and whether the serve was allowed or gated, and why), when ad revenue ACCRUED
against it, and when it was TAKEN DOWN.

Shape decision — dedicated table, not the typed event log
---------------------------------------------------------
Per ``attribution_audit.py``'s own decision rule: use the typed event log when a
record is INVESTIGATION-scoped; use a dedicated table when it is keyed by a
DOMAIN id and needs replay/queries. A paper's fetch/serve/accrue/takedown trace
is keyed by ``arxiv_id`` and is corpus-wide (NOT investigation-scoped), so it
maps cleanly onto a dedicated table — mirroring ``attribution_audit`` /
``decisions_log`` (defensive module-local ``ensure_tables``, deterministic
sha256 row id for append-only idempotency, ``connect_write`` single-writer, a
``record_event`` writer, and a ``trace`` query). The canonical DDL also lives in
``substrate/graph/schema.py`` (V12).

§9.0 — NO WITHHELD BODY IN ANY AUDIT ROW
----------------------------------------
This is a HARD invariant. An audit row stores ONLY references and counters:
``arxiv_id`` / ``document_id`` / the event ``kind`` / a ``reason`` / a ``tier``
/ an integer ``amount_cents`` / a small JSON ``detail`` of NON-body refs. It
NEVER stores ``raw_text``, a snippet, served body text, or any paper content.
This follows the ``source.read`` event shape (document_id + refs + dwell
evidence, no body). The writer enforces this defensively: ``detail`` is
canonical-JSON of caller-supplied refs and the writer RECURSIVELY rejects any
``detail`` key that smells like a body (``raw_text`` / ``snippet`` / ``body`` /
``full_text`` / ``text`` / ``content``) — at the top level, nested in sub-dicts,
or inside lists — so a careless caller cannot leak content into the audit trail,
even buried under a nested key (round-2: the prior top-level-only scan let a
nested body bypass).

Event kinds — namespaced STRING constants, NOT typed event payloads
-------------------------------------------------------------------
``kind`` is one of the namespaced strings in :data:`ARXIV_AUDIT_KINDS`
(``arxiv.fetch`` / ``arxiv.serve`` / ``arxiv.accrue`` / ``arxiv.takedown``).
These are PLAIN STRINGS stored in a CHECK-constrained column — they are NOT new
``substrate/schemas/events.py`` typed payloads. This is deliberate (the binding
M4 decision): adding a typed payload would bump ``EVENT_SCHEMA_VERSION`` and trip
the codegen-staleness CI gate (it regenerates ``types.ts`` from the registries).
A dedicated audit TABLE with string kinds touches no codegen surface, so the
staleness gate stays green with zero schema bump.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# Namespaced string kinds (NOT ActionType / typed payloads — see module docstring).
ARXIV_FETCH = "arxiv.fetch"
ARXIV_SERVE = "arxiv.serve"
ARXIV_ACCRUE = "arxiv.accrue"
ARXIV_TAKEDOWN = "arxiv.takedown"

ARXIV_AUDIT_KINDS: frozenset[str] = frozenset(
    {ARXIV_FETCH, ARXIV_SERVE, ARXIV_ACCRUE, ARXIV_TAKEDOWN}
)

# Ordering for the reconstructed lifecycle so a ``trace`` reads fetch → serve →
# accrue → takedown within the same instant (the timestamp orders across
# instants; this orders ties deterministically).
_KIND_ORDER: dict[str, int] = {
    ARXIV_FETCH: 0,
    ARXIV_SERVE: 1,
    ARXIV_ACCRUE: 2,
    ARXIV_TAKEDOWN: 3,
}

# §9.0 tripwire: keys that smell like a paper body. ``detail`` must never carry
# one — the audit trail records refs + counts, never content.
_FORBIDDEN_DETAIL_KEYS: frozenset[str] = frozenset(
    {"raw_text", "snippet", "body", "full_text", "text", "content"}
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace drift, so a re-record of the
    same event yields a stable id (append-only idempotency)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _event_id(
    *, arxiv_id: str, kind: str, document_id: str, reason: str | None, detail_json: str
) -> str:
    """Deterministic sha256 id from (arxiv_id, kind, document_id, reason, detail).

    ``reason`` is part of an event's IDENTITY: two events that differ only by
    reason are DISTINCT compliance events, so they must get distinct ids (round-2
    fix — previously ``reason`` was excluded, so a re-takedown of the same paper
    under a DIFFERENT reason collapsed onto the first row and the new reason was
    silently lost). A truly identical re-record (same reason + detail) still
    collapses to one row (idempotent, append-only); a changed reason, ref, or
    count produces a distinct row — never an in-place mutation. ``None`` reason is
    distinct from an empty-string reason via the sentinel below."""
    reason_token = "\x01NONE\x01" if reason is None else reason
    h = hashlib.sha256(
        f"{arxiv_id}\x00{kind}\x00{document_id}\x00{reason_token}\x00{detail_json}".encode()
    ).hexdigest()[:24]
    return f"arxiv-audit-{h}"


@dataclass(frozen=True)
class ArxivAuditEvent:
    """One persisted audit row. Body-free by construction (§9.0): ``detail`` is a
    JSON dict of NON-body refs/counters only."""

    event_id: str
    arxiv_id: str
    document_id: str
    kind: str
    reason: str | None
    tier: str | None
    amount_cents: int | None
    detail: dict[str, Any]
    recorded_at: str


def ensure_tables(con: Any) -> None:
    """Defensive table create (module-local). Canonical schema in
    ``substrate/graph/schema.py`` V12 chunk."""
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS arxiv_audit (
                event_id      TEXT PRIMARY KEY,
                arxiv_id      TEXT NOT NULL,
                document_id   TEXT NOT NULL,
                kind          TEXT NOT NULL CHECK (kind IN (
                    'arxiv.fetch', 'arxiv.serve', 'arxiv.accrue', 'arxiv.takedown'
                )),
                reason        TEXT,
                tier          TEXT,
                amount_cents  INTEGER,
                detail_json   TEXT NOT NULL DEFAULT '{}',
                recorded_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_arxiv_audit_arxiv "
            "ON arxiv_audit(arxiv_id)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_arxiv_audit_document "
            "ON arxiv_audit(document_id)"
        )
    except Exception:
        pass


def _find_body_keys(obj: Any) -> set[str]:
    """RECURSIVELY collect any body-shaped key anywhere in ``obj`` — at the top
    level, nested inside dicts, AND inside lists/tuples of dicts. A body hidden
    under ``detail={"meta": {"raw_text": ...}}`` or
    ``detail={"items": [{"body": ...}]}`` must be found, not just a top-level key
    (round-2: the prior top-level-only scan let a nested body bypass §9.0)."""
    bad: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in _FORBIDDEN_DETAIL_KEYS:
                bad.add(k)
            bad |= _find_body_keys(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            bad |= _find_body_keys(item)
    return bad


def _reject_body_in_detail(detail: dict[str, Any]) -> None:
    """§9.0 enforcement: refuse any ``detail`` carrying a body-shaped key ANYWHERE
    in its nested structure (dicts AND lists). The audit trail records refs +
    counts, never paper content — a careless caller must NOT be able to leak a
    body into it, even buried under a nested key."""
    bad = _find_body_keys(detail)
    if bad:
        raise ValueError(
            f"arxiv_audit detail must not carry body content (§9.0); offending "
            f"keys (any nesting depth): {sorted(bad)}. The audit trail stores "
            "document_id/arxiv_id/refs/counts only — never raw_text/snippet/body."
        )


def record_event(
    con: Any,
    *,
    arxiv_id: str,
    document_id: str,
    kind: str,
    reason: str | None = None,
    tier: str | None = None,
    amount_cents: int | None = None,
    detail: dict[str, Any] | None = None,
) -> str:
    """Append one audit event and return its ``event_id``.

    Append-only + idempotent (matching ``decisions_log.persist_decision`` /
    ``attribution_audit.record_attribution``): the ``event_id`` is a deterministic
    sha256 of (arxiv_id, kind, document_id, reason, detail), so re-recording an
    identical event is a no-op returning the existing id, and a prior row is NEVER
    mutated. ``reason`` is part of the identity, so a re-takedown under a DIFFERENT
    reason is a DISTINCT event (its reason is not lost), while a true identical
    re-run stays idempotent.

    §9.0: ``detail`` may carry only NON-body refs/counters; a body-shaped key is
    rejected.
    """
    if kind not in ARXIV_AUDIT_KINDS:
        raise ValueError(
            f"unknown arxiv_audit kind {kind!r}; expected one of "
            f"{sorted(ARXIV_AUDIT_KINDS)}"
        )
    detail = dict(detail or {})
    _reject_body_in_detail(detail)
    ensure_tables(con)
    detail_json = _canonical_json(detail)
    event_id = _event_id(
        arxiv_id=arxiv_id,
        kind=kind,
        document_id=document_id,
        reason=reason,
        detail_json=detail_json,
    )
    existing = con.execute(
        "SELECT event_id FROM arxiv_audit WHERE event_id = ?",
        [event_id],
    ).fetchone()
    if existing is not None:
        return event_id
    con.execute(
        """
        INSERT INTO arxiv_audit (
            event_id, arxiv_id, document_id, kind, reason, tier,
            amount_cents, detail_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            event_id, arxiv_id, document_id, kind, reason, tier,
            amount_cents, detail_json,
        ],
    )
    return event_id


def _row_to_event(r: tuple) -> ArxivAuditEvent:
    return ArxivAuditEvent(
        event_id=r[0],
        arxiv_id=r[1],
        document_id=r[2],
        kind=r[3],
        reason=r[4],
        tier=r[5],
        amount_cents=int(r[6]) if r[6] is not None else None,
        detail=json.loads(r[7]) if r[7] else {},
        recorded_at=r[8] or "",
    )


def trace(con: Any, arxiv_id: str) -> list[ArxivAuditEvent]:
    """Reconstruct one paper's full fetch→serve→accrue→takedown history, ordered
    by time then by lifecycle stage (so legs recorded in the same instant read in
    fetch→serve→accrue→takedown order). The single ToS-compliance query."""
    ensure_tables(con)
    rows = con.execute(
        """
        SELECT event_id, arxiv_id, document_id, kind, reason, tier,
               amount_cents, detail_json,
               strftime(recorded_at, '%Y-%m-%dT%H:%M:%S')
        FROM arxiv_audit
        WHERE arxiv_id = ?
        ORDER BY recorded_at, event_id
        """,
        [arxiv_id],
    ).fetchall()
    events = [_row_to_event(r) for r in rows]
    # Stable secondary sort by lifecycle stage for same-instant ties; the SQL
    # ORDER BY already sorts across instants.
    events.sort(key=lambda e: (e.recorded_at, _KIND_ORDER.get(e.kind, 99)))
    return events


__all__ = [
    "ARXIV_ACCRUE",
    "ARXIV_AUDIT_KINDS",
    "ARXIV_FETCH",
    "ARXIV_SERVE",
    "ARXIV_TAKEDOWN",
    "ArxivAuditEvent",
    "ensure_tables",
    "record_event",
    "trace",
]
