"""Operator probe for OA-005 Autoresearch Wedge 1 ratification.

OA-005/G6 closes only when the operator has run the local mutation cohort and
filed a real ratify-or-reject decision artifact. This probe validates the
mechanical evidence chain without making the decision:

1. Wedge 1 readiness criteria are satisfied.
2. The mutation outcome JSON is present and loadable.
3. The computed verdict is terminal (ratify or reject, not insufficient data).
4. The filed markdown decision exists and matches the computed verdict.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from tools.prompt_autoresearch.outcomes_io import load_outcomes_json
from tools.prompt_autoresearch.readiness import audit_wedge1_readiness
from tools.prompt_autoresearch.verdict import compute_verdict

DEFAULT_ROLE = "synthesizer"
DEFAULT_OUTCOMES_PATH = Path("reports/autoresearch/synthesizer-outcomes.json")
DEFAULT_VERDICT_PATH = Path("docs/decisions/autoresearch-wedge-1-verdict.md")


@dataclass(frozen=True)
class ProbeCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class AutoresearchWedge1ProbeResult:
    status: str
    role: str
    outcomes_path: str
    verdict_path: str
    computed_decision: str | None
    filed_decision: str | None
    iteration_count: int
    acceptance_rate: float
    mean_delta: float
    checks: list[ProbeCheck]
    does_not_close_oa005: bool = True


def _filed_decision(path: Path) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"\*\*Decision:\*\*\s*`(ratify|reject|insufficient_data)`",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(1).lower() if match else None


def probe_autoresearch_wedge1(
    *,
    repo_root: Path,
    role: str = DEFAULT_ROLE,
    outcomes_path: Path = DEFAULT_OUTCOMES_PATH,
    verdict_path: Path = DEFAULT_VERDICT_PATH,
) -> AutoresearchWedge1ProbeResult:
    root = repo_root.resolve()
    outcomes_abs = outcomes_path if outcomes_path.is_absolute() else root / outcomes_path
    verdict_abs = verdict_path if verdict_path.is_absolute() else root / verdict_path
    checks: list[ProbeCheck] = []

    readiness = audit_wedge1_readiness(root)
    unsatisfied = [
        f"{item.id}={item.status}"
        for item in readiness.items
        if item.status != "satisfied"
    ]
    checks.append(ProbeCheck(
        name="readiness_all_satisfied",
        passed=readiness.all_satisfied,
        detail="all readiness criteria satisfied"
        if readiness.all_satisfied
        else "unsatisfied: " + ", ".join(unsatisfied),
    ))

    json_role: str | None = None
    outcomes = []
    load_error: str | None = None
    try:
        json_role, outcomes = load_outcomes_json(outcomes_abs)
    except ValueError as exc:
        load_error = str(exc)
    checks.append(ProbeCheck(
        name="outcomes_json_loadable",
        passed=load_error is None,
        detail=f"loaded {len(outcomes)} outcome(s) from {outcomes_abs}"
        if load_error is None
        else load_error,
    ))

    effective_role = role or json_role
    checks.append(ProbeCheck(
        name="role_matches_outcomes",
        passed=json_role in (None, effective_role),
        detail=f"cli_role={role!r} json_role={json_role!r}",
    ))

    computed_decision: str | None = None
    iteration_count = 0
    acceptance_rate = 0.0
    mean_delta = 0.0
    if load_error is None and effective_role:
        verdict = compute_verdict(effective_role, outcomes)
        computed_decision = verdict.decision
        iteration_count = verdict.iteration_count
        acceptance_rate = verdict.acceptance_rate
        mean_delta = verdict.mean_delta

    checks.append(ProbeCheck(
        name="computed_verdict_terminal",
        passed=computed_decision in {"ratify", "reject"},
        detail=f"computed_decision={computed_decision!r}",
    ))

    filed_decision = _filed_decision(verdict_abs)
    checks.append(ProbeCheck(
        name="verdict_file_exists",
        passed=verdict_abs.is_file(),
        detail=f"path={verdict_abs}",
    ))
    checks.append(ProbeCheck(
        name="filed_decision_terminal",
        passed=filed_decision in {"ratify", "reject"},
        detail=f"filed_decision={filed_decision!r}",
    ))
    checks.append(ProbeCheck(
        name="filed_decision_matches_computed",
        passed=(
            filed_decision in {"ratify", "reject"}
            and computed_decision == filed_decision
        ),
        detail=(
            f"computed_decision={computed_decision!r} "
            f"filed_decision={filed_decision!r}"
        ),
    ))

    return AutoresearchWedge1ProbeResult(
        status="PASS" if all(check.passed for check in checks) else "FAIL",
        role=effective_role or role,
        outcomes_path=str(outcomes_abs),
        verdict_path=str(verdict_abs),
        computed_decision=computed_decision,
        filed_decision=filed_decision,
        iteration_count=iteration_count,
        acceptance_rate=acceptance_rate,
        mean_delta=mean_delta,
        checks=checks,
    )


def format_text(result: AutoresearchWedge1ProbeResult) -> str:
    lines = [
        f"autoresearch-wedge1-probe: {result.status}",
        f"role: {result.role}",
        f"outcomes_path: {result.outcomes_path}",
        f"verdict_path: {result.verdict_path}",
        f"computed_decision: {result.computed_decision}",
        f"filed_decision: {result.filed_decision}",
        f"iteration_count: {result.iteration_count}",
        f"acceptance_rate: {result.acceptance_rate:.3f}",
        f"mean_delta: {result.mean_delta:+.3f}",
    ]
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"{marker} {check.name}: {check.detail}")
    lines.append("oa005_closed_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate OA-005/G6 Autoresearch Wedge 1 ratify-or-reject evidence. "
            "Does not close OA-005 by itself."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root. Defaults to current directory.",
    )
    parser.add_argument(
        "--role",
        default=DEFAULT_ROLE,
        help=f"Role to validate. Default: {DEFAULT_ROLE}",
    )
    parser.add_argument(
        "--outcomes",
        type=Path,
        default=DEFAULT_OUTCOMES_PATH,
        help=f"Mutation outcomes JSON. Default: {DEFAULT_OUTCOMES_PATH}",
    )
    parser.add_argument(
        "--verdict",
        type=Path,
        default=DEFAULT_VERDICT_PATH,
        help=f"Filed verdict markdown. Default: {DEFAULT_VERDICT_PATH}",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = probe_autoresearch_wedge1(
        repo_root=args.repo_root,
        role=args.role,
        outcomes_path=args.outcomes,
        verdict_path=args.verdict,
    )
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
