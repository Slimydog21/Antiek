"""Rights-tier resolution — the one source of truth for arXiv tiering.

Sibling to ``substrate.books`` (the servability projection that derives a
presentation status from ``content_class``); this package holds the tier
resolver that maps a license URI to a ``RightsTier`` and the predicates that
ride on the tier (body-serving guard, ad-eligibility). Pure logic + decision
tables, no I/O — the same convention as ``substrate.legal_gate`` and
``substrate.books.servability``.

Public surface:
    - RightsTier            (re-exported from substrate.schemas.documents)
    - resolve_tier          authoritative license_uri -> RightsTier
    - body_servable         predicate: may a full body be emitted from storage
                            on the current commercial surface? (== tier is T1)
    - guard_servable_body   enforcing wrapper: raises on a non-T1 body (T2 the
                            NC non-commercial-display tier, or T3 link-back-only)
    - T3BodyServeError       raised by the guard
    - ads_allowed           predicate: may ads run? (== tier is T1)
"""

from __future__ import annotations

from substrate.rights.ad_eligibility import ads_allowed
from substrate.rights.arxiv_tiers import (
    RightsTier,
    T3BodyServeError,
    body_servable,
    guard_servable_body,
    resolve_tier,
)

__all__ = [
    "RightsTier",
    "resolve_tier",
    "body_servable",
    "guard_servable_body",
    "T3BodyServeError",
    "ads_allowed",
]
