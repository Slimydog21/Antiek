"""M1 "single source of truth" gate (HPRJ SPR-03).

Every color in the widget CSS block (``LEMON_WIDGET_CSS``) must DERIVE from
an atomic palette constant — there must be no hex literal duplicated into
the CSS string by hand. This is what keeps the palette coherent when seven
widget files evolve independently: change ``LEMON_INK`` once and every
surface follows; a hand-copied ``#0F1419`` would silently drift.

The check: extract every ``#rrggbb`` from ``LEMON_WIDGET_CSS`` and assert
each one traces to a non-``_CSS`` ``LEMON_*`` constant. We exclude the
``*_CSS`` aggregates from the source set so the test is meaningful (a hex
must trace to an *atomic* constant, not merely appear in some CSS string).

Scope note: this targets the SPR-03 widget palette (``LEMON_WIDGET_CSS``).
``TOKENS_CSS`` is the SPR-02 projection *chrome* palette (the
``--antiek-*`` set) — a deliberately separate, byte-pinned language — and is
out of scope for this constant-derivation check.
"""

from __future__ import annotations

import re

from services.html_projection import tokens
from services.html_projection.styles import default_registry

_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def _atomic_constant_hexes() -> set[str]:
    """All hex values reachable from atomic LEMON_* constants (strings,
    tuples, and tuples-of-tuples), excluding the ``*_CSS`` aggregates."""
    found: set[str] = set()
    for name in dir(tokens):
        if not name.startswith("LEMON_") or name.endswith("_CSS"):
            continue
        value = getattr(tokens, name)
        # str() flattens nested tuples/pairs into one searchable blob.
        for hex_match in _HEX.findall(str(value)):
            found.add(hex_match.lower())
    return found


def test_widget_css_hexes_all_derive_from_atomic_constants() -> None:
    css_hexes = {h.lower() for h in _HEX.findall(tokens.LEMON_WIDGET_CSS)}
    assert css_hexes, "expected at least one color in LEMON_WIDGET_CSS"
    atomic = _atomic_constant_hexes()
    orphans = css_hexes - atomic
    assert not orphans, (
        "LEMON_WIDGET_CSS contains hex literal(s) not derived from any "
        f"atomic LEMON_* constant: {sorted(orphans)}"
    )


def test_widget_css_carries_the_load_bearing_palette() -> None:
    # Guard against the inverse failure: the CSS deriving from constants but
    # silently dropping the brand-defining ink. The Lemon-UI ink is the
    # 2px-border / hard-shadow signature; if it vanished, the derivation
    # test could still pass on a hollowed-out stylesheet.
    assert tokens.LEMON_INK.lower() in tokens.LEMON_WIDGET_CSS.lower()
    assert tokens.LEMON_SURFACE.lower() in tokens.LEMON_WIDGET_CSS.lower()


# ── Day / night / print gates (HPRJ SPR-06 task 3) ────────────────────────
#
# The projection is the operator's thesis made literal: every artifact is
# HTML that keeps the source's design philosophy AND Antiek's. An artifact
# that renders exactly one way fails that on the most basic axis, so the
# chrome palette owes the reader three surfaces — day, night and paper.
#
# These gates enforce the token discipline that makes those three possible
# rather than the surfaces themselves (which are CSS, and CSS is not
# executable here). The discipline is:
#
#   1. every colour in TOKENS_CSS lives in a ``:root`` token block, so a
#      surface is switched by redefining tokens and NEVER by editing rules;
#   2. TOKENS_CSS carries exactly one ``prefers-color-scheme: dark`` block
#      and exactly one ``@media print`` block — one night, one paper;
#   3. under any dark surface (the base's night block, or the ``slate``
#      builtin) no block background is LIGHTER than the document surface.
#
# Gate 3 is the defect that motivated this work: five hardcoded ``#fafaff``
# insets rendered voice / region / note / image / table-header blocks as
# near-white boxes on slate's dark page.
#
# REPAIRED DONE-BAR (recorded deliberately): the sprint spec asked for "no
# element whose computed background is lighter than its PAGE background".
# That is unsatisfiable for any dark theme with a page/surface ramp — slate
# deliberately floats a ``#171b22`` document card on a darker ``#0f1419``
# page, so the document itself is lighter than the page by design. The
# invariant the day palette actually obeys, and the one that catches the
# real defect, is measured against the DOCUMENT SURFACE: every inset sits
# at or below ``.antiek-doc``'s background, and the page sits at or below
# it too. That is what is asserted here.

_ROOT_SELECTOR = ":root"
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_comments(css: str) -> str:
    """Drop ``/* … */`` comments before any selector matching.

    Load-bearing, and it was found by mutation testing rather than by
    reading: ``ProjectionStyle.stylesheet()`` splices a
    ``/* --- antiek-style:slate --- */`` marker between the base and the
    theme. A parser that keeps it reads the theme's FIRST selector as
    ``"/* --- antiek-style:slate --- */\n:root"``, which matches nothing,
    so the theme's whole token block vanishes and the surface gate grades
    the day palette twice — green over an empty set. Mirrors the
    comment-safety fix in ``apps/reading/src/design/token-parity.test.ts``.
    """
    return _COMMENT.sub("", css)


def _match_brace(css: str, open_idx: int) -> int:
    """Index of the ``}`` matching the ``{`` at ``open_idx``."""
    depth = 0
    for i in range(open_idx, len(css)):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    raise AssertionError("unbalanced braces in stylesheet")


def _context_name(condition: str) -> str:
    """Normalise an ``@media`` condition to a short context name."""
    cond = condition.strip().lower()
    if "prefers-color-scheme" in cond and "dark" in cond:
        return "dark"
    if cond == "print":
        return "print"
    return cond


def _rules_in_context(css: str, active: frozenset[str]) -> list[tuple[str, str]]:
    """``(selector, declarations)`` in TRUE SOURCE ORDER, descending only into
    ``@media`` blocks whose context is in ``active``.

    Source order is load-bearing: ``ProjectionStyle.stylesheet()`` appends the
    theme AFTER the base, and later CSS wins. A parser that hoisted media
    blocks would silently invert that and grade the wrong cascade.
    """
    css = _strip_comments(css)
    rules: list[tuple[str, str]] = []
    i, n = 0, len(css)
    while i < n:
        if css[i] in " \n\t\r;":
            i += 1
            continue
        if css.startswith("@media", i):
            open_idx = css.index("{", i)
            cond = css[i + len("@media") : open_idx]
            close_idx = _match_brace(css, open_idx)
            if _context_name(cond) in active:
                rules.extend(_rules_in_context(css[open_idx + 1 : close_idx], active))
            i = close_idx + 1
            continue
        open_idx = css.index("{", i)
        close_idx = _match_brace(css, open_idx)
        rules.append((css[i:open_idx].strip(), css[open_idx + 1 : close_idx]))
        i = close_idx + 1
    return rules


def _declarations(block: str) -> list[tuple[str, str, bool]]:
    """``(property, value, important)`` triples, in source order."""
    out: list[tuple[str, str, bool]] = []
    for chunk in block.split(";"):
        if ":" not in chunk:
            continue
        prop, _, value = chunk.partition(":")
        important = "!important" in value
        out.append(
            (
                prop.strip().lower(),
                value.replace("!important", "").strip(),
                important,
            )
        )
    return out


def _root_vars(rules: list[tuple[str, str]]) -> dict[str, str]:
    """Last-wins ``--name -> value`` map from every ``:root`` block in order.

    ``!important`` is honoured, not stripped: the print block relies on it to
    beat a theme that ``stylesheet()`` appends AFTER the base, so a parser that
    ignored it would grade the wrong winner and green-light a print reset that
    a dark theme silently defeats.
    """
    found: dict[str, str] = {}
    locked: set[str] = set()
    for selector, block in rules:
        if selector != _ROOT_SELECTOR:
            continue
        for prop, value, important in _declarations(block):
            if not prop.startswith("--"):
                continue
            if prop in locked and not important:
                continue
            found[prop] = value
            if important:
                locked.add(prop)
    return found


_VAR_CALL = re.compile(r"var\(\s*(--[a-z0-9-]+)\s*(?:,([^)]*))?\)", re.IGNORECASE)


def _resolve(value: str, variables: dict[str, str], depth: int = 0) -> str:
    """Resolve ``var(--x[, fallback])`` against the token map (bounded)."""
    if depth > 8:
        return value
    match = _VAR_CALL.search(value)
    if match is None:
        return value.strip()
    name, fallback = match.group(1).lower(), (match.group(2) or "").strip()
    replacement = variables.get(name, fallback)
    return _resolve(
        value[: match.start()] + replacement + value[match.end() :],
        variables,
        depth + 1,
    )


def _luminance(color: str) -> float | None:
    """WCAG relative luminance of a ``#rgb``/``#rrggbb``; ``None`` if not a hex."""
    text = color.strip()
    if not text.startswith("#"):
        return None
    digits = text[1:]
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    if len(digits) != 6:
        return None
    channels = []
    for offset in (0, 2, 4):
        raw = int(digits[offset : offset + 2], 16) / 255
        channels.append(raw / 12.92 if raw <= 0.04045 else ((raw + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _backgrounds(rules: list[tuple[str, str]], variables: dict[str, str]) -> dict[str, float]:
    """Last-wins resolved background LUMINANCE per selector (hex ones only)."""
    out: dict[str, float] = {}
    for selector, block in rules:
        for prop, value, _important in _declarations(block):
            if prop not in ("background", "background-color"):
                continue
            lum = _luminance(_resolve(value, variables))
            if lum is None:
                out.pop(selector, None)  # transparent/keyword clears a prior hex
            else:
                out[selector] = lum
    return out


def _surface_violations(css: str, context: frozenset[str]) -> list[str]:
    """Selectors whose background is lighter than ``.antiek-doc``'s surface.

    Pure, so the red-proof below can drive it directly on a synthetic sheet.
    """
    rules = _rules_in_context(css, context)
    variables = _root_vars(rules)
    backgrounds = _backgrounds(rules, variables)
    surface = backgrounds.get(".antiek-doc")
    assert surface is not None, (
        "the document surface (.antiek-doc background) must resolve to a "
        "colour; without it there is nothing to measure insets against"
    )
    epsilon = 1e-9
    return sorted(
        f"{selector} ({lum:.4f} > surface {surface:.4f})"
        for selector, lum in backgrounds.items()
        if selector != ".antiek-doc" and lum > surface + epsilon
    )


def _root_block_spans(css: str) -> list[tuple[int, int]]:
    """``(start, end)`` character spans of every ``:root{...}`` body."""
    css = _strip_comments(css)
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"(^|[\s}])(:root)\s*\{", css):
        open_idx = css.index("{", match.start(2))
        spans.append((open_idx, _match_brace(css, open_idx)))
    return spans


def test_tokens_css_declares_every_colour_in_a_root_token_block() -> None:
    """No raw hex outside a ``:root`` block — the precondition for theming.

    A hex baked into a rule (``background:#fafaff``) cannot be re-pointed by a
    night block or a theme; it is a colour the reader can never change. All
    five ``#fafaff`` insets and both ``#f6f6fa`` code slabs were exactly that.
    """
    css = _strip_comments(tokens.TOKENS_CSS)
    spans = _root_block_spans(css)
    assert spans, "TOKENS_CSS must declare its palette in a :root block"
    orphans = [
        match.group(0)
        for match in re.finditer(r"#[0-9a-fA-F]{3,8}\b", css)
        if not any(start < match.start() < end for start, end in spans)
    ]
    assert not orphans, (
        "TOKENS_CSS declares colour(s) outside a :root token block: "
        f"{sorted(set(orphans))}; move them to a --antiek-* token so day, "
        "night, print and every wheel theme can re-point them"
    )


def test_tokens_css_ships_exactly_one_night_and_one_paper_surface() -> None:
    """One ``prefers-color-scheme: dark`` block and one ``@media print`` block.

    Exactly one of each, not "at least one": two night blocks means two
    palettes racing on source order, which is how a token set silently
    forks.
    """
    css = tokens.TOKENS_CSS
    assert css.count("prefers-color-scheme") == 1, (
        "TOKENS_CSS must carry exactly one prefers-color-scheme block; found "
        f"{css.count('prefers-color-scheme')}"
    )
    assert css.count("@media print") == 1, (
        f"TOKENS_CSS must carry exactly one @media print block; found {css.count('@media print')}"
    )


def _assert_context_is_live(css: str, context: frozenset[str], label: str) -> None:
    """Guard against grading an EMPTY SET.

    ``_rules_in_context`` silently falls back to the day cascade when the
    requested ``@media`` block is absent, so a night/print assertion would
    pass by grading day twice. Prove the block was actually entered.
    """
    assert _rules_in_context(css, context) != _rules_in_context(css, frozenset()), (
        f"no {label} block was entered; this gate would be grading day twice"
    )


def test_night_palette_keeps_every_inset_at_or_below_the_surface() -> None:
    """Under the base night block, no block background outshines the page."""
    _assert_context_is_live(tokens.TOKENS_CSS, frozenset({"dark"}), "night")
    violations = _surface_violations(tokens.TOKENS_CSS, frozenset({"dark"}))
    assert not violations, (
        "night mode renders lighter-than-surface block(s): "
        f"{violations}; every --antiek-* background token must be redefined "
        "in the prefers-color-scheme:dark block"
    )


def test_slate_builtin_keeps_every_inset_at_or_below_the_surface() -> None:
    """The reported defect: near-white insets on slate's dark page."""
    slate = default_registry().get("slate")
    violations = _surface_violations(slate.stylesheet(), frozenset())
    assert not violations, (
        "the slate builtin renders lighter-than-surface block(s): "
        f"{violations}; a dark theme must redefine the --antiek-* tokens, "
        "not only .antiek-doc"
    )


def test_day_palette_keeps_every_inset_at_or_below_the_surface() -> None:
    """The same invariant the day palette has always obeyed, now asserted."""
    violations = _surface_violations(tokens.TOKENS_CSS, frozenset())
    assert not violations, f"day mode renders lighter-than-surface block(s): {violations}"


def test_print_block_overrides_an_appended_theme() -> None:
    """Paper must beat the wheel.

    ``stylesheet()`` appends the theme AFTER the base, so a dark theme's
    ``:root`` would otherwise out-order the base's print block and send light
    ink to a printer that drops backgrounds. The print token overrides carry
    ``!important`` for exactly this reason; this asserts they still do, and
    that printing slate therefore lands on a light surface.
    """
    slate = default_registry().get("slate")
    _assert_context_is_live(slate.stylesheet(), frozenset({"print"}), "print")
    rules = _rules_in_context(slate.stylesheet(), frozenset({"print"}))
    variables = _root_vars(rules)
    surface = _luminance(_resolve(variables["--antiek-surface"], variables))
    assert surface is not None and surface > 0.5, (
        "printing the slate builtin must land on a light surface, but "
        f"--antiek-surface resolves to {variables['--antiek-surface']!r}"
    )
    # And paper obeys the same ramp: nothing outshines the sheet.
    assert _surface_violations(slate.stylesheet(), frozenset({"print"})) == []


def test_surface_gate_is_not_a_rubber_stamp() -> None:
    """Red-proof: the checker must flag a light inset on a dark surface.

    Without this the three gates above could be green over an empty set (the
    failure mode this repo keeps hitting), so drive the pure checker on a
    synthetic sheet whose answer is known.
    """
    bad = (
        ":root{--antiek-surface:#171b22;--antiek-inset:#fafaff;}\n"
        ".antiek-doc{background:var(--antiek-surface);}\n"
        ".antiek-note{background:var(--antiek-inset);}\n"
    )
    assert any(v.startswith(".antiek-note") for v in _surface_violations(bad, frozenset()))
    good = bad.replace("--antiek-inset:#fafaff", "--antiek-inset:#12161d")
    assert _surface_violations(good, frozenset()) == []
