"""Recursive note twin — insights + open questions as a first-class twin.

Every human-viewable information asset on Antiek is intended to carry a
*twin document*: the LLM note-taker substrate of insights and open questions
derived from that asset. Twins are mergeable, referenceable, and the seed
for intelligent search / combined contexts.

This module is pure structure. Production LLM extraction lives in
``substrate.research_bridge.extractor`` and ``roles.note_taker``; those
emit items that *feed* ``build_note_twin``. No network, no DuckDB.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

TwinKind = Literal["insight", "open_question"]

_TWIN_ID_PREFIX = "twin"
_MAX_ITEMS_PER_KIND = 200


class TwinItemError(ValueError):
    """Raised when a twin item violates structural invariants."""


@dataclass(frozen=True)
class TwinItem:
    """One insight or open question on a twin document.

    ``text`` is required and non-empty after strip. ``confidence`` is in
    ``[0.0, 1.0]`` when known; ``None`` means unknown (not zero).
    ``source_quote`` is optional provenance from the parent asset.
    ``item_id`` is content-addressed from kind+text so re-builds of the
    same item are stable across twin rebuilds.
    """

    kind: TwinKind
    text: str
    confidence: float | None = None
    source_quote: str | None = None
    item_id: str = ""

    def __post_init__(self) -> None:
        if self.kind not in ("insight", "open_question"):
            raise TwinItemError(
                f"unknown twin kind {self.kind!r}; allowed: insight, open_question"
            )
        cleaned = self.text.strip()
        if not cleaned:
            raise TwinItemError("TwinItem.text must be non-empty after strip")
        object.__setattr__(self, "text", cleaned)
        if self.confidence is not None:
            c = float(self.confidence)
            if c < 0.0 or c > 1.0:
                raise TwinItemError(
                    f"TwinItem.confidence must be in [0,1], got {c}"
                )
            object.__setattr__(self, "confidence", c)
        if self.source_quote is not None:
            q = self.source_quote.strip()
            object.__setattr__(self, "source_quote", q or None)
        if not self.item_id:
            digest = hashlib.sha256(
                f"{self.kind}\0{self.text}".encode()
            ).hexdigest()[:16]
            object.__setattr__(self, "item_id", f"{self.kind[:3]}-{digest}")


@dataclass(frozen=True)
class NoteTwin:
    """Twin document for one parent information asset.

    ``twin_id`` is deterministic from ``asset_id`` + source fingerprint so
    the same asset+content rebuilds to the same twin identity. Items are
    ordered: insights first (stable insert order), then open questions.
    """

    asset_id: str
    twin_id: str
    insights: tuple[TwinItem, ...]
    open_questions: tuple[TwinItem, ...]
    source_sha256: str
    version: int = 1

    @property
    def item_count(self) -> int:
        return len(self.insights) + len(self.open_questions)


def _fingerprint_source(source_text: str | None, items: Sequence[TwinItem]) -> str:
    if source_text is not None:
        return hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    # Fallback: fingerprint the item texts so twins without source text
    # still have a stable content hash for identity.
    payload = "\n".join(f"{i.kind}:{i.text}" for i in items)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _twin_id_for(asset_id: str, source_sha256: str) -> str:
    digest = hashlib.sha256(
        f"{asset_id}\0{source_sha256}".encode()
    ).hexdigest()[:20]
    return f"{_TWIN_ID_PREFIX}:{asset_id}:{digest}"


def _coerce_items(
    raw: Iterable[TwinItem | dict[str, object] | str],
    kind: TwinKind,
) -> tuple[TwinItem, ...]:
    out: list[TwinItem] = []
    seen: set[str] = set()
    for entry in raw:
        if isinstance(entry, TwinItem):
            item = entry if entry.kind == kind else TwinItem(
                kind=kind,
                text=entry.text,
                confidence=entry.confidence,
                source_quote=entry.source_quote,
            )
        elif isinstance(entry, dict):
            text = str(entry.get("text") or entry.get("summary") or "").strip()
            conf = entry.get("confidence", entry.get("llm_confidence"))
            quote = entry.get("source_quote") or entry.get("quote")
            item = TwinItem(
                kind=kind,
                text=text,
                confidence=float(conf) if conf is not None else None,
                source_quote=str(quote) if quote is not None else None,
            )
        else:
            item = TwinItem(kind=kind, text=str(entry))
        if item.item_id in seen:
            continue
        seen.add(item.item_id)
        out.append(item)
        if len(out) >= _MAX_ITEMS_PER_KIND:
            break
    return tuple(out)


def build_note_twin(
    asset_id: str,
    insights: Iterable[TwinItem | dict[str, object] | str] = (),
    open_questions: Iterable[TwinItem | dict[str, object] | str] = (),
    *,
    source_text: str | None = None,
    version: int = 1,
) -> NoteTwin:
    """Build a note twin for ``asset_id`` from extracted items.

    Accepts ``TwinItem`` instances, dicts shaped like research-bridge
    ``ExtractedItem`` (``summary``/``quote``/``llm_confidence``), or bare
    strings. Deduplicates by content-addressed ``item_id``. Empty twins
    (no insights and no questions) are allowed — an asset with nothing
    extracted still gets a twin identity so the surface can show an honest
    empty state rather than "no twin."
    """
    aid = asset_id.strip()
    if not aid:
        raise TwinItemError("asset_id must be non-empty")
    if version < 1:
        raise TwinItemError("version must be >= 1")

    insight_items = _coerce_items(insights, "insight")
    question_items = _coerce_items(open_questions, "open_question")
    all_items = insight_items + question_items
    source_sha = _fingerprint_source(source_text, all_items)
    twin_id = _twin_id_for(aid, source_sha)
    return NoteTwin(
        asset_id=aid,
        twin_id=twin_id,
        insights=insight_items,
        open_questions=question_items,
        source_sha256=source_sha,
        version=version,
    )


def merge_twins(twins: Sequence[NoteTwin], *, merged_asset_id: str | None = None) -> NoteTwin:
    """Merge multiple twins into one substrate (union by item_id).

    Used when combining contexts or after multi-sub-agent research completes.
    Higher ``version`` does not win item text — first-seen item wins so the
    merge is deterministic given twin order. ``merged_asset_id`` defaults to
    a stable join of parent asset ids.
    """
    if not twins:
        raise TwinItemError("merge_twins requires at least one twin")
    asset_id = merged_asset_id or "+".join(t.asset_id for t in twins)
    insights: list[TwinItem] = []
    questions: list[TwinItem] = []
    seen_i: set[str] = set()
    seen_q: set[str] = set()
    for twin in twins:
        for item in twin.insights:
            if item.item_id not in seen_i:
                seen_i.add(item.item_id)
                insights.append(item)
        for item in twin.open_questions:
            if item.item_id not in seen_q:
                seen_q.add(item.item_id)
                questions.append(item)
    # Fingerprint from merged items (not a single source document).
    return build_note_twin(
        asset_id,
        insights=insights,
        open_questions=questions,
        source_text=None,
        version=max(t.version for t in twins),
    )


def twin_to_markdown(twin: NoteTwin) -> str:
    """Render a twin as Markdown (HTML projection input / human view)."""
    lines = [
        f"# Note twin — `{twin.asset_id}`",
        "",
        f"- twin_id: `{twin.twin_id}`",
        f"- source_sha256: `{twin.source_sha256[:12]}…`",
        f"- version: {twin.version}",
        "",
        "## Insights",
        "",
    ]
    if twin.insights:
        for item in twin.insights:
            conf = (
                f" (confidence {item.confidence:.2f})"
                if item.confidence is not None
                else ""
            )
            lines.append(f"- {item.text}{conf}")
            if item.source_quote:
                lines.append(f"  > {item.source_quote}")
    else:
        lines.append("_No insights extracted._")
    lines.extend(["", "## Open questions", ""])
    if twin.open_questions:
        for item in twin.open_questions:
            lines.append(f"- {item.text}")
            if item.source_quote:
                lines.append(f"  > {item.source_quote}")
    else:
        lines.append("_No open questions extracted._")
    lines.append("")
    return "\n".join(lines)


_HTML_ESCAPE = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
}


def _esc(s: str) -> str:
    return re.sub(r'[&<>"]', lambda m: _HTML_ESCAPE[m.group(0)], s)


def twin_to_html(twin: NoteTwin) -> str:
    """Render a twin as a self-contained HTML fragment (HTML-first vision).

    PDF is never the primary view surface. This is the human-viewable
    projection of the twin substrate; agents can further wrap it in the
    html_projection shell later.
    """
    parts = [
        '<article class="antiek-note-twin" '
        f'data-asset-id="{_esc(twin.asset_id)}" '
        f'data-twin-id="{_esc(twin.twin_id)}">',
        f"<header><h1>Note twin — {_esc(twin.asset_id)}</h1></header>",
        "<section class=\"insights\"><h2>Insights</h2><ul>",
    ]
    if twin.insights:
        for item in twin.insights:
            parts.append(f"<li data-item-id=\"{_esc(item.item_id)}\">{_esc(item.text)}")
            if item.source_quote:
                parts.append(f"<blockquote>{_esc(item.source_quote)}</blockquote>")
            parts.append("</li>")
    else:
        parts.append("<li class=\"empty\">No insights extracted.</li>")
    parts.append("</ul></section>")
    parts.append("<section class=\"open-questions\"><h2>Open questions</h2><ul>")
    if twin.open_questions:
        for item in twin.open_questions:
            parts.append(f"<li data-item-id=\"{_esc(item.item_id)}\">{_esc(item.text)}")
            if item.source_quote:
                parts.append(f"<blockquote>{_esc(item.source_quote)}</blockquote>")
            parts.append("</li>")
    else:
        parts.append("<li class=\"empty\">No open questions extracted.</li>")
    parts.append("</ul></section></article>")
    return "".join(parts)
