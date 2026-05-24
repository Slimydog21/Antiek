"""
H-004 — Unobserved spawn (WARN-ONLY at Wave 1).

Spawned workers that aren't registered with the worker registry are
opaque: an orchestrator fires them off, awaits them, and mid-flight has
no observability. Yegge's polecat-vs-sub-agent distinction. The
substrate-correct path is to register every long-running spawn so the
operator can see it.

At Wave 1 the worker registry doesn't yet exist (it lands in a future
``feature/yegge-spr-04-worker-identity`` sprint), so this detector
operates in **warn-only** mode: it prints warnings to stderr but does
not block the commit. When SPR-04 lands the warn-only flag flips to
blocking; the diff is one line. The warn-only stance is deliberate —
shipping a blocking detector before its prerequisite would either block
all spawns (loud false positives) or require carving out everything
that exists today (a whitelist-shaped detector that adds no signal).

Detected spawn forms:
  - ``subprocess.Popen(...)`` / ``subprocess.run(...)`` /
    ``subprocess.check_output(...)`` etc.
  - ``asyncio.create_task(...)`` / ``asyncio.ensure_future(...)``
  - ``threading.Thread(...)``
  - ``multiprocessing.Process(...)`` / ``multiprocessing.Pool(...)``

Carve-out (require this on a noqa): truly ephemeral subprocess calls
(<100ms measured). Reason must include the literal substring
``ephemeral, <100ms``.

See HERESIES.md H-004.
"""

from __future__ import annotations

import ast
import os
from typing import Iterable, List

from ._common import Violation, parse_noqa

# IMPORTANT: flip MODE to "blocking" when SPR-04 (worker registry)
# lands on main. Update HERESIES.md H-004 entry at the same time.
MODE = "warn_only"
HERESY_ID = "H-004"

# subprocess.run() inside test helpers and migrations is fine; tests do
# this constantly to exercise spawned binaries deterministically. The
# overhead of registry registration would dwarf the test runtime.
_WHITELIST_PREFIXES = (
    "tests/",
    "scripts/",                 # one-off dev tools
    "substrate/event_log/migrations/",
)


def _is_whitelisted(rel_path: str) -> bool:
    normalized = rel_path.replace(os.sep, "/")
    return any(normalized.startswith(p) for p in _WHITELIST_PREFIXES)


# (module, attribute) shape that constitutes a spawn. Kept narrow so we
# don't over-match unrelated APIs that happen to share names.
_SPAWN_TARGETS: set[tuple[str, str]] = {
    ("subprocess", "Popen"),
    ("subprocess", "run"),
    ("subprocess", "call"),
    ("subprocess", "check_call"),
    ("subprocess", "check_output"),
    ("asyncio", "create_task"),
    ("asyncio", "ensure_future"),
    ("threading", "Thread"),
    ("multiprocessing", "Process"),
    ("multiprocessing", "Pool"),
}


def _spawn_kind(call: ast.Call) -> str | None:
    """Return a human-readable spawn kind if this call is one we recognize."""
    if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
        pair = (call.func.value.id, call.func.attr)
        if pair in _SPAWN_TARGETS:
            return f"{pair[0]}.{pair[1]}"
    return None


def run(files: Iterable[str]) -> List[Violation]:
    violations: List[Violation] = []
    for path in files:
        if not path.endswith(".py"):
            continue
        if _is_whitelisted(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError:
            continue

        source_lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            kind = _spawn_kind(node)
            if kind is None:
                continue

            lineno = getattr(node, "lineno", 0) or 1
            snippet = source_lines[lineno - 1] if 0 <= lineno - 1 < len(source_lines) else ""
            if parse_noqa(snippet) == HERESY_ID:
                continue

            violations.append(Violation(
                heresy_id=HERESY_ID,
                file=path,
                line=lineno,
                snippet=snippet,
                reason=(
                    f"Unobserved {kind} — at Wave 1 this is warn-only; flip to "
                    "register_worker(...) when SPR-04 ships. Carve-out: "
                    "# noqa: H004 -- ephemeral, <100ms (measured)."
                ),
            ))
    return violations
