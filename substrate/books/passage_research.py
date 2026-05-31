"""Spin a deep research from a book passage — the cross-workflow seam
(Read SPR-08, backend pieces M1 + M4).

Two backend halves of the seam; the reader-side UI (ResearchThis.tsx,
return-to-reading, the Playwright e2e) layers on the DRW reading surface,
which is unbuilt.

1. **The research seed, gated.** ``build_research_seed`` turns a passage
   into the context that pre-seeds the Research workflow's planner. The
   case that bites (rigor #3): seeding a deep research with a *gated*
   book's full text would launder that text past the SPR-01 serve gate.
   So the seed re-derives servability at the data layer — through the
   SPR-02 serving-boundary guard (``serve_full_text_guarded``, the single
   sanctioned full-body serve path, which composes the content_class gate
   with the independent license-tier cross-check) — and **refuses to put
   gated full text in the seed**: a gated book contributes title/author/TOC
   + the bounded snippet only, exactly what the serve gate would expose.
   The guard lives in the SAME layer (``substrate.books.serve_guard``,
   adjacent to ``serve.py``), so it is imported normally at module top — no
   layering inversion, no cycle (serve_guard does not import passage_research).
   For a non-arXiv book (no ``license_uri``) the guard is a transparent
   pass-through, so behaviour here is unchanged; a genuine T3-body drift now
   RAISES rather than seeding a forbidden body.
   Defense in depth: even if the caller hands us the selected passage
   text, we drop it for a gated book.

2. **The two-way provenance link.** ``link_passage_to_research`` records
   that a passage spawned a research, and ``researches_for_passage`` /
   ``passage_for_research`` read it back both ways. This reuses the
   existing ``question.escalated_to_research`` event (a passage question
   escalating to a child investigation is exactly that relationship), so
   there is no new schema — the link lives in the trajectory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from substrate.event_log import emit_typed, trajectory
from substrate.schemas.events import QuestionEscalatedToResearchPayload

from .serve_guard import serve_full_text_guarded
from .servability import ServabilityStatus

# A passage is addressed by (document_id, page_index). We encode that as a
# synthetic question_id so the existing escalation event can carry it
# without a schema change. Format: passage:<document_id>:p<page_index>
_PASSAGE_PREFIX = "passage"
_PASSAGE_RE = re.compile(r"^passage:(?P<doc>.+):p(?P<page>\d+)$")


def passage_id(document_id: str, page_index: int) -> str:
    return f"{_PASSAGE_PREFIX}:{document_id}:p{page_index}"


def parse_passage_id(pid: str) -> Optional[tuple[str, int]]:
    m = _PASSAGE_RE.match(pid)
    if not m:
        return None
    return m.group("doc"), int(m.group("page"))


@dataclass(frozen=True)
class ResearchSeed:
    """The context handed to the Research planner. ``seed_text`` is the
    only text that crosses into the research — and it is NEVER gated full
    text. ``gated`` records whether the source book was gated (in which
    case ``seed_text`` is a bounded snippet, not the passage body)."""

    document_id: str
    page_index: int
    book_title: Optional[str]
    book_author: Optional[str]
    servability: str
    seed_text: str
    gated: bool


def build_research_seed(
    con: Any,
    *,
    document_id: str,
    page_index: int,
    passage_text: Optional[str] = None,
) -> ResearchSeed:
    """Build the (gate-safe) research seed for a passage.

    ``passage_text`` is the text the reader selected. For a SERVABLE book
    it becomes the seed body. For a GATED or taken-down book it is
    DROPPED and replaced by the bounded snippet the serve gate would
    expose — the seed can never carry gated full text, even if the caller
    supplies it.

    Routes the full-body serve through the SPR-02 serving-boundary guard,
    ``substrate.books.serve_guard.serve_full_text_guarded`` — same layer,
    imported normally at module top (no inversion, no cycle).
    """
    served = serve_full_text_guarded(con, document_id)
    if not served.found:
        raise ValueError(f"{document_id} is not a registered book")

    status = served.servability or ServabilityStatus.GATED_METADATA_ONLY
    is_gated = not served.servable

    if served.servable:
        # Licensed/public-domain: the selected passage (or the served body)
        # may seed the research.
        body = passage_text or served.full_text or ""
    else:
        # Gated / taken-down: NEVER the passage body. Only the bounded
        # snippet (or nothing). Drop any passage_text the caller passed.
        body = served.snippet or ""

    title = served.title or document_id
    author = served.author
    context = f"From the book “{title}”"
    if author:
        context += f" by {author}"
    context += f" (page {page_index + 1})."
    seed_text = f"{context}\n\n{body}".strip()

    return ResearchSeed(
        document_id=document_id,
        page_index=page_index,
        book_title=served.title,
        book_author=author,
        servability=status.value if hasattr(status, "value") else str(status),
        seed_text=seed_text,
        gated=is_gated,
    )


def link_passage_to_research(
    *,
    document_id: str,
    page_index: int,
    investigation_id: str,
    parent_investigation_id: str = "read-spin",
) -> Optional[str]:
    """Record that a passage spawned a research. Reuses the existing
    ``question.escalated_to_research`` event — the passage is the
    "question", the research is the child investigation. Returns the
    event_id."""
    return emit_typed(
        parent_investigation_id,
        QuestionEscalatedToResearchPayload(
            question_id=passage_id(document_id, page_index),
            child_investigation_id=investigation_id,
        ),
        document_id=document_id,
        role="read/spin_research",
        policy_id="read/books/spin_research",
    )


def researches_for_passage(
    document_id: str,
    page_index: int,
    *,
    parent_investigation_id: str = "read-spin",
) -> list[str]:
    """Forward link: the child research investigation_ids spawned from a
    passage. Surfaced in the reader as 'this passage spawned N
    researches'."""
    pid = passage_id(document_id, page_index)
    out: list[str] = []
    for e in trajectory(parent_investigation_id):
        if (
            e.get("action_type") == "question.escalated_to_research"
            and e.get("payload", {}).get("question_id") == pid
        ):
            child = e["payload"].get("child_investigation_id")
            if child:
                out.append(child)
    return out


def passage_for_research(
    investigation_id: str,
    *,
    parent_investigation_id: str = "read-spin",
) -> Optional[tuple[str, int]]:
    """Backward link: the (document_id, page_index) a research was spun
    from. Lets the completed research link back to the originating
    passage."""
    for e in trajectory(parent_investigation_id):
        if (
            e.get("action_type") == "question.escalated_to_research"
            and e.get("payload", {}).get("child_investigation_id") == investigation_id
        ):
            return parse_passage_id(e["payload"].get("question_id", ""))
    return None
