#!/usr/bin/env python3
"""Smoke the Phase-8 candidate replay opt-in path without model dispatch."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from interfaces.research.api.broadcast import EventBroadcaster
from middleware.archive.archive import ArchiveInputs, archive_synthesis_via_db
from middleware.backtest import backtest
from middleware.outcomes.recorder import build_outcome_record, record_outcome_via_db
from orchestration.loop_one import orchestrator as orch
from orchestration.loop_one.coordinator import InvestigationCoordinator
from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path


@contextmanager
def _patched_env(values: dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def _archive_synthesis(
    db_path: Path,
    *,
    synthesis_id: str,
    investigation_id: str,
    question: str,
) -> None:
    init_database_at_path(str(db_path))
    with connect_write(str(db_path), purpose="phase8_replay_smoke") as con:
        archive_synthesis_via_db(
            con,
            ArchiveInputs(
                target_question=question,
                synthesis_timestamp=datetime.now(UTC),
                status="passed",
                implicit_recommendation="proceed",
                thesis_text=f"Smoke synthesis for {question}",
                model_versions={"smoke": "stub"},
            ),
            investigation_id=investigation_id,
            synthesis_id=synthesis_id,
        )
        record_outcome_via_db(
            con,
            build_outcome_record(
                synthesis_id=synthesis_id,
                observer="phase8-replay-smoke",
                payload={"thesis_outcomes": [{"outcome": "confirmed"}]},
            ),
        )


async def _run_smoke() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="phase8-replay-smoke-") as tmp:
        root = Path(tmp)
        baseline_db = root / "baseline.duckdb"
        overlay_parent = root / "workspaces"
        heldout_ids = ("heldout-smoke-1", "heldout-smoke-2")
        for heldout_id in heldout_ids:
            _archive_synthesis(
                baseline_db,
                synthesis_id=heldout_id,
                investigation_id=f"inv-{heldout_id}",
                question=f"Will candidate replay handle {heldout_id}?",
            )

        async def _stub_candidate_backtest(**kwargs: Any) -> Any:
            heldout_id = str(kwargs["heldout_synthesis_id"])
            workspace = kwargs["workspace"]
            candidate_id = f"candidate-{heldout_id}"
            investigation_id = orch._phase8_replay_investigation_id(heldout_id)
            _archive_synthesis(
                workspace.db_path,
                synthesis_id=candidate_id,
                investigation_id=investigation_id,
                question=f"Candidate replay for {heldout_id}",
            )
            import duckdb

            con = duckdb.connect(str(workspace.db_path), read_only=True)
            try:
                return backtest(con, candidate_id)
            finally:
                con.close()

        original_runner = orch._phase8_run_candidate_heldout_backtest
        env = {
            "ANTIEK_DUCKDB_PATH": str(baseline_db),
            orch.PHASE8_REPLAY_HELDOUT_SYNTHESIS_IDS_ENV: ",".join(heldout_ids),
            orch.PHASE8_REPLAY_OVERLAY_PARENT_ENV: str(overlay_parent),
            orch.PHASE8_REPLAY_RUNNER_ENV: "loop1",
            "ANTIEK_RESEARCH_EVENTS_DIR": str(root / "prod-events"),
            "ANTIEK_RESEARCH_DIR": str(root / "prod-research"),
            "ANTIEK_KNOWLEDGE_SKILLS_DIR": str(root / "prod-skills"),
        }
        try:
            orch._phase8_run_candidate_heldout_backtest = _stub_candidate_backtest
            with _patched_env(env):
                broadcaster = EventBroadcaster()
                evaluation = orch._phase8_candidate_replay_evaluation(
                    ctx=orch.InvestigationContext(
                        investigation_id="phase8-replay-smoke",
                        question="Smoke Phase-8 candidate replay",
                    ),
                    synthesis_row={
                        "synthesis_id": "syn-phase8-replay-smoke",
                        "investigation_id": "phase8-replay-smoke",
                        "target_question": "Smoke Phase-8 candidate replay",
                        "implicit_recommendation": "proceed",
                        "thesis": {"thesis_summary": "Smoke candidate replay."},
                    },
                    matched_domains=["quantum-computing-knowledge"],
                    broadcaster=broadcaster,
                    coordinator=InvestigationCoordinator(broadcaster),
                )
                if inspect.isawaitable(evaluation):
                    evaluation = await evaluation
        finally:
            orch._phase8_run_candidate_heldout_backtest = original_runner

        assert evaluation is not None
        return {
            "ready_for_gate": evaluation.ready_for_gate,
            "replay_status": evaluation.replay.status,
            "candidate_reports": len(evaluation.replay.reports),
            "errors": [error.__dict__ for error in evaluation.replay.errors],
            "baseline_score": evaluation.comparison.baseline_score,
            "candidate_score": evaluation.comparison.candidate_score,
            "cohort_size": evaluation.comparison.cohort_size,
            "notes": evaluation.notes,
        }


def main() -> int:
    summary = asyncio.run(_run_smoke())
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["candidate_reports"] == 2 and not summary["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
