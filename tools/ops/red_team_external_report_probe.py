"""Operator probe for OA-008 external anti-gaming red-team report.

OA-008 closes only when an external firm files the Sprint 23-24 red-team
report with a GO verdict. This probe validates the filed markdown artifact for
non-template evidence across the four attack classes and the final calibration
verdict; it does not replace the external review.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from substrate.anti_gaming.red_team import AttackClass, run_red_team_report

DEFAULT_REPORT_PATH = Path("docs/sprint23_red_team.md")
PLACEHOLDER_MARKERS = (
    "_[",
    "[fill in]",
    "[to be filled in",
    "[YYYY",
    "[PASS / FAIL]",
    "[YES / NO]",
    "[GO / NO-GO]",
    "Template — to be filled in",
)

REQUIRED_SCOPE_FRAGMENTS = (
    "external red-team",
    "substrate/anti_gaming/",
    "tools/stripe_connect/payouts.py",
    "pre-payout",
)


@dataclass(frozen=True)
class ProbeCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class RedTeamExternalReportProbeResult:
    status: str
    report_path: str
    author_present: bool
    reviewed_date_present: bool
    substrate_version_present: bool
    checks: list[ProbeCheck]
    does_not_close_oa008: bool = True


def _fold(text: str) -> str:
    return " ".join(text.split()).lower()


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


def _missing_fragments(text: str, fragments: tuple[str, ...]) -> list[str]:
    folded = _fold(text)
    return [
        fragment
        for fragment in fragments
        if _fold(fragment) not in folded
    ]


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"^###\s+{re.escape(heading)}\b.*$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not match:
        return ""
    rest = text[match.end():]
    next_heading = re.search(r"^###\s+", rest, flags=re.MULTILINE)
    return rest[: next_heading.start()] if next_heading else rest


def _attack_heading_fragment(attack_class: AttackClass) -> str:
    return {
        AttackClass.A_BOTNET_VIEW_INFLATION: "Attack class A",
        AttackClass.B_ATTRIBUTION_GRAPH_INJECTION: "Attack class B",
        AttackClass.C_MULTI_ACCOUNT_SELF_ATTRIBUTION: "Attack class C",
        AttackClass.D_CREATOR_CLUSTER_COLLUSION: "Attack class D",
    }[attack_class]


def _attack_checks(text: str) -> list[ProbeCheck]:
    checks: list[ProbeCheck] = []
    for attack_class in AttackClass:
        heading = _attack_heading_fragment(attack_class)
        section = _section(text, heading)
        checks.append(ProbeCheck(
            name=f"{attack_class.value}_section_present",
            passed=bool(section.strip()),
            detail=heading,
        ))
        checks.append(ProbeCheck(
            name=f"{attack_class.value}_observed_result_filled",
            passed=(
                bool(section.strip())
                and "observed result:" in section.lower()
                and "[to be filled in" not in section.lower()
            ),
            detail="observed result populated",
        ))
        checks.append(ProbeCheck(
            name=f"{attack_class.value}_verdict_pass",
            passed=bool(re.search(
                r"\*\*Verdict:\*\*[ \t]*(PASS)\b|"
                r"\*\*Verdict:[ \t]*(PASS)[ \t]*\*\*",
                section,
                flags=re.IGNORECASE,
            )),
            detail="attack verdict PASS",
        ))
    return checks


def _closing_verdict_checks(text: str) -> list[ProbeCheck]:
    return [
        ProbeCheck(
            name="all_attack_classes_caught",
            passed=bool(re.search(
                r"\*\*All four attack classes caught pre-payout\?\*\*[ \t]*YES\b|"
                r"\*\*All four attack classes caught pre-payout\?:[ \t]*YES[ \t]*\*\*",
                text,
                flags=re.IGNORECASE,
            )),
            detail="§4 all-four caught answer is YES",
        ),
        ProbeCheck(
            name="false_positive_within_target",
            passed=bool(re.search(
                r"\*\*False-positive rate within target\?\*\*[ \t]*YES\b|"
                r"\*\*False-positive rate within target\?:[ \t]*YES[ \t]*\*\*",
                text,
                flags=re.IGNORECASE,
            )),
            detail="§4 false-positive answer is YES",
        ),
        ProbeCheck(
            name="detection_latency_within_target",
            passed=bool(re.search(
                r"\*\*Detection latency within target\?\*\*[ \t]*YES\b|"
                r"\*\*Detection latency within target\?:[ \t]*YES[ \t]*\*\*",
                text,
                flags=re.IGNORECASE,
            )),
            detail="§4 latency answer is YES",
        ),
        ProbeCheck(
            name="recommended_go",
            passed=bool(re.search(
                r"\*\*Recommended go/no-go for Sprint 23-24 ship:\*\*[ \t]*GO\b|"
                r"\*\*Recommended go/no-go for Sprint 23-24 ship:[ \t]*GO[ \t]*\*\*",
                text,
                flags=re.IGNORECASE,
            )),
            detail="§4 recommended verdict GO",
        ),
    ]


def probe_red_team_external_report(
    report_path: Path = DEFAULT_REPORT_PATH,
) -> RedTeamExternalReportProbeResult:
    checks: list[ProbeCheck] = []
    baseline = run_red_team_report(substrate_version="probe-baseline", fp_sample_size=200)
    if not report_path.exists():
        checks.append(ProbeCheck(
            name="report_file_exists",
            passed=False,
            detail=f"missing report file: {report_path}",
        ))
        checks.append(ProbeCheck(
            name="internal_baseline_go",
            passed=baseline.overall_verdict == "GO",
            detail=f"internal baseline verdict={baseline.overall_verdict}",
        ))
        return RedTeamExternalReportProbeResult(
            status="FAIL",
            report_path=str(report_path),
            author_present=False,
            reviewed_date_present=False,
            substrate_version_present=False,
            checks=checks,
        )

    text = report_path.read_text(encoding="utf-8")
    author_present = _field_present(text, "Author")
    reviewed_date_present = _field_present(text, "Reviewed")
    substrate_version_present = _field_present(text, "Substrate version under review")
    missing_scope = _missing_fragments(text, REQUIRED_SCOPE_FRAGMENTS)
    checks.extend([
        ProbeCheck(
            name="report_file_exists",
            passed=True,
            detail=f"path={report_path}",
        ),
        ProbeCheck(
            name="no_template_placeholders",
            passed=not _has_placeholder(text),
            detail="no template placeholders remain"
            if not _has_placeholder(text)
            else "template placeholders remain",
        ),
        ProbeCheck(
            name="author_present",
            passed=author_present,
            detail="external author field populated",
        ),
        ProbeCheck(
            name="reviewed_date_present",
            passed=reviewed_date_present,
            detail="review date populated",
        ),
        ProbeCheck(
            name="substrate_version_present",
            passed=substrate_version_present,
            detail="substrate version populated",
        ),
        ProbeCheck(
            name="scope_required_fragments",
            passed=not missing_scope,
            detail="all required scope fragments present"
            if not missing_scope
            else "missing=" + ", ".join(missing_scope),
        ),
        ProbeCheck(
            name="internal_baseline_go",
            passed=baseline.overall_verdict == "GO",
            detail=f"internal baseline verdict={baseline.overall_verdict}",
        ),
    ])
    checks.extend(_attack_checks(text))
    checks.extend(_closing_verdict_checks(text))
    return RedTeamExternalReportProbeResult(
        status="PASS" if all(check.passed for check in checks) else "FAIL",
        report_path=str(report_path),
        author_present=author_present,
        reviewed_date_present=reviewed_date_present,
        substrate_version_present=substrate_version_present,
        checks=checks,
    )


def format_text(result: RedTeamExternalReportProbeResult) -> str:
    lines = [
        f"red-team-external-report-probe: {result.status}",
        f"report_path: {result.report_path}",
        f"author_present: {result.author_present}",
        f"reviewed_date_present: {result.reviewed_date_present}",
        f"substrate_version_present: {result.substrate_version_present}",
    ]
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"{marker} {check.name}: {check.detail}")
    lines.append("oa008_closed_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the OA-008 external red-team report artifact. "
            "Does not replace external review or close OA-008 by itself."
        )
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help=f"Report path. Default: {DEFAULT_REPORT_PATH}",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = probe_red_team_external_report(args.report_path.expanduser().resolve())
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
