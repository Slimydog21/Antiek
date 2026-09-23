"""Zero-script gate — the token layer (audit wave-3 #4/#7/#8/#9).

Each payload below was GREEN on main before the token layer existed and
is what a browser would execute or fetch. The byte-layer regexes lost
them in the gap between bytes and tokens: a ``>`` inside a quoted
attribute value, an HTML5 character reference the scheme decoder did not
know, a single-quoted/unquoted/escaped CSS context, or a meta refresh in
an attribute order the regex did not anticipate. The token layer sees
what the browser sees.

Every seeded-red case names the kind it must report, and the GREEN cases
pin that the layer adds no false positive on the prose/relative shapes
the byte layer already tolerates.
"""

from __future__ import annotations

import pytest

from services.html_projection.gate import (
    find_violations,
    is_script_free,
    normalise_css,
)
from services.html_projection.styles import (
    ProjectionStyle,
    StyleError,
    validate_style,
)


@pytest.mark.parametrize(
    ("html", "expected_kind"),
    [
        # #4 — a `>` inside a quoted attribute value ended the `<[^>]*>`
        # interior early, so everything after it was never scanned.
        ('<div title="a>b" onerror=alert(1)>x</div>', "event_handler"),
        ('<img alt="a>b" src="https://evil.example/x">', "external_img_src"),
        # #7 — character references the scheme decoder did not know.
        ('<a href="javascript&colon;alert(1)">x</a>', "javascript_href"),
        ('<a href="&#x006A;avascript:alert(1)">x</a>', "javascript_href"),
        ('<a href="&#0106;avascript:alert(1)">x</a>', "javascript_href"),
        ('<a href="&#106avascript:alert(1)">x</a>', "javascript_href"),
        # #8 — CSS contexts the byte layer did not collect, and fetch
        # tokens it matched only literally.
        ("<div style='background:url(https://evil.example/x)'>x</div>", "external_css_src"),
        ("<div style=background:url(//evil.example/x)>x</div>", "external_css_src"),
        ("<style>body{background:u\\72l(https://evil.example/x)}</style>", "external_css_src"),
        ("<style>@\\69mport \"https://evil.example/x\";</style>", "external_css_src"),
        ('<style>body{background:image-set("https://evil.example/x" 1x)}</style>', "external_css_src"),
        ("<style>body{background:u/**/rl(https://evil.example/x)}</style>", "external_css_src"),
        ("<style>body{background:url(https://evil.example/x)}", "external_css_src"),
        # #9 — declarative refresh: any attribute order, no `url=`, quotes.
        ('<meta content="0;url=https://evil.example/" http-equiv="refresh">', "external_nav_redirect"),
        ('<meta http-equiv="refresh" content="0; https://evil.example/">', "external_nav_redirect"),
        ("<meta http-equiv=\"refresh\" content=\"0;url='https://evil.example/'\">", "external_nav_redirect"),
        # URL-parser normalisation the byte layer never applied.
        ('<img src="https:\\\\evil.example\\x">', "external_img_src"),
        ('<input type=image src="https://evil.example/x">', "external_img_src"),
    ],
)
def test_token_layer_reds_what_the_byte_layer_missed(html: str, expected_kind: str) -> None:
    kinds = [v.kind for v in find_violations(html)]
    assert expected_kind in kinds, f"{html!r} -> {kinds}"


@pytest.mark.parametrize(
    "html",
    [
        '<a href="https://example.com">external cite</a>',
        '<meta http-equiv="refresh" content="0;url=/internal">',
        '<img src="data:image/png;base64,AAAA">',
        '<img srcset="/a.png 1x, /b.png 2x">',
        "<div style='background:url(/x.png)'>x</div>",
        "<p>background:url(x) is shorthand</p>",
        '<a href="/x?onsale=1&online=true">y</a>',
        '<base href="/app/">',
        "<p>javascript:alert(1) in prose</p>",
    ],
)
def test_token_layer_adds_no_false_positive(html: str) -> None:
    assert is_script_free(html), find_violations(html)


def test_token_layer_only_adds_kinds_the_byte_layer_missed() -> None:
    # A payload both layers catch reports the class ONCE, from the byte
    # layer — verdicts the byte layer already reaches are unchanged.
    kinds = [v.kind for v in find_violations("<img src=x onerror=alert(1)>")]
    assert kinds.count("event_handler") == 1


def test_normalise_css_reads_escapes_and_comments_like_an_engine() -> None:
    assert normalise_css("u\\72l(") == "url("
    assert normalise_css("@\\69mport") == "@import"
    assert normalise_css("u/**/rl(") == "url("
    assert normalise_css("URL(") == "url("


@pytest.mark.parametrize(
    "theme_css",
    [
        '</style><img alt="a>b" onerror=alert(1)><style>',
        "body{background:u\\72l(https://evil.example/x)}",
        "@\\69mport 'https://evil.example/x';",
        'body{background:image-set("https://evil.example/x" 1x)}',
    ],
)
def test_forked_style_cannot_carry_a_fetch_or_markup(theme_css: str) -> None:
    fork = ProjectionStyle(
        name="fork-x", label="Fork", description="d", theme_css=theme_css,
        builtin=False, parent="antiek",
    )
    with pytest.raises(StyleError):
        validate_style(fork)


@pytest.mark.parametrize(
    "theme_css",
    [
        # A RELATIVE url() is not an external fetch (the gate allows it) but the
        # fork policy bans every url(); the CSS escape used to walk past it.
        "body{background:u\\72l(/local.png)}",
        # Closing the wrapper element plants markup; a <p> is harmless to the
        # gate, so only the </style ban rejects it.
        "</style><p>planted</p><style>",
    ],
)
def test_fork_denylist_reads_css_like_an_engine(theme_css: str) -> None:
    # Control: the gate alone lets these through — the denylist is the gate.
    assert not find_violations(f"<style>\n{theme_css}</style>"), theme_css
    fork = ProjectionStyle(
        name="fork-y", label="Fork", description="d", theme_css=theme_css,
        builtin=False, parent="antiek",
    )
    with pytest.raises(StyleError):
        validate_style(fork)


def test_benign_fork_still_validates() -> None:
    fork = ProjectionStyle(
        name="fork-ok", label="Fork", description="d",
        theme_css="body{color:#333;font-family:serif}", builtin=False, parent="antiek",
    )
    validate_style(fork)
