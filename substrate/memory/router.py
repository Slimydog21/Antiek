"""Pure deterministic reconciliation for extracted account-memory candidates."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from runtime.db_lock import LockedConnection

from ._text import lexical_tokens, normalized_text
from .models import MemoryDecision, MemoryItem
from .store import list_memory

_NEGATION_TOKENS = frozenset(
    {
        "aren't",
        "avoid",
        "avoids",
        "can't",
        "cannot",
        "deny",
        "denies",
        "didn't",
        "dislike",
        "dislikes",
        "doesn't",
        "don't",
        "isn't",
        "never",
        "no",
        "not",
        "refuse",
        "refuses",
        "wasn't",
        "without",
        "won't",
    }
)
_NEGATION_MODIFIERS = frozenset(
    {
        "anymore",
        "are",
        "be",
        "been",
        "being",
        "did",
        "do",
        "does",
        "is",
        "longer",
        "was",
        "were",
    }
)
_NUMBER_RE = re.compile(r"(?<!\w)[+-]?(?:\d+(?:[.,]\d+)*)%?(?!\w)")


def load_memory_timeline(con: LockedConnection, candidate: MemoryItem) -> list[MemoryItem]:
    """Load the complete exact-key timeline required by the pure router."""
    return list_memory(
        con,
        candidate.owner_user_id,
        subject=candidate.subject,
        predicate=candidate.predicate,
        include_invalidated=True,
    )


def route_memory_update(existing: list[MemoryItem], candidate: MemoryItem) -> MemoryDecision:
    """Classify ``candidate`` as ADD, UPDATE, SUPERSEDE, or NOOP.

    Matching is owner-local and uses the writer's exact ``(subject, predicate)``
    key. Exact or less-informative repeats are NOOPs. A candidate that retains
    an existing object's lexical content and adds detail is an UPDATE. A changed
    value for the same key is a SUPERSEDE; a new key is an ADD.

    The function performs no I/O and does not mutate either argument. ``existing``
    must come from ``load_memory_timeline`` (or an equivalent all-time query) so
    future heads cannot be mistaken for novel facts. A caller persists ADD,
    UPDATE, and SUPERSEDE candidates with ``write_memory_item``; that existing
    write chokepoint preserves and invalidates the prior version.
    """
    if candidate.valid_to is not None or candidate.superseded_by is not None:
        raise ValueError("candidate memory must be a current, unsuperseded item")

    candidate_key = _memory_key(candidate)
    same_key = [
        item
        for item in existing
        if item.owner_user_id == candidate.owner_user_id and _memory_key(item) == candidate_key
    ]
    if not same_key:
        return MemoryDecision(
            action="ADD",
            candidate=candidate,
            reason="no memory has the same owner, subject, and predicate",
        )

    by_edge_id = {item.edge_id: item for item in same_key}
    missing_successors = [
        item.superseded_by
        for item in same_key
        if item.superseded_by is not None and item.superseded_by not in by_edge_id
    ]
    if missing_successors:
        raise ValueError("existing memory timeline is incomplete; include superseded successors")

    heads = [item for item in same_key if item.valid_to is None]
    if len(heads) != 1:
        raise ValueError("existing memory timeline must contain exactly one current head")
    matched = heads[0]
    candidate_start = _as_utc_naive(candidate.valid_from)
    head_start = _as_utc_naive(matched.valid_from)
    if candidate_start < head_start:
        raise ValueError("candidate valid_from cannot precede the current memory head")
    if normalized_text(matched.object) == normalized_text(candidate.object):
        return MemoryDecision(
            action="NOOP",
            candidate=candidate,
            matched_item=matched,
            reason="candidate duplicates the current memory head",
        )
    if candidate_start == head_start:
        raise ValueError("candidate valid_from must be later than the current memory head")

    if _contradicts(matched.object, candidate.object):
        return MemoryDecision(
            action="SUPERSEDE",
            candidate=candidate,
            matched_item=matched,
            reason="candidate conflicts with the current value for this memory key",
        )
    if _augments(matched.object, candidate.object):
        return MemoryDecision(
            action="UPDATE",
            candidate=candidate,
            matched_item=matched,
            reason="candidate retains the current value and adds information",
        )
    if _augments(candidate.object, matched.object):
        return MemoryDecision(
            action="NOOP",
            candidate=candidate,
            matched_item=matched,
            reason="candidate is a less-informative restatement of current memory",
        )
    return MemoryDecision(
        action="SUPERSEDE",
        candidate=candidate,
        matched_item=matched,
        reason="candidate changes the current value for this memory key",
    )


def _memory_key(item: MemoryItem) -> tuple[str, str]:
    return item.subject, item.predicate


def _contradicts(existing: str, candidate: str) -> bool:
    existing_tokens = frozenset(lexical_tokens(existing))
    candidate_tokens = frozenset(lexical_tokens(candidate))
    existing_negated = bool(existing_tokens & _NEGATION_TOKENS)
    candidate_negated = bool(candidate_tokens & _NEGATION_TOKENS)
    existing_core = existing_tokens - _NEGATION_TOKENS - _NEGATION_MODIFIERS
    candidate_core = candidate_tokens - _NEGATION_TOKENS - _NEGATION_MODIFIERS
    if existing_negated != candidate_negated and existing_core and existing_core == candidate_core:
        return True

    existing_numbers = frozenset(_NUMBER_RE.findall(existing.casefold()))
    candidate_numbers = frozenset(_NUMBER_RE.findall(candidate.casefold()))
    return bool(
        existing_numbers and candidate_numbers and not existing_numbers.issubset(candidate_numbers)
    )


def _augments(existing: str, candidate: str) -> bool:
    existing_tokens = frozenset(lexical_tokens(existing))
    candidate_tokens = frozenset(lexical_tokens(candidate))
    if existing_tokens:
        return existing_tokens < candidate_tokens
    normalized_existing = normalized_text(existing)
    normalized_candidate = normalized_text(candidate)
    return bool(
        normalized_existing
        and normalized_existing != normalized_candidate
        and normalized_existing in normalized_candidate
    )


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


__all__ = ["load_memory_timeline", "route_memory_update"]
