"""The companion renderings (companions SPR-01) — the human-facing shells,
on the twin-notes honesty conventions (twin_notes.py:29,42,46,49): sections
mirror sources, empty states are honest ("No findings yet."), never
fabricated filler.

EVERY claim carries its evidence_id (``data-evidence-id``) — the human text
and the agent index are literally the same rows rendered two ways, so a
claim's id resolves row-by-row into the index (the referential-integrity
contract). Deterministic by construction: rows render in evidence_id order;
nothing wall-clock enters the output (the stamp is source-derived).

The rights boundary at render: a WITHHELD document's claims render as
metadata lines (kind + id), never their text — "body never rides the
companion" (the §9.0 posture extended to the narrative surface).
"""

from __future__ import annotations

from html import escape as _esc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .projector import AnchorRead, BiteRead, ClaimRead, DocumentView, ProcessRead

#: The honest project-scope shell — rendered for callers that want the
#: SHELL; the projector's rebuild_project RAISES instead (never a fake
#: aggregate).
PROJECT_SCOPE_UNAVAILABLE_LINE = (
    "Project scope unavailable — the project container has not landed yet."
)


def render_project_companion() -> str:
    """The honest project-scope shell (the unit-3 container hasn't landed —
    say so, never fake a project aggregate)."""
    return (
        '<!doctype html>\n<html lang="en">\n<head><meta charset="utf-8">'
        "<title>Project companion</title></head>\n<body>\n"
        f'<p class="empty">{_esc(PROJECT_SCOPE_UNAVAILABLE_LINE)}</p>\n'
        "</body>\n</html>\n"
    )


def render_document_companion(view: DocumentView) -> str:
    """The per-document companion: where this document stands — its claims
    (text only when servable), its anchors, and the process that produced
    them (threads, diligence, reading position) — with honest empty states
    and every claim carrying its evidence_id."""
    if not view.exists:
        body = '<p class="empty">This document is not on record.</p>'
        title = "A document"
    else:
        title = view.title or "A document"
        claim_items = "".join(_claim_li(c, servable=view.servable) for c in view.claims) or (
            '<li class="empty">No findings yet.</li>'
        )
        anchor_items = "".join(_anchor_li(a) for a in view.anchors) or (
            '<li class="empty">No anchored passages yet.</li>'
        )
        process_items = "".join(_process_li(p) for p in view.processes) or (
            '<li class="empty">No process on record yet.</li>'
        )
        # The unit-8 bite ledger — a DERIVED document's companion section
        # (calm: ordinal + class + traced, never the bite's text here).
        bite_items = "".join(_bite_li(b) for b in view.bites)
        withheld = (
            '<p class="empty">This document’s text is withheld — only its metadata is shown.</p>'
            if not view.servable
            else ""
        )
        body = (
            f"{withheld}"
            f"<section><h2>Where this document stands</h2><ul>{claim_items}</ul></section>\n"
            f"<section><h2>Anchored passages</h2><ul>{anchor_items}</ul></section>\n"
            f"<section><h2>Process</h2><ul>{process_items}</ul></section>"
            + (
                f"<section><h2>The generated bites</h2><ul>{bite_items}</ul></section>"
                if view.bites
                else ""
            )
        )
    return (
        '<!doctype html>\n<html lang="en">\n<head><meta charset="utf-8">'
        f"<title>{_esc(title)} — companion</title></head>\n<body>\n"
        f"<h1>{_esc(title)}</h1>\n{body}\n</body>\n</html>\n"
    )


def _claim_li(claim: ClaimRead, *, servable: bool) -> str:
    kind_label = "Finding" if claim.node_kind == "insight" else "Open question"
    # The withheld boundary at render: the claim's existence + kind + id
    # are metadata; its TEXT stays with its lawful store.
    text = (
        _esc(claim.text)
        if servable
        else f"<em>{kind_label} grounded in a withheld source</em>"
    )
    return (
        f'<li data-evidence-id="{_esc(claim.evidence_id)}">'
        f"<strong>{kind_label}.</strong> {text}</li>"
    )


def _anchor_li(anchor: AnchorRead) -> str:
    where = (
        f"page {anchor.page_index_hint + 1}"
        if anchor.page_index_hint is not None
        else "a passage"
    )
    return (
        f'<li data-evidence-id="{_esc(anchor.evidence_id)}">'
        f"A passage on {where} — {_esc(anchor.status)}</li>"
    )


def _bite_li(bite: BiteRead) -> str:
    label = {
        "author_verbatim": "author's words ✓",
        "llm_compressed": "compressed",
        "llm_expanded": "expanded",
        "research_supplemented": "research-added",
    }.get(bite.contribution_class, bite.contribution_class)
    traced = "traced to the core" if bite.traced else "no direct source — honestly generated"
    return (
        f'<li data-evidence-id="{_esc(bite.evidence_id)}">'
        f"Bite {bite.ordinal + 1} — {_esc(label)} · {traced}</li>"
    )


def _process_li(process: ProcessRead) -> str:
    return (
        f'<li data-evidence-id="{_esc(process.evidence_id)}">'
        f"{_esc(process.label)} — {_esc(process.status_line)}</li>"
    )
