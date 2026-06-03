"""P5 chunk provenance policy — ASR SR-09.

Codegen-facing citation eligibility for graph chunks and their parent documents.
``personal_reading`` (the Personal-Reading Lane fourth rights state) is
owner-readable on privileged paths but must **never** surface as a citable
source in synthesis, attribution, or public-graph provenance — the same §9.0
posture as retrieval and serve gates, expressed here for GATE-CONFORMANCE.

This module is imported by ``check_conformance.py``; it does not touch live DB
rows. Runtime paths continue to enforce via ``retrieval_gate``,
``NON_ATTRIBUTABLE_CONTENT_CLASSES``, and ``PUBLIC_GRAPH_CONTENT_CLASSES``;
this gate proves those vocabularies stay aligned with the non-citable policy.
"""

from __future__ import annotations

from substrate.ad_inventory.attribution import PUBLIC_GRAPH_CONTENT_CLASSES
from substrate.collective_graph.eligibility import NON_ATTRIBUTABLE_CONTENT_CLASSES
from substrate.constants import (
    PERSONAL_READING_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)
from substrate.graph.retrieval_gate import (
    PERSONAL_ONLY_CONTENT_CLASSES,
    _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES,
)

# Content classes whose chunks/documents must never be cited as public-graph
# evidence. Today only personal_reading; extend here when a new owner-only lane
# lands (never fold into RESTRICTED_CONTENT_CLASSES — opposite monetization).
NON_CITABLE_CONTENT_CLASSES: frozenset[str] = frozenset({
    PERSONAL_READING_CONTENT_CLASS,
})


def is_chunk_citable(content_class: str | None) -> bool:
    """True iff a chunk grounded on ``content_class`` may appear in public
    synthesis provenance / attribution-eligible citation sets.

    Deny-by-default: NULL/unknown is not citable (fail-closed, SR-07 posture).
    """
    if content_class is None:
        return False
    return content_class not in NON_CITABLE_CONTENT_CLASSES


def is_document_citable(content_class: str | None) -> bool:
    """Alias for document-level checks — citation policy is per document class."""
    return is_chunk_citable(content_class)


def provenance_policy_errors() -> list[str]:
    """Cross-check that substrate gate vocabularies agree on non-citable lanes.

    Returns human-readable divergence messages (empty = policy aligned).
    """
    errors: list[str] = []
    pr = PERSONAL_READING_CONTENT_CLASS

    if pr != "personal_reading":
        errors.append(
            f"PERSONAL_READING_CONTENT_CLASS={pr!r}; expected 'personal_reading'."
        )

    if pr not in NON_CITABLE_CONTENT_CLASSES:
        errors.append(
            f"{pr!r} must be in NON_CITABLE_CONTENT_CLASSES "
            f"(got {sorted(NON_CITABLE_CONTENT_CLASSES)!r})."
        )

    if is_chunk_citable(pr) or is_document_citable(pr):
        errors.append(
            f"{pr!r} must be non-citable: is_chunk_citable and is_document_citable "
            "must both be False."
        )

    if pr not in NON_ATTRIBUTABLE_CONTENT_CLASSES:
        errors.append(
            f"{pr!r} must be in collective_graph NON_ATTRIBUTABLE_CONTENT_CLASSES."
        )

    if pr in PUBLIC_GRAPH_CONTENT_CLASSES:
        errors.append(
            f"{pr!r} must NOT be in PUBLIC_GRAPH_CONTENT_CLASSES "
            "(public-graph chunks are citable for monetization)."
        )

    if pr not in PERSONAL_ONLY_CONTENT_CLASSES:
        errors.append(
            f"{pr!r} must be in retrieval_gate PERSONAL_ONLY_CONTENT_CLASSES."
        )

    if pr not in _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES:
        errors.append(
            f"{pr!r} must be in retrieval_gate "
            "_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES."
        )

    if pr in SERVABLE_CONTENT_CLASSES:
        errors.append(
            f"{pr!r} must NOT be in SERVABLE_CONTENT_CLASSES "
            "(owner-readable ≠ publicly servable)."
        )

    return errors