"""Operator probe for OA-017 KYC/1099 counsel signoff evidence.

OA-017 closes only when counsel reviews the §9.5 KYC, 1099, and creator ToS
posture and the operator commits the signoff artifact. This probe validates the
artifact against the live substrate thresholds and rechecks the KYC settlement
gate behavior; it does not provide legal advice or close OA-017 by itself.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from substrate.billing.kyc import (
    KYC_PAYOUT_FLOOR_USD_CENTS,
    KycRegistry,
    begin,
    can_settle,
    complete,
    invite,
)
from substrate.billing.tax_reports import IRS_1099_NEC_THRESHOLD_USD_CENTS

DEFAULT_SIGNOFF_PATH = Path("docs/decisions/oa-017-kyc-1099-signoff.md")

PLACEHOLDER_MARKERS = (
    "_[",
    "[fill in]",
    "[counsel",
    "[firm",
    "[date",
    "[todo",
    "TBD",
    "TODO",
)

REQUIRED_FRAGMENTS = (
    "US tax",
    "KYC",
    "1099",
    "Terms of Service",
    "Stripe Connect",
    "substrate/billing/kyc.py",
    "substrate/billing/tax_reports.py",
    "creator accounts",
)


@dataclass(frozen=True)
class ProbeCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Kyc1099SignoffProbeResult:
    status: str
    signoff_path: str
    counsel_name_present: bool
    firm_present: bool
    signed_date_present: bool
    kyc_payout_floor_usd_cents: int
    irs_1099_nec_threshold_usd_cents: int
    checks: list[ProbeCheck]
    does_not_close_oa017: bool = True


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


def _field_present(text: str, label: str) -> bool:
    patterns = (
        rf"\*\*{re.escape(label)}:\*\*[ \t]*\S+",
        rf"\*\*{re.escape(label)}:[ \t]*[^*\s][^*]*\*\*",
        rf"^{re.escape(label)}:[ \t]*\S+",
    )
    return any(
        re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        for pattern in patterns
    )


def _mentions_money_amount(text: str, cents: int) -> bool:
    dollars = cents // 100
    patterns = (
        rf"\${dollars}(?:\.00)?\b",
        rf"{dollars}\s*USD",
        rf"{cents}\s*cents",
    )
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _live_kyc_gate_checks() -> list[ProbeCheck]:
    registry = KycRegistry()
    recipient_ref = "oa017-probe-creator"
    below_or_at_floor = can_settle(
        registry,
        recipient_ref=recipient_ref,
        amount_usd_cents=KYC_PAYOUT_FLOOR_USD_CENTS,
    )
    above_floor_without_kyc = can_settle(
        registry,
        recipient_ref=recipient_ref,
        amount_usd_cents=KYC_PAYOUT_FLOOR_USD_CENTS + 1,
    )
    invite(registry, recipient_ref=recipient_ref, stripe_account_ref="acct_oa017")
    begin(registry, recipient_ref=recipient_ref)
    complete(registry, recipient_ref=recipient_ref, stripe_account_ref="acct_oa017")
    above_floor_with_kyc = can_settle(
        registry,
        recipient_ref=recipient_ref,
        amount_usd_cents=KYC_PAYOUT_FLOOR_USD_CENTS + 1,
    )
    return [
        ProbeCheck(
            name="kyc_floor_rollover_allowed",
            passed=below_or_at_floor is True,
            detail=f"amount_cents={KYC_PAYOUT_FLOOR_USD_CENTS}",
        ),
        ProbeCheck(
            name="above_floor_requires_kyc",
            passed=above_floor_without_kyc is False,
            detail=f"amount_cents={KYC_PAYOUT_FLOOR_USD_CENTS + 1}",
        ),
        ProbeCheck(
            name="completed_kyc_allows_above_floor",
            passed=above_floor_with_kyc is True,
            detail=f"amount_cents={KYC_PAYOUT_FLOOR_USD_CENTS + 1}",
        ),
    ]


def probe_kyc_1099_signoff(
    signoff_path: Path = DEFAULT_SIGNOFF_PATH,
) -> Kyc1099SignoffProbeResult:
    checks: list[ProbeCheck] = []
    if not signoff_path.exists():
        checks.append(ProbeCheck(
            name="signoff_file_exists",
            passed=False,
            detail=f"missing signoff file: {signoff_path}",
        ))
        checks.extend(_live_kyc_gate_checks())
        return Kyc1099SignoffProbeResult(
            status="FAIL",
            signoff_path=str(signoff_path),
            counsel_name_present=False,
            firm_present=False,
            signed_date_present=False,
            kyc_payout_floor_usd_cents=KYC_PAYOUT_FLOOR_USD_CENTS,
            irs_1099_nec_threshold_usd_cents=IRS_1099_NEC_THRESHOLD_USD_CENTS,
            checks=checks,
        )

    text = signoff_path.read_text(encoding="utf-8")
    counsel_name_present = _field_present(text, "Counsel")
    firm_present = _field_present(text, "Firm")
    signed_date_present = _field_present(text, "Signed")
    missing_fragments = _missing_fragments(text, REQUIRED_FRAGMENTS)
    checks.extend([
        ProbeCheck(
            name="signoff_file_exists",
            passed=True,
            detail=f"path={signoff_path}",
        ),
        ProbeCheck(
            name="no_template_placeholders",
            passed=not _has_placeholder(text),
            detail="no template placeholders remain"
            if not _has_placeholder(text)
            else "template placeholders remain",
        ),
        ProbeCheck(
            name="counsel_name_present",
            passed=counsel_name_present,
            detail="counsel field populated",
        ),
        ProbeCheck(
            name="firm_present",
            passed=firm_present,
            detail="firm field populated",
        ),
        ProbeCheck(
            name="signed_date_present",
            passed=signed_date_present,
            detail="signed date field populated",
        ),
        ProbeCheck(
            name="signoff_required_fragments",
            passed=not missing_fragments,
            detail="all required fragments present"
            if not missing_fragments
            else "missing=" + ", ".join(missing_fragments),
        ),
        ProbeCheck(
            name="kyc_payout_floor_named",
            passed=_mentions_money_amount(text, KYC_PAYOUT_FLOOR_USD_CENTS),
            detail=f"expected=${KYC_PAYOUT_FLOOR_USD_CENTS / 100:.2f}",
        ),
        ProbeCheck(
            name="irs_1099_threshold_named",
            passed=_mentions_money_amount(text, IRS_1099_NEC_THRESHOLD_USD_CENTS),
            detail=f"expected=${IRS_1099_NEC_THRESHOLD_USD_CENTS / 100:.2f}",
        ),
    ])
    checks.extend(_live_kyc_gate_checks())
    return Kyc1099SignoffProbeResult(
        status="PASS" if all(check.passed for check in checks) else "FAIL",
        signoff_path=str(signoff_path),
        counsel_name_present=counsel_name_present,
        firm_present=firm_present,
        signed_date_present=signed_date_present,
        kyc_payout_floor_usd_cents=KYC_PAYOUT_FLOOR_USD_CENTS,
        irs_1099_nec_threshold_usd_cents=IRS_1099_NEC_THRESHOLD_USD_CENTS,
        checks=checks,
    )


def format_text(result: Kyc1099SignoffProbeResult) -> str:
    lines = [
        f"kyc-1099-signoff-probe: {result.status}",
        f"signoff_path: {result.signoff_path}",
        f"counsel_name_present: {result.counsel_name_present}",
        f"firm_present: {result.firm_present}",
        f"signed_date_present: {result.signed_date_present}",
        f"kyc_payout_floor_usd_cents: {result.kyc_payout_floor_usd_cents}",
        f"irs_1099_nec_threshold_usd_cents: {result.irs_1099_nec_threshold_usd_cents}",
    ]
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"{marker} {check.name}: {check.detail}")
    lines.append("oa017_closed_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the OA-017 KYC/1099/creator-ToS counsel signoff artifact "
            "and live KYC settlement gate. Does not close OA-017 by itself."
        )
    )
    parser.add_argument(
        "--signoff-path",
        type=Path,
        default=DEFAULT_SIGNOFF_PATH,
        help=f"Signoff artifact path. Default: {DEFAULT_SIGNOFF_PATH}",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = probe_kyc_1099_signoff(args.signoff_path.expanduser().resolve())
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
