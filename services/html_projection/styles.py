"""Forkable projection styles — the "wheel of styles" backend (v1 foundation).

The operator's thesis: every information artifact is HTML, and its *look* is a
choice on a clickable wheel — the reader picks a style (Antiek / academic paper /
book / blog / slate), regenerates an artifact in a different style, or forks a new
style onto the wheel. Because the projection renderer is DETERMINISTIC with a
data-island round-trip (``extract_island(render(d)) == d``), restyling is pure
presentation: "regenerate in style X" is ``render(extract_island(artifact), ctx,
style=X)`` — NO model call, byte-identical for a given (doc, style).

Design — base + theme layering (NOT wholesale stylesheet replacement)
--------------------------------------------------------------------
A style is the canonical Antiek structural stylesheet (:data:`tokens.TOKENS_CSS`
— the block classes, provenance footer, hidden data island, the zero-script
contract) PLUS an appended theme override block. Later CSS rules win, so a theme
re-skins typography / color / measure / rhythm while every style KEEPS Antiek's
structural chrome and provenance discipline. This is the operator's "retain the
source's design philosophy AND retain core Antiek design philosophy" made literal:
``source_fidelity`` styles (paper/book/blog) lean into the source's reading feel;
the Antiek base underneath guarantees the artifact is still an Antiek artifact.

Every style is validated to be script-free and self-contained (no ``<script>``,
no ``javascript:``, no external ``@import``/``url()``) through the SAME
:mod:`services.html_projection.gate` the renderer's output must pass — so a
user-forked style cannot smuggle script into the reader (the stored-XSS class this
projection engine exists to prevent). Determinism: no wall-clock, no randomness;
:func:`StyleRegistry.list_styles` returns insertion order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import gate, tokens


@dataclass(frozen=True)
class ProjectionStyle:
    """One entry on the style wheel.

    ``theme_css`` is appended AFTER the Antiek base stylesheet; :meth:`stylesheet`
    composes the two. ``source_fidelity`` marks styles that deliberately emulate a
    source medium (academic paper, book, blog) versus the pure Antiek house look.
    ``builtin`` distinguishes shipped styles from user-forked ones (a forked style
    can be removed from the wheel; a builtin cannot).

    ``parent`` is the slug of the style a fork was derived from, so provenance
    survives across sessions (``None`` for builtins and for forks created before
    the provenance column existed). It is metadata for the wheel's "forked from X"
    rendering; it is never read by the renderer, so a style's bytes stay a pure
    function of everything *except* ``parent``.
    """

    name: str  # slug: [a-z0-9-], the stable id used in URLs / persistence
    label: str  # human label shown on the wheel
    description: str
    theme_css: str = ""  # override layer appended after the Antiek base
    source_fidelity: bool = False
    builtin: bool = True
    parent: str | None = None  # slug of the style this fork came from (builtins/legacy -> None)

    def stylesheet(self) -> str:
        """The complete inlined stylesheet for this style: Antiek base + theme."""
        base = tokens.TOKENS_CSS
        if not self.theme_css.strip():
            return base
        return f"{base}\n/* --- antiek-style:{self.name} --- */\n{self.theme_css}"


_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# External-asset / script vectors that would break the self-contained + script-free
# invariants even inside a CSS block. The gate covers <script>/javascript:; these
# guard the CSS-specific escape hatches (@import and url() pull external bytes;
# expression() is dead-IE script; behavior:/-moz-binding: bind script).
_CSS_FORBIDDEN = re.compile(
    r"@import|url\s*\(|expression\s*\(|behavior\s*:|-moz-binding|javascript:",
    re.IGNORECASE,
)


class StyleError(ValueError):
    """A style is malformed, unsafe, or unknown."""


def validate_style(style: ProjectionStyle) -> None:
    """Reject a style whose slug is malformed or whose CSS is unsafe.

    Runs the composed stylesheet through the zero-script gate (wrapped in a
    ``<style>`` element exactly as the renderer emits it) AND a CSS-specific
    external-asset check. Raises :class:`StyleError` on any violation. This is the
    gate a user-forked style must clear before it can join the wheel — a forked
    style is untrusted input.
    """
    if not _SLUG_RE.match(style.name):
        raise StyleError(
            f"style name {style.name!r} must be a lowercase slug ([a-z0-9] with "
            "single hyphens), so it is URL- and filename-safe",
        )
    if not style.label.strip():
        raise StyleError(f"style {style.name!r} needs a non-empty label")

    css = style.theme_css
    m = _CSS_FORBIDDEN.search(css)
    if m is not None:
        raise StyleError(
            f"style {style.name!r} theme CSS contains a forbidden construct "
            f"({m.group(0)!r}): projection styles must be self-contained "
            "(no @import/url()/expression()/behavior/binding/javascript:)",
        )
    # The composed stylesheet, as the renderer will emit it, must pass the gate.
    violations = gate.find_violations(f"<style>\n{style.stylesheet()}</style>")
    if violations:
        raise StyleError(
            f"style {style.name!r} would introduce {len(violations)} script "
            f"violation(s): {violations[0]}",
        )


class StyleRegistry:
    """An ordered, validated set of projection styles — one wheel.

    Built-ins are registered at construction. User forks are added via
    :meth:`register`; each is validated first. Iteration/list order is insertion
    order (deterministic) so the wheel renders stably.
    """

    def __init__(self, styles: list[ProjectionStyle] | None = None) -> None:
        self._styles: dict[str, ProjectionStyle] = {}
        for s in styles or []:
            self._add(s, validate=False)  # builtins are trusted, but see below

    def _add(self, style: ProjectionStyle, *, validate: bool) -> None:
        if validate:
            validate_style(style)
        self._styles[style.name] = style

    def register(self, style: ProjectionStyle) -> ProjectionStyle:
        """Add (or replace) a user-forked style after validation.

        Replacing a BUILTIN is refused — the house defaults are stable anchors on
        the wheel. Returns the registered style for chaining.
        """
        existing = self._styles.get(style.name)
        if existing is not None and existing.builtin:
            raise StyleError(
                f"cannot override builtin style {style.name!r}; fork it under a new name",
            )
        self._add(style, validate=True)
        return style

    def remove(self, name: str) -> None:
        """Remove a user-forked style. Builtins cannot be removed."""
        s = self._styles.get(name)
        if s is None:
            raise StyleError(f"unknown style {name!r}")
        if s.builtin:
            raise StyleError(f"cannot remove builtin style {name!r}")
        del self._styles[name]

    def get(self, name: str) -> ProjectionStyle:
        try:
            return self._styles[name]
        except KeyError:
            raise StyleError(
                f"unknown style {name!r}; known: {', '.join(self._styles)}",
            ) from None

    def has(self, name: str) -> bool:
        return name in self._styles

    def list_styles(self) -> list[ProjectionStyle]:
        """All styles in insertion (wheel) order."""
        return list(self._styles.values())

    def names(self) -> list[str]:
        return list(self._styles)


# ── Built-in styles (the default wheel) ────────────────────────────────────
# Each theme override targets the structural classes the renderer emits
# (``.antiek-doc`` wrapper, ``.antiek-doc-title``) plus generic block elements, so
# it re-skins without needing per-block knowledge. The Antiek base underneath
# still defines layout, the provenance footer, and the hidden data island.

DEFAULT_STYLE_NAME = "antiek"

_ACADEMIC_CSS = """\
.antiek-doc {
  font-family: "Charter", "Georgia", "Times New Roman", serif;
  max-width: 44rem;
  line-height: 1.7;
  color: #16130d;
}
.antiek-doc-title { font-weight: 700; letter-spacing: -0.01em; }
.antiek-doc h2, .antiek-doc h3 { font-family: inherit; font-weight: 700; }
.antiek-doc p { text-align: justify; hyphens: auto; }
.antiek-doc a { color: #7a1f1f; text-decoration-thickness: 1px; }
"""

_BOOK_CSS = """\
.antiek-doc {
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", serif;
  max-width: 38rem;
  line-height: 1.75;
  color: #241a12;
  background: #f7f1e6;
}
.antiek-doc-title { font-variant: small-caps; letter-spacing: 0.02em; }
.antiek-doc p { text-indent: 1.4em; margin-block: 0; }
.antiek-doc p:first-of-type { text-indent: 0; }
.antiek-doc a { color: #4a3b2a; }
"""

_BLOG_CSS = """\
.antiek-doc {
  font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
  max-width: 40rem;
  line-height: 1.65;
  color: #1a1a1a;
}
.antiek-doc-title { font-weight: 800; letter-spacing: -0.02em; }
.antiek-doc p { margin-block: 1.1em; }
.antiek-doc a { color: #1d4aff; text-underline-offset: 2px; }
"""

_SLATE_CSS = """\
body { background: #0f1419; }
.antiek-doc {
  font-family: "Inter", system-ui, sans-serif;
  max-width: 42rem;
  line-height: 1.7;
  color: #e6e1d8;
  background: #171b22;
}
.antiek-doc-title { color: #f4efe6; }
.antiek-doc a { color: #7aa2ff; }
"""

BUILTIN_STYLES: list[ProjectionStyle] = [
    ProjectionStyle(
        name=DEFAULT_STYLE_NAME,
        label="Antiek",
        description="The Antiek house look — Lemon chrome, day/night tokens.",
        theme_css="",  # the base stylesheet IS the Antiek style
        source_fidelity=False,
    ),
    ProjectionStyle(
        name="academic-paper",
        label="Academic paper",
        description="Serif, single justified column, wide margins — a preprint feel.",
        theme_css=_ACADEMIC_CSS,
        source_fidelity=True,
    ),
    ProjectionStyle(
        name="book",
        label="Book",
        description="Old-style serif, narrow measure, indented paragraphs — a printed page.",
        theme_css=_BOOK_CSS,
        source_fidelity=True,
    ),
    ProjectionStyle(
        name="blog",
        label="Blog",
        description="Clean sans, comfortable measure — a modern web article.",
        theme_css=_BLOG_CSS,
        source_fidelity=True,
    ),
    ProjectionStyle(
        name="slate",
        label="Slate (dark)",
        description="Dark reading surface for long sessions.",
        theme_css=_SLATE_CSS,
        source_fidelity=False,
    ),
]


def default_registry() -> StyleRegistry:
    """A fresh registry seeded with the built-in wheel.

    Returns a NEW registry each call so a caller (or a per-user session) can fork
    styles onto its own wheel without mutating global state.
    """
    return StyleRegistry(list(BUILTIN_STYLES))


def resolve_style(
    style: ProjectionStyle | str | None,
    *,
    registry: StyleRegistry | None = None,
) -> ProjectionStyle:
    """Coerce ``None`` / a slug / a ProjectionStyle into a ProjectionStyle.

    ``None`` → the Antiek default. A ``str`` is looked up in ``registry`` (or a
    fresh default registry). A :class:`ProjectionStyle` is returned as-is (an
    ad-hoc style not on any wheel — validated by the caller if untrusted).
    """
    if style is None:
        return BUILTIN_STYLES[0]
    if isinstance(style, ProjectionStyle):
        return style
    reg = registry or default_registry()
    return reg.get(style)


__all__ = [
    "ProjectionStyle",
    "StyleRegistry",
    "StyleError",
    "validate_style",
    "default_registry",
    "resolve_style",
    "BUILTIN_STYLES",
    "DEFAULT_STYLE_NAME",
]
