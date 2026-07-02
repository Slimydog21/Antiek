"""HTML escaping primitives (HPRJ SPR-02 / M2 + M3).

Two distinct escaping regimes live here:

1.  ``escape_text`` / ``escape_attr`` — ordinary HTML-text and
    attribute-value escaping for the VISIBLE projection. Used by the
    renderer + partials so user content never injects markup into the
    visible surface.

2.  ``island_escape`` / ``island_unescape`` — the data-island escaping
    regime. The data island embeds canonical doc-model JSON inside a
    ``<template data-antiek="doc-model">`` element. A ``<template>``'s
    content is parsed but not rendered, which gives a free "inert"
    container — BUT the HTML parser still tokenises the content, so a
    literal ``</template>`` inside the JSON would prematurely close the
    template and corrupt the round-trip. The island regime therefore
    escapes the JSON so it survives an HTML parse round-trip with
    byte-identical recovery.

Why ``<template>`` and not a ``<script type="application/json">``: the
master-spec SCRIPT-FREE invariant (Key invariant 1) is absolute — a
script tag in an artifact is an RCE vector for the §7 continuous-research
daemon. ``<script type="application/json">`` is inert in practice, but it
is still a ``<script>`` byte-sequence and the zero-script gate (M4) MUST
flag it. A ``<template>`` is not a script, is inert by spec, and round-
trips cleanly with the escaping below. This is the load-bearing choice
that lets the island coexist with the script-free invariant.

ISLAND ESCAPING ALGORITHM
-------------------------
The island content is canonical doc-model JSON, UTF-8. We escape the
minimal set that the HTML tokenizer would otherwise consume:

  - ``<``  →  ``&lt;``        (prevents ``</template>`` and any tag open)
  - ``&``  →  ``&amp;``        (prevents entity interpretation)
  - ``>``  →  ``&gt;``         (belt-and-braces; ``>`` is only special
                                after ``<``, but escaping it keeps the
                                content unambiguous under re-parsing)

We do NOT escape quotes: the JSON lives as element TEXT (between
``<template ...>`` and ``</template>``), not inside an attribute, so
quotes carry no tokenizer meaning. Not escaping quotes also keeps the
round-trip trivially invertible (the unescape is the exact inverse).

This set is provably sufficient: after escaping, the content contains no
``<``, so the HTML tokenizer sees no start-tag, no end-tag, no comment,
no CDATA — it treats the entire run as character tokens. The DOM stores
them as text; ``textContent`` recovers the escaped string; the inverse
unescape recovers the original JSON bytes. The M3 round-trip test proves
this over an adversarial corpus including ``</template>`` inside strings,
nested ``<template>``-looking substrings, unicode, and every quote
flavour.

INVERTIBILITY: ``island_unescape`` is the exact inverse of
``island_escape``. The escapes are applied in a fixed order and undone in
the reverse order; the character sets are disjoint (``&`` is escaped
first, so a literal ``&lt;`` in the source becomes ``&amp;lt;`` and
round-trips correctly — see the adversarial test).
"""

from __future__ import annotations

# ── Visible-surface escaping ──


def escape_text(s: str) -> str:
    """Escape a string for use as HTML element text content.

    Escapes ``&``, ``<``, ``>``. Does NOT escape quotes (not special in
    text content). Sufficient to prevent markup injection into the
    visible surface.
    """
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def escape_attr(s: str) -> str:
    """Escape a string for use as a double-quoted attribute value.

    Escapes ``&``, ``<``, ``>``, and ``"``. The renderer always emits
    attributes double-quoted, so escaping the double quote is sufficient
    (single quotes inside a double-quoted attr are safe).
    """
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ── Data-island escaping ──


def island_escape(s: str) -> str:
    """Escape a string for embedding as text inside ``<template>``.

    Escapes ``&``, ``<``, ``>`` in that order. Invertible by
    ``island_unescape``. See module docstring for the sufficiency proof.
    """
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def island_unescape(s: str) -> str:
    """Inverse of ``island_escape``.

    Undoes the escapes in reverse order. Because ``island_escape``
    escapes ``&`` first (so no escaped sequence contains a literal ``&``
    that a later step would corrupt), the unescape is unambiguous: every
    ``&...;`` in the escaped string is one of our three entities.
    """
    return (
        s.replace("&gt;", ">")
        .replace("&lt;", "<")
        .replace("&amp;", "&")
    )


__all__ = [
    "escape_attr",
    "escape_text",
    "island_escape",
    "island_unescape",
]
