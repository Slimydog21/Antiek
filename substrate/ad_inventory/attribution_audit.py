"""Append-only attribution-audit record + A/B/C comparison surface (SPR-04 M3/M6).

The trust layer the operator named as the #1 waste mode this project prevents:
*untrustworthy attribution*. A claiming publisher (or counsel, or a regulator)
must be able to reconstruct exactly WHY they earned what they earned. This
module persists, per attribution computation, the FULL inputs + the algorithm +
a math-version stamp + the per-asset output split + a timestamp — append-only,
through the single-writer lock — so the computation can be REPLAYED months later
and yield byte/decimal-identical output (defensibility, rigor #5).

Persistence shape: a dedicated audit table (``attribution_audit``), mirroring
``decisions_log.py`` (defensive ``ensure_table``, idempotent insert on a
deterministic PK, ``load_*`` query helpers, canonical schema chunk in
``schema.py`` V10). NOT the typed event log: the event log is investigation-
scoped JSONL, but an attribution computation is keyed by impression-set + period,
which maps cleanly onto a queryable table and onto replay. See
``ATTRIBUTION_TRUST_AUDIT.md`` for the decision + reverse-if.

This module RECORDS and COMPARES. It never disburses, never writes escrow or
payout — the 70/30 split (``payout.py``) and Stripe Connect are untouched.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from .attribution import (
    ATTRIBUTION_ALGORITHM_VERSION,
    AttributionAlgorithm,
    AttributionResult,
    compute_attribution_option_a,
    compute_attribution_option_b,
    compute_attribution_option_c,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace drift. The audit record
    must serialize identically every time so the replay test compares against a
    stable byte string and so a recomputed audit_id is stable (idempotency)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _audit_id(*, impression_set_ref: str, algorithm: str, version: str,
              inputs_json: str) -> str:
    """Deterministic id from (impression-set, algorithm, version, inputs). Two
    identical computations collapse to one audit row (idempotent re-record),
    and a changed input or a bumped version produces a distinct row — never an
    in-place mutation of a prior record (append-only)."""
    h = hashlib.sha256(
        f"{impression_set_ref}\x00{algorithm}\x00{version}\x00{inputs_json}".encode()
    ).hexdigest()[:24]
    return f"attr-audit-{h}"


# The keys each algorithm's stored ``inputs`` carry. The replay function reads
# exactly these back, so a schema drift in either direction breaks replay loudly
# rather than silently attributing against the wrong inputs.
_ALGO_INPUT_KEYS: dict[str, tuple[str, ...]] = {
    AttributionAlgorithm.OPTION_A_EQUAL_SPLIT.value: ("chunk_to_document",),
    AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER.value: (
        "chunk_to_document", "chunk_to_claim_confidence", "document_to_source_tier",
    ),
    AttributionAlgorithm.OPTION_C_LOAD_BEARING.value: (
        "chunk_to_document", "claim_load_bearing_scores", "chunk_to_claim_id",
    ),
}


@dataclass(frozen=True)
class AttributionAuditRecord:
    """One persisted attribution computation. ``inputs`` is the exact kwargs the
    stamped algorithm was called with (canonical-JSON round-trippable);
    ``shares`` is the per-asset output split it produced."""

    audit_id: str
    impression_set_ref: str
    page_id: str
    algorithm: str
    algorithm_version: str
    inputs: dict[str, Any]
    shares: dict[str, float]
    computed_at: str


def ensure_table(con: Any) -> None:
    """Defensive table create. Canonical schema in ``schema.py`` V10 chunk."""
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS attribution_audit (
                audit_id            TEXT PRIMARY KEY,
                impression_set_ref  TEXT NOT NULL,
                page_id             TEXT NOT NULL,
                algorithm           TEXT NOT NULL CHECK (algorithm IN (
                    'equal_split_per_chunk_citation',
                    'claim_confidence_times_source_tier',
                    'load_bearing_via_secondary_pass'
                )),
                algorithm_version   TEXT NOT NULL,
                inputs_json         TEXT NOT NULL,
                shares_json         TEXT NOT NULL,
                computed_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_attribution_audit_impression_set "
            "ON attribution_audit(impression_set_ref)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_attribution_audit_page "
            "ON attribution_audit(page_id)"
        )
    except Exception:
        pass


def record_attribution(
    con: Any,
    *,
    impression_set_ref: str,
    result: AttributionResult,
    inputs: dict[str, Any],
    algorithm_version: str = ATTRIBUTION_ALGORITHM_VERSION,
) -> str:
    """Append one attribution-audit record and return its ``audit_id``.

    Append-only + idempotent (matching ``decisions_log.persist_decision``): the
    ``audit_id`` is derived from the inputs + algorithm + version, so re-recording
    an identical computation is a no-op returning the existing id, and a prior
    record is NEVER mutated. ``inputs`` MUST be the exact kwargs the algorithm
    was called with — the replay function feeds them straight back."""
    ensure_table(con)
    algorithm = result.algorithm.value
    expected = _ALGO_INPUT_KEYS.get(algorithm)
    if expected is not None and set(inputs.keys()) != set(expected):
        raise ValueError(
            f"inputs for {algorithm} must carry exactly {sorted(expected)}, "
            f"got {sorted(inputs.keys())} (replay would attribute against the "
            "wrong inputs otherwise)"
        )
    inputs_json = _canonical_json(inputs)
    shares_json = _canonical_json(result.shares)
    audit_id = _audit_id(
        impression_set_ref=impression_set_ref,
        algorithm=algorithm,
        version=algorithm_version,
        inputs_json=inputs_json,
    )
    existing = con.execute(
        "SELECT audit_id FROM attribution_audit WHERE audit_id = ?",
        [audit_id],
    ).fetchone()
    if existing is not None:
        return audit_id
    con.execute(
        """
        INSERT INTO attribution_audit (
            audit_id, impression_set_ref, page_id, algorithm,
            algorithm_version, inputs_json, shares_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            audit_id, impression_set_ref, result.page_id, algorithm,
            algorithm_version, inputs_json, shares_json,
        ],
    )
    return audit_id


def _row_to_record(r: tuple) -> AttributionAuditRecord:
    return AttributionAuditRecord(
        audit_id=r[0],
        impression_set_ref=r[1],
        page_id=r[2],
        algorithm=r[3],
        algorithm_version=r[4],
        inputs=json.loads(r[5]),
        shares=json.loads(r[6]),
        computed_at=r[7] or "",
    )


def load_record(con: Any, audit_id: str) -> Optional[AttributionAuditRecord]:
    """Load one audit record by id (the replay entry point)."""
    ensure_table(con)
    row = con.execute(
        """
        SELECT audit_id, impression_set_ref, page_id, algorithm,
               algorithm_version, inputs_json, shares_json,
               strftime(computed_at, '%Y-%m-%dT%H:%M:%S')
        FROM attribution_audit WHERE audit_id = ?
        """,
        [audit_id],
    ).fetchone()
    return _row_to_record(row) if row is not None else None


def load_for_impression_set(
    con: Any, impression_set_ref: str,
) -> list[AttributionAuditRecord]:
    """Audit query: every recorded computation for one impression-set."""
    ensure_table(con)
    rows = con.execute(
        """
        SELECT audit_id, impression_set_ref, page_id, algorithm,
               algorithm_version, inputs_json, shares_json,
               strftime(computed_at, '%Y-%m-%dT%H:%M:%S')
        FROM attribution_audit
        WHERE impression_set_ref = ?
        ORDER BY computed_at, audit_id
        """,
        [impression_set_ref],
    ).fetchall()
    return [_row_to_record(r) for r in rows]


# ---------------------------------------------------------------------------
# Replay (M3 reproducibility) — the defensibility load-bearer
# ---------------------------------------------------------------------------


def _run_stamped_algorithm(
    *, page_id: str, algorithm: str, inputs: dict[str, Any],
) -> AttributionResult:
    """Re-run the algorithm a record was stamped with, against its recorded
    inputs. This is the single dispatch point the replay relies on — if a
    future maintainer adds an algorithm they add it here and the version stamp
    forces a new record, so an old record always replays against the math it
    was computed with."""
    if algorithm == AttributionAlgorithm.OPTION_A_EQUAL_SPLIT.value:
        return compute_attribution_option_a(
            page_id=page_id,
            chunk_to_document=inputs["chunk_to_document"],
        )
    if algorithm == AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER.value:
        return compute_attribution_option_b(
            page_id=page_id,
            chunk_to_document=inputs["chunk_to_document"],
            chunk_to_claim_confidence=inputs["chunk_to_claim_confidence"],
            document_to_source_tier=inputs["document_to_source_tier"],
        )
    if algorithm == AttributionAlgorithm.OPTION_C_LOAD_BEARING.value:
        return compute_attribution_option_c(
            page_id=page_id,
            chunk_to_document=inputs["chunk_to_document"],
            claim_load_bearing_scores=inputs["claim_load_bearing_scores"],
            chunk_to_claim_id=inputs["chunk_to_claim_id"],
        )
    raise ValueError(f"unknown algorithm in audit record: {algorithm!r}")


@dataclass(frozen=True)
class ReplayResult:
    """Outcome of replaying a recorded computation. ``identical`` is the
    honest answer: True only when the recomputed split matches the recorded one
    canonically (same keys, same float bytes)."""

    audit_id: str
    identical: bool
    recorded_shares: dict[str, float]
    recomputed_shares: dict[str, float]


def replay(con: Any, audit_id: str) -> ReplayResult:
    """Feed a recorded record's inputs to its stamped algorithm and compare the
    recomputed split to the recorded one. The comparison is on canonical JSON so
    a difference in float bytes or key set is caught (not papered over by an
    approximate compare) — this is what lets us truthfully claim "reproducible"."""
    record = load_record(con, audit_id)
    if record is None:
        raise ValueError(f"audit record {audit_id!r} not found")
    recomputed = _run_stamped_algorithm(
        page_id=record.page_id,
        algorithm=record.algorithm,
        inputs=record.inputs,
    )
    identical = _canonical_json(recomputed.shares) == _canonical_json(record.shares)
    return ReplayResult(
        audit_id=audit_id,
        identical=identical,
        recorded_shares=record.shares,
        recomputed_shares=dict(recomputed.shares),
    )


# ---------------------------------------------------------------------------
# A/B/C comparison surface (M6) — read-only
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AlgorithmComparison:
    """Per-asset A-vs-B-vs-C share comparison over one set of inputs. Read-only:
    surfaces the comparison so the OPERATOR picks the production algorithm —
    this module does not pick it and never writes to payout/escrow.

    ``default_algorithm`` records that Option B (confidence × tier) is the
    current default and why, per master-spec §9.3 (it aligns incentives toward
    quality: higher-confidence claims grounded in higher-tier sources earn more
    — see compute_attribution_option_b's docstring)."""

    page_id: str
    per_asset: dict[str, dict[str, float]]  # document_id → {"A":.., "B":.., "C":..}
    default_algorithm: str = AttributionAlgorithm.OPTION_B_CONFIDENCE_TIMES_TIER.value
    default_rationale: str = (
        "Option B (claim_confidence × source_tier) is the current default per "
        "master-spec §9.3: it aligns contributor incentives toward quality "
        "without the per-claim LLM cost of Option C. The choice is the "
        "operator's — this surface compares, it does not decide."
    )


def compare_algorithms(
    *,
    page_id: str,
    chunk_to_document: dict[str, str],
    chunk_to_claim_confidence: dict[str, float],
    document_to_source_tier: dict[str, int],
    claim_load_bearing_scores: dict[str, float],
    chunk_to_claim_id: dict[str, str],
) -> AlgorithmComparison:
    """Run all three algorithms over the SAME inputs and emit a per-asset
    A-vs-B-vs-C comparison. Read-only — does not persist, disburse, or write
    escrow. Every document appearing in ANY algorithm's split is present in the
    table, with 0.0 for an algorithm that gave it no share (an honest 0, not an
    absence)."""
    a = compute_attribution_option_a(
        page_id=page_id, chunk_to_document=chunk_to_document,
    ).shares
    b = compute_attribution_option_b(
        page_id=page_id,
        chunk_to_document=chunk_to_document,
        chunk_to_claim_confidence=chunk_to_claim_confidence,
        document_to_source_tier=document_to_source_tier,
    ).shares
    c = compute_attribution_option_c(
        page_id=page_id,
        chunk_to_document=chunk_to_document,
        claim_load_bearing_scores=claim_load_bearing_scores,
        chunk_to_claim_id=chunk_to_claim_id,
    ).shares
    all_docs = set(a) | set(b) | set(c)
    per_asset = {
        doc_id: {
            "A": a.get(doc_id, 0.0),
            "B": b.get(doc_id, 0.0),
            "C": c.get(doc_id, 0.0),
        }
        for doc_id in sorted(all_docs)
    }
    return AlgorithmComparison(page_id=page_id, per_asset=per_asset)


def comparison_to_json(cmp: AlgorithmComparison) -> dict[str, Any]:
    """Serialize the comparison to a JSON-friendly dict (the read-only API/
    report shape)."""
    return {
        "page_id": cmp.page_id,
        "default_algorithm": cmp.default_algorithm,
        "default_rationale": cmp.default_rationale,
        "per_asset": cmp.per_asset,
    }


__all__ = [
    "AlgorithmComparison",
    "AttributionAuditRecord",
    "ReplayResult",
    "compare_algorithms",
    "comparison_to_json",
    "ensure_table",
    "load_for_impression_set",
    "load_record",
    "record_attribution",
    "replay",
]
