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
from substrate.research_bridge.dogfood_log import write_dogfood_scaffold
from substrate.research_bridge.dogfood_report import (
    build_report_from_db_path,
    default_dogfood_metrics_path,
)
from substrate.research_bridge.draft_export import record_draft_export
from substrate.research_bridge.gap import would_run_percentage


def _cmd_research_bridge_dogfood_report(args: argparse.Namespace) -> int:
    db_path = ensure_research_bridge_initialized(args.db)
    report = build_report_from_db_path(db_path)
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
    return 0


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
