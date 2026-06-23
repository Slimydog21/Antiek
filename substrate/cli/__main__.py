"""Unified ``antiek`` CLI entrypoint."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable


def _lint_main() -> Callable[[list[str] | None], int]:
    import importlib.util
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[2]
        / "scripts" / "lint_context_injection.py"
    )
    spec = importlib.util.spec_from_file_location("antiek_lint", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"lint script not found: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn: Callable[[list[str] | None], int] = module.main
    return fn


_SUBCOMMAND_MODULES: dict[str, str] = {
    "burn": "substrate.observability.burn_cli",
    "branch": "substrate.conversation.cli",
    "hooks": "substrate.cli.hooks",
    "harness": "substrate.cli.harness",
    "compact": "substrate.cli.compact",
    "queue": "substrate.cli.queue",
}


def _import_subcommand(name: str) -> Callable[[list[str] | None], int]:
    if name == "lint":
        return _lint_main()
    module_name = _SUBCOMMAND_MODULES.get(name)
    if module_name is None:
        raise ValueError(f"unknown subcommand {name!r}")
    mod = importlib.import_module(module_name)
    main_fn: Callable[[list[str] | None], int] = mod.main
    return main_fn


SUBCOMMANDS = ("burn", "branch", "hooks", "harness", "compact", "queue", "lint")


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