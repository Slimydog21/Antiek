"""Operator-run intake for the §9.10 publisher opt-in lane.

Parses a publisher's catalog manifest and, per work:

  1. Validates the work's serving grant (``manifest.validate_grant``).
  2. Routes the rights decision through the ONE chokepoint
     (``acquisition.licenses_core.classify``): a VALID grant is handed to
     classify() as ``source_declaration['publisher_grant']`` -> branch 1 ->
     ``opt_in_licensed`` (servable), basis ``publisher_opt_in (<holder>)``;
     an INVALID/absent grant is handed to classify() WITHOUT a publisher_grant
     (only the ``rights_holder`` name) -> deny-by-default gated branch
     (``restricted_pending_opt_in``), accrual-eligible because a rights holder
     exists. content_class is NEVER assigned by any other route.
  3. Ingests the body through the shared servable path
     (``acquisition.books.adapter.ingest_servable_book`` ->
     ``substrate.books.ingest.register_book``), passing classify()'s
     ``content_class`` + ``license_basis``. The gated body is still
     chunked/embedded (register stores the document + chunks); only full-text
     SERVING is withheld — servability is DERIVED from content_class.
  4. Links the work to the publisher's ip_holder (created ``pre_onboarded`` on
     first sight, REUSED on resubmission), keyed on the stable ``publisher_id``.
  5. Accrues escrow to that holder via the EXISTING seam
     (``substrate.ip_holders.accrue_escrow``) — accrual only, never disburses.
     The disbursement modules under ``substrate/ad_inventory/`` (the money path)
     are never imported or called here; disbursement stays operator-gated
     (G2/G3). The G4 grep over this package finds no money-path token.

§16 box-bounded: every write goes through ``ingest_servable_book`` ->
``runtime.db_lock.connect_write`` (the single writer). In staging mode the
``db_path`` is the staging file (SPR-01); the live DB is untouched until the
operator runs the merge.

Idempotency (re-submission): the body bytes are rendered DETERMINISTICALLY, so
``acquisition.books.adapter.book_doc_id`` (a content hash of those bytes) is
stable for the SAME work across runs — re-running the manifest updates the same
document in place rather than duplicating it. The publisher's ip_holder is
reused (keyed on publisher_id). A resubmission that flips a grant flips the SAME
work's servability: add a grant -> servable; withdraw it -> gated. Identity
keys on a content-stable id (ISBN/DOI is validated + recorded; the body
content-hash is what the document_id rests on), NEVER on title+author — two
generic-title works with different bodies stay distinct.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from acquisition.licenses_core import classify
from substrate.dedup import IdentityRecord, identity_basis

from .manifest import (
    GrantValidation,
    Manifest,
    ManifestEntry,
    PublisherIdentity,
    load_manifest,
    validate_grant,
)

# A nominal per-work escrow seed accrued at intake to a granted publisher's
# holder. This is NOT the ad-attention accrual (that runs per-impression in
# substrate/ad_inventory/frame_attention_accrual.py); it is the opt-in lane's
# acknowledgement that a servable opt-in work begins accruing to its holder.
# A tiny positive amount so accrue_escrow's positive-amount contract holds and
# the SPR-10 audit can see the holder linkage is live. Accrual only — never
# disburses.
OPT_IN_INTAKE_ACCRUAL_USD = Decimal("0.01")


@dataclass(frozen=True)
class WorkOutcome:
    """Per-work result of an intake attempt.

    ``content_class`` + ``license_basis`` are the values classify() returned and
    the ingest stamped — the auditor reads "why is this servable?" from
    ``license_basis`` alone. ``servable`` is DERIVED (membership in
    SERVABLE_CONTENT_CLASSES); ``gated_reason`` explains a gated work."""

    title: str
    document_id: Optional[str]
    content_class: str
    license_basis: str
    servable: bool
    ip_holder_id: Optional[str]
    identity_basis: str
    gated_reason: Optional[str] = None
    accrued: bool = False
    skipped_reason: Optional[str] = None


@dataclass(frozen=True)
class OptInIntakeSummary:
    """Per-manifest summary (defensibility + the handoff's per-manifest block).

    Names the publisher + its (existing | newly pre_onboarded) holder, the
    servable / gated split with the reason each gated work failed grant
    validation, and whether escrow accrued."""

    publisher_id: str
    publisher_display_name: str
    ip_holder_id: str
    holder_was_created: bool
    servable_count: int
    gated_count: int
    skipped_count: int
    escrow_accrued: bool

    def render(self) -> str:
        return (
            f"opt-in [{self.publisher_display_name} / {self.ip_holder_id}"
            f"{' (new)' if self.holder_was_created else ' (reused)'}]: "
            f"{self.servable_count} servable, {self.gated_count} gated, "
            f"{self.skipped_count} skipped; "
            f"escrow accrued: {'yes' if self.escrow_accrued else 'no'}"
        )


@dataclass(frozen=True)
class IntakeResult:
    """Everything intake produced: per-work outcomes + the summary."""

    summary: OptInIntakeSummary
    outcomes: tuple[WorkOutcome, ...] = field(default_factory=tuple)


def _render_body_bytes(entry: ManifestEntry) -> bytes:
    """Render the work's body to DETERMINISTIC ingestible PDF bytes.

    Idempotency rests on this determinism: the same body text renders to the
    same bytes, so ``book_doc_id`` (a content hash) is stable across runs and a
    resubmission updates the same document rather than duplicating it. Reuses
    the existing ``acquisition.books.public_domain.text_to_pdf`` (byte-invariant)
    so there is no second PDF renderer.

    ``body_text`` is rendered directly; ``body_path`` is read from disk (an
    operator-supplied file). Exactly one must be present.
    """
    from acquisition.books.public_domain import text_to_pdf

    text: Optional[str] = None
    if entry.body_text is not None:
        text = entry.body_text
    elif entry.body_path:
        with open(entry.body_path, "r", encoding="utf-8") as f:
            text = f.read()
    if text is None or not text.strip():
        raise ValueError(
            f"work {entry.title!r} has no body (need body_text or body_path)"
        )
    return text_to_pdf(text, title=entry.title)


def _identity_record(entry: ManifestEntry, body_text: Optional[str]) -> IdentityRecord:
    """Project a manifest entry into the single substrate.dedup identity record
    so identity keys through the ONE ladder (DOI > ISBN > content-hash >
    title+author LOW). ISBN/DOI win; title+author is only the LOW fallback the
    collapse pass refuses to silently merge on."""
    return IdentityRecord(
        ref_id=f"opt_in:{entry.doi or entry.isbn or entry.title}",
        source="opt_in",
        doi=entry.doi,
        isbn=entry.isbn,
        title=entry.title,
        author=entry.author,
        body=body_text,
    )


def _source_declaration_for(
    publisher: PublisherIdentity, validation: GrantValidation
) -> dict:
    """Build the ``source_declaration`` handed to classify().

    A VALID grant becomes ``publisher_grant`` (classify branch 1 ->
    opt_in_licensed servable). An INVALID/absent grant passes ONLY the
    rights_holder name (no publisher_grant) so classify() lands the work on the
    deny-by-default gated branch — gated, but accrual-eligible because a rights
    holder exists (escrow accrues to the pre-onboarded holder)."""
    holder = validation.rights_holder or publisher.display_name
    if validation.valid:
        return {
            "publisher_grant": {
                "rights_holder": holder,
                # The verbatim authorization statement classify() folds into the
                # basis prefix; the full text is appended below so the row names
                # the grant in full.
                "statement": validation.grant_text,
            }
        }
    # No (valid) grant: declare the rights holder so the gated work is
    # accrual-eligible, but NEVER a publisher_grant (that would flip servable).
    return {"rights_holder": holder}


def _compose_basis(classification, validation: GrantValidation) -> str:
    """The license_basis stamped on the row. For a servable opt-in work, append
    the verbatim grant statement to classify()'s basis so an auditor answers
    'by whose grant, what text?' from the row alone. For a gated work, fold the
    grant-validation reason into classify()'s gated basis."""
    base = classification.license_basis
    if classification.servable and validation.grant_text:
        return f"{base} -- grant: {validation.grant_text}"
    if not classification.servable and validation.reason:
        return f"{base} -- opt-in intake: {validation.reason}"
    return base


def resolve_publisher_holder(
    publisher: PublisherIdentity, *, db_path: str
) -> tuple[str, bool]:
    """Resolve the publisher's ip_holder ONCE, keyed on the STABLE publisher_id.

    The holder seam keys on the display-name string it is given, so we hand it a
    string derived purely from ``publisher_id`` — never the mutable
    ``display_name``. Two submissions of the same publisher_id collapse to ONE
    pre_onboarded holder even when the human-facing display_name was edited
    between runs. Returns ``(ip_holder_id, was_created)``.
    """
    from runtime.db_lock import connect_write
    from substrate.books.ingest import resolve_or_create_ip_holder
    from substrate.ip_holders import list_all

    holder_display = f"opt_in:{publisher.publisher_id}"
    with connect_write(db_path, purpose="opt_in/holder") as con:
        existing = {h.ip_holder_id for h in list_all(con)}
        ip_holder_id = resolve_or_create_ip_holder(con, holder_display)
    return ip_holder_id, ip_holder_id not in existing


def ingest_entry(
    entry: ManifestEntry,
    publisher: PublisherIdentity,
    *,
    ip_holder_id: str,
    db_path: str,
    catalog_grant=None,
    investigation_id: str = "inv-opt-in",
    embedder=None,
    accrual_usd: Decimal = OPT_IN_INTAKE_ACCRUAL_USD,
) -> WorkOutcome:
    """Ingest ONE manifest entry, linking it to ``ip_holder_id``.

    THE BINDING: content_class comes ONLY from ``classify()`` — a valid grant
    becomes ``publisher_grant`` (servable), an invalid/absent grant gates
    deny-by-default. The body is rendered deterministically and written through
    ``ingest_servable_book`` -> ``connect_write``. A servable work accrues
    escrow to the linked holder via the existing seam (accrual only).

    Shared by ``intake_manifest`` (manifest loop) and the orchestrator's
    per-candidate ingest thunk, so both routes make the SAME rights decision via
    the SAME chokepoint.
    """
    from acquisition.books.adapter import ingest_servable_book
    from runtime.db_lock import connect_write
    from substrate.ip_holders import accrue_escrow

    validation = validate_grant(entry, catalog_grant=catalog_grant)
    ikey_basis = identity_basis(_identity_record(entry, entry.body_text))

    # Render the body BEFORE classify so a body-less work is a clean skip
    # (never silently servable, never silently gated-with-no-body).
    try:
        pdf_bytes = _render_body_bytes(entry)
    except Exception as exc:
        return WorkOutcome(
            title=entry.title,
            document_id=None,
            content_class="",
            license_basis="",
            servable=False,
            ip_holder_id=ip_holder_id,
            identity_basis=ikey_basis,
            skipped_reason=str(exc),
        )

    source_declaration = _source_declaration_for(publisher, validation)
    # THE BINDING: the one chokepoint decides content_class. A publisher's own
    # catalog is a legitimate source.
    classification = classify(None, source_declaration, legitimate_source=True)
    basis = _compose_basis(classification, validation)

    result = ingest_servable_book(
        pdf_bytes,
        investigation_id=investigation_id,
        content_class=classification.content_class,
        ip_holder_id=ip_holder_id,
        license_basis=basis,
        provenance=f"opt_in:{publisher.publisher_id}",
        source_uri=ikey_basis,
        db_path=db_path,
        embedder=embedder,
    )

    accrued = False
    if classification.servable:
        # A servable opt-in work begins accruing to its publisher's holder via
        # the EXISTING seam — accrual only; the money path is untouched.
        with connect_write(db_path, purpose="opt_in/accrue") as con:
            accrue_escrow(con, ip_holder_id, accrual_usd)
        accrued = True

    return WorkOutcome(
        title=entry.title,
        document_id=result.document_id,
        content_class=classification.content_class,
        license_basis=basis,
        servable=classification.servable,
        ip_holder_id=ip_holder_id,
        identity_basis=ikey_basis,
        gated_reason=None if classification.servable else validation.reason,
        accrued=accrued,
    )


def intake_manifest(
    manifest: Manifest,
    *,
    investigation_id: str = "inv-opt-in",
    db_path: Optional[str] = None,
    embedder=None,
    accrual_usd: Decimal = OPT_IN_INTAKE_ACCRUAL_USD,
) -> IntakeResult:
    """Ingest a parsed publisher catalog manifest.

    Returns per-work outcomes + a per-manifest summary. Every content_class
    decision routes through ``classify()``; every write goes through
    ``ingest_servable_book`` -> ``connect_write`` (the single writer / staging
    path). The publisher's ip_holder is resolved ONCE (pre-onboarded on first
    sight, reused on resubmission) and every work links to it.
    """
    from substrate.graph import default_db_path, ensure_initialized

    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)

    ip_holder_id, holder_was_created = resolve_publisher_holder(
        manifest.publisher, db_path=resolved_db_path
    )

    outcomes: list[WorkOutcome] = []
    servable_count = gated_count = skipped_count = 0
    for entry in manifest.entries:
        outcome = ingest_entry(
            entry,
            manifest.publisher,
            ip_holder_id=ip_holder_id,
            db_path=resolved_db_path,
            catalog_grant=manifest.catalog_grant,
            investigation_id=investigation_id,
            embedder=embedder,
            accrual_usd=accrual_usd,
        )
        outcomes.append(outcome)
        if outcome.skipped_reason:
            skipped_count += 1
        elif outcome.servable:
            servable_count += 1
        else:
            gated_count += 1
    escrow_accrued = any(o.accrued for o in outcomes)

    summary = OptInIntakeSummary(
        publisher_id=manifest.publisher.publisher_id,
        publisher_display_name=manifest.publisher.display_name,
        ip_holder_id=ip_holder_id,
        holder_was_created=holder_was_created,
        servable_count=servable_count,
        gated_count=gated_count,
        skipped_count=skipped_count,
        escrow_accrued=escrow_accrued,
    )
    return IntakeResult(summary=summary, outcomes=tuple(outcomes))


def intake_manifest_file(
    path: str,
    *,
    investigation_id: str = "inv-opt-in",
    db_path: Optional[str] = None,
    embedder=None,
) -> IntakeResult:
    """Load a manifest JSON file from ``path`` and ingest it."""
    return intake_manifest(
        load_manifest(path),
        investigation_id=investigation_id,
        db_path=db_path,
        embedder=embedder,
    )
