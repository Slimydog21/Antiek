"""AFA-S6 operator CLI — monthly close, root lookup, offline verify.

Usage (from the platform repo root)::

    python -m tools.afa_month_close close --month 2026-07
    python -m tools.afa_month_close close --month 2026-07 --db /path/to.duckdb
    python -m tools.afa_month_close root  --month 2026-07
    python -m tools.afa_month_close verify --root <hex|path> --statement path.json \\
                                          --proof path.json

``close`` is idempotent when the ledger is unchanged (same statements
digest → same root); a mutated ledger under an already-closed period is
refused (no silent history rewrite).

``verify`` is the offline path: it needs only the statement JSON, the
proof JSON, and the root (hex string or root.txt path). No DB.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


def _resolve_db(override: str | None) -> str:
    if override:
        return override
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _cmd_close(args: argparse.Namespace) -> int:
    from runtime.db_lock import connect_write
    from substrate.ad_inventory.monthly_close import (
        CloseError,
        close_month,
        default_artifact_dir,
        ensure_tables_close,
    )

    db = _resolve_db(args.db)
    artifact_dir = args.artifact_dir or str(default_artifact_dir(args.month))
    try:
        with connect_write(db, purpose=f"afa_month_close:{args.month}") as con:
            # Ensure accrual tables exist (defensive) + close tables.
            from substrate.ad_inventory.frame_attention_accrual import ensure_tables

            ensure_tables(con)
            ensure_tables_close(con)
            result = close_month(
                con,
                args.month,
                artifact_dir=artifact_dir,
                persist=not args.dry_run,
            )
    except CloseError as e:
        print(f"CLOSE FAILED: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"CLOSE ERROR: {e}", file=sys.stderr)
        return 1

    status = "REUSED" if result.reused else "CLOSED"
    print(f"{status} period={result.period}")
    print(f"  root            {result.month_root_hex}")
    print(f"  statements      {len(result.statements)}")
    print(f"  payee_cents     {result.total_payee_cents}")
    print(f"  house_cents     {result.total_house_cents}")
    print(f"  window_cents    {result.total_window_cents}")
    print(f"  cross_foots     {result.cross_foots()}")
    print(f"  math_version    {result.attribution_math_version}")
    print(f"  close_version   {result.month_close_version}")
    print(f"  merkle          {result.merkle_serialization}")
    if result.artifact_dir:
        print(f"  artifact_dir    {result.artifact_dir}")
    if args.json:
        print(json.dumps({
            "status": status.lower(),
            "period": result.period,
            "month_root_hex": result.month_root_hex,
            "statement_count": len(result.statements),
            "total_payee_cents": result.total_payee_cents,
            "total_house_cents": result.total_house_cents,
            "total_window_cents": result.total_window_cents,
            "reused": result.reused,
            "artifact_dir": result.artifact_dir,
        }, indent=2))
    return 0


def _cmd_root(args: argparse.Namespace) -> int:
    from runtime.db_lock import connect_write
    from substrate.ad_inventory.monthly_close import ensure_tables_close, get_root

    db = _resolve_db(args.db)
    # Read via write-lock-free path when possible; fall back to write conn
    # only to ensure_tables on a virgin DB.
    try:
        from runtime.db_lock import connect_read

        con = connect_read(db)
        with contextlib.suppress(Exception):
            ensure_tables_close(con)  # no-op on read if tables exist; may fail
        root = get_root(con, args.month)
        con.close()
    except Exception:
        with connect_write(db, purpose=f"afa_month_root:{args.month}") as con:
            ensure_tables_close(con)
            root = get_root(con, args.month)

    if root is None:
        print(f"no close recorded for period {args.month}", file=sys.stderr)
        return 1
    print(root)
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    """Offline verify — delegates to the stdlib-only verifier module."""
    from substrate.ad_inventory.verify_statement import main as verify_main

    root_arg = args.root
    # Allow raw hex or a path to root.txt.
    root_path: Path
    if Path(root_arg).is_file():
        root_path = Path(root_arg)
    else:
        # Write a temp root file so the verifier CLI shape is unchanged.
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="afa-verify-")) / "root.txt"
        tmp.write_text(root_arg.strip() + "\n", encoding="utf-8")
        root_path = tmp

    proof_path = args.proof
    if proof_path is None:
        # Convention: proof next to statement as ../proofs/<same-name>.
        stmt = Path(args.statement)
        candidate = stmt.parent.parent / "proofs" / stmt.name
        if candidate.is_file():
            proof_path = str(candidate)
        else:
            print(
                "verify requires --proof (or a sibling proofs/<name>.json)",
                file=sys.stderr,
            )
            return 2

    return verify_main([args.statement, proof_path, str(root_path)])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m tools.afa_month_close",
        description="AFA-S6 monthly close: statements + Merkle month root",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("close", help="close a calendar month (idempotent)")
    c.add_argument("--month", required=True, help="YYYY-MM")
    c.add_argument("--db", default=None, help="DuckDB path (default: house graph)")
    c.add_argument(
        "--artifact-dir", default=None,
        help="directory for statement/proof/root artifacts",
    )
    c.add_argument(
        "--dry-run", action="store_true",
        help="compute only; do not persist or write artifacts",
    )
    c.add_argument("--json", action="store_true", help="also emit JSON summary")
    c.set_defaults(func=_cmd_close)

    r = sub.add_parser("root", help="print the published month root hex")
    r.add_argument("--month", required=True, help="YYYY-MM")
    r.add_argument("--db", default=None)
    r.set_defaults(func=_cmd_root)

    v = sub.add_parser(
        "verify",
        help="offline: validate statement + proof against root (no DB)",
    )
    v.add_argument("--root", required=True, help="hex digest or path to root.txt")
    v.add_argument("--statement", required=True, help="path to statement JSON")
    v.add_argument(
        "--proof", default=None,
        help="path to proof JSON (default: sibling proofs/<name>.json)",
    )
    v.set_defaults(func=_cmd_verify)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
