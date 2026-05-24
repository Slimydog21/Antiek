"""
Antiek heresy detectors — mechanical CI guards for recurrent invariant
violations documented in ``HERESIES.md``.

Per Yegge (December 2025 interview): prompt warnings and LLM-judges are
unreliable enforcers; CI gates that always run are the only thing that
keeps a heresy from quietly returning. Every detector in this package is
intentionally mechanical (regex or AST) so it is fast (<200ms per
detector on a typical staged diff) and deterministic. No LLM, no
heuristic, no flake.

Wire up via ``.githooks/pre-commit``; activated per-clone with
``git config core.hooksPath .githooks``.

Each detector module exports a function ``run(files: Sequence[str]) ->
list[Violation]``. The caller (``run_all``) aggregates and decides exit
code per the detector's ``MODE`` constant (``blocking`` or ``warn_only``).

Spec: ``~/specs/antiek-yegge-execute/sprint-02-heresy-registry.html``.
"""

from __future__ import annotations

from ._common import Violation, NOQA_REASON_MIN_CHARS, parse_noqa

__all__ = ["Violation", "NOQA_REASON_MIN_CHARS", "parse_noqa"]
