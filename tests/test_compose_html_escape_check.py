"""Red-proof tests for the compose-tier HTML-escaping static gate.

The load-bearing assertion is the NEGATIVE CONTROL (the serve_gate_audit
convention): a detector that is green on the clean tree but can't red an
injected leak proves nothing. So we construct each member of the recurring
class — f-string attribute, f-string content, ``.format``, ``%``,
concatenation — and observe the flag, then assert the real tree is clean and
that escaped / safe patterns are NOT flagged.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from tools.compose_html_escape_check import (  # noqa: E402
    audit,
    audit_source,
    main,
)

# ── NEGATIVE CONTROL: every member of the class MUST be flagged ──────────────

_FSTRING_ATTR = '''
def section(parent, excerpt):
    return f'<section data-parent="{parent}">{excerpt}</section>'
'''

_FSTRING_CONTENT = '''
def article(base_draft_html):
    return f"<article>{base_draft_html}</article>"
'''

_FORMAT = '''
def link(url, label):
    return '<a href="{}">{}</a>'.format(url, label)
'''

_PERCENT = '''
def bold(body):
    return "<b>%s</b>" % body
'''

_CONCAT = '''
def wrap(body):
    return "<section>" + body + "</section>"
'''


@pytest.mark.parametrize(
    ("source", "ctx_fragment"),
    [
        (_FSTRING_ATTR, "attribute"),
        (_FSTRING_CONTENT, "content"),
        (_FORMAT, "format"),
        (_PERCENT, "percent"),
        (_CONCAT, "content"),
    ],
)
def test_injected_leak_is_flagged(source: str, ctx_fragment: str) -> None:
    findings = audit_source(source, path="leak.py")
    assert findings, f"expected a finding for {ctx_fragment!r} leak"
    assert any(ctx_fragment in f.context for f in findings), (
        f"expected context to mention {ctx_fragment!r}; got {[f.context for f in findings]}"
    )


def test_attribute_and_content_both_reported() -> None:
    # The exact #962 shape: one f-string, two holes (attr + content).
    findings = audit_source(
        'f\'<section data-parent="{parent}">{excerpt}</section>\'', path="x.py"
    )
    contexts = {f.context for f in findings}
    assert "attribute" in contexts
    assert "content" in contexts


def test_base_draft_html_whole_interpolation_caught() -> None:
    # The worst #955 vector: untrusted HTML interpolated WHOLE.
    findings = audit_source(
        'f\'<section data-role="base-draft">{base_draft_html.strip()}</section>\'',
        path="x.py",
    )
    assert findings
    assert any("base_draft_html" in f.expr for f in findings)


# ── POSITIVE CONTROL: escaped values are NOT flagged ─────────────────────────

@pytest.mark.parametrize(
    "source",
    [
        "import html\nf'<p>{html.escape(excerpt)}</p>'",
        "f'<p>{_esc(excerpt)}</p>'",
        "f'<p>{markup.escape(excerpt)}</p>'",      # any .escape attribute call
        "f'<p>{escape_html(excerpt)}</p>'",        # named helper
        # escaped in attribute context too
        "f'<a href=\"{html.escape(url)}\">ok</a>'",
    ],
)
def test_escaped_values_pass(source: str) -> None:
    assert audit_source(source, path="ok.py") == []


# ── SAFE PATTERNS: non-interpolation / non-HTML MUST NOT be flagged ──────────

@pytest.mark.parametrize(
    "source",
    [
        'x = "<div class=card>static</div>"',          # plain literal, no hole
        'x = f"total {count} items"',                 # non-HTML f-string
        # triple-angle prompt delimiter is NOT an HTML tag
        'prompt = f"""Document id: {document_id}\\n<<<INPUT>>>\\n{raw_text}\\n<<<END INPUT>>>"""',
        'x = "a < b and c > d"',                      # comparison, not a tag
    ],
)
def test_safe_patterns_not_flagged(source: str) -> None:
    assert audit_source(source, path="safe.py") == [], (
        f"false positive on safe pattern: {source!r}"
    )


# ── KEYSTONE: the real main-tip compose tier is clean ────────────────────────

def test_real_compose_tier_is_clean() -> None:
    """The gate must be green on the real tree (the class is confined to open
    PR branches #962/#955, which are not on main). A regression here means
    either a new leak landed on main OR the detector gained a false positive."""
    substrate = Path(_REPO) / "substrate"
    findings = audit([substrate], Path(_REPO))
    # Show what would fail, do not just assert emptily.
    rendered = "\n".join(f.render() for f in findings) or "(none)"
    assert findings == [], f"unexpected findings on main-tip compose tier:\n{rendered}"


# ── EXIT-CONTRACT + scope: CLI returns 0 clean / 1 on a leak; compose-scope ──

def test_cli_exit_code_clean(tmp_path: Path) -> None:
    (tmp_path / "good_compose.py").write_text(
        "import html\n"
        "def s(p, e):\n    return f'<section data-parent=\"{html.escape(p)}\">{html.escape(e)}</section>'\n",
        encoding="utf-8",
    )
    assert main([str(tmp_path), "--repo", str(tmp_path)]) == 0


def test_cli_exit_code_leak(tmp_path: Path) -> None:
    (tmp_path / "leak_compose.py").write_text(
        "def s(parent):\n    return f'<section data-parent=\"{parent}\"></section>'\n",
        encoding="utf-8",
    )
    assert main([str(tmp_path), "--repo", str(tmp_path)]) == 1


def test_directory_scan_is_compose_scoped(tmp_path: Path) -> None:
    """A non-compose file with the pattern is NOT audited on a directory scan
    (out-of-tier fragment composition / prompt templates); an explicit file
    target IS audited regardless of name."""
    (tmp_path / "render.py").write_text(   # name lacks `_compose` → skipped on dir scan
        "def r(x):\n    return f'<p>{x}</p>'\n", encoding="utf-8"
    )
    assert audit([tmp_path], tmp_path) == []          # dir scan skips it
    # explicit file target → audited
    assert audit([tmp_path / "render.py"], tmp_path) != []


def test_main_default_target_is_substrate() -> None:
    # The default target is `substrate`; on the real tree it is clean → exit 0.
    assert main(["--repo", _REPO]) == 0


# ── REGRESSION (mimo heterogeneous critic): f-string + concat bypass ─────────
# A developer who escapes the attribute and splits the class into
#   f'<tag attr="{esc(x)}">' + raw + '</tag>'
# put the opening tag inside an f-string operand. The gate must catch `raw`.


def test_fstring_concat_inline_now_caught() -> None:
    """The inline (single-expression) refactoring of the class is flagged."""
    src = (
        "import html\n"
        "def r(parent, excerpt):\n"
        "    return f'<section data-parent=\"{html.escape(parent)}\">' + excerpt + \"</section>\"\n"
    )
    findings = audit_source(src, path="t.py")
    assert findings
    assert any(f.expr == "excerpt" for f in findings), (
        f"raw `excerpt` concatenated after an escaped-attr f-string must be flagged; "
        f"got {[f.expr for f in findings]}"
    )


def test_fstring_concat_escaped_content_passes() -> None:
    """Escaped content concatenated into an HTML-bearing chain is clean."""
    src = (
        "import html\n"
        "def r(parent, excerpt):\n"
        "    return f'<section data-parent=\"{html.escape(parent)}\">' + html.escape(excerpt) + \"</section>\"\n"
    )
    assert audit_source(src, path="t.py") == []


def test_concat_findings_deduplicated() -> None:
    """A `+` chain emits each unescaped site exactly once (ast.walk revisits
    nested BinOps; findings are deduped by location+expr+context)."""
    src = 'x = "<div>" + a + "<br>" + b + "</div>"'
    findings = audit_source(src, path="t.py")
    keys = [(f.lineno, f.col, f.expr) for f in findings]
    assert sorted(keys) == sorted(set(keys)), f"duplicate findings: {keys}"
    assert {f.expr for f in findings} == {"a", "b"}


def test_known_limit_cross_statement_concat() -> None:
    """Documented data-flow limit (NOT a false negative we hide): when an
    HTML-bearing f-string is assigned to a VARIABLE and a raw value is
    concatenated with that variable later, the tag is hidden behind the name
    and catching it needs intraprocedural SSA (v2). This test LOCKS the current
    behavior so the limit is visible; a v2 that adds the data-flow pass must
    flip it to flagged and remove this note."""
    src = (
        "import html\n"
        "def r(parent, excerpt):\n"
        "    header = f'<section data-parent=\"{html.escape(parent)}\">'\n"
        "    return header + excerpt + \"</section>\"\n"
    )
    assert audit_source(src, path="t.py") == [], (
        "if this flips non-empty, a data-flow pass landed — update honest-limit (i)"
    )


def test_trailing_content_after_closing_tag_flagged() -> None:
    """A content hole that follows a CLOSING tag (no following `<`) is still
    content — must be flagged. Tightened after mimo edge-case exploration found
    f'<div>{x}</div>{x}' flagged only the first hole."""
    # natural single-trailing pattern
    fs = audit_source('f"<p>static</p>{user_input}"', path="t.py")
    assert fs and fs[0].expr == "user_input"
    # same var twice, both positions
    two = audit_source("f'<div>{x}</div>{x}'", path="t.py")
    assert len(two) == 2, f"expected both holes flagged; got {len(two)}"
    # escaped trailing is clean
    assert audit_source("import html\nf'<p>s</p>{html.escape(z)}'", path="t.py") == []


def test_every_unescaped_hole_in_html_fstring_flagged() -> None:
    """Hard-to-vary rule: in an HTML-building f-string there is no 'safe'
    unescaped hole — escape everything (attribute OR content)."""
    src = 'f\'<a href="{url}" title="{title}">{label}</a>\''
    fs = audit_source(src, path="t.py")
    assert {f.expr for f in fs} == {"url", "title", "label"}
    assert {f.context for f in fs} == {"attribute", "content"}
