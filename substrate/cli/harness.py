"""``antiek harness`` CLI — fork / apply / diff / status."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from substrate.harness.apply import apply_harness
from substrate.harness.fork import ForkAlreadyExists, create_fork, list_forks
from substrate.harness_diff import diff_snapshots, load_snapshot
from substrate.harness_diff.snapshot import list_snapshots


def _cmd_fork(args: argparse.Namespace) -> int:
    try:
        fork = create_fork(args.name, args.project_root)
    except ForkAlreadyExists as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    sys.stdout.write(
        f"created harness fork {fork.name} at {fork.path}\n"
        f"  extension.py: {fork.has_extension}\n"
        f"  config.toml:  {fork.has_config}\n"
        f"\n"
        f"next steps:\n"
        f"  - edit {fork.path}/extension.py to register hooks\n"
        f"  - tune {fork.path}/config.toml for compaction/queue policies\n"
        f"  - apply: antiek harness apply --fork {fork.name}\n"
    )
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    try:
        result = apply_harness(
            project_root=args.project_root,
            fork_name=args.fork,
            capture_tag=args.capture,
        )
    except FileNotFoundError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    if args.json:
        out = {
            "extensions": [asdict(r) for r in result.extension_results],
            "compaction_policy": result.compaction_config.policy.value,
            "queue_names": list(result.queue_names),
            "import_map_size": len(result.import_map.get("imports", {})),
            "snapshot_path": str(result.snapshot_path) if result.snapshot_path else None,
            "snapshot_tag": result.snapshot.tag,
        }
        for ext in out["extensions"]:
            ext["path"] = str(ext["path"])
        sys.stdout.write(json.dumps(out, indent=2, default=str) + "\n")
        return 0

    sys.stdout.write(f"applied harness ({len(result.extension_results)} extension(s))\n")
    for r in result.extension_results:
        sys.stdout.write(f"  [{r.status}] {r.extension_id}\n")
        if r.error:
            sys.stdout.write(f"      error: {r.error}\n")
    sys.stdout.write(f"compaction policy: {result.compaction_config.policy.value}\n")
    sys.stdout.write(f"queues registered: {len(result.queue_names)}\n")
    sys.stdout.write(f"adapters discovered: {len(result.import_map.get('imports', {}))}\n")
    if result.snapshot_path:
        sys.stdout.write(f"snapshot saved to: {result.snapshot_path}\n")
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    try:
        a = load_snapshot(args.a, args.project_root)
        b = load_snapshot(args.b, args.project_root)
    except FileNotFoundError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    d = diff_snapshots(a, b)
    if args.json:
        sys.stdout.write(json.dumps(asdict(d), indent=2, default=str) + "\n")
        return 0

    if d.is_empty():
        sys.stdout.write(f"no changes between {args.a} and {args.b}\n")
        return 0

    sys.stdout.write(f"diff {args.a} -> {args.b}:\n\n")
    if d.substrate_version_changed:
        old, new = d.substrate_version_changed
        sys.stdout.write(f"substrate version: {old} -> {new}\n\n")
    if d.seams_added:
        sys.stdout.write("seams added:\n")
        for s in d.seams_added:
            sys.stdout.write(f"  + {s}\n")
        sys.stdout.write("\n")
    if d.seams_removed:
        sys.stdout.write("seams removed:\n")
        for s in d.seams_removed:
            sys.stdout.write(f"  - {s}\n")
        sys.stdout.write("\n")
    if d.hooks_added:
        sys.stdout.write("hooks added:\n")
        for h in d.hooks_added:
            sys.stdout.write(
                f"  + {h['extension_id']} @ {h['seam_id']} ({h.get('stage', '?')}, prio={h.get('priority', '?')})\n"
            )
        sys.stdout.write("\n")
    if d.hooks_removed:
        sys.stdout.write("hooks removed:\n")
        for h in d.hooks_removed:
            sys.stdout.write(f"  - {h['extension_id']} @ {h['seam_id']}\n")
        sys.stdout.write("\n")
    if d.model_config_changes:
        sys.stdout.write("model_config changes:\n")
        for k, (av, bv) in d.model_config_changes.items():
            sys.stdout.write(f"  {k}: {av!r} -> {bv!r}\n")
        sys.stdout.write("\n")
    if d.tools_added or d.tools_removed or d.tools_changed:
        sys.stdout.write("tools:\n")
        for t in d.tools_added:
            sys.stdout.write(f"  + {t}\n")
        for t in d.tools_removed:
            sys.stdout.write(f"  - {t}\n")
        for name, old, new in d.tools_changed:
            sys.stdout.write(f"  ~ {name}: {old!r} -> {new!r}\n")
        sys.stdout.write("\n")
    if d.system_prompt_changed:
        sys.stdout.write("system_prompt: digest changed\n")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    forks = list_forks(args.project_root)
    snaps = list_snapshots(args.project_root)
    if args.json:
        sys.stdout.write(
            json.dumps(
                {
                    "forks": [
                        {
                            "name": f.name, "path": str(f.path),
                            "has_extension": f.has_extension, "has_config": f.has_config,
                        }
                        for f in forks
                    ],
                    "snapshots": [
                        {"tag": s.tag, "captured_at": s.captured_at, "version": s.substrate_version}
                        for s in snaps
                    ],
                },
                indent=2,
            )
            + "\n"
        )
        return 0

    sys.stdout.write(f"forks ({len(forks)}):\n")
    for f in forks:
        flags = []
        if not f.has_extension:
            flags.append("no extension.py")
        if not f.has_config:
            flags.append("no config.toml")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        sys.stdout.write(f"  - {f.name}{flag_str}\n")
    sys.stdout.write(f"\nsnapshots ({len(snaps)}):\n")
    for s in snaps:
        sys.stdout.write(f"  - {s.tag}  (v{s.substrate_version})  {s.captured_at}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="antiek harness", description="Per-project harness operations")
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fork", help="Scaffold a new harness fork")
    f.add_argument("name")
    f.set_defaults(func=_cmd_fork)

    a = sub.add_parser("apply", help="Load fork(s) and capture a HarnessSnapshot")
    a.add_argument("--fork", help="Only apply this fork (default: all)")
    a.add_argument("--capture", help="Save snapshot under this tag")
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=_cmd_apply)

    d = sub.add_parser("diff", help="Diff two captured snapshots")
    d.add_argument("a")
    d.add_argument("b")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=_cmd_diff)

    s = sub.add_parser("status", help="List forks + snapshots")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=_cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
