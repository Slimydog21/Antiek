"""Source-agnostic license → servable-class core, shared across acquisition.

THE LOAD-BEARING INVARIANT (hard-to-vary): *no item is ever served on a
license Antiek does not actually hold.* "Free to read" is NEVER conflated
with "free to redistribute." Unknown / unmatched / missing license → GATED,
never servable. The unknown-fallback is the deny-by-default safety branch.

This module holds the GENERIC primitives that every source-specific license
table (arXiv, open-access aggregators, …) shares: the resolution dataclass,
the row type, the substring first-match-wins matching engine, the canonical
Creative-Commons rows, and the audit-string composer. The CC-family
semantics are a LEGAL determination — they must have exactly ONE home so two
sprints can't drift into divergent verdicts on the same license. Each source
module composes its own table as ``(source_specific_rows,) + CC_LICENSE_ROWS``
and resolves against it via ``resolve_against_table``.

This module is PURE — no I/O, no DB, no network — so the mapping is unit
-testable in isolation and cheap to audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from substrate.constants import (
    GATED_DEFAULT_CONTENT_CLASS,
    SOURCE_DECLARED_OPEN_CONTENT_CLASS,
)

# ``SERVABLE_CONTENT_CLASS`` ("opt_in_licensed") means EXACTLY "a publisher
# claimed this work via the §9.10 opt-in flow" — it is RESERVED for genuine
# publisher opt-ins and is kept here for any code that genuinely needs that
# class. The source-declared CC licenses below NO LONGER route through it
# (2026-05-29 remap): stamping a CC-BY/CC-BY-SA work as opt_in_licensed was a
# false provenance (the open license was declared at the source, not claimed
# by a publisher). Corrected routing:
#   * CC-BY / CC-BY-SA   -> ``source_declared_open`` (servable, attribution /
#                           share-alike obligations remain; NOT public domain,
#                           NOT a §9.10 opt-in).
#   * CC0                -> ``public_domain`` (a public-domain dedication: no
#                           rights holder, no attribution obligation).
#   * CC Public-Domain Mark -> ``public_domain`` (unchanged; see CC_PDM_ROW).
SERVABLE_CONTENT_CLASS = "opt_in_licensed"
PUBLIC_DOMAIN_CONTENT_CLASS = "public_domain"
# ``SOURCE_DECLARED_OPEN_CONTENT_CLASS`` is imported from substrate.constants
# (above) rather than re-literalled here — the source-declared-open class has
# exactly one string home, and the CC-BY/CC-BY-SA rows below reference the
# imported name.


@dataclass(frozen=True)
class LicenseResolution:
    """Result of resolving a license URI. ``content_class`` is always a
    member of the substrate's valid book content classes; ``gated`` items
    resolve to ``GATED_DEFAULT_CONTENT_CLASS``."""

    content_class: str
    redistributable: bool
    license_name: str
    rationale: str
    # The URI we resolved against (echoed back for the audit string).
    license_uri: Optional[str]


@dataclass(frozen=True)
class LicenseRow:
    """One row of a mapping table.

    ``match`` is matched case-insensitively as a SUBSTRING of the license
    URI, so ``creativecommons.org/licenses/by/4.0`` matches both the http
    and https forms and the trailing-slash variants sources emit across
    their license-element history. Rows are evaluated top-to-bottom; the
    FIRST match wins, so the more-specific NC/SA/ND fragments must precede
    the bare ``/by/`` row (otherwise a CC-BY-NC URI would match ``/by/`` and
    be misclassified as servable). Order is the safety contract here.
    """

    match: str
    content_class: str
    redistributable: bool
    license_name: str
    rationale: str


# ---------------------------------------------------------------------------
# Canonical Creative-Commons rows — the ONE legal home for CC semantics.
# Read top-to-bottom; first match wins. More-restrictive CC variants (NC /
# ND) come BEFORE the permissive ones so a CC-BY-NC URI is never mis-matched
# by the bare /by/ row. Any source table prepends its own rows and appends
# this tuple, preserving this internal NC/ND-before-BY ordering.
# ---------------------------------------------------------------------------

CC_LICENSE_ROWS: tuple[LicenseRow, ...] = (
    # CC-BY-NC* — JUDGMENT CALL (documented in the SPR-02 handoff). NC
    # licenses forbid commercial reuse. Antiek serves full text behind a
    # per-second ad border with a 70% payout — an ad-funded, commercial
    # context. So NC does NOT cleanly grant Antiek's redistribution → GATED.
    # Reverse-if: Antiek adds a non-commercial serving mode, or makes a
    # per-license commercial-use determination, this row should flip.
    LicenseRow(
        match="creativecommons.org/licenses/by-nc",
        content_class=GATED_DEFAULT_CONTENT_CLASS,
        redistributable=False,
        license_name="CC BY-NC (non-commercial)",
        rationale=(
            "NC forbids commercial reuse; Antiek's ad-funded serving is "
            "commercial -> gated. Reverse if Antiek adds a non-commercial "
            "serving mode or a per-license commercial-use determination."
        ),
    ),
    # CC *-ND (no-derivatives). Chunking + reflowing into the reader is
    # arguably a derivative presentation; conservative stance is gated.
    LicenseRow(
        match="creativecommons.org/licenses/by-nd",
        content_class=GATED_DEFAULT_CONTENT_CLASS,
        redistributable=False,
        license_name="CC BY-ND (no-derivatives)",
        rationale=(
            "ND bars derivative presentation; Antiek's chunked/reflowed "
            "serving is arguably derivative -> gated (conservative)."
        ),
    ),
    # CC-BY-SA (share-alike). Redistributable; SA copyleft is a downstream
    # obligation Antiek inherits, not a bar to serving. NOT a §9.10 publisher
    # opt-in — the open license was declared at the source (2026-05-29 remap).
    LicenseRow(
        match="creativecommons.org/licenses/by-sa",
        content_class=SOURCE_DECLARED_OPEN_CONTENT_CLASS,
        redistributable=True,
        license_name="CC BY-SA",
        rationale=(
            "CC BY-SA permits redistribution (incl. commercial) with "
            "attribution + share-alike -> servable as source_declared_open "
            "(source-declared open license, not a §9.10 publisher opt-in)."
        ),
    ),
    # CC-BY (attribution only) — 4.0 and 3.0 both match this fragment. NOT a
    # §9.10 publisher opt-in — the open license was declared at the source.
    LicenseRow(
        match="creativecommons.org/licenses/by",
        content_class=SOURCE_DECLARED_OPEN_CONTENT_CLASS,
        redistributable=True,
        license_name="CC BY",
        rationale=(
            "CC BY permits redistribution (incl. commercial) with "
            "attribution -> servable as source_declared_open "
            "(source-declared open license, not a §9.10 publisher opt-in)."
        ),
    ),
    # CC0 / public-domain dedication. CC0 waives ALL rights and dedicates the
    # work to the public domain — there is no rights holder and no attribution
    # obligation, so the truthful class is public_domain (2026-05-29 remap;
    # previously mis-routed to opt_in_licensed).
    LicenseRow(
        match="creativecommons.org/publicdomain/zero",
        content_class=PUBLIC_DOMAIN_CONTENT_CLASS,
        redistributable=True,
        license_name="CC0 1.0 (public-domain dedication)",
        rationale=(
            "CC0 waives all rights -> public_domain (a public-domain "
            "dedication: no rights holder, no attribution obligation)."
        ),
    ),
)


# The CC Public-Domain Mark (works whose copyright has expired worldwide).
# Distinct from CC0: PDM marks an already-public-domain work rather than
# dedicating one, so it routes through public_domain, not opt_in_licensed.
# Its fragment (publicdomain/mark) does not collide with publicdomain/zero,
# so placement relative to the CC rows is not order-sensitive.
CC_PDM_ROW: LicenseRow = LicenseRow(
    match="creativecommons.org/publicdomain/mark",
    content_class=PUBLIC_DOMAIN_CONTENT_CLASS,
    redistributable=True,
    license_name="CC Public Domain Mark 1.0",
    rationale=(
        "PDM marks a worldwide-public-domain work -> freely redistributable "
        "-> servable as public_domain."
    ),
)


def resolve_against_table(
    license_uri: Optional[str], table: tuple[LicenseRow, ...]
) -> LicenseResolution:
    """Map a license URI to a servable-class resolution against ``table``.

    Deny-by-default: a ``None`` / empty / unmatched URI resolves to
    ``GATED_DEFAULT_CONTENT_CLASS`` with ``redistributable=False``. This is
    the load-bearing safety branch — an unknown license is NEVER guessed
    servable. Rows are tried top-to-bottom; the first substring match wins.
    """
    if not license_uri or not license_uri.strip():
        return LicenseResolution(
            content_class=GATED_DEFAULT_CONTENT_CLASS,
            redistributable=False,
            license_name="(no license declared)",
            rationale="no license declared -> gated by default.",
            license_uri=license_uri,
        )

    uri_l = license_uri.strip().lower()
    for row in table:
        if row.match in uri_l:
            return LicenseResolution(
                content_class=row.content_class,
                redistributable=row.redistributable,
                license_name=row.license_name,
                rationale=row.rationale,
                license_uri=license_uri,
            )

    # Unmatched URI (incl. "all rights reserved" and any URI not in the
    # table). The fallback IS the invariant: unknown -> gated, never served.
    return LicenseResolution(
        content_class=GATED_DEFAULT_CONTENT_CLASS,
        redistributable=False,
        license_name="(unrecognised license)",
        rationale=(
            "license URI not in the servable table (unknown / "
            "all-rights-reserved) -> gated by default."
        ),
        license_uri=license_uri,
    )


def license_basis_string(resolution: LicenseResolution) -> str:
    """Compose the audit ``license_basis`` string stamped on the asset.

    For a servable item this names the license + its URI; for a gated item
    it states WHY it's gated. Either way the substrate row carries a
    self-explaining provenance string a reviewer can read without re-running
    the mapping.
    """
    uri = resolution.license_uri
    if resolution.redistributable:
        return f"{resolution.license_name} ({uri})"
    # Gated: lead with the why.
    if uri:
        return f"GATED: {resolution.license_name} ({uri}) -- {resolution.rationale}"
    return f"GATED: {resolution.rationale}"
