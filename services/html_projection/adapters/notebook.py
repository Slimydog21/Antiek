"""Notebook (Tier-2/3) → doc-model adapter (HPRJ SPR-06 M2).

Per the M1 decision (`docs/decisions/spr-06-codec-and-routing-decision.md`): a
notebook's `content.tiptap.json` is already a valid SPR-02 renderer doc-model
(its node types are exactly the renderer's partial set). So this adapter is NOT
a doc-model transform — it is a **rights-aware resolver**.

Unlike the SPR-05 synthesis adapter (which built the doc-model, so the filter
dropped text from the island), a notebook carries **ref_ids** and resolves the
chunk text **live at render time** via `ctx.resolver`. The leak surface is
therefore the resolver output (the rendered HTML), and the rights gate is the
resolver: a non-servable source (`personal_reading` / `restricted_pending_opt_in`
/ NULL per `SERVABLE_CONTENT_CLASSES` — REUSED, not reimplemented) resolves to a
**cite-only payload built from identity only** (title + ip_holder), so the
passage text never reaches the renderer. A deleted/missing ref resolves to a
`Tombstone` (the renderer renders it, exactly as the live surface does).

Rights filtering lives IN this adapter: `adapt_notebook` returns BOTH the
doc-model and the `RenderContext` carrying the rights resolver, so no caller can
render a notebook with unfiltered third-party text by building its own context.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from substrate.constants import SERVABLE_CONTENT_CLASSES

from ..context import RenderContext, ResolvedRef, Tombstone

# The payload keys the renderer partials read as displayable text. For a
# cite-only ref we set every one of these to the notice (and pass through NO
# original payload), so a passage cannot leak via an unexpected key.
_TEXT_KEYS: tuple[str, ...] = (
    "statement",
    "text",
    "body",
    "passage",
    "question",
    "answer",
    "transcript",
    "summary",
)


@dataclass(frozen=True)
class ResolvedRefData:
    """A notebook ref resolved against the live graph: its kind, rights, owner,
    and full payload. The caller (the route / a resolver function) builds these
    from the graph; the adapter applies rights."""

    kind: str
    content_class: str | None
    ip_holder_id: str | None
    title: str | None
    payload: dict = field(default_factory=dict)
    deleted_at: str | None = None  # set => deleted (renders a tombstone)
    # The source document's id (when resolved) — a stable node identity for the
    # knowledge-graph projection (title alone collides across same-named docs).
    source_document_id: str | None = None

    @property
    def servable(self) -> bool:
        # REUSED allowlist — the single rights source of truth.
        return self.content_class in SERVABLE_CONTENT_CLASSES


def _cite_only_notice(d: ResolvedRefData) -> str:
    parts = [d.title or "source"]
    if d.ip_holder_id:
        parts.append(d.ip_holder_id)
    return (
        f"[cite-only — {' · '.join(parts)}; full text withheld under the "
        f"source's rights]"
    )


class RightsAwareResolver:
    """A `RefResolver` that withholds non-servable third-party passage text.

    - servable ref       -> ResolvedRef with the full payload (text included);
    - non-servable ref   -> ResolvedRef with a CITE-ONLY payload built from
                            identity only (no original payload passes through);
    - deleted ref        -> Tombstone(deleted_at set);
    - missing ref        -> Tombstone(deleted_at=None) — "missing, not deleted".
    """

    def __init__(self, refs: dict[str, ResolvedRefData]) -> None:
        self._refs: dict[str, ResolvedRefData] = dict(refs)

    def __call__(self, ref_id: str, block_type: str) -> ResolvedRef | Tombstone:
        data = self._refs.get(ref_id)
        if data is None:
            return Tombstone(
                kind=block_type, deleted_at=None, prior_text=None, ref_id=ref_id
            )
        if data.deleted_at is not None:
            return Tombstone(
                kind=data.kind or block_type,
                deleted_at=data.deleted_at,
                prior_text=None,
                ref_id=ref_id,
            )
        if data.servable:
            return ResolvedRef(kind=data.kind, payload=dict(data.payload))
        # CITE-ONLY: identity-only payload; NEVER pass through data.payload,
        # which may carry the passage in any key.
        notice = _cite_only_notice(data)
        safe: dict = {key: notice for key in _TEXT_KEYS}
        safe["title"] = data.title
        safe["ip_holder_id"] = data.ip_holder_id
        safe["cite_only"] = True
        return ResolvedRef(kind=data.kind, payload=safe)


def adapt_notebook(
    content_tiptap: dict,
    *,
    title: str | None,
    resolved_refs: dict[str, ResolvedRefData],
) -> tuple[dict, RenderContext]:
    """Adapt a notebook to `(doc_model, ctx)`. The notebook's TipTap is already
    a renderer doc-model; the rights filter is the resolver baked into `ctx`, so
    `render(*adapt_notebook(...))` is the only rights-correct path."""
    content = (
        content_tiptap.get("content", [])
        if isinstance(content_tiptap, dict)
        else []
    )
    doc_model = {"content": content, "title": title, "edges": []}
    ctx = RenderContext(resolver=RightsAwareResolver(resolved_refs))
    return doc_model, ctx


__all__ = [
    "ResolvedRefData",
    "RightsAwareResolver",
    "adapt_notebook",
]
