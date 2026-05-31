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
from typing import Any, Mapping, Optional

from substrate.constants import (
    GATED_DEFAULT_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
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


# Compact CC codes ("cc-by", "cc-by-nc-nd", "cc0") that OA aggregators
# (OpenAlex / Unpaywall / PMC / DOAJ) emit as often as full URIs. These carry
# the SAME legal verdict as the URI rows above and so live HERE, the one CC
# home, rather than being forked per source — the classify() chokepoint and
# the OA resolver both compose this tuple. The codes carry the same
# NC/ND-before-BY ordering contract: "cc-by-nc" must precede "cc-by", else a
# CC-BY-NC code would match the bare "cc-by" row and be mis-served.
CC_SHORT_CODE_ROWS: tuple[LicenseRow, ...] = (
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


# ---------------------------------------------------------------------------
# THE rights-classification chokepoint (SPR-02). Exactly one function decides
# every fetched work's content_class + whether it is ingested at all. Every
# Wave-2 connector calls THIS; no connector assigns a content_class by any
# other route. It composes the existing license-resolution engine
# (resolve_against_table over the canonical CC table) rather than re-deriving
# CC semantics — there is one legal home for "what is servable".
# ---------------------------------------------------------------------------

# The classify() decision lives over the SAME canonical CC rows the per-source
# resolvers compose, so a CC license classifies identically here and inside
# acquisition.arxiv / acquisition.openaccess (no divergent CC verdict). URI rows
# come before the compact short-code rows so a full URI is classified by the
# canonical legal row; both forms reach the chokepoint because a connector may
# hand classify() either an aggregator short code or a full license URI.
_CLASSIFY_TABLE: tuple[LicenseRow, ...] = (
    (CC_PDM_ROW,) + CC_LICENSE_ROWS + CC_SHORT_CODE_ROWS
)

# license_basis values the classify branches stamp, named so the per-batch
# rights audit (substrate.rights_audit) and a lawyer read the SAME tokens.
PUBLISHER_GRANT_BASIS_PREFIX = "publisher_opt_in"
PUBLIC_DOMAIN_DECLARED_BASIS = "public_domain: source-declared public-domain status"
CIRCUMVENTED_SKIP_BASIS = (
    "SKIP: access was circumvented (shadow library / paywall bypass) -- "
    "never ingested; a non-servable work from an illegitimate source is not "
    "stored at all"
)


@dataclass(frozen=True)
class ClassificationResult:
    """The single rights decision for one fetched work.

    ``content_class`` is always a member of the substrate's book content-class
    vocabulary (a servable class only when a license was positively
    established; ``GATED_DEFAULT_CONTENT_CLASS`` otherwise). ``ingest`` is the
    gated-mass-ingest vs never-ingest verdict: a positively-licensed work and a
    GATED work from a *legitimate* source are ingested; a non-servable work
    whose access was *circumvented* is NOT ingested at all (``ingest=False``).
    ``servable`` is DERIVED from the class (membership in
    SERVABLE_CONTENT_CLASSES) — never an independent flag that could drift.
    ``accrual_eligible`` is True only for a gated work held for an
    in-copyright reason (a rights holder exists) so M6's escrow accrual fires
    for exactly those — never for public-domain / open-licensed works.
    ``license_basis`` is the human-legible provenance a reviewer can read
    months later in front of counsel; a servable result NEVER carries an empty
    basis (impossible by construction)."""

    content_class: str
    ingest: bool
    servable: bool
    accrual_eligible: bool
    license_basis: str
    rationale: str

    @property
    def skipped(self) -> bool:
        """A work that is not ingested (circumvented-access, never stored)."""
        return not self.ingest


def _is_truthy_pd_signal(value: Any) -> bool:
    """Whether a ``source_declaration['public_domain']`` value is a POSITIVE
    public-domain assertion. A bare ``True`` or a non-empty descriptive string
    (e.g. a jurisdiction/date basis) counts; ``False`` / ``None`` / empty does
    NOT (intellectual honesty: "we couldn't tell" never upgrades to servable)."""
    if value is True:
        return True
    if isinstance(value, str):
        return bool(value.strip())
    return False


def classify(
    license: Optional[str],
    source_declaration: Mapping[str, Any],
    *,
    legitimate_source: bool,
) -> ClassificationResult:
    """Map a work's license + source declaration to its rights class,
    deny-by-default. THE single classification chokepoint (SPR-02).

    Resolution order (first positive signal wins; everything else gates):

    1. **Publisher grant** — ``source_declaration['publisher_grant']`` present
       (a §9.10 opt-in: a publisher claimed the work) -> ``opt_in_licensed``
       (servable). The basis names the rights holder.
    2. **License string** — resolved against the canonical CC table
       (``resolve_against_table``). A redistribution-granting CC license ->
       its servable class (``public_domain`` for CC0/PDM,
       ``source_declared_open`` for CC-BY/-SA). A recognised-but-restrictive
       CC license (NC/ND) -> gated, with the basis naming *why*.
    3. **Declared public domain** — a positive
       ``source_declaration['public_domain']`` signal AND no contrary license
       -> ``public_domain`` (servable).
    4. **Everything else** — unknown, ambiguous, missing, or unrecognised ->
       ``GATED_DEFAULT_CONTENT_CLASS`` (the deny-by-default safety branch).

    Then the legitimacy gate decides ingest-vs-skip (M3):

    - A **servable** work is ingested servable regardless of
      ``legitimate_source`` (a public-domain text is lawful from any
      legitimate fetch; this argument exists to gate the *non-servable* case).
    - A **gated** work from a ``legitimate_source=True`` (open API, PD
      repository, publisher-granted catalog) is ingested GATED — body stored,
      withheld, graph-resident, escrow accruing if a rights holder exists.
    - A **gated** work from a ``legitimate_source=False`` (circumvented access:
      shadow library, paywall bypass) is NEVER ingested -> ``ingest=False``.

    ``legitimate_source`` is keyword-only and has NO default, so a connector
    cannot silently omit the legitimacy judgment — the omission is a TypeError,
    not a quietly-gated ingest.
    """
    content_class, basis, rationale, accrual_eligible = _resolve_class(
        license, source_declaration
    )
    servable = content_class in SERVABLE_CONTENT_CLASSES

    # The legitimacy gate. A servable work is lawful to ingest from any
    # legitimate fetch; only the non-servable (gated) branch consults
    # legitimacy, and an illegitimate gated work is skipped outright (never
    # stored) — gated mass-ingest is for in-copyright works a LAWFUL source
    # surfaces, never for circumvented access.
    if not servable and not legitimate_source:
        return ClassificationResult(
            content_class=content_class,
            ingest=False,
            servable=False,
            accrual_eligible=False,
            license_basis=CIRCUMVENTED_SKIP_BASIS,
            rationale=(
                "non-servable work from an illegitimate (circumvented-access) "
                "source -> skip; never ingested, no body stored, no escrow."
            ),
        )

    return ClassificationResult(
        content_class=content_class,
        ingest=True,
        servable=servable,
        accrual_eligible=accrual_eligible and not servable,
        license_basis=basis,
        rationale=rationale,
    )


def _resolve_class(
    license: Optional[str],
    source_declaration: Mapping[str, Any],
) -> tuple[str, str, str, bool]:
    """Resolve (content_class, license_basis, rationale, accrual_eligible)
    BEFORE the legitimacy gate. Pure mapping of the positive signals; the
    fallback is the deny-by-default gated class. ``accrual_eligible`` is True
    only when the work gates for an in-copyright reason with a rights holder —
    the M6 escrow seam keys off it."""
    # 1. Publisher §9.10 opt-in grant — the publisher claimed the work.
    grant = source_declaration.get("publisher_grant")
    if grant:
        rights_holder = _grant_rights_holder(grant)
        holder_tag = f" ({rights_holder})" if rights_holder else ""
        return (
            SERVABLE_CONTENT_CLASS,  # "opt_in_licensed"
            f"{PUBLISHER_GRANT_BASIS_PREFIX}{holder_tag}",
            "publisher claimed the work via the §9.10 opt-in flow -> servable.",
            False,
        )

    # 2. License string resolved against the canonical CC table.
    if license and license.strip():
        resolution = resolve_against_table(license, _CLASSIFY_TABLE)
        if resolution.redistributable:
            return (
                resolution.content_class,
                license_basis_string(resolution),
                resolution.rationale,
                False,
            )
        # A recognised-but-restrictive CC license (NC/ND) or an unrecognised
        # URI -> gated. The basis names WHY. A declared license that gates is
        # an in-copyright restriction; a rights holder exists -> accrual-eligible.
        return (
            GATED_DEFAULT_CONTENT_CLASS,
            license_basis_string(resolution),
            resolution.rationale,
            True,
        )

    # 3. Declared public domain with no contrary license.
    if _is_truthy_pd_signal(source_declaration.get("public_domain")):
        pd_note = source_declaration.get("public_domain")
        basis = (
            f"public_domain: {pd_note}"
            if isinstance(pd_note, str) and pd_note.strip()
            else PUBLIC_DOMAIN_DECLARED_BASIS
        )
        return (
            PUBLIC_DOMAIN_CONTENT_CLASS,
            basis,
            "source positively declared public-domain status -> servable.",
            False,
        )

    # 4. Deny-by-default. Unknown / ambiguous / missing / in-copyright. A
    # rights-holder existing (rights_holder declared) makes it accrual-eligible
    # so escrow accrues to a pre-onboarded holder; an anonymous unknown work
    # gates but accrues to nobody.
    has_rights_holder = bool(
        source_declaration.get("rights_holder")
        or source_declaration.get("rights_holder_name")
    )
    return (
        GATED_DEFAULT_CONTENT_CLASS,
        "GATED: no positively-established redistribution license -> gated by "
        "default (deny-by-default safety branch).",
        "no positively-established license / unknown rights -> gated.",
        has_rights_holder,
    )


def _grant_rights_holder(grant: Any) -> Optional[str]:
    """Pull the rights-holder name out of a ``publisher_grant`` signal. The
    signal is a mapping (``{'rights_holder': 'MIT Press', ...}``) for the rich
    case; a bare truthy value (e.g. ``True``) is a grant with no named holder."""
    if isinstance(grant, Mapping):
        holder = grant.get("rights_holder") or grant.get("rights_holder_name")
        return str(holder) if holder else None
    return None
