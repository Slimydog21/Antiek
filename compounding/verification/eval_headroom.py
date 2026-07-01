"""Loop 3 eval-headroom audit.

Criterion 5 in ``docs/loop_3_unlock_criteria.md`` requires a large curated eval
set, measured current-policy performance, a documented ceiling, and evidence
that cheaper GEPA prompt optimization has already plateaued. This audit checks
the evidence shape without running evals, GEPA, SFT, or RL.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_EVIDENCE_PATH = Path("reports/loop3/eval-headroom.json")
DEFAULT_MIN_EVAL_EXAMPLES = 200
ALLOWED_CEILING_KINDS = {"closed_weight", "human_agreement"}


@dataclass(frozen=True)
class EvalHeadroomAudit:
    status: str
    evidence_path: str
    eval_set_path: str | None
    eval_example_count: int
    min_eval_examples: int
    current_policy_id: str | None
    current_score: float | None
    ceiling_kind: str | None
    ceiling_score: float | None
    reward_noise_floor: float | None
    headroom_margin: float | None
    gepa_plateaued: bool
    checks: list[dict[str, Any]]
    does_not_unlock_loop3: bool = True


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _number(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _resolve_ref(reference: str | None, *, base_dir: Path) -> Path | None:
    if not reference:
        return None
    path = Path(reference).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path


def _count_jsonl_rows(path: Path | None) -> int:
    if path is None or not path.is_file():
        return 0
    count = 0
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if _is_eval_row(payload):
                    count += 1
    except OSError:
        return 0
    return count


def _is_eval_row(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if not _nonempty_str(payload.get("chunk_text")):
        return False
    expected = payload.get("expected_parameters")
    if not isinstance(expected, list):
        return False
    for item in expected:
        if not isinstance(item, dict):
            return False
        if not all(field in item for field in ("name", "value", "units")):
            return False
    return True


def _read_text(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _gepa_plateaued(payload: dict[str, Any] | None, *, base_dir: Path) -> bool:
    if payload is None:
        return False
    report = _resolve_ref(
        payload.get("gepa_report_ref") if _nonempty_str(payload.get("gepa_report_ref")) else None,
        base_dir=base_dir,
    )
    text = _read_text(report).lower()
    return payload.get("gepa_plateaued") is True and "gepa" in text and "plateau" in text


def _ref_exists(payload: dict[str, Any] | None, field: str, *, base_dir: Path) -> bool:
    if payload is None or not _nonempty_str(payload.get(field)):
        return False
    path = _resolve_ref(payload[field], base_dir=base_dir)
    return path is not None and path.is_file()


def audit_eval_headroom(
    *,
    evidence_path: Path = DEFAULT_EVIDENCE_PATH,
    min_eval_examples: int = DEFAULT_MIN_EVAL_EXAMPLES,
) -> EvalHeadroomAudit:
    evidence_abs = evidence_path.expanduser().resolve()
    base_dir = Path.cwd().resolve()
    payload = _load_json_object(evidence_abs) if evidence_abs.is_file() else None
    eval_ref = (
        payload.get("eval_set_path")
        if payload is not None and _nonempty_str(payload.get("eval_set_path"))
        else None
    )
    eval_path = _resolve_ref(eval_ref, base_dir=base_dir)
    eval_count = _count_jsonl_rows(eval_path)
    current_policy_id = (
        payload.get("current_policy_id").strip()
        if payload is not None and _nonempty_str(payload.get("current_policy_id"))
        else None
    )
    current_score = _number(payload.get("current_score")) if payload is not None else None
    ceiling_kind = (
        payload.get("ceiling_kind").strip()
        if payload is not None and _nonempty_str(payload.get("ceiling_kind"))
        else None
    )
    ceiling_score = _number(payload.get("ceiling_score")) if payload is not None else None
    reward_noise_floor = (
        _number(payload.get("reward_noise_floor")) if payload is not None else None
    )
    headroom_margin = (
        ceiling_score - current_score
        if ceiling_score is not None and current_score is not None
        else None
    )
    gepa_plateaued = _gepa_plateaued(payload, base_dir=base_dir)
    checks = [
        {
            "name": "evidence_exists",
            "passed": evidence_abs.is_file(),
            "detail": str(evidence_abs),
        },
        {
            "name": "evidence_json_object",
            "passed": payload is not None,
            "detail": "top-level JSON object",
        },
        {
            "name": "eval_set_exists",
            "passed": eval_path is not None and eval_path.is_file(),
            "detail": str(eval_path) if eval_path is not None else "<missing>",
        },
        {
            "name": "eval_set_min_examples",
            "passed": eval_count >= min_eval_examples,
            "detail": f"{eval_count} >= {min_eval_examples}",
        },
        {
            "name": "default_threshold_evidence_mode",
            "passed": min_eval_examples == DEFAULT_MIN_EVAL_EXAMPLES,
            "detail": f"min_eval_examples={min_eval_examples}",
        },
        {
            "name": "current_policy_measured",
            "passed": current_policy_id is not None and current_score is not None,
            "detail": f"policy_id={current_policy_id!r} score={current_score!r}",
        },
        {
            "name": "current_score_source_exists",
            "passed": _ref_exists(payload, "current_score_ref", base_dir=base_dir),
            "detail": (
                str(payload.get("current_score_ref"))
                if payload is not None and payload.get("current_score_ref")
                else "<missing>"
            ),
        },
        {
            "name": "ceiling_characterized",
            "passed": ceiling_kind in ALLOWED_CEILING_KINDS and ceiling_score is not None,
            "detail": f"kind={ceiling_kind!r} score={ceiling_score!r}",
        },
        {
            "name": "ceiling_source_exists",
            "passed": _ref_exists(payload, "ceiling_ref", base_dir=base_dir),
            "detail": (
                str(payload.get("ceiling_ref"))
                if payload is not None and payload.get("ceiling_ref")
                else "<missing>"
            ),
        },
        {
            "name": "reward_noise_floor_present",
            "passed": reward_noise_floor is not None and reward_noise_floor >= 0,
            "detail": f"reward_noise_floor={reward_noise_floor!r}",
        },
        {
            "name": "reward_noise_floor_source_exists",
            "passed": _ref_exists(payload, "reward_noise_floor_ref", base_dir=base_dir),
            "detail": (
                str(payload.get("reward_noise_floor_ref"))
                if payload is not None and payload.get("reward_noise_floor_ref")
                else "<missing>"
            ),
        },
        {
            "name": "headroom_exceeds_noise",
            "passed": (
                headroom_margin is not None
                and reward_noise_floor is not None
                and headroom_margin > reward_noise_floor
            ),
            "detail": f"margin={headroom_margin!r} noise={reward_noise_floor!r}",
        },
        {
            "name": "gepa_plateaued",
            "passed": gepa_plateaued,
            "detail": "requires gepa_plateaued=true and GEPA plateau report",
        },
    ]
    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return EvalHeadroomAudit(
        status=status,
        evidence_path=str(evidence_abs),
        eval_set_path=str(eval_path) if eval_path is not None else None,
        eval_example_count=eval_count,
        min_eval_examples=min_eval_examples,
        current_policy_id=current_policy_id,
        current_score=current_score,
        ceiling_kind=ceiling_kind,
        ceiling_score=ceiling_score,
        reward_noise_floor=reward_noise_floor,
        headroom_margin=headroom_margin,
        gepa_plateaued=gepa_plateaued,
        checks=checks,
    )


def format_text(result: EvalHeadroomAudit) -> str:
    lines = [
        f"loop3-eval-headroom: {result.status}",
        f"evidence_path: {result.evidence_path}",
        f"eval_set_path: {result.eval_set_path}",
        f"eval_example_count: {result.eval_example_count}",
        f"min_eval_examples: {result.min_eval_examples}",
        f"current_policy_id: {result.current_policy_id}",
        f"current_score: {result.current_score}",
        f"ceiling_kind: {result.ceiling_kind}",
        f"ceiling_score: {result.ceiling_score}",
        f"reward_noise_floor: {result.reward_noise_floor}",
        f"headroom_margin: {result.headroom_margin}",
        f"gepa_plateaued: {str(result.gepa_plateaued).lower()}",
    ]
    for check in result.checks:
        marker = "PASS" if check["passed"] else "FAIL"
        lines.append(f"{marker} {check['name']}: {check['detail']}")
    lines.append("loop3_unlocked_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Loop 3 eval headroom evidence. This is read-only and does "
            "not run GEPA, SFT, RL, or unlock Loop 3 by itself."
        )
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=DEFAULT_EVIDENCE_PATH,
        help=f"Eval-headroom evidence JSON. Default: {DEFAULT_EVIDENCE_PATH}.",
    )
    parser.add_argument(
        "--min-eval-examples",
        type=int,
        default=DEFAULT_MIN_EVAL_EXAMPLES,
        help=f"Minimum curated eval rows. Default: {DEFAULT_MIN_EVAL_EXAMPLES}.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.min_eval_examples < 1:
        parser.error("--min-eval-examples must be >= 1")
    result = audit_eval_headroom(
        evidence_path=args.evidence,
        min_eval_examples=args.min_eval_examples,
    )
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
