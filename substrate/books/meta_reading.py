"""Meta-reading — a one-shot, read-only, page-cited synthesis over the
reader's OWNED corpus (Read SPR-08 M4).

"Deep-research my owned corpus → make me an asset (X pages / X minutes)."
This is the PROPOSED Research↔Read boundary (operator decision 2, sign-off
pending — see ``docs/decisions/spr-08-meta-reading-boundary.md``): a synthesis
that learns from books you own, kept in Read (not Research) because it is
scoped to the owned corpus, internet-agnostic, and produced as a re-openable
reading asset rather than a live investigation.

THREE PROPERTIES THAT DEFINE THE BOUNDARY (each tested):

1. OWNED-CORPUS-ONLY / INTERNET-AGNOSTIC. Retrieval is exclusively
   ``substrate.graph.search.search`` over a bounded set of owned document ids
   (``document_ids=...``) — the owned DuckDB graph, never the open internet.
   There is NO acquisition / Exa / Browserbase / open-web call anywhere on
   this path; if there were, this would be Research, not Read. The corpus
   scope is a HARD boundary at the planner (``corpus_scope="hard"``) that is
   REVERSIBLE to ``"soft"`` if the operator withholds sign-off (the rollback
   in the decision doc). "soft" widens retrieval to the whole owned graph
   (still no internet) — it never opens an internet path.

2. HARD LENGTH-BOX (operator decision 3). The deliverable is BUILT to the
   requested size up front via a word budget (``budget_for``), not trimmed
   after the fact. The model is asked for ~budget words and the result is
   bounded to the budget; if the synthesis cannot fit, it is labelled
   ``truncated``. The minutes→words math reuses the SPR-14 narration pace
   (``NARRATION_WPM``); the pages→words math is stated below.

3. PAGE-CITED, RE-OPENABLE. Citations carry the chunk + its resolved page
   (``page_anchor``) so opening one lands the SPR-07 in-book reader. The
   §9.0 gate is the SAME one chunk-search uses (default ``policy_tag``), so a
   withheld region's body never enters the synthesis or a citation.

§16: the synthesis is generated through the ONE Hermes-routed dispatch path,
research tier choosing the provider. No new runtime, no internet retrieval.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from substrate.dispatch.research_tier import resolve_research_tier
from substrate.dispatch.router import dispatch
from substrate.dispatch.session_routing import dispatch_routing_kwargs
from substrate.graph.search import EmbeddingModel, search

from .book_qa import Citation, _citations_from_chunks
from .model import list_book_assets

# ── Length-box mappings (operator decision 3 — documented, not magic) ──
#
# minutes → words: the SAME spoken-English pace the SPR-14 TTS budget uses
# (150 wpm — a common narration pace). An "X minutes" asset is built to
# ~X × 150 words so the narration of the asset lands near X minutes. We import
# the number indirectly via a local constant to avoid a TS-only-module import
# on the python side; it MUST match apps/reading/src/api/tts.ts NARRATION_WPM.
NARRATION_WPM = 150

# pages → words: a "page" here is a reading-density page of synthesis prose,
# not a book page. 300 words/page is the long-standing manuscript convention
# (a double-spaced page ≈ 250–300 words; we take the denser 300 so an "X pages"
# asset is a substantive page, not a sparse one). Stated so a maintainer can
# re-pick it: it is a readability choice, not a derived constant.
WORDS_PER_PAGE = 300

# Degenerate bounds — stated, never silent (rigor #3). A 0/negative size is a
# caller bug; an absurdly-large one would ask the model for a runaway
# transcript. We REJECT both with a stated bound rather than clamp silently, so
# the caller fixes the request. The minutes ceiling matches the TTS
# MAX_NARRATION_MINUTES (120) so the two length-boxes agree.
MIN_PAGES = 1
MAX_PAGES = 60  # 60 × 300 = 18k words — already a long-read asset
MIN_MINUTES = 1
MAX_MINUTES = 120

# How many owned chunks to ground the synthesis on. Bounded so the prompt
# stays within budget; the synthesis cites the chunks it was built from.
DEFAULT_SYNTHESIS_TOP_K = 24

CorpusScope = Literal["hard", "soft"]
LengthUnit = Literal["pages", "minutes"]


class MetaReadingError(ValueError):
    """A degenerate length request (0 / negative / above the cap), with the
    stated bound in the message. Raised before any dispatch."""


@dataclass(frozen=True)
class LengthBox:
    """The resolved length budget. ``word_budget`` is what the model is asked
    to fill and the result is bounded to (built-to-size, not post-trimmed)."""

    unit: LengthUnit
    amount: int
    word_budget: int


def budget_for(unit: LengthUnit, amount: int) -> LengthBox:
    """Resolve an "X pages" / "X minutes" request to a word budget, applying
    the degenerate bound. Throws ``MetaReadingError`` with the stated bound on
    a 0/negative or above-cap request — never a silent clamp."""
    if unit == "pages":
        if amount < MIN_PAGES:
            raise MetaReadingError(
                f"Length must be at least {MIN_PAGES} page(s); got {amount}."
            )
        if amount > MAX_PAGES:
            raise MetaReadingError(
                f"Length is capped at {MAX_PAGES} pages; got {amount}."
            )
        return LengthBox(unit="pages", amount=amount, word_budget=amount * WORDS_PER_PAGE)
    if unit == "minutes":
        if amount < MIN_MINUTES:
            raise MetaReadingError(
                f"Length must be at least {MIN_MINUTES} minute(s); got {amount}."
            )
        if amount > MAX_MINUTES:
            raise MetaReadingError(
                f"Length is capped at {MAX_MINUTES} minutes; got {amount}."
            )
        return LengthBox(unit="minutes", amount=amount, word_budget=amount * NARRATION_WPM)
    raise MetaReadingError(f"Unknown length unit {unit!r} (expected 'pages' or 'minutes').")


def _bound_to_budget(text: str, word_budget: int) -> tuple[str, bool]:
    """Bound a synthesis to the word budget (whole words, never a mid-word
    cut). Returns (bounded_text, truncated) — ``truncated`` is True when the
    synthesis overran and was cut, so the caller can label it honestly rather
    than present a silently-clipped asset as complete."""
    words = text.split()
    if len(words) <= word_budget:
        return text.strip(), False
    return " ".join(words[:word_budget]).strip(), True


@dataclass(frozen=True)
class MetaReading:
    """The one-shot read-only deliverable. ``report`` is MODEL-generated
    synthesis prose, bounded to the length-box; ``citations`` open the SPR-07
    reader. ``truncated`` is True when the synthesis was cut to fit (labelled,
    never hidden). ``corpus_document_ids`` records exactly which owned docs were
    in scope — the defensible record that this never reached the open internet.
    ``empty`` is True when the owned corpus had nothing to synthesize from."""

    report: str
    citations: list[Citation]
    length_box: LengthBox
    corpus_scope: CorpusScope
    corpus_document_ids: list[str]
    truncated: bool
    empty: bool
    context_chunk_count: int = 0


def resolve_owned_corpus(
    con: Any,
    *,
    scope: CorpusScope = "hard",
    document_ids: Sequence[str] | None = None,
    limit: int = 200,
) -> list[str]:
    """The owned-corpus document-id set the synthesis is scoped to.

    HARD scope (the proposed boundary): exactly the servable owned books the
    operator can read (``list_book_assets(servable_only=True)``), optionally
    intersected with an explicit ``document_ids`` the operator picked. SOFT
    scope (rollback when sign-off withheld): the same servable owned set with
    NO explicit-pick intersection required — i.e. the whole owned readable
    corpus. NEITHER scope touches the open internet; soft only WIDENS within
    the owned graph. The owned set is ``servable_only`` because a withheld
    book is not yours to synthesize from (and its body is gated anyway)."""
    owned = [a.document_id for a in list_book_assets(con, servable_only=True, limit=limit)]
    if scope == "hard" and document_ids:
        picked = set(document_ids)
        return [d for d in owned if d in picked]
    return owned


def generate_meta_reading(
    con: Any,
    *,
    prompt: str,
    unit: LengthUnit,
    amount: int,
    model: EmbeddingModel,
    investigation_id: str,
    scope: CorpusScope = "hard",
    document_ids: Sequence[str] | None = None,
    research_tier: str = "deep",
    top_k: int = DEFAULT_SYNTHESIS_TOP_K,
    config: Any | None = None,
) -> MetaReading:
    """Generate the meta-reading deliverable over the owned corpus ONLY.

    INTERNET-AGNOSTIC BY CONSTRUCTION: the only retrieval is ``search`` over
    the owned ``document_ids`` set; there is no acquisition / open-web call on
    this path. The length-box is resolved (and a degenerate request rejected)
    BEFORE any retrieval or dispatch. An empty owned corpus returns an honest
    empty deliverable (no dispatch). Raises ``MetaReadingError`` on a degenerate
    length; ``ProviderError`` propagates when dispatch is unavailable (→ 503)."""
    length_box = budget_for(unit, amount)  # rejects degenerate up front

    corpus_ids = resolve_owned_corpus(con, scope=scope, document_ids=document_ids)
    if not corpus_ids:
        return MetaReading(
            report="",
            citations=[],
            length_box=length_box,
            corpus_scope=scope,
            corpus_document_ids=[],
            truncated=False,
            empty=True,
            context_chunk_count=0,
        )

    retrieved = search(
        con,
        prompt,
        model=model,
        top_k=top_k,
        document_ids=corpus_ids,  # owned corpus IN-clause — gated, no internet
    )
    context_chunks = retrieved["results"]
    if not context_chunks:
        return MetaReading(
            report="",
            citations=[],
            length_box=length_box,
            corpus_scope=scope,
            corpus_document_ids=corpus_ids,
            truncated=False,
            empty=True,
            context_chunk_count=0,
        )

    synth_prompt = _build_synthesis_prompt(
        prompt=prompt, length_box=length_box, context_chunks=context_chunks
    )
    target = resolve_research_tier(research_tier)
    result = dispatch(
        synth_prompt,
        role="synthesizer",
        investigation_id=investigation_id,
        provider_override=target.provider,
        model_override=target.model,
        config=config,
        **dispatch_routing_kwargs(investigation_id, presence="engaged"),
    )
    report, truncated = _bound_to_budget(result.text, length_box.word_budget)
    return MetaReading(
        report=report,
        citations=_citations_from_chunks(context_chunks),
        length_box=length_box,
        corpus_scope=scope,
        corpus_document_ids=corpus_ids,
        truncated=truncated,
        empty=False,
        context_chunk_count=len(context_chunks),
    )


def _build_synthesis_prompt(
    *,
    prompt: str,
    length_box: LengthBox,
    context_chunks: Sequence[dict[str, Any]],
) -> str:
    """Assemble the synthesis prompt: the ask, the hard word budget (built-to-
    size), and the owned-corpus passages. The model is told to synthesize ONLY
    from the passages and to aim for the budget."""
    parts: list[str] = []
    parts.append(
        "Synthesize a single coherent report from the reader's OWN books below. "
        f"Write approximately {length_box.word_budget} words "
        f"(~{length_box.amount} {length_box.unit}). Draw ONLY on the provided "
        "passages — do not introduce facts that are not in them. Where a claim "
        "rests on a passage, make that visible in the prose."
    )
    parts.append(f"\nThe reader's ask: {prompt}")
    parts.append("\nPassages from the reader's owned corpus:")
    for i, ch in enumerate(context_chunks, start=1):
        title = ch.get("document_title") or ch.get("document_id", "")
        parts.append(f"[{i}] (from “{title}”) {ch.get('chunk_text', '')}")
    return "\n".join(parts)
