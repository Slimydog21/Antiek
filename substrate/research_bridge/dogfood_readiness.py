"""Read-only readiness gate for Deep Research Bridge dogfood closure."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db_path import ensure_research_bridge_initialized
from .dogfood_log import (
    DOGFOOD_PROJECT_COUNT,
    DogfoodLogValidation,
    Wave4CandidatesValidation,
    default_dogfood_dir,
    validate_dogfood_log,
    validate_wave4_candidates,
)
from .dogfood_reconcile import (
    DogfoodSessionReconciliation,
    reconcile_dogfood_sessions_from_db_path,
)
from .dogfood_report import build_report_from_db_path
from .dogfood_verdict import (
    DogfoodVerdictValidation,
    default_verdict_path,
    validate_verdict_doc,
)

READINESS_JSON_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DogfoodMetricsArtifactValidation:
    path: Path
    current: bool
    missing_requirements: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing_requirements


@dataclass(frozen=True)
class DogfoodReadiness:
    dogfood_root: Path
    metrics_path: Path
    verdict_path: Path
    log_validation: DogfoodLogValidation
    wave4_validation: Wave4CandidatesValidation
    reconciliation: DogfoodSessionReconciliation
    metrics_artifact: DogfoodMetricsArtifactValidation
    verdict_validation: DogfoodVerdictValidation
    missing_requirements: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing_requirements


def _resolve_dogfood_root(root: str | Path | None) -> Path:
    return Path(root).expanduser() if root is not None else default_dogfood_dir()


def _resolve_metrics_path(
    metrics_path: str | Path | None,
    dogfood_root: Path,
) -> Path:
    if metrics_path is not None:
        return Path(metrics_path).expanduser()
    return dogfood_root / "dogfood_metrics.md"


def validate_metrics_artifact(
    db_path: str,
    *,
    dogfood_root: str | Path | None = None,
    metrics_path: str | Path | None = None,
) -> DogfoodMetricsArtifactValidation:
    root = _resolve_dogfood_root(dogfood_root)
    path = _resolve_metrics_path(metrics_path, root)
    expected = build_report_from_db_path(db_path, dogfood_root=root)

    missing: list[str] = []
    current = False
    if not path.exists():
        missing.append("dogfood_metrics.md is missing")
    else:
        current = path.read_text(encoding="utf-8") == expected
        if not current:
            missing.append("dogfood_metrics.md is stale; regenerate dogfood-report")

    return DogfoodMetricsArtifactValidation(
        path=path,
        current=current,
        missing_requirements=tuple(missing),
    )


def audit_dogfood_readiness(
    db_path: str,
    *,
    dogfood_root: str | Path | None = None,
    metrics_path: str | Path | None = None,
    verdict_path: str | Path | None = None,
) -> DogfoodReadiness:
    root = _resolve_dogfood_root(dogfood_root)
    resolved_metrics_path = _resolve_metrics_path(metrics_path, root)
    resolved_verdict_path = (
        Path(verdict_path).expanduser() if verdict_path is not None else default_verdict_path()
    )

    log_validation = validate_dogfood_log(root)
    wave4_validation = validate_wave4_candidates(root)
    reconciliation = reconcile_dogfood_sessions_from_db_path(db_path, root=root)
    metrics_artifact = validate_metrics_artifact(
        db_path,
        dogfood_root=root,
        metrics_path=resolved_metrics_path,
    )
    verdict_validation = validate_verdict_doc(resolved_verdict_path)

    missing: list[str] = []
    missing.extend(log_validation.missing_requirements)
    missing.extend(wave4_validation.missing_requirements)
    missing.extend(reconciliation.missing_requirements)
    missing.extend(metrics_artifact.missing_requirements)
    missing.extend(verdict_validation.missing_requirements)

    return DogfoodReadiness(
        dogfood_root=root,
        metrics_path=resolved_metrics_path,
        verdict_path=resolved_verdict_path,
        log_validation=log_validation,
        wave4_validation=wave4_validation,
        reconciliation=reconciliation,
        metrics_artifact=metrics_artifact,
        verdict_validation=verdict_validation,
        missing_requirements=tuple(dict.fromkeys(missing)),
    )


def _status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def render_readiness_summary(readiness: DogfoodReadiness) -> str:
    lines = [
        f"dogfood root: {readiness.dogfood_root}",
        "dogfood log: "
        f"{_status(readiness.log_validation.ok)} "
        f"({len(readiness.log_validation.complete_project_entries)}/"
        f"{DOGFOOD_PROJECT_COUNT} complete projects)",
        "wave4 candidates: "
        f"{_status(readiness.wave4_validation.ok)} "
        f"({len(readiness.wave4_validation.candidates)} candidate(s))",
        "session reconciliation: "
        f"{_status(readiness.reconciliation.ok)} "
        f"({len(readiness.reconciliation.sessions)}/"
        f"{DOGFOOD_PROJECT_COUNT} reconciled sessions)",
        "metrics artifact: "
        f"{_status(readiness.metrics_artifact.ok)} "
        f"({readiness.metrics_path})",
        "verdict document: "
        f"{_status(readiness.verdict_validation.ok)} "
        f"({readiness.verdict_path})",
    ]
    if readiness.ok:
        lines.append("DOGFOOD_READINESS_OK")
    else:
        for missing in readiness.missing_requirements:
            lines.append(f"missing: {missing}")
    return "\n".join(lines) + "\n"


def readiness_to_json_payload(readiness: DogfoodReadiness) -> dict[str, Any]:
    return {
        "schema_version": READINESS_JSON_SCHEMA_VERSION,
        "ok": readiness.ok,
        "dogfood_root": str(readiness.dogfood_root),
        "metrics_path": str(readiness.metrics_path),
        "verdict_path": str(readiness.verdict_path),
        "expected_project_count": DOGFOOD_PROJECT_COUNT,
        "missing_requirements": list(readiness.missing_requirements),
        "checks": {
            "dogfood_log": {
                "ok": readiness.log_validation.ok,
                "operator_log_path": str(readiness.log_validation.operator_log_path),
                "expected_projects": DOGFOOD_PROJECT_COUNT,
                "planned_projects": len(readiness.log_validation.planned_projects),
                "filled_project_entries": len(
                    readiness.log_validation.filled_project_entries
                ),
                "complete_project_entries": len(
                    readiness.log_validation.complete_project_entries
                ),
                "project_session_ids": len(readiness.log_validation.project_entries),
                "missing_requirements": list(
                    readiness.log_validation.missing_requirements
                ),
            },
            "wave4_candidates": {
                "ok": readiness.wave4_validation.ok,
                "wave4_candidates_path": str(
                    readiness.wave4_validation.wave4_candidates_path
                ),
                "valid_candidates": len(readiness.wave4_validation.candidates),
                "missing_requirements": list(
                    readiness.wave4_validation.missing_requirements
                ),
            },
            "session_reconciliation": {
                "ok": readiness.reconciliation.ok,
                "operator_log_path": str(readiness.reconciliation.operator_log_path),
                "expected_sessions": DOGFOOD_PROJECT_COUNT,
                "reconciled_sessions": len(readiness.reconciliation.sessions),
                "sessions": [
                    {
                        "project_name": row.project_name,
                        "session_id": row.session_id,
                        "blocks_pasted": row.blocks_pasted,
                        "gap_runs": row.gap_runs,
                        "draft_exports": row.draft_exports,
                        "prompt_signals": row.prompt_signals,
                    }
                    for row in readiness.reconciliation.sessions
                ],
                "missing_requirements": list(
                    readiness.reconciliation.missing_requirements
                ),
            },
            "metrics_artifact": {
                "ok": readiness.metrics_artifact.ok,
                "path": str(readiness.metrics_artifact.path),
                "current": readiness.metrics_artifact.current,
                "missing_requirements": list(
                    readiness.metrics_artifact.missing_requirements
                ),
            },
            "verdict_document": {
                "ok": readiness.verdict_validation.ok,
                "path": str(readiness.verdict_validation.path),
                "mode_a_verdict": readiness.verdict_validation.mode_a_verdict,
                "mode_b_verdict": readiness.verdict_validation.mode_b_verdict,
                "next_questions": list(readiness.verdict_validation.next_questions),
                "missing_requirements": list(
                    readiness.verdict_validation.missing_requirements
                ),
            },
        },
    }


def render_readiness_json(readiness: DogfoodReadiness) -> str:
    return json.dumps(readiness_to_json_payload(readiness), sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check whether Deep Research Bridge dogfood is ready for verdict closure.",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="DuckDB path. Defaults to ANTIEK_DUCKDB_PATH / substrate default.",
    )
    parser.add_argument(
        "--dogfood-root",
        default=None,
        help="Dogfood directory. Defaults to ~/Desktop/Antiek/runs/adrb.",
    )
    parser.add_argument(
        "--metrics-path",
        default=None,
        help="Metrics report path. Defaults to <dogfood-root>/dogfood_metrics.md.",
    )
    parser.add_argument(
        "--verdict-path",
        default=None,
        help="Verdict path. Defaults to ~/Desktop/Antiek/docs/adrb_post_dogfood_verdict.md.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Write a stable machine-readable readiness payload.",
    )
    args = parser.parse_args(argv)

    db_path = ensure_research_bridge_initialized(args.db)
    readiness = audit_dogfood_readiness(
        db_path,
        dogfood_root=args.dogfood_root,
        metrics_path=args.metrics_path,
        verdict_path=args.verdict_path,
    )
    if args.json:
        sys.stdout.write(render_readiness_json(readiness))
    else:
        sys.stdout.write(render_readiness_summary(readiness))
    return 0 if readiness.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
