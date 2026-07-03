"""Dogfood metrics report for the Antiek Deep Research Bridge.

SPR-06 asks for a small CLI that turns bridge substrate rows into the
operator-facing dogfood metrics doc. This module deliberately reports only
metrics the DuckDB substrate can prove; operator-written notes and qualitative
verdicts stay in the dogfood log.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.db_lock import connect_read

from .db_path import ensure_research_bridge_initialized
from .dogfood_log import default_dogfood_dir

S3_WOULD_RUN_THRESHOLD = 0.60


@dataclass(frozen=True)
class SessionSignalMetrics:
    session_id: str
    would_run: int
    total_signaled: int
    would_run_pct: float


@dataclass(frozen=True)
class SessionBlockMetrics:
    session_id: str
    blocks_pasted: int
    first_block_at: str
    latest_block_at: str


@dataclass(frozen=True)
class SessionDraftExportMetrics:
    session_id: str
    draft_exports: int


@dataclass(frozen=True)
class DogfoodMetrics:
    total_blocks_pasted: int
    total_extractions: int
    total_gap_runs: int
    total_mode_a_draft_exports: int
    total_llm_cost_usd: float
    would_run: int
    total_signaled_prompts: int
    would_run_pct: float | None
    average_blocks_per_session: float
    sessions_with_blocks: int
    sessions_with_gap_runs: int
    sessions_with_blocks_no_gap_runs: tuple[str, ...]
    block_sessions: tuple[SessionBlockMetrics, ...]
    draft_export_sessions: tuple[SessionDraftExportMetrics, ...]
    by_session: tuple[SessionSignalMetrics, ...]

    @property
    def s3_status(self) -> str:
        if self.would_run_pct is None:
            return "INSUFFICIENT"
        return "PASS" if self.would_run_pct >= S3_WOULD_RUN_THRESHOLD else "FAIL"


def _scalar(con: Any, sql: str, params: list[Any] | None = None) -> Any:
    row = con.execute(sql, params or []).fetchone()
    return row[0] if row else None


def _latest_signal_rows(con: Any) -> list[tuple[str | None, str, str]]:
    return con.execute(
        """
        SELECT session_id, prompt_id, signal_type
        FROM (
            SELECT r.session_id,
                   p.prompt_id,
                   s.signal_type,
                   ROW_NUMBER() OVER (
                       PARTITION BY p.prompt_id
                       ORDER BY s.occurred_at DESC, s.signal_id DESC
                   ) AS rn
            FROM research_gap_prompt_signals s
            JOIN research_gap_prompts p ON p.prompt_id = s.prompt_id
            JOIN research_gap_runs r ON r.run_id = p.run_id
        ) ranked
        WHERE rn = 1
        ORDER BY COALESCE(session_id, ''), prompt_id
        """
    ).fetchall()


def build_dogfood_metrics(con: Any) -> DogfoodMetrics:
    total_blocks = int(_scalar(con, "SELECT COUNT(*) FROM research_pastes") or 0)
    total_extractions = int(
        _scalar(con, "SELECT COUNT(*) FROM research_paste_extractions") or 0
    )
    total_gap_runs = int(_scalar(con, "SELECT COUNT(*) FROM research_gap_runs") or 0)
    total_mode_a_draft_exports = int(
        _scalar(con, "SELECT COUNT(*) FROM research_draft_exports") or 0
    )
    extraction_cost = float(
        _scalar(con, "SELECT COALESCE(SUM(cost_usd), 0) FROM research_paste_extractions")
        or 0.0
    )
    gap_cost = float(
        _scalar(con, "SELECT COALESCE(SUM(total_cost_usd), 0) FROM research_gap_runs")
        or 0.0
    )

    session_rows = con.execute(
        """
        SELECT session_id, COUNT(*) AS n, MIN(pasted_at), MAX(pasted_at)
        FROM research_pastes
        WHERE session_id IS NOT NULL AND TRIM(session_id) != ''
        GROUP BY session_id
        ORDER BY session_id
        """
    ).fetchall()
    sessions_with_blocks = len(session_rows)
    average_blocks = (
        sum(int(r[1]) for r in session_rows) / sessions_with_blocks
        if sessions_with_blocks
        else 0.0
    )
    block_session_metrics = tuple(
        SessionBlockMetrics(
            session_id=str(r[0]),
            blocks_pasted=int(r[1]),
            first_block_at=str(r[2]),
            latest_block_at=str(r[3]),
        )
        for r in session_rows
    )
    draft_export_rows = con.execute(
        """
        SELECT session_id, COUNT(*) AS n
        FROM research_draft_exports
        WHERE session_id IS NOT NULL AND TRIM(session_id) != ''
        GROUP BY session_id
        ORDER BY session_id
        """
    ).fetchall()
    draft_export_sessions = tuple(
        SessionDraftExportMetrics(
            session_id=str(r[0]),
            draft_exports=int(r[1]),
        )
        for r in draft_export_rows
    )

    gap_session_rows = con.execute(
        """
        SELECT DISTINCT session_id
        FROM research_gap_runs
        WHERE session_id IS NOT NULL AND TRIM(session_id) != ''
        """
    ).fetchall()
    gap_sessions = {str(r[0]) for r in gap_session_rows}
    block_sessions = {str(r[0]) for r in session_rows}
    sessions_with_blocks_no_gap_runs = tuple(
        sorted(block_sessions.difference(gap_sessions))
    )

    signal_rows = _latest_signal_rows(con)
    would = sum(
        1 for _session_id, _prompt_id, signal in signal_rows if signal == "would_run"
    )
    total_signaled = len(signal_rows)
    pct = (would / total_signaled) if total_signaled else None

    by_session: list[SessionSignalMetrics] = []
    session_signal_counts: dict[str, list[int]] = {}
    for session_id, _prompt_id, signal in signal_rows:
        key = session_id or "(no session)"
        counts = session_signal_counts.setdefault(key, [0, 0])
        counts[1] += 1
        if signal == "would_run":
            counts[0] += 1
    for session_id in sorted(session_signal_counts):
        would_n, total_n = session_signal_counts[session_id]
        by_session.append(
            SessionSignalMetrics(
                session_id=session_id,
                would_run=would_n,
                total_signaled=total_n,
                would_run_pct=would_n / total_n if total_n else 0.0,
            )
        )

    return DogfoodMetrics(
        total_blocks_pasted=total_blocks,
        total_extractions=total_extractions,
        total_gap_runs=total_gap_runs,
        total_mode_a_draft_exports=total_mode_a_draft_exports,
        total_llm_cost_usd=extraction_cost + gap_cost,
        would_run=would,
        total_signaled_prompts=total_signaled,
        would_run_pct=pct,
        average_blocks_per_session=average_blocks,
        sessions_with_blocks=sessions_with_blocks,
        sessions_with_gap_runs=len(gap_sessions),
        sessions_with_blocks_no_gap_runs=sessions_with_blocks_no_gap_runs,
        block_sessions=block_session_metrics,
        draft_export_sessions=draft_export_sessions,
        by_session=tuple(by_session),
    )


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def render_dogfood_report(metrics: DogfoodMetrics) -> str:
    lines = [
        "# Antiek Deep Research Bridge Dogfood Metrics",
        "",
        f"S3 status: {metrics.s3_status}",
        f"S3 would-run threshold: {S3_WOULD_RUN_THRESHOLD * 100:.0f}%",
        f"Mode B would-run rate: {_pct(metrics.would_run_pct)} "
        f"({metrics.would_run}/{metrics.total_signaled_prompts} latest prompt signals)",
        "",
        "## Substrate Totals",
        "",
        f"- Blocks pasted: {metrics.total_blocks_pasted}",
        f"- Extractions recorded: {metrics.total_extractions}",
        f"- Gap runs recorded: {metrics.total_gap_runs}",
        f"- Mode A draft exports recorded: {metrics.total_mode_a_draft_exports}",
        f"- Total recorded LLM cost: ${metrics.total_llm_cost_usd:.4f}",
        "",
        "## Session Coverage",
        "",
        f"- Sessions with pasted blocks: {metrics.sessions_with_blocks}",
        f"- Sessions with gap runs: {metrics.sessions_with_gap_runs}",
        f"- Average blocks per session: {metrics.average_blocks_per_session:.2f}",
        "- Sessions with blocks but no gap run: "
        + (
            ", ".join(metrics.sessions_with_blocks_no_gap_runs)
            if metrics.sessions_with_blocks_no_gap_runs
            else "none"
        ),
        "",
        "## Block Timing By Session",
        "",
    ]
    if not metrics.block_sessions:
        lines.append("- No sessions with pasted blocks recorded yet.")
    else:
        for row in metrics.block_sessions:
            lines.append(
                f"- {row.session_id}: {row.blocks_pasted} block(s), "
                f"first block at {row.first_block_at}, latest block at {row.latest_block_at}"
            )
    lines.extend([
        "",
        "## Mode A Draft Exports By Session",
        "",
    ])
    if not metrics.draft_export_sessions:
        lines.append("- No Mode A draft exports recorded yet.")
    else:
        for row in metrics.draft_export_sessions:
            lines.append(f"- {row.session_id}: {row.draft_exports} draft export(s)")
    lines.extend([
        "",
        "## Would-Run Breakdown",
        "",
    ])
    if not metrics.by_session:
        lines.append("- No prompt signals recorded yet.")
    else:
        for row in metrics.by_session:
            lines.append(
                f"- {row.session_id}: {_pct(row.would_run_pct)} "
                f"({row.would_run}/{row.total_signaled})"
            )
    lines.extend([
        "",
        "## Not Proved By This Report",
        "",
        "- Operator qualitative verdicts; read `operator-log.md` for those.",
        "- Sessions the operator opened without creating any substrate row.",
        "- Whether exported Mode A drafts were sent or published downstream.",
    ])
    return "\n".join(lines) + "\n"


def build_report_from_db_path(db_path: str) -> str:
    con = connect_read(db_path)
    try:
        return render_dogfood_report(build_dogfood_metrics(con))
    finally:
        con.close()


def default_dogfood_metrics_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser()
    return default_dogfood_dir() / "dogfood_metrics.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render Antiek Deep Research Bridge dogfood metrics.",
    )
    parser.add_argument(
        "--db",
        help="DuckDB path. Defaults to ANTIEK_DUCKDB_PATH / substrate default.",
    )
    parser.add_argument(
        "--output",
        help="Markdown output path. Defaults to stdout.",
    )
    args = parser.parse_args(argv)

    db_path = ensure_research_bridge_initialized(args.db)
    report = build_report_from_db_path(db_path)
    if args.output:
        path = default_dogfood_metrics_path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
