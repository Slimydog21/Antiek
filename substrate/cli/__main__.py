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
    elif name == "midnight-oil-worker":
        from substrate.midnight_oil.worker_cli import main
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


SUBCOMMANDS = (
    "burn",
    "branch",
    "hooks",
    "harness",
    "compact",
    "queue",
    "midnight-oil-worker",
    "lint",
)


def _print_usage() -> None:
    sys.stdout.write(
        "usage: antiek <subcommand> [args...]\n"
        "\n"
        "Available subcommands:\n"
        "  burn      Per-call burn telemetry\n"
        "  branch    Conversation checkpoint + branch\n"
        "  hooks     Inspect / manage substrate hooks\n"
        "  harness   Per-project harness fork / apply / diff / status\n"
        "  compact   Manual compaction\n"
        "  queue     Bounded-queue inspection\n"
        "  midnight-oil-worker  Durable autonomous research worker\n"
        "  lint      Context-injection static analysis\n"
        "\n"
        "Run `antiek <subcommand> --help` for subcommand-specific flags.\n"
    )


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
    handler = _import_subcommand(sub)
    return handler(args[1:])


if __name__ == "__main__":
    raise SystemExit(main())
