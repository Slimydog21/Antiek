"""Phase runner CLI — operator-facing wrapper around
``orchestration.phase_runner.runner``.

Mirrors the upstream Researchmaxx ``phase_runner.py`` subcommands so
SKILL.md prose that says "run phase_runner verify --phase 8" still
works during the migration window. The library API
(``runner.verify_phase`` etc.) is the load-bearing surface; this CLI
is the operator's shell-level entry point.

Subcommands:

  enter    --investigation-id ID --phase N [--topic TOPIC]
  exit     --investigation-id ID --phase N [--outputs-path P]...
  verify   --investigation-id ID --phase N
           Returns exit code 2 on postcondition failure (the worker
           must stop).
  assert   --investigation-id ID [--phase N]
  status   --investigation-id ID

Postcondition wiring: ``verify`` and ``status`` require an importable module
with a callable ``run_check``. The default is
``orchestration.phase_runner.postconditions``; ``--postcondition-module``
can select another checker. Invalid configuration exits 2 before invoking
the runner or writing verification evidence.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from typing import cast

from orchestration.phase_log import PhaseAssertionError

from . import runner as _runner


class PostconditionConfigurationError(ValueError):
    """The CLI cannot resolve its required artifact checker."""


def _load_postcondition_check(module_path: str | None):
    """Resolve the required ``run_check(phase, investigation_id)`` callable."""
    if not module_path or not module_path.strip():
        raise PostconditionConfigurationError("postcondition module must not be empty")
    try:
        mod = importlib.import_module(module_path)
    except Exception as exc:
        # Import-time failures, including a missing nested dependency, must
        # never select the library's structural-only verification default.
        raise PostconditionConfigurationError(
            f"cannot load postcondition module {module_path!r}: {exc}"
        ) from exc
    check = getattr(mod, "run_check", None)
    if not callable(check):
        raise PostconditionConfigurationError(
            f"postcondition module {module_path!r} must expose callable run_check"
        )
    typed_check = cast(_runner.PostconditionCheck, check)
    # The library selects its optional default by truthiness. A callable
    # object with __bool__ returning False must still run on the CLI path.
    def required_check(phase: int, investigation_id: str) -> tuple[bool, str]:
        return typed_check(phase, investigation_id)

    return required_check


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _cmd_enter(args) -> int:
    _runner.enter_phase(
        args.investigation_id, args.phase, topic=args.topic or "",
        enforce_precondition=not args.no_precondition,
    )
    print(f"entered phase {args.phase} for {args.investigation_id}")
    return 0


def _cmd_exit(args) -> int:
    _runner.exit_phase(
        args.investigation_id, args.phase,
        outputs_paths=args.outputs_path or None,
    )
    print(f"exited phase {args.phase} for {args.investigation_id}")
    return 0


def _cmd_verify(args) -> int:
    """Keystone subcommand — exits 2 on postcondition failure so the
    worker MUST stop. The phase log is NOT marked verified in that
    case; a subsequent assert will refuse to advance."""
    check = _load_postcondition_check(args.postcondition_module)
    outcome = _runner.verify_phase(
        args.investigation_id, args.phase,
        postcondition_check=check,
    )
    if not outcome.passed:
        print(
            f"FAIL: phase {args.phase} postcondition: {outcome.reason}",
            file=sys.stderr,
        )
        return 2
    print(f"OK: phase {args.phase} verified — {outcome.reason}")
    return 0


def _cmd_assert(args) -> int:
    try:
        if args.phase is not None:
            _runner.assert_phase(args.investigation_id, args.phase)
            print(f"OK: phase {args.phase} completed and verified")
        else:
            _runner.assert_ready_for_completion(args.investigation_id)
            print("OK: investigation ready for completion")
    except PhaseAssertionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 2
    return 0


def _cmd_status(args) -> int:
    check = _load_postcondition_check(args.postcondition_module)
    snap = _runner.phase_status(
        args.investigation_id, postcondition_check=check,
    )
    print(json.dumps(snap, indent=2, default=str))
    return 0


# ---------------------------------------------------------------------------
# Argparse wiring
# ---------------------------------------------------------------------------


_DEFAULT_POSTCONDITION_MODULE = "orchestration.phase_runner.postconditions"


def _add_postcondition_arg(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--postcondition-module", default=_DEFAULT_POSTCONDITION_MODULE,
        help=(
            "Dotted module path exposing ``run_check(phase, "
            "investigation_id) -> (passed, reason)``. Required: load failures "
            "or a missing callable exit 2 without verification."
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="antiek-phase-runner",
        description=(
            "Phase runner CLI — composes phase_log (state machine) with "
            "postconditions (artifact-level check) per the 9-phase "
            "autonomous-research protocol."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("enter", help="Mark a phase entered")
    sp.add_argument("--investigation-id", required=True)
    sp.add_argument("--phase", type=int, required=True)
    sp.add_argument("--topic", help="Topic label (used on first log write)")
    sp.add_argument(
        "--no-precondition", action="store_true",
        help="Skip precondition check (recovery scenario only)",
    )
    sp.set_defaults(func=_cmd_enter)

    sp = sub.add_parser("exit", help="Mark a phase exited")
    sp.add_argument("--investigation-id", required=True)
    sp.add_argument("--phase", type=int, required=True)
    sp.add_argument(
        "--outputs-path", action="append", default=[],
        help="Output file path (repeatable). Hash auto-computed.",
    )
    sp.set_defaults(func=_cmd_exit)

    sp = sub.add_parser(
        "verify",
        help=(
            "Run phase postcondition; mark verified iff it passes. "
            "Exits 2 on failure."
        ),
    )
    sp.add_argument("--investigation-id", required=True)
    sp.add_argument("--phase", type=int, required=True)
    _add_postcondition_arg(sp)
    sp.set_defaults(func=_cmd_verify)

    sp = sub.add_parser(
        "assert", help="Assert a phase (or full readiness). Exits 2 on failure.",
    )
    sp.add_argument("--investigation-id", required=True)
    sp.add_argument(
        "--phase", type=int, default=None,
        help="If omitted, assert ready-for-completion (phases 6, 7, 8).",
    )
    sp.set_defaults(func=_cmd_assert)

    sp = sub.add_parser(
        "status",
        help="Dump phase log + live postcondition status (observe-only).",
    )
    sp.add_argument("--investigation-id", required=True)
    _add_postcondition_arg(sp)
    sp.set_defaults(func=_cmd_status)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PostconditionConfigurationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
