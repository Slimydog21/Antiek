"""Operator probe for OA-006 auth vendor selection evidence.

OA-006 closes only when the operator chooses Clerk or Supabase, signs up, and
commits the filed decision artifact. This probe validates that artifact for
completeness against the Sprint 22 integration surface; it does not choose the
vendor or wire the production adapter.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

DEFAULT_DECISION_PATH = Path("docs/decisions/oa-006-auth-vendor.md")

PLACEHOLDER_MARKERS = (
    "_[",
    "[fill in]",
    "[vendor",
    "[date",
    "[todo",
    "TBD",
    "TODO",
    "Clerk / Supabase",
    "Clerk or Supabase",
)

REQUIRED_OPERATOR_STEPS = (
    "Sign up",
    "OAuth providers",
    "callback endpoint",
    "session middleware",
    "sign-up/sign-in UI",
)

REQUIRED_INTEGRATION_FRAGMENTS = (
    "interfaces/research/api/app.py",
    "apps/reading/src/modes/Login/",
    "substrate.multi_user.auth.normalize_verified_claims()",
    "ANTIEK_EXTERNAL_AUTH_VENDOR",
    "ANTIEK_EXTERNAL_AUTH_HEADER_SECRET",
    "X-Antiek-Verified-Claims",
)

REQUIRED_SECURITY_FRAGMENTS = (
    "issuer",
    "audience",
    "expiry",
    "key-rotation",
    "rollback",
)


@dataclass(frozen=True)
class ProbeCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class AuthVendorDecisionProbeResult:
    status: str
    decision_path: str
    decision: str | None
    signup_date: str | None
    checks: list[ProbeCheck]
    does_not_close_oa006: bool = True


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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


def _extract_decision(text: str) -> str | None:
    patterns = (
        r"\*\*Decision:\s*(Clerk|Supabase)\s*\*\*",
        r"^Decision:\s*(Clerk|Supabase)\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).capitalize()
    return None


def _extract_signup_date(text: str) -> str | None:
    match = re.search(
        r"\*\*Sign-up date:\s*(\d{4}-\d{2}-\d{2})\s*\*\*",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r"^Sign-up date:\s*(\d{4}-\d{2}-\d{2})\s*$",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    if not match:
        return None
    candidate = match.group(1)
    try:
        date.fromisoformat(candidate)
    except ValueError:
        return None
    return candidate


def probe_auth_vendor_decision(
    decision_path: Path = DEFAULT_DECISION_PATH,
) -> AuthVendorDecisionProbeResult:
    checks: list[ProbeCheck] = []
    if not decision_path.exists():
        return AuthVendorDecisionProbeResult(
            status="FAIL",
            decision_path=str(decision_path),
            decision=None,
            signup_date=None,
            checks=[
                ProbeCheck(
                    name="decision_file_exists",
                    passed=False,
                    detail=f"missing decision file: {decision_path}",
                )
            ],
        )

    text = _read(decision_path)
    decision = _extract_decision(text)
    signup_date = _extract_signup_date(text)

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
        name="vendor_choice_binary",
        passed=decision in {"Clerk", "Supabase"},
        detail=f"decision={decision!r}",
    ))
    checks.append(ProbeCheck(
        name="signup_date_iso",
        passed=signup_date is not None,
        detail=f"signup_date={signup_date!r}",
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

    missing_steps = _missing_fragments(text, REQUIRED_OPERATOR_STEPS)
    checks.append(ProbeCheck(
        name="operator_steps_covered",
        passed=not missing_steps,
        detail="all OA-006 operator steps covered"
        if not missing_steps
        else "missing=" + ", ".join(missing_steps),
    ))

    missing_integration = _missing_fragments(text, REQUIRED_INTEGRATION_FRAGMENTS)
    checks.append(ProbeCheck(
        name="integration_surface_covered",
        passed=not missing_integration,
        detail="all integration fragments covered"
        if not missing_integration
        else "missing=" + ", ".join(missing_integration),
    ))

    missing_security = _missing_fragments(text, REQUIRED_SECURITY_FRAGMENTS)
    checks.append(ProbeCheck(
        name="security_boundary_covered",
        passed=not missing_security,
        detail="issuer/audience/expiry/key-rotation/rollback covered"
        if not missing_security
        else "missing=" + ", ".join(missing_security),
    ))

    status = "PASS" if all(check.passed for check in checks) else "FAIL"
    return AuthVendorDecisionProbeResult(
        status=status,
        decision_path=str(decision_path),
        decision=decision,
        signup_date=signup_date,
        checks=checks,
    )


def format_text(result: AuthVendorDecisionProbeResult) -> str:
    lines = [
        f"auth-vendor-decision-probe: {result.status}",
        f"decision_path: {result.decision_path}",
        f"decision: {result.decision or ''}",
        f"signup_date: {result.signup_date or ''}",
    ]
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"{marker} {check.name}: {check.detail}")
    lines.append("oa006_closed_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the OA-006 Clerk/Supabase auth-vendor decision artifact. "
            "Does not choose the vendor or close OA-006 by itself."
        )
    )
    parser.add_argument(
        "--decision-path",
        type=Path,
        default=DEFAULT_DECISION_PATH,
        help=f"Path to the filed decision markdown. Default: {DEFAULT_DECISION_PATH}",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = probe_auth_vendor_decision(args.decision_path.expanduser().resolve())
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
