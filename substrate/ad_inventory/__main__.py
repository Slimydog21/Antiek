"""Operator CLI for advertiser admission (Sprint 23-24 phase 5).

Substrate-only CLI that exercises the advertiser-onboarding state
machine against the on-disk DuckDB. Mirrors the
``acquisition.search.exa`` pattern: ``python -m
substrate.ad_inventory <subcommand>``.

Subcommands::

    python -m substrate.ad_inventory submit --display-name "Acme" \\
        --contact-email ops@acme.example --vertical recruiting \\
        --vertical saas --intent hiring_manager --budget-cents 50000

    python -m substrate.ad_inventory approve --id adv-acme --notes vetted
    python -m substrate.ad_inventory reject  --id adv-acme \\
        --reason "off-brand"
    python -m substrate.ad_inventory activate --id adv-acme \\
        --legal-gate-passed
    python -m substrate.ad_inventory suspend --id adv-acme \\
        --reason "brand-safety review"
    python -m substrate.ad_inventory churn  --id adv-acme

    python -m substrate.ad_inventory list             # latest record per id
    python -m substrate.ad_inventory list --serving    # only ACTIVE
    python -m substrate.ad_inventory show --id adv-acme

Output: compact table by default; ``--json`` for machine-parseable.

The operator is responsible for §9.0 legal-gate assertion. The
substrate refuses ``activate`` unless ``--legal-gate-passed`` is set;
omitting the flag prints a clear refusal."""

from __future__ import annotations

import argparse
import json
import sys

from substrate.ad_inventory.advertiser_onboarding import (
    AdvertiserOnboardingError,
    AdvertiserRecord,
    activate_advertiser,
    approve_advertiser,
    churn_advertiser,
    load_registry,
    reject_advertiser,
    save_record,
    submit_application,
    suspend_advertiser,
)

# ── Helpers ────────────────────────────────────────────────────────


def _resolve_db_path(override: str | None) -> str:
    if override:
        return override
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _print_record(rec: AdvertiserRecord, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps({
            "advertiser_id": rec.advertiser_id,
            "display_name": rec.display_name,
            "contact_email": rec.contact_email,
            "verticals": list(rec.verticals),
            "audience_intents": list(rec.audience_intents),
            "status": rec.status.value,
            "submitted_at": rec.submitted_at,
            "last_status_change_at": rec.last_status_change_at,
            "operator_notes": rec.operator_notes,
            "rejection_reason": rec.rejection_reason,
            "monthly_budget_usd_cents": rec.monthly_budget_usd_cents,
        }, indent=2))
        return
    print(f"  advertiser_id   {rec.advertiser_id}")
    print(f"  display_name    {rec.display_name}")
    print(f"  contact         {rec.contact_email}")
    print(f"  status          {rec.status.value}")
    if rec.verticals:
        print(f"  verticals       {', '.join(rec.verticals)}")
    if rec.audience_intents:
        print(f"  intents         {', '.join(rec.audience_intents)}")
    if rec.monthly_budget_usd_cents is not None:
        print(f"  budget          ${rec.monthly_budget_usd_cents / 100:,.2f}/mo")
    if rec.operator_notes:
        print(f"  notes           {rec.operator_notes}")
    if rec.rejection_reason:
        print(f"  rejection       {rec.rejection_reason}")
    print(f"  last_change_at  {rec.last_status_change_at}")


def _with_write(db_path: str, purpose: str, fn) -> AdvertiserRecord:
    """Common pattern: load → transition → save inside a single
    locked write."""
    from runtime.db_lock import connect_write

    with connect_write(db_path, purpose=purpose) as con:
        registry = load_registry(con)
        record = fn(registry)
        save_record(con, record)
    return record


# ── Subcommand handlers ────────────────────────────────────────────


def _cmd_submit(args: argparse.Namespace) -> int:
    db = _resolve_db_path(args.db)
    try:
        rec = _with_write(
            db, "cli:advertiser_submit",
            lambda registry: submit_application(
                registry,
                display_name=args.display_name,
                contact_email=args.contact_email,
                verticals=tuple(args.vertical or ()),
                audience_intents=tuple(args.intent or ()),
                monthly_budget_usd_cents=args.budget_cents,
                advertiser_id=args.advertiser_id,
            ),
        )
    except AdvertiserOnboardingError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    _print_record(rec, as_json=args.json)
    return 0


def _cmd_approve(args: argparse.Namespace) -> int:
    db = _resolve_db_path(args.db)
    try:
        rec = _with_write(
            db, "cli:advertiser_approve",
            lambda registry: approve_advertiser(
                registry,
                advertiser_id=args.advertiser_id,
                operator_notes=args.notes or "",
            ),
        )
    except AdvertiserOnboardingError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    _print_record(rec, as_json=args.json)
    return 0


def _cmd_reject(args: argparse.Namespace) -> int:
    db = _resolve_db_path(args.db)
    try:
        rec = _with_write(
            db, "cli:advertiser_reject",
            lambda registry: reject_advertiser(
                registry,
                advertiser_id=args.advertiser_id,
                rejection_reason=args.reason,
            ),
        )
    except AdvertiserOnboardingError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    _print_record(rec, as_json=args.json)
    return 0


def _cmd_activate(args: argparse.Namespace) -> int:
    if not args.legal_gate_passed:
        print(
            "REFUSED: --legal-gate-passed is required.\n"
            "The §9.0 legal gate is a binding invariant — the operator "
            "must assert it has passed against a real graph before any "
            "advertiser becomes ACTIVE. Pass --legal-gate-passed only "
            "after that assertion is true.",
            file=sys.stderr,
        )
        return 2
    db = _resolve_db_path(args.db)
    try:
        rec = _with_write(
            db, "cli:advertiser_activate",
            lambda registry: activate_advertiser(
                registry,
                advertiser_id=args.advertiser_id,
                legal_gate_passed=True,
            ),
        )
    except AdvertiserOnboardingError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    _print_record(rec, as_json=args.json)
    return 0


def _cmd_suspend(args: argparse.Namespace) -> int:
    db = _resolve_db_path(args.db)
    try:
        rec = _with_write(
            db, "cli:advertiser_suspend",
            lambda registry: suspend_advertiser(
                registry,
                advertiser_id=args.advertiser_id,
                reason=args.reason,
            ),
        )
    except AdvertiserOnboardingError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    _print_record(rec, as_json=args.json)
    return 0


def _cmd_churn(args: argparse.Namespace) -> int:
    db = _resolve_db_path(args.db)
    try:
        rec = _with_write(
            db, "cli:advertiser_churn",
            lambda registry: churn_advertiser(
                registry, advertiser_id=args.advertiser_id,
            ),
        )
    except AdvertiserOnboardingError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    _print_record(rec, as_json=args.json)
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    import duckdb

    db = _resolve_db_path(args.db)
    con = duckdb.connect(db, read_only=True)
    try:
        registry = load_registry(con)
    finally:
        con.close()

    if args.serving:
        records = registry.all_serving()
    else:
        seen: dict[str, AdvertiserRecord] = {}
        for r in registry.records:
            seen[r.advertiser_id] = r
        records = [seen[k] for k in sorted(seen)]

    if args.json:
        print(json.dumps([
            {
                "advertiser_id": r.advertiser_id,
                "display_name": r.display_name,
                "status": r.status.value,
                "verticals": list(r.verticals),
            }
            for r in records
        ], indent=2))
        return 0

    if not records:
        print("(none)")
        return 0
    for r in records:
        print(f"{r.advertiser_id:<24}  {r.status.value:<16}  {r.display_name}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    import duckdb

    db = _resolve_db_path(args.db)
    con = duckdb.connect(db, read_only=True)
    try:
        registry = load_registry(con)
    finally:
        con.close()
    rec = registry.latest(args.advertiser_id)
    if rec is None:
        print(f"NOT FOUND: {args.advertiser_id}", file=sys.stderr)
        return 2
    _print_record(rec, as_json=args.json)
    return 0


# ── Parser wiring ──────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m substrate.ad_inventory",
        description="Operator CLI for advertiser admission (Sprint 23-24 phase 5).",
    )
    p.add_argument("--db", help="Override DuckDB path; defaults to ANTIEK_DUCKDB_PATH.")
    p.add_argument("--json", action="store_true", help="Machine-parseable JSON output.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_submit = sub.add_parser("submit", help="Submit a new advertiser application.")
    sp_submit.add_argument("--display-name", required=True)
    sp_submit.add_argument("--contact-email", required=True)
    sp_submit.add_argument("--vertical", action="append", default=[])
    sp_submit.add_argument("--intent", action="append", default=[])
    sp_submit.add_argument("--budget-cents", type=int, default=None)
    sp_submit.add_argument("--advertiser-id", default=None)
    sp_submit.set_defaults(func=_cmd_submit)

    sp_approve = sub.add_parser("approve", help="Approve a PENDING_REVIEW application.")
    sp_approve.add_argument("--id", dest="advertiser_id", required=True)
    sp_approve.add_argument("--notes", default="")
    sp_approve.set_defaults(func=_cmd_approve)

    sp_reject = sub.add_parser("reject", help="Reject a PENDING_REVIEW or APPROVED application (terminal).")
    sp_reject.add_argument("--id", dest="advertiser_id", required=True)
    sp_reject.add_argument("--reason", required=True)
    sp_reject.set_defaults(func=_cmd_reject)

    sp_activate = sub.add_parser("activate", help="APPROVED → ACTIVE (requires --legal-gate-passed).")
    sp_activate.add_argument("--id", dest="advertiser_id", required=True)
    sp_activate.add_argument(
        "--legal-gate-passed", action="store_true",
        help="Assert §9.0 legal-gate has passed for the production graph.",
    )
    sp_activate.set_defaults(func=_cmd_activate)

    sp_suspend = sub.add_parser("suspend", help="ACTIVE → SUSPENDED.")
    sp_suspend.add_argument("--id", dest="advertiser_id", required=True)
    sp_suspend.add_argument("--reason", required=True)
    sp_suspend.set_defaults(func=_cmd_suspend)

    sp_churn = sub.add_parser("churn", help="ACTIVE/SUSPENDED → CHURNED (terminal).")
    sp_churn.add_argument("--id", dest="advertiser_id", required=True)
    sp_churn.set_defaults(func=_cmd_churn)

    sp_list = sub.add_parser("list", help="List advertisers (latest record per id).")
    sp_list.add_argument("--serving", action="store_true", help="Only ACTIVE.")
    sp_list.set_defaults(func=_cmd_list)

    sp_show = sub.add_parser("show", help="Show latest record for one advertiser.")
    sp_show.add_argument("--id", dest="advertiser_id", required=True)
    sp_show.set_defaults(func=_cmd_show)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
