"""The research-only quotation policy — the one negotiable term on a
derivable-only source (books/publishers SPR-1).

``research_only`` withholds the body from everyone. What a publisher actually
negotiates is not *whether* the body is served (it never is) but how much of it
may appear verbatim inside the agent's research artifact as a quotation. That
number is the knob the deal turns, so it is a policy value carried per document,
not a constant compiled into the gate.

Three things keep the knob from becoming a hole:

1. **Deny by default.** An absent, malformed, or unrecognised policy resolves to
   :data:`DERIVED_ONLY`, a cap of zero characters. A source whose terms were
   never recorded quotes nothing. This is the same posture the surrounding rights
   substrate takes everywhere else: the absence of a permission is a denial.

2. **A hard ceiling the policy cannot raise.** Every resolved cap is clamped to
   ``SERVE_SNIPPET_MAX_CHARS`` — the bound the gated-book path already serves
   under, the *Authors Guild v. Google* (2d Cir. 2015) bounded-excerpt regime. A
   deal may tighten the cap and may not loosen it past a bound the platform
   already defends. So no per-document value, however it was written, can turn a
   quotation into the body; :func:`apply_quotation_policy` cannot return more
   than 500 characters of any work.

3. **Quotation is not serving.** A cap above zero permits a bounded excerpt
   inside a cited claim. It never permits ``full_text``: the serve gate withholds
   the body for this class unconditionally, and this module is only consulted for
   what may ride alongside a citation.

Pure logic and decision tables, no I/O — the convention the rest of
``substrate.rights`` follows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from substrate.constants import SERVE_SNIPPET_MAX_CHARS

# The metadata keys a deal is recorded under on ``documents.metadata``. The tier
# name is the ordinary case (a deal picks a shape off the rate card); the
# explicit character count covers a bespoke term that no named tier matches.
QUOTATION_TIER_METADATA_KEY: Final[str] = "research_only_quotation_tier"
QUOTATION_CHARS_METADATA_KEY: Final[str] = "research_only_max_quote_chars"

# The named deal shapes. DERIVED_ONLY is the default and the only one that needs
# no negotiation — it is what a publisher gets by saying nothing at all.
DERIVED_ONLY: Final[str] = "derived_only"
BRIEF_QUOTATION: Final[str] = "brief_quotation"
SNIPPET_PARITY: Final[str] = "snippet_parity"

#: tier name -> the verbatim characters that tier permits inside a cited claim.
#: SNIPPET_PARITY is deliberately pinned to the existing gated-book bound rather
#: than a number of its own: the most permissive research-only deal is exactly as
#: permissive as the fair-use excerpt the platform already serves, never more.
QUOTATION_TIERS: Final[dict[str, int]] = {
    DERIVED_ONLY: 0,
    BRIEF_QUOTATION: 200,
    SNIPPET_PARITY: SERVE_SNIPPET_MAX_CHARS,
}

#: No resolved policy may exceed this, whatever a document's metadata claims.
QUOTATION_CEILING_CHARS: Final[int] = SERVE_SNIPPET_MAX_CHARS


@dataclass(frozen=True)
class QuotationPolicy:
    """How much of a ``research_only`` work may be quoted verbatim.

    ``tier`` names the deal shape the cap came from, so a rendered artifact can
    say which term produced the quotation it is showing. ``max_quote_chars`` is
    already clamped to :data:`QUOTATION_CEILING_CHARS` by the resolver — a
    consumer may use it directly without re-checking the bound.
    """

    tier: str
    max_quote_chars: int

    @property
    def quotation_permitted(self) -> bool:
        return self.max_quote_chars > 0


#: The policy every unrecorded, malformed, or unrecognised source resolves to.
DEFAULT_QUOTATION_POLICY: Final[QuotationPolicy] = QuotationPolicy(
    tier=DERIVED_ONLY, max_quote_chars=QUOTATION_TIERS[DERIVED_ONLY]
)


def _clamp(chars: int) -> int:
    return max(0, min(int(chars), QUOTATION_CEILING_CHARS))


def resolve_quotation_policy(metadata: Any) -> QuotationPolicy:
    """Resolve the quotation policy recorded on a document's ``metadata``.

    ``metadata`` is whatever the documents row carries — a dict, a JSON string,
    or ``None``. Anything that is not a mapping carrying a recognised key yields
    :data:`DEFAULT_QUOTATION_POLICY`.

    An explicit character count wins over a tier name, because a bespoke term is
    by definition the one that was negotiated for this work; the tier name then
    still rides along on the result as the shape the deal started from. A count
    that is not an integer, or is negative, is not a term — it is a mistake, and a
    mistake resolves to zero rather than to the tier's number, so a typo cannot
    silently widen a quotation. A tier name nobody recognises is likewise zero:
    the deal it refers to is not one this build knows how to honour.

    Booleans are rejected explicitly. ``isinstance(True, int)`` is true in
    Python, so ``{"research_only_max_quote_chars": True}`` would otherwise resolve
    to a one-character quotation — a nonsense term arriving from a JSON blob.
    """
    parsed = _as_mapping(metadata)
    if parsed is None:
        return DEFAULT_QUOTATION_POLICY

    raw_tier = parsed.get(QUOTATION_TIER_METADATA_KEY)
    tier = raw_tier if isinstance(raw_tier, str) and raw_tier in QUOTATION_TIERS else DERIVED_ONLY

    if QUOTATION_CHARS_METADATA_KEY in parsed:
        raw_chars = parsed[QUOTATION_CHARS_METADATA_KEY]
        if isinstance(raw_chars, bool) or not isinstance(raw_chars, int):
            return QuotationPolicy(tier=tier, max_quote_chars=0)
        return QuotationPolicy(tier=tier, max_quote_chars=_clamp(raw_chars))

    return QuotationPolicy(tier=tier, max_quote_chars=_clamp(QUOTATION_TIERS[tier]))


def _as_mapping(metadata: Any) -> dict[str, Any] | None:
    """Coerce a metadata blob to a mapping, or ``None`` when it is not one.

    Mirrors ``substrate.books.serve_guard._rights_context_from_metadata``: a
    corrupt blob is not a permission, so it reads as absent rather than raising
    into a serve path.
    """
    if isinstance(metadata, dict):
        return metadata
    if isinstance(metadata, (str, bytes, bytearray)):
        import json

        try:
            decoded = json.loads(metadata)
        except (ValueError, TypeError):
            return None
        return decoded if isinstance(decoded, dict) else None
    return None


def apply_quotation_policy(
    raw_text: str | None, policy: QuotationPolicy
) -> str | None:
    """Cut the quotation a ``research_only`` source permits, or ``None``.

    Returns ``None`` — not an empty string — when the policy permits nothing or
    there is no body, so a caller that renders "quote or nothing" does not print
    empty quotation marks around a work it may not quote.

    The returned text is never longer than ``policy.max_quote_chars``, which the
    resolver has already clamped to :data:`QUOTATION_CEILING_CHARS`. An excerpt
    that was cut carries an ellipsis so the reader can see it is an excerpt,
    matching ``substrate.books.serve._snippet``.
    """
    if not raw_text or not policy.quotation_permitted:
        return None
    if len(raw_text) <= policy.max_quote_chars:
        return raw_text
    return raw_text[: policy.max_quote_chars].rstrip() + "…"


__all__ = [
    "BRIEF_QUOTATION",
    "DEFAULT_QUOTATION_POLICY",
    "DERIVED_ONLY",
    "QUOTATION_CEILING_CHARS",
    "QUOTATION_CHARS_METADATA_KEY",
    "QUOTATION_TIERS",
    "QUOTATION_TIER_METADATA_KEY",
    "QuotationPolicy",
    "SNIPPET_PARITY",
    "apply_quotation_policy",
    "resolve_quotation_policy",
]
