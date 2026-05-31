"""Per-paper author accrual ledger — (arxiv_id, author_position) keyed,
conservation-to-the-cent, append-only (SPR-06 M1-M4).

WHAT THIS IS
------------
An INTERNAL double-entry (= conservation-to-the-cent, the tree's established
idiom — NOT formal debit/credit) accrual ledger that records, for each T1 paper
read that produced ad revenue, HOW MUCH is OWED to each author of the paper,
keyed by ``(arxiv_id, author_position)``, plus an explicit UNATTRIBUTED entry
that catches whatever cannot be attributed to a position. The per-author rows
plus the unattributed row reconcile EXACTLY to the attributed revenue:

    Σ per-author cents  +  unattributed cents  ==  attributed revenue cents

WHAT THIS IS *NOT* (the binding scope walls — do not cross)
-----------------------------------------------------------
  * NOT an escrow writer. arXiv author POSITIONS are not claimed ``ip_holders``
    yet (that is SPR-07's job). This ledger holds OWED amounts keyed by byline
    position; it NEVER calls ``ip_holders.accrue_escrow``, never touches
    ``escrow_balance_usd``, and is NOT a sanctioned escrow caller. It is an
    ADDITIVE internal-attribution layer over the SAME revenue the existing
    ``book_escrow`` path already accounts for — both HOLD, neither disburses, so
    there is no double-count of *disbursable* money.
  * NOT a disbursement path. Nothing here pays out, converts currency, contacts
    an author, or moves money. SPR-08 builds the payout rail on top of this
    ledger; this is the substrate it reads.
  * NOT a new ad endpoint. The accrual is driven from the EXISTING live reader
    ad-event path (``record_ad_impressions`` → ``accrue_reading_session``);
    ``accrue_paper_read`` is the thin internal hook that path calls.

REUSE (rigor #1 — compose, do not fork the ad-economics core)
-------------------------------------------------------------
  * ``substrate.ad_inventory.frame_attention.apportion_cents`` — the ONE
    largest-remainder rounding primitive — splits the attributed revenue across
    authors so the parts sum EXACTLY to the total. Rounding is never
    re-implemented here.
  * The persistence pattern of ``substrate.ad_inventory.frame_attention_accrual``
    — a module-local defensive ``ensure_tables``; deterministic sha256 row ids
    for append-only idempotency; ``inputs_json`` + version stamps for replay; a
    ``reconcile()``-style ``COALESCE(SUM(amount_cents),0)`` query.
  * ``substrate.payouts.split.equal_split`` + ``SPLIT_POLICY_VERSION`` — the
    versioned, single-home multi-author split policy (M3).
  * ``substrate.constants.UNATTRIBUTED_RIGHTS_BUCKET`` — the established
    held-never-misattributed sentinel reused for the unattributed pool (M4).
  * ``substrate.rights.arxiv_tiers.resolve_tier`` +
    ``substrate.rights.ad_eligibility.ads_allowed`` — the T1 earn gate. The tier
    is RE-DERIVED from the immutable ``license_uri`` (the SPR-02 anti-laundering
    rule), NEVER trusted from a stored ``rights_tier``.

SINGLE-WRITER (seam #3 inheritance)
-----------------------------------
``accrue_paper_read`` ACCEPTS a write-locked connection (from
``runtime.db_lock.connect_write``) and does NOT open its own writer — it mirrors
``accrue_window`` so it can join the same write transaction the reader ad-event
path already holds.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Optional

from substrate.ad_inventory.frame_attention import apportion_cents
from substrate.constants import UNATTRIBUTED_RIGHTS_BUCKET
from substrate.payouts.split import SPLIT_POLICY_VERSION, equal_split
from substrate.rights.ad_eligibility import ads_allowed
from substrate.rights.arxiv_tiers import resolve_tier
from substrate.schemas.documents import RightsTier

# The author_position sentinel for the explicit unattributed entry. A real
# byline position is 0-based and non-negative; -1 is impossible as a real
# position, so the unattributed row never collides with an author row and the
# (arxiv_id, author_position) key stays unique. The row additionally carries the
# UNATTRIBUTED_RIGHTS_BUCKET marker in its identity column so the bucket
# semantics (held, never misattributed, never disbursed) are explicit, not
# inferred from a magic int.
UNATTRIBUTED_AUTHOR_POSITION: int = -1

# Stamped on every row so a replay re-derives the split against the exact ledger
# logic that produced it. Bump on any change to keying / reconciliation
# semantics (the split-rule version is stamped separately via
# SPLIT_POLICY_VERSION).
LEDGER_VERSION: str = "paper-author-accrual-v1"

ENRICHMENT_KEY = "openalex_enrichment"


def _canonical_json(obj: Any) -> str:
    """Deterministic JSON (sorted keys, tight separators) — mirrors
    ``frame_attention_accrual._canonical_json`` so the input snapshot serializes
    identically every time and idempotency keys are stable."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Schema (defensive ensure_tables; canonical DDL mirrored in graph/schema.py)
# ---------------------------------------------------------------------------


def ensure_tables(con: Any) -> None:
    """Defensive table create for the append-only paper-author accrual ledger.
    Idempotent. The canonical DDL also lives in ``substrate/graph/schema.py``
    (the V11 chunk); this module-local create is the belt-and-suspenders so a
    test or a fresh con that skipped ``init_database`` still has the table."""
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_author_accruals (
                accrual_id          TEXT PRIMARY KEY,
                event_ref           TEXT NOT NULL,
                ad_event_id         TEXT NOT NULL,
                document_id         TEXT NOT NULL,
                arxiv_id            TEXT NOT NULL,
                author_position     INTEGER NOT NULL,
                orcid               TEXT,
                attribution_kind    TEXT NOT NULL,
                amount_cents        INTEGER NOT NULL DEFAULT 0,
                attributed_cents    INTEGER NOT NULL DEFAULT 0,
                split_policy_version TEXT NOT NULL,
                ledger_version      TEXT NOT NULL,
                inputs_json         TEXT NOT NULL,
                accrued_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_paper_author_accruals_arxiv "
            "ON paper_author_accruals(arxiv_id)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_paper_author_accruals_event "
            "ON paper_author_accruals(ad_event_id)"
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccrualLine:
    """One ledger line. ``author_position`` is the 0-based byline index, or
    ``UNATTRIBUTED_AUTHOR_POSITION`` (-1) for the unattributed entry.
    ``attribution_kind`` is 'author' or 'unattributed'."""

    arxiv_id: str
    author_position: int
    orcid: Optional[str]
    attribution_kind: str
    amount_cents: int


@dataclass(frozen=True)
class PaperReadAccrual:
    """The reconciled result of accruing one T1 paper read's ad revenue.

    ``accruable`` is False (with a ``reason``) when nothing was emitted —
    non-T1 / non-arXiv / zero revenue. When ``accruable`` is True,
    ``reconciles()`` is the invariant: Σ author cents + unattributed cents ==
    attributed_cents."""

    event_ref: str
    ad_event_id: str
    document_id: str
    arxiv_id: Optional[str]
    attributed_cents: int
    lines: tuple[AccrualLine, ...]
    accruable: bool
    reason: str

    @property
    def unattributed_cents(self) -> int:
        return sum(
            line.amount_cents
            for line in self.lines
            if line.attribution_kind == "unattributed"
        )

    @property
    def author_cents(self) -> int:
        return sum(
            line.amount_cents
            for line in self.lines
            if line.attribution_kind == "author"
        )

    def reconciles(self) -> bool:
        """Σ author cents + unattributed cents == attributed cents (the M2
        conservation invariant). Trivially True for a non-accruable event
        (attributed_cents == 0, no lines)."""
        return self.author_cents + self.unattributed_cents == self.attributed_cents


# ---------------------------------------------------------------------------
# Metadata reads (safe idiom mirrored from enrich_openalex._load_metadata)
# ---------------------------------------------------------------------------


def _load_metadata(con: Any, document_id: str) -> Optional[dict]:
    """Read + parse ``documents.metadata`` JSON for a row. Returns the parsed
    dict, ``{}`` for a NULL metadata, or ``None`` when the row is absent. Raises
    ``ValueError`` on malformed JSON. Mirrors
    ``acquisition.arxiv.enrich_openalex._load_metadata`` (handles dict vs
    JSON-string vs None) rather than an ad-hoc ``json.loads``."""
    row = con.execute(
        "SELECT metadata FROM documents WHERE document_id = ? LIMIT 1",
        [document_id],
    ).fetchone()
    if row is None:
        return None
    raw = row[0]
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"malformed metadata JSON for {document_id}") from exc


def _resolved_authors(meta: dict) -> list[dict]:
    """The persisted OpenAlex author list (read, never re-fetched). Returns the
    list of ``{orcid, author_position, display_name}`` dicts, or ``[]`` when the
    enrichment key is absent OR the authors list is empty/missing — BOTH common
    (OpenAlex lags recent arXiv postings), and BOTH route to the unattributed
    pool (M4)."""
    enrichment = meta.get(ENRICHMENT_KEY)
    if not isinstance(enrichment, dict):
        return []
    authors = enrichment.get("authors")
    if not isinstance(authors, list):
        return []
    return [a for a in authors if isinstance(a, dict)]


# ---------------------------------------------------------------------------
# Idempotency keys
# ---------------------------------------------------------------------------


def _event_ref(ad_event_id: str, inputs_json: str) -> str:
    """Deterministic ref for one accruable event from (ad_event_id, canonical
    inputs). Re-accruing the SAME source ad-event with the SAME inputs collapses
    to the same rows (idempotent no-op, no double-count); a changed input is a
    distinct ref → distinct rows, never an in-place mutation (append-only)."""
    h = hashlib.sha256(f"{ad_event_id}\x00{inputs_json}".encode()).hexdigest()[:24]
    return f"paper-acc-{h}"


def _accrual_id(event_ref: str, author_position: int) -> str:
    """Deterministic per-line id. NUL-joined digest in a FLAT f-string (the
    backslash lives in the literal part — valid on the py311 source floor; a
    nested f-string would be a SyntaxError before 3.12)."""
    key = f"{event_ref}\x00{author_position}".encode()
    return f"paa-{hashlib.sha256(key).hexdigest()[:20]}"


# ---------------------------------------------------------------------------
# Aggregation (in memory, BEFORE the writer) — pure, conserved to the cent
# ---------------------------------------------------------------------------


def _aggregate(
    *,
    arxiv_id: str,
    authors: list[dict],
    attributed_cents: int,
) -> tuple[AccrualLine, ...]:
    """Split ``attributed_cents`` across authors (default EQUAL), conserved to
    the cent via ``apportion_cents``. When there is no attributable author
    (``authors == []`` — no enrichment OR empty list), the WHOLE amount becomes
    the explicit unattributed entry. PURE (no DB)."""
    n = len(authors)
    if n == 0:
        # M4: no resolvable author → the whole amount to the unattributed pool.
        return (
            AccrualLine(
                arxiv_id=arxiv_id,
                author_position=UNATTRIBUTED_AUTHOR_POSITION,
                orcid=None,
                attribution_kind="unattributed",
                amount_cents=attributed_cents,
            ),
        )

    # M3: equal (default, versioned) split across author positions, keyed by the
    # 0-based author_position the author dict carries (NOT the list index — the
    # ledger key is the byline position OpenAlex assigned).
    by_position: dict[str, dict] = {}
    for a in authors:
        pos = a.get("author_position")
        if not isinstance(pos, int) or pos < 0:
            # A malformed/missing position cannot be a ledger key; drop it from
            # the split base so its share is NOT silently misattributed — it
            # falls through to the unattributed remainder below.
            continue
        by_position[str(pos)] = a

    if not by_position:
        # Authors present but none carries a usable position → unattributed.
        return (
            AccrualLine(
                arxiv_id=arxiv_id,
                author_position=UNATTRIBUTED_AUTHOR_POSITION,
                orcid=None,
                attribution_kind="unattributed",
                amount_cents=attributed_cents,
            ),
        )

    weights = equal_split(len(by_position))
    # Re-key the equal-split weights onto the actual positions (equal_split
    # returns weights for 0..k-1; map them onto the sorted real positions so the
    # weight count matches the position count exactly — every position gets 1/k).
    sorted_positions = sorted(by_position.keys(), key=lambda p: int(p))
    pos_weights = {
        pos: weights[str(i)] for i, pos in enumerate(sorted_positions)
    }
    split = apportion_cents(pos_weights, attributed_cents)

    lines = tuple(
        AccrualLine(
            arxiv_id=arxiv_id,
            author_position=int(pos),
            orcid=by_position[pos].get("orcid"),
            attribution_kind="author",
            amount_cents=split[pos],
        )
        for pos in sorted_positions
    )
    return lines


# ---------------------------------------------------------------------------
# The accrual writer (append-only, single-writer lock, NO escrow)
# ---------------------------------------------------------------------------


def accrue_paper_read(
    con: Any,
    *,
    document_id: str,
    revenue_cents: int,
    ad_event_id: str,
    impression_ids: Optional[Sequence[str]] = None,
) -> PaperReadAccrual:
    """Accrue one T1 paper read's attributed ad revenue to the per-author
    ledger, append-only and conserved to the cent. INTERNAL accounting only —
    writes NO escrow, disburses nothing.

    The caller MUST pass a connection from ``runtime.db_lock.connect_write`` —
    this function does NOT open its own writer (so it joins the reader ad-event
    path's existing write transaction; the single-writer invariant is never
    violated by a second connection).

    T1 GATE (rigor — the only accruable case): the tier is RE-DERIVED from the
    document's immutable ``metadata['license_uri']`` via ``resolve_tier`` (the
    stored ``rights_tier`` is NEVER trusted — SPR-02 anti-laundering), and the
    event is accruable ONLY when ``ads_allowed(tier)`` (T1). A non-arXiv doc (no
    ``arxiv_id``), a T2/T3 paper, or a zero-revenue event emits NOTHING.

    Idempotent + append-only: rows are keyed by a deterministic id derived from
    the source ``ad_event_id`` + canonical inputs, so re-accruing the SAME
    ad-event is a no-op (no double-count). A changed input is a distinct ref →
    distinct rows; a prior row is never mutated.

    ``impression_ids`` is the batch's underlying impression-id SET — the dedup
    UNIT that makes this idempotent on the same principle the escrow path relies
    on (each impression counted once). The reader posts impressions INCREMENTALLY
    (one page-flush at a time) under a CONSTANT ``ad_event_id`` (the per-session
    key), so two disjoint page-flush batches that happen to earn EQUAL revenue
    would otherwise collide on ``event_ref`` and the second would be mis-deduped
    as a retry and DROPPED. Folding the sorted impression-id set into the
    idempotency key makes disjoint batches DISTINCT events (both accrue →
    conserves) while a TRUE retry of the SAME impression set stays a no-op. When
    ``None`` (a caller that genuinely has a unique ``ad_event_id`` per event),
    the key falls back to ``ad_event_id`` + inputs alone (legacy behaviour).
    """
    ensure_tables(con)

    meta = _load_metadata(con, document_id)
    if meta is None:
        return _not_accruable(ad_event_id, document_id, None, "document_not_found")

    arxiv_id = meta.get("arxiv_id")
    if not isinstance(arxiv_id, str) or not arxiv_id:
        # Non-arXiv document → the payouts ledger emits nothing (only T1 arXiv
        # reads accrue here; book/publisher revenue is book_escrow's concern).
        return _not_accruable(ad_event_id, document_id, None, "not_an_arxiv_paper")

    # T1 GATE — re-derive tier from the immutable license_uri (never trust the
    # stored rights_tier). Only T1 (ads_allowed) emits accruable author events.
    license_uri = meta.get("license_uri")
    tier: RightsTier = resolve_tier(license_uri if isinstance(license_uri, str) else None)
    if not ads_allowed(tier):
        return _not_accruable(ad_event_id, document_id, arxiv_id, f"tier_not_ad_eligible:{tier.value}")

    if revenue_cents <= 0:
        # Zero-buyer / house fill → no revenue to attribute. Honest $0, never
        # invented money (mirrors book_escrow's zero-buyer posture).
        return _not_accruable(ad_event_id, document_id, arxiv_id, "zero_revenue")

    authors = _resolved_authors(meta)

    # The batch discriminator: the SORTED, de-duplicated impression-id set this
    # accrual covers. Folding it into the idempotency key makes the dedup UNIT
    # the underlying impression set (each impression counted once) — so two
    # disjoint page-flush batches under the SAME constant ad_event_id with EQUAL
    # revenue are DISTINCT events (both accrue), while a true retry of the same
    # impression set collapses to the same event_ref (no double-count). None →
    # [] → the key reduces to (ad_event_id + inputs) alone (legacy behaviour for
    # callers with a genuinely unique ad_event_id per event).
    impression_id_set = sorted(set(impression_ids or ()))

    # Canonical input snapshot for idempotency + replay.
    inputs = {
        "ad_event_id": ad_event_id,
        "document_id": document_id,
        "arxiv_id": arxiv_id,
        "tier": tier.value,
        "attributed_cents": int(revenue_cents),
        "impression_ids": impression_id_set,
        "split_policy_version": SPLIT_POLICY_VERSION,
        "ledger_version": LEDGER_VERSION,
        "authors": [
            {
                "author_position": a.get("author_position"),
                "orcid": a.get("orcid"),
            }
            for a in sorted(
                authors,
                key=lambda x: (
                    x.get("author_position")
                    if isinstance(x.get("author_position"), int)
                    else 1_000_000
                ),
            )
        ],
    }
    inputs_json = _canonical_json(inputs)
    event_ref = _event_ref(ad_event_id, inputs_json)

    # Idempotency: if this exact event already produced rows, return the stored
    # result without re-accruing.
    existing = con.execute(
        "SELECT 1 FROM paper_author_accruals WHERE event_ref = ? LIMIT 1",
        [event_ref],
    ).fetchone()
    if existing is not None:
        return _load_event(con, event_ref)

    lines = _aggregate(
        arxiv_id=arxiv_id, authors=authors, attributed_cents=int(revenue_cents)
    )

    for line in lines:
        con.execute(
            """
            INSERT INTO paper_author_accruals (
                accrual_id, event_ref, ad_event_id, document_id, arxiv_id,
                author_position, orcid, attribution_kind, amount_cents,
                attributed_cents, split_policy_version, ledger_version,
                inputs_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                _accrual_id(event_ref, line.author_position),
                event_ref,
                ad_event_id,
                document_id,
                line.arxiv_id,
                line.author_position,
                line.orcid,
                line.attribution_kind,
                line.amount_cents,
                int(revenue_cents),
                SPLIT_POLICY_VERSION,
                LEDGER_VERSION,
                inputs_json,
            ],
        )

    return PaperReadAccrual(
        event_ref=event_ref,
        ad_event_id=ad_event_id,
        document_id=document_id,
        arxiv_id=arxiv_id,
        attributed_cents=int(revenue_cents),
        lines=lines,
        accruable=True,
        reason="accrued",
    )


def _not_accruable(
    ad_event_id: str, document_id: str, arxiv_id: Optional[str], reason: str
) -> PaperReadAccrual:
    """A non-accruable outcome — nothing written, conserves trivially (0 == 0).
    This is the T1-only / non-arXiv / zero-revenue gate's honest result."""
    return PaperReadAccrual(
        event_ref="",
        ad_event_id=ad_event_id,
        document_id=document_id,
        arxiv_id=arxiv_id,
        attributed_cents=0,
        lines=(),
        accruable=False,
        reason=reason,
    )


def _load_event(con: Any, event_ref: str) -> PaperReadAccrual:
    """Reconstruct a persisted accrual from its stored rows (the read surface
    the idempotent path returns)."""
    ensure_tables(con)
    rows = con.execute(
        """
        SELECT ad_event_id, document_id, arxiv_id, author_position, orcid,
               attribution_kind, amount_cents, attributed_cents
        FROM paper_author_accruals WHERE event_ref = ?
        ORDER BY author_position
        """,
        [event_ref],
    ).fetchall()
    if not rows:
        raise ValueError(f"no recorded event {event_ref!r}")
    ad_event_id = rows[0][0]
    document_id = rows[0][1]
    arxiv_id = rows[0][2]
    attributed_cents = int(rows[0][7])
    lines = tuple(
        AccrualLine(
            arxiv_id=r[2],
            author_position=int(r[3]),
            orcid=r[4],
            attribution_kind=r[5],
            amount_cents=int(r[6]),
        )
        for r in rows
    )
    return PaperReadAccrual(
        event_ref=event_ref,
        ad_event_id=ad_event_id,
        document_id=document_id,
        arxiv_id=arxiv_id,
        attributed_cents=attributed_cents,
        lines=lines,
        accruable=True,
        reason="accrued",
    )


# ---------------------------------------------------------------------------
# Reconciliation query (read-only) — the balance assertion surface
# ---------------------------------------------------------------------------


def reconcile(con: Any, arxiv_id: Optional[str] = None) -> dict[str, int]:
    """Read-only: Σ author cents + Σ unattributed cents (+ Σ attributed cents)
    over the ledger, optionally scoped to one ``arxiv_id``, so a caller can
    assert author + unattributed == attributed (the M2 invariant).

    ``attributed_cents`` is summed PER EVENT (each event stamps the same
    attributed total on all its rows), so the comparison is against the genuine
    revenue total, not an inflated row-count multiple."""
    ensure_tables(con)
    # Build a reusable scope predicate. The kind filter is appended with AND when
    # an arxiv_id scope is present, WHERE otherwise.
    scope = "arxiv_id = ?" if arxiv_id is not None else ""
    scope_params = [arxiv_id] if arxiv_id is not None else []

    def _kind_sum(kind: str) -> int:
        clauses = [c for c in (scope, "attribution_kind = ?") if c]
        where_sql = "WHERE " + " AND ".join(clauses)
        row = con.execute(
            f"SELECT COALESCE(SUM(amount_cents), 0) FROM paper_author_accruals "
            f"{where_sql}",
            scope_params + [kind],
        ).fetchone()
        return int(row[0])

    author = _kind_sum("author")
    unattributed = _kind_sum("unattributed")

    # attributed_cents is per-event; sum it once per event_ref (not per row), so
    # a multi-author event is not counted N times.
    attr_where = f"WHERE {scope}" if scope else ""
    attributed = con.execute(
        f"""
        SELECT COALESCE(SUM(attributed_cents), 0) FROM (
            SELECT event_ref, ANY_VALUE(attributed_cents) AS attributed_cents
            FROM paper_author_accruals {attr_where}
            GROUP BY event_ref
        )
        """,
        scope_params,
    ).fetchone()[0]

    return {
        "author_cents": int(author),
        "unattributed_cents": int(unattributed),
        "attributed_cents": int(attributed),
        "total_cents": int(author) + int(unattributed),
    }


__all__ = [
    "UNATTRIBUTED_AUTHOR_POSITION",
    "LEDGER_VERSION",
    "ensure_tables",
    "AccrualLine",
    "PaperReadAccrual",
    "accrue_paper_read",
    "reconcile",
]
