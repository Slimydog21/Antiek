#!/usr/bin/env python3
"""SPR-02 — Hermetic contract repro for cascade auto-decompose.

Proves (without network or provider keys):
  • ``roles.decomposer.prompt.render_full_prompt`` is keyword-only after ``*``.
  • ``substrate.dispatch.router.dispatch`` requires ``investigation_id`` (kw-only).
  • The pre-fix call patterns raise ``TypeError`` before any LLM request.

Exit 0 when contracts match the planner fix in ``roles/cascade_planner/planner.py``.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from roles.decomposer.prompt import render_full_prompt  # noqa: E402
from substrate.dispatch.router import dispatch  # noqa: E402


def _param_kind(fn, name: str):
    return inspect.signature(fn).parameters[name].kind


def _assert_kwonly(fn, name: str, *, label: str) -> None:
    kind = _param_kind(fn, name)
    if kind != inspect.Parameter.KEYWORD_ONLY:
        raise AssertionError(f"{label}: {name!r} must be keyword-only, got {kind!r}")


def _expect_typeerror(label: str, fn) -> None:
    try:
        fn()
    except TypeError as exc:
        print(f"REPRO_OK: {label} → TypeError: {exc}")
        return
    raise AssertionError(f"{label}: expected TypeError, call succeeded")


def main() -> int:
    # --- Signature lock (inspect, not training memory) ---
    for pname in ("investigation_id", "question", "context", "extra_user_prefix"):
        _assert_kwonly(render_full_prompt, pname, label="render_full_prompt")
    _assert_kwonly(dispatch, "investigation_id", label="dispatch")

    # Positional ``question`` alone must not bind (all user args are kw-only).
    _expect_typeerror(
        "old pattern render_full_prompt(question) positional",
        lambda: render_full_prompt("What is the TAM for photonics?"),  # type: ignore[misc]
    )

    # Pre-fix dispatch omitted investigation_id (would crash before HTTP).
    _expect_typeerror(
        "old pattern dispatch(prompt, role) without investigation_id",
        lambda: dispatch("prompt", "decomposer"),  # type: ignore[call-arg]
    )

    # Correct local assembly — no network (prompt string only).
    prompt = render_full_prompt(
        investigation_id="repro-inv",
        question="What is the TAM for photonics?",
        context="",
    )
    if "repro-inv" not in prompt or "photonics" not in prompt:
        raise AssertionError("render_full_prompt keyword call did not embed placeholders")

    print("REPRO_OK: contracts locked — auto-decompose path can reach dispatch kwargs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())