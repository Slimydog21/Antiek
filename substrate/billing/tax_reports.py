"""Annual 1099 reporting stub (master-spec §9.5).

Per the Sprint 23-24 phase 4 deliverable list: *"KYC + 1099 reporting
+ ToS for any creator above threshold."* This module is the substrate
side of the 1099 contract — it aggregates payouts per recipient per
tax year and emits a CSV the operator hands to their accountant.

The substrate does NOT call any tax service. The IRS 1099 form
requires recipient TIN / SSN / EIN — all of which live behind
Stripe Connect's KYC flow (substrate/billing/kyc.py). The operator
exports the aggregated payout totals, the accountant joins them
against Stripe's KYC export, and the actual 1099 paperwork is
filed via the accountant.

Substrate scope:

  - aggregate payouts (substrate's transfer_log) per recipient_ref
    per tax year
  - flag recipients whose annual total ≥ §9.5 $600 threshold (the
    IRS 1099-NEC reporting threshold)
  - emit a CSV with one row per recipient
  - record the emission as an append-only ``tax_reports`` row so
    the operator can prove they ran the export

What is OUT of substrate scope:

  - filing the actual 1099 with the IRS
  - joining recipient_ref → SSN/TIN (Stripe Connect holds this)
  - state-tax 1099-NEC variants
  - 1042-S for non-US recipients
"""

from __future__ import annotations

import csv
import io
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# Per IRS regulations (effective 2026 tax year): aggregate non-employee
# compensation ≥ $600 in a calendar year triggers 1099-NEC reporting.
# §9.5 cites this as the binding threshold for KYC.
IRS_1099_NEC_THRESHOLD_USD_CENTS: int = 60_000


@dataclass(frozen=True)
class AnnualPayoutAggregate:
    """One recipient's total payout across a tax year. Drives the
    1099 reporting decision."""

    recipient_ref: str
    tax_year: int
    total_usd_cents: int
    transfer_count: int

    @property
    def total_usd(self) -> float:
        return self.total_usd_cents / 100.0

    @property
    def above_1099_threshold(self) -> bool:
        return self.total_usd_cents >= IRS_1099_NEC_THRESHOLD_USD_CENTS


@dataclass(frozen=True)
class TaxReportRecord:
    """One row in the ``tax_reports`` table. Marks a report emission."""

    report_id: str
    recipient_ref: str
    tax_year: int
    total_payout_usd_cents: int
    above_1099_threshold: bool
    csv_export_path: str | None
    emitted_at: str


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# ── Aggregation ────────────────────────────────────────────────────


def aggregate_annual_payouts(
    con: Any, *, tax_year: int,
) -> list[AnnualPayoutAggregate]:
    """Aggregate ``payout_transfers`` rows whose status='transferred'
    in the given tax year, grouped by recipient. Returns one
    ``AnnualPayoutAggregate`` per recipient with at least one
    transferred row in the window.

    The ``payout_transfers`` schema is defined in
    ``substrate/graph/schema.py`` (Sprint 23-24 V4 chunk). The
    ``recipient_account_id`` is the Stripe Connect account ref; the
    substrate treats it as opaque (the integration layer maps it
    back to user_id / ip_holder_id at audit time).
    """
    year_start = f"{tax_year:04d}-01-01 00:00:00"
    year_end = f"{tax_year + 1:04d}-01-01 00:00:00"
    rows = con.execute(
        """
        SELECT recipient_account_id,
               SUM(amount_usd_cents) AS total,
               COUNT(*) AS n
        FROM payout_transfers
        WHERE status = 'transferred'
          AND recipient_account_id IS NOT NULL
          AND initiated_at >= ?::TIMESTAMP
          AND initiated_at <  ?::TIMESTAMP
        GROUP BY recipient_account_id
        ORDER BY recipient_account_id
        """,
        [year_start, year_end],
    ).fetchall()
    return [
        AnnualPayoutAggregate(
            recipient_ref=r[0],
            tax_year=tax_year,
            total_usd_cents=int(r[1] or 0),
            transfer_count=int(r[2] or 0),
        )
        for r in rows
    ]


# ── CSV export ─────────────────────────────────────────────────────


_CSV_HEADER = [
    "recipient_ref",
    "tax_year",
    "total_payout_usd",
    "transfer_count",
    "above_1099_threshold",
]


def render_csv(aggregates: list[AnnualPayoutAggregate]) -> str:
    """Render aggregates as CSV. Header row first; one data row per
    aggregate. Deterministic ordering (sorted by recipient_ref so
    diffs are stable)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_CSV_HEADER)
    for a in sorted(aggregates, key=lambda x: x.recipient_ref):
        writer.writerow([
            a.recipient_ref,
            a.tax_year,
            f"{a.total_usd:.2f}",
            a.transfer_count,
            "true" if a.above_1099_threshold else "false",
        ])
    return buf.getvalue()


def write_csv(aggregates: list[AnnualPayoutAggregate], path: str) -> str:
    """Render + write the CSV to ``path``. Returns the absolute path
    the CSV landed at."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(render_csv(aggregates))
    return os.path.abspath(path)


# ── Persistence — emission audit log ──────────────────────────────


def ensure_table(con: Any) -> None:
    """Defensive table-creation. Canonical schema in
    ``substrate/graph/schema.py`` V5 chunk."""
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS tax_reports (
                report_id               TEXT PRIMARY KEY,
                recipient_ref           TEXT NOT NULL,
                tax_year                INTEGER NOT NULL,
                total_payout_usd_cents  INTEGER NOT NULL,
                above_1099_threshold    BOOLEAN NOT NULL,
                csv_export_path         TEXT,
                emitted_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    except Exception:
        pass


def record_emission(
    con: Any,
    *,
    aggregates: list[AnnualPayoutAggregate],
    csv_export_path: str | None = None,
) -> list[TaxReportRecord]:
    """Insert one ``tax_reports`` row per aggregate, marking the
    emission. Returns the persisted records.

    Why per-recipient rows: so the operator can later prove they
    emitted reports for each individual recipient at a specific
    time. The csv_export_path rides on every row so the audit trail
    points back to the file the operator handed the accountant."""
    ensure_table(con)
    out: list[TaxReportRecord] = []
    emitted = _now_iso()
    for a in aggregates:
        report_id = f"taxrep-{uuid.uuid4().hex[:12]}"
        con.execute(
            """
            INSERT INTO tax_reports (
                report_id, recipient_ref, tax_year,
                total_payout_usd_cents, above_1099_threshold,
                csv_export_path
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                report_id, a.recipient_ref, a.tax_year,
                a.total_usd_cents, a.above_1099_threshold,
                csv_export_path,
            ],
        )
        out.append(TaxReportRecord(
            report_id=report_id,
            recipient_ref=a.recipient_ref,
            tax_year=a.tax_year,
            total_payout_usd_cents=a.total_usd_cents,
            above_1099_threshold=a.above_1099_threshold,
            csv_export_path=csv_export_path,
            emitted_at=emitted,
        ))
    return out


def load_emissions(
    con: Any, *, tax_year: int | None = None,
) -> list[TaxReportRecord]:
    """Read back the emission audit log. Optional tax_year filter."""
    ensure_table(con)
    if tax_year is not None:
        rows = con.execute(
            "SELECT report_id, recipient_ref, tax_year, "
            "total_payout_usd_cents, above_1099_threshold, "
            "csv_export_path, emitted_at "
            "FROM tax_reports WHERE tax_year = ? "
            "ORDER BY emitted_at, report_id",
            [tax_year],
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT report_id, recipient_ref, tax_year, "
            "total_payout_usd_cents, above_1099_threshold, "
            "csv_export_path, emitted_at "
            "FROM tax_reports "
            "ORDER BY tax_year, emitted_at, report_id"
        ).fetchall()
    out: list[TaxReportRecord] = []
    for r in rows:
        emitted_at = (
            r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6])
        )
        out.append(TaxReportRecord(
            report_id=r[0],
            recipient_ref=r[1],
            tax_year=int(r[2]),
            total_payout_usd_cents=int(r[3]),
            above_1099_threshold=bool(r[4]),
            csv_export_path=r[5],
            emitted_at=emitted_at,
        ))
    return out


__all__ = [
    "AnnualPayoutAggregate",
    "IRS_1099_NEC_THRESHOLD_USD_CENTS",
    "TaxReportRecord",
    "aggregate_annual_payouts",
    "ensure_table",
    "load_emissions",
    "record_emission",
    "render_csv",
    "write_csv",
]
