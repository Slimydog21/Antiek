"""Unified ``antiek`` CLI entrypoint."""

from __future__ import annotations

import sys
from collections.abc import Callable


def _import_subcommand(name: str) -> Callable[[list[str] | None], int]:
    if name == "burn":
        from substrate.observability.burn_cli import main
    elif name == "branch":
        from substrate.conversation.cli import main
    elif name == "hooks":
        from substrate.cli.hooks import main
    elif name == "harness":
        from substrate.cli.harness import main
    elif name == "compact":
        from substrate.cli.compact import main
    elif name == "queue":
        from substrate.cli.queue import main
    elif name == "lint":
        import importlib.util
        from pathlib import Path

        script = (
            Path(__file__).resolve().parents[2]
            / "scripts" / "lint_context_injection.py"
        )
        spec = importlib.util.spec_from_file_location("antiek_lint", script)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        main = module.main
    else:
        raise ValueError(f"unknown subcommand {name!r}")
    return main


SUBCOMMANDS = ("burn", "branch", "hooks", "harness", "compact", "queue", "lint")


_DESCRIPTIONS = {
    "burn": "Per-call burn telemetry",
    "branch": "Conversation checkpoint + branch",
    "hooks": "Inspect / manage substrate hooks",
    "harness": "Per-project harness fork / apply / diff / status",
    "compact": "Manual compaction",
    "queue": "Bounded-queue inspection",
    "lint": "Context-injection static analysis",
}


def _load_failure(name: str) -> str | None:
    """Why ``name`` cannot run, or None when it can.

    This exists because the help text used to list all seven verbs as available
    while every one of them failed at import: six raised ModuleNotFoundError for
    modules that ship with an unmerged branch, and ``lint`` pointed at a script
    that is not in the tree. A help screen that cannot be true is the same defect
    as a gate that cannot fail -- detection that never reaches a decision, on the
    user's side of the boundary. So the list is probed, not asserted.
    """
    try:
        _import_subcommand(name)
    except (ImportError, FileNotFoundError, OSError) as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def _print_usage() -> None:
    lines = ["usage: antiek <subcommand> [args...]", "", "Subcommands:"]
    unavailable = 0
    for name in SUBCOMMANDS:
        description = _DESCRIPTIONS.get(name, "")
        failure = _load_failure(name)
        if failure is None:
            lines.append(f"  {name:<9} {description}")
        else:
            unavailable += 1
            lines.append(f"  {name:<9} {description}")
            lines.append(f"  {'':<9} UNAVAILABLE -- {failure}")
    if unavailable:
        lines += [
            "",
            f"{unavailable} of {len(SUBCOMMANDS)} subcommands cannot load on this "
            "installation. Their modules ship with a branch that is not merged here; "
            "see docs/engineering_deferrals.md.",
        ]
    lines += ["", "Run `antiek <subcommand> --help` for subcommand-specific flags.", ""]
    sys.stdout.write("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] in ("-h", "--help"):
        _print_usage()
        return 0
    sub = args[0]
    if sub not in SUBCOMMANDS:
        sys.stderr.write(f"error: unknown subcommand {sub!r}\n")
        _print_usage()
        return 2
    failure = _load_failure(sub)
    if failure is not None:
        sys.stderr.write(
            f"error: subcommand {sub!r} is unavailable on this installation.\n"
            f"       {failure}\n"
            "       Its module ships with a branch that is not merged here; see "
            "docs/engineering_deferrals.md.\n"
        )
        return 3
    handler = _import_subcommand(sub)
    return handler(args[1:])


if __name__ == "__main__":
    raise SystemExit(main())
