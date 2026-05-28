"""arXiv per-paper license URI → Antiek servable-class mapping.

THE LOAD-BEARING INVARIANT (hard-to-vary): *no paper is ever served on a
license Antiek does not actually hold.* arXiv hosting a paper is NOT a
redistribution right — the right comes from the paper's declared license.
Unknown / unmatched / missing license → GATED, never servable. The
unknown-fallback is the deny-by-default safety branch.

The mapping is a DATA TABLE (``_LICENSE_TABLE``), not scattered
conditionals, so a reviewer reads ONE table and sees which licenses are
servable and why. Each row carries:

  - a matcher (an exact URI or a substring fragment that identifies the
    license family),
  - the resulting ``content_class`` (a member of
    ``substrate.books.ingest._VALID_BOOK_CONTENT_CLASSES``),
  - ``redistributable`` (does Antiek's ad-funded full-text serving have
    a grant under this license),
  - a human license name (for the ``license_basis`` audit string),
  - a one-line rationale.

The set of license URIs arXiv actually emits (the
``{http://arxiv.org/schemas/atom}license`` element):
https://info.arxiv.org/help/license/index.html

This module is PURE — no I/O, no DB, no network — so the mapping is unit
-testable in isolation and cheap to audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from substrate.constants import GATED_DEFAULT_CONTENT_CLASS

# Servable papers (an actual redistribution grant) land here. This is the
# "we hold an opt-in-equivalent license" class — distinct from
# public_domain (CC0 is a PD dedication but arXiv routes it through the
# same servable lane; see the CC0 row rationale).
_SERVABLE_CONTENT_CLASS = "opt_in_licensed"


@dataclass(frozen=True)
class LicenseResolution:
    """Result of resolving a license URI. ``content_class`` is always a
    member of the substrate's valid book content classes; ``gated`` papers
    resolve to ``GATED_DEFAULT_CONTENT_CLASS``."""

    content_class: str
    redistributable: bool
    license_name: str
    rationale: str
    # The URI we resolved against (echoed back for the audit string).
    license_uri: Optional[str]


@dataclass(frozen=True)
class _Row:
    """One row of the mapping table.

    ``match`` is matched case-insensitively as a SUBSTRING of the license
    URI, so ``creativecommons.org/licenses/by/4.0`` matches both the http
    and https forms and the trailing-slash variants arXiv emits across its
    license-element history. Rows are evaluated top-to-bottom; the FIRST
    match wins, so the more-specific NC/SA/ND fragments must precede the
    bare ``/by/`` row (otherwise a CC-BY-NC URI would match ``/by/`` and be
    misclassified as servable). Order is the safety contract here.
    """

    match: str
    content_class: str
    redistributable: bool
    license_name: str
    rationale: str


# ---------------------------------------------------------------------------
# THE TABLE — the audit artifact. Read top-to-bottom; first match wins.
# More-restrictive CC variants (NC / ND) come BEFORE the permissive ones so
# a CC-BY-NC URI is never mis-matched by the bare /by/ row.
# ---------------------------------------------------------------------------

_LICENSE_TABLE: tuple[_Row, ...] = (
    # --- GATED CC variants (must precede the permissive /by/ rows) ---
    # CC-BY-NC* — JUDGMENT CALL (documented in the SPR-02 handoff). NC
    # licenses forbid commercial reuse. Antiek serves full text behind a
    # per-second ad border with a 70% payout — an ad-funded, commercial
    # context. So NC does NOT cleanly grant Antiek's redistribution → GATED.
    # Reverse-if: Antiek adds a non-commercial serving mode, or makes a
    # per-license commercial-use determination, this row should flip.
    _Row(
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
    _Row(
        match="creativecommons.org/licenses/by-nd",
        content_class=GATED_DEFAULT_CONTENT_CLASS,
        redistributable=False,
        license_name="CC BY-ND (no-derivatives)",
        rationale=(
            "ND bars derivative presentation; Antiek's chunked/reflowed "
            "serving is arguably derivative -> gated (conservative)."
        ),
    ),
    # --- SERVABLE CC variants ---
    # CC-BY-SA (share-alike). Redistributable; SA copyleft is a downstream
    # obligation Antiek inherits, not a bar to serving.
    _Row(
        match="creativecommons.org/licenses/by-sa",
        content_class=_SERVABLE_CONTENT_CLASS,
        redistributable=True,
        license_name="CC BY-SA",
        rationale=(
            "CC BY-SA permits redistribution (incl. commercial) with "
            "attribution + share-alike -> servable."
        ),
    ),
    # CC-BY (attribution only) — 4.0 and 3.0 both match this fragment.
    _Row(
        match="creativecommons.org/licenses/by",
        content_class=_SERVABLE_CONTENT_CLASS,
        redistributable=True,
        license_name="CC BY",
        rationale=(
            "CC BY permits redistribution (incl. commercial) with "
            "attribution -> servable."
        ),
    ),
    # CC0 / public-domain dedication. arXiv emits the publicdomain/zero URI.
    _Row(
        match="creativecommons.org/publicdomain/zero",
        content_class=_SERVABLE_CONTENT_CLASS,
        redistributable=True,
        license_name="CC0 1.0 (public-domain dedication)",
        rationale=(
            "CC0 waives all rights -> freely redistributable -> servable."
        ),
    ),
    # --- GATED: arXiv default + reserved ---
    # arXiv's default "non-exclusive license to distribute". This lets
    # arXiv host the paper; the AUTHOR retains copyright. NO grant to
    # Antiek. This is the most common arXiv license and the one most
    # likely to be mistaken for "free to serve".
    _Row(
        match="arxiv.org/licenses/nonexclusive-distrib",
        content_class=GATED_DEFAULT_CONTENT_CLASS,
        redistributable=False,
        license_name="arXiv non-exclusive license to distribute",
        rationale=(
            "Grants arXiv hosting only; author retains copyright; no "
            "redistribution grant to Antiek -> gated."
        ),
    ),
)


def resolve_license(license_uri: Optional[str]) -> LicenseResolution:
    """Map an arXiv license URI to a servable-class resolution.

    Deny-by-default: a ``None`` / empty / unmatched URI resolves to
    ``GATED_DEFAULT_CONTENT_CLASS`` with ``redistributable=False``. This is
    the load-bearing safety branch — an unknown license is NEVER guessed
    servable.
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
    for row in _LICENSE_TABLE:
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
    """Compose the audit ``license_basis`` string stamped on the book_asset.

    For a servable paper this names the license + its URI; for a gated
    paper it states WHY it's gated. Either way the substrate row carries a
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
