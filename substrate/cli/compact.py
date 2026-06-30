"""``antiek compact`` CLI — operator-driven compaction."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from substrate.conversation.compaction import (
    ContextPressureNeedsOperator,
    ContextPressureTooHigh,
    should_compact,
)
from substrate.conversation.compaction import (
    compact as compact_fn,
)
from substrate.conversation.event_log import EventLog
from substrate.conversation.policy import CompactionConfig, CompactionPolicy
from substrate.conversation.token_counter import declare_token_count_seam
from substrate.hooks import HookRegistry, load_extensions


def _resolve_session_id(project_root: Path, override: str | None) -> str | None:
    if override:
        return override
    marker = project_root / ".antiek" / "active_session_id"
    if marker.exists():
        return marker.read_text().strip()
    return None


def _build_registry_for_compaction(project_root: Path) -> HookRegistry:
    reg = HookRegistry()
    declare_token_count_seam(reg)
    load_extensions(reg, project_root=project_root)
    return reg


def _make_subprocess_summarizer(cmd: str) -> Any:
    def _summarize(messages: list[dict[str, Any]], model: str) -> str:
        payload = json.dumps({"messages": messages, "model": model})
        proc = subprocess.run(
            shutil.which(cmd.split()[0]) or cmd.split()[0],
            input=payload, text=True, capture_output=True, timeout=120,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"summarizer command {cmd!r} exited {proc.returncode}: {proc.stderr[:500]}"
            )
        return proc.stdout
    return _summarize


def _stub_summarizer(messages: list[dict[str, Any]], model: str) -> str:
    return (
        f"[stub-summary: {len(messages)} messages elided; "
        f"model={model}; pass --summarizer-cmd to use a real summarizer]"
    )


def _cmd_status(args: argparse.Namespace) -> int:
    session_id = _resolve_session_id(args.project_root, args.session)
    if session_id is None:
        sys.stderr.write(
            "error: no active session (no --session given and no "
            ".antiek/active_session_id marker). Try `antiek branch switch <id>` first.\n"
        )
        return 2

    reg = _build_registry_for_compaction(args.project_root)
    log = EventLog(session_id, args.project_root, fsync_on_append=False)
    config = CompactionConfig.for_project(args.project_root)
    trigger, current, threshold = should_compact(
        registry=reg, log=log, config=config,
        model=args.model, context_window=args.context_window, project_id=None,
    )
    payload = {
        "session": session_id,
        "events": log.position(),
        "current_tokens": current,
        "threshold_tokens": threshold,
        "threshold_pct": config.threshold_pct,
        "policy": config.policy.value,
        "would_trigger": trigger,
        "model": args.model,
        "context_window": args.context_window,
    }
    if args.json:
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        for k, v in payload.items():
            sys.stdout.write(f"  {k:<18} {v}\n")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    session_id = _resolve_session_id(args.project_root, args.session)
    if session_id is None:
        sys.stderr.write("error: no active session\n")
        return 2

    reg = _build_registry_for_compaction(args.project_root)
    config = CompactionConfig.for_project(args.project_root)
    if args.policy:
        config = CompactionConfig(
            policy=CompactionPolicy(args.policy),
            threshold_pct=config.threshold_pct,
            keep_first_n=config.keep_first_n,
            keep_last_n=config.keep_last_n,
            summary_model=config.summary_model,
        )

    summarizer = (
        _make_subprocess_summarizer(args.summarizer_cmd)
        if args.summarizer_cmd
        else _stub_summarizer
    )

    try:
        result = compact_fn(
            session_id=session_id, project_root=args.project_root,
            registry=reg, config=config,
            model=args.model, context_window=args.context_window,
            summarizer=summarizer,
        )
    except ContextPressureTooHigh as exc:
        sys.stderr.write(f"STRICT raised: {exc}\n")
        return 3
    except ContextPressureNeedsOperator as exc:
        sys.stderr.write(f"INTERACTIVE: {exc}\n")
        return 4

    if args.json:
        sys.stdout.write(
            json.dumps(
                {
                    "session": result.session_id,
                    "pre_compaction_branch": result.pre_compaction_branch,
                    "pre_tokens": result.pre_tokens,
                    "post_tokens": result.post_tokens,
                    "n_summarized": result.n_summarized,
                    "position_at_compaction": result.position_at_compaction,
                    "summary_marker_position": result.summary_marker_position,
                },
                indent=2,
            ) + "\n"
        )
    else:
        sys.stdout.write(
            f"compacted session {result.session_id}:\n"
            f"  branch: {result.pre_compaction_branch}\n"
            f"  pre  -> post tokens: {result.pre_tokens} -> {result.post_tokens}\n"
            f"  messages summarized: {result.n_summarized}\n"
            f"  marker position:     {result.summary_marker_position}\n"
        )
        if result.pre_compaction_branch:
            sys.stdout.write(
                f"\nrecovery: `antiek branch switch {result.pre_compaction_branch}`\n"
            )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="antiek compact")
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    p.add_argument("--session", help="Override active session id")
    p.add_argument("--model", default="claude-opus-4-7")
    p.add_argument("--context-window", type=int, default=1_000_000)
    sub = p.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=_cmd_status)
    rn = sub.add_parser("run")
    rn.add_argument("--policy", choices=["strict", "lossy", "interactive"])
    rn.add_argument("--summarizer-cmd")
    rn.add_argument("--json", action="store_true")
    rn.set_defaults(func=_cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
