"""Talk-to-book — gated, page-cited question answering over ONE book
(Read SPR-08 M2).

The book-level multi-turn conversation lives in the reader UI
(``apps/reading/src/modes/Reading``); this is the per-turn backend it calls.
A turn is: retrieve the most relevant chunks OF THIS BOOK (and only this book)
through the §9.0 retrieval gate, hand the model that gated context plus the
running conversation, and return a structured answer whose claims cite
page-level locations back into the SPR-07 reader.

The three load-bearing properties (rigor #3 degenerate inputs are tested):

1. §9.0 NO-LEAK. Retrieval goes through ``substrate.graph.search.search`` with
   a ``policy_tag`` the CALLER supplies (default: non-privileged
   'attribution_eligible'). On the default / any non-privileged tag a withheld /
   restricted / personal book's chunks never enter the result set — and
   therefore never enter the model's context or a citation; a talk-to-book
   answer then CANNOT quote or cite that region because the body never reaches
   it. The ONE exception is the authenticated OWNER reading his OWN
   gated/personal book: the caller (which has done the owner-auth check) passes
   a PRIVILEGED tag ('operator_only' ∈ ``PRIVILEGED_POLICY_TAGS``) and the
   SAME gate then admits ``restricted_pending_opt_in`` + ``personal_reading``.
   This is the SAME gate the chunk-search path uses; we do not re-implement or
   bypass it — we only forward the tag the caller already resolved.

2. NO-EXTRACTABLE-TEXT books fail gracefully. A scanned-image PDF has no
   embedded chunks (nothing to embed / retrieve). ``answer_book_question``
   returns an empty-context answer that SAYS it has nothing to ground on,
   rather than dispatching a model to hallucinate. The caller surfaces the
   honest "no readable text in this book" state.

3. APPROXIMATE PAGE CITATIONS are labelled approximate. A chunk's page is
   resolved from ``section_path`` (``page_anchor.page_index_from_section_path``);
   when it does not resolve to a ``Page N`` marker the citation carries
   ``page_index=None`` and ``page_resolved=False`` so the UI shows an honest
   "page not pinpointed — open the book" rather than a fabricated page.

§16: the answer is generated through the ONE Hermes-routed dispatch path
(``substrate.dispatch.router.dispatch``) as the ``thought_partner`` role — the
SAME role Surface E / AISidecar / FloatMenu Dialogue use — so TalkToBook is
not a second partner personality. Book-scoped retrieval + page citations stay
on ``/books/{id}/ask`` (dual structure: one role, book-grounded path). The
curated fast/deep research tier chooses WHICH registered provider the primary
prefers (a per-call override, not a second runtime). No new ASR/LLM/TTS host.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from substrate.dispatch.research_tier import resolve_research_tier
from substrate.dispatch.router import DispatchResult, dispatch
from substrate.graph.search import EmbeddingModel, search

from .page_anchor import page_index_from_section_path

# How many of the book's chunks to ground a turn on. Small enough to keep the
# prompt focused (and cheap), large enough to answer a cross-passage question.
DEFAULT_QA_TOP_K = 6

# How many prior turns of the running conversation to carry into the prompt.
# The multi-turn thread lives in the reader's session state (the floating
# bookmark); the client sends the recent tail, we bound it so a long thread
# can't blow the context budget. The bound is stated, not silent.
MAX_HISTORY_TURNS = 8


@dataclass(frozen=True)
class Citation:
    """One page-level citation in a talk-to-book answer. ``page_index`` is the
    0-based reader page the cited chunk anchors to, or ``None`` when the
    chunk's ``section_path`` does not resolve to a page (then ``page_resolved``
    is False and the UI must show an honest "page not pinpointed")."""

    chunk_id: str
    document_id: str
    page_index: int | None
    page_resolved: bool
    snippet: str  # a bounded excerpt of the cited chunk (already gate-served)


@dataclass(frozen=True)
class Turn:
    """One prior conversation turn carried into the next prompt. ``question``
    is user-sourced; ``answer`` is the model's prior reply (MODEL-sourced —
    never relabelled). Kept distinct so the prompt builder never conflates the
    two."""

    question: str
    answer: str


@dataclass(frozen=True)
class BookAnswer:
    """A talk-to-book turn result. ``answer`` is MODEL-generated prose;
    ``citations`` anchor its claims back into the book. ``grounded`` is False
    when there was no extractable text to retrieve — the honest no-context
    state (the model was NOT asked to answer ungrounded). ``shape`` is the
    thought_partner response shape (challenge|synthesis|extension) when a
    model ran; None on the no-context branch."""

    answer: str
    citations: list[Citation]
    grounded: bool
    # Diagnostic: how many of the book's chunks were retrieved for this turn.
    context_chunk_count: int = 0
    # None only on the deliberate no-context branch where no model was called.
    dispatch_result: DispatchResult | None = None
    authority_digest: str | None = None
    # thought_partner shape — same vocabulary as POST /thought-partner.
    shape: str | None = None


def _chunks_as_selected_notes(
    context_chunks: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map book-scoped retrieval hits to thought_partner ``selected_notes``.

    Same shape ``_retrieve_thought_partner_context`` / Surface E use — so the
    role sees one vocabulary whether notes came from the library graph or
    this open book's passages.
    """
    notes: list[dict[str, Any]] = []
    for ch in context_chunks:
        page_index = page_index_from_section_path(ch.get("section_path"))
        page_tag = (
            f"page {page_index + 1}" if page_index is not None else "page not marked"
        )
        body = (ch.get("chunk_text") or "").strip()
        notes.append({
            "note_id": ch.get("chunk_id") or "",
            "note_text": f"({page_tag}) {body}".strip(),
            "source_event_ids": [ch["document_id"]] if ch.get("document_id") else [],
            "confidence": float(ch.get("similarity") or 0.0),
        })
    return notes


def _display_answer_from_tp(parsed: Any, raw: str) -> str:
    """Prefer structured thought_partner fields for the reader-facing answer.

    TalkToBook is multi-turn prose in the bookmark; dumping raw JSON would
    feel like a different partner. Shape still travels separately.
    """
    shape = getattr(parsed, "shape", "synthesis")
    if shape == "challenge" and parsed.challenges:
        return "\n".join(c.condition for c in parsed.challenges)
    if shape == "extension" and parsed.extensions:
        lines = []
        for e in parsed.extensions:
            line = e.sub_question
            if e.rationale:
                line = f"{line} — {e.rationale}"
            lines.append(line)
        return "\n".join(lines)
    if parsed.synthesis and parsed.synthesis.text.strip():
        return str(parsed.synthesis.text.strip())
    return (raw or "").strip()


def _build_prompt(
    *,
    book_title: str | None,
    question: str,
    history: Sequence[Turn],
    context_chunks: Sequence[dict[str, Any]],
) -> str:
    """Assemble a thought_partner prompt over THIS book's passages.

    Dual structure: book-scoped retrieval stays here; the ROLE is the shared
    ``thought_partner`` (Surface E / sidecar / Dialogue). History is folded
    into the user prompt so multi-turn TalkToBook still works.
    """
    from roles.thought_partner import (
        THOUGHT_PARTNER_SYSTEM_PROMPT,
        compose_thought_partner_prompt,
    )

    title = book_title or "this book"
    user_bits: list[str] = [
        f"The reader is in the book “{title}”. Answer ONLY from the selected "
        "notes (passages of this book). If they do not contain the answer, say "
        "so plainly — do not invent. Prefer SYNTHESIS for direct questions; "
        "use CHALLENGE / EXTENSION when the reader asks what could go wrong or "
        "what to look into next.",
    ]
    if history:
        user_bits.append("Conversation so far:")
        for t in history[-MAX_HISTORY_TURNS:]:
            user_bits.append(f"Reader: {t.question}")
            user_bits.append(f"You: {t.answer}")
    user_bits.append(f"Reader's question: {question}")
    role_prompt = compose_thought_partner_prompt(
        user_prompt="\n".join(user_bits),
        selected_notes=_chunks_as_selected_notes(context_chunks),
    )
    return (
        THOUGHT_PARTNER_SYSTEM_PROMPT
        + "\n\nBOOK-SCOPED CONTEXT: selected notes are passages from the open "
        "book only (TalkToBook path). Cite note_ids; page tags are in the note "
        "text.\n\n"
        + role_prompt
    )


def _citations_from_chunks(context_chunks: Sequence[dict[str, Any]]) -> list[Citation]:
    """Turn the retrieved (gate-served) chunks into page-level citations. Each
    chunk that survived the §9.0 gate is a legitimate, citable source; the page
    is resolved best-effort and labelled approximate when it does not pin."""
    out: list[Citation] = []
    for ch in context_chunks:
        page_index = page_index_from_section_path(ch.get("section_path"))
        text = ch.get("chunk_text", "") or ""
        out.append(
            Citation(
                chunk_id=ch.get("chunk_id", ""),
                document_id=ch.get("document_id", ""),
                page_index=page_index,
                page_resolved=page_index is not None,
                snippet=text[:240] + ("…" if len(text) > 240 else ""),
            )
        )
    return out


def answer_book_question(
    con: Any,
    *,
    document_id: str,
    question: str,
    model: EmbeddingModel,
    investigation_id: str,
    history: Sequence[Turn] | None = None,
    research_tier: str = "deep",
    top_k: int = DEFAULT_QA_TOP_K,
    config: Any | None = None,
    policy_tag: str = "attribution_eligible",
    authorized_dispatch: Callable[[str], tuple[DispatchResult, str]] | None = None,
) -> BookAnswer:
    """Answer one talk-to-book turn, page-cited, gate-safe.

    Retrieval is scoped to ``document_id`` through the §9.0 gate. A book with no
    extractable chunks returns an ungrounded, honest no-context answer WITHOUT
    dispatching a model (rigor #3). Otherwise the gated context + the running
    conversation are dispatched through the curated research tier; the reply's
    claims are backed by the page-level citations of the retrieved chunks.

    ``policy_tag`` is the §9.0 retrieval policy threaded straight through to
    ``substrate.graph.search.search`` — it is NOT re-interpreted here. The
    DEFAULT ('attribution_eligible') is non-privileged: the gate excludes
    restricted (``restricted_pending_opt_in``) AND owner-only
    (``personal_reading``) content, so a withheld book's chunks never enter the
    result set, the model context, or a citation. The owner read path (the
    authenticated owner talking to HIS OWN gated/personal book) passes a
    PRIVILEGED tag (``operator_only`` ∈ ``PRIVILEGED_POLICY_TAGS``) so — and
    only then — the gate admits those classes. The privilege decision is the
    CALLER's (it owns the auth check); this function only forwards the tag.

    Raises ``ProviderError`` when every provider in the dispatch chain is
    unavailable (no key) — the caller maps that to an honest 503, never a
    fabricated answer.
    """
    history = history or []

    retrieved = search(
        con,
        question,
        model=model,
        top_k=top_k,
        document_id=document_id,
        # §9.0 gate, applied via the caller-supplied policy_tag. The DEFAULT is
        # non-privileged ⇒ restricted/personal chunks never enter retrieval (so
        # never the model context or a citation). The authenticated-owner caller
        # passes a PRIVILEGED tag to read his own gated/personal book in full.
        policy_tag=policy_tag,
    )
    context_chunks = retrieved["results"]

    if not context_chunks:
        # No extractable text (scanned-image PDF) OR a fully-withheld book:
        # nothing to ground on. Do NOT dispatch a model to guess — return the
        # honest no-context state.
        return BookAnswer(
            answer=(
                "I couldn't find any readable text in this book to answer from. "
                "It may be a scanned/image-only edition, or its passages aren't "
                "available."
            ),
            citations=[],
            grounded=False,
            context_chunk_count=0,
        )

    prompt = _build_prompt(
        book_title=None,
        question=question,
        history=history,
        context_chunks=context_chunks,
    )
    authority_digest: str | None = None
    if authorized_dispatch is None:
        target = resolve_research_tier(research_tier)
        result = dispatch(
            prompt,
            role="thought_partner",
            investigation_id=investigation_id,
            provider_override=target.provider,
            model_override=target.model,
            config=config,
        )
    else:
        result, authority_digest = authorized_dispatch(prompt)
    from roles.thought_partner import parse_thought_partner_response

    parsed = parse_thought_partner_response(result.text)
    return BookAnswer(
        answer=_display_answer_from_tp(parsed, result.text),
        citations=_citations_from_chunks(context_chunks),
        grounded=True,
        context_chunk_count=len(context_chunks),
        dispatch_result=result,
        authority_digest=authority_digest,
        shape=parsed.shape,
    )
