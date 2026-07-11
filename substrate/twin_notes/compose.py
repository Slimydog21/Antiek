"""Compose twin documents into a human-viewable HTML analysis draft.

Supports the operator vision of merging completed sub-agent researches into a
written analysis before full merge into a parent asset. Pure function — no LLM,
no network, no graph writes.

Rules:
* All twins must share one ``parent_asset_id`` (cross-parent → error).
* Insights/questions are HTML-escaped (no raw script injection).
* Output is a self-contained HTML fragment suitable for HTML-native surfaces.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from dataclasses import dataclass

from substrate.twin_notes.store import TwinDocument, TwinNotesError, TwinParentMismatch


@dataclass(frozen=True)
class AnalysisDraft:
    parent_asset_id: str
    title: str
    html: str
    twin_ids: list[str]
    insight_count: int
    question_count: int


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def compose_analysis_html(
    twins: Sequence[TwinDocument],
    *,
    title: str = "Combined analysis",
) -> AnalysisDraft:
    """Build an HTML analysis draft from one or more same-parent twins."""
    docs = list(twins)
    if not docs:
        raise TwinNotesError("compose requires at least one twin")
    parents = {d.parent_asset_id for d in docs}
    if len(parents) != 1:
        raise TwinParentMismatch(
            "cannot compose twins from different parents: " + ", ".join(sorted(parents))
        )
    parent = next(iter(parents))
    title_clean = (title or "Combined analysis").strip() or "Combined analysis"

    insights: list[str] = []
    questions: list[str] = []
    twin_ids: list[str] = []
    for d in docs:
        twin_ids.append(d.twin_id)
        for i in d.insights:
            t = i.strip()
            if t:
                insights.append(t)
        for q in d.questions:
            t = q.strip()
            if t:
                questions.append(t)

    # Dedupe while preserving order (casefold key).
    def _uniq(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for it in items:
            k = " ".join(it.split()).casefold()
            if k in seen:
                continue
            seen.add(k)
            out.append(it)
        return out

    insights = _uniq(insights)
    questions = _uniq(questions)

    parts: list[str] = [
        '<article class="antiek-twin-analysis" data-parent="'
        + _escape(parent)
        + '">',
        f"<h1>{_escape(title_clean)}</h1>",
        f'<p class="meta">parent={_escape(parent)} twins={len(twin_ids)}</p>',
    ]
    parts.append("<section><h2>Insights</h2>")
    if insights:
        parts.append("<ul>")
        for i in insights:
            parts.append(f"<li>{_escape(i)}</li>")
        parts.append("</ul>")
    else:
        parts.append("<p><em>No insights.</em></p>")
    parts.append("</section>")

    parts.append("<section><h2>Questions</h2>")
    if questions:
        parts.append("<ul>")
        for q in questions:
            parts.append(f"<li>{_escape(q)}</li>")
        parts.append("</ul>")
    else:
        parts.append("<p><em>No questions.</em></p>")
    parts.append("</section>")
    parts.append("</article>")

    return AnalysisDraft(
        parent_asset_id=parent,
        title=title_clean,
        html="\n".join(parts) + "\n",
        twin_ids=twin_ids,
        insight_count=len(insights),
        question_count=len(questions),
    )


__all__ = ["AnalysisDraft", "compose_analysis_html"]
