"""The standing corpus audit — prove the live corpus is rights-correct + clean,
every batch, forever (SPR-10, the defensibility capstone).

This module turns "the corpus is safe to serve" from a claim into a command. It
opens the live DuckDB **read-only** and asserts five corpus-level invariants,
returning a structured :class:`AuditResult` (per-check pass/fail + counts +
offending ids). It is the seal on the box: every prior corpus-ingest sprint
builds a gate; this one proves those gates still hold on the *accumulated*
corpus, batch after batch, where a per-batch gate structurally cannot see drift
introduced by a future schema change, a merge that copied a row a gate never
saw, or a connector added without its gate wired in.

It mints NO new rights / dedup / quality / budget logic. Each check COMPOSES the
gate the owning sprint already shipped (rigor #4 — consume, do not redefine):

  (a) servable-without-basis — every work whose ``content_class`` ∈
      ``substrate.constants.SERVABLE_CONTENT_CLASSES`` has a non-empty
      ``license_basis``. The allowlist is imported, never re-listed (SPR-02).
  (b) gated-leak — TWO arms, both asserted against the PUBLIC SERVE PROJECTION
      (``substrate.books.serve.serve_full_text`` → ``substrate.books.servability``),
      NOT merely ``content_class != restricted``:
        (b1) no ``restricted_pending_opt_in`` body renders on the serve path — a
             gated doc returns at most a bounded snippet, never full text.
        (b2) no SERVABLE-classed doc whose ``license_basis`` CONTRADICTS
             servability (a ``GATED:``/circumvented basis) renders full text.
             This is the catastrophic real-world §9.0 failure (b1 structurally
             cannot see): a body that SHOULD be gated but was mislabeled with a
             servable ``content_class`` — the serve path trusts the column and
             renders it, while b1 never selects it (its class is not the gated
             one). b2 cross-checks the served class against the basis the ONE
             classify() chokepoint wrote, on the SAME serve projection, so a
             class/basis desync (a hand-stamped class, a merge that corrupted a
             row) is caught from REAL data — no stubbed serve path needed (SPR-02).
  (c) dedup identity — no two distinct documents share a stable identity
      (DOI / ISBN-13 / arXiv-id / source-id / content-hash), keyed through the
      ONE identity ladder in ``substrate.dedup`` (SPR-04).
  (d) extraction quality — no body whose head is ``b'<!DO'`` (an HTML landing
      page mis-stored as a body) and no empty body for a non-skipped document
      (SPR-03's extraction notion).
  (e) budget — corpus size (doc count / DB bytes / chunk count) is within the
      SPR-09 box ceiling, read through ``substrate.ingest_budget.BudgetGovernor``
      (the same governor the continuous engine consults). The audit never
      re-derives the ceiling number.
  (f) third-party-on-servable — no document whose ``document_type`` ∈
      ``substrate.constants.THIRD_PARTY_DOCUMENT_TYPES`` (web_article /
      video_transcript / social_thread / newsletter_post) sits on a class in
      ``SERVABLE_CONTENT_CLASSES`` without a positive ``license_basis``
      (Personal-Reading Lane SPR-02). Such a third-party work is the OWNER's
      private reading and MUST land ``personal_reading``; this is the standing
      DB backstop for the connector deny-by-default lane. The check mirrors
      ``_check_servable_basis``'s join exactly, scoped to the third-party types,
      with both allowlists imported (never re-listed). A servable third-party
      row WITH a real basis (a PG public-domain text via the urls connector, a
      CC-BY transcript) is the lawful SPR-05/SPR-07 exception, deliberately NOT
      flagged.

Plus THE BINDING (SPR-10's headline enforcement), a STATIC check independent of
any DB: ``content_class`` is decided by exactly ONE function —
``acquisition.licenses_core.classify()`` (the public-corpus family) or passed as
an imported constant by the third-party reading connectors (never a string
literal). :func:`assert_no_content_class_bypass` AST-walks every connector under
``acquisition/{books,textbooks,papers,opt_in,urls,youtube,twitter,substack}/``
and asserts ZERO of them assign ``content_class`` to a string LITERAL (the
retired anti-pattern) rather than forwarding a classify()-derived value or an
imported lane constant. This is the assertion that keeps the rights audit
single-source: if two places could mint a content_class, "every servable work
has a basis" is no longer a property of one chokepoint.

----------------------------------------------------------------------------
§16 BOX-BOUNDED + READ-ONLY (a hard constraint, not a nicety)
----------------------------------------------------------------------------
The audit + the ``--summary`` dashboard run against the live prod DuckDB WHILE
``antiek.service`` serves. They MUST open read-only (``runtime.db_lock.connect_read``)
and NEVER call ``connect_write`` — otherwise they would contend for the
single-writer flock and stall the live API. A standing audit is therefore an
in-process FUNCTION (``run_audit(db_path) -> AuditResult``) that SPR-01's merge
step and a CI job both CALL — never a daemon, queue, worker, or second runtime.
There is exactly one ``connect_read`` import in this module and zero writers.

----------------------------------------------------------------------------
Provenance — the verbatim 2026-05-29 hand-run verification queries
----------------------------------------------------------------------------
The operator characterised the first prod batch (31 docs: 22 servable
public-domain classics + 9 gated open-access papers, 5,017 embedded chunks) by
hand. Those queries are the seed assertions these checks mechanise so the
hand-run never has to be repeated:

    -- servable / gated split (M5 dashboard + check a/b context)
    SELECT content_class, COUNT(*) FROM documents
      GROUP BY content_class ORDER BY 2 DESC;

    -- check (a): 0 servable works without a basis
    SELECT d.document_id
      FROM documents d LEFT JOIN book_assets b USING (document_id)
     WHERE d.content_class IN (<SERVABLE_CONTENT_CLASSES>)
       AND (b.license_basis IS NULL OR TRIM(b.license_basis) = '');

    -- check (d): 0 empty bodies
    SELECT document_id FROM documents
     WHERE raw_text IS NULL OR TRIM(raw_text) = '';

    -- corpus size (check e + dashboard)
    SELECT COUNT(*) FROM documents;  SELECT COUNT(*) FROM chunks;
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

# Read-only DB access funnels through the one sanctioned read path. There is NO
# import of connect_write anywhere in this module (§16: the audit must not
# contend for the single-writer lock while the live API serves).
from runtime.db_lock import connect_read
from substrate.books.serve import serve_full_text
from substrate.constants import (
    GATED_DEFAULT_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
    THIRD_PARTY_DOCUMENT_TYPES,
)
from substrate.dedup import (
    Confidence,
    IdentityRecord,
    identity_key,
)
from substrate.ingest_budget import (
    DEFAULT_HARD_DB_SIZE_BYTES,
    BudgetGovernor,
    BudgetState,
)

# Check names — stable string ids so CI, the dashboard, and the merge step refer
# to the same checks. Order is the reading order of the spec's M2 list.
CHECK_SERVABLE_BASIS = "servable_without_basis"
CHECK_GATED_LEAK = "gated_body_leak"
CHECK_DEDUP = "dedup_identity"
CHECK_EXTRACTION = "extraction_quality"
CHECK_BUDGET = "budget_ceiling"
# Personal-Reading Lane (SPR-02): no third-party document_type (web_article /
# video_transcript / social_thread / newsletter_post) sits on a SERVABLE
# content_class without a positive license_basis. This is the standing DB
# backstop for the connector deny-by-default lane — it catches a third-party
# row that slipped onto a servable class by ANY route (a future connector that
# passes a servable class with no basis, a merge that copied a servable class
# onto a third-party row, a manual reclassify) regardless of whether the static
# bypass-scan saw the write site.
CHECK_THIRD_PARTY_SERVABLE = "third_party_servable"

ALL_CHECK_NAMES = (
    CHECK_SERVABLE_BASIS,
    CHECK_GATED_LEAK,
    CHECK_DEDUP,
    CHECK_EXTRACTION,
    CHECK_BUDGET,
    CHECK_THIRD_PARTY_SERVABLE,
)

# An HTML landing page mis-stored as a body starts with the doctype — the
# SPR-03 extraction-quality notion's canonical garbage marker.
_HTML_BODY_HEAD = "<!do"

# The prefix the ONE classify() chokepoint stamps on a GATED work's
# license_basis (acquisition.licenses_core.license_basis_string for a
# non-redistributable resolution, and CIRCUMVENTED_SKIP_BASIS). A SERVABLE
# content_class carrying this basis is a class/basis contradiction — the body
# the basis says is gated is being served. The check is case-insensitive on a
# stripped basis so a leading-whitespace or lower-case variant still reads as a
# gated basis (intellectual honesty: we never let a formatting nicety hide a
# mislabel). This composes the basis tokens licenses_core owns; it mints no new
# rights vocabulary.
_GATED_BASIS_MARKERS = ("gated:", "skip: access was circumvented")


# ---------------------------------------------------------------------------
# Result shape — structured + JSON-able so CI and the dashboard consume it.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckResult:
    """One check's verdict. ``ok`` is the pass/fail; ``count`` is how many
    offenders were found (0 when ``ok``); ``offending`` is the bounded list of
    offending ids/keys for a human to act on; ``detail`` is a one-line reason."""

    name: str
    ok: bool
    count: int
    offending: tuple[str, ...]
    detail: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["offending"] = list(self.offending)
        return d


@dataclass(frozen=True)
class AuditResult:
    """The whole-corpus verdict. ``ok`` iff every check passed. ``checks`` is the
    per-check breakdown (ordered as :data:`ALL_CHECK_NAMES`). The dashboard reads
    the verdict line off THIS object — never recomputes it — so the summary and
    the audit can never disagree (one source of truth)."""

    ok: bool
    db_path: str
    checks: tuple[CheckResult, ...]

    def check(self, name: str) -> CheckResult:
        for c in self.checks:
            if c.name == name:
                return c
        raise KeyError(name)

    @property
    def failed_checks(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if not c.ok)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "db_path": self.db_path,
            "checks": [c.to_dict() for c in self.checks],
        }


# Bound how many offending ids we carry/print, so a wholesale regression does not
# produce an unbounded blob — the first N is enough to act on; ``count`` carries
# the true total.
_MAX_OFFENDING = 50


def _bounded(ids: list[str]) -> tuple[str, ...]:
    return tuple(ids[:_MAX_OFFENDING])


# ---------------------------------------------------------------------------
# The five read-only checks. Each takes an already-open read-only connection
# (so run_audit opens ONE read connection for the whole audit) and is
# deterministic + idempotent on an unchanged corpus.
# ---------------------------------------------------------------------------


def _check_servable_basis(con: Any) -> CheckResult:
    """(a) Every servable work carries a non-empty ``license_basis``.

    Servable is defined by ``SERVABLE_CONTENT_CLASSES`` (imported, never
    re-listed — a future taxonomy change can't silently desync the audit). The
    basis lives on ``book_assets``; a servable document with a NULL/empty basis
    (or no book_assets row at all) is an offender. NULL and empty-string are
    treated identically — an empty basis is no basis (a surfaced assumption)."""
    placeholders = ", ".join("?" for _ in SERVABLE_CONTENT_CLASSES)
    rows = con.execute(
        f"""
        SELECT d.document_id
          FROM documents d
          LEFT JOIN book_assets b ON d.document_id = b.document_id
         WHERE d.content_class IN ({placeholders})
           AND (b.license_basis IS NULL OR TRIM(b.license_basis) = '')
         ORDER BY d.document_id
        """,
        list(SERVABLE_CONTENT_CLASSES),
    ).fetchall()
    offenders = [r[0] for r in rows]
    ok = not offenders
    return CheckResult(
        name=CHECK_SERVABLE_BASIS,
        ok=ok,
        count=len(offenders),
        offending=_bounded(offenders),
        detail=(
            "all servable works carry a license_basis"
            if ok
            else f"{len(offenders)} servable work(s) with empty/missing license_basis"
        ),
    )


def _check_third_party_servable(con: Any) -> CheckResult:
    """(f) No third-party document_type sits on a servable class without a basis.

    Personal-Reading Lane (SPR-02). The third-party reading connectors (urls /
    youtube / twitter / Substack) emit a ``document_type`` in
    ``THIRD_PARTY_DOCUMENT_TYPES``; such a work is the OWNER's private reading
    and MUST land ``personal_reading`` (owner-readable, public-non-servable) —
    NEVER a publicly servable class. This check is the standing DB backstop for
    that lane: it flags any third-party document sitting on a class in
    ``SERVABLE_CONTENT_CLASSES`` that carries no positive ``license_basis``.

    It mirrors :func:`_check_servable_basis` exactly — the same
    ``documents LEFT JOIN book_assets`` join, the same NULL/empty-basis-is-no-
    basis treatment — but scoped to the third-party types. The two allowlists
    are IMPORTED from ``substrate.constants`` (``THIRD_PARTY_DOCUMENT_TYPES`` and
    ``SERVABLE_CONTENT_CLASSES``), never re-listed here, so adding a servable
    class or a third-party document_type updates this check automatically and it
    can never silently desync from the connector lane.

    WHY THE BASIS CARVE-OUT (intellectual honesty, not a loophole). A third-party
    document_type with a servable class AND a real ``license_basis`` is NOT an
    offender — that is the lawful exception SPR-05/SPR-07 rely on (a Project-
    Gutenberg public-domain text reached through the urls connector, a CC-BY
    YouTube transcript). Those land a POSITIVE rights class with a basis on
    purpose; flagging them would false-positive the lawful open-content path. A
    NULL/empty basis on a servable third-party row is the §9.0 leak this check
    exists to catch — exactly the case the deny-by-default lane prevents going
    forward, asserted here against the ACCUMULATED corpus where a per-write gate
    cannot see a row a future merge introduced."""
    tp_placeholders = ", ".join("?" for _ in THIRD_PARTY_DOCUMENT_TYPES)
    sv_placeholders = ", ".join("?" for _ in SERVABLE_CONTENT_CLASSES)
    rows = con.execute(
        f"""
        SELECT d.document_id
          FROM documents d
          LEFT JOIN book_assets b ON d.document_id = b.document_id
         WHERE d.document_type IN ({tp_placeholders})
           AND d.content_class IN ({sv_placeholders})
           AND (b.license_basis IS NULL OR TRIM(b.license_basis) = '')
         ORDER BY d.document_id
        """,
        list(THIRD_PARTY_DOCUMENT_TYPES) + list(SERVABLE_CONTENT_CLASSES),
    ).fetchall()
    offenders = [r[0] for r in rows]
    ok = not offenders
    return CheckResult(
        name=CHECK_THIRD_PARTY_SERVABLE,
        ok=ok,
        count=len(offenders),
        offending=_bounded(offenders),
        detail=(
            "no third-party document sits on a servable class without a basis"
            if ok
            else f"{len(offenders)} third-party document(s) on a servable class "
            "with empty/missing license_basis (should be personal_reading)"
        ),
    )


def _check_gated_leak(con: Any) -> CheckResult:
    """(b) No gated body renders on the PUBLIC SERVE PROJECTION — two arms.

    This is the headline §9.0 check. We do NOT trust the ``content_class``
    column as proof; both arms assert against the SAME serve path the API uses
    (``serve_full_text``), so a body the serve projection would render is the
    thing we test, not a column comparison.

    (b1) Every gated (``restricted_pending_opt_in``) document must return NO
         full text on the serve path (``servable is False`` AND
         ``full_text is None``). A bounded snippet is allowed (Authors Guild v.
         Google); full text is the catastrophe this whole spec exists to
         prevent. This catches a serve-path regression (a future bug in
         servability_of, a takedown-flag desync) on an already-gated row.

    (b2) Every SERVABLE-classed document whose ``license_basis`` CONTRADICTS its
         class (a ``GATED:`` / circumvented-access basis — the marker the ONE
         classify() chokepoint writes for a NON-servable resolution) is a
         mislabel: the serve path TRUSTS the servable column and renders the
         full body, while (b1) never selects it because its class is not the
         gated one. We confirm the leak on the REAL serve projection
         (``served.servable`` / ``served.full_text``) and flag it — so a
         class/basis desync (a hand-stamped servable class over a gated body, a
         merge that copied the wrong class onto a row) is caught from REAL data.
         This is the exact "one in-copyright work mis-classed as servable and
         served publicly" failure the capstone names; (b1) alone is structurally
         blind to it. The basis is the classify()-written provenance on
         ``book_assets`` — composing it here mints no new rights logic, it
         cross-checks the served class against the chokepoint's own verdict."""
    # --- arm (b1): gated rows must not render ---
    gated_ids = [
        r[0]
        for r in con.execute(
            "SELECT document_id FROM documents WHERE content_class = ? ORDER BY document_id",
            [GATED_DEFAULT_CONTENT_CLASS],
        ).fetchall()
    ]
    leaked: list[str] = []
    for doc_id in gated_ids:
        served = serve_full_text(con, doc_id)
        # A gated doc must NOT be servable and must NOT return full text on the
        # public projection. snippet is allowed (bounded fair-use view).
        if served.servable or served.full_text is not None:
            leaked.append(f"{doc_id} (gated body renders full text)")

    # --- arm (b2): a servable class over a gated basis must not render ---
    placeholders = ", ".join("?" for _ in SERVABLE_CONTENT_CLASSES)
    mislabel_rows = con.execute(
        f"""
        SELECT d.document_id, b.license_basis
          FROM documents d
          JOIN book_assets b ON d.document_id = b.document_id
         WHERE d.content_class IN ({placeholders})
         ORDER BY d.document_id
        """,
        list(SERVABLE_CONTENT_CLASSES),
    ).fetchall()
    for doc_id, basis in mislabel_rows:
        if not _basis_contradicts_servable(basis):
            continue
        # The basis says GATED but the class is servable. Confirm on the REAL
        # serve projection that the body actually renders (so this is a true
        # leak, not a benign label note): a servable-classed row renders full
        # text by construction, which is precisely why the mislabel is a leak.
        served = serve_full_text(con, doc_id)
        if served.servable or served.full_text is not None:
            leaked.append(f"{doc_id} (servable class over GATED basis renders full text)")

    ok = not leaked
    return CheckResult(
        name=CHECK_GATED_LEAK,
        ok=ok,
        count=len(leaked),
        offending=_bounded(leaked),
        detail=(
            f"no gated body reachable on the serve projection "
            f"({len(gated_ids)} gated + {len(mislabel_rows)} servable doc(s) checked)"
            if ok
            else f"{len(leaked)} body/bodies render full text on the public serve path "
            "despite a gated basis or gated class"
        ),
    )


def _basis_contradicts_servable(basis: Optional[str]) -> bool:
    """Whether a ``license_basis`` asserts the work is GATED.

    A servable ``content_class`` carrying such a basis is a class/basis
    contradiction — the body the basis says is withheld is being served. Reads
    the markers the ONE classify() chokepoint writes
    (``acquisition.licenses_core.license_basis_string`` for a non-redistributable
    resolution, ``CIRCUMVENTED_SKIP_BASIS``); case-insensitive on a stripped
    basis so a formatting variant cannot hide a mislabel. An empty/NULL basis is
    NOT a contradiction here — that is check (a)'s job (servable-without-basis),
    kept distinct so the two checks do not double-count the same row."""
    if not basis or not basis.strip():
        return False
    head = basis.strip().lower()
    return any(head.startswith(m) for m in _GATED_BASIS_MARKERS)


def _check_dedup(con: Any) -> CheckResult:
    """(c) Dedup identity holds corpus-wide.

    No two DISTINCT documents resolve to the same HIGH-confidence stable
    identity key (DOI / ISBN-13 / arXiv-id / source-id / content-hash), via the
    ONE identity ladder in ``substrate.dedup`` (SPR-04). We build an
    ``IdentityRecord`` per document from the columns the connectors stamp
    (source_uri / metadata-carried doi+isbn+arxiv+source_id, title/author/body)
    and key it through ``identity_key``. A LOW-confidence (title+author/ref)
    key NEVER counts as a collision — that is the dedup module's own
    LOW-never-merges rule, so two distinct generic-title works are not flagged
    a false duplicate. Two documents sharing one HIGH key is a true dedup
    failure (a merge that copied a row, or a connector that minted a second id
    for a work already present)."""
    rows = con.execute(
        """
        SELECT document_id, source_uri, title, author, raw_text, metadata
          FROM documents
         ORDER BY document_id
        """
    ).fetchall()
    seen: dict[str, str] = {}
    collisions: list[str] = []
    for document_id, source_uri, title, author, raw_text, metadata in rows:
        record = _document_identity_record(
            document_id, source_uri, title, author, raw_text, metadata
        )
        ikey = identity_key(record)
        if ikey.confidence is Confidence.LOW:
            # LOW keys never merge (dedup module contract) — never a collision.
            continue
        composite = f"{ikey.key_type.value}:{ikey.key}"
        prior = seen.get(composite)
        if prior is not None:
            collisions.append(f"{composite} <- {prior} & {document_id}")
        else:
            seen[composite] = document_id
    ok = not collisions
    return CheckResult(
        name=CHECK_DEDUP,
        ok=ok,
        count=len(collisions),
        offending=_bounded(collisions),
        detail=(
            f"dedup identity holds across {len(rows)} document(s)"
            if ok
            else f"{len(collisions)} duplicate identity key(s) across distinct documents"
        ),
    )


def _document_identity_record(
    document_id: str,
    source_uri: Optional[str],
    title: Optional[str],
    author: Optional[str],
    raw_text: Optional[str],
    metadata: Optional[str],
) -> IdentityRecord:
    """Map a documents row to a dedup ``IdentityRecord``.

    Stable identifiers (doi / isbn / arxiv_id / source_id) are read from the
    document's JSON ``metadata`` when the connector recorded them there;
    ``ref_id`` is the document_id itself so a record always has a unique,
    LOW-never-merges fallback. ``body`` feeds the content-hash level, which is
    how two book documents (which carry no DOI/ISBN at this layer) are caught
    as a true duplicate of the same text.

    METADATA-KEY CONTRACT (the audit's coverage depends on it — a surfaced
    assumption, not silent). The corpus-wide dedup check (c) can only key a
    document on a stable identifier the WRITE path stamped into
    ``documents.metadata``. For the characterised first prod batch this is
    real for both corpus types: arXiv papers carry ``metadata['arxiv_id']``
    (acquisition.arxiv.adapter -> insert_document), and PD books key on the
    content-hash of their extracted body (>= MIN_CONTENT_HASH_CHARS). It is a
    KNOWN COVERAGE GAP for a DOI-only cross-source duplicate: the OA/PLOS/
    bioRxiv connectors dedup on ``doi`` AT DISCOVERY but do not currently
    persist ``doi`` onto the documents row (they store ``journal`` /
    ``oa_status`` / etc.), so check (c)'s DOI rung is DEFENSIVE-ONLY until an
    OA-direct write path lands. The contract any such write path MUST honour to
    make the DOI rung live: stamp ``metadata['doi']`` (and ``metadata['isbn']``
    where applicable) onto the documents row. This is read here as ``doi`` /
    ``DOI`` and ``isbn`` / ``isbn13`` / ``ISBN`` so a connector that follows the
    contract is covered without a further audit change. (The gap never produces
    a FALSE collision — it only fails to catch a DOI-only duplicate the current
    corpus does not contain; it is honestly recorded, not hidden behind a green
    check.)"""
    meta: dict[str, Any] = {}
    if metadata:
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, dict):
                meta = parsed
        except (ValueError, TypeError):
            meta = {}

    def _m(*keys: str) -> Optional[str]:
        for k in keys:
            v = meta.get(k)
            if isinstance(v, str) and v.strip():
                return v
        return None

    return IdentityRecord(
        ref_id=document_id,
        source=(source_uri or "unknown"),
        doi=_m("doi", "DOI"),
        isbn=_m("isbn", "isbn13", "ISBN"),
        arxiv_id=_m("arxiv_id", "arxiv"),
        source_id=_m("source_id"),
        title=title,
        author=author,
        body=raw_text,
    )


def _check_extraction(con: Any) -> CheckResult:
    """(d) Extraction quality holds (the SPR-03 notion).

    Two failure modes, both corpus-poisoning:
      * an HTML landing page mis-stored as a body — ``raw_text`` whose head
        (case-insensitively) is ``<!DO`` (a ``<!DOCTYPE html>`` doctype);
      * an empty body — a document row with NULL or whitespace-only ``raw_text``
        (a failed extraction that nonetheless landed a row).

    A document whose body is HTML-as-body OR empty is an offender. (A book whose
    extraction was below the word floor is skipped BEFORE a documents row is
    written, so a documents row with an empty body is a real defect, not a known
    skip.)"""
    rows = con.execute(
        "SELECT document_id, raw_text FROM documents ORDER BY document_id"
    ).fetchall()
    offenders: list[str] = []
    for document_id, raw_text in rows:
        if raw_text is None or not raw_text.strip():
            offenders.append(f"{document_id} (empty body)")
            continue
        if raw_text.lstrip()[: len(_HTML_BODY_HEAD)].lower() == _HTML_BODY_HEAD:
            offenders.append(f"{document_id} (html-as-body)")
    ok = not offenders
    return CheckResult(
        name=CHECK_EXTRACTION,
        ok=ok,
        count=len(offenders),
        offending=_bounded(offenders),
        detail=(
            f"extraction quality holds across {len(rows)} document(s)"
            if ok
            else f"{len(offenders)} document(s) with empty or HTML-as-body text"
        ),
    )


def _check_budget(con: Any, db_path: str, governor: Optional[BudgetGovernor]) -> CheckResult:
    """(e) Corpus is within the SPR-09 budget ceiling.

    Composes ``substrate.ingest_budget.BudgetGovernor`` — the same governor the
    continuous engine consults — rather than re-deriving any ceiling. The DB
    artifact size is the corpus-size dimension the audit owns (doc/chunk counts
    are reported in the summary; the binding ceiling on artifact growth is the
    governor's DB-size guard). The governor's verdict is HALT when the DB has
    crossed the hard ceiling; check (e) fails on HALT.

    Disk-free and process-RSS dimensions of the governor are box-runtime
    properties, not corpus properties, so for the standing corpus audit we read
    ONLY the DB-size dimension against the live file (an unreadable/absent dim is
    unconstrained — the governor never fabricates a number). A caller may pass a
    pre-configured ``governor`` (a test injects a tiny ceiling to plant an
    over-budget violation)."""
    gov = governor or BudgetGovernor(db_path=db_path)
    db_size = _db_file_size(db_path)
    # Read ONLY the DB-size dimension (corpus artifact growth); the disk/RSS
    # dimensions are box-runtime, not corpus, so we mark them unconstrained (-1)
    # for the standing corpus audit.
    from substrate.ingest_budget import BudgetReading

    reading = BudgetReading(free_disk_bytes=-1, db_size_bytes=db_size, rss_bytes=-1)
    verdict = gov.check(reading)
    over = verdict.state is BudgetState.HALT
    return CheckResult(
        name=CHECK_BUDGET,
        ok=not over,
        count=1 if over else 0,
        offending=(("db_size_bytes=%d" % db_size,) if over else ()),
        detail=(
            f"corpus within SPR-09 budget ceiling ({verdict.render()})"
            if not over
            else f"corpus OVER the SPR-09 budget ceiling: {verdict.render()}"
        ),
    )


def _db_file_size(db_path: str) -> int:
    try:
        return int(os.path.getsize(db_path))
    except (OSError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# THE BINDING — the static, non-DB assertion (SPR-10's headline enforcement).
# ---------------------------------------------------------------------------

# The connector packages whose content_class assignments must come ONLY from
# classify() (the public-corpus rights family) PLUS the third-party reading
# connectors whose content_class must come from an imported constant, never a
# string literal (Personal-Reading Lane SPR-02). The bypass-scanner flags only
# NON-EMPTY string LITERALS, so the constant-based M1-M3 connector edits
# (content_class=PERSONAL_READING_CONTENT_CLASS, an ast.Name) do NOT trip it —
# but a FUTURE connector under one of these dirs that re-introduces
# content_class="..." (a literal) WILL. "substack" is listed ahead of its SPR-06
# connector landing: the scanner skips a dir that does not yet exist
# (assert_no_content_class_bypass: ``if not sub_dir.is_dir(): continue``), so the
# allowlist is ready the moment acquisition/substack/ appears.
_BINDING_DIRS = (
    "books",
    "textbooks",
    "papers",
    "opt_in",
    "urls",
    "youtube",
    "twitter",
    "substack",
)
_BINDING_ROOT = "acquisition"


@dataclass(frozen=True)
class BindingResult:
    """Result of the static content_class-bypass assertion. ``ok`` iff zero
    connectors assign content_class to a string literal that bypasses
    classify(). ``offending`` lists ``path:line`` for each literal found."""

    ok: bool
    offending: tuple[str, ...]
    files_scanned: int

    @property
    def count(self) -> int:
        return len(self.offending)


class _ContentClassLiteralVisitor(ast.NodeVisitor):
    """Find every ``content_class=<string literal>`` that bypasses classify().

    The detector is SEMANTIC, not a grep: it walks the AST so docstrings and
    ``.md`` prose are never parsed as code (a string in a docstring is an
    ``ast.Expr`` statement, never a keyword named ``content_class``), and a
    FORWARD of a classify()-derived value is recognised and allowed.

    FLAGGED (the retired anti-pattern — a second chokepoint):
      * a keyword argument ``content_class="public_domain"`` (a non-empty string
        literal) at ANY call site — the live leak at
        ``public_domain.py``'s ``ingest_servable_book(..., content_class="public_domain")``;
      * an assignment ``content_class = "public_domain"`` to a non-empty string
        literal.

    ALLOWED (a classify()-derived value forwarded — the correct pattern):
      * ``content_class=decision.content_class`` / ``classification.content_class``
        / ``result.content_class`` (any attribute access);
      * ``content_class=some_name`` (a variable the connector already bound from
        a classify() result; the classify() chokepoint decided it upstream);
      * ``content_class=classify(...).content_class`` (a direct call result);
      * ``content_class=""`` — the empty-string literal, which is the documented
        marker on a body-less SKIP outcome (never an ingest), explicitly left
        alone by the spec.

    The ONLY thing flagged is a NON-EMPTY string literal — the exact shape of
    the retired ``content_class="public_domain"`` anti-pattern."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.offending: list[str] = []

    def _flag_if_literal(self, value: ast.AST, lineno: int) -> None:
        if (
            isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and value.value != ""  # "" is the documented skip-outcome marker
        ):
            self.offending.append(f"{self.path}:{lineno} content_class={value.value!r}")

    def visit_Call(self, node: ast.Call) -> None:
        for kw in node.keywords:
            if kw.arg == "content_class":
                self._flag_if_literal(kw.value, getattr(kw.value, "lineno", node.lineno))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "content_class":
                self._flag_if_literal(node.value, node.lineno)
            elif isinstance(target, ast.Attribute) and target.attr == "content_class":
                self._flag_if_literal(node.value, node.lineno)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        target = node.target
        if (
            node.value is not None
            and isinstance(target, ast.Name)
            and target.id == "content_class"
        ):
            self._flag_if_literal(node.value, node.lineno)
        self.generic_visit(node)


def _acquisition_root() -> Path:
    """The ``acquisition/`` directory next to this package (repo-relative)."""
    return Path(__file__).resolve().parent.parent / _BINDING_ROOT


def assert_no_content_class_bypass(root: Optional[str] = None) -> BindingResult:
    """THE BINDING: assert no connector assigns content_class outside classify().

    AST-scans every ``*.py`` under ``acquisition/{books,textbooks,papers,opt_in}/``
    and returns a :class:`BindingResult` listing any string-literal content_class
    assignment (the retired second-chokepoint anti-pattern). ``.md`` files and
    docstrings are never code, so they are structurally immune to a false flag.

    On the integrated tree BEFORE the SPR-10 fix this MUST flag
    ``acquisition/books/public_domain.py``'s
    ``ingest_servable_book(..., content_class="public_domain")``; after
    ``ingest_work`` is routed through classify() it returns ``ok=True`` with zero
    code-literal offenders. SPR-01's merge step and a CI job call this so a
    future connector that re-introduces a literal fails the build."""
    base = Path(root) if root else _acquisition_root()
    offending: list[str] = []
    files_scanned = 0
    for sub in _BINDING_DIRS:
        sub_dir = base / sub
        if not sub_dir.is_dir():
            continue
        for py_file in sorted(sub_dir.rglob("*.py")):
            files_scanned += 1
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(py_file))
            except (OSError, SyntaxError):
                continue
            rel = _display_path(py_file, base)
            visitor = _ContentClassLiteralVisitor(rel)
            visitor.visit(tree)
            offending.extend(visitor.offending)
    return BindingResult(
        ok=not offending,
        offending=tuple(offending),
        files_scanned=files_scanned,
    )


def _display_path(py_file: Path, base: Path) -> str:
    """A short, stable ``acquisition/<sub>/<file>`` path for offender reporting."""
    try:
        return os.path.join(_BINDING_ROOT, str(py_file.relative_to(base)))
    except ValueError:
        return str(py_file)


# ---------------------------------------------------------------------------
# The one entrypoint — run_audit(db_path) -> AuditResult.
# ---------------------------------------------------------------------------


def run_audit(
    db_path: str,
    *,
    governor: Optional[BudgetGovernor] = None,
    include_binding: bool = True,
) -> AuditResult:
    """Open ``db_path`` READ-ONLY and run all five corpus checks (+ the static
    BINDING assertion), returning a structured :class:`AuditResult`.

    This is the importable form SPR-01's merge step and a CI job both call. It
    opens exactly ONE read-only connection (``connect_read``) for the whole
    audit and never writes — safe to run against the live DB while the API
    serves. ``governor`` lets a caller inject a budget governor (a test plants a
    tiny ceiling); ``include_binding`` folds THE BINDING's static result into the
    overall verdict (the merge step wants both gates in one call)."""
    con = connect_read(db_path)
    try:
        checks = [
            _check_servable_basis(con),
            _check_gated_leak(con),
            _check_dedup(con),
            _check_extraction(con),
            _check_budget(con, db_path, governor),
            _check_third_party_servable(con),
        ]
    finally:
        con.close()

    ok = all(c.ok for c in checks)
    if include_binding:
        binding = assert_no_content_class_bypass()
        if not binding.ok:
            ok = False
            checks.append(
                CheckResult(
                    name="content_class_binding",
                    ok=False,
                    count=binding.count,
                    offending=binding.offending,
                    detail=(
                        f"{binding.count} connector(s) assign content_class by a "
                        "string literal, bypassing classify()"
                    ),
                )
            )
        else:
            checks.append(
                CheckResult(
                    name="content_class_binding",
                    ok=True,
                    count=0,
                    offending=(),
                    detail=(
                        f"all {binding.files_scanned} connector(s) route content_class "
                        "through classify()"
                    ),
                )
            )
    return AuditResult(ok=ok, db_path=db_path, checks=tuple(checks))


# ---------------------------------------------------------------------------
# Dashboard / summary — reads read-only, reuses the AuditResult verdict.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorpusSummary:
    """Truthful corpus-state snapshot for the operator dashboard (M5).

    All counts are read READ-ONLY off the live DB. The ``verdict`` line is
    sourced from the M2 :class:`AuditResult` — NOT recomputed — so the summary
    and the audit can never disagree (one source of truth)."""

    db_path: str
    total_docs: int
    db_size_bytes: int
    total_chunks: int
    servable_docs: int
    gated_docs: int
    by_source: tuple[tuple[str, int], ...]
    verdict_ok: bool
    verdict_failed_checks: tuple[str, ...]

    def render(self) -> str:
        lines = [
            f"Corpus state @ {self.db_path}",
            f"  total documents : {self.total_docs}",
            f"  DB size         : {self.db_size_bytes} bytes",
            f"  total chunks    : {self.total_chunks}",
            f"  servable / gated: {self.servable_docs} / {self.gated_docs}",
            "  by source:",
        ]
        if self.by_source:
            for src, n in self.by_source:
                lines.append(f"    {src}: {n}")
        else:
            lines.append("    (none)")
        verdict = "PASS" if self.verdict_ok else "FAIL"
        lines.append(f"  last audit      : {verdict}")
        if not self.verdict_ok:
            lines.append(f"    failed checks : {', '.join(self.verdict_failed_checks)}")
        return "\n".join(lines)


def summarize_corpus(
    db_path: str,
    *,
    audit: Optional[AuditResult] = None,
    governor: Optional[BudgetGovernor] = None,
) -> CorpusSummary:
    """Build the corpus-state summary. Runs the audit (if not provided) so the
    verdict line is the SAME object the audit returns — never a recomputed
    verdict. Read-only throughout."""
    result = audit or run_audit(db_path, governor=governor)
    con = connect_read(db_path)
    try:
        (total_docs,) = con.execute("SELECT COUNT(*) FROM documents").fetchone()
        (total_chunks,) = con.execute("SELECT COUNT(*) FROM chunks").fetchone()
        placeholders = ", ".join("?" for _ in SERVABLE_CONTENT_CLASSES)
        (servable_docs,) = con.execute(
            f"SELECT COUNT(*) FROM documents WHERE content_class IN ({placeholders})",
            list(SERVABLE_CONTENT_CLASSES),
        ).fetchone()
        # Gated = everything not in the servable allowlist (NULL / restricted /
        # unrecognised) — the deny-by-default complement.
        (gated_docs,) = con.execute(
            f"SELECT COUNT(*) FROM documents WHERE content_class IS NULL "
            f"OR content_class NOT IN ({placeholders})",
            list(SERVABLE_CONTENT_CLASSES),
        ).fetchone()
        by_source_rows = con.execute(
            """
            SELECT COALESCE(source_uri, '(unknown)') AS src, COUNT(*) AS n
              FROM documents GROUP BY 1 ORDER BY 2 DESC, 1
            """
        ).fetchall()
    finally:
        con.close()
    by_source = tuple((str(_source_label(src)), int(n)) for src, n in by_source_rows)
    return CorpusSummary(
        db_path=db_path,
        total_docs=int(total_docs),
        db_size_bytes=_db_file_size(db_path),
        total_chunks=int(total_chunks),
        servable_docs=int(servable_docs),
        gated_docs=int(gated_docs),
        by_source=by_source,
        verdict_ok=result.ok,
        verdict_failed_checks=tuple(c.name for c in result.failed_checks),
    )


# Coarse source label from a source_uri host, so the by-source line groups by
# the connector family (gutenberg / archive.org / arxiv / a publisher host)
# rather than fanning out one bucket per document URL.
def _source_label(source_uri: Optional[str]) -> str:
    if not source_uri:
        return "(unknown)"
    s = str(source_uri)
    for host, label in (
        ("gutenberg.org", "project_gutenberg"),
        ("archive.org", "archive_org"),
        ("arxiv.org", "arxiv"),
        ("standardebooks.org", "standard_ebooks"),
        ("wikisource.org", "wikisource"),
        ("hathitrust.org", "hathitrust"),
        ("loc.gov", "library_of_congress"),
        ("doi.org", "open_access"),
        ("opt_in:", "publisher_opt_in"),
    ):
        if host in s:
            return label
    return s


# ---------------------------------------------------------------------------
# CLI — python -m substrate.corpus_audit --db-path <p> [--summary] [--json]
# ---------------------------------------------------------------------------


def _print_audit(result: AuditResult, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
        return
    verdict = "PASS" if result.ok else "FAIL"
    print(f"corpus audit: {verdict}  ({result.db_path})")
    for c in result.checks:
        mark = "ok " if c.ok else "FAIL"
        print(f"  [{mark}] {c.name}: {c.detail}")
        if not c.ok and c.offending:
            for off in c.offending:
                print(f"        - {off}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m substrate.corpus_audit",
        description=(
            "Standing corpus audit — prove the live corpus is rights-correct + "
            "clean (read-only). Exits 0 only when every check passes."
        ),
    )
    parser.add_argument(
        "--db-path",
        required=True,
        help=(
            "Path to the live DuckDB. MUST be the same DB the systemd units' "
            "ANTIEK_DUCKDB_PATH points at (see corpus-mass-ingest.md preflight 1)."
        ),
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help=(
            "Print the corpus-state dashboard (size / servable-gated split / "
            "by-source / last-audit verdict) instead of the bare check list. "
            "The verdict is sourced from the same AuditResult (one source of truth)."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON (for CI / the dashboard).",
    )
    args = parser.parse_args(argv)

    db_path = os.path.expanduser(args.db_path)
    if not os.path.exists(db_path):
        print(f"corpus audit: db not found at {db_path}", file=sys.stderr)
        return 2

    result = run_audit(db_path)

    if args.summary:
        summary = summarize_corpus(db_path, audit=result)
        if args.json:
            print(
                json.dumps(
                    {
                        "summary": {
                            "db_path": summary.db_path,
                            "total_docs": summary.total_docs,
                            "db_size_bytes": summary.db_size_bytes,
                            "total_chunks": summary.total_chunks,
                            "servable_docs": summary.servable_docs,
                            "gated_docs": summary.gated_docs,
                            "by_source": [list(x) for x in summary.by_source],
                            "verdict_ok": summary.verdict_ok,
                            "verdict_failed_checks": list(summary.verdict_failed_checks),
                        }
                    },
                    indent=2,
                )
            )
        else:
            print(summary.render())
    else:
        _print_audit(result, as_json=args.json)

    # Exit 0 ONLY when all checks pass; non-zero on any failure so a merge step
    # or CI job hard-blocks go-live.
    return 0 if result.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
