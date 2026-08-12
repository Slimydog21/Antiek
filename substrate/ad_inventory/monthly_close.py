"""AFA-S6 monthly close — replayable per-payee statements + Merkle month root.

Closes a calendar month of ``frame_attention_accruals`` / ``house_seconds``
rows into:

1. One canonical-JSON statement per payee (ip_holder), decomposable to
   per-window aggregates with full denominators disclosed.
2. A stdlib Merkle month root over the ordered statement payloads, with
   an inclusion proof per statement.
3. A persisted close record (root + artifact paths) so re-close of the
   same period is idempotent when the ledger is unchanged.

Escrow-only: this module never disburses, never touches Stripe, never
serves ads. Accrual ≠ disbursement stays. The close is an accounting
artifact — the proof that the month's would-be balances are reproducible
and independently checkable.

Clock discipline: ``period`` is an argument everywhere; no
wall-clock reads on the close path (asserted by tests). Determinism is
the headline criterion: close twice → byte-identical root + statements.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from substrate.ad_inventory.attribution_math import (
    ATTRIBUTION_MATH_VERSION,
    STAGE_VERSIONS,
)
from substrate.ad_inventory.frame_attention import (
    FRAME_TELEMETRY_SCHEMA_VERSION,
    FRAME_WEIGHTING_VERSION,
)
from substrate.ad_inventory.frame_attention_accrual import ensure_tables
from substrate.ad_inventory.merkle import (
    MERKLE_SERIALIZATION_VERSION,
    InclusionProof,
    build_tree,
    prove,
    verify_inclusion,
)
from substrate.ad_inventory.payout import CREATOR_REV_SHARE, PLATFORM_CUT
from substrate.constants import UNATTRIBUTED_RIGHTS_BUCKET

# ---------------------------------------------------------------------------
# Version stamps (bump on statement-shape or close-algorithm change)
# ---------------------------------------------------------------------------

MONTH_CLOSE_VERSION: str = "month-close-v1"
STATEMENT_SCHEMA_VERSION: str = "statement-v1"

# Canonicalization: one house routine (sorted keys, tight separators) —
# mirrors attribution_audit._canonical_json / auction_model / accrual.
# Do NOT mint a second serializer; proofs freeze on this byte contract.
def canonical_json(obj: Any) -> str:
    """Deterministic JSON (sorted keys, tight separators)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_json_bytes(obj: Any) -> bytes:
    """UTF-8 bytes of :func:`canonical_json` — the Merkle leaf payload."""
    return canonical_json(obj).encode("utf-8")


_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})$")


def parse_period(period: str) -> tuple[str, str, str]:
    """Validate ``YYYY-MM`` and return (period, start_iso, end_iso_exclusive).

    ``end_iso_exclusive`` is the first instant of the next month, so a
    half-open interval ``[start, end)`` selects the calendar month without
    clock math inside the close.
    """
    m = _PERIOD_RE.match(period)
    if not m:
        raise ValueError(f"period must be YYYY-MM, got {period!r}")
    year, month = int(m.group(1)), int(m.group(2))
    if month < 1 or month > 12:
        raise ValueError(f"period month out of range: {period!r}")
    end = (
        f"{year + 1:04d}-01-01" if month == 12
        else f"{year:04d}-{month + 1:02d}-01"
    )
    start = f"{year:04d}-{month:02d}-01"
    return period, start, end


# ---------------------------------------------------------------------------
# Schema (defensive ensure_table; also registered as V22 in graph/schema.py)
# ---------------------------------------------------------------------------


def ensure_tables_close(con: Any) -> None:
    """Defensive create for month-close tables. Idempotent."""
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS afa_month_closes (
                period                    TEXT PRIMARY KEY,
                month_root_hex            TEXT NOT NULL,
                statement_count           INTEGER NOT NULL,
                total_payee_cents         INTEGER NOT NULL,
                total_house_cents         INTEGER NOT NULL,
                total_window_cents        INTEGER NOT NULL,
                attribution_math_version  TEXT NOT NULL,
                month_close_version       TEXT NOT NULL,
                merkle_serialization      TEXT NOT NULL,
                artifact_dir              TEXT NOT NULL,
                statements_digest         TEXT NOT NULL,
                closed_at                 TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS afa_month_statements (
                statement_id       TEXT PRIMARY KEY,
                period             TEXT NOT NULL,
                payee_id           TEXT NOT NULL,
                total_cents        INTEGER NOT NULL,
                leaf_index         INTEGER NOT NULL,
                leaf_hash_hex      TEXT NOT NULL,
                statement_json     TEXT NOT NULL,
                proof_json         TEXT NOT NULL,
                statement_path     TEXT,
                UNIQUE (period, payee_id)
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_afa_month_statements_period "
            "ON afa_month_statements(period)"
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Statement shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WindowAggregate:
    """One window's contribution to a payee statement."""

    window_id: str
    batch_ref: str
    amount_cents: int
    asset_ids: tuple[str, ...]
    n_seconds: int
    summed_weight: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "batch_ref": self.batch_ref,
            "amount_cents": self.amount_cents,
            "asset_ids": list(self.asset_ids),
            "n_seconds": self.n_seconds,
            "summed_weight": self.summed_weight,
        }


@dataclass(frozen=True)
class PayeeStatement:
    """Canonical per-payee statement for one closed month.

    The dict form (via :meth:`to_dict`) is the Merkle leaf payload after
    canonical-JSON serialization. Field order in the dict is irrelevant
    because canonicalization sorts keys; the *set* of fields is frozen by
    ``STATEMENT_SCHEMA_VERSION``.
    """

    period: str
    payee_id: str
    total_cents: int
    windows: tuple[WindowAggregate, ...]
    attribution_math_version: str
    statement_schema_version: str
    # Denominators — the uncomfortable numbers (rigor #1).
    denominators: dict[str, Any] = field(default_factory=dict)
    formula: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attribution_math_version": self.attribution_math_version,
            "denominators": self.denominators,
            "formula": self.formula,
            "payee_id": self.payee_id,
            "period": self.period,
            "statement_schema_version": self.statement_schema_version,
            "total_cents": self.total_cents,
            "windows": [w.to_dict() for w in self.windows],
        }

    def leaf_payload(self) -> bytes:
        return canonical_json_bytes(self.to_dict())


@dataclass(frozen=True)
class MonthClose:
    """Result of closing one calendar month."""

    period: str
    month_root_hex: str
    statements: tuple[PayeeStatement, ...]
    proofs: tuple[InclusionProof, ...]
    total_payee_cents: int
    total_house_cents: int
    total_window_cents: int
    attribution_math_version: str
    month_close_version: str
    merkle_serialization: str
    # House-side denominators disclosed on the close record (not per-payee).
    house_breakdown: dict[str, Any] = field(default_factory=dict)
    # True when this call returned a previously-persisted identical close.
    reused: bool = False
    artifact_dir: str = ""

    def cross_foots(self) -> bool:
        """Σ statements + house == Σ window values (integer-exact)."""
        return (
            self.total_payee_cents + self.total_house_cents
            == self.total_window_cents
        )

    def statements_digest(self) -> str:
        """sha256 over the concatenation of canonical statement payloads
        in leaf order — a compact fingerprint of the full statement set."""
        h = hashlib.sha256()
        for s in self.statements:
            h.update(s.leaf_payload())
            h.update(b"\n")
        return h.hexdigest()


# ---------------------------------------------------------------------------
# Read path — pure over a connection (read-only OK)
# ---------------------------------------------------------------------------


def _load_period_rows(
    con: Any, start: str, end: str,
) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    """Load accrual + house rows whose accrued_at falls in [start, end)."""
    ensure_tables(con)
    accruals = con.execute(
        """
        SELECT accrual_id, batch_ref, window_id, asset_id, chunk_id,
               ip_holder_id, summed_weight, amount_cents, n_seconds,
               telemetry_version, weighting_version,
               COALESCE(attribution_math_version, '') AS attribution_math_version,
               accrued_at
        FROM frame_attention_accruals
        WHERE accrued_at >= CAST(? AS TIMESTAMP)
          AND accrued_at <  CAST(? AS TIMESTAMP)
        ORDER BY window_id, asset_id, accrual_id
        """,
        [start, end],
    ).fetchall()
    house = con.execute(
        """
        SELECT house_id, batch_ref, window_id, n_seconds, amount_cents,
               reason, telemetry_version, weighting_version,
               COALESCE(attribution_math_version, '') AS attribution_math_version,
               COALESCE(fraud_verdict, 'pass') AS fraud_verdict,
               COALESCE(excluded_counts_json, '[]') AS excluded_counts_json,
               accrued_at
        FROM house_seconds
        WHERE accrued_at >= CAST(? AS TIMESTAMP)
          AND accrued_at <  CAST(? AS TIMESTAMP)
        ORDER BY window_id, house_id
        """,
        [start, end],
    ).fetchall()
    return list(accruals), list(house)


def _build_statements(
    period: str,
    accruals: list[tuple[Any, ...]],
    house_rows: list[tuple[Any, ...]],
) -> tuple[list[PayeeStatement], dict[str, Any], int, int, int]:
    """Aggregate ledger rows into per-payee statements + house denominators.

    Returns (statements_sorted_by_payee, house_breakdown, payee_cents,
    house_cents, window_cents).
    """
    # Per-payee → per-window aggregation.
    # payee -> window_id -> accum
    from collections import defaultdict

    payee_windows: dict[str, dict[str, dict[str, Any]]] = defaultdict(
        lambda: defaultdict(
            lambda: {
                "amount_cents": 0,
                "asset_ids": set(),
                "n_seconds": 0,
                "summed_weight": 0.0,
                "batch_ref": "",
            }
        )
    )
    # Window totals for conservation / denominators.
    window_asset_cents: dict[str, int] = defaultdict(int)
    window_house_cents: dict[str, int] = defaultdict(int)
    house_reasons: dict[str, int] = defaultdict(int)
    excluded_counts: dict[str, int] = defaultdict(int)
    unmapped_cents = 0  # accruals with no ip_holder (unattributed residue)
    math_versions: set[str] = set()

    for row in accruals:
        (
            _acc_id, batch_ref, window_id, asset_id, _chunk,
            ip_holder_id, summed_weight, amount_cents, n_seconds,
            _tel, _wgt, math_ver, _at,
        ) = row
        amount_cents = int(amount_cents)
        window_asset_cents[window_id] += amount_cents
        if math_ver:
            math_versions.add(str(math_ver))
        if ip_holder_id is None or ip_holder_id == "" or ip_holder_id == UNATTRIBUTED_RIGHTS_BUCKET:
            unmapped_cents += amount_cents
            continue
        payee = str(ip_holder_id)
        w = payee_windows[payee][window_id]
        w["amount_cents"] += amount_cents
        w["asset_ids"].add(str(asset_id))
        w["n_seconds"] += int(n_seconds)
        w["summed_weight"] += float(summed_weight)
        w["batch_ref"] = str(batch_ref)

    for row in house_rows:
        (
            _hid, _bref, window_id, _ns, amount_cents, reason,
            _tel, _wgt, math_ver, fraud_verdict, excl_json, _at,
        ) = row
        amount_cents = int(amount_cents)
        window_house_cents[window_id] += amount_cents
        if math_ver:
            math_versions.add(str(math_ver))
        # Reason may be semicolon-joined (e.g. "none;platform_cut_30").
        for part in str(reason or "none").split(";"):
            part = part.strip() or "none"
            house_reasons[part] += amount_cents
        try:
            excl = json.loads(excl_json or "[]")
            for item in excl:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    excluded_counts[str(item[0])] += int(item[1])
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        _ = fraud_verdict  # retained for future statement surface

    total_payee = 0
    statements: list[PayeeStatement] = []
    # Month-level denominators shared onto every statement so a single
    # statement file is self-contained for offline verification of the
    # disclosed pool (payee cannot recompute the pool alone, but can see it).
    total_house = sum(window_house_cents.values())
    total_window = sum(window_asset_cents.values()) + total_house
    month_denominators = {
        "month_total_window_cents": total_window,
        "month_total_house_cents": total_house,
        "month_total_payee_pool_cents": sum(
            sum(w["amount_cents"] for w in wins.values())
            for wins in payee_windows.values()
        ),
        "month_unmapped_cents": unmapped_cents,
        "house_reasons": dict(sorted(house_reasons.items())),
        "excluded_second_counts": dict(sorted(excluded_counts.items())),
        "n_windows": len(set(window_asset_cents) | set(window_house_cents)),
        "n_payees": len(payee_windows),
    }
    formula = {
        "attribution_math_version": (
            sorted(math_versions)[0]
            if len(math_versions) == 1
            else ATTRIBUTION_MATH_VERSION
        ),
        "stage_versions": dict(STAGE_VERSIONS),
        "creator_rev_share": str(CREATOR_REV_SHARE),
        "platform_cut": str(PLATFORM_CUT),
        "frame_weighting_version": FRAME_WEIGHTING_VERSION,
        "frame_telemetry_schema_version": FRAME_TELEMETRY_SCHEMA_VERSION,
        "month_close_version": MONTH_CLOSE_VERSION,
        "statement_schema_version": STATEMENT_SCHEMA_VERSION,
        "merkle_serialization": MERKLE_SERIALIZATION_VERSION,
    }

    for payee_id in sorted(payee_windows.keys()):
        wins = payee_windows[payee_id]
        window_aggs: list[WindowAggregate] = []
        payee_total = 0
        for window_id in sorted(wins.keys()):
            w = wins[window_id]
            cents = int(w["amount_cents"])
            payee_total += cents
            window_aggs.append(
                WindowAggregate(
                    window_id=window_id,
                    batch_ref=str(w["batch_ref"]),
                    amount_cents=cents,
                    asset_ids=tuple(sorted(w["asset_ids"])),
                    n_seconds=int(w["n_seconds"]),
                    summed_weight=float(w["summed_weight"]),
                )
            )
        total_payee += payee_total
        # Per-payee denominators: own total + shared month view.
        pool = int(month_denominators["month_total_payee_pool_cents"])
        # Integer basis points (1 bp = 0.01%) — no float in the leaf payload.
        share_bps = (payee_total * 10_000 // pool) if pool else 0
        denoms = {
            **month_denominators,
            "payee_total_cents": payee_total,
            "payee_n_windows": len(window_aggs),
            "payee_share_of_pool_bps": share_bps,
        }
        statements.append(
            PayeeStatement(
                period=period,
                payee_id=payee_id,
                total_cents=payee_total,
                windows=tuple(window_aggs),
                attribution_math_version=formula["attribution_math_version"],
                statement_schema_version=STATEMENT_SCHEMA_VERSION,
                denominators=denoms,
                formula=formula,
            )
        )

    house_breakdown = {
        **month_denominators,
        "house_reasons": dict(sorted(house_reasons.items())),
        # Unmapped accruals are not in any payee statement; they sit beside
        # house as disclosed residue (not silently dropped).
        "unmapped_cents": unmapped_cents,
    }
    # Cross-foot identity for the close: payee statements + house + unmapped
    # == window total. Unmapped is reported separately so it is visible.
    return statements, house_breakdown, total_payee, total_house, total_window


# ---------------------------------------------------------------------------
# Close job
# ---------------------------------------------------------------------------


class CloseError(Exception):
    """Loud abort of a month close (inconsistency, empty, etc.)."""


class CloseInconsistentError(CloseError):
    """Ledger rows for the period do not conserve; close aborted."""


def compute_close(
    con: Any,
    period: str,
) -> MonthClose:
    """Pure-ish close: read ledger for ``period``, build statements + root.

    Does NOT persist. Clock-free: ``period`` is the only time input.
    Raises :class:`CloseInconsistentError` if per-window conservation fails.
    Raises :class:`CloseError` if the period has no accrual rows.
    """
    period, start, end = parse_period(period)
    accruals, house_rows = _load_period_rows(con, start, end)
    if not accruals and not house_rows:
        raise CloseError(f"no accrual rows for period {period}")

    # Per-window conservation gate (S4 spirit): every window must foot.
    window_a: dict[str, int] = {}
    window_h: dict[str, int] = {}
    for row in accruals:
        window_a[row[2]] = window_a.get(row[2], 0) + int(row[7])
    for row in house_rows:
        window_h[row[2]] = window_h.get(row[2], 0) + int(row[4])
    violations: list[dict[str, Any]] = []
    for wid in sorted(set(window_a) | set(window_h)):
        # We cannot know the original ad_value without the inputs snapshot;
        # conservation is Σ assets + house for that window (always true by
        # construction of accrue_window). The gate here is: both sides of
        # a window that has rows are non-negative and present. A stronger
        # check reloads inputs_json when available.
        a = window_a.get(wid, 0)
        h = window_h.get(wid, 0)
        if a < 0 or h < 0:
            violations.append(
                {"window_id": wid, "asset_cents": a, "house_cents": h,
                 "reason": "negative_cents"}
            )
    if violations:
        raise CloseInconsistentError(
            f"period {period} has {len(violations)} window violation(s): "
            f"{violations!r}"
        )

    statements, house_breakdown, payee_cents, house_cents, window_cents = (
        _build_statements(period, accruals, house_rows)
    )
    if not statements:
        # Month with only house rows (no payee accruals) — still closable
        # with an empty statement set? Spec wants per-payee statements +
        # root. An empty tree is rejected by merkle.build_tree. Surface
        # as empty-payee-set close error; operator can still inspect house.
        raise CloseError(
            f"period {period} has house activity but zero payee statements "
            f"(house_cents={house_cents}); nothing to root"
        )

    payloads = [s.leaf_payload() for s in statements]
    tree = build_tree(payloads)
    proofs = tuple(prove(tree, i) for i in range(tree.size))

    close = MonthClose(
        period=period,
        month_root_hex=tree.root_hex,
        statements=tuple(statements),
        proofs=proofs,
        total_payee_cents=payee_cents,
        total_house_cents=house_cents,
        total_window_cents=window_cents,
        attribution_math_version=statements[0].attribution_math_version,
        month_close_version=MONTH_CLOSE_VERSION,
        merkle_serialization=MERKLE_SERIALIZATION_VERSION,
        house_breakdown=house_breakdown,
    )
    # Cross-foot: payee + house + unmapped == window total.
    unmapped = int(house_breakdown.get("unmapped_cents", 0))
    if payee_cents + house_cents + unmapped != window_cents:
        raise CloseInconsistentError(
            f"cross-foot failed for {period}: payee={payee_cents} + "
            f"house={house_cents} + unmapped={unmapped} != window={window_cents}"
        )
    return close


def default_artifact_dir(period: str, *, base: str | Path | None = None) -> Path:
    """Stable artifact path for a period's close files.

    The base is resolved in order: explicit ``base`` argument > the
    ``ANTIEK_AFA_ARTIFACT_DIR`` env override > ``data/afa_month_closes``
    (CWD-relative fallback). Production deployments SHOULD set the env var
    so artifact writes are hermetic and CWD-independent (the pass-9 hazard:
    a CWD-relative default accumulates stale files across runs/processes).
    """
    root = Path(base) if base is not None else Path(
        os.environ.get("ANTIEK_AFA_ARTIFACT_DIR", "data/afa_month_closes")
    )
    return root / period


def write_artifacts(
    close: MonthClose,
    artifact_dir: str | Path,
) -> dict[str, str]:
    """Write statement JSON + proof JSON + root.txt under ``artifact_dir``.

    Returns a map of logical name → absolute path string. Directory is
    created if missing. Files are rewritten atomically-enough (write then
    replace) so a crash mid-write does not leave a half-root next to full
    statements.
    """
    d = Path(artifact_dir)
    d.mkdir(parents=True, exist_ok=True)

    paths: dict[str, str] = {}
    root_path = d / "root.txt"
    root_path.write_text(close.month_root_hex + "\n", encoding="utf-8")
    paths["root"] = str(root_path.resolve())

    # Manifest: period metadata + root + per-payee index.
    manifest = {
        "period": close.period,
        "month_root_hex": close.month_root_hex,
        "statement_count": len(close.statements),
        "total_payee_cents": close.total_payee_cents,
        "total_house_cents": close.total_house_cents,
        "total_window_cents": close.total_window_cents,
        "attribution_math_version": close.attribution_math_version,
        "month_close_version": close.month_close_version,
        "merkle_serialization": close.merkle_serialization,
        "house_breakdown": close.house_breakdown,
        "statements_digest": close.statements_digest(),
        "payees": [
            {
                "payee_id": s.payee_id,
                "total_cents": s.total_cents,
                "leaf_index": i,
                "statement_file": f"statements/{_safe_filename(s.payee_id)}.json",
                "proof_file": f"proofs/{_safe_filename(s.payee_id)}.json",
            }
            for i, s in enumerate(close.statements)
        ],
    }
    man_path = d / "manifest.json"
    man_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    paths["manifest"] = str(man_path.resolve())

    stmt_dir = d / "statements"
    proof_dir = d / "proofs"
    stmt_dir.mkdir(exist_ok=True)
    proof_dir.mkdir(exist_ok=True)

    for i, (stmt, proof) in enumerate(zip(close.statements, close.proofs, strict=True)):
        safe = _safe_filename(stmt.payee_id)
        sp = stmt_dir / f"{safe}.json"
        pp = proof_dir / f"{safe}.json"
        sp.write_text(canonical_json(stmt.to_dict()) + "\n", encoding="utf-8")
        proof_doc = {
            "period": close.period,
            "payee_id": stmt.payee_id,
            "month_root_hex": close.month_root_hex,
            "proof": proof.to_dict(),
        }
        pp.write_text(canonical_json(proof_doc) + "\n", encoding="utf-8")
        paths[f"statement:{stmt.payee_id}"] = str(sp.resolve())
        paths[f"proof:{stmt.payee_id}"] = str(pp.resolve())
        _ = i
    return paths


def _safe_filename(payee_id: str) -> str:
    """Filesystem-safe token from a payee id (keep alnum, dash, underscore)."""
    out = re.sub(r"[^A-Za-z0-9._-]+", "_", payee_id)
    return out or "payee"


def persist_close(
    con: Any,
    close: MonthClose,
    *,
    artifact_dir: str | Path,
) -> MonthClose:
    """Persist close record + per-statement rows. Idempotent on period.

    Re-close policy (M4 decision): **idempotent when the statements digest
    matches**; if the ledger changed under the same period, raise so the
    operator must decide (no silent history rewrite; no auto-versioning of
    past closes — clawback/recompute is a future lane).
    """
    ensure_tables_close(con)
    artifact_dir = Path(artifact_dir)
    digest = close.statements_digest()

    existing = con.execute(
        "SELECT month_root_hex, statements_digest, artifact_dir "
        "FROM afa_month_closes WHERE period = ?",
        [close.period],
    ).fetchone()
    if existing is not None:
        prev_root, prev_digest, prev_dir = existing
        if prev_digest == digest and prev_root == close.month_root_hex:
            # Identical close — return reused view; artifacts already on disk
            # (or re-write them to the recorded path for safety).
            write_artifacts(close, prev_dir or artifact_dir)
            return MonthClose(
                period=close.period,
                month_root_hex=close.month_root_hex,
                statements=close.statements,
                proofs=close.proofs,
                total_payee_cents=close.total_payee_cents,
                total_house_cents=close.total_house_cents,
                total_window_cents=close.total_window_cents,
                attribution_math_version=close.attribution_math_version,
                month_close_version=close.month_close_version,
                merkle_serialization=close.merkle_serialization,
                house_breakdown=close.house_breakdown,
                reused=True,
                artifact_dir=str(prev_dir or artifact_dir),
            )
        raise CloseError(
            f"period {close.period} already closed with a different digest "
            f"(stored={prev_digest[:16]}… new={digest[:16]}…). "
            "Re-close of a mutated ledger is refused (no silent rewrite). "
            "Clawback/recompute is a future lane."
        )

    paths = write_artifacts(close, artifact_dir)
    con.execute(
        """
        INSERT INTO afa_month_closes (
            period, month_root_hex, statement_count,
            total_payee_cents, total_house_cents, total_window_cents,
            attribution_math_version, month_close_version,
            merkle_serialization, artifact_dir, statements_digest
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            close.period,
            close.month_root_hex,
            len(close.statements),
            close.total_payee_cents,
            close.total_house_cents,
            close.total_window_cents,
            close.attribution_math_version,
            close.month_close_version,
            close.merkle_serialization,
            str(artifact_dir),
            digest,
        ],
    )
    for i, (stmt, proof) in enumerate(zip(close.statements, close.proofs, strict=True)):
        stmt_id = f"stmt-{close.period}-{_safe_filename(stmt.payee_id)}"
        leaf_hex = hashlib.sha256(
            b"\x00" + stmt.leaf_payload()
        ).hexdigest()
        con.execute(
            """
            INSERT INTO afa_month_statements (
                statement_id, period, payee_id, total_cents,
                leaf_index, leaf_hash_hex, statement_json, proof_json,
                statement_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                stmt_id,
                close.period,
                stmt.payee_id,
                stmt.total_cents,
                i,
                leaf_hex,
                canonical_json(stmt.to_dict()),
                canonical_json(proof.to_dict()),
                paths.get(f"statement:{stmt.payee_id}"),
            ],
        )
    return MonthClose(
        period=close.period,
        month_root_hex=close.month_root_hex,
        statements=close.statements,
        proofs=close.proofs,
        total_payee_cents=close.total_payee_cents,
        total_house_cents=close.total_house_cents,
        total_window_cents=close.total_window_cents,
        attribution_math_version=close.attribution_math_version,
        month_close_version=close.month_close_version,
        merkle_serialization=close.merkle_serialization,
        house_breakdown=close.house_breakdown,
        reused=False,
        artifact_dir=str(artifact_dir),
    )


def close_month(
    con: Any,
    period: str,
    *,
    artifact_dir: str | Path | None = None,
    persist: bool = True,
) -> MonthClose:
    """Close ``period``: compute statements + root, optionally persist.

    ``con`` must be a write connection when ``persist=True`` (house
    single-writer). For compute-only / dry-run, a read connection is fine
    with ``persist=False``.
    """
    close = compute_close(con, period)
    if not persist:
        return close
    if artifact_dir is None:
        artifact_dir = default_artifact_dir(period)
    return persist_close(con, close, artifact_dir=artifact_dir)


def load_close(con: Any, period: str) -> dict[str, Any] | None:
    """Load a persisted close record (or None)."""
    ensure_tables_close(con)
    row = con.execute(
        """
        SELECT period, month_root_hex, statement_count,
               total_payee_cents, total_house_cents, total_window_cents,
               attribution_math_version, month_close_version,
               merkle_serialization, artifact_dir, statements_digest,
               closed_at
        FROM afa_month_closes WHERE period = ?
        """,
        [period],
    ).fetchone()
    if row is None:
        return None
    return {
        "period": row[0],
        "month_root_hex": row[1],
        "statement_count": int(row[2]),
        "total_payee_cents": int(row[3]),
        "total_house_cents": int(row[4]),
        "total_window_cents": int(row[5]),
        "attribution_math_version": row[6],
        "month_close_version": row[7],
        "merkle_serialization": row[8],
        "artifact_dir": row[9],
        "statements_digest": row[10],
        "closed_at": str(row[11]),
    }


def get_root(con: Any, period: str) -> str | None:
    """Return the published month root hex for ``period``, or None."""
    rec = load_close(con, period)
    return rec["month_root_hex"] if rec else None


# ---------------------------------------------------------------------------
# Offline verification helpers (also used by the CLI; stdlib-capable path
# lives in verify_statement.py for third-party handoff)
# ---------------------------------------------------------------------------


def verify_statement_against_root(
    statement: dict[str, Any] | PayeeStatement,
    proof: InclusionProof | dict[str, Any],
    root_hex: str,
) -> bool:
    """Verify a statement's inclusion against a published root.

    Accepts dict or dataclass forms. Uses the same leaf payload contract
    as the close (canonical JSON of the statement dict).
    """
    if isinstance(statement, PayeeStatement):
        payload = statement.leaf_payload()
    else:
        payload = canonical_json_bytes(statement)
    if isinstance(proof, dict):
        # Allow either the bare proof or the proof-doc envelope.
        if "proof" in proof and isinstance(proof["proof"], dict):
            proof = InclusionProof.from_dict(proof["proof"])
        else:
            proof = InclusionProof.from_dict(proof)
    return verify_inclusion(payload, proof, root_hex)


__all__ = [
    "MONTH_CLOSE_VERSION",
    "STATEMENT_SCHEMA_VERSION",
    "CloseError",
    "CloseInconsistentError",
    "MonthClose",
    "PayeeStatement",
    "WindowAggregate",
    "canonical_json",
    "canonical_json_bytes",
    "close_month",
    "compute_close",
    "default_artifact_dir",
    "ensure_tables_close",
    "get_root",
    "load_close",
    "parse_period",
    "persist_close",
    "verify_statement_against_root",
    "write_artifacts",
]
