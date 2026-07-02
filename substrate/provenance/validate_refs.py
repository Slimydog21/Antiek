"""Pure helpers for model-emitted reference validation.

Role parsers may accept identifiers emitted by an LLM only after comparing
them with the canonical references the model was shown. A miss is not a fact;
it is dropped before it can become graph provenance.
"""

from __future__ import annotations

from collections.abc import Iterable


def _canonical_set(canonical_refs: Iterable[str]) -> frozenset[str]:
    return frozenset(
        ref.strip()
        for ref in canonical_refs
        if isinstance(ref, str) and ref.strip()
    )


def validate_ref(candidate: object, canonical_refs: Iterable[str]) -> str | None:
    """Return the canonical reference when ``candidate`` is allowed.

    Non-strings, blank strings, and strings absent from ``canonical_refs`` return
    ``None``. The function intentionally does no fuzzy matching; provenance
    references are identity claims, not search queries.
    """
    if not isinstance(candidate, str):
        return None
    cleaned = candidate.strip()
    if not cleaned:
        return None
    allowed = _canonical_set(canonical_refs)
    return cleaned if cleaned in allowed else None


def validate_refs(candidates: object, canonical_refs: Iterable[str]) -> tuple[str, ...]:
    """Validate a list-like set of candidate refs, preserving first-seen order."""
    if not isinstance(candidates, (list, tuple)):
        return ()
    allowed = _canonical_set(canonical_refs)
    out: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        cleaned = candidate.strip()
        if cleaned and cleaned in allowed and cleaned not in seen:
            out.append(cleaned)
            seen.add(cleaned)
    return tuple(out)
