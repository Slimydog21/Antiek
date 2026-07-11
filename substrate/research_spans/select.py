"""Query-aware span selection with injectable ranker and extractor.

Public API:
    ``extract_select(query, document_record, budget, extractor, ranker, counter)``
    is the composed public API.  It calls the extractor, verifies every
    returned span against the exact DocumentRecord, ranks, and budgets.
    Returns a validated ``SelectionResult`` with bound counter/accounting.

    The extractor is **required** — there is no default no-op extractor
    exposed as a production default.  Callers who want extraction must
    inject a real extractor.

Selection algorithm:
    ``_select_candidates(candidates, budget, query, ranker, counter)``
    is the lower-level private function.  It ranks and greedily fills
    the budget.  Prefer ``extract_select`` for the full pipeline.

Query-aware contract (REJECT fix #7):
    The selection interface operates on (query, raw_document, token_budget)
    with an injected extractor and ranker.  The ``ExtractorProtocol``
    defines how raw documents are decomposed into spans;
    ``RankerProtocol`` scores spans for a given query.  The default
    ``DefaultRanker`` preserves retrieval score order — it does NOT
    claim semantic query awareness.  Callers who want genuine
    query-aware ranking inject a ranker that re-scores by relevance.

SelectionResult:
    Invariant-safe: private/factory or __post_init__ validates
    budget>0, total>=0<=budget, dropped>=0, selected tuple types,
    and recomputes model-facing token total using stored accounting.
    Callers cannot forge a SelectionResult.

Budget accounting (REJECT fix F):
    Budget must cover EXACT text sent to synthesis including adjacent
    attribution and separators.  The canonical ``render_and_count``
    function is shared by selection and assembly.  SelectionResult
    binds counter/accounting so assembly cannot switch to a different
    counter and exceed the budget.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .span import ExtractiveSpan

if TYPE_CHECKING:
    from .assemble import DocumentRecord


# ---------------------------------------------------------------------------
# Token counting (mirrors context_pack/assembler convention)
# ---------------------------------------------------------------------------


@runtime_checkable
class TokenCounter(Protocol):
    """Injectable token counter.  Default: chars/4 heuristic."""

    def count(self, text: str) -> int: ...


class DefaultTokenCounter:
    """Char-count / 4 heuristic — matches context_pack/assembler."""

    def count(self, text: str) -> int:
        if not text:
            return 0
        return max(1, (len(text) + 3) // 4)


# ---------------------------------------------------------------------------
# Canonical render and count — shared by selection and assembly
# ---------------------------------------------------------------------------


def render_and_count(
    span: ExtractiveSpan,
    counter: TokenCounter,
    separator: str = "\n---\n",
) -> int:
    """Render one span with adjacent attribution and count tokens.

    This is the ONE canonical render/count function shared by selection
    and assembly.  Both use the same function to ensure budget accounting
    is consistent — assembly cannot produce a different count than what
    selection budgeted for.

    The rendered output includes full provenance attribution:
    span_id, document_id, URL, revision, content hash, chunk_id, score.
    The model-facing context is mechanically bindable by SPR-04.

    Returns the token count of the rendered attributed span.
    """
    rendered = render_span_text(span)
    count = counter.count(rendered)
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError(
            "counter.count must return a non-boolean int, "
            f"got {type(count).__name__}"
        )
    if count < 0:
        raise ValueError(f"counter.count returned negative ({count})")
    return count


def render_span_text(span: ExtractiveSpan) -> str:
    """Canonical model-facing rendering for one span."""
    attribution = (
        f"[source: {span.document_id} | "
        f"span: {span.span_id} | "
        f"url: {span.source_url} | "
        f"rev: {span.revision} | "
        f"hash: {span.content_hash} | "
        f"chunk: {span.chunk_id} | "
        f"start: {span.start} | end: {span.end} | "
        f"score: {span.retrieval_score:.3f}]"
    )
    return f"{attribution}\n{span.text}"


def render_context_text(
    spans: Sequence[ExtractiveSpan], separator: str = "\n---\n"
) -> str:
    """Canonical exact synthesis context for a span sequence."""
    return separator.join(render_span_text(span) for span in spans)


# ---------------------------------------------------------------------------
# Extractor protocol (REJECT fix #7)
# ---------------------------------------------------------------------------


@runtime_checkable
class ExtractorProtocol(Protocol):
    """Injectable extractor: decomposes a raw document into spans.

    ``extract`` takes a query string, raw document text, a source URL,
    a document id, a revision, a content hash, and a token budget.
    It returns a sequence of ``ExtractiveSpan`` instances extracted
    from the document.

    There is no default extractor.  Callers must inject a real extractor.
    """

    def extract(
        self,
        query: str,
        document_text: str,
        source_url: str,
        document_id: str,
        revision: str,
        content_hash: str,
        budget: int,
    ) -> Sequence[ExtractiveSpan]: ...


# ---------------------------------------------------------------------------
# Ranker protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class RankerProtocol(Protocol):
    """Injectable ranker: scores spans for a given query.

    ``score`` returns a float; higher is better.  The selection
    algorithm sorts by this score (descending) and greedily fills
    the budget.  Scores must be finite.
    """

    def score(self, query: str, span: ExtractiveSpan) -> float: ...


class DefaultRanker:
    """Preserve the retrieval score order (descending).

    This is the identity ranker — it trusts the retriever's own
    scoring.  It does NOT claim semantic query awareness.
    Inject a different ranker to re-order by query relevance,
    diversity, or any other criterion.
    """

    def score(self, query: str, span: ExtractiveSpan) -> float:
        return span.retrieval_score


# ---------------------------------------------------------------------------
# Selection result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SelectionResult:
    """Outcome of a span selection pass.

    Invariant-safe: __post_init__ validates budget>0, total>=0<=budget,
    dropped>=0, selected tuple types, and recomputes model-facing token
    total using stored accounting.  Callers cannot forge.
    """

    selected: tuple[ExtractiveSpan, ...]
    total_tokens: int
    budget: int
    dropped_count: int

    # Bound counter and render function — assembly cannot switch.
    _bound_counter: TokenCounter | None = None
    _bound_render_and_count: object | None = None

    def __post_init__(self) -> None:
        """Validate all invariants.  Reject forged results."""
        # Budget must be positive.
        if not isinstance(self.budget, int) or self.budget <= 0:
            raise ValueError(
                f"budget must be a positive int, got {self.budget!r}"
            )

        # Total tokens: non-negative, within budget.
        if not isinstance(self.total_tokens, int) or self.total_tokens < 0:
            raise ValueError(
                f"total_tokens must be a non-negative int, got {self.total_tokens!r}"
            )
        if self.total_tokens > self.budget:
            raise ValueError(
                f"total_tokens ({self.total_tokens}) exceeds budget ({self.budget})"
            )

        # Dropped count: non-negative.
        if not isinstance(self.dropped_count, int) or self.dropped_count < 0:
            raise ValueError(
                f"dropped_count must be a non-negative int, got {self.dropped_count!r}"
            )

        # Selected must be a tuple of ExtractiveSpan.
        if not isinstance(self.selected, tuple):
            raise TypeError(
                f"selected must be tuple, got {type(self.selected).__name__}"
            )
        for i, item in enumerate(self.selected):
            if not isinstance(item, ExtractiveSpan):
                raise TypeError(
                    f"selected[{i}] must be ExtractiveSpan, "
                    f"got {type(item).__name__}"
                )

        if self._bound_counter is None:
            raise ValueError("SelectionResult requires bound token accounting")
        if self._bound_render_and_count is not render_and_count:
            raise ValueError("SelectionResult requires canonical render accounting")
        recomputed = self._bound_counter.count(render_context_text(self.selected))
        if isinstance(recomputed, bool) or not isinstance(recomputed, int):
            raise TypeError("counter.count must return a non-boolean int")
        if recomputed < 0:
            raise ValueError(f"counter.count returned negative ({recomputed})")
        if recomputed != self.total_tokens:
            raise ValueError(
                f"total_tokens ({self.total_tokens}) does not match "
                f"recomputed total ({recomputed}) using bound counter"
            )

    @property
    def budget_saturated(self) -> bool:
        """True if the selection filled the budget to capacity."""
        return self.total_tokens >= self.budget


# ---------------------------------------------------------------------------
# Budget presets (low / medium / high)
# ---------------------------------------------------------------------------


def span_budget_for_tier(
    tier_name: str,
    *,
    default_if_unknown: int = 2_000,
) -> int:
    """Per-document span budget derived from TierBudget.token_budget.

    Uses ``TierBudget.token_budget // breadth`` as the per-document
    allocation.  This is the structural derivation from the single
    authority (``tiers.py``); no duplicate constants.

    Raises ``ImportError`` if ``substrate.research_budget.tiers`` is
    unavailable (no silent fallback).  Returns ``default_if_unknown``
    for unrecognized tier names only.

    REJECT fix #9: no silent ImportError fallback.  The caller must
    handle the import failure explicitly.
    """
    from substrate.research_budget.tiers import TIERS

    tier = TIERS.get(tier_name)
    if tier is None:
        return default_if_unknown
    # Per-document = total // breadth.  Floor at 1 to avoid zero-budget.
    return max(1, tier.token_budget // tier.breadth)


# Named presets for common use.  These call through to the single
# tier authority — they are NOT independent constants.
def span_budget_low() -> int:
    """Low preset: derived from FAST tier."""
    return span_budget_for_tier("fast")


def span_budget_medium() -> int:
    """Medium preset: derived from DEEP tier."""
    return span_budget_for_tier("deep")


def span_budget_high() -> int:
    """High preset: derived from WRESTLE tier."""
    return span_budget_for_tier("wrestle")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_ranker_scores(
    query: str,
    candidates: Sequence[ExtractiveSpan],
    ranker: RankerProtocol,
) -> None:
    """Validate that the ranker returns finite scores for all candidates.

    Raises ValueError if any score is NaN or infinite.
    """
    for i, span in enumerate(candidates):
        score = ranker.score(query, span)
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise TypeError(
                f"ranker.score must return a non-boolean int or float, "
                f"got {type(score).__name__} for span {i}"
            )
        if score != score:  # NaN check
            raise ValueError(f"ranker.score returned NaN for span {i}")
        if score == float("inf") or score == float("-inf"):
            raise ValueError(
                f"ranker.score returned infinite ({score}) for span {i}"
            )


def _validate_counter_counts(
    text: str,
    counter: TokenCounter,
    label: str,
) -> int:
    """Validate that the counter returns a non-negative int.

    Raises ValueError if count is negative or not an int.
    """
    count = counter.count(text)
    if not isinstance(count, int):
        raise TypeError(
            f"counter.count must return int, got {type(count).__name__} for {label}"
        )
    if count < 0:
        raise ValueError(
            f"counter.count returned negative ({count}) for {label}"
        )
    return count


def _validate_span_against_record(
    span: ExtractiveSpan,
    record: DocumentRecord,
) -> None:
    """Validate that a span matches its source document record.

    Checks: document_id, source_url, revision, content_hash, text slice.
    """
    if span.document_id != record.document_id:
        raise ValueError(
            f"span document_id {span.document_id!r} does not match "
            f"record document_id {record.document_id!r}"
        )
    if span.source_url != record.source_url:
        raise ValueError(
            f"span source_url {span.source_url!r} does not match "
            f"record source_url {record.source_url!r}"
        )
    if span.revision != record.revision:
        raise ValueError(
            f"span revision {span.revision!r} does not match "
            f"record revision {record.revision!r}"
        )
    if span.content_hash != record.content_hash:
        raise ValueError(
            f"span content_hash {span.content_hash!r} does not match "
            f"record content_hash {record.content_hash!r}"
        )
    # Verify text matches content slice.
    expected_text = record.content[span.start : span.end]
    if span.text != expected_text:
        raise ValueError(
            f"span text does not match record.content[{span.start}:{span.end}]. "
            f"Expected {expected_text!r}, got {span.text!r}"
        )


# ---------------------------------------------------------------------------
# Public API: extract_select (composed pipeline)
# ---------------------------------------------------------------------------


def extract_select(
    query: str,
    document: DocumentRecord,
    budget: int,
    *,
    extractor: ExtractorProtocol,
    ranker: RankerProtocol | None = None,
    counter: TokenCounter | None = None,
) -> SelectionResult:
    """Public composed API: extract spans from a document, rank, and select.

    Calls the extractor to decompose the document into spans, verifies
    every returned span against the exact DocumentRecord, ranks with
    the injectable ranker, and selects spans within the token budget.

    Returns a validated ``SelectionResult`` with bound counter/accounting.

    The extractor is **required** — there is no default no-op extractor.
    Callers who want extraction must inject a real extractor.

    Args:
        query: The search query.  Must be non-empty.
        document: The source document record.  Must be a DocumentRecord.
        budget: Token budget.  Must be a positive int.
        extractor: The extractor to decompose the document.  Required.
        ranker: Injectable ranker.  Default: retrieval score order.
        counter: Injectable token counter.  Default: chars/4 heuristic.

    Returns:
        A validated ``SelectionResult`` with bound counter/accounting.

    Raises:
        TypeError: If extractor is not an ExtractorProtocol.
        ValueError: If query is empty, budget is not positive, or
            extractor returns spans that don't match the document.
    """
    # Import here to avoid circular import at module level.
    from .assemble import DocumentRecord as _DocRecord

    # Validate inputs.
    if not isinstance(query, str) or not query:
        raise ValueError("query must be a non-empty string")
    if not isinstance(document, _DocRecord):
        raise TypeError(
            f"document must be DocumentRecord, got {type(document).__name__}"
        )
    if not isinstance(budget, int) or budget <= 0:
        raise ValueError(f"budget must be a positive int, got {budget!r}")
    if not isinstance(extractor, ExtractorProtocol):
        raise TypeError(
            f"extractor must implement ExtractorProtocol, "
            f"got {type(extractor).__name__}"
        )

    ranker = ranker or DefaultRanker()
    counter = counter or DefaultTokenCounter()

    # Call the extractor.
    candidates = extractor.extract(
        query=query,
        document_text=document.content,
        source_url=document.source_url,
        document_id=document.document_id,
        revision=document.revision,
        content_hash=document.content_hash,
        budget=budget,
    )

    # Validate extractor outputs.
    if not isinstance(candidates, Sequence):
        raise TypeError(
            f"extractor.extract must return a Sequence, "
            f"got {type(candidates).__name__}"
        )

    # Verify every span against the document record.
    validated: list[ExtractiveSpan] = []
    for i, span in enumerate(candidates):
        if not isinstance(span, ExtractiveSpan):
            raise TypeError(
                f"extractor returned non-ExtractiveSpan at index {i}: "
                f"{type(span).__name__}"
            )
        _validate_span_against_record(span, document)
        validated.append(span)

    # Validate ranker scores are finite.
    _validate_ranker_scores(query, validated, ranker)

    # Select candidates within budget.
    result = _select_candidates(
        validated,
        budget=budget,
        query=query,
        ranker=ranker,
        counter=counter,
    )

    # Bind counter and render function to the result for assembly.
    # We need to create a new SelectionResult with bound accounting.
    return SelectionResult(
        selected=result.selected,
        total_tokens=result.total_tokens,
        budget=result.budget,
        dropped_count=result.dropped_count,
        _bound_counter=counter,
        _bound_render_and_count=render_and_count,
    )


# ---------------------------------------------------------------------------
# Private: _select_candidates (lower-level selection)
# ---------------------------------------------------------------------------


def _select_candidates(
    candidates: Sequence[ExtractiveSpan],
    *,
    budget: int,
    query: str,
    ranker: RankerProtocol | None = None,
    counter: TokenCounter | None = None,
) -> SelectionResult:
    """Select spans that fit within ``budget`` tokens.

    Lower-level private function.  Prefer ``extract_select`` for the
    full pipeline with document verification.

    Algorithm:
    1. Score each candidate with the ranker (default: retrieval score).
    2. Sort by score descending.
    3. Greedily add spans until the budget is exhausted.  The boundary
       is exact: a span that would push the total over the budget is
       dropped (not truncated — truncation would break verbatim
       fidelity).

    Uses the shared ``render_and_count`` function for budget accounting
    so the budget covers EXACT text sent to synthesis including adjacent
    attribution and separators.

    Returns a ``SelectionResult`` with bound counter/accounting.
    """
    if budget <= 0:
        raise ValueError(f"budget must be positive, got {budget}")

    ranker = ranker or DefaultRanker()
    counter = counter or DefaultTokenCounter()

    # Score + sort (stable, descending).
    scored: list[tuple[float, int, ExtractiveSpan]] = []
    for i, span in enumerate(candidates):
        score = ranker.score(query, span)
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise TypeError("ranker.score must return a non-boolean int or float")
        if score != score:  # NaN
            raise ValueError(f"ranker.score returned NaN for span {i}")
        if score == float("inf") or score == float("-inf"):
            raise ValueError(
                f"ranker.score returned infinite ({score}) for span {i}"
            )
        scored.append((score, i, span))
    scored.sort(key=lambda t: (-t[0], t[1]))

    selected: list[ExtractiveSpan] = []
    total_tokens = 0

    for _score, _idx, span in scored:
        # Use shared render_and_count — covers attribution + separator.
        candidate = (*selected, span)
        candidate_tokens = counter.count(render_context_text(candidate))
        if isinstance(candidate_tokens, bool) or not isinstance(candidate_tokens, int):
            raise TypeError("counter.count must return a non-boolean int")
        if candidate_tokens < 0:
            raise ValueError(f"counter.count returned negative ({candidate_tokens})")
        if candidate_tokens <= budget:
            selected.append(span)
            total_tokens = candidate_tokens
        # If it doesn't fit, skip — no truncation.

    return SelectionResult(
        selected=tuple(selected),
        total_tokens=total_tokens,
        budget=budget,
        dropped_count=len(candidates) - len(selected),
        _bound_counter=counter,
        _bound_render_and_count=render_and_count,
    )
