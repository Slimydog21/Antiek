"""Grounder JSON response parser + GroundingVerdict types.

Extracted from ``interfaces/research/api/grounding.py`` in Sprint 4
day 4-5. The bridge handler calls ``parse_grounder_response`` on the
LLM output and acts on the returned verdict to emit either
``ClaimGroundingCheckPassedPayload`` or
``ClaimGroundingCheckFailedPayload``.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

# Shared JSON-tolerant decoder lives at roles/_json_decode.py — moved
# there in Sprint 4 day 4-5 precisely because importing it from
# wrestling.py created a circular load path once roles/grounder/ +
# roles/note_taker/ + future roles/challenger/ all needed it.
try:
    from .._json_decode import extract_json_object as _extract_json_object
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from roles._json_decode import (
        extract_json_object as _extract_json_object,
    )

try:
    from substrate.provenance.validate_refs import validate_ref
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.provenance.validate_refs import validate_ref


# Closed failure-reason set — mirrors the Literal on
# ``ClaimGroundingCheckFailedPayload.reason``. The bridge enforces this
# at write time via the Pydantic Literal; the parser enforces it earlier
# to avoid producing values the schema would reject.
GROUNDING_FAILURE_REASONS: frozenset[str] = frozenset({
    "absent_from_source",
    "paraphrased_not_stated",
    "out_of_scope",
    "ambiguous",
})

GroundingFailureReason = Literal[
    "absent_from_source",
    "paraphrased_not_stated",
    "out_of_scope",
    "ambiguous",
]


@dataclass(frozen=True)
class GroundingVerdict:
    """Parsed grounder response.

    ``grounded``: True when the claim was found in the source.
    ``located_chunk_id``: the chunk where the claim was located (only
        meaningful when ``grounded`` is True).
    ``confidence``: model's subjective probability, clamped to [0, 1].
    ``reason``: the failure reason (only meaningful when ``grounded``
        is False).
    """

    grounded: bool
    located_chunk_id: str | None
    confidence: float
    reason: str | None


def parse_grounder_response(
    text: str,
    *,
    canonical_chunk_ids: Iterable[str] | None = None,
) -> GroundingVerdict:
    """Parse the LLM's JSON response. Returns a GroundingVerdict.

    Conservative defaults per the role prompt's "default to false when
    uncertain":

    - Malformed input → ``(False, None, 0.0, "ambiguous")``.
    - grounded=true with non-string chunk_id → chunk_id None.
    - When ``canonical_chunk_ids`` is supplied, a chunk_id outside that set
      is dropped at parse time rather than trusted as provenance.
    - Confidence out of [0, 1] → clamped.
    - Failure reason not in GROUNDING_FAILURE_REASONS → coerced to
      ``ambiguous``.
    """
    obj = _extract_json_object(text)
    if obj is None:
        return GroundingVerdict(False, None, 0.0, "ambiguous")

    grounded = bool(obj.get("grounded"))
    if grounded:
        chunk_id = obj.get("located_chunk_id")
        if canonical_chunk_ids is not None:
            chunk_id = validate_ref(chunk_id, canonical_chunk_ids)
        elif not isinstance(chunk_id, str):
            chunk_id = None
        try:
            confidence = float(obj.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        return GroundingVerdict(True, chunk_id, confidence, None)

    reason = obj.get("reason")
    if not isinstance(reason, str) or reason not in GROUNDING_FAILURE_REASONS:
        reason = "ambiguous"
    return GroundingVerdict(False, None, 0.0, reason)
