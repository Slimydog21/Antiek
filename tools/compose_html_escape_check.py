#!/usr/bin/env python3
"""Compose-tier HTML-escaping static gate (compose-xss-guard).

Context (assume zero project knowledge)
=======================================
Antiek is an HTML-native platform: every information asset it ingests
(arxiv/substack abstracts, acquired books, research artifacts) is normalized to
canonical HTML and rendered. The compose tier (``substrate/*_compose*.py`` and
the research-artifact composer) builds the HTML scaffolds that become the
substrate of the "infinite information platform" — recursive twin documents,
write-mode draft merges, research sections. Two open PRs
(#962 ``recursive_twin_note_taker_compose``,
#955 ``write_mode_twin_draft_merge_compose``) built those scaffolds by **raw
interpolation of untrusted values with zero ``html.escape``**::

    f'<section data-parent="{parent}">{excerpt}</section>'

``parent`` / ``excerpt`` derive from ingested external content; on an HTML-native
platform that is stored XSS the moment the scaffold renders. Both PRs passed
Strix Security Review, which does not catch this class in pure-compose modules.

The codebase ALREADY escapes correctly everywhere that matters —
``substrate/research_artifact/render.py::_esc`` (``html.escape(s, quote=True)``)
wraps every interpolation in the renderer, and the frontend has a static
``_DOM_MUTATION`` gate (``tools/lint/reading_physics_check.py``) forbidding
``innerHTML=``. The compose tier was the only un-gated surface. This module is
the gate that makes the recurring class **structurally impossible**: a compose
module that builds an HTML tag by interpolating an unescaped value reds the
check before it ships, instead of leaking to review (or past it).

What it is — and honestly is not
================================
This is a **static, AST-level** guard. It walks every ``.py`` under the target
directory and inspects each f-string (``ast.JoinedStr``), ``str.format`` call,
``%`` formatting, and ``+`` concatenation of a string literal with a value. It
reconstructs the literal skeleton (holes removed), decides whether the literal
is HTML-building (contains an opening ``<[a-zA-Z]`` tag), then flags any
interpolated value that sits **inside an open tag** (attribute context —
``data-x="{var}"``) or **immediately adjacent to a tag delimiter** (content
context — ``>{var}<``) UNLESS the value is wrapped in a known escaper.

The escaper allow-list matches the existing house convention, not an invented
one: ``html.escape`` (and any ``.escape`` attribute call such as
``markupsafe.escape``), plus the named helpers already in the tree
(``_esc`` / ``_escape`` / ``escape_html`` / ``html_escape`` / ``markup_escape``).

Honest limits (named, not hidden):
  (i)  **Interpolation + simple concatenation only.** HTML built by deep
       concatenation chains across many non-literal operands, by ``io.StringIO``
       writes, or by a template engine is not modeled. The recurring class in
       the compose tier is f-string interpolation; that is what is gated, with
       ``.format`` / ``%`` / single-adjacency ``+`` as defense-in-depth.
  (ii) **Literal tag shapes.** A tag whose name or ``<`` is itself produced by a
       nested variable (``f"{lt}section>"``) has no literal tag shape to match
       and is not caught — the safe direction is to always write tags as
       literals. Review-owned, like the dynamic-import limit of
       ``reading_physics_check``.
  (iii)**Escaper-by-name.** A value is "escaped" only if it is a direct call to
        an allowlisted escaper; an escape applied through an un-named helper
        reads as unescaped (a false positive — the safe direction), matching
        ``serve_gate_audit``'s gate-by-name honesty note.
  (iv) **Scope is the target dir + the ``_compose`` filename filter.** Run on
       ``substrate/`` to cover the scaffold composers; the detector only fires on
       literals/f-strings that contain tag shapes, so non-HTML string building is
       never flagged. NB ``substrate/research_artifact/compose.py`` is the fragment
       composer (it interpolates ALREADY-escaped fragments like ``rows`` /
       ``conflict_block``, not raw inputs) and deliberately does NOT match the
       ``_compose`` filter — interpolating a fragment there is the correct pattern,
       so a regression in that file is review-owned, not gate-owned.

The complementary *runtime* escape happens in ``render.py::_esc``; the two are
deliberately different planes (code-shape here, live-render there), mirroring the
serve-governance tripwire's relationship to the data-plane corpus audit.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# Escaper allow-list — matches the render.py::_esc convention (html.escape +
# the named helpers present in the tree). Any ``.escape`` attribute call
# (html.escape / markupsafe.escape / cgi.escape) counts.
ESCAPER_NAMES = frozenset(
    {"_esc", "_escape", "escape_html", "html_escape", "markup_escape"}
)
ESCAPER_ATTRS = frozenset({"escape"})

# An opening HTML tag anywhere in the literal text => this string builds HTML.
_OPEN_TAG = re.compile(r"(?<!<)<[a-zA-Z][\w-]*")
# An unclosed open tag in the tail of `before` => the hole is in ATTRIBUTE
# context (data-x="{var}"). `<tag ...` with no closing `>` before the hole.
_OPEN_TAG_UNCLOSED = re.compile(r"(?<!<)<[a-zA-Z][\w-]*[^<>]*$")
@dataclass(frozen=True)
class Finding:
    """A single unescaped interpolation into an HTML literal."""

    path: str
    lineno: int
    col: int
    context: str  # "attribute" | "content" | "attribute/content"
    expr: str
    near: str

    def render(self) -> str:
        return (
            f"{self.path}:{self.lineno}:{self.col}: compose-XSS — unescaped "
            f"{{value}} interpolated into HTML {self.context} context. Wrap it "
            f"in html.escape(...) / _esc(...) (render.py convention). "
            f"expr=`{self.expr}` near=`{self.near}`"
        )


# --------------------------------------------------------------------------- #
# Escaper recognition
# --------------------------------------------------------------------------- #


def _is_escaped(node: ast.AST) -> bool:
    """True iff ``node`` is a direct call to an allowlisted escaper."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in ESCAPER_ATTRS
    if isinstance(func, ast.Name):
        return func.id in ESCAPER_NAMES
    return False


def _unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover — ast.unparse is total for valid AST
        return "<expr>"


def _snippet(before: str, after: str, span: int = 48) -> str:
    b = before[-span:] if before else ""
    a = after[:span] if after else ""
    return f"{b}{{value}}{a}".strip()


# --------------------------------------------------------------------------- #
# f-strings (ast.JoinedStr)
# --------------------------------------------------------------------------- #


def _joined_str_findings(jstr: ast.JoinedStr, path: str) -> list[Finding]:
    # Reconstruct ordered literal segments, keeping hole positions as "".
    segs: list[str] = []
    holes: list[tuple[int, ast.FormattedValue]] = []
    for idx, val in enumerate(jstr.values):
        if isinstance(val, ast.FormattedValue):
            holes.append((idx, val))
            segs.append("")
        elif isinstance(val, ast.Constant) and isinstance(val.value, str):
            segs.append(val.value)
        else:
            segs.append("")

    if not _OPEN_TAG.search("".join(segs)):
        return []  # not HTML-building

    def before(i: int) -> str:
        return "".join(segs[j] for j in range(i))

    def after(i: int) -> str:
        return "".join(segs[j] for j in range(i + 1, len(segs)))

    out: list[Finding] = []
    for idx, fv in holes:
        if _is_escaped(fv.value):
            continue
        b, a = before(idx), after(idx)
        # In an HTML-building f-string an unescaped hole is either inside an
        # open tag (attribute) or in element text (content). There is no third
        # "safe" position — escape everything you interpolate into HTML (the
        # render.py::_esc discipline). This also catches trailing content after
        # a closing tag, e.g. f"<p>static</p>{user_input}" (harden finding).
        attr_ctx = bool(_OPEN_TAG_UNCLOSED.search(b))
        ctx = "attribute" if attr_ctx else "content"
        out.append(
            Finding(path, fv.lineno, fv.col_offset, ctx, _unparse(fv.value), _snippet(b, a))
        )
    return out


# --------------------------------------------------------------------------- #
# str.format — "<tag>{}</tag>".format(value)
# --------------------------------------------------------------------------- #


_FMT_FIELD = re.compile(r"\{[^}]*\}")


def _format_call_findings(call: ast.Call, path: str) -> list[Finding]:
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr == "format"):
        return []
    recv = func.value
    if not (isinstance(recv, ast.Constant) and isinstance(recv.value, str)):
        return []
    tmpl = recv.value
    if not _OPEN_TAG.search(tmpl) or not _FMT_FIELD.search(tmpl):
        return []
    # Conservative: any positional/kw filler that is not a direct escaper call
    # is a potential unescaped value flowing into an HTML template. Safe
    # direction (a fully-escaped template is vanishingly rare in practice).
    fillers: list[ast.expr] = list(call.args) + [
        kw.value for kw in call.keywords
    ]
    for arg in fillers:
        if not _is_escaped(arg):
            return [
                Finding(
                    path,
                    call.lineno,
                    call.col_offset,
                    "format-template",
                    _unparse(arg),
                    tmpl[:80],
                )
            ]
    return []


# --------------------------------------------------------------------------- #
# %-formatting — "<tag>%s</tag>" % value
# --------------------------------------------------------------------------- #

_PERCENT_FIELD = re.compile(r"%[srdif]")


def _percent_findings(binop: ast.BinOp, path: str) -> list[Finding]:
    if not (isinstance(binop.op, ast.Mod)):
        return []
    left = binop.left
    if not (isinstance(left, ast.Constant) and isinstance(left.value, str)):
        return []
    tmpl = left.value
    if not _OPEN_TAG.search(tmpl) or not _PERCENT_FIELD.search(tmpl):
        return []
    right = binop.right
    vals: list[ast.expr] = list(right.elts) if isinstance(right, ast.Tuple) else [right]
    for v in vals:
        if not _is_escaped(v):
            return [
                Finding(
                    path,
                    binop.lineno,
                    binop.col_offset,
                    "percent-template",
                    _unparse(v),
                    tmpl[:80],
                )
            ]
    return []


# --------------------------------------------------------------------------- #
# Concatenation — "<tag>" + value  /  value + "<tag>"  (single adjacency)
# --------------------------------------------------------------------------- #


def _flatten_add(node: ast.expr) -> list[ast.expr]:
    """Flatten a left-assoc ``+`` chain into ordered operands."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return [*_flatten_add(node.left), *_flatten_add(node.right)]
    return [node]


def _is_tag_literal(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and bool(_OPEN_TAG.search(node.value))
    )


def _joined_str_skeleton(jstr: ast.JoinedStr) -> str:
    """Literal text of an f-string with interpolation holes removed."""
    return "".join(
        v.value
        for v in jstr.values
        if isinstance(v, ast.Constant) and isinstance(v.value, str)
    )


def _is_tag_bearing(node: ast.AST) -> bool:
    """True if ``node`` produces text containing an opening HTML tag.

    Generalizes ``_is_tag_literal``: a developer who escapes the attribute and
    splits the class into ``f'<tag attr="{esc(x)}">' + raw + '</tag>'`` puts the
    opening tag inside an f-string operand (``ast.JoinedStr``), not a constant.
    Recognizing JoinedStr operands as tag-bearing is what keeps that natural
    refactoring inside the gate (harden finding, mimo heterogeneous critic).
    """
    if _is_tag_literal(node):
        return True
    if isinstance(node, ast.JoinedStr):
        return bool(_OPEN_TAG.search(_joined_str_skeleton(node)))
    return False


def _literal_text_of(node: ast.AST, *, head: bool) -> str:
    """Leading (head=True) / trailing (head=False) literal text of a tag operand."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value[:48] if head else node.value[-48:]
    if isinstance(node, ast.JoinedStr):
        skel = _joined_str_skeleton(node)
        return skel[:48] if head else skel[-48:]
    return ""


def _concat_findings(binop: ast.BinOp, path: str) -> list[Finding]:
    if not isinstance(binop.op, ast.Add):
        return []
    ops = _flatten_add(binop)
    if not any(_is_tag_bearing(o) for o in ops):
        return []  # the chain does not build HTML
    out: list[Finding] = []
    for i, op in enumerate(ops):
        # Skip literals and f-strings (their holes are handled by the JoinedStr
        # detector) and direct escaper calls; only raw VALUE operands flowing
        # into the HTML-bearing chain are flagged.
        if isinstance(op, (ast.Constant, ast.JoinedStr)) or _is_escaped(op):
            continue
        near = ""
        if i > 0 and _is_tag_bearing(ops[i - 1]):
            near = _literal_text_of(ops[i - 1], head=False)
        elif i < len(ops) - 1 and _is_tag_bearing(ops[i + 1]):
            near = _literal_text_of(ops[i + 1], head=True)
        out.append(
            Finding(path, op.lineno, op.col_offset, "content", _unparse(op), near)
        )
    return out


# --------------------------------------------------------------------------- #
# Per-file / per-tree audit
# --------------------------------------------------------------------------- #


def audit_source(source: str, path: str = "<src>") -> list[Finding]:
    """Audit a source string. Returns findings (empty = clean)."""
    tree = ast.parse(source)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            findings.extend(_joined_str_findings(node, path))
        elif isinstance(node, ast.Call):
            findings.extend(_format_call_findings(node, path))
        elif isinstance(node, ast.BinOp):
            findings.extend(_percent_findings(node, path))
            findings.extend(_concat_findings(node, path))
    # Dedup: ast.walk revisits nested BinOp/JoinedStr nodes, emitting the same
    # site from each enclosing expression. Key by location+expr+context
    # (harden finding, mimo heterogeneous critic).
    seen: set[tuple[str, int, int, str, str]] = set()
    unique: list[Finding] = []
    for f in findings:
        key = (f.path, f.lineno, f.col, f.expr, f.context)
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    return unique


def audit_file(py: Path, repo: Path) -> list[Finding]:
    try:
        rel = str(py.relative_to(repo))
    except ValueError:
        rel = str(py)
    try:
        source = py.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        return audit_source(source, rel)
    except SyntaxError:
        return []


def audit(paths: Iterable[Path], repo: Path) -> list[Finding]:
    findings: list[Finding] = []
    for base in paths:
        if base.is_file():
            # An explicit file target is audited as-is (used to test the
            # known-vulnerable PR branches whose names lack `_compose`).
            findings.extend(audit_file(base, repo))
            continue
        # Directory scans are scoped to the compose tier
        # (``*_compose*.py``) — the scaffold composers that interpolate raw
        # inputs. render.py / extractor.py use fragment composition and
        # prompt delimiters respectively and are deliberately out of scope;
        # see the module docstring's "Scope is the target dir" honesty note.
        for py in sorted(base.rglob("*.py")):
            if "_compose" not in py.name:
                continue
            findings.extend(audit_file(py, repo))
    return findings


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compose-tier HTML-escaping static gate. Fails (exit 1) when a "
            "Python module builds an HTML tag by interpolating an unescaped "
            "value (f-string / .format / % / +). See module docstring."
        )
    )
    parser.add_argument(
        "targets",
        nargs="*",
        default=["substrate"],
        help="Files/dirs to audit (default: substrate).",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Repo root for relative path display (default: cwd).",
    )
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve() if args.repo else Path.cwd().resolve()
    targets = [(repo / t if not Path(t).is_absolute() else Path(t)) for t in args.targets]
    findings = audit(targets, repo)

    if findings:
        print(
            f"compose-XSS gate: {len(findings)} unescaped HTML interpolation(s) "
            f"found (must be html.escape / _esc):"
        )
        for f in findings:
            print(f"  {f.render()}")
        return 1

    print("compose-XSS gate: OK — no unescaped HTML interpolation in compose tier.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
