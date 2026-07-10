"""Book-import SPR-01 — allowlist sanitizer + trusted-HTML contract tests.

The red-proof discipline this file enforces (parent spec, anti-stub-theater):

1. Every attack payload is first proven DANGEROUS in its raw form
   (``test_red_proof_raw_payloads_are_dangerous``) — i.e. a pass-through
   "sanitizer" provably FAILS this suite, so a green run means the sanitizer
   did real work, not that the assertions were vacuous.
2. The sanitized output is then proven inert against the same predicate AND
   against a re-parse auditor that walks the output with a real HTML parser
   and asserts every surviving tag/attribute/URL is allowlisted — a stronger
   property than substring absence.
"""

from __future__ import annotations

import html as html_mod
from collections.abc import Callable
from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest

from substrate.books.html_sanitizer import (
    ALLOWED_TAGS,
    CONTENT_SANITIZED_KEY,
    SANITIZER_VERSION,
    SANITIZER_VERSION_KEY,
    is_trusted_sanitized,
    sanitize_book_html,
    sanitized_html_provenance,
)

# ---------------------------------------------------------------------------
# The attack corpus. Each entry is a payload that would be dangerous if it
# reached a browser (or a talk-to-book grounding) unsanitized.
# ---------------------------------------------------------------------------

ATTACK_PAYLOADS: dict[str, str] = {
    "bare_script": '<p>hi</p><script>window.__x = 1</script>',
    "nested_mutation_script": "<scr<script>ipt>alert(1)</script>",
    "img_onerror": '<img src="x" onerror="fetch(\'/api/steal\')">',
    "onclick_handler": '<p onclick="alert(1)">click me</p>',
    "onload_body": '<body onload="alert(1)"><p>text</p></body>',
    "javascript_href": '<a href="javascript:alert(1)">go</a>',
    "javascript_href_tab_split": '<a href="jav\tascript:alert(1)">go</a>',
    "javascript_href_entity": '<a href="javascript&colon;alert(1)">go</a>',
    "vbscript_href": '<a href="vbscript:msgbox(1)">go</a>',
    "data_url_script": '<a href="data:text/html,<script>alert(1)</script>">x</a>',
    "iframe": '<iframe src="https://evil.example/"></iframe>',
    "object_embed": '<object data="x"></object><embed src="x">',
    "svg_onload": '<svg onload="alert(1)"><circle r="1"/></svg>',
    "math_href": '<math><maction actiontype="statusline#javascript:alert(1)">x</maction></math>',
    "style_expression_attr": '<p style="width: expression(alert(1))">text</p>',
    "style_url_javascript": '<p style="background:url(javascript:alert(1))">text</p>',
    "style_block": "<style>p { background: url(javascript:alert(1)) }</style><p>t</p>",
    "template_smuggle": "<template><script>alert(1)</script></template>",
    "noscript_smuggle": "<noscript><p onmouseover=alert(1)>x</p></noscript>",
    "formaction": '<button formaction="javascript:alert(1)">x</button>',
    "meta_refresh": '<meta http-equiv="refresh" content="0;url=javascript:alert(1)">',
    "base_hijack": '<base href="https://evil.example/">',
    "comment_conditional": "<!--[if IE]><script>alert(1)</script><![endif]--><p>t</p>",
}


def _strip_controls(text: str) -> str:
    """Strip the whitespace/control characters browsers ignore when sniffing
    schemes and tag names; lowercase for matching."""
    out = []
    for ch in text.lower():
        if ch in "\t\n\r\x0b\x0c" or ord(ch) < 0x20:
            continue
        out.append(ch)
    return "".join(out)


# Markup-level dangers must appear as RAW markup to be dangerous — a browser
# parses HTML once, so escaped text like ``&lt;script&gt;`` in prose is inert
# and must NOT be flagged.
_MARKUP_MARKS = (
    "<script",
    "<iframe",
    "<object",
    "<embed",
    "<svg",
    "<template",
    "<style",
    "<meta",
    "<base",
    "onerror=",
    "onclick=",
    "onload=",
    "onmouseover=",
    "formaction=",
    "expression(",
    "url(javascript",
    "style=",
)

# Scheme-level dangers live in attribute VALUES, where a browser decodes
# entities (``javascript&colon;`` executes) — so these are matched against the
# entity-decoded text as well as the raw text.
_SCHEME_MARKS = ("javascript:", "vbscript:", "data:text/html")


def _looks_dangerous(html_text: str) -> bool:
    raw = _strip_controls(html_text)
    decoded = _strip_controls(html_mod.unescape(html_text))
    if any(mark in raw for mark in _MARKUP_MARKS):
        return True
    return any(mark in decoded for mark in _SCHEME_MARKS)


# ---------------------------------------------------------------------------
# Red-proof: the corpus IS dangerous raw, so a pass-through sanitizer fails.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(ATTACK_PAYLOADS))
def test_red_proof_raw_payloads_are_dangerous(name: str) -> None:
    """Prove the suite bites: every raw payload trips the danger predicate,
    so an identity/pass-through sanitize_book_html would fail the inertness
    tests below on every one of these inputs."""
    assert _looks_dangerous(ATTACK_PAYLOADS[name]), (
        f"attack payload {name!r} no longer trips the danger predicate — "
        "the inertness assertions below would be vacuous for it"
    )


def test_red_proof_pass_through_sanitizer_would_fail() -> None:
    """The explicit both-directions check: substituting the identity function
    for the sanitizer leaves every payload dangerous."""
    identity: Callable[[str], str] = lambda x: x  # noqa: E731 — the counterfactual
    assert all(_looks_dangerous(identity(p)) for p in ATTACK_PAYLOADS.values())


# ---------------------------------------------------------------------------
# Inertness: sanitized output defeats every payload.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(ATTACK_PAYLOADS))
def test_sanitized_payloads_are_inert(name: str) -> None:
    cleaned = sanitize_book_html(ATTACK_PAYLOADS[name])
    assert not _looks_dangerous(cleaned), (
        f"payload {name!r} survived sanitization: {cleaned!r}"
    )


def test_script_content_does_not_leak_as_text() -> None:
    """Dropping <script> but keeping its text would still poison talk-to-book
    grounding (prompt-injection) — the content must go with the tag."""
    cleaned = sanitize_book_html("<p>keep</p><script>SECRET_JS_BODY</script>")
    assert "SECRET_JS_BODY" not in cleaned
    assert "keep" in cleaned


def test_style_block_content_dropped() -> None:
    cleaned = sanitize_book_html("<style>CSS_BODY</style><p>keep</p>")
    assert "CSS_BODY" not in cleaned
    assert "keep" in cleaned


# ---------------------------------------------------------------------------
# Re-parse auditor: every surviving tag / attribute / URL is allowlisted.
# ---------------------------------------------------------------------------


class _Auditor(HTMLParser):
    """Walks sanitizer output and records anything outside the allowlist."""

    _URL_ATTRS = {"href", "src"}
    _ATTR_ALLOW = {
        "id", "title", "lang", "dir", "href", "src", "alt",
        "width", "height", "colspan", "rowspan", "scope", "start",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.violations: list[str] = []

    def _check(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ALLOWED_TAGS:
            self.violations.append(f"tag:{tag}")
        for name, value in attrs:
            lname = name.lower()
            if lname not in self._ATTR_ALLOW or lname.startswith("on"):
                self.violations.append(f"attr:{tag}.{lname}")
            if lname in self._URL_ATTRS and value:
                scheme = urlsplit(value).scheme.lower()
                if scheme not in ("", "http", "https"):
                    self.violations.append(f"url:{tag}.{lname}={value}")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._check(tag.lower(), attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._check(tag.lower(), attrs)


def _audit(html_text: str) -> list[str]:
    auditor = _Auditor()
    auditor.feed(html_text)
    auditor.close()
    return auditor.violations


@pytest.mark.parametrize("name", sorted(ATTACK_PAYLOADS))
def test_reparse_audit_of_sanitized_output(name: str) -> None:
    assert _audit(sanitize_book_html(ATTACK_PAYLOADS[name])) == []


def test_reparse_audit_bites_on_raw_input() -> None:
    """Counterfactual for the auditor itself: raw payloads DO violate it."""
    violating = [n for n, p in ATTACK_PAYLOADS.items() if _audit(p)]
    # Not every payload parses into a visible violation pre-sanitize (some are
    # pure-text mutations), but the overwhelming majority must.
    assert len(violating) >= len(ATTACK_PAYLOADS) - 3


# ---------------------------------------------------------------------------
# Benign structure preservation — the sanitizer must not lobotomize a book.
# ---------------------------------------------------------------------------

_BENIGN_BOOK = """
<section id="ch1">
  <h1 id="chapter-one">Chapter One</h1>
  <p>It was the best of <em>times</em>, it was the worst of <strong>times</strong>.</p>
  <ul><li>first</li><li>second</li></ul>
  <blockquote><p>A quoted passage.</p></blockquote>
  <pre><code>x = 1 &lt; 2</code></pre>
  <table><tr><th colspan="2">head</th></tr><tr><td>a</td><td>b</td></tr></table>
  <p>See <a href="#chapter-two">the next chapter</a> and
     <a href="https://example.org/notes">the notes</a>.</p>
  <img src="https://example.org/cover.png" alt="the cover" width="120" height="80" />
  <img src="images/figure1.png" alt="relative figure" />
</section>
"""


def test_benign_structure_preserved() -> None:
    cleaned = sanitize_book_html(_BENIGN_BOOK)
    for fragment in (
        '<section id="ch1">',
        '<h1 id="chapter-one">',
        "<em>times</em>",
        "<strong>times</strong>",
        "<li>first</li>",
        "<blockquote>",
        "<pre><code>",
        '<th colspan="2">',
        '<a href="#chapter-two">',
        '<a href="https://example.org/notes">',
        '<img src="https://example.org/cover.png" alt="the cover" width="120" height="80" />',
        '<img src="images/figure1.png" alt="relative figure" />',
    ):
        assert fragment in cleaned, f"benign fragment lost: {fragment!r}"
    assert _audit(cleaned) == []


def test_text_escaping_preserved_and_stable() -> None:
    cleaned = sanitize_book_html("<p>a &lt; b &amp; c &gt; d</p>")
    assert cleaned == "<p>a &lt; b &amp; c &gt; d</p>"


def test_unknown_tags_dropped_children_kept() -> None:
    cleaned = sanitize_book_html("<custom-widget><p>inner text</p></custom-widget>")
    assert "custom-widget" not in cleaned
    assert "<p>inner text</p>" in cleaned


def test_truncated_input_is_closed() -> None:
    cleaned = sanitize_book_html("<blockquote><p>never closed")
    assert cleaned.endswith("</p></blockquote>")


def test_unsafe_id_and_numeric_attrs_dropped() -> None:
    cleaned = sanitize_book_html(
        '<p id="1) bad id {}">x</p><td colspan="2; DROP TABLE">y</td>'
    )
    assert "bad id" not in cleaned
    assert "DROP TABLE" not in cleaned
    assert "<p>x</p>" in cleaned


# ---------------------------------------------------------------------------
# Determinism + idempotence — document/chunk content-addressing depends on it.
# ---------------------------------------------------------------------------


def test_deterministic() -> None:
    for payload in (*ATTACK_PAYLOADS.values(), _BENIGN_BOOK):
        assert sanitize_book_html(payload) == sanitize_book_html(payload)


def test_idempotent() -> None:
    for payload in (*ATTACK_PAYLOADS.values(), _BENIGN_BOOK):
        once = sanitize_book_html(payload)
        assert sanitize_book_html(once) == once, f"not a fixed point for {payload!r}"


# ---------------------------------------------------------------------------
# The trusted-HTML provenance contract.
# ---------------------------------------------------------------------------


def test_provenance_stamp_shape() -> None:
    stamp = sanitized_html_provenance()
    assert stamp[CONTENT_SANITIZED_KEY] is True
    assert stamp[SANITIZER_VERSION_KEY] == SANITIZER_VERSION
    assert SANITIZER_VERSION  # non-empty, pinned


def test_trusted_predicate_accepts_stamped_metadata() -> None:
    assert is_trusted_sanitized(sanitized_html_provenance())
    # As stored: documents.metadata round-trips through JSON.
    import json

    assert is_trusted_sanitized(json.dumps({"other": 1, **sanitized_html_provenance()}))


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        "",
        "not json",
        "[1, 2]",
        "{}",
        {"content_sanitized": False, "content_sanitizer_version": "x"},
        {"content_sanitized": "true", "content_sanitizer_version": "x"},
        {"content_sanitized": True},  # no version → not auditable → untrusted
        {"content_sanitized": True, "content_sanitizer_version": ""},
        {"content_sanitizer_version": SANITIZER_VERSION},
    ],
)
def test_trusted_predicate_denies_by_default(metadata: object) -> None:
    assert not is_trusted_sanitized(metadata)  # type: ignore[arg-type]


def test_trusted_predicate_accepts_older_versions() -> None:
    """A version bump must not brick previously sanitized rows; the pinned
    version exists for audit, not as an equality gate."""
    assert is_trusted_sanitized(
        {CONTENT_SANITIZED_KEY: True, SANITIZER_VERSION_KEY: "books-allowlist/0.9.0"}
    )
