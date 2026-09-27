"""Pin resolution + the re-resolution ladder for anchored highlights
(anchor-first SPR-01).

RESOLUTION (pin time): the client sends quote/prefix/suffix (+ an optional
page hint); the SERVER locates the unique (chunk_id, start, end) against its
own chunk store under the cross-runtime ``unicode-nfc-v1`` normalization
(substrate/feedback/domain.py — IMPORTED, never forked). An ambiguous or
unlocatable match is an honest refusal, never a guess. The stored anchor's
prefix/suffix are rebuilt from the chunk's canonical 32-scalar windows, so
``validate_node_text_anchor`` passes by construction — the same contract the
agent-work leases validate against (domain.py:42-71).

RE-RESOLUTION (the four-step ladder, per anchor, in order):
  1. exact   — node_id present AND node_text_sha256 matches → active
  2. migrate — the SAME text hash lives in a DIFFERENT chunk (a re-chunk
               reminted ids) → active, node_id rewritten, migration event
  3. fuzzy   — quote+prefix+suffix locate a unique span → drifted (offsets +
               the new location's context rewritten, quote kept, visible)
  4. none    → orphaned (row kept, listed, never deleted)

Rights at rest, at resolution time: quote/prefix/suffix are persisted ONLY
when is_servable_full_text(servability_of(content_class)) holds for the
document — the server decides from its own rights rows; the client's flag is
never authoritative. Metadata-only anchors (non-servable at pin) get steps 1
and 4 ONLY, exactly per the spec: without a stored quote there is no fuzzy
path (steps 2-3 require the servable text columns). Every status/location
transition emits a metadata-only audit event via substrate/event_log.log_event
— ids, hashes, offsets, statuses; NEVER quote text.

The write-lock discipline (the arXiv lesson): every pass runs inside the
CALLER's LockedConnection scope (the source-merge post-commit hook passes its
own); this module opens no connection of its own.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from runtime.db_lock import LockedConnection
from substrate.books.highlights.schema import SqlExecutor, init_highlights_schema
from substrate.books.highlights.store import (
    AnchorRow,
    HighlightsStore,
    HighlightStatus,
)
from substrate.books.page_anchor import page_index_from_section_path
from substrate.books.servability import is_servable_full_text, servability_of
from substrate.event_log import log_event
from substrate.feedback.domain import (
    NodeTextAnchor,
    normalize_node_text,
    validate_node_text_anchor,
)

# The audit action types (free-form, the source_merge.committed convention).
ANCHOR_MIGRATED = "anchor.migrated"
ANCHOR_DRIFTED = "anchor.drifted"
ANCHOR_ORPHANED = "anchor.orphaned"
ANCHOR_RESTORED = "anchor.restored"

_AUDIT_ROLE = "books/highlights"
_AUDIT_POLICY = "books/highlights/reanchor"


class PinResolutionError(ValueError):
    """An honest refusal: the passage could not be uniquely located.

    ``reason`` is the operator-facing vocabulary — "not_found" (the passage
    is not in the served chunks) or "ambiguous" (the context matches more
    than one span; never resolved by guessing)."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class PinResolution:
    """Where a pin landed, resolved server-side."""

    anchor: NodeTextAnchor
    page_index_hint: int | None


@dataclass(frozen=True, slots=True)
class ReanchorReport:
    """What one re-resolution pass did (counts are post-pass row statuses)."""

    document_id: str
    evaluated: int
    active: int
    migrated: int
    drifted: int
    orphaned: int
    event_ids: tuple[str | None, ...]


@dataclass(frozen=True, slots=True)
class _Chunk:
    chunk_id: str
    section_path: str | None
    normalized_text: str
    text_sha256: str


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_chunks(con: LockedConnection, document_id: str) -> list[_Chunk]:
    rows = con.execute(
        "SELECT chunk_id, section_path, text FROM chunks WHERE document_id = ? "
        "ORDER BY chunk_index",
        [document_id],
    ).fetchall()
    out: list[_Chunk] = []
    for row in rows:
        normalized = normalize_node_text(str(row[2]))
        out.append(
            _Chunk(
                chunk_id=str(row[0]),
                section_path=None if row[1] is None else str(row[1]),
                normalized_text=normalized,
                text_sha256=_sha256(normalized),
            )
        )
    return out


def _locate(
    chunks: list[_Chunk], *, quote: str, prefix: str, suffix: str
) -> list[tuple[_Chunk, int, int]]:
    """Every (chunk, start, end) whose quote occurrence is flanked by the
    given context. Prefix matches the window ENDING at the quote start;
    suffix matches the window STARTING at the quote end — a shorter client
    context still locates (it is the client's job to send enough context;
    under-contextualized pins simply risk the honest "ambiguous" refusal)."""
    nq = normalize_node_text(quote)
    np_ = normalize_node_text(prefix)
    ns = normalize_node_text(suffix)
    if not nq:
        return []
    found: list[tuple[_Chunk, int, int]] = []
    for chunk in chunks:
        text = chunk.normalized_text
        start = 0
        while True:
            i = text.find(nq, start)
            if i < 0:
                break
            end = i + len(nq)
            if text[max(0, i - len(np_)) : i] == np_ and text[end : end + len(ns)] == ns:
                found.append((chunk, i, end))
            start = i + 1
    return found


def _locate_fuzzy(
    chunks: list[_Chunk], *, quote: str, prefix: str, suffix: str
) -> list[tuple[_Chunk, int, int]]:
    """The drift-tolerant re-anchor (ladder step 3). Drift means the text
    AROUND the passage changed — requiring all three of quote+prefix+suffix
    to match would orphan every insertion before a passage, which is exactly
    what the drifted status exists to survive. So context DISAMBIGUATES
    rather than gates, in confidence order, first unique level wins:
      1. quote with BOTH context windows matching;
      2. quote with EITHER window matching;
      3. the quote alone — only when it occurs exactly once in the document
         (a unique occurrence is an unambiguous location, never a guess).
    Zero or still-multiple candidates at every level → no location (the
    anchor goes orphaned; it is never re-pointed ambiguously)."""
    nq = normalize_node_text(quote)
    np_ = normalize_node_text(prefix)
    ns = normalize_node_text(suffix)
    if not nq:
        return []
    both: list[tuple[_Chunk, int, int]] = []
    either: list[tuple[_Chunk, int, int]] = []
    bare: list[tuple[_Chunk, int, int]] = []
    for chunk in chunks:
        text = chunk.normalized_text
        start = 0
        while True:
            i = text.find(nq, start)
            if i < 0:
                break
            end = i + len(nq)
            prefix_ok = text[max(0, i - len(np_)) : i] == np_
            suffix_ok = text[end : end + len(ns)] == ns
            if prefix_ok and suffix_ok:
                both.append((chunk, i, end))
            elif prefix_ok or suffix_ok:
                either.append((chunk, i, end))
            else:
                bare.append((chunk, i, end))
            start = i + 1
    for level in (both, either, bare):
        if len(level) == 1:
            return level
    return []


def _context_windows(text: str, start: int, end: int) -> tuple[str, str, str]:
    """The canonical (quote, prefix, suffix) for a span — the 32-scalar
    windows validate_node_text_anchor expects (domain.py:64-65)."""
    quote = text[start:end]
    prefix = text[max(0, start - 32) : start]
    suffix = text[end : min(len(text), end + 32)]
    return quote, prefix, suffix


def resolve_pin(
    con: LockedConnection,
    *,
    document_id: str,
    quote: str,
    prefix: str,
    suffix: str,
    page_index_hint: int | None = None,
) -> PinResolution:
    """Locate the unique (chunk_id, start, end) for a pin. Refuses honestly
    (PinResolutionError) when the passage is absent or ambiguous."""
    chunks = _load_chunks(con, document_id)
    candidates = _locate(chunks, quote=quote, prefix=prefix, suffix=suffix)
    if not candidates:
        raise PinResolutionError("not_found", "the passage could not be located in this document")
    if len(candidates) > 1:
        raise PinResolutionError(
            "ambiguous",
            f"the passage matches {len(candidates)} spans — send more context",
        )
    chunk, start, end = candidates[0]
    canonical_quote, canonical_prefix, canonical_suffix = _context_windows(
        chunk.normalized_text, start, end
    )
    anchor = NodeTextAnchor(
        node_id=chunk.chunk_id,
        node_text_sha256=chunk.text_sha256,
        start_scalar=start,
        end_scalar=end,
        quote=canonical_quote,
        prefix=canonical_prefix,
        suffix=canonical_suffix,
    )
    # The lease contract, enforced on what we are about to persist.
    validate_node_text_anchor(chunk.normalized_text, anchor)
    hint = page_index_hint
    if hint is None:
        hint = page_index_from_section_path(chunk.section_path)
    return PinResolution(anchor=anchor, page_index_hint=hint)


def document_servable(con: SqlExecutor, document_id: str) -> bool:
    """Rights truth from the server's own rows — never the client's say-so.
    Read-only: any connection that can execute a SELECT (write side and read
    side alike, the SqlExecutor protocol) satisfies it."""
    row = con.execute(
        "SELECT content_class FROM documents WHERE document_id = ? LIMIT 1",
        [document_id],
    ).fetchone()
    if row is None:
        return False
    content_class = None if row[0] is None else str(row[0])
    return is_servable_full_text(servability_of(content_class))


def _audit(
    *,
    document_id: str,
    action_type: str,
    payload: dict[str, Any],
    events_dir: str | None,
) -> str | None:
    """A metadata-only audit event on the document's reading thread (the
    read-<documentId> convention the source-merge events already use). The
    payload carries ids, hashes, offsets, statuses — NEVER quote text."""
    return log_event(
        f"read-{document_id}",
        action_type,
        payload=payload,
        role=_AUDIT_ROLE,
        policy_id=_AUDIT_POLICY,
        document_id=document_id,
        events_dir=events_dir,
    )


def _reanchor_one(
    row: AnchorRow,
    chunks: list[_Chunk],
    *,
    events_dir: str | None,
    store: HighlightsStore,
    con: LockedConnection,
) -> tuple[HighlightStatus, str | None, str | None]:
    """Evaluate one anchor down the ladder. Returns (new_status, transition,
    event_id). Metadata-only anchors (servable_at_pin=False) get steps 1 and
    4 ONLY, exactly per the spec: without a stored quote there is no fuzzy
    path (steps 2-3 need the servable text columns)."""
    anchor = row.anchor
    by_id = {c.chunk_id: c for c in chunks}
    current = by_id.get(anchor.node_id)

    # Step 1 — exact: same chunk, same text hash.
    if current is not None and current.text_sha256 == anchor.node_text_sha256:
        transition = None
        if row.status is not HighlightStatus.ACTIVE:
            store.update_status(con, row.anchor_id, HighlightStatus.ACTIVE)
            transition = ANCHOR_RESTORED
            event_id = _audit(
                document_id=row.document_id,
                action_type=ANCHOR_RESTORED,
                payload={
                    "anchor_id": row.anchor_id,
                    "from_status": str(row.status),
                    "to_status": str(HighlightStatus.ACTIVE),
                    "node_id": anchor.node_id,
                    "node_text_sha256": anchor.node_text_sha256,
                },
                events_dir=events_dir,
            )
            return HighlightStatus.ACTIVE, transition, event_id
        return HighlightStatus.ACTIVE, None, None

    if row.servable_at_pin:
        # Step 2 — migrate: the SAME text hash lives in exactly one OTHER
        # chunk (a re-chunk reminted ids; the hash is the identity).
        hash_matches = [
            c
            for c in chunks
            if c.text_sha256 == anchor.node_text_sha256 and c.chunk_id != anchor.node_id
        ]
        if len(hash_matches) == 1:
            target = hash_matches[0]
            store.update_after_reanchor(
                con,
                row.anchor_id,
                node_id=target.chunk_id,
                node_text_sha256=target.text_sha256,
                start_scalar=anchor.start_scalar,
                end_scalar=anchor.end_scalar,
                status=HighlightStatus.ACTIVE,
                quote=anchor.quote,
                prefix=anchor.prefix,
                suffix=anchor.suffix,
            )
            event_id = _audit(
                document_id=row.document_id,
                action_type=ANCHOR_MIGRATED,
                payload={
                    "anchor_id": row.anchor_id,
                    "from_status": str(row.status),
                    "to_status": str(HighlightStatus.ACTIVE),
                    "from_node_id": anchor.node_id,
                    "node_id": target.chunk_id,
                    "node_text_sha256": target.text_sha256,
                },
                events_dir=events_dir,
            )
            return HighlightStatus.ACTIVE, ANCHOR_MIGRATED, event_id

        # Step 3 — fuzzy: quote+prefix+suffix locate a unique span → drifted.
        found = _locate_fuzzy(
            chunks, quote=anchor.quote, prefix=anchor.prefix, suffix=anchor.suffix
        )
        if len(found) == 1:
            chunk, start, end = found[0]
            quote, prefix, suffix = _context_windows(chunk.normalized_text, start, end)
            store.update_after_reanchor(
                con,
                row.anchor_id,
                node_id=chunk.chunk_id,
                node_text_sha256=chunk.text_sha256,
                start_scalar=start,
                end_scalar=end,
                status=HighlightStatus.DRIFTED,
                quote=quote,
                prefix=prefix,
                suffix=suffix,
            )
            event_id = _audit(
                document_id=row.document_id,
                action_type=ANCHOR_DRIFTED,
                payload={
                    "anchor_id": row.anchor_id,
                    "from_status": str(row.status),
                    "to_status": str(HighlightStatus.DRIFTED),
                    "node_id": chunk.chunk_id,
                    "node_text_sha256": chunk.text_sha256,
                    "start_scalar": start,
                    "end_scalar": end,
                },
                events_dir=events_dir,
            )
            return HighlightStatus.DRIFTED, ANCHOR_DRIFTED, event_id

    # Step 4 — none of the above: orphaned (kept, listed, never deleted).
    if row.status is not HighlightStatus.ORPHANED:
        store.update_status(con, row.anchor_id, HighlightStatus.ORPHANED)
        event_id = _audit(
            document_id=row.document_id,
            action_type=ANCHOR_ORPHANED,
            payload={
                "anchor_id": row.anchor_id,
                "from_status": str(row.status),
                "to_status": str(HighlightStatus.ORPHANED),
                "last_node_id": anchor.node_id,
            },
            events_dir=events_dir,
        )
        return HighlightStatus.ORPHANED, ANCHOR_ORPHANED, event_id
    return HighlightStatus.ORPHANED, None, None


def reanchor_document(
    con: LockedConnection,
    *,
    document_id: str,
    events_dir: str | None = None,
) -> ReanchorReport:
    """The re-resolution pass for one document. Runs INSIDE the caller's
    write-lock scope (the source-merge post-commit hook passes its own); it
    opens no connection of its own."""
    init_highlights_schema(con)
    store = HighlightsStore()
    rows = store.list_for_document(con, document_id)
    chunks = _load_chunks(con, document_id)
    counts: dict[HighlightStatus, int] = {
        HighlightStatus.ACTIVE: 0,
        HighlightStatus.DRIFTED: 0,
        HighlightStatus.ORPHANED: 0,
    }
    transitioned: dict[str, int] = {"migrated": 0, "drifted": 0, "orphaned": 0}
    event_ids: list[str | None] = []
    for row in rows:
        new_status, transition, event_id = _reanchor_one(
            row, chunks, events_dir=events_dir, store=store, con=con
        )
        counts[new_status] += 1
        if transition is not None:
            event_ids.append(event_id)
            if transition == ANCHOR_MIGRATED:
                transitioned["migrated"] += 1
            elif transition == ANCHOR_DRIFTED:
                transitioned["drifted"] += 1
            elif transition == ANCHOR_ORPHANED:
                transitioned["orphaned"] += 1
    return ReanchorReport(
        document_id=document_id,
        evaluated=len(rows),
        active=counts[HighlightStatus.ACTIVE],
        migrated=transitioned["migrated"],
        drifted=counts[HighlightStatus.DRIFTED],
        orphaned=counts[HighlightStatus.ORPHANED],
        event_ids=tuple(event_ids),
    )
