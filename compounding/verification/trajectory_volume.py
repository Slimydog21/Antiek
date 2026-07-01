"""Loop 3 trajectory-volume and open-weight policy coverage audit.

This module is intentionally read-only. It answers the first Loop 3 unlock
question from ``docs/loop_3_unlock_criteria.md`` without weakening the gate:

* how many sealed investigation trajectories exist, and
* what fraction of LLM dispatch events use an explicitly approved open-weight
  policy id.

The open-weight classifier is allowlist-only. A policy id is not treated as
fine-tunable merely because a model name looks open; the operator must pass an
explicit registry via ``--open-weight-policy-id`` or ``--open-weight-policy-file``.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_MIN_SEALED_INVESTIGATIONS = 10_000
DEFAULT_MIN_OPEN_WEIGHT_FRACTION = 0.80


@dataclass(frozen=True)
class TrajectoryVolumeAudit:
    status: str
    events_dir: str
    sealed_investigation_count: int
    min_sealed_investigations: int
    llm_event_count: int
    open_weight_llm_event_count: int
    open_weight_policy_fraction: float
    min_open_weight_policy_fraction: float
    open_weight_policy_ids: list[str]
    closed_or_unknown_policy_ids: dict[str, int]
    live_jsonl_included: bool
    checks: list[dict[str, Any]]
    does_not_unlock_loop3: bool = True


def load_open_weight_policy_ids(paths: Iterable[Path]) -> set[str]:
    """Load explicit policy ids from JSON or newline-delimited text files.

    Accepted JSON shapes:

    * ``["provider/model", ...]``
    * ``{"open_weight_policy_ids": ["provider/model", ...]}``
    * ``{"provider/model": true, "other": false}``
    """
    policy_ids: set[str] = set()
    for path in paths:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            payload = json.loads(text)
            if isinstance(payload, list):
                policy_ids.update(str(item).strip() for item in payload if str(item).strip())
            elif isinstance(payload, dict) and "open_weight_policy_ids" in payload:
                values = payload["open_weight_policy_ids"]
                if not isinstance(values, list):
                    raise ValueError(
                        f"{path}: open_weight_policy_ids must be a list"
                    )
                policy_ids.update(str(item).strip() for item in values if str(item).strip())
            elif isinstance(payload, dict):
                policy_ids.update(
                    str(key).strip()
                    for key, value in payload.items()
                    if value is True and str(key).strip()
                )
            else:
                raise ValueError(f"{path}: unsupported JSON policy registry")
            continue

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            policy_ids.add(stripped)
    return policy_ids


def _read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _read_parquet_rows(paths: Sequence[Path]) -> list[dict[str, Any]]:
    if not paths:
        return []

    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - duckdb is a core dependency.
        raise RuntimeError("duckdb is required to audit sealed parquet trajectories") from exc

    quoted_paths = ", ".join(json.dumps(str(path)) for path in paths)
    con = duckdb.connect(":memory:")
    try:
        result = con.execute(f"SELECT * FROM read_parquet([{quoted_paths}])")
        columns = [desc[0] for desc in result.description]
        return [dict(zip(columns, row, strict=False)) for row in result.fetchall()]
    finally:
        con.close()


def _is_dispatch_call(row: dict[str, Any]) -> bool:
    action_type = row.get("action_type")
    if action_type == "dispatch.call":
        return True
    payload = row.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return False
    return isinstance(payload, dict) and payload.get("action_type") == "dispatch.call"


def _policy_id(row: dict[str, Any]) -> str | None:
    value = row.get("policy_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    payload = row.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    provider = payload.get("provider")
    model = payload.get("model")
    if isinstance(provider, str) and isinstance(model, str) and provider and model:
        return f"{provider}/{model}"
    return None


def audit_trajectory_volume(
    *,
    events_dir: Path,
    open_weight_policy_ids: Iterable[str] = (),
    include_live_jsonl: bool = False,
    min_sealed_investigations: int = DEFAULT_MIN_SEALED_INVESTIGATIONS,
    min_open_weight_policy_fraction: float = DEFAULT_MIN_OPEN_WEIGHT_FRACTION,
) -> TrajectoryVolumeAudit:
    root = events_dir.expanduser().resolve()
    explicit_open = {item.strip() for item in open_weight_policy_ids if item.strip()}
    parquet_paths = sorted(root.glob("*.parquet")) if root.is_dir() else []
    rows = _read_parquet_rows(parquet_paths)
    if include_live_jsonl and root.is_dir():
        for path in sorted(root.glob("*.jsonl")):
            rows.extend(_read_jsonl_rows(path))

    llm_policy_counts: dict[str, int] = {}
    for row in rows:
        if not _is_dispatch_call(row):
            continue
        policy = _policy_id(row) or "<missing>"
        llm_policy_counts[policy] = llm_policy_counts.get(policy, 0) + 1

    llm_event_count = sum(llm_policy_counts.values())
    open_weight_llm_event_count = sum(
        count for policy, count in llm_policy_counts.items() if policy in explicit_open
    )
    fraction = (
        open_weight_llm_event_count / llm_event_count
        if llm_event_count
        else 0.0
    )
    closed_or_unknown = {
        policy: count
        for policy, count in sorted(llm_policy_counts.items())
        if policy not in explicit_open
    }
    checks = [
        {
            "name": "events_dir_exists",
            "passed": root.is_dir(),
            "detail": str(root),
        },
        {
            "name": "sealed_investigation_count",
            "passed": len(parquet_paths) >= min_sealed_investigations,
            "detail": f"{len(parquet_paths)} >= {min_sealed_investigations}",
        },
        {
            "name": "llm_events_present",
            "passed": llm_event_count > 0,
            "detail": f"{llm_event_count} dispatch.call event(s)",
        },
        {
            "name": "sealed_only_evidence_mode",
            "passed": not include_live_jsonl,
            "detail": (
                "live JSONL excluded"
                if not include_live_jsonl
                else "live JSONL included for diagnostics only"
            ),
        },
        {
            "name": "open_weight_policy_coverage",
            "passed": (
                llm_event_count > 0
                and fraction >= min_open_weight_policy_fraction
            ),
            "detail": (
                f"{fraction:.3f} >= {min_open_weight_policy_fraction:.3f}"
            ),
        },
    ]
    status = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    return TrajectoryVolumeAudit(
        status=status,
        events_dir=str(root),
        sealed_investigation_count=len(parquet_paths),
        min_sealed_investigations=min_sealed_investigations,
        llm_event_count=llm_event_count,
        open_weight_llm_event_count=open_weight_llm_event_count,
        open_weight_policy_fraction=fraction,
        min_open_weight_policy_fraction=min_open_weight_policy_fraction,
        open_weight_policy_ids=sorted(explicit_open),
        closed_or_unknown_policy_ids=closed_or_unknown,
        live_jsonl_included=include_live_jsonl,
        checks=checks,
    )


def format_text(result: TrajectoryVolumeAudit) -> str:
    lines = [
        f"loop3-trajectory-volume: {result.status}",
        f"events_dir: {result.events_dir}",
        f"sealed_investigation_count: {result.sealed_investigation_count}",
        f"min_sealed_investigations: {result.min_sealed_investigations}",
        f"llm_event_count: {result.llm_event_count}",
        f"open_weight_llm_event_count: {result.open_weight_llm_event_count}",
        f"open_weight_policy_fraction: {result.open_weight_policy_fraction:.3f}",
        (
            "min_open_weight_policy_fraction: "
            f"{result.min_open_weight_policy_fraction:.3f}"
        ),
        "open_weight_policy_ids: "
        + (", ".join(result.open_weight_policy_ids) or "<none>"),
        "closed_or_unknown_policy_ids: "
        + (
            ", ".join(
                f"{policy}={count}"
                for policy, count in result.closed_or_unknown_policy_ids.items()
            )
            or "<none>"
        ),
        f"live_jsonl_included: {str(result.live_jsonl_included).lower()}",
    ]
    for check in result.checks:
        marker = "PASS" if check["passed"] else "FAIL"
        lines.append(f"{marker} {check['name']}: {check['detail']}")
    lines.append("loop3_unlocked_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Loop 3 trajectory volume and explicit open-weight policy coverage. "
            "This is read-only and does not unlock Loop 3 by itself."
        )
    )
    parser.add_argument(
        "--events-dir",
        type=Path,
        default=Path("~/.antiek/research_events"),
        help="Trajectory event directory. Defaults to ~/.antiek/research_events.",
    )
    parser.add_argument(
        "--open-weight-policy-id",
        action="append",
        default=[],
        help="Explicit policy id to count as open-weight, e.g. openrouter/deepseek/...",
    )
    parser.add_argument(
        "--open-weight-policy-file",
        type=Path,
        action="append",
        default=[],
        help="JSON or newline-delimited file of explicit open-weight policy ids.",
    )
    parser.add_argument(
        "--include-live-jsonl",
        action="store_true",
        help="Include live JSONL rows for diagnostics. Sealed count still uses parquet only.",
    )
    parser.add_argument(
        "--min-sealed-investigations",
        type=int,
        default=DEFAULT_MIN_SEALED_INVESTIGATIONS,
        help=f"Minimum sealed investigations. Default: {DEFAULT_MIN_SEALED_INVESTIGATIONS}.",
    )
    parser.add_argument(
        "--min-open-weight-policy-fraction",
        type=float,
        default=DEFAULT_MIN_OPEN_WEIGHT_FRACTION,
        help=(
            "Minimum fraction of LLM dispatch events whose policy_id is explicitly "
            f"open-weight. Default: {DEFAULT_MIN_OPEN_WEIGHT_FRACTION}."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.min_sealed_investigations < 1:
        parser.error("--min-sealed-investigations must be >= 1")
    if not 0.0 <= args.min_open_weight_policy_fraction <= 1.0:
        parser.error("--min-open-weight-policy-fraction must be between 0 and 1")

    open_weight_ids = set(args.open_weight_policy_id)
    open_weight_ids.update(
        load_open_weight_policy_ids(
            path.expanduser().resolve() for path in args.open_weight_policy_file
        )
    )
    result = audit_trajectory_volume(
        events_dir=args.events_dir,
        open_weight_policy_ids=open_weight_ids,
        include_live_jsonl=args.include_live_jsonl,
        min_sealed_investigations=args.min_sealed_investigations,
        min_open_weight_policy_fraction=args.min_open_weight_policy_fraction,
    )
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
