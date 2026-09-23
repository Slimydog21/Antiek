"""Zero-script gate (HPRJ SPR-02 / M4).

Asserts a projection contains NO executable script. The master-spec
SCRIPT-FREE invariant (Key invariant 1) is absolute: the §7 continuous-
research daemon ingests artifacts autonomously, so a script in an artifact
is an RCE vector. This gate is the mechanical backstop — it runs on every
projection (M4) AND is reused on the ingest side in SPR-07, so it is
STDLIB-ONLY (no third-party deps; an HTML parser dependency here would
become an ingest-side dependency there).

The gate catches EACH class of script violation, not just ``<script>``.
A gate that only matches ``<script>`` is rubber-stamping: an attacker (or
a careless partial) can ship executable bytes via uppercase tags, event-
handler attributes, ``javascript:`` hrefs, or external ``<img src>`` that
exfiltrates or fetches code. Each class has a dedicated check + a seeded-
red test (M4). The gate is GREEN on the full golden corpus (the renderer
never emits any of these) and RED on each seeded violation.

WHY REGEX AND NOT AN HTML PARSER: an HTML parser normalises (lowercases
tags, reorders attributes, drops malformed constructs), which is exactly
what an evasion relies on. The gate must catch the BYTES as they appear
in the artifact, case-insensitively and whitespace-tolerantly, without
"helpfully" reinterpreting them. A regex over the raw string, case-folded
with whitespace collapsed around the structural tokens, catches the
evasion tricks a parser would paper over. This is the standard approach
for script-detection gates (it is what CSP-reporting scanners and email-
sanitiser pre-filters do). The tradeoff — false positives on the literal
word "script" in prose — is handled by scoping each check to the
syntactic position where the byte-sequence is dangerous (a ``<script``
tag open, an ``on...=`` attribute, a ``javascript:`` scheme), not the
bare word.

DETERMINISM: the gate is a pure function of its input string. No wall-
clock, no I/O. The same HTML always yields the same verdict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser


class ScriptViolation(Exception):
    """Raised by ``assert_script_free`` when a projection contains
    executable script. The offending class + a sample match is on the
    instance for diagnostics."""

    def __init__(self, violations: list[Violation]) -> None:
        self.violations = violations
        summary = "; ".join(
            f"{v.kind}: {v.match!r}" for v in violations
        )
        super().__init__(
            f"assert_script_free: {len(violations)} script violation(s) "
            f"found: {summary}"
        )


@dataclass(frozen=True)
class Violation:
    """One detected script-violation class.

    Attributes
    ----------
    kind:
        The violation class (``script_tag``, ``event_handler``,
        ``javascript_href``, ``external_img_src``, ``css_expression``,
        ``external_css_src``, ``external_nav_redirect``).
    match:
        The offending byte substring (truncated for the message).
    """

    kind: str
    match: str


# ── Checks ──
#
# Each check operates on the RAW html string (not a DOM). We case-fold
# for tag/attribute/scheme matching because HTML is case-insensitive
# there. We do NOT case-fold the whole string up front for the
# ``javascript:`` check — that check needs to survive the scheme being
# split across entities/whitespace, so it runs on a whitespace-collapsed
# lowercased copy. The script-tag check matches ``<script`` followed by a
# tag-terminator (space, ``>``, ``/``, or end) so it does not false-fire
# on the prose word "script" (which is never preceded by ``<``).

# <script ...> or </script> — tag open or close, any case, with optional
# whitespace after the tag name. The ``\b``-free boundary is the ``<``
# followed by ``/``-optional ``script`` then a tag-terminator.
_SCRIPT_TAG_RE = re.compile(
    r"<\s*/?\s*script\b", re.IGNORECASE
)

# Event-handler attribute: ``on<word>=`` as an attribute. Matches
# ``onclick=``, ``on-load=``, ``ONERROR =``, etc. The ``on`` prefix + a
# word char + optional more word chars/dashes + ``=``. We require the
# ``=`` so the bare word "online" in prose (no ``=``) does not fire.
_EVENT_HANDLER_RE = re.compile(
    r"\bon[a-z0-9_-]+\s*=", re.IGNORECASE
)

# javascript:/vbscript: scheme in a URL-bearing attribute. The check is
# ATTRIBUTE-SCOPED, not bare-text, because a projection may legitimately
# contain the literal string "javascript:alert(1)" in prose (a security
# researcher's notebook documenting an XSS). The danger is the scheme
# appearing in an attribute a browser interprets as a URL: href, src,
# action, formaction, xlink:href, data (for <object>), or poster. We
# match the attribute name + = + optional quote + the scheme. Whitespace
# and a couple of common entity obfuscations are collapsed/decoded first
# (see _decode_for_scheme_check) so "java\tscript:" and "jav&#97;script:"
# in an attribute are caught. The check covers both quoted and unquoted
# attribute values.
_JS_SCHEME_RE = re.compile(
    r"(?:href|src|action|formaction|xlink:href|data|poster)\s*=\s*[\"']?\s*"
    r"(?:java\s*script|vbscript)\s*:",
    re.IGNORECASE,
)

# External img/audio/video/source/iframe src: any src= pointing at an
# http(s):// URL (or // protocol-relative). The self-contained invariant
# forbids external assets; an external src is a fetch vector (and the
# daemon ingesting the artifact would follow it). data: URIs are
# permitted (inline, self-contained) — but the renderer doesn't emit
# them either; allowing them here is forward-compat for SPR-03 widgets
# that may inline small images.
_EXTERNAL_SRC_RE = re.compile(
    r"<\s*(?:img|audio|video|source|iframe|embed|track)\b[^>]*\b(?:src|srcset)\s*=\s*"
    r"[\"']?\s*(?:https?:)?//",
    re.IGNORECASE,
)

# Dedicated srcset check: srcset is a comma/space-separated LIST of URLs
# (``"a.png 1x, b.png 2x"``), so an external entry need not be the first
# token. The broad regex above already catches a srcset whose first URL is
# external; this dedicated scan catches an external URL anywhere in a
# srcset list on img/source, which the ``[\"']?\s*``-anchored broad regex
# could miss when the first candidate is relative and a later one is
# external. It reports the same ``external_img_src`` class.
_EXTERNAL_SRCSET_RE = re.compile(
    r"<\s*(?:img|source)\b[^>]*\bsrcset\s*=\s*[\"']?\s*(?:https?:)?//",
    re.IGNORECASE,
)

# CSS expression() — dead IE RCE vector. Browsers ignore it now, but the
# gate flags it so a projection never carries the byte sequence. Scoped
# to inside a style attribute or <style> block context by requiring the
# ``expression(`` token.
_CSS_EXPRESSION_RE = re.compile(
    r"expression\s*\(", re.IGNORECASE
)

# External CSS fetch: ``@import url(...)`` or ``url(...)`` pointing at an
# http(s):// (or protocol-relative //) endpoint, inside a <style> block or
# a style="..." attribute. CSS can exfiltrate page data (attribute
# selectors + background requests) and @import fetches+executes remote
# CSS — both are external-fetch/exfiltration vectors the self-contained
# invariant forbids. Matches ``url(``, ``url (`` (lenient), and bare
# ``@import "..."``/``@import url(...)`` forms.
_EXTERNAL_CSS_URL_RE = re.compile(
    r"(?:url|@import)\s*\(?\s*[\"']?\s*(?:https?:)?//",
    re.IGNORECASE,
)

# External navigation/redirect vectors. Not scripts, but relevant to the
# autonomous-ingest RCE threat: the §7 daemon ingesting an artifact that
# redirects (meta refresh) or whose relative URLs are hijacked to an
# external origin (<base href>). The self-contained invariant forbids
# external assets; an external-nav/redirect is the same class of "the
# artifact reaches out to a remote origin at read/ingest time" threat.
# meta refresh with an external url=.
_META_REFRESH_RE = re.compile(
    r"<meta\b[^>]*http-equiv\s*=\s*[\"']?refresh"
    r"[^>]*content\s*=\s*[\"']?\s*\d+\s*;\s*url\s*=\s*(?:https?:)?//",
    re.IGNORECASE,
)
# <base href> pointing at an external origin.
_BASE_HREF_RE = re.compile(
    r"<base\b[^>]*href\s*=\s*[\"']?\s*(?:https?:)?//",
    re.IGNORECASE,
)

# Additional external-fetch vectors the self-contained invariant forbids
# (grok-style adversarial follow-up to the zero-script lens): elements
# whose URL-bearing attribute fetches remote content or navigates to an
# external origin at read/ingest time, not covered by the src/srcset,
# CSS url(), meta-refresh, or base-href checks above.
#   * <object data="https://…"> — fetches+renders remote content (classic
#     external-fetch AND code-execution vector).
#   * <link rel=stylesheet href="https://…"> — fetches+executes remote CSS
#     (same class as @import in <style>, which the gate already flags).
#   * <svg><use href="https://…"> — fetches an external SVG fragment.
#   * <form action="https://…"> / <button formaction="https://…"> —
#     navigates/submits to an external origin.
# All report ``external_nav_redirect`` (the existing "artifact reaches out
# to a remote origin" class) so callers handling that kind cover these too.
_EXTERNAL_FETCH_EXTRA_RE = re.compile(
    r"<\s*(?:object|link|svg|use|form|button)\b[^>]*\b"
    r"(?:data|href|xlink:href|action|formaction)\s*=\s*"
    r"[\"']?\s*(?:https?:)?//",
    re.IGNORECASE,
)


def _decode_for_scheme_check(s: str) -> str:
    """Lowercase + collapse whitespace + decode the two most common
    entity obfuscations of the ``javascript:`` scheme (``&#106;`` = j,
    ``&#x6a;`` = j) so the scheme check survives them. This is NOT a
    full HTML-entity decoder — it covers the obfuscations that bypass a
    naive ``javascript:`` substring match, which is the threat model."""
    s = s.lower()
    # Strip NUL + C0 control chars + whitespace inside potential scheme
    # tokens. Python's ``\s`` does NOT match the NUL byte (``\x00``) nor
    # other C0 controls, but browsers historically strip NUL from URLs
    # before scheme resolution, so ``java\x00script:`` resolves to
    # ``javascript:`` in a browser. We strip the whole C0 range (plus
    # DEL) so any raw-control-char insertion in the scheme is collapsed
    # before the scheme match.
    s = re.sub(r"[\x00-\x1f\x7f\s]+", "", s)
    # Decode numeric char refs for the letters in "javascript"/"vbscript".
    s = re.sub(r"&#(\d{1,3});", lambda m: chr(int(m.group(1))), s)
    return re.sub(r"&#x([0-9a-f]{1,2});", lambda m: chr(int(m.group(1), 16)), s)


def _tag_interiors(html: str) -> list[str]:
    """Return the interior text of every opening/closing tag in ``html``.

    A tag interior is the text between ``<`` (and an optional ``/``) and
    the closing ``>``. Scoping event-handler + attribute checks to tag
    interiors prevents false positives on prose that happens to contain
    ``onword=`` or ``javascript:`` (a security notebook documenting XSS
    is the canonical false-positive case). Text content between tags is
    NOT scanned for attributes — attributes only exist inside tags.
    """
    interiors: list[str] = []
    for m in re.finditer(r"<[^>]*>", html):
        interiors.append(m.group(0))
    return interiors


# An attribute value: quoted either way, or an unquoted run up to whitespace
# or the tag close. Used to BLANK values while leaving attribute NAMES intact.
_ATTR_VALUE_RE = re.compile(r"""=\s*(?:"[^"]*"|'[^']*'|[^\s"'>]+)""")


def _attr_names_only(tag: str) -> str:
    """A tag interior with every attribute VALUE blanked.

    Scoping the event-handler scan to tag interiors (above) stops prose from
    false-firing, but it does not stop the tag's own attribute VALUES from
    matching — and a URL is an attribute value full of ``name=value`` pairs.
    Any ingested link carrying an ``on...=`` token cleared the word boundary
    and was classified as an event handler:

        ?onsale=1        -> matched "onsale="
        ?online=true     -> matched "online="
        #section-only=2  -> matched "only="   (the dash is a word boundary)

    That is not hypothetical prose; it is an ordinary marketing URL, and
    GET /documents/{id}/render answers 500 for the whole document when one
    appears. Blanking values leaves the NAME side of every pair matchable, so
    ``onclick="x()"``, ``onclick=alert(1)``, ``ONLOAD="z()"`` and
    ``onclick ="x()"`` all still fire.
    """
    return _ATTR_VALUE_RE.sub("=", tag)


# ── Second detector: the TOKENS a browser-grade tokenizer produces ──
#
# The regex checks above scan the BYTES, on purpose (see the module
# docstring). But four evasions live exactly in the gap between bytes and
# tokens, and a browser is a tokenizer, not a regex:
#
#   * a ``>`` inside a QUOTED attribute value ends the ``<[^>]*>`` tag
#     interior early, so ``<div title="a>b" onerror=alert(1)>`` is never
#     scanned for its handler (and ``<img alt="a>b" src="https://…">``
#     never for its external src);
#   * the scheme decoder above knows ``&#NNN;`` and ``&#xHH;`` only, so
#     ``&colon;``, ``&#x006A;``, ``&#0106;`` and the semicolon-less
#     ``&#106avascript:`` all decode to ``javascript:`` in a browser and
#     to nothing here;
#   * the CSS context is collected only from a double-quoted ``style="…"``,
#     and the fetch tokens are matched literally, so a single-quoted or
#     unquoted style attribute, a CSS identifier escape (``u\72l(``,
#     ``@\69mport``) or ``image-set("https://…")`` fetch without a match;
#   * the meta-refresh regex wants ``http-equiv`` BEFORE ``content``, a
#     literal ``url=`` and an unquoted URL, while the declarative-refresh
#     algorithm accepts any order, no ``url=`` at all, and quotes.
#
# So the gate runs BOTH detectors and unions them. ``html.parser`` is
# stdlib (the SPR-07 ingest-side constraint holds), tokenizes attributes
# the way a browser does (quotes respected, every HTML5 character
# reference decoded, names case-folded) and hands ``<style>`` bodies over
# as raw CDATA. The token layer only ADDS a class the byte layer missed,
# so every verdict the byte layer already reaches is unchanged; the byte
# layer still catches the malformed-byte tricks a tokenizer would repair.

_URL_ATTRS = frozenset(
    {"href", "src", "action", "formaction", "xlink:href", "data", "poster"}
)
_MEDIA_TAGS = frozenset(
    {"img", "audio", "video", "source", "iframe", "embed", "track", "input"}
)
_FETCH_TAGS = frozenset({"object", "link", "svg", "use", "form", "button", "input"})
_FETCH_ATTRS = frozenset({"data", "href", "xlink:href", "action", "formaction"})

_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_ESCAPE_RE = re.compile(r"\\([0-9a-fA-F]{1,6})[ \t\n\r\f]?|\\(.)", re.DOTALL)
_CSS_EXTERNAL_FETCH_RE = re.compile(
    r"(?:@import|(?<![\w-])(?:url|image-set|src)\s*\()\s*\(?\s*[\"']?\s*(?:https?:)?//",
    re.IGNORECASE,
)


def normalise_css(css: str) -> str:
    """CSS as the engine reads it: comments removed, identifier escapes
    (``\\72`` -> ``r``, ``\\i`` -> ``i``) decoded, NUL dropped, lower-cased.

    Public so ``styles.validate_style`` can run its own denylist over the
    same normalised text — a denylist over raw CSS is what ``u\\72l(``
    walks past."""
    css = _CSS_COMMENT_RE.sub("", css)

    def _esc(m: re.Match[str]) -> str:
        if m.group(1):
            try:
                return chr(int(m.group(1), 16))
            except (ValueError, OverflowError):
                return ""
        return m.group(2)

    css = _CSS_ESCAPE_RE.sub(_esc, css)
    return css.replace("\x00", "").lower()


def _url_as_browser(value: str) -> str:
    """A URL the way the URL parser sees it: leading/trailing C0+space
    stripped, tab/newline removed, backslashes folded to slashes (special
    schemes), lower-cased."""
    v = value.strip("\x00\t\n\r\f\v ")
    v = re.sub(r"[\t\n\r\x00]", "", v)
    return v.replace("\\", "/").lower()


def _is_external(value: str) -> bool:
    return _url_as_browser(value).startswith(("http://", "https://", "//"))


def _is_script_scheme(value: str) -> bool:
    # Same collapse the byte layer applies (all C0 + whitespace removed),
    # on the ALREADY entity-decoded attribute value the tokenizer gives us.
    v = re.sub(r"[\x00-\x20\x7f]+", "", value).lower()
    return v.startswith(("javascript:", "vbscript:"))


def _srcset_candidates(value: str) -> list[str]:
    out: list[str] = []
    for cand in value.split(","):
        cand = cand.strip()
        if cand:
            out.append(cand.split()[0])
    return out


def _refresh_url(content: str) -> str:
    """The URL a declarative ``<meta http-equiv=refresh>`` navigates to,
    per the HTML "shared declarative refresh steps": digits/dots, then
    whitespace and an optional ``;``/``,``, then an OPTIONAL ``url=``, then
    an optionally quoted URL. Empty string when there is none."""
    s = content.lstrip("\t\n\f\r ")
    i = 0
    while i < len(s) and (s[i].isdigit() or s[i] == "."):
        i += 1
    rest = s[i:].lstrip("\t\n\f\r ")
    if rest[:1] in (";", ","):
        rest = rest[1:].lstrip("\t\n\f\r ")
    if rest[:3].lower() == "url":
        rest = rest[3:].lstrip("\t\n\f\r ")
        if rest[:1] == "=":
            rest = rest[1:].lstrip("\t\n\f\r ")
    if rest[:1] in ("'", '"'):
        quote = rest[0]
        rest = rest[1:]
        end = rest.find(quote)
        if end != -1:
            rest = rest[:end]
    return rest.strip()


class _TokenScan(HTMLParser):
    """Collect one sample per violation class from the token stream."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: dict[str, str] = {}
        self._css: list[str] = []
        self._style_buf: list[str] | None = None

    def _hit(self, kind: str, sample: str) -> None:
        self.found.setdefault(kind, _trunc(sample))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        pairs = [(name, value or "") for name, value in attrs]
        if tag == "script":
            self._hit("script_tag", f"<{tag}")
        if tag == "style":
            self._style_buf = []
        first: dict[str, str] = {}
        for name, value in pairs:
            first.setdefault(name, value)
            if name.startswith("on") and len(name) > 2:
                self._hit("event_handler", f"{name}=")
            if name in _URL_ATTRS and _is_script_scheme(value):
                self._hit("javascript_href", f"{name}={value}")
            if name == "style":
                self._css.append(value)
            if tag in _MEDIA_TAGS and name == "src" and _is_external(value):
                self._hit("external_img_src", f"<{tag} src={value}")
            if tag in _MEDIA_TAGS and name == "srcset" and any(
                _is_external(c) for c in _srcset_candidates(value)
            ):
                self._hit("external_img_src", f"<{tag} srcset={value}")
            if tag in _FETCH_TAGS and name in _FETCH_ATTRS and _is_external(value):
                self._hit("external_nav_redirect", f"<{tag} {name}={value}")
            if tag == "base" and name == "href" and _is_external(value):
                self._hit("external_nav_redirect", f"<base href={value}")
        if tag == "meta" and first.get("http-equiv", "").strip().lower() == "refresh":
            url = _refresh_url(first.get("content", ""))
            if url and _is_external(url):
                self._hit("external_nav_redirect", f"<meta refresh -> {url}")

    def handle_endtag(self, tag: str) -> None:
        if tag == "style" and self._style_buf is not None:
            self._css.append("".join(self._style_buf))
            self._style_buf = None

    def handle_data(self, data: str) -> None:
        if self._style_buf is not None:
            self._style_buf.append(data)

    def close(self) -> None:
        super().close()
        if self._style_buf is not None:  # unterminated <style>: still CSS
            self._css.append("".join(self._style_buf))
            self._style_buf = None
        for css in self._css:
            norm = normalise_css(css)
            m = _CSS_EXPRESSION_RE.search(norm)
            if m:
                self._hit("css_expression", m.group(0))
            m = _CSS_EXTERNAL_FETCH_RE.search(norm)
            if m:
                self._hit("external_css_src", m.group(0))


def _token_layer(html: str) -> dict[str, str]:
    scan = _TokenScan()
    scan.feed(html)
    scan.close()
    return scan.found


def find_violations(html: str) -> list[Violation]:
    """Return every script-violation found in ``html``. Empty list = clean.

    Pure; deterministic; stdlib-only. Does not raise — caller decides
    whether to raise (``assert_script_free``) or report.
    """
    violations: list[Violation] = []
    tag_interiors = _tag_interiors(html)

    # 1. <script> tag (any case, open or close). Scanned on the raw html
    # (the tag-interior scan would also work, but the script-tag regex is
    # already tag-scoped by its ``<`` anchor).
    for m in _SCRIPT_TAG_RE.finditer(html):
        violations.append(Violation("script_tag", _trunc(m.group(0))))
        break  # one sample per class is enough; the class is failed

    # 2. Event-handler attributes (on*=). SCOPED TO TAG INTERIORS so prose
    # like "online = connected" does not false-fire.
    for tag in tag_interiors:
        mh = _EVENT_HANDLER_RE.search(_attr_names_only(tag))
        if mh:
            violations.append(Violation("event_handler", _trunc(mh.group(0))))
            break

    # 3. javascript:/vbscript: scheme in a URL-bearing attribute.
    # Attribute-scoped so legitimate prose mentioning "javascript:" does
    # not false-fire (see _JS_SCHEME_RE docstring).
    decoded = _decode_for_scheme_check(html)
    for m in _JS_SCHEME_RE.finditer(decoded):
        violations.append(Violation("javascript_href", _trunc(m.group(0))))
        break

    # 4. External asset src/srcset (img/audio/video/source/iframe/embed/
    # track). srcset is a URL-bearing attribute on img/source that browsers
    # fetch — the canonical evasion of a src-only check for the same
    # external-fetch/exfil threat — so it is scanned alongside src.
    for m in _EXTERNAL_SRC_RE.finditer(html):
        violations.append(Violation("external_img_src", _trunc(m.group(0))))
        break
    # Dedicated srcset scan: catches an external URL anywhere in a
    # comma/space-separated srcset list (broad regex above catches the
    # first-token case).
    for m in _EXTERNAL_SRCSET_RE.finditer(html):
        violations.append(Violation("external_img_src", _trunc(m.group(0))))
        break

    # 5. CSS-context checks — scoped to <style> block content + inline
    # style="..." attributes so prose like "the expression(x) evaluates"
    # or "url(http://...)" in body text does not false-fire.
    css_contexts: list[str] = []
    for sm in re.finditer(
        r"<style\b[^>]*>(.*?)</style>", html, re.IGNORECASE | re.DOTALL
    ):
        css_contexts.append(sm.group(1))
    for tag in tag_interiors:
        style_m = re.search(r'\bstyle\s*=\s*"([^"]*)"', tag, re.IGNORECASE)
        if style_m:
            css_contexts.append(style_m.group(1))
    for ctx_css in css_contexts:
        expr_m = _CSS_EXPRESSION_RE.search(ctx_css)
        if expr_m:
            violations.append(Violation("css_expression", _trunc(expr_m.group(0))))
            break
    # External CSS fetch (@import/url() to an http(s):// or // endpoint).
    # CSS exfiltrates page data and @import fetches+executes remote CSS —
    # both external-fetch/exfil vectors the self-contained invariant
    # forbids. Scanned on the same css_contexts as expression().
    for ctx_css in css_contexts:
        url_m = _EXTERNAL_CSS_URL_RE.search(ctx_css)
        if url_m:
            violations.append(Violation("external_css_src", _trunc(url_m.group(0))))
            break

    # 6. External navigation/redirect vectors (meta refresh, base href).
    # Not scripts, but the autonomous-ingest daemon following a redirect or
    # resolving hijacked relative URLs against an external origin is the
    # same "artifact reaches out to a remote origin" class the
    # self-contained invariant forbids.
    for m in _META_REFRESH_RE.finditer(html):
        violations.append(Violation("external_nav_redirect", _trunc(m.group(0))))
        break
    for m in _BASE_HREF_RE.finditer(html):
        violations.append(Violation("external_nav_redirect", _trunc(m.group(0))))
        break
    # Additional external-fetch vectors: <object data>, <link href>,
    # <svg><use href>, <form action>/<button formaction> pointing external.
    for m in _EXTERNAL_FETCH_EXTRA_RE.finditer(html):
        violations.append(Violation("external_nav_redirect", _trunc(m.group(0))))
        break

    # 7. Token layer: the same classes on the tokenizer's view. Only a
    # class the byte layer MISSED is added, so existing verdicts are
    # byte-for-byte unchanged and the union is strictly stronger.
    seen = {v.kind for v in violations}
    for kind, sample in _token_layer(html).items():
        if kind not in seen:
            violations.append(Violation(kind, sample))

    return violations


def _trunc(s: str, n: int = 60) -> str:
    """Truncate a match for the diagnostic message."""
    s = s.strip()
    return s if len(s) <= n else s[:n] + "…"


def is_script_free(html: str) -> bool:
    """Return True iff ``html`` contains no executable script."""
    return not find_violations(html)


def assert_script_free(html: str) -> None:
    """Raise ``ScriptViolation`` if ``html`` contains any script; else
    return None. The violation the renderer + ingest side call."""
    violations = find_violations(html)
    if violations:
        raise ScriptViolation(violations)


__all__ = [
    "ScriptViolation",
    "Violation",
    "assert_script_free",
    "find_violations",
    "is_script_free",
    "normalise_css",
]
