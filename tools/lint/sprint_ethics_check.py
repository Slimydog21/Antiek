#!/usr/bin/env python3
"""Sprint-ethics articulation lint.

DDIA-execution SPR-08. Anchors philosophy P9 (ethics is a load-bearing
trade-off line in sprint headers, not a closing chapter).

Scans Markdown and HTML spec/sprint files under ``specs/``,
``docs/decisions/``, and ``docs/`` for trigger terms (publisher,
consent, Bartz, etc.). If a file mentions a trigger term, it MUST
include either:

    a) An ethics articulation block (heading "Ethics articulation"
       with all four field labels: Technical risk, Societal/user risk,
       Reputational risk, Operator decision), OR
    b) An explicit "Ethics N/A — <justification>" sentence.

The lint catches PRESENCE, not quality. Quality is operator + peer
review. Presence alone forces engineers to surface the trade-off
during the spec-authoring window, which is when it's cheapest to
discuss.

Run::

    .venv/bin/python tools/lint/sprint_ethics_check.py
    .venv/bin/python tools/lint/sprint_ethics_check.py path/to/spec.md

Today: forward-only. Existing sprint documents that pre-date this
lint are not retroactively scanned. The path-allowlist mechanism
exists for that, but currently the allowlist is empty — see
docs/decisions/sprint_ethics_articulation.md "Forward-only policy".
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

TRIGGER_TXT = REPO_ROOT / "tools" / "lint" / "ethics_trigger_terms.txt"
ALLOWLIST_TXT = REPO_ROOT / "tools" / "lint" / "ethics_allowlist.txt"

# Where to scan.
SCAN_DIRS = ["specs", "docs"]

# What extensions count as spec/sprint documents.
SCAN_EXTS = (".md", ".html")

# What we don't scan: anything under docs/runbooks/ (operator
# diagnostics, not spec/sprint headers) and docs/decisions/ that
# pre-date SPR-08 (the forward-only policy).
SKIP_PATTERNS = [
    "docs/runbooks/",
]

# Required field labels for a real block. Looked up case-insensitive
# inside the "Ethics articulation" section.
REQUIRED_FIELDS = [
    "Technical risk",
    "Societal",        # accepts "Societal" or "Societal / user risk"
    "Reputational",
    "Operator decision",
]

# Marker strings that DECLARE the block. Either form acceptable.
BLOCK_HEADING_PATTERNS = [
    re.compile(r"##\s+Ethics articulation\b", re.IGNORECASE),
    re.compile(r"<h2[^>]*>\s*Ethics articulation\s*</h2>", re.IGNORECASE),
]

NA_DECLARATION = re.compile(
    r"Ethics\s+N/A\s*[—\-:]\s*\S",
    re.IGNORECASE,
)


def _load_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    out: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "  # " in line:
            line = line.split("  # ", 1)[0].rstrip()
        if line:
            out.append(line)
    return out


def load_triggers() -> list[str]:
    return _load_lines(TRIGGER_TXT)


def load_allowlist() -> list[str]:
    return _load_lines(ALLOWLIST_TXT)


def _is_skipped(rel_path: str, allowlist: list[str]) -> bool:
    for pattern in SKIP_PATTERNS:
        if rel_path.startswith(pattern):
            return True
    for entry in allowlist:
        if entry.endswith("/"):
            if rel_path == entry.rstrip("/") or rel_path.startswith(entry):
                return True
        else:
            if rel_path == entry:
                return True
    return False


def _has_trigger(text: str, triggers: list[str]) -> set[str]:
    """Return the set of triggers found in the text. Case-insensitive
    whole-word match.
    """
    found: set[str] = set()
    lower = text.lower()
    for trig in triggers:
        # Whole-word for alpha terms; substring is OK for hyphenated
        # legal-term codes (e.g., Bartz, MDL).
        pattern = re.compile(
            rf"\b{re.escape(trig.lower())}\b"
            if not any(c in trig for c in "_-/")
            else re.escape(trig.lower())
        )
        if pattern.search(lower):
            found.add(trig)
    return found


def _has_valid_block(text: str) -> tuple[bool, list[str]]:
    """Return (has_block_or_na, missing_fields) for a file.

    has_block_or_na is True if either:
        - A "Ethics N/A — <justification>" sentence appears, OR
        - The "Ethics articulation" heading appears AND all four
          REQUIRED_FIELDS labels appear after it.

    If the heading appears but fields are missing, return False with
    the list of missing field labels.
    """
    if NA_DECLARATION.search(text):
        return (True, [])

    heading_match = None
    for pat in BLOCK_HEADING_PATTERNS:
        m = pat.search(text)
        if m:
            heading_match = m
            break
    if heading_match is None:
        return (False, ["[no Ethics articulation heading or 'Ethics N/A'] "])

    after = text[heading_match.end():]
    missing: list[str] = []
    for field in REQUIRED_FIELDS:
        if not re.search(rf"\b{re.escape(field)}", after, re.IGNORECASE):
            missing.append(field)
    return (not missing, missing)


def _iter_scannable_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for scan_dir in SCAN_DIRS:
        base = root / scan_dir
        if not base.exists():
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            for fname in filenames:
                if fname.endswith(SCAN_EXTS):
                    out.append(Path(dirpath) / fname)
    return out


def check_files(
    files: list[Path], triggers: list[str], allowlist: list[str]
) -> list[tuple[Path, set[str], list[str]]]:
    """Return list of (path, found_triggers, missing_fields) for each
    file that mentions triggers but lacks a valid block.
    """
    violations: list[tuple[Path, set[str], list[str]]] = []
    for fpath in files:
        try:
            rel = fpath.resolve().relative_to(REPO_ROOT)
        except ValueError:
            continue
        rel_str = str(rel)
        if _is_skipped(rel_str, allowlist):
            continue
        try:
            text = fpath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        found = _has_trigger(text, triggers)
        if not found:
            continue
        ok, missing = _has_valid_block(text)
        if not ok:
            violations.append((rel, found, missing))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sprint_ethics_check",
        description=(
            "Lint spec/sprint files: those mentioning §9.0-relevant "
            "terms must include an Ethics articulation block."
        ),
        epilog=(
            "See docs/templates/sprint_ethics_block.md and "
            "docs/decisions/sprint_ethics_articulation.md."
        ),
    )
    parser.add_argument("files", nargs="*")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    triggers = load_triggers()
    allowlist = load_allowlist()

    t0 = time.monotonic()
    if args.files:
        files = [Path(p) for p in args.files if p.endswith(SCAN_EXTS)]
    else:
        files = _iter_scannable_files(REPO_ROOT)

    violations = check_files(files, triggers, allowlist)
    elapsed = time.monotonic() - t0

    if violations:
        print(
            f"sprint_ethics_check: {len(violations)} file(s) need an "
            f"Ethics articulation block ({elapsed:.2f}s):",
            file=sys.stderr,
        )
        for path, found, missing in violations:
            triggers_str = ", ".join(sorted(found))
            if missing == ["[no Ethics articulation heading or 'Ethics N/A'] "]:
                print(
                    f"  {path}: triggered by [{triggers_str}] — "
                    "no Ethics articulation block found",
                    file=sys.stderr,
                )
            else:
                print(
                    f"  {path}: triggered by [{triggers_str}] — "
                    f"heading present but missing fields: {missing}",
                    file=sys.stderr,
                )
        print(
            "\nP9 (philosophy doc): ethics is a load-bearing trade-off "
            "line in sprint headers, not a closing chapter. See "
            "docs/templates/sprint_ethics_block.md for the template "
            "and the 'Ethics N/A —' skip form.",
            file=sys.stderr,
        )
        return 1

    if not args.quiet:
        print(
            f"sprint_ethics_check: clean ({len(files)} file(s), "
            f"{elapsed:.2f}s)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
