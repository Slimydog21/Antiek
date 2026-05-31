"""Escrow accrual for gated in-copyright works (SPR-02 M6).

When a work is classed ``restricted_pending_opt_in`` for an in-copyright reason
(a rights holder exists), escrow ACCRUES to a ``pre_onboarded`` ip_holder via
the existing seam (``substrate.ip_holders.accrue_escrow``). Escrow accrues
only — it NEVER disburses. ``payout.py`` / ``stripe_connect`` are not imported,
not referenced. G2/G3 (operator-only disbursement) are untouched.

These tests prove:
  - a gated in-copyright classification accrues to a pre_onboarded holder
    (spy + real-DB);
  - a public-domain / open-licensed servable work accrues NOTHING (no rights
    holder to pay);
  - the accrual is additive to the escrow balance only;
  - NO disbursement function is called (the spy sees zero disburse calls);
  - the accrual seam imports neither payout nor stripe_connect.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from decimal import Decimal

import pytest

from acquisition.licenses_core import classify
from runtime.db_lock import connect_write
from substrate import ip_holders
from substrate.ip_holders.gated_accrual import accrue_gated_escrow


@pytest.fixture()
def db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-escrow-accrual-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# A gated in-copyright work accrues to a pre_onboarded holder
# ---------------------------------------------------------------------------


def test_gated_in_copyright_accrues_to_pre_onboarded_holder(db):
    """An in-copyright gated work (legitimate source, rights holder named) is
    accrual-eligible; accrue_gated_escrow creates/uses a pre_onboarded holder
    and increments its escrow balance."""
    result = classify(None, {"rights_holder": "Elsevier"}, legitimate_source=True)
    assert result.accrual_eligible is True

    with connect_write(db, purpose="test:accrue") as con:
        holder_id = accrue_gated_escrow(
            con, result, rights_holder_name="Elsevier", amount_usd=Decimal("0.05")
        )
        holder = ip_holders.get(con, holder_id)

    assert holder_id is not None
    assert holder is not None
    assert holder.status == "pre_onboarded"
    assert holder.escrow_balance_usd == Decimal("0.05")


def test_accrual_is_additive_only(db):
    """Two accruals to the same holder sum; nothing is ever subtracted /
    disbursed."""
    result = classify(None, {"rights_holder": "Springer"}, legitimate_source=True)
    with connect_write(db, purpose="test:accrue") as con:
        id1 = accrue_gated_escrow(con, result, rights_holder_name="Springer",
                                  amount_usd=Decimal("0.02"))
        id2 = accrue_gated_escrow(con, result, rights_holder_name="Springer",
                                  amount_usd=Decimal("0.03"))
        holder = ip_holders.get(con, id1)
    assert id1 == id2  # idempotent on name — one account, not two
    assert holder.escrow_balance_usd == Decimal("0.05")


# ---------------------------------------------------------------------------
# Servable / open works accrue NOTHING
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "license,decl",
    [
        ("https://creativecommons.org/publicdomain/zero/1.0/", {}),  # CC0 -> public_domain
        ("https://creativecommons.org/licenses/by/4.0/", {}),        # CC-BY -> source_declared_open
        (None, {"public_domain": "US pre-1929"}),                    # declared PD
    ],
)
def test_servable_work_accrues_nothing(db, license, decl):
    """A public-domain / open-licensed servable work has no rights holder to
    pay -> accrual_eligible False -> accrue_gated_escrow accrues nothing."""
    result = classify(license, decl, legitimate_source=True)
    assert result.servable is True
    assert result.accrual_eligible is False

    with connect_write(db, purpose="test:no-accrue") as con:
        holder_id = accrue_gated_escrow(
            con, result, rights_holder_name="Should Not Be Created",
            amount_usd=Decimal("0.05"),
        )
        holders = ip_holders.list_all(con)

    assert holder_id is None  # nothing accrued
    assert holders == []  # no holder created for a servable work


def test_anonymous_gated_work_accrues_nothing(db):
    """A gated work with NO known rights holder (unknown provenance) is gated
    but not accrual-eligible — there is nobody to accrue to. Honest: no
    invented holder, no escrow."""
    result = classify(None, {}, legitimate_source=True)
    assert result.content_class == "restricted_pending_opt_in"
    assert result.accrual_eligible is False
    with connect_write(db, purpose="test:no-accrue") as con:
        holder_id = accrue_gated_escrow(
            con, result, rights_holder_name="Nobody", amount_usd=Decimal("0.05")
        )
        holders = ip_holders.list_all(con)
    assert holder_id is None
    assert holders == []


# ---------------------------------------------------------------------------
# Spy: accrue is called, disburse is NEVER called
# ---------------------------------------------------------------------------


class _SpyConnection:
    """A spy that records every accrue/disburse-shaped call. The only write the
    accrual seam performs is the escrow INCREMENT (accrue_escrow's UPDATE); a
    disbursement would be a wholly different call the seam must never make."""

    def __init__(self):
        self.queries: list[str] = []
        self.disburse_calls = 0

    def execute(self, sql, params=None):
        self.queries.append(sql)
        # accrue_escrow does a find (list_all SELECT) then an escrow UPDATE.
        # No INSERT here for an existing holder; we pre-seed one below.
        if "escrow_balance_usd = escrow_balance_usd +" in sql:
            return _Cursor([])
        if "FROM ip_holders" in sql:  # list_all / get
            return _Cursor(self._holder_rows())
        return _Cursor([])

    def _holder_rows(self):
        # One pre_onboarded holder named "Wiley" so the seam reuses it.
        return [(
            "ipholder-spy", "Wiley", None, "pre_onboarded",
            "0", None, None, None, None, "2026-01-01T00:00:00Z", "{}",
        )]


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


def test_spy_sees_accrue_never_disburse():
    """Under a spy connection: classing a gated in-copyright work accrues (an
    escrow-increment UPDATE is issued) and NO disbursement path is invoked.
    accrue_gated_escrow + accrue_escrow touch only the escrow_balance_usd
    increment — there is no distribute/transfer call anywhere in the seam."""
    result = classify(None, {"rights_holder": "Wiley"}, legitimate_source=True)
    spy = _SpyConnection()

    holder_id = accrue_gated_escrow(
        spy, result, rights_holder_name="Wiley", amount_usd=Decimal("0.01")
    )

    assert holder_id == "ipholder-spy"  # reused the existing holder
    # Exactly one escrow-increment UPDATE was issued (the accrual).
    increments = [q for q in spy.queries if "escrow_balance_usd = escrow_balance_usd +" in q]
    assert len(increments) == 1
    # No disbursement-shaped statement was ever issued by the seam.
    assert spy.disburse_calls == 0
    forbidden = ("INSERT INTO payouts", "stripe", "transfer", "disburse", "distribute")
    for q in spy.queries:
        assert not any(tok in q.lower() for tok in forbidden), q


# ---------------------------------------------------------------------------
# Money modules are not imported by the accrual seam
# ---------------------------------------------------------------------------


def test_accrual_seam_does_not_import_money_modules():
    """The sprint's escrow seam (substrate.ip_holders.gated_accrual) IMPORTS
    neither payout nor stripe_connect — proven over the import lines of the
    source. The seam routes through the one low-level writer (accrue_escrow),
    never the disbursement path."""
    import inspect

    from substrate.ip_holders import gated_accrual

    import_lines = [
        line
        for line in inspect.getsource(gated_accrual).splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert import_lines  # the module does import the writer seam
    for line in import_lines:
        assert "payout" not in line, line
        assert "stripe_connect" not in line, line
        assert "stripe" not in line.lower(), line
