"""Forkable projection styles — the style-wheel backend (v1 foundation).

Asserts the load-bearing invariants:
  - style is PURE presentation: the round-trip extract_island(render(d, style)) == d
    holds for EVERY builtin style (styling never touches the data island);
  - every builtin style renders to script-free, gate-passing HTML;
  - a style actually changes the inlined <style> block;
  - restyle_artifact regenerates an existing artifact in a new style with NO model
    call and preserves the doc-model;
  - the registry validates user forks (rejecting script / external-asset CSS),
    refuses to override or remove builtins, and lists in deterministic wheel order.
"""

from __future__ import annotations

import pytest

from services.html_projection import (
    BUILTIN_STYLES,
    ProjectionStyle,
    StyleError,
    default_registry,
    extract_island,
    render,
    resolve_style,
    restyle_artifact,
    validate_style,
)
from services.html_projection.gate import find_violations
from services.html_projection.tests.fixtures.golden import golden_corpus

_STYLE_NAMES = [s.name for s in BUILTIN_STYLES]


def _sample_doc() -> dict:
    # A doc-model rich enough to exercise title + edges + blocks in the island.
    for doc in golden_corpus():
        if doc.get("content"):
            return doc
    return golden_corpus()[0]


@pytest.mark.parametrize("style_name", _STYLE_NAMES)
def test_roundtrip_holds_for_every_style(ctx, style_name):
    """Styling is pure presentation: the doc-model recovered from the island is
    identical no matter which style rendered it."""
    doc = _sample_doc()
    html = render(doc, ctx, style=style_name)
    assert extract_island(html) == doc


@pytest.mark.parametrize("style_name", _STYLE_NAMES)
def test_every_builtin_style_is_script_free(ctx, style_name):
    """Every builtin style renders to gate-passing (zero-script) HTML."""
    html = render(_sample_doc(), ctx, style=style_name)
    assert find_violations(html) == []


def test_default_style_matches_no_style(ctx):
    """style=None and style='antiek' produce byte-identical output (the default)."""
    doc = _sample_doc()
    assert render(doc, ctx) == render(doc, ctx, style="antiek")


def test_style_changes_the_stylesheet(ctx):
    """A source-fidelity style visibly changes the inlined stylesheet vs default."""
    doc = _sample_doc()
    default_html = render(doc, ctx, style="antiek")
    book_html = render(doc, ctx, style="book")
    assert default_html != book_html
    assert "antiek-style:book" in book_html
    # but the body/island is unchanged — only presentation differs
    assert extract_island(default_html) == extract_island(book_html)


def test_restyle_artifact_regenerates_without_model(ctx):
    """restyle_artifact recovers the doc-model from an artifact and re-projects it
    in a new style — deterministically, no model call — preserving the doc-model."""
    doc = _sample_doc()
    original = render(doc, ctx, style="antiek")
    restyled = restyle_artifact(original, ctx, style="academic-paper")
    assert extract_island(restyled) == doc
    assert "antiek-style:academic-paper" in restyled
    # Idempotent/deterministic: restyling again yields identical bytes.
    assert restyle_artifact(original, ctx, style="academic-paper") == restyled


def test_registry_lists_builtins_in_order():
    reg = default_registry()
    assert reg.names() == _STYLE_NAMES
    assert reg.get("antiek").label == "Antiek"


def test_register_user_fork_and_use(ctx):
    reg = default_registry()
    fork = ProjectionStyle(
        name="my-serif",
        label="My Serif",
        description="a personal fork",
        theme_css=".antiek-doc { font-family: Georgia, serif; }",
        source_fidelity=True,
        builtin=False,
    )
    reg.register(fork)
    assert reg.has("my-serif")
    html = render(_sample_doc(), ctx, style=resolve_style("my-serif", registry=reg))
    assert find_violations(html) == []
    assert "My Serif".lower() not in html  # label isn't leaked into CSS
    reg.remove("my-serif")
    assert not reg.has("my-serif")


def test_cannot_override_or_remove_builtin():
    reg = default_registry()
    with pytest.raises(StyleError, match="builtin"):
        reg.register(
            ProjectionStyle(name="antiek", label="hijack", description="x", builtin=False)
        )
    with pytest.raises(StyleError, match="builtin"):
        reg.remove("antiek")


@pytest.mark.parametrize(
    "bad_css",
    [
        "@import url('http://evil.example/x.css');",
        ".x { background: url('http://evil.example/tracker.gif'); }",
        ".x { width: expression(alert(1)); }",
        ".x { behavior: url(#default#time2); }",
        ".x { background: javascript:alert(1); }",
    ],
)
def test_validate_rejects_unsafe_css(bad_css):
    style = ProjectionStyle(
        name="evil", label="Evil", description="x", theme_css=bad_css, builtin=False
    )
    with pytest.raises(StyleError):
        validate_style(style)


def test_validate_rejects_bad_slug():
    with pytest.raises(StyleError, match="slug"):
        validate_style(
            ProjectionStyle(name="Bad Slug!", label="x", description="x", builtin=False)
        )


def test_registry_register_runs_validation():
    reg = default_registry()
    with pytest.raises(StyleError):
        reg.register(
            ProjectionStyle(
                name="sneaky",
                label="Sneaky",
                description="x",
                theme_css="@import url('http://evil.example/x.css');",
                builtin=False,
            )
        )
    assert not reg.has("sneaky")
