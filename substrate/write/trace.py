"""Trace-to-source target resolution (specs/write/ SPR-07).

From a block or a generated sentence's citation, decide *what the shared
reader should show* — the data-verification path that makes editing
trustworthy. This is the backend decision core; it reuses two existing
contracts and invents no reader of its own:

- ``substrate/write/provenance.resolve_provenance`` (SPR-01) — block →
  node → document → chunks, with dangling + user-originated states.
- ``substrate/books/servability`` (Read SPR-01) — the deny-by-default
  full-text gate over ``documents.content_class`` + ``book_assets.taken_down``.

The mandatory mechanical gate (SPR-07 M4): a block sourced from a **gated
book** resolves to ``servable_snippet`` — metadata/snippet only, NEVER the
gated full text. Write must not become a side door around Read's
servability gate. A brainstorm-originated block traces to its **session**
(labeled, no invented document); a deleted source is **unavailable**,
stated plainly.

This module computes the authoritative target and enforces servability. The
API command records the Write→Read seam before the shared HTML reader opens;
rendering and return navigation remain downstream UI responsibilities.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Literal

try:
    from ..books.servability import is_servable_full_text, servability_of
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.books.servability import (  # type: ignore[no-redef]
        is_servable_full_text,
        servability_of,
    )

from .outline_block import OutlineBlock
from .provenance import resolve_provenance

TraceKind = Literal[
    "source_span",       # open the document at the cited span (full text ok)
    "servable_snippet",  # gated book — metadata/snippet only, NO full text
    "node_only",         # resolved to a node with no linked document
    "session",           # user-originated — show the brainstorm/authoring session
    "unavailable",       # dangling source — stated plainly, no fabrication
]


@dataclass(frozen=True)
class TraceTarget:
    """What the shared reader should open for a traced block. ``full_text_allowed``
    is the load-bearing safety bit: it is True ONLY for genuinely servable
    sources."""

    kind: TraceKind
    full_text_allowed: bool
    document_id: str | None = None
    document_title: str | None = None
    chunk_ids: list[str] = field(default_factory=list)
    servability_status: str | None = None
    detail: str = ""


def resolve_trace_target(con: Any, block: OutlineBlock | str) -> TraceTarget:
    """Resolve the trace target for a block. ``con`` is any duckdb
    connection (read-only is fine)."""
    chain = resolve_provenance(con, block)

    if chain.status == "user_originated":
        return TraceTarget(
            kind="session", full_text_allowed=True,
            detail="user-originated — opens the brainstorm/authoring session, labeled",
        )
    if chain.status == "dangling":
        return TraceTarget(
            kind="unavailable", full_text_allowed=False,
            detail="source unavailable (node deleted or not yet promoted)",
        )
    # status == "resolved"
    if chain.document_id is None:
        return TraceTarget(
            kind="node_only", full_text_allowed=False,
            servability_status=None,
            detail="resolved to a node with no linked source document",
        )

    # The gate: a gated book shows servable content only, never full text.
    content_class, taken_down = _document_gate_state(con, chain.document_id)
    status = servability_of(content_class, taken_down=taken_down)
    full_ok = is_servable_full_text(status)
    return TraceTarget(
        kind="source_span" if full_ok else "servable_snippet",
        full_text_allowed=full_ok,
        document_id=chain.document_id,
        document_title=chain.document_title,
        chunk_ids=list(chain.chunk_ids),
        servability_status=status.value,
        detail=(
            f"servable at span (status {status.value})"
            if full_ok
            else f"gated source (status {status.value}) — snippet/metadata only, no full text"
        ),
    )


def _document_gate_state(con: Any, document_id: str) -> tuple[str | None, bool]:
    """Read the document's content_class and its book-level takedown
    override (if any). A non-book document simply has no book_assets row →
    taken_down False; its content_class still drives the gate."""
    row = con.execute(
        "SELECT content_class FROM documents WHERE document_id = ?",
        [document_id],
    ).fetchone()
    content_class = row[0] if row else None
    taken_down = False
    try:
        td = con.execute(
            "SELECT taken_down FROM book_assets WHERE document_id = ?",
            [document_id],
        ).fetchone()
        if td is not None:
            taken_down = bool(td[0])
    except Exception:
        # book_assets may not exist in an older DB; absence ⇒ not taken down.
        taken_down = False
    return content_class, taken_down
