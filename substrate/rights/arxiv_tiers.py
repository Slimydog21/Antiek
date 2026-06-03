"""Authoritative arXiv rights-tier resolver — THE one source of truth
(SPR-02 M1).

What this module owns
---------------------
A pure, deny-by-default function ``resolve_tier(license_uri) -> RightsTier``
that partitions every arXiv ``<license>`` value into exactly one of three
rights tiers, and a serving-boundary guard (``assert_no_t3_body`` /
``guard_servable_body``) that is mechanically incapable of emitting a T3 body
out of Antiek storage.

The taxonomy (closed, exhaustive, deny-by-default floor):

    T1  redistributable open    — CC0 / CC-BY / CC-BY-SA. Antiek may host AND
                                   commercially exploit (ad-funded serving,
                                   payouts). The only tier ads may run on, and
                                   the only tier whose body may be EMITTED from
                                   Antiek storage on the current commercial
                                   surface.
    T2  non-commercial          — CC-BY-NC*. Non-commercial DISPLAY only. On the
                                   current ad-funded (commercial) surface a T2
                                   body is NOT body-servable: the canonical
                                   resolver ``acquisition.licenses_core`` already
                                   gates CC-BY-NC (``redistributable=False``,
                                   "Antiek's ad-funded serving is commercial"),
                                   so the body-serve guard raises on a T2 body
                                   here. A genuine non-commercial serving mode +
                                   §9.0/counsel sign-off is the future state that
                                   would promote T2 to body-servable (see
                                   docs/decisions/arxiv-t2-noncommercial-serving.md).
    T3  default / unknown / none — the arXiv-default non-exclusive-distribution
                                   license (the MAJORITY of the corpus),
                                   all-rights-reserved, any unrecognised URI,
                                   AND an absent / empty license. Link-back only;
                                   NEVER rehosted from Antiek storage.

Why a wrong promotion is the cardinal sin (honesty bar 1)
---------------------------------------------------------
A wrong T3 -> T1 promotion rehosts + monetizes a paper Antiek holds no
redistribution right to — a redistribution violation (the *Hachette v.
Internet Archive* / *Bartz v. Anthropic* liability the §9.0 gate exists to
avoid). A wrong T1 -> T3 demotion merely leaves money on the table. The two
errors are NOT symmetric, so every ambiguous input biases to T3.

How the tier is decided — structured signal, never a display name (rigor bar)
-----------------------------------------------------------------------------
The verdict is DERIVED from the canonical license resolver
(``acquisition.licenses_core`` via ``acquisition.arxiv.licenses.resolve_license``)
— the ONE legal home for Creative-Commons semantics — so the tier table cannot
disagree with the servable-class mapping that the serving layer enforces:

  * ``resolution.redistributable is True``  -> **T1** (CC0 -> public_domain,
    CC-BY / CC-BY-SA -> source_declared_open). Redistributability is a
    structured boolean the legal table sets per row, not a parsed string.
  * non-redistributable AND the resolved license URI is a CC NonCommercial
    license -> **T2**. The NC determination keys off the canonical structured
    URI fragment (``creativecommons.org/licenses/by-nc``) — the SAME fragment
    the legal table's CC-BY-NC row matches — NOT the human ``license_name``
    display string. The fragment is a license-identity token in the URI, which
    is structured license data; the display name is not.
  * everything else non-redistributable -> **T3** (arXiv-default,
    all-rights-reserved, ND, an unrecognised URI, and — the load-bearing case —
    an absent / empty URI). This is the deny-by-default floor.

Because the split runs OFF the resolver, the tiers inherit the resolver's
NC/ND-before-BY first-match safety ordering for free: a ``by-nc-sa`` or
``by-nc-nd`` URI resolves non-redistributable (never matches the bare ``/by/``
row), so it lands in T2/T3, never T1.

CC version / port ambiguity (honesty bar 1)
-------------------------------------------
The canonical fragments are version- and port-agnostic by construction: they
match the license *family* path segment (``/licenses/by-nc``,
``/publicdomain/zero``), so 4.0, 3.0, 2.5, and any jurisdiction port
(``/by/3.0/us/``) all resolve to the same family. This is deliberate: the
commercial-redistribution right does not differ across CC versions or ports
for our purposes (all CC-BY versions permit commercial redistribution with
attribution; all CC-BY-NC versions forbid commercial use). A version we have
never seen still resolves — to T3 if its family fragment is unrecognised,
never optimistically to T1.

One source of truth (defensibility bar 5)
------------------------------------------
``substrate.schemas.documents.classify_tier`` is RECONCILED to delegate here
(it no longer carries its own NC/redistributable branch). Serving (T3-body
guard below), ad-eligibility (``substrate.rights.ad_eligibility``), and any
future payout gate all cite THIS module. Two callers can never drift into
divergent tier verdicts on the same license.
"""

from __future__ import annotations

from substrate.constants import SERVABLE_CONTENT_CLASSES
from substrate.schemas.documents import RightsTier

# The canonical Creative-Commons NonCommercial license-identity fragment. This
# is the SAME token the legal table's CC-BY-NC row matches
# (``acquisition.licenses_core.CC_LICENSE_ROWS``); it is duplicated here as a
# single named constant only so the NC determination is a structured URI match
# rather than a parse of the human ``license_name``. It is version- and
# port-agnostic: ``by-nc``, ``by-nc-sa``, and ``by-nc-nd`` all contain it, and
# all CC versions/ports of those families do too. Lowercased; the resolver
# lowercases the URI before matching.
_CC_NON_COMMERCIAL_FRAGMENT: str = "creativecommons.org/licenses/by-nc"


def resolve_tier(license_uri: str | None) -> RightsTier:
    """Map an arXiv ``<license>`` URI to its authoritative rights tier.

    Pure and deny-by-default: a ``None`` / empty / whitespace / unrecognised
    URI resolves to ``RightsTier.T3_DEFAULT_UNKNOWN`` — an unknown license is
    NEVER guessed into a redistributable or even a display-only tier. T3 is the
    only tier reachable without a positive, structured signal.

    The verdict is derived from the canonical license resolver so the tier can
    never disagree with the servable-class mapping the serving layer enforces.
    """
    # Lazy import (mirrors the prior ``classify_tier`` note): ``substrate``
    # sits below ``acquisition`` in the import stack, and
    # ``acquisition.arxiv.__init__`` re-exports the harvester which imports
    # ``substrate.schemas.documents``. Importing ``acquisition.arxiv.licenses``
    # at module top would invert the layering and risk a cycle. The legal
    # resolver stays the one home for CC semantics; we only consume it.
    from acquisition.arxiv.licenses import resolve_license

    resolution = resolve_license(license_uri)

    # T1: a structured redistributable resolution. The legal table sets
    # ``redistributable=True`` ONLY for CC0 / CC-BY / CC-BY-SA; everything else
    # (incl. every NC and ND variant, arXiv-default, unknown, absent) is False.
    if resolution.redistributable:
        return RightsTier.T1_REDISTRIBUTABLE

    # T2: non-redistributable AND a CC NonCommercial license. Keyed off the
    # canonical structured URI fragment on the resolution's echoed-back URI,
    # not the human display name. ``license_uri`` is the input we resolved
    # against; guard against None before lowercasing.
    uri = resolution.license_uri
    if uri and _CC_NON_COMMERCIAL_FRAGMENT in uri.strip().lower():
        return RightsTier.T2_NON_COMMERCIAL

    # T3: the deny-by-default floor — arXiv-default, all-rights-reserved, ND,
    # any unrecognised URI, and the absent/empty case.
    return RightsTier.T3_DEFAULT_UNKNOWN


# ---------------------------------------------------------------------------
# Serving-boundary guard — mechanically incapable of emitting a T3 body.
# ---------------------------------------------------------------------------
#
# The serving chokepoint (``substrate.books.serve.serve_full_text``) gates on
# ``documents.content_class`` against ``SERVABLE_CONTENT_CLASSES``. This guard
# is the tier-side counterpart: it relates a RightsTier to whether a FULL BODY
# may be EMITTED/DISPLAYED from Antiek storage on the CURRENT (commercial)
# surface, and fails CLOSED. It is the negative the tests assert against — "a
# T3 (or T2) body cannot be served here."
#
# The question this guard owns: "may a body leave storage to be displayed on
# Antiek's current ad-funded surface?" That ceiling is {T1} ONLY. T1
# (CC0/CC-BY/CC-BY-SA) may be redistributed-and-monetized, so its body may be
# emitted. T2 (CC-BY-NC*) is NON-COMMERCIAL-DISPLAY-ONLY and is NOT
# body-servable here: the canonical resolver
# ``acquisition.licenses_core.CC_LICENSE_ROWS`` resolves CC-BY-NC to
# ``redistributable=False`` + gated, with the binding rationale "NC forbids
# commercial reuse; Antiek's ad-funded serving is commercial -> gated." A
# commercial, ad-funded platform may not emit an NC body, so this guard raises
# on a T2 body — staying single-source-of-truth with that resolver (an auditor
# gets the SAME deny from both). T3 (link-back-only) and any unknown/garbage
# tier are likewise impossible to emit, deny-by-default. The {T1,T2}
# "non-commercial display" world is exactly the resolver's "Reverse-if" future
# (a non-commercial serving mode that does NOT yet exist) plus §9.0/counsel
# sign-off — NOT today's default; see
# docs/decisions/arxiv-t2-noncommercial-serving.md.
#
# This guard does NOT itself decide the commercial/ad question — that is a
# SEPARATE, identically-{T1} gate in ``substrate.rights.ad_eligibility``. Today
# the two ceilings coincide at {T1}; the ad gate stays distinct because the
# *future* gated→permissive flip ({T1}→{T1,T2}) would split them (a T2 body
# becomes display-servable while ads stay T1-only).


# Tiers whose FULL BODY Antiek may emit from its own storage on the current
# (commercial) surface. {T1} ONLY: T1 (CC0/CC-BY/CC-BY-SA) is redistributable
# open. T2 (CC-BY-NC*) is non-commercial-display-only and is NOT body-servable
# here — emitting an NC body from a commercial ad-funded platform contradicts
# ``acquisition.licenses_core``'s binding CC-BY-NC gate; the guard raises on a
# T2 body. T3 (arXiv-default/unknown) and any unrecognised tier are the
# deny-by-default non-grant. Kept as ONE named frozenset so the future flip to
# ``{T1, T2}`` — contingent on BOTH a genuine non-commercial serving mode (the
# resolver's "Reverse-if") AND §9.0/counsel sign-off — is a one-line, one-place
# change. See docs/decisions/arxiv-t2-noncommercial-serving.md.
_BODY_SERVABLE_TIERS: frozenset[RightsTier] = frozenset(
    {RightsTier.T1_REDISTRIBUTABLE}
)


def body_servable(tier: RightsTier) -> bool:
    """Whether a FULL body may be emitted/displayed from Antiek storage for
    ``tier`` on the current (commercial) surface.

    True for T1 (redistributable open) ONLY. T2 (CC-BY-NC*: non-commercial
    display only) is NOT body-servable here — a commercial ad-funded platform
    may not emit an NC body, coherent with ``acquisition.licenses_core`` gating
    CC-BY-NC. T3 (link-back-only) and any unrecognised tier are the
    deny-by-default zone. This is the body-EMISSION ceiling; the ad gate is a
    separate, identically-{T1} predicate
    (``substrate.rights.ad_eligibility.ads_allowed``). Pure predicate; the
    enforcing wrapper is :func:`guard_servable_body`.
    """
    return tier in _BODY_SERVABLE_TIERS


class T3BodyServeError(RuntimeError):
    """Raised when a caller attempts to emit a body for a non-body-servable
    tier on the current commercial surface (T2 CC-BY-NC non-commercial-display,
    T3 link-back-only, or any unknown/corrupt tier). The serving layer is meant
    to NEVER reach this — the guard is the mechanical backstop that turns a
    would-be redistribution / NC-commercial-use violation into a loud failure
    instead of a silently-leaked body. (The name retains the ``T3`` prefix for
    continuity; it covers every non-{T1} tier.)"""


def guard_servable_body(tier: RightsTier, body: str | None) -> str | None:
    """Pass ``body`` through iff ``tier`` may have its body emitted from Antiek
    storage; otherwise raise ``T3BodyServeError``.

    This is the mechanically-incapable-of-emitting-a-T3-body chokepoint: route
    every from-storage body emission through here and a T3 body cannot leave,
    by construction. Fails closed: an unrecognised tier value (which
    ``resolve_tier`` cannot produce, but a corrupt stored value might) is NOT
    in ``_BODY_SERVABLE_TIERS`` and therefore also raises.
    """
    if not body_servable(tier):
        raise T3BodyServeError(
            f"refusing to emit a full body for tier {tier!r}: only "
            f"{sorted(t.value for t in _BODY_SERVABLE_TIERS)} may have a body "
            f"emitted/displayed from Antiek storage on the current commercial "
            f"surface. T2 (CC-BY-NC) is non-commercial-display-only and may NOT "
            f"be emitted from a commercial ad-funded platform (coherent with "
            f"acquisition.licenses_core gating CC-BY-NC); T3 is link-back-only; "
            f"an unknown tier is denied by default. This is the deny-by-default "
            f"redistribution boundary (master-spec §9.0). The commercial/ad "
            f"gate is a separate, identically-T1 predicate "
            f"(substrate.rights.ad_eligibility)."
        )
    return body


# ---------------------------------------------------------------------------
# Drift guard — the tier resolver and the serving-class allowlist share intent.
# ---------------------------------------------------------------------------
#
# The body-servable tier set (T1) and the serving layer's content-class
# allowlist must stay coherent: the T1 redistributable resolutions
# (public_domain, source_declared_open) MUST both be members of
# SERVABLE_CONTENT_CLASSES, or a paper this resolver calls T1 would be denied
# at the serve gate (or vice versa). We assert the T1-producing classes are a
# subset of the serve allowlist at import time so a future edit that diverges
# the two fails loudly here rather than silently mis-gating a paper.
_T1_CONTENT_CLASSES: frozenset[str] = frozenset({"public_domain", "source_declared_open"})
assert set(SERVABLE_CONTENT_CLASSES) >= _T1_CONTENT_CLASSES, (
    "T1 redistributable content classes drifted out of SERVABLE_CONTENT_CLASSES: "
    f"{_T1_CONTENT_CLASSES!r} not all in {set(SERVABLE_CONTENT_CLASSES)!r}. "
    "A paper resolve_tier() calls T1 would then be denied at the serve gate. "
    "Fix substrate/constants.py and acquisition/licenses_core.py together."
)


__all__ = [
    "RightsTier",
    "resolve_tier",
    "body_servable",
    "guard_servable_body",
    "T3BodyServeError",
]
