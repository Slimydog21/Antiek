"""``antiek branch`` CLI."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

from substrate.conversation.branch import create_branch, list_branches
from substrate.conversation.checkpoint import create_checkpoint, list_checkpoints


def _active_session_file(project_root: Path) -> Path:
    return project_root / ".antiek" / "active_session_id"


def _read_active(project_root: Path) -> str | None:
    f = _active_session_file(project_root)
    return f.read_text().strip() if f.exists() else None


def _write_active(project_root: Path, session_id: str) -> None:
    f = _active_session_file(project_root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(session_id)


def _conversation_dir(project_root: Path) -> Path:
    return project_root / ".antiek" / "conversation"


def _cmd_list(args: argparse.Namespace) -> int:
    branches = list_branches(args.project_root)
    if args.json:
        sys.stdout.write(json.dumps([asdict(b) for b in branches], indent=2) + "\n")
        return 0
    if not branches:
        sys.stdout.write("(no branches)\n")
        return 0
    by_parent: dict[str, list] = {}
    for b in branches:
        by_parent.setdefault(b.parent_session_id, []).append(b)
    children_ids = {b.child_session_id for b in branches}
    roots = sorted({b.parent_session_id for b in branches if b.parent_session_id not in children_ids})

    def _print(parent: str, depth: int) -> None:
        for b in sorted(by_parent.get(parent, []), key=lambda x: x.created_at):
            indent = "  " * depth
            sys.stdout.write(
                f"{indent}- {b.child_session_id}  name={b.name!r}  "
                f"from {b.parent_session_id}@pos{b.branch_position}  ({b.created_at})\n"
            )
            _print(b.child_session_id, depth + 1)

    active = _read_active(args.project_root)
    for r in roots:
        marker = " (active)" if r == active else ""
        sys.stdout.write(f"{r}{marker}\n")
        _print(r, 1)
    return 0


def _cmd_from(args: argparse.Namespace) -> int:
    sess, pos_str = args.source.split(":", 1)
    pos = int(pos_str)
    existing = [c for c in list_checkpoints(sess, args.project_root) if c.position == pos]
    cp = existing[0] if existing else create_checkpoint(sess, args.project_root, pos, label=f"auto-{args.name}")
    child = create_branch(sess, cp, args.name, args.project_root)
    sys.stdout.write(f"created branch {child} from {sess}:{pos} (hash {cp.hash[:12]}…)\n")
    return 0


def _cmd_switch(args: argparse.Namespace) -> int:
    target_dir = _conversation_dir(args.project_root) / args.session_id
    if not target_dir.is_dir():
        sys.stderr.write(f"error: no session dir at {target_dir}\n")
        return 2
    _write_active(args.project_root, args.session_id)
    sys.stdout.write(f"active session: {args.session_id}\n")
    return 0


def _cmd_delete(args: argparse.Namespace) -> int:
    target_dir = _conversation_dir(args.project_root) / args.session_id
    if not target_dir.is_dir():
        sys.stderr.write(f"error: no session dir at {target_dir}\n")
        return 2
    if args.cascade:
        branches = list_branches(args.project_root)
        descendants: set[str] = set()

        def _collect(parent: str) -> None:
            for b in branches:
                if b.parent_session_id == parent:
                    descendants.add(b.child_session_id)
                    _collect(b.child_session_id)

        _collect(args.session_id)
        for d in descendants:
            d_dir = _conversation_dir(args.project_root) / d
            if d_dir.is_dir():
                shutil.rmtree(d_dir)
        shutil.rmtree(target_dir)
        sys.stdout.write(f"deleted {args.session_id} and {len(descendants)} descendant(s)\n")
    else:
        shutil.rmtree(target_dir)
        sys.stdout.write(f"deleted {args.session_id}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="antiek branch", description="Conversation branches")
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    sub = p.add_subparsers(dest="cmd", required=True)
    lst = sub.add_parser("list")
    lst.add_argument("--json", action="store_true")
    lst.set_defaults(func=_cmd_list)
    frm = sub.add_parser("from")
    frm.add_argument("source")
    frm.add_argument("--name", required=True)
    frm.set_defaults(func=_cmd_from)
    sw = sub.add_parser("switch")
    sw.add_argument("session_id")
    sw.set_defaults(func=_cmd_switch)
    dl = sub.add_parser("delete")
    dl.add_argument("session_id")
    dl.add_argument("--cascade", action="store_true")
    dl.set_defaults(func=_cmd_delete)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
