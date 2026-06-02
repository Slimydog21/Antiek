"""
``python -m tools.boundary_task`` — operator-facing CLI.

Subcommands:

- ``queue <description> --duration=<minutes>`` — push a task
- ``pop`` — claim the next queued task (move to 'running')
- ``status`` — markdown-friendly listing of every task
- ``cancel <id>`` — cancel a queued or running task
- ``done <id>`` — mark a running task done (typically the daemon's job)

Markdown output is the deliberate default for ``status`` — the operator
can pipe it into a note system or paste into a session. Set
``--json`` for machine-readable.

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e5-boundary-cli.html
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from tools.boundary_task import store


def _format_markdown(tasks: list[store.BoundaryTask]) -> str:
    if not tasks:
        return "_(no boundary tasks)_"
    lines = ["| id | status    | duration | description |",
             "|----|-----------|----------|-------------|"]
    for t in tasks:
        # Truncate long descriptions in the table so the row stays
        # one line; the JSON output preserves the full text.
        desc = t.description.replace("\n", " ").replace("|", "\\|")
        if len(desc) > 60:
            desc = desc[:57] + "..."
        lines.append(
            f"| {t.id} | {t.status:<9} | {t.duration_minutes}m | {desc} |"
        )
    return "\n".join(lines)


def cmd_queue(args: argparse.Namespace) -> int:
    description = " ".join(args.description).strip()
    if not description:
        print("queue: description must be non-empty", file=sys.stderr)
        return 1
    try:
        task = store.queue(description, args.duration)
    except ValueError as exc:
        print(f"queue: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(asdict(task), indent=2))
    else:
        print(f"queued task id={task.id}: {task.description}  ({task.duration_minutes}m)")
    return 0


def cmd_pop(args: argparse.Namespace) -> int:
    task = store.pop()
    if task is None:
        print("(queue is empty)")
        return 0
    if args.json:
        print(json.dumps(asdict(task), indent=2))
    else:
        print(f"popped task id={task.id}: {task.description}  ({task.duration_minutes}m)")
    return 0


def cmd_done(args: argparse.Namespace) -> int:
    try:
        task = store.mark_done(args.task_id)
    except (KeyError, ValueError) as exc:
        print(f"done: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(asdict(task), indent=2))
    else:
        print(f"marked task id={task.id} done at {task.completed_at}")
    return 0


def cmd_cancel(args: argparse.Namespace) -> int:
    try:
        task = store.cancel(args.task_id)
    except KeyError as exc:
        print(f"cancel: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(asdict(task), indent=2))
    else:
        print(f"cancelled task id={task.id}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    tasks = store.status()
    if args.json:
        print(json.dumps([asdict(t) for t in tasks], indent=2))
        return 0
    queued = sum(1 for t in tasks if t.status == "queued")
    running = sum(1 for t in tasks if t.status == "running")
    done = sum(1 for t in tasks if t.status == "done")
    cancelled = sum(1 for t in tasks if t.status == "cancelled")
    print(_format_markdown(tasks))
    print()
    print(
        f"_{queued} queued · {running} running · {done} done · {cancelled} cancelled_"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.boundary_task",
        description=(
            "Boundary-task queue. Queue a slow task at session start, "
            "let the §7 daemon (or a manual `pop`) execute it, pull "
            "progress via `status`. The operator pulls; nothing pushes."
        ),
    )
    p.add_argument("--json", action="store_true", help="emit JSON instead of human-friendly text")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_queue = sub.add_parser("queue", help="push a task")
    p_queue.add_argument("description", nargs="+", help="task description (rest of argv)")
    p_queue.add_argument(
        "--duration",
        type=int,
        required=True,
        help=f"estimated minutes ({store.MIN_DURATION_MINUTES}..{store.MAX_DURATION_MINUTES})",
    )
    p_queue.set_defaults(func=cmd_queue)

    p_pop = sub.add_parser("pop", help="claim the next queued task")
    p_pop.set_defaults(func=cmd_pop)

    p_done = sub.add_parser("done", help="mark a running task done")
    p_done.add_argument("task_id", type=int)
    p_done.set_defaults(func=cmd_done)

    p_cancel = sub.add_parser("cancel", help="cancel a task")
    p_cancel.add_argument("task_id", type=int)
    p_cancel.set_defaults(func=cmd_cancel)

    p_status = sub.add_parser("status", help="list all tasks")
    p_status.set_defaults(func=cmd_status)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
