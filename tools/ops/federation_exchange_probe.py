"""Operator probe for OA-018 synthetic federation exchange support.

OA-018 closes only after a real partner instance federates the first slice and
the operator records the exchange decision. This probe packages the mechanical
support evidence locally: two fresh DuckDB-backed Antiek instances configure
each other as trusted partners, sign an outbound citation, accept it inbound,
persist the nonce, and reject replay.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from runtime.db_lock import connect_write
from substrate.cross_graph.federation import (
    FederationConfig,
    federate_outbound_citation,
)
from substrate.cross_graph.federation_config_store import (
    load_config as load_federation_config,
)
from substrate.cross_graph.federation_config_store import (
    save_config as save_federation_config,
)
from substrate.cross_graph.inbound import (
    accept_inbound_citation,
    load_active_nonces,
    remember_nonce_persistent,
)
from substrate.cross_graph.partner_identity import (
    generate_shared_secret,
    load_registry,
    register_partner,
    save_record,
    trust_partner,
    verify_partner_token,
)
from substrate.graph.schema import init_database

SENDER_PARTNER_ID = "prt-oa018-sender"
RECEIVER_PARTNER_ID = "prt-oa018-receiver"
NONCE = "oa018-synthetic-nonce"


@dataclass(frozen=True)
class ProbeCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class FederationExchangeProbeResult:
    status: str
    sender_db_path: str
    receiver_db_path: str
    sender_partner_id: str
    receiver_partner_id: str
    sender_reference_id: str | None
    receiver_reference_id: str | None
    revenue_routing_handle: str | None
    checks: list[ProbeCheck]
    does_not_close_oa018: bool = True


def _init_db(db_path: Path) -> None:
    con = connect_write(str(db_path), purpose="oa018_federation_probe_init")
    try:
        init_database(con)
    finally:
        con.close()


def _configure_partner_instance(
    *,
    db_path: Path,
    allowed_partner_id: str,
    partner_id: str,
    partner_name: str,
    partner_url: str,
    shared_secret_hex: str,
    operator_notes: str,
) -> None:
    con = connect_write(str(db_path), purpose="oa018_federation_probe_config")
    try:
        save_federation_config(
            con,
            FederationConfig(
                allowed_partner_substrates=(allowed_partner_id,),
                require_opt_in_for_outbound_citations=True,
                require_attribution_for_outbound_citations=True,
            ),
        )
        registry = load_registry(con)
        pending = register_partner(
            registry,
            display_name=partner_name,
            substrate_url=partner_url,
            shared_secret_hex=shared_secret_hex,
            partner_id=partner_id,
            operator_notes=operator_notes,
        )
        save_record(con, pending)
        trusted = trust_partner(
            registry,
            partner_id=partner_id,
            operator_notes=f"{operator_notes}; synthetic probe trusted",
        )
        save_record(con, trusted)
    finally:
        con.close()


def _default_receiver_path(sender_db_path: Path) -> Path:
    return sender_db_path.with_name(f"{sender_db_path.stem}.receiver.duckdb")


def run_probe(
    sender_db_path: Path,
    receiver_db_path: Path | None = None,
) -> FederationExchangeProbeResult:
    receiver_path = receiver_db_path or _default_receiver_path(sender_db_path)
    for db_path in (sender_db_path, receiver_path):
        _init_db(db_path)

    shared_secret = generate_shared_secret()
    _configure_partner_instance(
        db_path=sender_db_path,
        allowed_partner_id=RECEIVER_PARTNER_ID,
        partner_id=RECEIVER_PARTNER_ID,
        partner_name="OA-018 Synthetic Receiver",
        partner_url="https://receiver.synthetic.antiek.local",
        shared_secret_hex=shared_secret,
        operator_notes="OA-018 synthetic sender-side partner",
    )
    _configure_partner_instance(
        db_path=receiver_path,
        allowed_partner_id=SENDER_PARTNER_ID,
        partner_id=SENDER_PARTNER_ID,
        partner_name="OA-018 Synthetic Sender",
        partner_url="https://sender.synthetic.antiek.local",
        shared_secret_hex=shared_secret,
        operator_notes="OA-018 synthetic receiver-side partner",
    )

    checks: list[ProbeCheck] = []

    sender_con = connect_write(
        str(sender_db_path), purpose="oa018_federation_probe_sender",
    )
    try:
        sender_cfg = load_federation_config(sender_con)
        sender_registry = load_registry(sender_con)
        sender_partner = sender_registry.latest(RECEIVER_PARTNER_ID)
        checks.append(ProbeCheck(
            name="sender_config_persisted",
            passed=sender_cfg.allowed_partner_substrates == (RECEIVER_PARTNER_ID,),
            detail=(
                "sender allows receiver partner "
                f"{sender_cfg.allowed_partner_substrates!r}"
            ),
        ))
        checks.append(ProbeCheck(
            name="sender_partner_trusted",
            passed=sender_partner is not None and sender_partner.state.value == "trusted",
            detail="sender registry latest receiver partner is trusted",
        ))
        outbound = federate_outbound_citation(
            config=sender_cfg,
            partner_registry=sender_registry,
            partner_id=RECEIVER_PARTNER_ID,
            referencing_user_id="user-oa018-sender",
            referencing_investigation_id="inv-oa018-synthetic",
            referenced_user_id="user-oa018-receiver",
            referenced_note_id="note-oa018-slice",
            revenue_routing_handle="revshare:oa018:synthetic",
            referenced_user_opted_in=True,
            referenced_user_attribution_consented=True,
            nonce=NONCE,
        )
        checks.append(ProbeCheck(
            name="outbound_signed_token",
            passed=outbound.signed_token.startswith("v1."),
            detail=(
                "sender produced transient signed token for "
                f"{outbound.partner_id}"
            ),
        ))
    finally:
        sender_con.close()

    receiver_con = connect_write(
        str(receiver_path), purpose="oa018_federation_probe_receiver",
    )
    try:
        receiver_cfg = load_federation_config(receiver_con)
        receiver_registry = load_registry(receiver_con)
        receiver_partner = receiver_registry.latest(SENDER_PARTNER_ID)
        checks.append(ProbeCheck(
            name="receiver_config_persisted",
            passed=receiver_cfg.allowed_partner_substrates == (SENDER_PARTNER_ID,),
            detail=(
                "receiver allows sender partner "
                f"{receiver_cfg.allowed_partner_substrates!r}"
            ),
        ))
        checks.append(ProbeCheck(
            name="receiver_partner_trusted",
            passed=receiver_partner is not None and receiver_partner.state.value == "trusted",
            detail="receiver registry latest sender partner is trusted",
        ))
        ledger = load_active_nonces(receiver_con)
        accepted = accept_inbound_citation(
            config=receiver_cfg,
            partner_registry=receiver_registry,
            nonce_ledger=ledger,
            partner_id=SENDER_PARTNER_ID,
            token=outbound.signed_token,
        )
        checks.append(ProbeCheck(
            name="inbound_accepted",
            passed=accepted.accepted and accepted.reference is not None,
            detail="receiver accepted signed outbound citation",
        ))

        if receiver_partner is not None:
            payload = verify_partner_token(
                shared_secret_hex=receiver_partner.shared_secret_hex,
                token=outbound.signed_token,
            )
        else:
            payload = None
        nonce_persisted = False
        if accepted.accepted and isinstance(payload, dict) and isinstance(
            payload.get("nonce"), str,
        ):
            nonce_persisted = remember_nonce_persistent(
                receiver_con,
                nonce=payload["nonce"],
                partner_id=SENDER_PARTNER_ID,
            )
        checks.append(ProbeCheck(
            name="nonce_persisted",
            passed=nonce_persisted,
            detail="receiver persisted verified nonce for restart-safe replay defense",
        ))

        inherited_ledger = load_active_nonces(receiver_con)
        replay = accept_inbound_citation(
            config=receiver_cfg,
            partner_registry=receiver_registry,
            nonce_ledger=inherited_ledger,
            partner_id=SENDER_PARTNER_ID,
            token=outbound.signed_token,
        )
        checks.append(ProbeCheck(
            name="replay_rejected",
            passed=not replay.accepted and (
                replay.rejection is not None
                and replay.rejection.value == "replay_detected"
            ),
            detail="receiver rejected the same signed citation after nonce reload",
        ))
    finally:
        receiver_con.close()

    return FederationExchangeProbeResult(
        status="PASS" if all(check.passed for check in checks) else "FAIL",
        sender_db_path=str(sender_db_path),
        receiver_db_path=str(receiver_path),
        sender_partner_id=SENDER_PARTNER_ID,
        receiver_partner_id=RECEIVER_PARTNER_ID,
        sender_reference_id=outbound.reference.reference_id,
        receiver_reference_id=(
            accepted.reference.reference_id
            if accepted.reference is not None
            else None
        ),
        revenue_routing_handle=accepted.revenue_routing_handle,
        checks=checks,
    )


def format_text(result: FederationExchangeProbeResult) -> str:
    lines = [
        f"federation-exchange-probe: {result.status}",
        f"sender_db_path: {result.sender_db_path}",
        f"receiver_db_path: {result.receiver_db_path}",
        f"sender_partner_id: {result.sender_partner_id}",
        f"receiver_partner_id: {result.receiver_partner_id}",
        f"sender_reference_id: {result.sender_reference_id or ''}",
        f"receiver_reference_id: {result.receiver_reference_id or ''}",
        f"revenue_routing_handle: {result.revenue_routing_handle or ''}",
    ]
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"{marker} {check.name}: {check.detail}")
    lines.append("oa018_closed_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a local two-instance synthetic federation exchange probe. "
            "Does not contact a real partner or close OA-018 by itself."
        )
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        help=(
            "Fresh sender DuckDB path to create. Defaults to a temporary "
            "probe DB."
        ),
    )
    parser.add_argument(
        "--receiver-db-path",
        type=Path,
        help=(
            "Fresh receiver DuckDB path to create. Defaults to a sibling of "
            "--db-path, or a second temporary DB."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    return parser


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    sender = args.db_path.expanduser().resolve()
    receiver = (
        args.receiver_db_path.expanduser().resolve()
        if args.receiver_db_path is not None
        else _default_receiver_path(sender)
    )
    if sender == receiver:
        raise ValueError("--db-path and --receiver-db-path must differ")
    for db_path in (sender, receiver):
        if db_path.exists():
            raise FileExistsError(f"probe DB path must not already exist: {db_path}")
        db_path.parent.mkdir(parents=True, exist_ok=True)
    return sender, receiver


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    try:
        if args.db_path is not None:
            sender_path, receiver_path = _resolve_paths(args)
            result = run_probe(sender_path, receiver_path)
        else:
            with tempfile.TemporaryDirectory(
                prefix="antiek-oa018-federation-",
            ) as tmpdir:
                sender_path = Path(tmpdir) / "sender.duckdb"
                receiver_path = Path(tmpdir) / "receiver.duckdb"
                result = run_probe(sender_path, receiver_path)
    except (FileExistsError, ValueError) as exc:
        parser.error(str(exc))

    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
