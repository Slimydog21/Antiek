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
    PERSONAL_READABLE_CONTENT_CLASSES,
    PERSONAL_READING_CONTENT_CLASS,
    RESEARCH_ONLY_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)
from substrate.graph.retrieval_gate import (
    _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES,
    PERSONAL_ONLY_CONTENT_CLASSES,
    RESEARCH_ONLY_CONTENT_CLASSES,
)

# Content classes whose chunks/documents must never be cited as public-graph
# evidence. Today only personal_reading; extend here when a new owner-only lane
# lands (never fold into RESTRICTED_CONTENT_CLASSES — opposite monetization).
# NOTE on research_only (books/publishers SPR-1): it is deliberately ABSENT here,
# and that absence is load-bearing rather than an oversight. A derivable-only work
# is ingested precisely so an agent can derive claims from it, and a derived claim
# that cannot name its source is an assertion, not research. So research_only IS
# citable; what the citation carries is identity — title, ip_holder, locator —
# while every body path withholds the text independently. The
# ``provenance_policy_errors`` checks below pin both halves of that so a future
# edit cannot quietly make it non-citable (which would hollow out the product) or
# quietly make its body citable-with-text (which would leak it).
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

    errors.extend(_research_only_policy_errors())
    return errors


def _research_only_policy_errors() -> list[str]:
    """The derivable-only lane's half of the conformance check.

    research_only is the one withheld class that must stay CITABLE, so it is
    checked from both sides: citable and non-attributable, retrievable only on a
    privileged path and servable on none.
    """
    errors: list[str] = []
    ro = RESEARCH_ONLY_CONTENT_CLASS

    if ro != "research_only":
        errors.append(
            f"RESEARCH_ONLY_CONTENT_CLASS={ro!r}; expected 'research_only'."
        )

    if ro in NON_CITABLE_CONTENT_CLASSES:
        errors.append(
            f"{ro!r} must NOT be in NON_CITABLE_CONTENT_CLASSES — a derived claim "
            "must be able to name the source it was derived from."
        )

    if not (is_chunk_citable(ro) and is_document_citable(ro)):
        errors.append(
            f"{ro!r} must be citable: is_chunk_citable and is_document_citable "
            "must both be True."
        )

    if ro in SERVABLE_CONTENT_CLASSES:
        errors.append(
            f"{ro!r} must NOT be in SERVABLE_CONTENT_CLASSES (derivable ≠ servable)."
        )

    if ro in PERSONAL_READABLE_CONTENT_CLASSES:
        errors.append(
            f"{ro!r} must NOT be in PERSONAL_READABLE_CONTENT_CLASSES — it is "
            "never-owner-readable, the inverse of personal_reading."
        )

    if ro in PERSONAL_ONLY_CONTENT_CLASSES:
        errors.append(
            f"{ro!r} must NOT be in retrieval_gate PERSONAL_ONLY_CONTENT_CLASSES "
            "(that set is granted to a matching owner_user_id on the privileged "
            "branch; research_only must never receive that grant)."
        )

    if ro not in RESEARCH_ONLY_CONTENT_CLASSES:
        errors.append(
            f"{ro!r} must be in retrieval_gate RESEARCH_ONLY_CONTENT_CLASSES."
        )

    if ro not in _NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES:
        errors.append(
            f"{ro!r} must be in retrieval_gate "
            "_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES."
        )

    if ro not in NON_ATTRIBUTABLE_CONTENT_CLASSES:
        errors.append(
            f"{ro!r} must be in collective_graph NON_ATTRIBUTABLE_CONTENT_CLASSES "
            "(the ingestion fee is the consideration, not a revenue share)."
        )

    if ro in PUBLIC_GRAPH_CONTENT_CLASSES:
        errors.append(
            f"{ro!r} must NOT be in PUBLIC_GRAPH_CONTENT_CLASSES."
        )

    return errors