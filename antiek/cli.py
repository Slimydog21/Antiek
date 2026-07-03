"""Top-level Antiek CLI.

The historical ``tools.antiek_cli`` module remains the implementation of
``antiek check``. This package owns product-facing commands exposed through the
``antiek`` console script declared in pyproject.toml.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from runtime.db_lock import connect_read, connect_write
from substrate.coordination.activation_view import (
    ReadActivationNextSession,
    ReadActivationView,
    build_read_activation_view,
    default_read_dogfood_log_path,
    recommend_read_activation_next_session,
)
from substrate.research_bridge.db_path import ensure_research_bridge_initialized
from substrate.research_bridge.dogfood_log import (
    DOGFOOD_PROJECT_COUNT,
    validate_dogfood_log,
    validate_wave4_candidates,
    write_dogfood_scaffold,
)
from substrate.research_bridge.dogfood_readiness import (
    audit_dogfood_readiness,
    render_readiness_json,
    render_readiness_summary,
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
from tools.activation.read_dogfood import (
    SESSION_TEMPLATE_KINDS,
    append_session_template,
    build_session_record,
    session_template,
)

READ_ACTIVATION_STATUS_JSON_SCHEMA_VERSION = 1
READ_ACTIVATION_APPEND_TEMPLATE_JSON_SCHEMA_VERSION = 1
READ_ACTIVATION_NEXT_SESSION_JSON_SCHEMA_VERSION = 1
READ_ACTIVATION_RECORD_SESSION_JSON_SCHEMA_VERSION = 1


def _read_activation_log_path(raw_path: str | None) -> Path:
    return Path(raw_path) if raw_path is not None else default_read_dogfood_log_path()


def _read_activation_status_payload(view: ReadActivationView) -> dict[str, object]:
    return {
        "schema_version": READ_ACTIVATION_STATUS_JSON_SCHEMA_VERSION,
        "view": asdict(view),
    }


def _render_read_activation_status_json(view: ReadActivationView) -> str:
    return json.dumps(_read_activation_status_payload(view), indent=2, sort_keys=True) + "\n"


def _cmd_read_activation_status(args: argparse.Namespace) -> int:
    view = build_read_activation_view(_read_activation_log_path(args.log))
    if args.json:
        sys.stdout.write(_render_read_activation_status_json(view))
    else:
        print(f"source: {view.source_path}")
        print(f"state: {view.state}")
        print(f"closure_ready: {str(view.closure_ready).lower()}")
        print(
            "valid sessions: "
            f"{view.valid_sessions}/{view.required_counts['valid_sessions']} "
            f"({view.total_sessions} total, {view.invalid_session_count} invalid)"
        )
        print(
            "live provider sessions: "
            f"{view.live_provider_sessions}/"
            f"{view.required_counts['live_provider_sessions']}"
        )
        print(
            "citation trace sessions: "
            f"{view.citation_trace_sessions}/"
            f"{view.required_counts['citation_trace_sessions']}"
        )
        print(
            "non-library sessions: "
            f"{view.non_library_sessions}/"
            f"{view.required_counts['non_library_sessions']}"
        )
        print(f"final verdict: {view.final_verdict or 'missing'}")
        for key, remaining in view.remaining_requirements.items():
            print(f"remaining: {key}={remaining}")
        for failure in view.failures:
            print(f"failure: {failure}")
    return 0 if view.closure_ready else 1


def _read_activation_next_session_payload(
    view: ReadActivationView,
    recommendation: ReadActivationNextSession,
) -> dict[str, object]:
    return {
        "schema_version": READ_ACTIVATION_NEXT_SESSION_JSON_SCHEMA_VERSION,
        "source_path": recommendation.source_path,
        "state": recommendation.state,
        "next_action": recommendation.next_action,
        "recommended_template": recommendation.recommended_template,
        "append_command": recommendation.append_command,
        "rationale": recommendation.rationale,
        "remaining_requirements": dict(recommendation.remaining_requirements),
        "view": asdict(view),
    }


def _cmd_read_activation_next_session(args: argparse.Namespace) -> int:
    view = build_read_activation_view(_read_activation_log_path(args.log))
    recommendation = recommend_read_activation_next_session(view)
    payload = _read_activation_next_session_payload(view, recommendation)
    if args.json:
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        print(f"source: {payload['source_path']}")
        print(f"state: {payload['state']}")
        print(f"next action: {payload['next_action']}")
        print(f"recommended template: {payload['recommended_template'] or 'none'}")
        if payload["append_command"] is not None:
            print(f"append command: {payload['append_command']}")
        print(f"rationale: {payload['rationale']}")
        for key, remaining in payload["remaining_requirements"].items():
            print(f"remaining: {key}={remaining}")
    return 1 if view.state == "invalid_log" else 0


def _read_activation_append_template_payload(
    *,
    kind: str,
    log_path: Path,
    view: ReadActivationView,
) -> dict[str, object]:
    return {
        "schema_version": READ_ACTIVATION_APPEND_TEMPLATE_JSON_SCHEMA_VERSION,
        "appended_template": kind,
        "log_path": str(log_path),
        "view": asdict(view),
    }


def _cmd_read_activation_append_template(args: argparse.Namespace) -> int:
    log_path = _read_activation_log_path(args.log)
    record = session_template(args.kind)
    append_session_template(log_path, record)
    view = build_read_activation_view(log_path)
    if args.json:
        payload = _read_activation_append_template_payload(
            kind=args.kind,
            log_path=log_path,
            view=view,
        )
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        print(f"appended template: {args.kind}")
        print(f"log: {log_path}")
        print(f"state: {view.state}")
        print(
            "valid sessions: "
            f"{view.valid_sessions}/{view.required_counts['valid_sessions']} "
            f"({view.total_sessions} total, {view.invalid_session_count} invalid)"
        )
        for failure in view.failures:
            print(f"failure: {failure}")
    return 0


def _read_activation_record_session_payload(
    *,
    session_id: str,
    log_path: Path,
    view: ReadActivationView,
) -> dict[str, object]:
    return {
        "schema_version": READ_ACTIVATION_RECORD_SESSION_JSON_SCHEMA_VERSION,
        "recorded_session_id": session_id,
        "log_path": str(log_path),
        "view": asdict(view),
    }


def _cmd_read_activation_record_session(args: argparse.Namespace) -> int:
    log_path = _read_activation_log_path(args.log)
    try:
        record = build_session_record(
            session_id=args.session_id,
            date=args.date,
            build_sha=args.build_sha,
            url=args.url,
            operator=args.operator,
            document_id=args.document_id,
            entry_door=args.entry_door,
            provider_status=args.provider_status,
            minutes_reading=args.minutes_reading,
            visible_content_note=args.visible_content_note,
            selected_text=args.selected_text,
            return_context_note=args.return_context_note,
            operator_note=args.operator_note,
            live_provider_ai=args.live_provider_ai,
            citation_traced=args.citation_traced,
            first_answer=args.first_answer,
            investigation_id=args.investigation_id,
            dialogue_no_key_copy=args.dialogue_no_key_copy or args.no_key_copy,
            research_no_key_copy=args.research_no_key_copy or args.no_key_copy,
            source_document_id=args.source_document_id,
            chunk_id=args.chunk_id,
            anchor=args.anchor,
            result_url=args.result_url,
            verdict=args.verdict,
            blocking_issue_ids=args.blocking_issue_id,
        )
    except ValueError as exc:
        print(f"record-session: {exc}", file=sys.stderr)
        return 2

    append_session_template(log_path, record)
    view = build_read_activation_view(log_path)
    if args.json:
        payload = _read_activation_record_session_payload(
            session_id=record["session_id"],
            log_path=log_path,
            view=view,
        )
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        print(f"recorded session: {record['session_id']}")
        print(f"log: {log_path}")
        print(f"state: {view.state}")
        print(
            "valid sessions: "
            f"{view.valid_sessions}/{view.required_counts['valid_sessions']} "
            f"({view.total_sessions} total, {view.invalid_session_count} invalid)"
        )
        for failure in view.failures:
            print(f"failure: {failure}")
    return 0


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


def _cmd_research_bridge_readiness(args: argparse.Namespace) -> int:
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
    print(f"planned projects: {len(result.planned_projects)}/{DOGFOOD_PROJECT_COUNT}")
    print(
        "filled project entries: "
        f"{len(result.filled_project_entries)}/{DOGFOOD_PROJECT_COUNT}"
    )
    print(
        "complete project entries: "
        f"{len(result.complete_project_entries)}/{DOGFOOD_PROJECT_COUNT}"
    )
    print(f"project session ids: {len(result.project_entries)}/{DOGFOOD_PROJECT_COUNT}")
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
    print(f"reconciled sessions: {len(result.sessions)}/{DOGFOOD_PROJECT_COUNT}")
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

    read = subparsers.add_parser("read", help="Read product commands.")
    read_subparsers = read.add_subparsers(dest="read_command")
    activation = read_subparsers.add_parser(
        "activation",
        help="Read activation gate commands.",
    )
    activation_subparsers = activation.add_subparsers(dest="activation_command")
    activation_status = activation_subparsers.add_parser(
        "status",
        help="Check Read activation dogfood evidence status.",
    )
    activation_status.add_argument(
        "--log",
        default=None,
        help=(
            "Read dogfood JSONL log. Defaults to "
            "reports/read-dogfood.jsonl in the repository."
        ),
    )
    activation_status.add_argument(
        "--json",
        action="store_true",
        help="Write a stable machine-readable activation status payload.",
    )
    activation_status.set_defaults(func=_cmd_read_activation_status)
    activation_next_session = activation_subparsers.add_parser(
        "next-session",
        help="Recommend the next Read activation dogfood session kind.",
    )
    activation_next_session.add_argument(
        "--log",
        default=None,
        help=(
            "Read dogfood JSONL log. Defaults to "
            "reports/read-dogfood.jsonl in the repository."
        ),
    )
    activation_next_session.add_argument(
        "--json",
        action="store_true",
        help="Write a stable machine-readable recommendation payload.",
    )
    activation_next_session.set_defaults(func=_cmd_read_activation_next_session)
    activation_append_template = activation_subparsers.add_parser(
        "append-template",
        help="Append a Read activation dogfood scaffold session.",
    )
    activation_append_template.add_argument(
        "--kind",
        required=True,
        choices=SESSION_TEMPLATE_KINDS,
        help="Template kind to append.",
    )
    activation_append_template.add_argument(
        "--log",
        default=None,
        help=(
            "Read dogfood JSONL log. Defaults to "
            "reports/read-dogfood.jsonl in the repository."
        ),
    )
    activation_append_template.add_argument(
        "--json",
        action="store_true",
        help="Write a stable machine-readable append result payload.",
    )
    activation_append_template.set_defaults(func=_cmd_read_activation_append_template)
    activation_record_session = activation_subparsers.add_parser(
        "record-session",
        help="Append a structured Read activation dogfood evidence session.",
    )
    activation_record_session.add_argument(
        "--log",
        default=None,
        help=(
            "Read dogfood JSONL log. Defaults to "
            "reports/read-dogfood.jsonl in the repository."
        ),
    )
    activation_record_session.add_argument("--session-id", required=True)
    activation_record_session.add_argument("--date", required=True)
    activation_record_session.add_argument("--build-sha", required=True)
    activation_record_session.add_argument("--url", required=True)
    activation_record_session.add_argument("--operator", required=True)
    activation_record_session.add_argument("--document-id", required=True)
    activation_record_session.add_argument("--entry-door", required=True)
    activation_record_session.add_argument("--provider-status", default=None)
    activation_record_session.add_argument(
        "--minutes-reading",
        type=int,
        required=True,
    )
    activation_record_session.add_argument("--visible-content-note", required=True)
    activation_record_session.add_argument("--selected-text", required=True)
    activation_record_session.add_argument("--return-context-note", required=True)
    activation_record_session.add_argument("--operator-note", required=True)
    activation_record_session.add_argument(
        "--live-provider-ai",
        action="store_true",
        help=(
            "Mark steps 3 and 4 as live provider-backed passes. Requires "
            "--first-answer and --investigation-id."
        ),
    )
    activation_record_session.add_argument(
        "--first-answer",
        default=None,
        help="First live provider answer for golden-path step 3.",
    )
    activation_record_session.add_argument(
        "--investigation-id",
        default=None,
        help="Child research investigation/session id for golden-path step 4.",
    )
    activation_record_session.add_argument(
        "--no-key-copy",
        default=None,
        help=(
            "Boundary copy to use for both inert Dialogue and Research steps "
            "when --live-provider-ai is absent."
        ),
    )
    activation_record_session.add_argument(
        "--dialogue-no-key-copy",
        default=None,
        help="Exact inert Dialogue boundary copy for step 3.",
    )
    activation_record_session.add_argument(
        "--research-no-key-copy",
        default=None,
        help="Exact inert Research boundary copy for step 4.",
    )
    activation_record_session.add_argument(
        "--citation-traced",
        action="store_true",
        help=(
            "Record citation/source tracing evidence. Requires "
            "--source-document-id, --result-url, and --chunk-id or --anchor."
        ),
    )
    activation_record_session.add_argument("--source-document-id", default=None)
    activation_record_session.add_argument("--chunk-id", default=None)
    activation_record_session.add_argument("--anchor", default=None)
    activation_record_session.add_argument("--result-url", default=None)
    activation_record_session.add_argument(
        "--verdict",
        choices=("ACTIVATE", "REPAIR", "ROLL BACK CLAIM"),
        default=None,
        help="Optional final operator verdict for the last evidence record.",
    )
    activation_record_session.add_argument(
        "--blocking-issue-id",
        action="append",
        default=None,
        help="Blocking issue id for a REPAIR verdict; repeat for multiple ids.",
    )
    activation_record_session.add_argument(
        "--json",
        action="store_true",
        help="Write a stable machine-readable record result payload.",
    )
    activation_record_session.set_defaults(func=_cmd_read_activation_record_session)

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

    readiness = bridge_subparsers.add_parser(
        "readiness",
        help="Check whether dogfood evidence is ready for verdict closure.",
    )
    readiness.add_argument(
        "--db",
        default=None,
        help="DuckDB path. Defaults to ANTIEK_DUCKDB_PATH / substrate default.",
    )
    readiness.add_argument(
        "--dogfood-root",
        default=None,
        help="Dogfood directory. Defaults to ~/Desktop/Antiek/runs/adrb.",
    )
    readiness.add_argument(
        "--metrics-path",
        default=None,
        help="Metrics report path. Defaults to <dogfood-root>/dogfood_metrics.md.",
    )
    readiness.add_argument(
        "--verdict-path",
        default=None,
        help=(
            "Verdict path. Defaults to "
            "~/Desktop/Antiek/docs/adrb_post_dogfood_verdict.md."
        ),
    )
    readiness.add_argument(
        "--json",
        action="store_true",
        help="Write a stable machine-readable readiness payload.",
    )
    readiness.set_defaults(func=_cmd_research_bridge_readiness)

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
