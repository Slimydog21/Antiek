"""Per-second frame-attention accrual + house-second rule (SPR-05 M4/M5).

Turns a window's per-second frame-attention batch (the
:class:`~substrate.ad_inventory.frame_attention.WindowFrameBatch` contract) into
APPEND-ONLY, TRACEABLE accrual down to ``ip_holder``, and records the leftover
as HOUSE SECONDS the platform pockets — so a window reconciles EXACTLY:

    Σ per-asset accrual cents  +  Σ house-second cents  ==  window ad value cents

This module ACCRUES; it never disburses (disbursement is operator-gated G2/G3 —
see ``ip_holders.accrue_escrow`` / ``speak/contributor.attempt_disbursement``).
The 70/30 split (``payout.py``) and Stripe Connect are untouched.

PERSISTENCE CHOICE (justified — rigor #4):
A per-second frame accrual is keyed by (window, asset) over a window's seconds,
which maps cleanly onto a queryable, replayable TABLE — exactly the reasoning
``attribution_audit.py`` gives for choosing a dedicated table over the typed
event log (the event log is investigation-scoped JSONL; this is not investigation
state). So we persist to two dedicated append-only tables —
``frame_attention_accruals`` (one row per window+asset) and ``house_seconds``
(one row per window) — mirroring ``attribution_audit``/``speak_accruals``:
defensive ``ensure_table``, deterministic idempotent PK, version stamps, replay.

AGGREGATION BEFORE THE WRITER (rigor #4 — designed before the writer):
The window batch is reduced IN MEMORY to per-asset summed weights and a house
total, THEN written as ≤ (1 row per eligible asset) + (≤1 house row). Never one
row per second, never seconds × assets rows. ``test_frame_attention_accrual``
asserts write count ≪ seconds × assets.

ESCROW (single-writer seam #3):
Each per-asset accrual routes to its ip_holder's escrow via the ONE sanctioned
writer ``ip_holders.accrue_escrow`` (pre-onboarded holders included; no payout
until claimed). This module is added to ``_SANCTIONED_ESCROW_CALLERS`` in
``tests/test_seam_single_escrow_writer.py`` — the seam's intended path for a new
sanctioned revenue source. House seconds accrue to NO contributor (the platform
keeps them); they are recorded explicitly, never silently dropped.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from substrate import ip_holders
from substrate.anti_gaming.frame_ivt import classify_batch
from substrate.anti_gaming.verdict import FraudVerdictKind

from .frame_attention import (
    FRAME_WEIGHTING_VERSION,
    WindowFrameBatch,
    apportion_cents,
    weigh_second,
)


def _canonical_json(obj: Any) -> str:
    """Deterministic JSON (sorted keys, tight separators) — mirrors
    ``attribution_audit._canonical_json`` so the input snapshot serializes
    identically every time and the replay compares against a stable byte
    string."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _batch_ref(window_id: str, inputs_json: str) -> str:
    """Deterministic ref for a window batch from (window_id, canonical inputs).
    An identical batch collapses to the same accrual rows (idempotent
    re-record); a changed input produces distinct rows — never an in-place
    mutation (append-only)."""
    h = hashlib.sha256(
        f"{window_id}\x00{inputs_json}".encode()
    ).hexdigest()[:24]
    return f"frame-batch-{h}"


# ---------------------------------------------------------------------------
# Schema (defensive ensure_table; canonical DDL mirrors speak_accruals)
# ---------------------------------------------------------------------------


def ensure_tables(con: Any) -> None:
    """Defensive table create for the two append-only ledgers. Idempotent."""
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS frame_attention_accruals (
                accrual_id         TEXT PRIMARY KEY,
                batch_ref          TEXT NOT NULL,
                window_id          TEXT NOT NULL,
                asset_id           TEXT NOT NULL,
                chunk_id           TEXT,
                ip_holder_id       TEXT,
                summed_weight      DOUBLE NOT NULL DEFAULT 0.0,
                amount_usd         DECIMAL(18, 6) NOT NULL DEFAULT 0,
                amount_cents       INTEGER NOT NULL DEFAULT 0,
                n_seconds          INTEGER NOT NULL DEFAULT 0,
                telemetry_version  TEXT NOT NULL,
                weighting_version  TEXT NOT NULL,
                inputs_json        TEXT NOT NULL,
                accrued_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_frame_accruals_window "
            "ON frame_attention_accruals(window_id)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_frame_accruals_holder "
            "ON frame_attention_accruals(ip_holder_id)"
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS house_seconds (
                house_id             TEXT PRIMARY KEY,
                batch_ref            TEXT NOT NULL,
                window_id            TEXT NOT NULL,
                n_seconds            INTEGER NOT NULL DEFAULT 0,
                amount_cents         INTEGER NOT NULL DEFAULT 0,
                reason               TEXT NOT NULL,
                telemetry_version    TEXT NOT NULL,
                weighting_version    TEXT NOT NULL,
                inputs_json          TEXT NOT NULL,
                fraud_verdict        TEXT NOT NULL DEFAULT 'pass',
                excluded_counts_json TEXT NOT NULL DEFAULT '[]',
                accrued_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # AFA-S2 M5: forward-compat for a house_seconds table created before the
        # anti-gaming audit columns existed (a pre-M5 DB). No-op on a fresh table
        # that already has them. NOTE: DuckDB's ALTER ... ADD COLUMN does NOT
        # support column CONSTRAINTS ("Adding columns with constraints not yet
        # supported"), so these are added NULLABLE (unlike the CREATE above, which
        # can carry NOT NULL DEFAULT). Pre-existing rows therefore read NULL for
        # these columns; _load_window_accrual coalesces NULL -> "pass"/[]. New
        # rows always INSERT a concrete value, so the live path is never NULL.
        con.execute(
            "ALTER TABLE house_seconds ADD COLUMN IF NOT EXISTS fraud_verdict TEXT"
        )
        con.execute(
            "ALTER TABLE house_seconds ADD COLUMN IF NOT EXISTS excluded_counts_json TEXT"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_house_seconds_window "
            "ON house_seconds(window_id)"
        )
        # Ad-pipeline gap S1 (frame-telemetry-v3): the client-hint ledger. A
        # client-supplied ``ad_value_usd_cents`` is accepted on the wire as an
        # IGNORED HINT and logged here for auditability (fraud investigation:
        # what the client CLAIMED vs what the server minted). It NEVER feeds
        # the accrual — ``WindowFrameBatch.ad_value_usd_cents`` is minted
        # server-side only. Append-only; keyed by (batch_ref, hint) so an
        # exact retry collapses to one row while a retry that CHANGES its
        # claim appends (the changing claim is itself the interesting event).
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS frame_telemetry_client_hints (
                hint_id                         TEXT PRIMARY KEY,
                window_id                       TEXT NOT NULL,
                batch_ref                       TEXT NOT NULL,
                client_hint_ad_value_usd_cents  INTEGER NOT NULL
                    CHECK (client_hint_ad_value_usd_cents >= 0),
                telemetry_version               TEXT NOT NULL,
                received_at                     TIMESTAMP NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_frame_client_hints_window "
            "ON frame_telemetry_client_hints(window_id)"
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Aggregation (in memory, BEFORE the writer)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrameAccrualLine:
    """One window+asset accrual line (post-aggregation). ``summed_weight`` is
    the sum of this asset's per-second normalized weights across the window;
    ``amount_cents`` is its conserved slice of the window ad value."""

    window_id: str
    asset_id: str
    chunk_id: str | None
    ip_holder_id: str | None
    summed_weight: float
    amount_cents: int
    n_seconds: int


@dataclass(frozen=True)
class HouseLine:
    """The window's house-second tally (post-aggregation). ``amount_cents`` is
    what the platform pockets (the seconds with no eligible asset in frame)."""

    window_id: str
    n_seconds: int
    amount_cents: int
    reason: str


@dataclass(frozen=True)
class WindowAccrual:
    """The full reconciled result of accruing one window batch."""

    batch_ref: str
    window_id: str
    total_ad_value_cents: int
    asset_lines: tuple[FrameAccrualLine, ...]
    house: HouseLine
    telemetry_version: str
    weighting_version: str
    # AFA-S2 M5: the anti-gaming filter's REPORTED exclusions for this window —
    # (reason, count) pairs (GIVT/SIVT/oversized). Every second the filter
    # removed is counted here, never silently dropped (honesty over coverage).
    # Empty when nothing was filtered. Defaulted so pre-M5 callers/rows are
    # unaffected; M5b persists these alongside the accrual rows.
    excluded_second_counts: tuple[tuple[str, int], ...] = ()
    # The window's composite fraud verdict kind ("pass"/"review"/"block"). A
    # "review" window still accrues (to escrow, operator queue); a "block" window
    # routes its whole value to house.
    fraud_verdict: str = FraudVerdictKind.PASS.value

    def reconciles(self) -> bool:
        """Σ asset cents + house cents == total ad value cents (the invariant)."""
        return (
            sum(line.amount_cents for line in self.asset_lines) + self.house.amount_cents
            == self.total_ad_value_cents
        )


def aggregate_window(
    batch: WindowFrameBatch,
    *,
    asset_to_ip_holder: dict[str, str | None] | None = None,
) -> WindowAccrual:
    """Reduce a window batch to per-asset accrual + a house tally, conserved to
    the cent — PURE (no DB). The accrual writer calls this, then persists.

    Method:
      1. The window's total ad value is split EQUALLY across its seconds
         (each second is worth ``total / n_seconds``, conserved by
         largest-remainder so the per-second cents sum back to the total).
      2. Each second is weighed (:func:`weigh_second`): a house second's whole
         cents go to the house tally; an eligible second's cents are
         apportioned across its eligible assets by their normalized weights
         (largest-remainder, conserved to the cent).
      3. Per-asset cents are summed across the window into one line per asset;
         per-asset weights are summed too (the per-second granularity survives
         in the summed weight, not in the row count).

    ``asset_to_ip_holder`` maps asset_id → ip_holder_id (None for unmapped/
    pre-claim). An asset in frame with no chunk still earns (it is the ASSET
    that is monetized). Conservation holds regardless of the mapping."""
    asset_to_ip_holder = asset_to_ip_holder or {}
    n_seconds = len(batch.seconds)
    total = batch.ad_value_usd_cents

    if n_seconds == 0:
        # No seconds at all: the entire ad value is a house second (empty
        # window). Recorded explicitly, never dropped.
        return WindowAccrual(
            batch_ref="",  # set by caller after canonicalization
            window_id=batch.window_id,
            total_ad_value_cents=total,
            asset_lines=(),
            house=HouseLine(
                window_id=batch.window_id,
                n_seconds=0,
                amount_cents=total,
                reason="empty_window_no_seconds",
            ),
            telemetry_version=batch.schema_version,
            weighting_version=FRAME_WEIGHTING_VERSION,
        )

    # AFA-S2 M5 — filter-before-allocate. Classify the batch; invalid seconds are
    # excluded from BOTH the numerator and the denominator of the split (they do
    # not earn AND do not dilute the per-second value). A BLOCK verdict or a
    # fully-filtered window routes the whole value to house — never invented
    # attribution. Every excluded second is counted and reported, never dropped.
    classification = classify_batch(batch)
    excluded = tuple(sorted(classification.counts_by_reason().items()))
    verdict_kind = classification.window_verdict.kind

    if verdict_kind is FraudVerdictKind.BLOCK:
        return _house_only_window(
            batch, total, reason="antigaming_block",
            excluded=excluded, verdict_kind=verdict_kind,
        )

    # Valid seconds keyed by POSITION (not second_index): position is unique and
    # contiguous, so the split is robust to gaps/duplicates and invalid positions
    # are simply absent from the denominator.
    valid = [
        (pos, sec)
        for pos, sec in enumerate(batch.seconds)
        if pos in classification.valid_positions
    ]
    if not valid:
        return _house_only_window(
            batch, total, reason="antigaming_all_seconds_filtered",
            excluded=excluded, verdict_kind=verdict_kind,
        )

    # Split the window's total ad value equally across its VALID seconds,
    # conserved to the cent (largest-remainder over equal weights).
    per_second_cents = apportion_cents({str(pos): 1.0 for pos, _ in valid}, total)

    asset_cents: dict[str, int] = {}
    asset_weight: dict[str, float] = {}
    asset_chunk: dict[str, str | None] = {}
    asset_nsec: dict[str, int] = {}
    house_cents = 0
    house_nsec = 0
    house_reasons: set[str] = set()

    for pos, sec in valid:
        sec_cents = per_second_cents[str(pos)]
        w = weigh_second(sec)
        if w.is_house_second:
            house_cents += sec_cents
            house_nsec += 1
            if not sec.samples:
                house_reasons.add("empty_or_no_assets_in_frame")
            else:
                house_reasons.add("no_eligible_asset_in_frame")
            continue
        # Eligible second: apportion this second's cents across eligible assets
        # by their normalized weights (Decimal weights → float for the rounding
        # primitive; the primitive conserves to the cent regardless).
        weights = {aw.asset_id: float(aw.weight) for aw in w.eligible_weights}
        split = apportion_cents(weights, sec_cents)
        for aw in w.eligible_weights:
            asset_cents[aw.asset_id] = asset_cents.get(aw.asset_id, 0) + split[aw.asset_id]
            asset_weight[aw.asset_id] = asset_weight.get(aw.asset_id, 0.0) + float(aw.weight)
            asset_chunk[aw.asset_id] = aw.chunk_id
            asset_nsec[aw.asset_id] = asset_nsec.get(aw.asset_id, 0) + 1

    asset_lines = tuple(
        FrameAccrualLine(
            window_id=batch.window_id,
            asset_id=aid,
            chunk_id=asset_chunk.get(aid),
            ip_holder_id=asset_to_ip_holder.get(aid),
            summed_weight=asset_weight[aid],
            amount_cents=asset_cents[aid],
            n_seconds=asset_nsec[aid],
        )
        for aid in sorted(asset_cents.keys())
    )

    house = HouseLine(
        window_id=batch.window_id,
        n_seconds=house_nsec,
        amount_cents=house_cents,
        reason=";".join(sorted(house_reasons)) if house_reasons else "none",
    )

    return WindowAccrual(
        batch_ref="",
        window_id=batch.window_id,
        total_ad_value_cents=total,
        asset_lines=asset_lines,
        house=house,
        telemetry_version=batch.schema_version,
        weighting_version=FRAME_WEIGHTING_VERSION,
        excluded_second_counts=excluded,
        fraud_verdict=verdict_kind.value,
    )


def _house_only_window(
    batch: WindowFrameBatch,
    total: int,
    *,
    reason: str,
    excluded: tuple[tuple[str, int], ...],
    verdict_kind: FraudVerdictKind,
) -> WindowAccrual:
    """A window whose ENTIRE value routes to house — a BLOCK verdict or a
    fully-filtered window. No contributor accrues (never invented attribution);
    the whole ad value is the house tally, and the exclusion counts + verdict are
    carried for the audit trail. Conservation is trivially exact (house == total,
    no asset lines)."""
    return WindowAccrual(
        batch_ref="",
        window_id=batch.window_id,
        total_ad_value_cents=total,
        asset_lines=(),
        house=HouseLine(
            window_id=batch.window_id,
            n_seconds=len(batch.seconds),
            amount_cents=total,
            reason=reason,
        ),
        telemetry_version=batch.schema_version,
        weighting_version=FRAME_WEIGHTING_VERSION,
        excluded_second_counts=excluded,
        fraud_verdict=verdict_kind.value,
    )


# ---------------------------------------------------------------------------
# Input snapshot (for replay) — canonical, deterministic
# ---------------------------------------------------------------------------


def _batch_inputs(
    batch: WindowFrameBatch,
    asset_to_ip_holder: dict[str, str | None],
) -> dict[str, Any]:
    """The exact inputs the aggregation consumed, in a canonical-JSON-round-
    trippable shape. Persisted on each row so :func:`replay` re-derives the
    accrual against the same inputs (mirrors attribution_audit's ``inputs``).

    ORDER IS LOAD-BEARING (AFA-S2 M5): the seconds are stored in their ORIGINAL
    order, NOT sorted by second_index. The anti-gaming filter in
    ``aggregate_window`` is order-sensitive (non-monotonic / duplicate detection
    depends on the sequence), so sorting the snapshot would make replay reconstruct
    a DIFFERENT (re-ordered, and thus differently-filtered) batch than the one that
    was accrued — the accrual and its replay would disagree. Preserving order keeps
    replay faithful AND keeps idempotency correct: the same batch in the same order
    yields the same ref; a re-ordered batch is a genuinely different accrual (and is
    itself caught by the filter as non-monotonic). Samples WITHIN a second are still
    sorted by asset_id — their order does not affect the filter, and weigh_second
    sorts them anyway."""
    return {
        "window_id": batch.window_id,
        "ad_value_usd_cents": batch.ad_value_usd_cents,
        "schema_version": batch.schema_version,
        "asset_to_ip_holder": {k: v for k, v in sorted(asset_to_ip_holder.items())},
        "seconds": [
            {
                "second_index": s.second_index,
                "lens": s.lens,
                "samples": [
                    {
                        "asset_id": sm.asset_id,
                        "chunk_id": sm.chunk_id,
                        "content_class": sm.content_class,
                        "viewport_area_fraction": sm.viewport_area_fraction,
                        "prominence": sm.prominence,
                        "focused_dwell_ms": sm.focused_dwell_ms,
                    }
                    for sm in sorted(s.samples, key=lambda x: x.asset_id)
                ],
            }
            for s in batch.seconds  # ORIGINAL order — see docstring
        ],
    }


# ---------------------------------------------------------------------------
# M4/M5 — the accrual writer (append-only, single-writer lock, escrow)
# ---------------------------------------------------------------------------


def accrue_window(
    con: Any,
    batch: WindowFrameBatch,
    *,
    asset_to_ip_holder: dict[str, str | None] | None = None,
) -> WindowAccrual:
    """Persist one window batch's accrual + house tally append-only and route
    each per-asset amount into its ip_holder's escrow.

    The caller MUST pass a connection obtained from
    ``runtime.db_lock.connect_write`` (the single-writer lock) — this function
    does not open its own writer (so it can participate in a larger write
    transaction and so the single-writer invariant is never violated by a
    second connection).

    Idempotent + append-only: rows are keyed by a deterministic id derived from
    the batch ref + asset, so re-accruing an identical batch is a no-op (it does
    NOT double-accrue to escrow). A changed batch is a distinct ref → distinct
    rows; a prior row is never mutated.

    Escrow: each asset line with a known ip_holder and amount > 0 routes through
    ``ip_holders.accrue_escrow`` (pre-onboarded included). House seconds accrue
    to NO contributor. Accrual ≠ disbursement — nothing leaves escrow here."""
    ensure_tables(con)
    asset_to_ip_holder = asset_to_ip_holder or {}

    inputs = _batch_inputs(batch, asset_to_ip_holder)
    inputs_json = _canonical_json(inputs)
    batch_ref = _batch_ref(batch.window_id, inputs_json)

    # Idempotency: if this exact batch already produced rows, return the stored
    # result without re-accruing (no double escrow write).
    existing = con.execute(
        "SELECT 1 FROM frame_attention_accruals WHERE batch_ref = ? "
        "UNION ALL SELECT 1 FROM house_seconds WHERE batch_ref = ? LIMIT 1",
        [batch_ref, batch_ref],
    ).fetchone()
    if existing is not None:
        return _load_window_accrual(con, batch_ref)

    result = aggregate_window(batch, asset_to_ip_holder=asset_to_ip_holder)
    # Set the real batch_ref while PRESERVING every other field — including the
    # AFA-S2 M5 audit fields (excluded_second_counts, fraud_verdict). Rebuilding
    # the dataclass by hand silently dropped them (a BLOCK window returned
    # "pass"/empty); replace() cannot.
    result = replace(result, batch_ref=batch_ref)

    # Write per-asset accrual rows (one per window+asset — write amplification
    # is bounded by the asset count, never the second count).
    for line in result.asset_lines:
        amount_usd = (Decimal(line.amount_cents) / Decimal(100)).quantize(Decimal("0.000001"))
        # NUL-joined digest key in a FLAT f-string (the backslash lives in the
        # literal part, valid on the declared py311 floor — mirrors
        # attribution_audit's id construction; a nested f-string here would be a
        # SyntaxError before 3.12).
        acc_key = f"{batch_ref}\x00{line.asset_id}".encode()
        accrual_id = f"frame-acc-{hashlib.sha256(acc_key).hexdigest()[:20]}"
        con.execute(
            """
            INSERT INTO frame_attention_accruals (
                accrual_id, batch_ref, window_id, asset_id, chunk_id,
                ip_holder_id, summed_weight, amount_usd, amount_cents,
                n_seconds, telemetry_version, weighting_version, inputs_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                accrual_id, batch_ref, line.window_id, line.asset_id, line.chunk_id,
                line.ip_holder_id, line.summed_weight, amount_usd, line.amount_cents,
                line.n_seconds, result.telemetry_version, result.weighting_version,
                inputs_json,
            ],
        )
        # Route into escrow via the ONE sanctioned writer (pre-onboarded
        # included). accrue_escrow rejects <= 0, so guard on amount > 0.
        if line.ip_holder_id is not None and amount_usd > 0:
            ip_holders.accrue_escrow(con, line.ip_holder_id, amount_usd)

    # Always write the house row (even amount 0) so the window's house decision
    # is auditable — never a silent absence.
    house_key = f"{batch_ref}\x00house".encode()
    house_id = f"frame-house-{hashlib.sha256(house_key).hexdigest()[:18]}"
    con.execute(
        """
        INSERT INTO house_seconds (
            house_id, batch_ref, window_id, n_seconds, amount_cents,
            reason, telemetry_version, weighting_version, inputs_json,
            fraud_verdict, excluded_counts_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            house_id, batch_ref, result.window_id, result.house.n_seconds,
            result.house.amount_cents, result.house.reason,
            result.telemetry_version, result.weighting_version, inputs_json,
            result.fraud_verdict,
            _canonical_json([[r, c] for r, c in result.excluded_second_counts]),
        ],
    )

    return result


def record_client_hint(
    con: Any,
    *,
    window_id: str,
    batch_ref: str,
    client_hint_ad_value_usd_cents: int,
    telemetry_version: str,
) -> str:
    """Append one client-supplied ad-value HINT to the audit ledger
    (ad-pipeline gap S1, frame-telemetry-v3).

    The wire shape re-accepts ``ad_value_usd_cents`` as an IGNORED HINT: it is
    logged here (``client_hint``) for auditability/fraud investigation and
    NEVER feeds the accrual — the server mints the value itself from its own
    fill/pricing record (``ad_routes.resolve_window_value_cents``), and a hint
    row has no economic effect whatsoever.

    Append-only + idempotent: rows are keyed by a deterministic id derived from
    (batch_ref, hint), so an exact retry collapses to one row (INSERT OR
    IGNORE) while a retry that CHANGES its claim appends a second row — a
    client that revises its claimed price is itself the audit event. The
    caller MUST hold the single-writer connection (the route calls this inside
    ``connect_write``, right after ``accrue_window``).
    """
    ensure_tables(con)
    hint_key = f"{batch_ref}\x00{client_hint_ad_value_usd_cents}".encode()
    hint_id = f"hint-{hashlib.sha256(hint_key).hexdigest()[:20]}"
    con.execute(
        """
        INSERT OR IGNORE INTO frame_telemetry_client_hints (
            hint_id, window_id, batch_ref, client_hint_ad_value_usd_cents,
            telemetry_version
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            hint_id,
            window_id,
            batch_ref,
            client_hint_ad_value_usd_cents,
            telemetry_version,
        ],
    )
    return hint_id


def _load_window_accrual(con: Any, batch_ref: str) -> WindowAccrual:
    """Reconstruct a persisted WindowAccrual from its stored rows (the read
    surface the idempotent path returns)."""
    ensure_tables(con)
    arows = con.execute(
        """
        SELECT window_id, asset_id, chunk_id, ip_holder_id, summed_weight,
               amount_cents, n_seconds, telemetry_version, weighting_version
        FROM frame_attention_accruals WHERE batch_ref = ?
        ORDER BY asset_id
        """,
        [batch_ref],
    ).fetchall()
    hrow = con.execute(
        """
        SELECT window_id, n_seconds, amount_cents, reason,
               telemetry_version, weighting_version,
               fraud_verdict, excluded_counts_json
        FROM house_seconds WHERE batch_ref = ?
        """,
        [batch_ref],
    ).fetchone()
    if hrow is None:
        raise ValueError(f"no house row for batch_ref {batch_ref!r}")
    window_id = hrow[0]
    asset_lines = tuple(
        FrameAccrualLine(
            window_id=r[0], asset_id=r[1], chunk_id=r[2], ip_holder_id=r[3],
            summed_weight=float(r[4]), amount_cents=int(r[5]), n_seconds=int(r[6]),
        )
        for r in arows
    )
    house = HouseLine(
        window_id=hrow[0], n_seconds=int(hrow[1]), amount_cents=int(hrow[2]),
        reason=hrow[3],
    )
    total = sum(line.amount_cents for line in asset_lines) + house.amount_cents
    telemetry_version = arows[0][7] if arows else hrow[4]
    weighting_version = arows[0][8] if arows else hrow[5]
    # AFA-S2 M5 audit fields — reconstruct from the persisted house row so the
    # idempotent-reload path reports the SAME verdict/exclusions as the fresh
    # accrual (a BLOCK window reloads as "block", not the "pass" default). A row
    # from a pre-M5 DB (columns added later via nullable ALTER) reads NULL here;
    # coalesce to the innocent defaults ("pass"/[]) rather than crash on
    # json.loads(None) or stamp the literal string "None".
    excluded_second_counts = tuple(
        (str(r), int(c)) for r, c in json.loads(hrow[7] or "[]")
    )
    return WindowAccrual(
        batch_ref=batch_ref,
        window_id=window_id,
        total_ad_value_cents=total,
        asset_lines=asset_lines,
        house=house,
        telemetry_version=telemetry_version,
        weighting_version=weighting_version,
        excluded_second_counts=excluded_second_counts,
        fraud_verdict=str(hrow[6]) if hrow[6] is not None else "pass",
    )


# ---------------------------------------------------------------------------
# Replay (defensibility — mirror SPR-04 attribution_audit.replay)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrameReplayResult:
    """Outcome of replaying a recorded window accrual. ``identical`` is the
    honest answer: True only when the recomputed per-asset+house cents match
    the recorded ones canonically."""

    batch_ref: str
    identical: bool
    recorded: dict[str, Any]
    recomputed: dict[str, Any]


def _accrual_signature(result: WindowAccrual) -> dict[str, Any]:
    """Canonical per-asset+house cents signature of an accrual (the thing
    replay compares — money outcome, not row metadata)."""
    return {
        "window_id": result.window_id,
        "total_ad_value_cents": result.total_ad_value_cents,
        "assets": {line.asset_id: line.amount_cents for line in result.asset_lines},
        "house_cents": result.house.amount_cents,
    }


def replay(con: Any, batch_ref: str) -> FrameReplayResult:
    """Re-derive a recorded window's accrual from its stored inputs + stamped
    weighting version and compare to what was persisted. Comparison is on
    canonical JSON so a cent difference is caught, not papered over — this is
    what lets us truthfully claim the accrual is reproducible."""
    ensure_tables(con)
    row = con.execute(
        "SELECT inputs_json, weighting_version FROM house_seconds WHERE batch_ref = ?",
        [batch_ref],
    ).fetchone()
    if row is None:
        raise ValueError(f"no recorded batch {batch_ref!r}")
    inputs = json.loads(row[0])

    # Rebuild the batch from the stored inputs and re-aggregate.
    from .frame_attention import FrameAttentionSample, FrameSecond

    seconds = tuple(
        FrameSecond(
            second_index=s["second_index"],
            lens=s["lens"],
            samples=tuple(
                FrameAttentionSample(
                    asset_id=sm["asset_id"],
                    viewport_area_fraction=sm["viewport_area_fraction"],
                    prominence=sm["prominence"],
                    focused_dwell_ms=sm["focused_dwell_ms"],
                    content_class=sm["content_class"],
                    chunk_id=sm["chunk_id"],
                )
                for sm in s["samples"]
            ),
        )
        for s in inputs["seconds"]
    )
    rebuilt = WindowFrameBatch(
        window_id=inputs["window_id"],
        seconds=seconds,
        ad_value_usd_cents=inputs["ad_value_usd_cents"],
        schema_version=inputs["schema_version"],
    )
    recomputed = aggregate_window(
        rebuilt, asset_to_ip_holder=inputs["asset_to_ip_holder"],
    )
    recorded = _load_window_accrual(con, batch_ref)

    rec_sig = _accrual_signature(recorded)
    rcm_sig = _accrual_signature(recomputed)
    identical = _canonical_json(rec_sig) == _canonical_json(rcm_sig)
    return FrameReplayResult(
        batch_ref=batch_ref,
        identical=identical,
        recorded=rec_sig,
        recomputed=rcm_sig,
    )


# ---------------------------------------------------------------------------
# Reconciliation query (read-only)
# ---------------------------------------------------------------------------


def window_reconciliation(con: Any, window_id: str) -> dict[str, int]:
    """Read-only: Σ contributor accrual cents + Σ house cents for a window, so a
    caller can assert they equal the window's total ad value (M6 invariant)."""
    ensure_tables(con)
    a = con.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM frame_attention_accruals "
        "WHERE window_id = ?",
        [window_id],
    ).fetchone()[0]
    h = con.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM house_seconds WHERE window_id = ?",
        [window_id],
    ).fetchone()[0]
    return {
        "contributor_cents": int(a),
        "house_cents": int(h),
        "total_cents": int(a) + int(h),
    }


__all__ = [
    "ensure_tables",
    "FrameAccrualLine",
    "HouseLine",
    "WindowAccrual",
    "aggregate_window",
    "accrue_window",
    "record_client_hint",
    "replay",
    "FrameReplayResult",
    "window_reconciliation",
]
