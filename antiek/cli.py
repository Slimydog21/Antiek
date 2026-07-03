"""Top-level Antiek CLI.

The historical ``tools.antiek_cli`` module remains the implementation of
``antiek check``. This package owns product-facing commands exposed through the
``antiek`` console script declared in pyproject.toml.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from runtime.db_lock import connect_read, connect_write
from substrate.research_bridge.db_path import ensure_research_bridge_initialized
from substrate.research_bridge.dogfood_log import (
    validate_dogfood_log,
    validate_wave4_candidates,
    write_dogfood_scaffold,
)
from substrate.research_bridge.dogfood_reconcile import (
    reconcile_dogfood_sessions,
)
from substrate.research_bridge.dogfood_report import (
    build_report_from_db_path,
    default_dogfood_metrics_path,
)
from substrate.research_bridge.dogfood_verdict import (
    validate_verdict_doc,
    write_verdict_scaffold,
)
from substrate.research_bridge.draft_export import record_draft_export
from substrate.research_bridge.gap import would_run_percentage


def _cmd_research_bridge_dogfood_report(args: argparse.Namespace) -> int:
    db_path = ensure_research_bridge_initialized(args.db)
    report = build_report_from_db_path(db_path, dogfood_root=args.dogfood_root)
    output_path = (
        default_dogfood_metrics_path()
        if args.output is None
        else default_dogfood_metrics_path(args.output)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"wrote {output_path}")
    return 0


def _cmd_research_bridge_dogfood_log_init(args: argparse.Namespace) -> int:
    result = write_dogfood_scaffold(
        args.root,
        overwrite_template=args.overwrite_template,
    )
    print(f"root: {result.root}")
    print(
        "template: "
        f"{result.template_path} "
        f"({'written' if result.template_written else 'kept'})"
    )
    print(
        "operator-log: "
        f"{result.operator_log_path} "
        f"({'written' if result.operator_log_written else 'kept'})"
    )
    print(
        "wave4-candidates: "
        f"{result.wave4_candidates_path} "
        f"({'written' if result.wave4_candidates_written else 'kept'})"
    )
    return 0


def _cmd_research_bridge_dogfood_log_validate(args: argparse.Namespace) -> int:
    result = validate_dogfood_log(args.root)
    print(f"operator-log: {result.operator_log_path}")
    print(f"planned projects: {len(result.planned_projects)}/5")
    print(f"filled project entries: {len(result.filled_project_entries)}/5")
    print(f"complete project entries: {len(result.complete_project_entries)}/5")
    print(f"project session ids: {len(result.project_entries)}/5")
    if result.ok:
        print("DOGFOOD_LOG_OK")
        return 0
    for missing in result.missing_requirements:
        print(f"missing: {missing}")
    return 1


def _cmd_research_bridge_wave4_validate(args: argparse.Namespace) -> int:
    result = validate_wave4_candidates(args.root)
    print(f"wave4-candidates: {result.wave4_candidates_path}")
    print(f"valid candidates: {len(result.candidates)}")
    if result.ok:
        print("WAVE4_CANDIDATES_OK")
        return 0
    for missing in result.missing_requirements:
        print(f"missing: {missing}")
    return 1


def _cmd_research_bridge_dogfood_log_reconcile(args: argparse.Namespace) -> int:
    db_path = ensure_research_bridge_initialized(args.db)
    con = connect_read(db_path)
    try:
        result = reconcile_dogfood_sessions(con, root=args.root)
    finally:
        con.close()

    print(f"operator-log: {result.operator_log_path}")
    print(f"reconciled sessions: {len(result.sessions)}/5")
    for row in result.sessions:
        print(
            f"- {row.project_name} [{row.session_id}]: "
            f"{row.blocks_pasted} block(s), {row.gap_runs} gap run(s), "
            f"{row.draft_exports} draft export(s), {row.prompt_signals} prompt signal(s)"
        )
    if result.ok:
        print("DOGFOOD_SESSIONS_OK")
        return 0
    for missing in result.missing_requirements:
        print(f"missing: {missing}")
    return 1


def _cmd_research_bridge_verdict_scaffold(args: argparse.Namespace) -> int:
    result = write_verdict_scaffold(args.path, overwrite=args.overwrite)
    print(f"verdict: {result.path} ({'written' if result.written else 'kept'})")
    return 0


def _cmd_research_bridge_verdict_validate(args: argparse.Namespace) -> int:
    result = validate_verdict_doc(args.path)
    print(f"verdict: {result.path}")
    print(f"Mode A: {result.mode_a_verdict or 'missing'}")
    print(f"Mode B: {result.mode_b_verdict or 'missing'}")
    print(f"next questions: {len(result.next_questions)}/3")
    if result.ok:
        print("DOGFOOD_VERDICT_OK")
        return 0
    for missing in result.missing_requirements:
        print(f"missing: {missing}")
    return 1


def _cmd_research_bridge_draft_export_record(args: argparse.Namespace) -> int:
    db_path = ensure_research_bridge_initialized(args.db)
    with connect_write(db_path, purpose="research_bridge_draft_export_cli") as con:
        export_id = record_draft_export(
            con,
            session_id=args.session_id,
            deliverable_id=args.deliverable_id,
            output_path=args.output_path,
        )
    print(f"recorded {export_id}")
    return 0


def _cmd_research_bridge_signals(args: argparse.Namespace) -> int:
    db_path = ensure_research_bridge_initialized(args.db)
    con = connect_read(db_path)
    try:
        would, total, pct = would_run_percentage(con, run_id=args.run_id)
    finally:
        con.close()

    scope = "all runs" if args.run_id is None else f"run {args.run_id}"
    print(f"{scope}: {pct * 100:.1f}% would-run ({would}/{total} latest prompt signals)")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="antiek")
    subparsers = parser.add_subparsers(dest="command")

    research = subparsers.add_parser("research", help="Research product commands.")
    research_subparsers = research.add_subparsers(dest="research_command")

    bridge = research_subparsers.add_parser(
        "bridge",
        help="Deep Research Bridge commands.",
    )
    bridge_subparsers = bridge.add_subparsers(dest="bridge_command")

    dogfood_report = bridge_subparsers.add_parser(
        "dogfood-report",
        help="Write the Deep Research Bridge dogfood metrics report.",
    )
    dogfood_report.add_argument(
        "--db",
        default=None,
        help="DuckDB path. Defaults to ANTIEK_DUCKDB_PATH / substrate default.",
    )
    dogfood_report.add_argument(
        "--output",
        default=None,
        help=(
            "Markdown output path. Defaults to "
            "~/Desktop/Antiek/runs/adrb/dogfood_metrics.md."
        ),
    )
    dogfood_report.add_argument(
        "--dogfood-root",
        default=None,
        help="Dogfood directory. Defaults to ~/Desktop/Antiek/runs/adrb.",
    )
    dogfood_report.set_defaults(func=_cmd_research_bridge_dogfood_report)

    dogfood_log = bridge_subparsers.add_parser(
        "dogfood-log",
        help="Create Deep Research Bridge dogfood log scaffolding.",
    )
    dogfood_log_subparsers = dogfood_log.add_subparsers(dest="dogfood_log_command")
    dogfood_log_init = dogfood_log_subparsers.add_parser(
        "init",
        help="Create dogfood log files.",
    )
    dogfood_log_init.add_argument(
        "--root",
        default=None,
        help="Dogfood directory. Defaults to ~/Desktop/Antiek/runs/adrb.",
    )
    dogfood_log_init.add_argument(
        "--overwrite-template",
        action="store_true",
        help="Rewrite _template.md. operator-log.md is never overwritten.",
    )
    dogfood_log_init.set_defaults(func=_cmd_research_bridge_dogfood_log_init)
    dogfood_log_validate = dogfood_log_subparsers.add_parser(
        "validate",
        help="Validate operator-owned dogfood log readiness.",
    )
    dogfood_log_validate.add_argument(
        "--root",
        default=None,
        help="Dogfood directory. Defaults to ~/Desktop/Antiek/runs/adrb.",
    )
    dogfood_log_validate.set_defaults(func=_cmd_research_bridge_dogfood_log_validate)
    dogfood_log_reconcile = dogfood_log_subparsers.add_parser(
        "reconcile",
        help="Reconcile operator dogfood sessions with bridge substrate rows.",
    )
    dogfood_log_reconcile.add_argument(
        "--root",
        default=None,
        help="Dogfood directory. Defaults to ~/Desktop/Antiek/runs/adrb.",
    )
    dogfood_log_reconcile.add_argument(
        "--db",
        default=None,
        help="DuckDB path. Defaults to ANTIEK_DUCKDB_PATH / substrate default.",
    )
    dogfood_log_reconcile.set_defaults(func=_cmd_research_bridge_dogfood_log_reconcile)
    wave4_validate = dogfood_log_subparsers.add_parser(
        "wave4-validate",
        help="Validate operator-owned Wave 4 candidate notes.",
    )
    wave4_validate.add_argument(
        "--root",
        default=None,
        help="Dogfood directory. Defaults to ~/Desktop/Antiek/runs/adrb.",
    )
    wave4_validate.set_defaults(func=_cmd_research_bridge_wave4_validate)

    verdict = bridge_subparsers.add_parser(
        "verdict",
        help="Scaffold or validate the Deep Research Bridge dogfood verdict.",
    )
    verdict_subparsers = verdict.add_subparsers(dest="verdict_command")
    verdict_scaffold = verdict_subparsers.add_parser(
        "scaffold",
        help="Create the post-dogfood verdict scaffold.",
    )
    verdict_scaffold.add_argument(
        "--path",
        default=None,
        help=(
            "Verdict path. Defaults to "
            "~/Desktop/Antiek/docs/adrb_post_dogfood_verdict.md."
        ),
    )
    verdict_scaffold.add_argument(
        "--overwrite",
        action="store_true",
        help="Rewrite the verdict scaffold if it already exists.",
    )
    verdict_scaffold.set_defaults(func=_cmd_research_bridge_verdict_scaffold)
    verdict_validate = verdict_subparsers.add_parser(
        "validate",
        help="Validate the post-dogfood verdict document.",
    )
    verdict_validate.add_argument(
        "--path",
        default=None,
        help=(
            "Verdict path. Defaults to "
            "~/Desktop/Antiek/docs/adrb_post_dogfood_verdict.md."
        ),
    )
    verdict_validate.set_defaults(func=_cmd_research_bridge_verdict_validate)

    draft_export = bridge_subparsers.add_parser(
        "draft-export",
        help="Record Mode A draft-export evidence.",
    )
    draft_export_subparsers = draft_export.add_subparsers(dest="draft_export_command")
    draft_export_record = draft_export_subparsers.add_parser(
        "record",
        help="Record one exported Mode A draft.",
    )
    draft_export_record.add_argument(
        "--db",
        default=None,
        help="DuckDB path. Defaults to ANTIEK_DUCKDB_PATH / substrate default.",
    )
    draft_export_record.add_argument("--session-id", required=True)
    draft_export_record.add_argument("--deliverable-id", required=True)
    draft_export_record.add_argument("--output-path", required=True)
    draft_export_record.set_defaults(func=_cmd_research_bridge_draft_export_record)

    signals = bridge_subparsers.add_parser(
        "signals",
        help="Print Mode B would-run percentage from prompt signals.",
    )
    signals.add_argument(
        "--db",
        default=None,
        help="DuckDB path. Defaults to ANTIEK_DUCKDB_PATH / substrate default.",
    )
    signals.add_argument(
        "--run-id",
        default=None,
        help="Optional gap run id. Defaults to all runs.",
    )
    signals.set_defaults(func=_cmd_research_bridge_signals)

    return parser


def _maybe_run_check_alias(args: list[str]) -> int | None:
    if not args:
        return None
    from tools.antiek_cli.__main__ import main as check_main
    from tools.antiek_cli.check import RUNNERS

    if args[0] == "check":
        return check_main(args)
    if args[0] in RUNNERS or args[0] == "all":
        return check_main(args)
    return None


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    check_rc = _maybe_run_check_alias(args)
    if check_rc is not None:
        return check_rc

    parser = _build_parser()
    parsed = parser.parse_args(args)
    func = getattr(parsed, "func", None)
    if func is None:
        parser.print_help()
        return 2
    return int(func(parsed))


if __name__ == "__main__":
    raise SystemExit(main())
