"""comment_quality.py — Ousterhout Ch. 13 what-vs-why comment lint (AOD SPR-05).

Ousterhout, Ch. 13: comments should describe what is NOT obvious from the code.
The cardinal sin is a **what-comment** that restates the next line at the same
level of detail (`# increment i by one` above `i += 1`): zero information,
reading cost, rots out of sync. A **why-comment** captures what the code cannot —
the rationale, a constraint/invariant, a magic number's units/provenance, a
cross-module contract. At 1000s of files, the what-comment is invisible without
a tool.

INFORMATIONAL, baseline-mode (reuses tools/lints/baseline.py): capture today's
what-comments as grandfathered, then report only NEW ones — the trend, without a
flag-day. It is NOT a hard gate (a what-vs-why classifier is judgment-laden; a
hard gate would train people to write worse comments to satisfy it). `enforce`
exits 0 always. It reports its own false-positive rate honestly (milestone 4).

------------------------------------------------------------------------------
THE HEURISTIC (milestone 1 — pinned before the detector)
------------------------------------------------------------------------------
Scope: only inline `#` comments (full-line and trailing one-liners). Module and
multi-line docstrings are OUT (Ch. 13 "interface comments" — a different lens).

WHAT (flag): a `#` comment whose meaningful tokens (lowercased, stop-words
removed, light stemming, number-words and a few operator-words mapped) are a
SUBSET of the identifiers/operators on the line it describes — it paraphrases the
code and adds nothing.
  e.g. `# set the counter to zero` over `counter = 0`; `# loop over items` over `for item in items:`.

WHY (never flagged) — the exemptions, each justified:
  * rationale markers: because, so that, to avoid, otherwise, note:, per §, see, e.g., i.e., rationale, invariant, hack, workaround, must, cannot
  * a citation/reference: `§`, a `#123` issue ref, a URL, a 4-digit year (provenance)
  * a magic number's units/source: contains a number + a unit word (ms, sec, bytes, %, px, MB, KB)
  * longer-than-the-code by a margin (>8 meaningful tokens, or > 1.6x the code line) — likely adds context
  * a directive, not prose: `# type:`, `# noqa`, `# pragma`, coding cookie, shebang, `# fmt:`
  * a section/divider header (mostly punctuation, or not attached to a statement)
  * TODO / FIXME / XXX — a different concern

The classifier is fuzzy by nature; milestone 4 measures and DISCLOSES its
false-positive rate rather than pretending it is exact.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import token as _token
import tokenize
from dataclasses import dataclass
from pathlib import Path

from tools.lints.baseline import (
    ViolationKey,
    compute_keys,
    filter_to_new_only,
    find_stale_baseline_entries,
    load_baseline,
    write_baseline,
)

__all__ = ["Violation", "classify_comment", "scan_paths", "main"]

LINT_NAME = "comment_quality"

WHY_MARKERS: tuple[str, ...] = (
    "because", "so that", "so we", "to avoid", "otherwise", "note:", "note that",
    "per §", "per rfc", "see ", "e.g.", "i.e.", "rationale", "invariant", "hack",
    "workaround", "must ", "cannot", "never ", "always ", "assumes", "guard",
    "otherwise:", "why ", "why:",
)

# A comment above one of these is a section / interface label (Ch. 13's
# "interface comment"), not a what-restatement of an executable statement — the
# section-header false-positive the milestone-4 tuning pass removed.
_DEFINITION_LINE = re.compile(r"^\s*(async\s+def\s|def\s|class\s|@|['\"])")
DIRECTIVE_MARKERS: tuple[str, ...] = (
    "type:", "noqa", "pragma", "-*-", "!", "fmt:", "isort:", "mypy:", "pylint:",
    "nosec", "coding:", "yapf:", "pyright:", "ruff:",
)
TODO_MARKERS: tuple[str, ...] = ("todo", "fixme", "xxx", "hack:")
UNIT_WORDS: tuple[str, ...] = (
    "ms", "sec", "secs", "seconds", "bytes", "byte", "kb", "mb", "gb", "px",
    "hz", "khz", "%", "percent", "μs", "us", "ns", "minutes", "hours", "days",
)

STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "to", "of", "for", "in", "on", "by", "with", "and", "or",
    "is", "are", "this", "that", "it", "we", "then", "here", "as", "at", "be",
    "into", "from", "each", "all", "its", "if", "over", "up", "down", "out",
})

NUMBER_WORDS: dict[str, str] = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "none": "none", "true": "true", "false": "false", "empty": "",
}

# operator/keyword tokens on the code line -> the plain-English word a
# what-comment tends to use for them, so "increment i" matches "i += 1".
OP_WORDS: dict[str, tuple[str, ...]] = {
    "=": ("set", "assign", "make", "store", "define"),
    "+=": ("increment", "add", "bump", "plus"),
    "-=": ("decrement", "subtract", "minus"),
    "*=": ("multiply", "times"),
    "/=": ("divide",),
    "return": ("return", "give"),
    "for": ("loop", "iterate", "each"),
    "while": ("loop", "while", "until"),
    "if": ("check", "test"),
    "append": ("append", "add"),
    "import": ("import",),
    "raise": ("raise", "throw", "error"),
    "not": ("not", "negate"),
    "+": ("add", "sum", "concat"),
    "-": ("subtract",),
    "==": ("equal", "check", "compare"),
    "del": ("delete", "remove"),
}

_WORD_RE = re.compile(r"[A-Za-z0-9μ]+")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_ISSUE_RE = re.compile(r"#\d+")
_URL_RE = re.compile(r"https?://|www\.")


@dataclass(frozen=True, order=True)
class Violation:
    path: str
    line: int
    col: int
    comment: str
    next_line: str
    reason: str


def _split_identifier(tok: str) -> list[str]:
    """snake_case / camelCase -> lowercased parts."""
    parts = re.split(r"[_\W]+", tok)
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        # split camelCase
        for piece in re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+", p):
            out.append(piece.lower())
    return out or [tok.lower()]


def _stem(word: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(word) > len(suf) + 2 and word.endswith(suf):
            return word[: -len(suf)]
    return word


def _content_tokens(comment_text: str) -> list[str]:
    """Meaningful comment tokens: lowercased, stop-words removed, number-words
    mapped, lightly stemmed."""
    raw = [w.lower() for w in _WORD_RE.findall(comment_text)]
    out: list[str] = []
    for w in raw:
        w = NUMBER_WORDS.get(w, w)
        if not w or w in STOPWORDS:
            continue
        out.append(_stem(w))
    return out


def _code_vocab(code_line: str) -> set[str]:
    """The identifier + operator vocabulary of a code line, expanded via
    OP_WORDS and split into sub-words, for subset-matching against a comment."""
    vocab: set[str] = set()
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(code_line).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        toks = []
    saw: list[str] = []
    for t in toks:
        if t.type in (_token.NAME, _token.NUMBER):
            saw.append(t.string)
            for part in _split_identifier(t.string):
                vocab.add(_stem(part))
        elif t.type == _token.OP:
            saw.append(t.string)
    for s in saw:
        for w in OP_WORDS.get(s, ()):  # keyword/op -> english
            vocab.add(_stem(w))
    # fallback: also add raw words from the line text
    for w in _WORD_RE.findall(code_line):
        vocab.add(_stem(w.lower()))
    return vocab


def classify_comment(comment_text: str, code_line: str) -> tuple[bool, str]:
    """(is_what_comment, reason). A what-comment is flagged; anything exempt or
    non-matching returns False with the reason it was spared."""
    low = comment_text.lower().strip()
    stripped = low.lstrip("#!-=* ").strip()

    if not stripped:
        return False, "empty/divider"
    if any(stripped.startswith(d) or low.lstrip("# ").startswith(d) for d in DIRECTIVE_MARKERS):
        return False, "directive (not prose)"
    if any(m in low for m in TODO_MARKERS):
        return False, "todo/fixme (different concern)"
    # divider / section header: box-drawing chars, a run of >=3 repeated
    # separators, or mostly punctuation
    if re.search(r"[─═━│┄┅•·]", comment_text) or re.search(r"([-=*#_~])\1{2,}", comment_text):
        return False, "divider/section header"
    if len(re.sub(r"[A-Za-z0-9]", "", comment_text)) > len(comment_text) * 0.6:
        return False, "divider/section header"
    if not code_line.strip():
        return False, "section header (no attached statement)"
    if _DEFINITION_LINE.match(code_line):
        return False, "interface/section label above a def/class/decorator/literal"

    # WHY exemptions
    if any(m in low for m in WHY_MARKERS):
        return False, "rationale marker (why-comment)"
    if _YEAR_RE.search(comment_text) or _ISSUE_RE.search(comment_text) or _URL_RE.search(comment_text) or "§" in comment_text:
        return False, "citation/provenance"
    words = _content_tokens(comment_text)
    if any(u in low.split() for u in UNIT_WORDS) and any(c.isdigit() for c in comment_text):
        return False, "magic-number units/provenance"
    if len(words) > 8:
        return False, "adds context (long comment)"
    if len(comment_text) > len(code_line.strip()) * 1.6 + 10:
        return False, "adds context (longer than code)"

    if not words:
        return False, "no meaningful tokens"

    vocab = _code_vocab(code_line)
    missing = [w for w in words if w not in vocab]
    if not missing:
        return True, f"restates code — every comment word maps to the line: {{{', '.join(words)}}}"
    return False, f"adds info (comment words not in code: {', '.join(missing)})"


def _next_code_line(lines: list[str], start_idx: int) -> tuple[int, str]:
    """From 0-based line index start_idx, the next line that has code (skipping
    blanks and full-line comments). Returns (1-based line no, text) or (-1, '')."""
    for i in range(start_idx, len(lines)):
        s = lines[i].strip()
        if s and not s.startswith("#"):
            return i + 1, lines[i]
    return -1, ""


def scan_file(path: Path) -> list[Violation]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    lines = source.splitlines()
    out: list[Violation] = []
    try:
        toks = tokenize.generate_tokens(io.StringIO(source).readline)
        comments = [t for t in toks if t.type == tokenize.COMMENT]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []
    for t in comments:
        row, col = t.start
        line_text = lines[row - 1] if 0 <= row - 1 < len(lines) else ""
        before = line_text[:col].strip()
        trailing = bool(before)  # code precedes the comment on this line
        if trailing:
            described_line, described_text = row, line_text[:col]
        else:
            # A full-line comment whose previous line is also a full-line comment
            # is part of a multi-line comment BLOCK (prose), not a per-line
            # restatement — skip it (milestone-4 tuning: kills wrapped-comment tails).
            prev = lines[row - 2].strip() if row >= 2 else ""
            if prev.startswith("#"):
                continue
            described_line, described_text = _next_code_line(lines, row)  # first code line at/after next
            if described_line == -1:
                continue
        is_what, reason = classify_comment(t.string, described_text)
        if is_what:
            out.append(
                Violation(
                    path=path.as_posix(), line=row, col=col,
                    comment=t.string.strip(),
                    next_line=described_text.strip(),
                    reason=reason,
                )
            )
    return out


_SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".git", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".hypothesis", "build", "dist"}


def scan_paths(paths: list[Path | str]) -> list[Violation]:
    out: list[Violation] = []
    for raw in paths:
        p = Path(raw)
        files = [p] if p.is_file() else [
            f for f in sorted(p.rglob("*.py"))
            if not any(part in _SKIP_DIRS for part in f.parts)
        ]
        for f in files:
            out.extend(scan_file(f))
    return sorted(out)


def _to_key(v: object) -> ViolationKey:
    assert isinstance(v, Violation)  # house adapter shape (see tools/lints/cli_with_baseline.py)
    return ViolationKey(path=v.path, line=v.line, col=v.col, kind="what_comment")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="comment_quality",
        description="Ousterhout what-vs-why comment lint (INFORMATIONAL — never fails the build).",
    )
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("capture", "enforce", "stale", "report"):
        sp = sub.add_parser(mode, help=f"{mode} mode")
        sp.add_argument("--paths", nargs="+", required=True, type=str)
        sp.add_argument("--baseline-file", type=Path, default=Path("tools/lints/baselines/comment_quality.json"))
        if mode == "report":
            sp.add_argument("--out", type=Path, default=Path("reports/complexity/comment_quality.md"))
    args = parser.parse_args(argv)

    violations = scan_paths(list(args.paths))
    keys = compute_keys(violations, _to_key)

    if args.mode == "capture":
        write_baseline(args.baseline_file, lint=LINT_NAME, violations=keys)
        print(f"captured {len(keys)} what-comment(s) to {args.baseline_file}")
        return 0

    if args.mode == "report":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Comment-quality report — Ousterhout Ch. 13 what-vs-why lens",
            "",
            f"- What-comments found: **{len(violations)}** across the scanned paths",
            "- INFORMATIONAL: a trend signal, never a build gate. Promotion to a soft-fail gate is conditioned on FP rate < ~5% on a labeled sample (see handoff).",
            "",
            "## Sample (first 25 flagged — open each to judge)",
            "",
            "| path:line | comment | describes | why flagged |",
            "|-----------|---------|-----------|-------------|",
        ]
        for v in violations[:25]:
            lines.append(f"| `{v.path}:{v.line}` | `{v.comment[:50]}` | `{v.next_line[:40]}` | {v.reason[:60]} |")
        lines.append("")
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {args.out}: {len(violations)} what-comments")
        return 0

    # enforce / stale — INFORMATIONAL, always exit 0
    try:
        baseline = load_baseline(args.baseline_file)
    except FileNotFoundError:
        print(f"baseline not found: {args.baseline_file} (run `capture` first)", file=sys.stderr)
        return 0
    new_only = filter_to_new_only(keys, baseline)
    for k in new_only:
        print(f"{k.path}:{k.line}: NEW what-comment")
    if args.mode == "stale":
        stale = find_stale_baseline_entries(keys, baseline)
        for k in stale:
            print(f"  fixed (baseline can shrink): {k.path}:{k.line}", file=sys.stderr)
    print(
        f"\n{len(new_only)} NEW what-comment(s) since baseline "
        f"(informational — exit 0)",
        file=sys.stderr,
    )
    return 0  # NEVER fails the build


if __name__ == "__main__":
    sys.exit(main())
