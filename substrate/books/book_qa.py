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
(``substrate.dispatch.router.dispatch``), with the curated fast/deep research
tier choosing WHICH registered provider the primary prefers (a per-call
override, not a second runtime). No new ASR/LLM/TTS host.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
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
    state (the model was NOT asked to answer ungrounded)."""

    answer: str
    citations: list[Citation]
    grounded: bool
    # Diagnostic: how many of the book's chunks were retrieved for this turn.
    context_chunk_count: int = 0
    # None only on the deliberate no-context branch where no model was called.
    dispatch_result: DispatchResult | None = None
    authority_digest: str | None = None


def _build_prompt(
    *,
    book_title: str | None,
    question: str,
    history: Sequence[Turn],
    context_chunks: Sequence[dict[str, Any]],
) -> str:
    """Assemble the dispatch prompt: the running conversation (bounded) + the
    gated book context + the new question. The model is instructed to answer
    ONLY from the provided book passages and to refuse rather than invent —
    the no-context branch never reaches here (see ``answer_book_question``)."""
    parts: list[str] = []
    title = book_title or "this book"
    parts.append(
        f"You are answering a reader's questions about the book “{title}”. "
        "Answer ONLY from the book passages provided below. If the passages do "
        "not contain the answer, say so plainly — do not invent facts or cite "
        "anything not in the passages."
    )
    if history:
        parts.append("\nThe conversation so far:")
        for t in history[-MAX_HISTORY_TURNS:]:
            parts.append(f"Reader: {t.question}")
            parts.append(f"You: {t.answer}")
    parts.append("\nBook passages (each tagged with its page when known):")
    for i, ch in enumerate(context_chunks, start=1):
        page_index = page_index_from_section_path(ch.get("section_path"))
        page_tag = f"page {page_index + 1}" if page_index is not None else "page not marked"
        parts.append(f"[{i}] ({page_tag}) {ch.get('chunk_text', '')}")
    parts.append(f"\nThe reader's question: {question}")
    return "\n".join(parts)


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
    deep: bool = False,
    prime_backend: Any | None = None,
    prime_outcome_sink: Callable[[Any], None] | None = None,
    canonical_checkpoint_sink: Callable[[list[str]], None] | None = None,
    resume_batch_outputs: list[str] | None = None,
    canonical_child_executor: Callable[
        [str, int, str, Callable[[], tuple[str, Decimal]]], tuple[str, Decimal]
    ] | None = None,
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
    if deep:
        # Deep Talk is deliberately the genuine recursive RLM workflow.  Prime,
        # when supplied, is merely the supplemental reduction input supported
        # by long_corpus; it can never replace these canonical batch calls.
        from orchestration.rlm.long_corpus import LongCorpusBatch, synthesize_long_corpus

        chunks = {str(ch.get("chunk_id", "")): ch for ch in context_chunks}

        def _run(text: str, phase: str, index: int) -> tuple[str, Decimal]:
            nonlocal authority_digest
            def execute() -> tuple[str, Decimal]:
                nonlocal authority_digest
                if authorized_dispatch is None:
                    target = resolve_research_tier(research_tier)
                    dispatched = dispatch(
                        text, role="user_agent", investigation_id=investigation_id,
                        provider_override=target.provider, model_override=target.model, config=config,
                    )
                else:
                    dispatched, authority_digest = authorized_dispatch(text)
                return dispatched.text, Decimal(str(dispatched.cost_usd))
            if canonical_child_executor is not None:
                return canonical_child_executor(phase, index, text, execute)
            return execute()

        def _batch(batch: LongCorpusBatch) -> tuple[str, Decimal]:
            selected = [chunks[item] for item in batch.corpus_chunk_ids]
            return _run(_build_prompt(
                book_title=None, question=question, history=history,
                context_chunks=selected,
            ), "canonical_batch", int(batch.batch_id.rsplit("-", 1)[-1]))

        def _reduce(outputs: list[str]) -> tuple[str, Decimal]:
            return _run(
                "Synthesize a final, grounded answer to the reader's question. "
                "Treat any section explicitly labelled supplemental Prime evidence as "
                "non-canonical and do not let it override the book-grounded analyses.\n\n"
                f"Question: {question}\n\n" + "\n\n".join(outputs),
                "final_reduce", 0,
            )

        answer, _session = synthesize_long_corpus(
            corpus_chunk_ids=list(chunks),
            chunk_token_counts={key: max(1, len(str(value.get("chunk_text", ""))) // 4)
                                for key, value in chunks.items()},
            target_batch_token_budget=8_000,
            investigation_id=investigation_id,
            synthesize_batch_fn=_batch,
            reduce_batch_outputs_fn=_reduce,
            prime_backend=prime_backend,
            prime_outcome_sink=prime_outcome_sink,
            canonical_checkpoint_sink=canonical_checkpoint_sink,
            resume_batch_outputs=resume_batch_outputs,
        )
        # A recursive turn contains several dispatch receipts.  The final text
        # is canonical, but no single DispatchResult truthfully represents the
        # whole workflow, so do not fabricate aggregate provider usage here.
        return BookAnswer(
            answer=answer, citations=_citations_from_chunks(context_chunks), grounded=True,
            context_chunk_count=len(context_chunks), authority_digest=authority_digest,
        )
    if authorized_dispatch is None:
        target = resolve_research_tier(research_tier)
        result = dispatch(
            prompt,
            role="user_agent",
            investigation_id=investigation_id,
            provider_override=target.provider,
            model_override=target.model,
            config=config,
        )
    else:
        result, authority_digest = authorized_dispatch(prompt)
    return BookAnswer(
        answer=result.text,
        citations=_citations_from_chunks(context_chunks),
        grounded=True,
        context_chunk_count=len(context_chunks),
        dispatch_result=result,
        authority_digest=authority_digest,
    )
