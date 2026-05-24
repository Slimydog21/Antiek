"""
Shared scaffolding for heresy detectors.

Two responsibilities:

1. The ``Violation`` dataclass — what every detector emits.
2. The noqa escape-hatch parser — every detector honors the same
   ``# noqa: H00N -- <reason>`` syntax, with a minimum reason length to
   prevent the bare-noqa anti-pattern (``noqa`` rot is itself a heresy
   the registry would catch, except it's caught here).

Why a minimum reason length? Bare ``noqa`` doesn't survive code review
six months out — a reviewer cannot tell whether the original author
had a real reason or was silencing a true bug. Requiring a reason of
at least 12 characters ("test fixture" is the minimum legitimate
reason, and that is exactly 12 chars) forces the author to write
something a reviewer can audit, and the regex below rejects shorter
strings at parse time so the detector exits non-zero on bare noqas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# A noqa reason of "test fixture" is 12 chars. Anything shorter is
# almost certainly rationalization. 12 was picked to admit the
# shortest legitimate reason verbatim; tighter thresholds would
# punish legitimate cases, looser thresholds re-admit ``noqa``-style
# noise.
NOQA_REASON_MIN_CHARS = 12

# ``# noqa: H001 -- test fixture seeds the table``
# Group 1 = heresy ID; group 2 = reason text.
#
# The reason group is greedy (``.+``) on purpose: non-greedy + anchored
# ``$`` matches a single character and leaves the rest of the reason to
# the trailing ``\s*$``, which fails as soon as the reason contains a
# non-space character. Greedy gives us the full tail; we strip leading
# and trailing whitespace ourselves below before length-checking.
_NOQA_RE = re.compile(
    r"#\s*noqa\s*:\s*(H\d{3})\s*--\s*(.+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Violation:
    """A single heresy violation, suitable for human or machine output.

    Attributes
    ----------
    heresy_id
        The HERESIES.md ID this violates (e.g. ``"H-001"``).
    file
        Path to the offending file (relative to repo root by convention).
    line
        1-based line number.
    snippet
        Short excerpt of the offending line for context.
    reason
        Human-readable explanation of why this is a violation.
    """

    heresy_id: str
    file: str
    line: int
    snippet: str
    reason: str

    def render(self) -> str:
        """Render as a single human-readable line for the pre-commit hook."""
        return (
            f"{self.heresy_id}: {self.file}:{self.line}\n"
            f"    {self.snippet.strip()}\n"
            f"    -> {self.reason}"
        )


def parse_noqa(line: str) -> Optional[str]:
    """Return the noqa heresy ID if the line carries a valid escape hatch.

    A valid escape hatch is ``# noqa: H00N -- <reason at least 12 chars>``.
    Bare ``noqa`` or ``noqa: H001`` without a reason returns None and is
    therefore NOT honored — the detector will still flag the line. This
    prevents the bare-noqa-rot pattern that makes static analysis useless
    over time.

    Returns the *dashed* form (``"H-001"``) so detectors can compare
    against their ``HERESY_ID`` constants directly. The undashed form
    (``"H001"``) is the wire syntax in source comments because it is
    less typo-prone for the author; the dashed form is the canonical
    human-readable ID in HERESIES.md.
    """
    m = _NOQA_RE.search(line)
    if not m:
        return None
    reason = m.group(2).strip()
    if len(reason) < NOQA_REASON_MIN_CHARS:
        return None
    raw = m.group(1).upper()        # e.g. "H001"
    return f"{raw[0]}-{raw[1:]}"     # -> "H-001"
