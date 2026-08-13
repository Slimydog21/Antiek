"""AFA-S6 — monthly close: replayable statements + Merkle month root.

Proves: determinism (same ledger → same root twice), per-payee exact-cent
conservation vs the accrual ledger, inclusion proofs verify, tampered
statements fail, the offline verifier works from files only (no DB), and
re-close is idempotent on an unchanged ledger.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from runtime.db_lock import connect_write
from substrate import ip_holders
from substrate.ad_inventory.frame_attention import (
    FrameAttentionSample,
    FrameSecond,
    WindowFrameBatch,
)
from substrate.ad_inventory.frame_attention_accrual import (
    accrue_window,
    ensure_tables,
)
from substrate.ad_inventory.merkle import (
    MERKLE_SERIALIZATION_VERSION,
    build_tree,
    prove,
    verify_inclusion,
)
from substrate.ad_inventory.monthly_close import (
    MONTH_CLOSE_VERSION,
    CloseError,
    canonical_json,
    close_month,
    compute_close,
    ensure_tables_close,
    get_root,
    load_close,
    parse_period,
    verify_statement_against_root,
    write_artifacts,
)
from substrate.ad_inventory.verify_statement import verify as offline_verify

_IP_HOLDERS_DDL = """
CREATE TABLE IF NOT EXISTS ip_holders (
    ip_holder_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    legal_contact_email TEXT,
    status TEXT NOT NULL DEFAULT 'pre_onboarded',
    escrow_balance_usd DECIMAL(18, 6) NOT NULL DEFAULT 0,
    escrow_account_ref TEXT,
    notification_sent_at TIMESTAMP,
    claimed_at TIMESTAMP,
    opted_out_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT
);
"""

_REPO = Path(__file__).resolve().parents[1]
_PY = os.environ.get(
    "AFA_TEST_PYTHON",
    str(_REPO.parents[1] / "platform" / ".venv" / "bin" / "python")
    if (_REPO.parents[1] / "platform" / ".venv" / "bin" / "python").exists()
    else sys.executable,
)
# Prefer the operator-specified venv; fall back to current interpreter.
_VENV_PY = Path("/Users/slimydog/Antiek/platform/.venv/bin/python")
if _VENV_PY.exists():
    _PY = str(_VENV_PY)


@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "close.duckdb")
    con = connect_write(db_path, purpose="afa_s6_test")
    con.execute(_IP_HOLDERS_DDL)
    ensure_tables(con)
    ensure_tables_close(con)
    yield con, db_path, tmp_path
    con.close()


def _sample(asset_id, *, area=0.6, prom=0.8, dwell=900, cc="public_domain", chunk=None):
    return FrameAttentionSample(
        asset_id=asset_id,
        viewport_area_fraction=area,
        prominence=prom,
        focused_dwell_ms=dwell,
        content_class=cc,
        chunk_id=chunk,
    )


def _window(window_id, n_seconds, samples, ad_value_cents):
    seconds = tuple(
        FrameSecond(second_index=i, lens="read", samples=samples)
        for i in range(n_seconds)
    )
    return WindowFrameBatch(
        window_id=window_id,
        seconds=seconds,
        ad_value_usd_cents=ad_value_cents,
    )


def _seed_month(con, *, period_start: str = "2026-07-01", n_holders: int = 3):
    """Accrue a multi-holder, multi-window month with nonzero server-minted value.

    Returns (holders, total_window_cents, period).
    """
    holders = [
        ip_holders.create_pre_onboarded(con, display_name=f"Publisher {i}")
        for i in range(n_holders)
    ]
    # Nonzero server-minted values (AFA-S1 posture) — not client-claimed.
    windows = [
        ("w-jul-1", 10, (_sample("doc-a", chunk="c-a"), _sample("doc-b", chunk="c-b")), 1000),
        ("w-jul-2", 20, (_sample("doc-a", chunk="c-a"), _sample("doc-c", chunk="c-c")), 2500),
        ("w-jul-3", 5, (_sample("doc-b", chunk="c-b"),), 700),
        ("w-jul-4", 15, (
            _sample("doc-a", chunk="c-a"),
            _sample("doc-b", chunk="c-b"),
            _sample("doc-c", chunk="c-c"),
        ), 3300),
    ]
    a2h = {
        "doc-a": holders[0],
        "doc-b": holders[1],
        "doc-c": holders[2] if n_holders > 2 else holders[0],
    }
    total = 0
    for wid, nsec, samples, cents in windows:
        batch = _window(wid, nsec, samples, cents)
        accrue_window(con, batch, asset_to_ip_holder=a2h)
        total += cents

    # Stamp accrued_at into the target month so period filter selects them.
    # (Default CURRENT_TIMESTAMP would put them in "now", not a fixed month.)
    start = datetime.fromisoformat(period_start)
    # Spread timestamps across the month deterministically.
    for i, (wid, *_rest) in enumerate(windows):
        ts = (start + timedelta(days=1 + i * 3, hours=12)).strftime("%Y-%m-%d %H:%M:%S")
        con.execute(
            "UPDATE frame_attention_accruals SET accrued_at = CAST(? AS TIMESTAMP) "
            "WHERE window_id = ?",
            [ts, wid],
        )
        con.execute(
            "UPDATE house_seconds SET accrued_at = CAST(? AS TIMESTAMP) "
            "WHERE window_id = ?",
            [ts, wid],
        )
    period = period_start[:7]  # YYYY-MM
    return holders, total, period


# ── Merkle unit edges ────────────────────────────────────────────────


def test_merkle_single_leaf_root_is_leaf_hash():
    payload = b'{"a":1}'
    tree = build_tree([payload])
    assert tree.size == 1
    assert tree.root_hex == tree.leaf_hashes[0].hex()
    proof = prove(tree, 0)
    assert proof.siblings == ()
    assert verify_inclusion(payload, proof, tree.root_hex)


def test_merkle_odd_leaf_count_promotes_unpaired():
    payloads = [f"leaf-{i}".encode() for i in range(3)]
    tree = build_tree(payloads)
    assert tree.size == 3
    for i, p in enumerate(payloads):
        assert verify_inclusion(p, prove(tree, i), tree.root_hex)


def test_merkle_empty_rejected():
    with pytest.raises(ValueError, match="zero leaves"):
        build_tree([])


def test_merkle_reorder_changes_root():
    a, b, c = b"one", b"two", b"three"
    r1 = build_tree([a, b, c]).root_hex
    r2 = build_tree([a, c, b]).root_hex
    assert r1 != r2


# ── Period parsing ───────────────────────────────────────────────────


def test_parse_period_accepts_yyyy_mm():
    p, start, end = parse_period("2026-07")
    assert p == "2026-07" and start == "2026-07-01" and end == "2026-08-01"


def test_parse_period_december_rolls_year():
    _, start, end = parse_period("2026-12")
    assert start == "2026-12-01" and end == "2027-01-01"


def test_parse_period_rejects_garbage():
    with pytest.raises(ValueError):
        parse_period("2026/07")
    with pytest.raises(ValueError):
        parse_period("2026-13")


# ── Close determinism + conservation ─────────────────────────────────


def test_close_determinism_same_root_twice(tmp_db):
    con, _db, tmp = tmp_db
    _holders, total, period = _seed_month(con)
    c1 = compute_close(con, period)
    c2 = compute_close(con, period)
    assert c1.month_root_hex == c2.month_root_hex
    assert c1.statements_digest() == c2.statements_digest()
    assert len(c1.statements) == len(c2.statements)
    for s1, s2 in zip(c1.statements, c2.statements, strict=True):
        assert s1.leaf_payload() == s2.leaf_payload()
    assert c1.total_window_cents == total


def test_close_cross_foots_to_ledger(tmp_db):
    con, _db, tmp = tmp_db
    holders, total, period = _seed_month(con)
    close = compute_close(con, period)
    # Σ statements + house + unmapped == window total
    unmapped = int(close.house_breakdown.get("unmapped_cents", 0))
    assert (
        close.total_payee_cents + close.total_house_cents + unmapped
        == close.total_window_cents
        == total
    )
    # Per-payee totals match ledger sums.
    for stmt in close.statements:
        ledger = con.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM frame_attention_accruals "
            "WHERE ip_holder_id = ? AND accrued_at >= CAST('2026-07-01' AS TIMESTAMP) "
            "AND accrued_at < CAST('2026-08-01' AS TIMESTAMP)",
            [stmt.payee_id],
        ).fetchone()[0]
        assert int(ledger) == stmt.total_cents
        assert stmt.total_cents == sum(w.amount_cents for w in stmt.windows)
    assert {s.payee_id for s in close.statements} == set(holders)


def test_close_no_datetime_now_on_path():
    """Clock discipline: the close module must not call datetime.now()."""
    src = Path("substrate/ad_inventory/monthly_close.py").read_text()
    # Strip comments/docstrings roughly; assert no now() call.
    assert "datetime.now(" not in src
    assert "datetime.utcnow(" not in src
    assert "time.time(" not in src


# ── Inclusion proofs + tamper ────────────────────────────────────────


def test_every_statement_verifies_against_root(tmp_db):
    con, _db, tmp = tmp_db
    _seed_month(con)
    close = compute_close(con, "2026-07")
    for stmt, proof in zip(close.statements, close.proofs, strict=True):
        assert verify_statement_against_root(stmt, proof, close.month_root_hex)
        assert verify_inclusion(stmt.leaf_payload(), proof, close.month_root_hex)


def test_tampered_cent_fails_verification(tmp_db):
    con, _db, tmp = tmp_db
    _seed_month(con)
    close = compute_close(con, "2026-07")
    stmt = close.statements[0]
    proof = close.proofs[0]
    # Mutate one cent on a copy of the statement dict.
    d = stmt.to_dict()
    d["total_cents"] = int(d["total_cents"]) + 1
    assert not verify_statement_against_root(d, proof, close.month_root_hex)
    ok, reason = offline_verify(d, proof.to_dict(), close.month_root_hex)
    assert not ok
    assert "recomputed root" in reason


def test_tampered_reorder_windows_fails(tmp_db):
    con, _db, tmp = tmp_db
    _seed_month(con)
    close = compute_close(con, "2026-07")
    # Find a multi-window statement.
    multi = next(s for s in close.statements if len(s.windows) >= 2)
    idx = close.statements.index(multi)
    proof = close.proofs[idx]
    d = multi.to_dict()
    d["windows"] = list(reversed(d["windows"]))
    assert not verify_statement_against_root(d, proof, close.month_root_hex)


def test_dropped_statement_changes_root(tmp_db):
    con, _db, tmp = tmp_db
    _seed_month(con)
    close = compute_close(con, "2026-07")
    payloads = [s.leaf_payload() for s in close.statements]
    full_root = build_tree(payloads).root_hex
    dropped = build_tree(payloads[:-1]).root_hex
    assert full_root != dropped


# ── Offline verifier (files only) ────────────────────────────────────


def test_offline_verifier_from_files(tmp_db):
    con, _db, tmp = tmp_db
    _seed_month(con)
    art = tmp / "artifacts"
    close = compute_close(con, "2026-07")
    paths = write_artifacts(close, art)

    root_path = Path(paths["root"])
    stmt_path = Path(paths[f"statement:{close.statements[0].payee_id}"])
    proof_path = Path(paths[f"proof:{close.statements[0].payee_id}"])

    # Run the stdlib-only module as a subprocess (no DB, no substrate beyond
    # the verifier file itself — the CLI entry still goes through -m).
    proc = subprocess.run(
        [
            sys.executable, "-m", "substrate.ad_inventory.verify_statement",
            str(stmt_path), str(proof_path), str(root_path),
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "VALID" in proc.stdout


def test_offline_verifier_refutes_tampered_file(tmp_db):
    con, _db, tmp = tmp_db
    _seed_month(con)
    art = tmp / "artifacts"
    close = compute_close(con, "2026-07")
    paths = write_artifacts(close, art)
    stmt_path = Path(paths[f"statement:{close.statements[0].payee_id}"])
    proof_path = Path(paths[f"proof:{close.statements[0].payee_id}"])
    root_path = Path(paths["root"])

    # Tamper the on-disk statement.
    d = json.loads(stmt_path.read_text())
    d["total_cents"] = int(d["total_cents"]) + 42
    stmt_path.write_text(json.dumps(d, sort_keys=True, separators=(",", ":")))

    proc = subprocess.run(
        [
            sys.executable, "-m", "substrate.ad_inventory.verify_statement",
            str(stmt_path), str(proof_path), str(root_path),
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "INVALID" in (proc.stderr + proc.stdout)


def test_verifier_import_isolation():
    """verify_statement.py imports only the stdlib (no substrate, no third-party)."""
    src = Path("substrate/ad_inventory/verify_statement.py").read_text()
    # Collect top-level import lines.
    imports = re.findall(r"^(?:from|import)\s+([\w.]+)", src, flags=re.M)
    allowed_roots = {
        "argparse", "hashlib", "json", "sys", "pathlib", "typing",
        "__future__",
    }
    for mod in imports:
        root = mod.split(".")[0]
        assert root in allowed_roots, f"non-stdlib import: {mod}"


# ── Idempotency ──────────────────────────────────────────────────────


def test_reclose_idempotent_same_digest(tmp_db):
    con, _db, tmp = tmp_db
    _seed_month(con)
    art = tmp / "close-art"
    c1 = close_month(con, "2026-07", artifact_dir=art, persist=True)
    assert not c1.reused
    c2 = close_month(con, "2026-07", artifact_dir=art, persist=True)
    assert c2.reused
    assert c1.month_root_hex == c2.month_root_hex
    assert get_root(con, "2026-07") == c1.month_root_hex
    rec = load_close(con, "2026-07")
    assert rec is not None
    assert rec["statement_count"] == len(c1.statements)


def test_reclose_refuses_mutated_ledger(tmp_db):
    con, _db, tmp = tmp_db
    holders, _total, period = _seed_month(con)
    art = tmp / "close-art"
    close_month(con, period, artifact_dir=art, persist=True)

    # Accrue an extra window into the same month → digest must change.
    batch = _window(
        "w-jul-extra", 8,
        (_sample("doc-a", chunk="c-a"),),
        900,
    )
    accrue_window(con, batch, asset_to_ip_holder={"doc-a": holders[0]})
    ts = "2026-07-20 10:00:00"
    con.execute(
        "UPDATE frame_attention_accruals SET accrued_at = CAST(? AS TIMESTAMP) "
        "WHERE window_id = 'w-jul-extra'",
        [ts],
    )
    con.execute(
        "UPDATE house_seconds SET accrued_at = CAST(? AS TIMESTAMP) "
        "WHERE window_id = 'w-jul-extra'",
        [ts],
    )
    with pytest.raises(CloseError, match="different digest"):
        close_month(con, period, artifact_dir=art, persist=True)


def test_empty_period_raises(tmp_db):
    con, _db, tmp = tmp_db
    with pytest.raises(CloseError, match="no accrual rows"):
        compute_close(con, "2020-01")


# ── CLI smoke ────────────────────────────────────────────────────────


def test_cli_close_and_verify(tmp_path):
    db_path = str(tmp_path / "cli.duckdb")
    con = connect_write(db_path, purpose="afa_s6_cli")
    con.execute(_IP_HOLDERS_DDL)
    ensure_tables(con)
    ensure_tables_close(con)
    _seed_month(con)
    # Close so the CLI can take the write lock (single-writer).
    con.close()
    tmp = tmp_path

    art = tmp / "cli-art"
    proc = subprocess.run(
        [
            sys.executable, "-m", "tools.afa_month_close",
            "close", "--month", "2026-07",
            "--db", db_path,
            "--artifact-dir", str(art),
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "CLOSED" in proc.stdout
    root_txt = (art / "root.txt").read_text().strip()
    assert re.fullmatch(r"[0-9a-f]{64}", root_txt)

    # root subcommand
    proc = subprocess.run(
        [
            sys.executable, "-m", "tools.afa_month_close",
            "root", "--month", "2026-07", "--db", db_path,
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == root_txt

    # verify subcommand (offline)
    stmt = next((art / "statements").glob("*.json"))
    proof = art / "proofs" / stmt.name
    proc = subprocess.run(
        [
            sys.executable, "-m", "tools.afa_month_close",
            "verify",
            "--root", root_txt,
            "--statement", str(stmt),
            "--proof", str(proof),
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "VALID" in proc.stdout


def test_version_stamps_present(tmp_db):
    con, _db, tmp = tmp_db
    _seed_month(con)
    close = compute_close(con, "2026-07")
    assert close.month_close_version == MONTH_CLOSE_VERSION
    assert close.merkle_serialization == MERKLE_SERIALIZATION_VERSION
    assert close.attribution_math_version == "attribution-math-v2"
    for s in close.statements:
        assert s.formula["creator_rev_share"] == str(Decimal("0.70"))
        assert "stage_versions" in s.formula
        assert s.denominators["month_total_window_cents"] == close.total_window_cents


def test_canonical_json_is_sorted_and_tight():
    blob = canonical_json({"b": 1, "a": {"z": 2, "y": 3}})
    assert blob == '{"a":{"y":3,"z":2},"b":1}'
