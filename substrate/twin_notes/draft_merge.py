"""Draft-merge: provisional combined HTML before final parent merge.

Operator vision (reading/research): after sub-agent researches complete, create
a *draft* combined document from the parent HTML + twin insights/questions,
review it, then optionally finalize later. This module never mutates the
parent asset store — it only builds a provisional artifact.

Vs siblings:
* ``compose_analysis_html`` — twins-only analysis article (no parent body)
* ``build_collective_pack`` — plain-text multi-twin prompt pack
* ``draft_merge`` — parent HTML + twins → provisional combined HTML draft

Rules:
* Same-parent twins only (cross-parent → TwinParentMismatch)
* Parent body and twin text HTML-escaped (no raw script)
* Output carries ``provisional=True`` and a draft id
"""

from __future__ import annotations

import hashlib
import html
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from substrate.twin_notes.store import TwinDocument, TwinNotesError, TwinParentMismatch


@dataclass(frozen=True)
class DraftMergeResult:
    draft_id: str
    parent_asset_id: str
    provisional: bool
    html: str
    twin_ids: list[str]
    insight_count: int
    question_count: int
    created_at: float
    notes: list[str] = field(default_factory=list)


def _escape(text: str) -> str:
    return html.escape(text or "", quote=True)


def _uniq(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        t = str(raw).strip()
        if not t:
            continue
        key = " ".join(t.split()).casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def build_draft_merge(
    *,
    parent_asset_id: str,
    parent_html: str,
    twins: Sequence[TwinDocument],
    title: str = "Draft merge",
    now: float | None = None,
) -> DraftMergeResult:
    """Build a provisional combined HTML draft.

    ``parent_html`` is treated as untrusted source text and is escaped into a
    ``<pre>``/article body so hostile script cannot execute in the draft.
    (Final merge paths that accept pre-sanitized HTML remain a separate residual.)
    """
    parent = (parent_asset_id or "").strip()
    if not parent:
        raise TwinNotesError("parent_asset_id must be non-empty")

    docs = list(twins)
    if not docs:
        raise TwinNotesError("draft merge requires at least one twin")

    parents = {d.parent_asset_id for d in docs}
    if parents != {parent}:
        raise TwinParentMismatch(
            "draft merge requires all twins to share parent_asset_id="
            + repr(parent)
            + "; got "
            + ", ".join(sorted(parents))
        )

    insights = _uniq(i for d in docs for i in d.insights)
    questions = _uniq(q for d in docs for q in d.questions)
    twin_ids = [d.twin_id for d in docs]
    ts = float(now if now is not None else time.time())
    title_clean = (title or "Draft merge").strip() or "Draft merge"

    basis = "|".join([parent, title_clean, *sorted(twin_ids), str(int(ts))])
    draft_id = "draft-" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]

    parts: list[str] = [
        '<article class="antiek-draft-merge" data-provisional="true" data-draft-id="'
        + _escape(draft_id)
        + '" data-parent="'
        + _escape(parent)
        + '">',
        f"<h1>{_escape(title_clean)}</h1>",
        '<p class="badge provisional"><strong>PROVISIONAL DRAFT</strong> — not merged into parent</p>',
        f'<p class="meta">parent={_escape(parent)} twins={len(twin_ids)}</p>',
        "<section><h2>Parent asset (escaped snapshot)</h2>",
        f"<pre class=\"parent-body\">{_escape(parent_html)}</pre>",
        "</section>",
        "<section><h2>Twin insights</h2>",
    ]
    if insights:
        parts.append("<ul>")
        for i in insights:
            parts.append(f"<li>{_escape(i)}</li>")
        parts.append("</ul>")
    else:
        parts.append("<p><em>No insights.</em></p>")
    parts.append("</section>")
    parts.append("<section><h2>Twin questions</h2>")
    if questions:
        parts.append("<ul>")
        for q in questions:
            parts.append(f"<li>{_escape(q)}</li>")
        parts.append("</ul>")
    else:
        parts.append("<p><em>No questions.</em></p>")
    parts.append("</section>")
    parts.append("</article>")

    notes = [
        "provisional=true — parent asset not mutated",
        "parent HTML escaped into draft (hostile script cannot execute)",
        "finalize/merge into parent is a separate product residual (rrv-712 / engagement)",
    ]

    return DraftMergeResult(
        draft_id=draft_id,
        parent_asset_id=parent,
        provisional=True,
        html="\n".join(parts) + "\n",
        twin_ids=twin_ids,
        insight_count=len(insights),
        question_count=len(questions),
        created_at=ts,
        notes=notes,
    )


__all__ = ["DraftMergeResult", "build_draft_merge"]
