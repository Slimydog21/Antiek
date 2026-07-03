"""Read-only readiness gate for Deep Research Bridge dogfood closure."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from .db_path import ensure_research_bridge_initialized
from .dogfood_log import (
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
        f"({len(readiness.log_validation.complete_project_entries)}/5 complete projects)",
        "wave4 candidates: "
        f"{_status(readiness.wave4_validation.ok)} "
        f"({len(readiness.wave4_validation.candidates)} candidate(s))",
        "session reconciliation: "
        f"{_status(readiness.reconciliation.ok)} "
        f"({len(readiness.reconciliation.sessions)}/5 reconciled sessions)",
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
    args = parser.parse_args(argv)

    db_path = ensure_research_bridge_initialized(args.db)
    readiness = audit_dogfood_readiness(
        db_path,
        dogfood_root=args.dogfood_root,
        metrics_path=args.metrics_path,
        verdict_path=args.verdict_path,
    )
    sys.stdout.write(render_readiness_summary(readiness))
    return 0 if readiness.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
