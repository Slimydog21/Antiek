"""Open-access license URI → Antiek servable-class mapping.

Same load-bearing invariant as arXiv: an item renders full text publicly
ONLY if its license actually grants redistribution. OA aggregators
(OpenAlex / Unpaywall / PMC / DOAJ) emit a wider license vocabulary than
arXiv, but the Creative-Commons core is identical and lives in
``acquisition.licenses_core`` — there is exactly ONE legal home for CC
semantics. This module adds the OA-specific rows and the public-domain mark,
then resolves against the composed table.

The critical OA-specific hazard is **bronze OA**: an article free-to-read on
the publisher's site under NO open license. Bronze grants reading, not
redistribution — so it must gate. It usually arrives with NO license URI and
falls through to the deny-by-default branch; but some sources emit an
explicit bronze/closed signal (a literal ``"bronze"`` or a
``"publisher-specific"`` string), which we match to a gated row so the audit
trail names WHY it gated rather than logging a bare "unrecognised license".
"""

from __future__ import annotations

from typing import Optional

from substrate.constants import GATED_DEFAULT_CONTENT_CLASS

from acquisition.licenses_core import (  # noqa: F401
    CC_LICENSE_ROWS,
    CC_PDM_ROW,
    PUBLIC_DOMAIN_CONTENT_CLASS,
    SOURCE_DECLARED_OPEN_CONTENT_CLASS,
    LicenseResolution,
    LicenseRow,
    license_basis_string,
    resolve_against_table,
)

# --- OA-specific rows (beyond the shared CC family) ---

# Bronze OA: free-to-read on the publisher site, no open license. Some
# sources (Unpaywall's oa_status, OpenAlex's oa.oa_status) emit the literal
# "bronze"; map it to an explicit gated row so the basis string says why.
_BRONZE_ROW: LicenseRow = LicenseRow(
    match="bronze",
    content_class=GATED_DEFAULT_CONTENT_CLASS,
    redistributable=False,
    license_name="Bronze OA (free-to-read, no open license)",
    rationale=(
        "Bronze OA grants reading on the publisher site only; no "
        "redistribution license -> gated."
    ),
)

# Some adapters surface a coarse "publisher-specific"/"closed" license string
# when an article is free-to-read but carries proprietary publisher terms.
# Treat the same as bronze: reading is not a redistribution grant.
_PUBLISHER_SPECIFIC_ROW: LicenseRow = LicenseRow(
    match="publisher-specific",
    content_class=GATED_DEFAULT_CONTENT_CLASS,
    redistributable=False,
    license_name="Publisher-specific license (proprietary terms)",
    rationale=(
        "Publisher-specific terms are not an open redistribution grant "
        "-> gated."
    ),
)

# OA aggregators emit CC licenses as compact codes ("cc-by", "cc-by-nc-nd",
# "cc0") as often as full URIs. We add short-code rows to the OA table rather
# than the shared CC core, because the codes are an OA-source vocabulary, not
# part of the canonical (URI-keyed) legal table. The codes carry the SAME
# NC/ND-before-BY ordering contract: "cc-by-nc" must precede "cc-by".
_CC_SHORT_CODE_ROWS: tuple[LicenseRow, ...] = (
    LicenseRow(
        match="cc-by-nc",
        content_class=GATED_DEFAULT_CONTENT_CLASS,
        redistributable=False,
        license_name="CC BY-NC (non-commercial)",
        rationale=(
            "NC forbids commercial reuse; Antiek's ad-funded serving is "
            "commercial -> gated."
        ),
    ),
    LicenseRow(
        match="cc-by-nd",
        content_class=GATED_DEFAULT_CONTENT_CLASS,
        redistributable=False,
        license_name="CC BY-ND (no-derivatives)",
        rationale="ND bars derivative presentation -> gated (conservative).",
    ),
    LicenseRow(
        match="cc-by-sa",
        content_class=SOURCE_DECLARED_OPEN_CONTENT_CLASS,
        redistributable=True,
        license_name="CC BY-SA",
        rationale=(
            "CC BY-SA permits redistribution with attribution + share-alike "
            "-> servable as source_declared_open (not a §9.10 publisher "
            "opt-in; 2026-05-29 remap)."
        ),
    ),
    LicenseRow(
        match="cc-by",
        content_class=SOURCE_DECLARED_OPEN_CONTENT_CLASS,
        redistributable=True,
        license_name="CC BY",
        rationale=(
            "CC BY permits redistribution with attribution -> servable as "
            "source_declared_open (not a §9.10 publisher opt-in; 2026-05-29 "
            "remap)."
        ),
    ),
    LicenseRow(
        match="cc0",
        content_class=PUBLIC_DOMAIN_CONTENT_CLASS,
        redistributable=True,
        license_name="CC0 1.0 (public-domain dedication)",
        rationale=(
            "CC0 waives all rights -> public_domain (no rights holder, no "
            "attribution obligation; 2026-05-29 remap)."
        ),
    ),
)

# The OA table: public-domain mark + the canonical CC URI rows + the CC
# short-code rows + the OA-specific gated signals. URI rows come before the
# short-code rows so a full URI is classified by the canonical legal row; the
# bronze/publisher-specific rows sit last (plain substrings, no CC collision).
_OA_TABLE: tuple[LicenseRow, ...] = (
    (CC_PDM_ROW,)
    + CC_LICENSE_ROWS
    + _CC_SHORT_CODE_ROWS
    + (_BRONZE_ROW, _PUBLISHER_SPECIFIC_ROW)
)


def resolve_oa_license(license_uri: Optional[str]) -> LicenseResolution:
    """Map an open-access license string/URI to a servable-class resolution.

    Deny-by-default: ``None`` / empty / unmatched (including bronze with no
    declared license) resolves to ``GATED_DEFAULT_CONTENT_CLASS`` with
    ``redistributable=False``. Resolved classes (2026-05-29 remap):
      - CC-BY / CC-BY-SA (URI or short code) -> ``source_declared_open``
        (servable; source-declared open license, NOT a §9.10 publisher opt-in);
      - CC0 (URI or short code) -> ``public_domain`` (servable; public-domain
        dedication);
      - CC Public-Domain Mark -> ``public_domain`` (servable);
      - bronze / publisher-specific / CC-NC / CC-ND / unknown -> gated.
    """
    return resolve_against_table(license_uri, _OA_TABLE)
