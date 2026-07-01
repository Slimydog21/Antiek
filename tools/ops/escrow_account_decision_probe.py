"""Operator probe for OA-014 segregated escrow account evidence.

OA-014 closes only when the operator opens a real segregated regulated escrow
account, stores the live reference in production secrets, and commits the
decision artifact. This probe validates the artifact and rechecks the payout
substrate's anti-commingling guard; it does not record account numbers.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from substrate.anti_gaming.verdict import FraudVerdict, FraudVerdictKind
from substrate.rev_share import MINIMUM_PAYOUT_USD_CENTS
from tools.stripe_connect import MockStripeProvider, StripeAccountStatus, StripeConnectAccount
from tools.stripe_connect.payouts import RevSharePayoutRouter, route_impression_revenue

DEFAULT_DECISION_PATH = Path("docs/decisions/oa-014-escrow-account.md")

PLACEHOLDER_MARKERS = (
    "_[",
    "[fill in]",
    "[bank",
    "[date",
    "[secret",
    "[account",
    "TBD",
    "TODO",
)

REQUIRED_DECISION_FRAGMENTS = (
    "segregated regulated",
    "not commingled",
    "fiduciary institution",
    "production secret",
    "segregated_account_ref",
    "RevSharePayoutRouter",
    "StripeOperationsLog",
    "tools/stripe_connect/accounts.py",
    "docs/decisions/oa-014-escrow-account.md",
)


@dataclass(frozen=True)
class ProbeCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class EscrowAccountDecisionProbeResult:
    status: str
    decision_path: str
    account_ref_present: bool
    checks: list[ProbeCheck]
    does_not_close_oa014: bool = True


def _fold(text: str) -> str:
    return " ".join(text.split()).lower()


def _missing_fragments(text: str, fragments: tuple[str, ...]) -> list[str]:
    folded = _fold(text)
    return [
        fragment
        for fragment in fragments
        if _fold(fragment) not in folded
    ]


def _has_placeholder(text: str) -> bool:
    return any(marker.lower() in text.lower() for marker in PLACEHOLDER_MARKERS)


def _non_placeholder_line(text: str, prefix: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            value = stripped.split(":", 1)[-1].strip().strip("*").strip()
            return bool(value) and not _has_placeholder(stripped)
    return False


def _has_account_ref_evidence(text: str) -> bool:
    patterns = (
        r"\*\*Segregated account ref:[ \t]*[^*\s][^*]*\*\*",
        r"\*\*Segregated account ref:\*\*[ \t]*\S+",
        r"\*\*Production secret ref:[ \t]*[^*\s][^*]*\*\*",
        r"\*\*Production secret ref:\*\*[ \t]*\S+",
        r"^Segregated account ref:[ \t]*\S+",
        r"^Production secret ref:[ \t]*\S+",
    )
    return any(re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE) for pattern in patterns)


def _live_guard_checks() -> list[ProbeCheck]:
    provider = MockStripeProvider()
    router = RevSharePayoutRouter(provider=provider)
    account_id = provider.create_connect_account(
        display_name="oa014-probe",
        legal_contact_email=None,
        account_kind="user_creator",
    )
    router.register_account(StripeConnectAccount(
        connect_account_id=account_id,
        account_kind="user_creator",
        substrate_ref="oa014-probe-user",
        status=StripeAccountStatus.ACTIVE,
    ))

    outcomes, _ = route_impression_revenue(
        router,
        impression_id="oa014-probe-impression",
        ad_revenue_cents=MINIMUM_PAYOUT_USD_CENTS * 10,
        attribution_shares={"doc-oa014": 1.0},
        document_to_recipient={"doc-oa014": ("creator", "oa014-probe-user")},
        verdict=FraudVerdict(kind=FraudVerdictKind.PASS, signals=()),
        current_month_index=1,
    )
    first_status = outcomes[0].status if outcomes else None
    return [
        ProbeCheck(
            name="missing_segregated_ref_escrows",
            passed=first_status == "escrowed",
            detail=f"outcome_status={first_status!r}",
        ),
        ProbeCheck(
            name="missing_segregated_ref_blocks_transfer",
            passed=len(provider.transfers) == 0,
            detail=f"transfer_count={len(provider.transfers)}",
        ),
    ]


def probe_escrow_account_decision(
    decision_path: Path = DEFAULT_DECISION_PATH,
) -> EscrowAccountDecisionProbeResult:
    checks: list[ProbeCheck] = []
    if not decision_path.exists():
        checks.append(ProbeCheck(
            name="decision_file_exists",
            passed=False,
            detail=f"missing decision file: {decision_path}",
        ))
        checks.extend(_live_guard_checks())
        return EscrowAccountDecisionProbeResult(
            status="FAIL",
            decision_path=str(decision_path),
            account_ref_present=False,
            checks=checks,
        )

    text = decision_path.read_text(encoding="utf-8")
    account_ref_present = _has_account_ref_evidence(text)
    checks.append(ProbeCheck(
        name="decision_file_exists",
        passed=True,
        detail=f"path={decision_path}",
    ))
    checks.append(ProbeCheck(
        name="no_template_placeholders",
        passed=not _has_placeholder(text),
        detail="no template placeholders remain"
        if not _has_placeholder(text)
        else "template placeholders remain",
    ))
    checks.append(ProbeCheck(
        name="author_filled",
        passed=_non_placeholder_line(text, "**Author:**")
        or _non_placeholder_line(text, "Author:"),
        detail="author field populated",
    ))
    checks.append(ProbeCheck(
        name="decided_date_filled",
        passed=_non_placeholder_line(text, "**Decided:**")
        or _non_placeholder_line(text, "Decided:"),
        detail="decided date populated",
    ))
    checks.append(ProbeCheck(
        name="account_or_secret_ref_recorded",
        passed=account_ref_present,
        detail="segregated account or production secret reference recorded",
    ))

    missing = _missing_fragments(text, REQUIRED_DECISION_FRAGMENTS)
    checks.append(ProbeCheck(
        name="decision_required_fragments",
        passed=not missing,
        detail="all required fragments present" if not missing else "missing=" + ", ".join(missing),
    ))
    checks.extend(_live_guard_checks())

    return EscrowAccountDecisionProbeResult(
        status="PASS" if all(check.passed for check in checks) else "FAIL",
        decision_path=str(decision_path),
        account_ref_present=account_ref_present,
        checks=checks,
    )


def format_text(result: EscrowAccountDecisionProbeResult) -> str:
    lines = [
        f"escrow-account-decision-probe: {result.status}",
        f"decision_path: {result.decision_path}",
        f"account_ref_present: {'yes' if result.account_ref_present else 'no'}",
    ]
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"{marker} {check.name}: {check.detail}")
    lines.append("oa014_closed_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the OA-014 segregated escrow account decision artifact "
            "and live anti-commingling payout guard. Does not close OA-014 by itself."
        )
    )
    parser.add_argument(
        "--decision-path",
        type=Path,
        default=DEFAULT_DECISION_PATH,
        help=f"Decision artifact path. Default: {DEFAULT_DECISION_PATH}",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = probe_escrow_account_decision(args.decision_path.expanduser().resolve())
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
