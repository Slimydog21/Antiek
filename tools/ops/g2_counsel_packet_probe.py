"""Operator support probe for OA-001/G2 counsel packet completeness.

G2 closes only when counsel reviews the Kalshi-pattern publisher notification
template and the operator commits the decision artifact. This probe validates
the packet the operator sends to counsel: it checks the packet exists, names
the live source files, covers the required legal-context prompts, and that the
current rendered notification template still has the required operator-review
shape.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from substrate.ip_holders import IpHolder, render_notification_email

DEFAULT_PACKET_PATH = Path("docs/g2_counsel_packet.md")
DEFAULT_DECISION_PATH = Path("docs/decisions/g2-lawyer-review.md")

PACKET_REQUIRED_FRAGMENTS = (
    "pre-onboarded escrow",
    "opt-in-only payout",
    "costless opt-out",
    "Bartz v. Anthropic",
    "Hachette v. Internet Archive",
    "Google Books",
    "docs/trust_center_public.md",
    "substrate/ip_holders/__init__.py",
    "NOTIFICATION_EMAIL_TEMPLATE",
    "legal@antiek.ai",
)

EMAIL_REQUIRED_FRAGMENTS = (
    "transformative under fair use",
    "NOT republishing your books",
    "NOT letting users read your books cover-to-cover",
    "Until you claim, no payment routes",
    "opt out at any time",
    "within 30 days",
    "legal@antiek.ai",
)

EMAIL_FORBIDDEN_FRAGMENTS = (
    "infringement",
    "damages",
    "settlement",
    "admission",
    "stole",
)


@dataclass(frozen=True)
class ProbeCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class G2CounselPacketProbeResult:
    status: str
    packet_path: str
    decision_path: str
    checks: list[ProbeCheck]
    does_not_close_oa001: bool = True


def _render_fixture_email() -> str:
    holder = IpHolder(
        ip_holder_id="mit-press",
        display_name="MIT Press",
        legal_contact_email="legal@mitpress.mit.edu",
        status="pre_onboarded",
        escrow_balance_usd=Decimal("0.00"),
        escrow_account_ref=None,
        notification_sent_at=None,
        claimed_at=None,
        opted_out_at=None,
        created_at=datetime.now(UTC).isoformat(),
    )
    return render_notification_email(holder)


def _missing_fragments(text: str, fragments: tuple[str, ...]) -> list[str]:
    folded = " ".join(text.split()).lower()
    return [
        fragment
        for fragment in fragments
        if " ".join(fragment.split()).lower() not in folded
    ]


def probe_g2_counsel_packet(
    *,
    packet_path: Path = DEFAULT_PACKET_PATH,
    decision_path: Path = DEFAULT_DECISION_PATH,
) -> G2CounselPacketProbeResult:
    checks: list[ProbeCheck] = []
    text = ""
    if packet_path.is_file():
        text = packet_path.read_text(encoding="utf-8")
    checks.append(ProbeCheck(
        name="packet_exists",
        passed=packet_path.is_file(),
        detail=f"path={packet_path}",
    ))

    missing_packet = _missing_fragments(text, PACKET_REQUIRED_FRAGMENTS)
    checks.append(ProbeCheck(
        name="packet_required_fragments",
        passed=not missing_packet,
        detail="all required fragments present"
        if not missing_packet
        else "missing=" + ", ".join(missing_packet),
    ))
    checks.append(ProbeCheck(
        name="packet_marks_not_closure",
        passed="does not close G2" in text or "does not close OA-001" in text,
        detail="packet explicitly says it is not the closure artifact",
    ))
    checks.append(ProbeCheck(
        name="packet_names_closure_artifact",
        passed=str(DEFAULT_DECISION_PATH) in text,
        detail=f"expected closure artifact={DEFAULT_DECISION_PATH}",
    ))

    email = _render_fixture_email()
    missing_email = _missing_fragments(email, EMAIL_REQUIRED_FRAGMENTS)
    checks.append(ProbeCheck(
        name="email_required_fragments",
        passed=not missing_email,
        detail="all required template fragments present"
        if not missing_email
        else "missing=" + ", ".join(missing_email),
    ))
    present_forbidden = [
        fragment for fragment in EMAIL_FORBIDDEN_FRAGMENTS
        if fragment.lower() in email.lower()
    ]
    checks.append(ProbeCheck(
        name="email_avoids_forbidden_admission_words",
        passed=not present_forbidden,
        detail="no forbidden words present"
        if not present_forbidden
        else "present=" + ", ".join(present_forbidden),
    ))
    checks.append(ProbeCheck(
        name="decision_not_already_filed",
        passed=not decision_path.exists(),
        detail=(
            f"{decision_path} is absent; G2 remains open"
            if not decision_path.exists()
            else f"{decision_path} exists; inspect before marking G2 closed"
        ),
    ))

    return G2CounselPacketProbeResult(
        status="PASS" if all(check.passed for check in checks) else "FAIL",
        packet_path=str(packet_path),
        decision_path=str(decision_path),
        checks=checks,
    )


def format_text(result: G2CounselPacketProbeResult) -> str:
    lines = [
        f"g2-counsel-packet-probe: {result.status}",
        f"packet_path: {result.packet_path}",
        f"decision_path: {result.decision_path}",
    ]
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"{marker} {check.name}: {check.detail}")
    lines.append("oa001_closed_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the OA-001/G2 counsel packet and live notification "
            "template. Does not close OA-001."
        )
    )
    parser.add_argument(
        "--packet-path",
        type=Path,
        default=DEFAULT_PACKET_PATH,
        help=f"Counsel packet path. Default: {DEFAULT_PACKET_PATH}",
    )
    parser.add_argument(
        "--decision-path",
        type=Path,
        default=DEFAULT_DECISION_PATH,
        help=f"Lawyer-review decision path. Default: {DEFAULT_DECISION_PATH}",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = probe_g2_counsel_packet(
        packet_path=args.packet_path,
        decision_path=args.decision_path,
    )
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
