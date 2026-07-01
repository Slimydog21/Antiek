"""Operator probe for OA-019 SOC 2 pursue/defer decision evidence.

OA-019 closes only when the operator has made and committed the real
PURSUE/DEFER decision. This probe validates the filed decision artifact for
completeness and threshold consistency; it does not make the decision.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_DECISION_PATH = Path("docs/soc2_decision.md")
PLACEHOLDER_MARKERS = (
    "_[",
    "[fill in]",
    "[count",
    "[link",
    "[amount",
    "[total",
    "[firm name",
    "[expected",
    "[YYYY",
    "PURSUE / DEFER",
    "ready / gap",
    "READY / GAPS REMAIN",
)


@dataclass(frozen=True)
class ProbeCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Soc2DecisionProbeResult:
    status: str
    decision_path: str
    decision: str | None
    deals_blocked_count: int | None
    gated_pipeline_count: int | None
    estimated_acv_at_risk_usd: int | None
    checks: list[ProbeCheck]
    does_not_close_oa019: bool = True


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_decision(text: str) -> str | None:
    match = re.search(
        r"\*\*Decision:\s*(PURSUE|DEFER)\s*\*\*",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(1).upper() if match else None


def _extract_int_after(label: str, text: str) -> int | None:
    match = re.search(
        rf"{re.escape(label)}\s*:\s*(\d+)\b",
        text,
        flags=re.IGNORECASE,
    )
    return int(match.group(1)) if match else None


def _extract_money_after(label: str, text: str) -> int | None:
    match = re.search(
        rf"{re.escape(label)}\s*:\s*\$?\s*([0-9][0-9,]*)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _section(text: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return ""
    rest = text[match.end():]
    next_heading = re.search(r"^##\s+", rest, flags=re.MULTILINE)
    return rest[: next_heading.start()] if next_heading else rest


def _has_placeholder(text: str) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in PLACEHOLDER_MARKERS)


def _non_placeholder_line(text: str, prefix: str) -> bool:
    for line in text.splitlines():
        if line.strip().startswith(prefix):
            return not _has_placeholder(line) and bool(line.split(":", 1)[-1].strip())
    return False


def _control_rows(text: str) -> list[str]:
    rows: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and "Sprint 18 scaffold" not in stripped:
            if "---" in stripped:
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if len(cells) == 4 and cells[0] != "Control":
                rows.append(stripped)
    return rows


def probe_soc2_decision(decision_path: Path) -> Soc2DecisionProbeResult:
    checks: list[ProbeCheck] = []
    if not decision_path.exists():
        return Soc2DecisionProbeResult(
            status="FAIL",
            decision_path=str(decision_path),
            decision=None,
            deals_blocked_count=None,
            gated_pipeline_count=None,
            estimated_acv_at_risk_usd=None,
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
    deals_blocked = _extract_int_after("Deals blocked on SOC 2 specifically", text)
    gated_pipeline = _extract_int_after("Pipeline of SOC-2-gated prospects", text)
    acv_at_risk = _extract_money_after(
        "Estimated annual contract value at risk if SOC 2 not pursued",
        text,
    )

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
        name="decision_binary",
        passed=decision in {"PURSUE", "DEFER"},
        detail=f"decision={decision!r}",
    ))
    checks.append(ProbeCheck(
        name="author_filled",
        passed=_non_placeholder_line(text, "**Author:**"),
        detail="author field populated",
    ))
    checks.append(ProbeCheck(
        name="decided_date_filled",
        passed=_non_placeholder_line(text, "**Decided:**"),
        detail="decided date populated",
    ))
    checks.append(ProbeCheck(
        name="procurement_counts_present",
        passed=deals_blocked is not None and gated_pipeline is not None,
        detail=(
            f"deals_blocked={deals_blocked!r} "
            f"gated_pipeline={gated_pipeline!r}"
        ),
    ))
    checks.append(ProbeCheck(
        name="acv_at_risk_present",
        passed=acv_at_risk is not None,
        detail=f"estimated_acv_at_risk_usd={acv_at_risk!r}",
    ))

    rows = _control_rows(text)
    checks.append(ProbeCheck(
        name="substrate_control_rows_populated",
        passed=bool(rows) and all(not _has_placeholder(row) for row in rows),
        detail=f"control_rows={len(rows)}",
    ))
    checks.append(ProbeCheck(
        name="substrate_readiness_verdict_filled",
        passed=_non_placeholder_line(text, "**Substrate readiness verdict:**"),
        detail="substrate readiness verdict populated",
    ))

    threshold_pursue = (
        (deals_blocked is not None and deals_blocked >= 1)
        or (gated_pipeline is not None and gated_pipeline >= 3)
    )
    if decision == "PURSUE":
        pursue_section = _section(text, "§4 If PURSUE")
        checks.append(ProbeCheck(
            name="pursue_threshold_consistent",
            passed=threshold_pursue,
            detail=(
                f"deals_blocked={deals_blocked!r} "
                f"gated_pipeline={gated_pipeline!r}"
            ),
        ))
        checks.append(ProbeCheck(
            name="pursue_plan_filled",
            passed=bool(pursue_section.strip()) and not _has_placeholder(pursue_section),
            detail="pursue section populated",
        ))
    elif decision == "DEFER":
        defer_section = _section(text, "§5 If DEFER")
        checks.append(ProbeCheck(
            name="defer_threshold_consistent",
            passed=not threshold_pursue,
            detail=(
                f"deals_blocked={deals_blocked!r} "
                f"gated_pipeline={gated_pipeline!r}"
            ),
        ))
        checks.append(ProbeCheck(
            name="defer_rationale_filled",
            passed=bool(defer_section.strip()) and not _has_placeholder(defer_section),
            detail="defer section populated",
        ))

    status = "PASS" if all(check.passed for check in checks) else "FAIL"
    return Soc2DecisionProbeResult(
        status=status,
        decision_path=str(decision_path),
        decision=decision,
        deals_blocked_count=deals_blocked,
        gated_pipeline_count=gated_pipeline,
        estimated_acv_at_risk_usd=acv_at_risk,
        checks=checks,
    )


def format_text(result: Soc2DecisionProbeResult) -> str:
    lines = [
        f"soc2-decision-probe: {result.status}",
        f"decision_path: {result.decision_path}",
        f"decision: {result.decision or ''}",
        f"deals_blocked_count: {result.deals_blocked_count}",
        f"gated_pipeline_count: {result.gated_pipeline_count}",
        f"estimated_acv_at_risk_usd: {result.estimated_acv_at_risk_usd}",
    ]
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"{marker} {check.name}: {check.detail}")
    lines.append("oa019_closed_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the OA-019 SOC 2 pursue/defer decision artifact. "
            "Does not make the decision or close OA-019 by itself."
        )
    )
    parser.add_argument(
        "--decision-path",
        type=Path,
        default=DEFAULT_DECISION_PATH,
        help=f"Path to the filed decision markdown. Default: {DEFAULT_DECISION_PATH}",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = probe_soc2_decision(args.decision_path.expanduser().resolve())
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
