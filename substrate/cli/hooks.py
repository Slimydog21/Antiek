"""``antiek hooks`` CLI — list / inspect / disable / enable."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from substrate.hooks import HookRegistry, load_extensions


def _fresh_registry_and_loads(project_root: Path) -> tuple[HookRegistry, list]:
    from substrate.harness.apply import _declare_standard_seams

    reg = HookRegistry()
    _declare_standard_seams(reg)
    results = load_extensions(reg, project_root=project_root)
    return reg, results


def _cmd_list(args: argparse.Namespace) -> int:
    reg, results = _fresh_registry_and_loads(args.project_root)
    hooks = reg.list_hooks()
    if args.json:
        out = {
            "extensions": [
                {"extension_id": r.extension_id, "path": str(r.path),
                 "status": r.status, "error": r.error}
                for r in results
            ],
            "hooks": hooks,
            "seams": reg.seams(),
        }
        sys.stdout.write(json.dumps(out, indent=2, default=str) + "\n")
        return 0

    sys.stdout.write(f"extensions ({len(results)}):\n")
    for r in results:
        suffix = f" — {r.error}" if r.error else ""
        sys.stdout.write(f"  [{r.status}] {r.extension_id}{suffix}\n")
    sys.stdout.write(f"\nhooks registered ({len(hooks)}):\n")
    if not hooks:
        sys.stdout.write("  (none)\n")
    for h in sorted(hooks, key=lambda h: (h["seam_id"], h["priority"], h["seq"])):
        sys.stdout.write(
            f"  {h['seam_id']:<25} {h['stage']:<5} prio={h['priority']:<4} "
            f"{h['extension_id']}\n"
        )
    sys.stdout.write(f"\ndeclared seams ({len(reg.seams())}):\n")
    for sid, desc in sorted(reg.seams().items()):
        sys.stdout.write(f"  {sid}  — {desc}\n")
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    reg, results = _fresh_registry_and_loads(args.project_root)
    matches = [r for r in results if r.extension_id == args.extension_id]
    if not matches:
        sys.stderr.write(f"error: no extension with id {args.extension_id!r}\n")
        return 2
    r = matches[0]
    sys.stdout.write(f"extension: {r.extension_id}\n")
    sys.stdout.write(f"path:      {r.path}\n")
    sys.stdout.write(f"status:    {r.status}\n")
    if r.error:
        sys.stdout.write(f"error:     {r.error}\n")
    if r.status == "loaded":
        ext_hooks = [h for h in reg.list_hooks() if h["extension_id"] == r.extension_id]
        sys.stdout.write(f"\nhooks ({len(ext_hooks)}):\n")
        for h in ext_hooks:
            sys.stdout.write(f"  {h['seam_id']:<25} {h['stage']:<5} prio={h['priority']}\n")
    return 0


def _cmd_disable(args: argparse.Namespace) -> int:
    if ":" not in args.extension_id:
        sys.stderr.write(
            f"error: extension_id must look like 'project:<name>' or 'operator:<name>', "
            f"got {args.extension_id!r}\n"
        )
        return 2
    scope, name = args.extension_id.split(":", 1)
    if scope == "project":
        base = args.project_root / "antiek_extensions" / name
    elif scope == "operator":
        base = Path.home() / ".antiek" / "extensions" / name
    else:
        sys.stderr.write(f"error: unknown scope {scope!r}\n")
        return 2
    if not base.is_dir():
        sys.stderr.write(f"error: no extension directory at {base}\n")
        return 2
    marker = base / ".disabled"
    marker.touch()
    sys.stdout.write(
        f"disabled {args.extension_id} (marker at {marker}); "
        f"effective on next session start\n"
    )
    return 0


def _cmd_enable(args: argparse.Namespace) -> int:
    if ":" not in args.extension_id:
        sys.stderr.write(f"error: extension_id must be scope:name\n")
        return 2
    scope, name = args.extension_id.split(":", 1)
    base = (
        args.project_root / "antiek_extensions" / name
        if scope == "project"
        else Path.home() / ".antiek" / "extensions" / name
    )
    marker = base / ".disabled"
    if not marker.exists():
        sys.stdout.write(f"{args.extension_id} is not disabled (no marker)\n")
        return 0
    marker.unlink()
    sys.stdout.write(f"enabled {args.extension_id}; effective on next session start\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="antiek hooks")
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    sub = p.add_subparsers(dest="cmd", required=True)
    lst = sub.add_parser("list")
    lst.add_argument("--json", action="store_true")
    lst.set_defaults(func=_cmd_list)
    insp = sub.add_parser("inspect")
    insp.add_argument("extension_id")
    insp.set_defaults(func=_cmd_inspect)
    dis = sub.add_parser("disable")
    dis.add_argument("extension_id")
    dis.set_defaults(func=_cmd_disable)
    en = sub.add_parser("enable")
    en.add_argument("extension_id")
    en.set_defaults(func=_cmd_enable)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
