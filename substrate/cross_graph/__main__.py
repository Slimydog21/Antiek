"""Operator CLI for federation administration (Sprint 30+ thread 1).

Substrate-only CLI that performs the local side of the operator-to-
operator federation handshake. The shared-secret exchange itself is
OUT-OF-BAND (operator phones operator, or PGP-encrypted email, or any
other channel) — this CLI only handles what the local substrate needs
to record.

Subcommands::

    python -m substrate.cross_graph register \\
        --partner-id prt-lab --display-name "Partner Lab" \\
        --substrate-url https://lab.example
    # → mints + prints a 64-hex-char shared_secret_hex EXACTLY ONCE.
    #   Hand it to the partner out-of-band.

    python -m substrate.cross_graph register \\
        --partner-id prt-lab --display-name "Partner Lab" \\
        --substrate-url https://lab.example \\
        --shared-secret-hex <secret>
    # → records the supplied secret (use when the OTHER side
    #   generated it and you are recording it locally).

    python -m substrate.cross_graph trust --id prt-lab --notes "verified"
    python -m substrate.cross_graph revoke --id prt-lab --reason "leak"

    python -m substrate.cross_graph list             # latest record per id
    python -m substrate.cross_graph list --trusted    # only TRUSTED
    python -m substrate.cross_graph show --id prt-lab

    python -m substrate.cross_graph config show
    python -m substrate.cross_graph config set --allowed prt-lab \\
        --allowed prt-other --no-require-opt-in

Output: compact table by default; ``--json`` for machine-parseable."""

from __future__ import annotations

import argparse
import json
import sys

from substrate.cross_graph.federation import FederationConfig
from substrate.cross_graph.federation_config_store import (
    load_config as load_federation_config,
)
from substrate.cross_graph.federation_config_store import (
    save_config as save_federation_config,
)
from substrate.cross_graph.partner_identity import (
    PartnerIdentityError,
    PartnerSubstrate,
    generate_shared_secret,
    load_registry,
    register_partner,
    revoke_partner,
    save_record,
    trust_partner,
)

# ── Helpers ────────────────────────────────────────────────────────


def _resolve_db_path(override: str | None) -> str:
    if override:
        return override
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _record_to_dict(rec: PartnerSubstrate) -> dict:
    """Audit-friendly dict shape. NEVER includes shared_secret_hex."""
    return {
        "partner_id": rec.partner_id,
        "display_name": rec.display_name,
        "substrate_url": rec.substrate_url,
        "state": rec.state.value,
        "registered_at": rec.registered_at,
        "last_state_change_at": rec.last_state_change_at,
        "operator_notes": rec.operator_notes,
        "revocation_reason": rec.revocation_reason,
    }


def _print_record(rec: PartnerSubstrate, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(_record_to_dict(rec), indent=2))
        return
    print(f"  partner_id      {rec.partner_id}")
    print(f"  display_name    {rec.display_name}")
    print(f"  substrate_url   {rec.substrate_url}")
    print(f"  state           {rec.state.value}")
    if rec.operator_notes:
        print(f"  notes           {rec.operator_notes}")
    if rec.revocation_reason:
        print(f"  revocation      {rec.revocation_reason}")
    print(f"  last_change_at  {rec.last_state_change_at}")


def _with_write(db_path: str, purpose: str, fn) -> PartnerSubstrate:
    from runtime.db_lock import connect_write

    with connect_write(db_path, purpose=purpose) as con:
        registry = load_registry(con)
        record = fn(registry)
        save_record(con, record)
    return record


# ── Subcommand handlers ────────────────────────────────────────────


def _cmd_register(args: argparse.Namespace) -> int:
    db = _resolve_db_path(args.db)
    if args.shared_secret_hex:
        secret = args.shared_secret_hex
        secret_was_generated = False
    else:
        secret = generate_shared_secret()
        secret_was_generated = True

    try:
        rec = _with_write(
            db, "cli:federation_register",
            lambda registry: register_partner(
                registry,
                display_name=args.display_name,
                substrate_url=args.substrate_url,
                shared_secret_hex=secret,
                operator_notes=args.notes or "",
                partner_id=args.partner_id,
            ),
        )
    except PartnerIdentityError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.json:
        payload = _record_to_dict(rec)
        # The secret rides in JSON output ONLY on this registration
        # call. Subsequent reads never include it.
        payload["shared_secret_hex"] = secret
        payload["secret_was_generated"] = secret_was_generated
        print(json.dumps(payload, indent=2))
    else:
        _print_record(rec, as_json=False)
        print("")
        if secret_was_generated:
            print("  GENERATED shared_secret_hex (hand this to the partner)")
        else:
            print("  RECORDED shared_secret_hex (supplied)")
        print(f"  {secret}")
        print("")
        print(
            "  ⚠  This is the only time this secret will appear in "
            "stdout. Subsequent reads NEVER carry the secret.",
        )
    return 0


def _cmd_trust(args: argparse.Namespace) -> int:
    db = _resolve_db_path(args.db)
    try:
        rec = _with_write(
            db, "cli:federation_trust",
            lambda registry: trust_partner(
                registry,
                partner_id=args.partner_id,
                operator_notes=args.notes or "",
            ),
        )
    except PartnerIdentityError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    _print_record(rec, as_json=args.json)
    return 0


def _cmd_revoke(args: argparse.Namespace) -> int:
    db = _resolve_db_path(args.db)
    try:
        rec = _with_write(
            db, "cli:federation_revoke",
            lambda registry: revoke_partner(
                registry,
                partner_id=args.partner_id,
                revocation_reason=args.reason,
            ),
        )
    except PartnerIdentityError as exc:
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

    if args.trusted:
        records = registry.all_trusted()
    else:
        seen: dict[str, PartnerSubstrate] = {}
        for r in registry.records:
            seen[r.partner_id] = r
        records = [seen[k] for k in sorted(seen)]

    if args.json:
        print(json.dumps(
            [_record_to_dict(r) for r in records], indent=2,
        ))
        return 0
    if not records:
        print("(none)")
        return 0
    for r in records:
        print(f"{r.partner_id:<24}  {r.state.value:<20}  {r.display_name}")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    import duckdb

    db = _resolve_db_path(args.db)
    con = duckdb.connect(db, read_only=True)
    try:
        registry = load_registry(con)
    finally:
        con.close()
    rec = registry.latest(args.partner_id)
    if rec is None:
        print(f"NOT FOUND: {args.partner_id}", file=sys.stderr)
        return 2
    _print_record(rec, as_json=args.json)
    return 0


def _cmd_config_show(args: argparse.Namespace) -> int:
    import duckdb

    db = _resolve_db_path(args.db)
    con = duckdb.connect(db, read_only=True)
    try:
        cfg = load_federation_config(con)
    finally:
        con.close()
    payload = {
        "allowed_partner_substrates": list(cfg.allowed_partner_substrates),
        "require_opt_in_for_outbound_citations": cfg.require_opt_in_for_outbound_citations,
        "require_attribution_for_outbound_citations": cfg.require_attribution_for_outbound_citations,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"  allowed_partner_substrates  {payload['allowed_partner_substrates']}")
        print(f"  require_opt_in              {payload['require_opt_in_for_outbound_citations']}")
        print(f"  require_attribution         {payload['require_attribution_for_outbound_citations']}")
    return 0


def _cmd_config_set(args: argparse.Namespace) -> int:
    from runtime.db_lock import connect_write

    db = _resolve_db_path(args.db)
    cfg = FederationConfig(
        allowed_partner_substrates=tuple(args.allowed or ()),
        require_opt_in_for_outbound_citations=not args.no_require_opt_in,
        require_attribution_for_outbound_citations=not args.no_require_attribution,
    )
    with connect_write(db, purpose="cli:federation_config_set") as con:
        save_federation_config(con, cfg)
    return _cmd_config_show(args)


# ── Parser ─────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m substrate.cross_graph",
        description="Operator CLI for federation administration (Sprint 30+ thread 1).",
    )
    p.add_argument("--db", help="Override DuckDB path; defaults to ANTIEK_DUCKDB_PATH.")
    p.add_argument("--json", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_reg = sub.add_parser("register", help="Register a new partner; mints a shared secret if none supplied.")
    sp_reg.add_argument("--partner-id", required=True)
    sp_reg.add_argument("--display-name", required=True)
    sp_reg.add_argument("--substrate-url", required=True)
    sp_reg.add_argument("--shared-secret-hex", default=None)
    sp_reg.add_argument("--notes", default="")
    sp_reg.set_defaults(func=_cmd_register)

    sp_trust = sub.add_parser("trust", help="PENDING_HANDSHAKE → TRUSTED.")
    sp_trust.add_argument("--id", dest="partner_id", required=True)
    sp_trust.add_argument("--notes", default="")
    sp_trust.set_defaults(func=_cmd_trust)

    sp_revoke = sub.add_parser("revoke", help="TRUSTED → REVOKED (terminal).")
    sp_revoke.add_argument("--id", dest="partner_id", required=True)
    sp_revoke.add_argument("--reason", required=True)
    sp_revoke.set_defaults(func=_cmd_revoke)

    sp_list = sub.add_parser("list", help="List partners.")
    sp_list.add_argument("--trusted", action="store_true")
    sp_list.set_defaults(func=_cmd_list)

    sp_show = sub.add_parser("show", help="Show one partner.")
    sp_show.add_argument("--id", dest="partner_id", required=True)
    sp_show.set_defaults(func=_cmd_show)

    sp_config = sub.add_parser("config", help="FederationConfig singleton.")
    config_sub = sp_config.add_subparsers(dest="config_cmd", required=True)

    sp_config_show = config_sub.add_parser("show")
    sp_config_show.set_defaults(func=_cmd_config_show)

    sp_config_set = config_sub.add_parser("set")
    sp_config_set.add_argument("--allowed", action="append", default=[])
    sp_config_set.add_argument("--no-require-opt-in", action="store_true")
    sp_config_set.add_argument("--no-require-attribution", action="store_true")
    sp_config_set.set_defaults(func=_cmd_config_set)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
