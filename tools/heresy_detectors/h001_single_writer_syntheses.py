"""
H-001 — Single-writer to ``syntheses``.

Sanctioned writer: ``middleware/archive/archive.py``. Test fixtures and
``scripts/exercise_substrate.py`` are whitelisted (they seed the table for
dev/test). Any other file that issues
INSERT/UPDATE/UPSERT/COPY INTO targeting ``syntheses`` is a heresy.

See HERESIES.md H-001 for the carve-out semantics and the prompt-warning
phrasing pulled into agent system prompts.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, List

from ._common import Violation, parse_noqa

MODE = "blocking"
HERESY_ID = "H-001"

# Whitelist of file path *prefixes* (relative to repo root, forward
# slashes) where INSERT/UPDATE/etc against ``syntheses`` is sanctioned.
# Keep this list short and concrete; every entry is justified in
# HERESIES.md.
_WHITELIST_PREFIXES = (
    "middleware/archive/archive.py",        # the one sanctioned writer
    "scripts/exercise_substrate.py",        # dev tool that seeds the table
    "tests/",                               # test fixtures legitimately seed
)

# The pattern needs to catch the common forms without over-matching on
# unrelated identifiers (e.g. ``synthesis`` singular, or string literals
# that happen to contain the word). The boundary regex ``\bsyntheses\b``
# rules out ``syntheses_v2`` style suffixes that would be a different
# table altogether (and therefore not this heresy).
_SQL_RE = re.compile(
    r"(?i)\b(INSERT\s+INTO|UPSERT\s+INTO|UPSERT|UPDATE|COPY\s+INTO)\b"
    r"\s+(?:\"|')?syntheses(?:\"|')?\b",
)


def _is_whitelisted(rel_path: str) -> bool:
    # Normalize separator so the detector works identically on POSIX and
    # any future Windows usage (CI today is Linux but the rule should not
    # encode platform assumptions).
    normalized = rel_path.replace(os.sep, "/")
    return any(normalized.startswith(p) for p in _WHITELIST_PREFIXES)


def run(files: Iterable[str]) -> List[Violation]:
    """Scan ``files`` for the heresy. Files outside the whitelist whose
    contents match the SQL regex are flagged. A line-level ``# noqa: H001
    -- <reason>`` escape hatch suppresses the violation when the reason is
    ≥12 chars.
    """
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
            # Don't fail the hook on unreadable files; pre-commit will
            # have its own complaints about those. We silently skip.
            continue
        for lineno, line in enumerate(source.splitlines(), start=1):
            if not _SQL_RE.search(line):
                continue
            if parse_noqa(line) == HERESY_ID:
                continue
            violations.append(Violation(
                heresy_id=HERESY_ID,
                file=path,
                line=lineno,
                snippet=line,
                reason=(
                    "Writing to syntheses outside middleware/archive/archive.py. "
                    "Route through archive_synthesis() or add a # noqa: H001 -- "
                    "<reason ≥12 chars> if this is a one-off migration."
                ),
            ))
    return violations
