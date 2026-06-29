"""Design tokens (inlined CSS) + widget-call seam (HPRJ SPR-02 / M2).

The HTML projection is SELF-CONTAINED: no external stylesheet, no external
script, no external asset. The CSS that styles the projection is inlined
into a single ``<style>`` element in the document ``<head>`` by the
renderer. This module owns that CSS as a single string constant so the
renderer, the gate (which must allow ``<style>`` but forbid ``<script>``),
and any future operator-theme override all agree on what "the projection
stylesheet" is.

WHY INLINE CSS AND NOT A ``<link>``: the master-spec self-contained
invariant (Key invariant 4) says an artifact opens correctly offline. A
``<link rel="stylesheet" href="...">`` to an external URL would (a) break
offline and (b) be an external-asset vector the zero-script gate would have
to special-case. Inlining removes both. The cost — a few KB per artifact —
is negligible against the determinism + offline guarantees.

WHY A TOKENS MODULE AND NOT A STRING IN THE RENDERER: three reasons.
1. SPR-03 (widgets) will add per-widget CSS tokens (chart palettes,
   sparkline stroke widths). Giving them a home now means SPR-03 adds to
   this module instead of reworking the renderer.
2. The zero-script gate (M4) needs to know the projection's legitimate
   ``<style>`` content lives here, so it can't be accused of
   rubber-stamping arbitrary style blocks. (The gate is stricter than
   that — it forbids script regardless of where CSS lives — but the
   separation makes the contract legible.)
3. Operator theme overrides (SPR-04 projection.html shell) replace this
   module's constants; the renderer stays untouched.

WIDGET-CALL SEAM (SPR-03, out of scope for SPR-02): the spec says widgets
(charts/sparklines/dep-graphs) are SPR-03 and "your contract is the tokens
module + a widget-call seam, not the widgets." The seam is
``WIDGET_SEAM``: a documented placeholder CSS class + a no-op registration
hook. SPR-03 replaces the hook body; SPR-02 ships the empty hook so the
renderer's widget-call sites have a stable target.

Determinism note: this module contains NO wall-clock, NO randomness, NO
dict/set iteration whose order varies. The CSS string is a literal. The
widget registry is a list (ordered, not a set) so registration order is
insertion order — deterministic.
"""

from __future__ import annotations

from typing import Final, Protocol


# ── Inlined stylesheet ──
#
# Every rule is plain CSS — no ``@import`` (would be an external asset),
# no ``url()`` (would be an external asset), no ``expression()`` (dead IE
# CSS-expression RCE vector — belt-and-braces, browsers ignore it now but
# the gate greps for it too). Variables use the standard ``--name`` syntax.
#
# The palette is a constrained PostHog-feel set (neutral surface, one
# accent, one warn for tombstones). It is intentionally NOT configurable
# per-render — determinism requires the same doc-model to always produce
# the same bytes, and a per-render theme argument would be a
# nondeterminism source. Theme overrides are an SPR-04 shell concern.

TOKENS_CSS: Final[str] = """\
:root{
  --antiek-surface:#ffffff;
  --antiek-ink:#1f1f2e;
  --antiek-muted:#5a5a6e;
  --antiek-rule:#e4e4ec;
  --antiek-accent:#5b6cff;
  --antiek-accent-soft:#eef0ff;
  --antiek-warn:#8a5a00;
  --antiek-warn-bg:#fff7e6;
  --antiek-mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
.antiek-doc{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:var(--antiek-ink);background:var(--antiek-surface);max-width:760px;margin:0 auto;padding:2rem 1.25rem;line-height:1.6;}
.antiek-doc h1{font-size:1.6rem;margin:0 0 1rem;}
.antiek-block{margin:0 0 1.25rem;}
.antiek-prose{margin:0 0 1rem;}
.antiek-highlight{border-left:3px solid var(--antiek-accent);background:var(--antiek-accent-soft);padding:.75rem 1rem;border-radius:.25rem;}
.antiek-highlight-passage{font-style:italic;}
.antiek-highlight-framing{margin-top:.5rem;color:var(--antiek-muted);font-size:.9rem;}
.antiek-voice{border:1px solid var(--antiek-rule);border-radius:.375rem;padding:.75rem 1rem;background:#fafaff;}
.antiek-voice-meta{color:var(--antiek-muted);font-size:.85rem;font-family:var(--antiek-mono);}
.antiek-voice-transcript{margin-top:.5rem;}
.antiek-qa{border:1px solid var(--antiek-rule);border-radius:.375rem;padding:.75rem 1rem;}
.antiek-qa-q{font-weight:600;}
.antiek-qa-a{margin-top:.4rem;}
.antiek-qa-attr{margin-top:.4rem;color:var(--antiek-muted);font-size:.85rem;font-style:italic;}
.antiek-cite{font-family:var(--antiek-mono);font-size:.9rem;}
.antiek-crossdoc{font-family:var(--antiek-mono);font-size:.9rem;color:var(--antiek-muted);}
.antiek-region{border:1px dashed var(--antiek-rule);border-radius:.375rem;padding:.75rem 1rem;background:#fafaff;}
.antiek-region-ref{font-family:var(--antiek-mono);font-size:.85rem;color:var(--antiek-muted);}
.antiek-claim{border:1px solid var(--antiek-rule);border-left:3px solid var(--antiek-ink);border-radius:.375rem;padding:.75rem 1rem;}
.antiek-claim-statement{font-weight:500;}
.antiek-note{background:#fafaff;border-radius:.375rem;padding:.6rem .9rem;font-size:.95rem;}
.antiek-question{border:1px solid var(--antiek-rule);border-radius:.375rem;padding:.75rem 1rem;}
.antiek-question-q{font-weight:600;}
.antiek-chat{border:1px solid var(--antiek-rule);border-radius:.375rem;padding:.75rem 1rem;}
.antiek-chat-turn{margin:0 0 .5rem;}
.antiek-chat-turn:last-child{margin-bottom:0;}
.antiek-chat-role{font-weight:600;font-size:.85rem;color:var(--antiek-muted);}
.antiek-mdsection{border-top:1px solid var(--antiek-rule);padding-top:.75rem;}
.antiek-mdsection-head{font-weight:600;color:var(--antiek-muted);font-size:.85rem;text-transform:uppercase;letter-spacing:.04em;}
.antiek-image{border:1px solid var(--antiek-rule);border-radius:.375rem;padding:.6rem;background:#fafaff;text-align:center;}
.antiek-image-alt{color:var(--antiek-muted);font-size:.85rem;font-style:italic;}
.antiek-latex{font-family:var(--antiek-mono);background:#f6f6fa;border-radius:.25rem;padding:.6rem .8rem;overflow-x:auto;font-size:.95rem;}
.antiek-tombstone{border:1px solid var(--antiek-warn);background:var(--antiek-warn-bg);color:var(--antiek-warn);border-radius:.375rem;padding:.6rem .9rem;font-size:.9rem;}
.antiek-tombstone-label{font-weight:600;}
.antiek-unsupported{border:1px dashed var(--antiek-warn);background:var(--antiek-warn-bg);color:var(--antiek-warn);border-radius:.375rem;padding:.6rem .9rem;font-size:.9rem;font-family:var(--antiek-mono);}
.antiek-edges{border-top:1px solid var(--antiek-rule);margin-top:1.5rem;padding-top:1rem;}
.antiek-edges h2{font-size:1.1rem;margin:0 0 .5rem;}
.antiek-edges ul{margin:0;padding-left:1.1rem;}
.antiek-edges li{margin:0 0 .25rem;}
.antiek-footer{border-top:1px solid var(--antiek-rule);margin-top:2rem;padding-top:.75rem;color:var(--antiek-muted);font-size:.8rem;font-family:var(--antiek-mono);}
.antiek-footer a{color:var(--antiek-muted);}
"""


# ── Lemon-UI widget palette + geometry (HPRJ SPR-03) ──
#
# SPR-03 builds the WIDGET LIBRARY: 7 pure-function SVG/CSS widgets
# (stat_chip, bar_chart, sparkline, donut, timeline, dep_graph,
# cite_block). These widgets have their OWN visual language — the
# Lemon-UI token palette — which is DISTINCT from the renderer-chrome
# palette in TOKENS_CSS above. The two palettes intentionally differ:
#
#   * TOKENS_CSS (--antiek-*) is the PROJECTION CHROME — the container
#     blocks, footers, tombstones the renderer emits. It is byte-pinned
#     by the determinism tests (M5 renders the golden corpus and
#     byte-compares, and the rendered HTML embeds TOKENS_CSS verbatim),
#     so it MUST NOT change shape. It stays exactly as SPR-02 shipped.
#
#   * The Lemon-UI palette below is the WIDGET language — chunky 2px
#     black borders, 4px offset hard shadows, a yellow accent, a blue
#     primary, and the success/warning/danger/info semantic set. Widgets
#     read THESE constants (never the --antiek-* vars) so a widget's
#     bytes are a function of this palette alone.
#
# WHY A SEPARATE PALETTE AND NOT THE CHROME PALETTE: the chrome palette
# is a constrained PostHog-feel neutral set (one accent, one warn). The
# widget library needs the full semantic set (success/warning/danger/
# info) for categorical charts, donut segments, and stat-chip deltas —
# colors the chrome palette deliberately lacks. Giving widgets their
# own palette means SPR-03 adds here without reworking the chrome
# (additive, non-breaking), and a future operator-theme override
# (SPR-04) can retone one without touching the other.
#
# Determinism: every constant below is a literal. No wall-clock, no
# randomness, no dict/set iteration. Widgets that index these MUST
# iterate in a fixed, declared order (see e.g. CATEGORY_COLORS below)
# so two renders of the same data are byte-identical.

# ── Core palette ──
LEMON_PRIMARY: Final[str] = "#1d4aff"
"""The Lemon-UI primary — a saturated royal blue. The default fill for a
primary affordance (a selected bar, a primary stat, the dep-graph root
node)."""

LEMON_ACCENT: Final[str] = "#F9BD2B"
"""The Lemon-UI accent — a warm sun-yellow. The highlight/featured fill:
a featured bar, the sparkline stroke, the active timeline node, the
donut's leading slice. This is the brand hook that makes a widget read
Lemon-UI."""

LEMON_INK: Final[str] = "#0F1419"
"""Near-black ink for text, axes, and the hard 2px borders + offset
shadow cast. Same ink as the chrome palette's surface text so a widget
embedded in a projection shares its text color with the surrounding
chrome (no color jump at the widget boundary)."""

LEMON_SURFACE: Final[str] = "#FFFFFF"
"""The widget card / SVG background. White so the offset shadow reads
and the categorical fills pop."""

# ── Semantic set (success / warning / danger / info) ──
# Used for stat-chip deltas (up = success, down = danger), donut
# segments, and any widget state that carries a severity. Each is a
# literal; the ORDER of this tuple is the deterministic dispatch order
# a widget MUST use when mapping categories to colors (so the same
# category list always maps to the same color sequence).
LEMON_SUCCESS: Final[str] = "#2EA043"
LEMON_WARNING: Final[str] = "#D29922"
LEMON_DANGER: Final[str] = "#DA3633"
LEMON_INFO: Final[str] = "#1F6FEB"

# ── Neutrals ──
# A 5-step neutral ramp for muted/secondary widget surfaces: axis text,
# gridlines, unfilled bars, a donut's "other" slice. Ordered light→dark
# so a widget can step down emphasis deterministically.
LEMON_NEUTRALS: Final[tuple[str, ...]] = (
    "#F4F7FA",  # 0 — panel/inset background
    "#DCE5ED",  # 1 — divider / gridline
    "#9AB0C0",  # 2 — muted bar / secondary segment
    "#4F5F70",  # 3 — secondary text / axis label
    "#0F1419",  # 4 — ink (== LEMON_INK)
)

# ── Tag tints ──
# Soft background + matching ink for pill/tag chips (a stat_chip's
# label, a cite_block's source-type tag, a timeline node's kind). Each
# tint is a (background, ink) pair. The ORDER of this tuple is the
# deterministic dispatch order for tinting categories.
LEMON_TAG_TINTS: Final[tuple[tuple[str, str], ...]] = (
    ("#EEF2FF", "#1d4aff"),  # primary tint — blue
    ("#FFF7E0", "#8a6500"),  # accent tint — yellow
    ("#E6F4EA", "#1a6b33"),  # success tint — green
    ("#FFE9E7", "#9a1f1c"),  # danger tint — red
    ("#E8F1FF", "#0a4a9c"),  # info tint — blue
    ("#EEF1F4", "#384858"),  # neutral tint — slate
)

# ── Categorical dispatch sequence ──
# The ordered color sequence a categorical widget (bar_chart, donut,
# dep_graph node fills) MUST walk when assigning colors to categories.
# Walking this tuple in order — NOT a dict/set — is what makes
# "categories [A, B, C]" always map to [accent, primary, info] and
# renders byte-identical across processes. The accent leads (the
# featured/first category carries the Lemon-UI brand hook).
LEMON_CATEGORY_COLORS: Final[tuple[str, ...]] = (
    LEMON_ACCENT,    # 0 — first category (brand hook)
    LEMON_PRIMARY,   # 1
    LEMON_INFO,      # 2
    LEMON_SUCCESS,   # 3
    LEMON_WARNING,   # 4
    LEMON_DANGER,    # 5
    LEMON_NEUTRALS[2],  # 6+ — overflow stays muted, deterministic
)

# ── Geometry ──
LEMON_BORDER_WIDTH: Final[str] = "2px"
"""Every Lemon-UI widget surface carries a 2px solid LEMON_INK border.
This is the load-bearing Lemon-UI geometry constant — the chunky black
outline is what makes a widget read Lemon-UI rather than flat-SaaS."""

LEMON_BORDER: Final[str] = f"{LEMON_BORDER_WIDTH} solid {LEMON_INK}"
"""The full border shorthand a widget emits: ``2px solid #0F1419``."""

LEMON_SHADOW: Final[str] = f"4px 4px 0 0 {LEMON_INK}"
"""The Lemon-UI offset hard shadow: 4px down, 4px right, 0 blur, 0
spread, cast in ink. No blur — a hard stamp-printed shadow, not a soft
Material elevation. Applied to every elevated widget surface (cards,
chips, nodes)."""

LEMON_RADIUS: Final[str] = "6px"
"""Corner radius for widget cards/chips. Matches the chrome radius
family (tokens.css --radius: 6px) so a widget's corners agree with the
surrounding projection chrome."""

# ── Spacing scale ──
# A 4px-base spacing scale (== Tailwind's base unit) so widget padding,
# gaps, and SVG insets come from one ladder. Ordered; widgets index by
# integer step. Literal values (not calc) so emitted CSS/SVG bytes are
# stable.
LEMON_SPACING: Final[tuple[str, ...]] = (
    "0",      # 0
    "2px",    # 1 — hairline gap
    "4px",    # 2 — base unit
    "8px",    # 3 — small padding
    "12px",   # 4 — card padding
    "16px",   # 5 — block gap
    "24px",   # 6 — section gap
)

# ── Widget stylesheet (inlined CSS for widget surfaces) ──
# Widgets emit their own inline <style> (or class attributes) drawn
# from this palette. This string is the shared widget-surface CSS a
# widget MAY inline at the top of its output so repeated widgets share
# one rule block. It is OPTIONAL — a widget may also emit inline
# styles directly. Either way, the bytes come from the constants above
# so the palette is the single source of truth.
#
# Like TOKENS_CSS: no @import, no url(), no expression(). The
# zero-script gate (gate.py) runs on the full projection, widgets
# included, so this CSS MUST be script-free — it is (plain literals).
# Built as an f-string so EVERY color + geometry value DERIVES from the
# atomic constants above — no duplicated hex literal lives in this string.
# This is the M1 "tokens are the single source of truth" contract, and it
# is mechanically enforced by ``tests/test_tokens_css_derives.py`` (every
# ``#rrggbb`` in this CSS must trace to a non-``_CSS`` LEMON_* constant).
# The interpolated output is byte-identical to the prior hand-written CSS.
LEMON_WIDGET_CSS: Final[str] = f"""\
.lemon{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:{LEMON_INK};background:{LEMON_SURFACE};border:{LEMON_BORDER};border-radius:{LEMON_RADIUS};box-shadow:{LEMON_SHADOW};}}
.lemon-card{{padding:{LEMON_SPACING[4]};}}
.lemon-label{{font-size:.8rem;font-weight:600;color:{LEMON_NEUTRALS[3]};text-transform:uppercase;letter-spacing:.04em;}}
.lemon-value{{font-size:1.5rem;font-weight:700;color:{LEMON_INK};}}
.lemon-muted{{color:{LEMON_NEUTRALS[3]};font-size:.85rem;}}
.lemon-tag{{display:inline-block;padding:{LEMON_SPACING[1]} {LEMON_SPACING[3]};border-radius:9999px;font-size:.75rem;font-weight:600;}}
.lemon-axis{{stroke:{LEMON_NEUTRALS[2]};stroke-width:1;}}
.lemon-grid{{stroke:{LEMON_NEUTRALS[1]};stroke-width:1;}}
"""


# ── Widget-call seam (SPR-03 target, empty in SPR-02) ──


class WidgetRenderer(Protocol):
    """Protocol for a SPR-03 widget renderer.

    A widget partial calls ``render_widget(ctx, kind, attrs)``. In SPR-02
    this always returns a placeholder (widgets are out of scope). SPR-03
    registers concrete renderers via ``register_widget``; the renderer
    core calls them through ``render_widget`` so the call site is stable.

    The contract: a widget renderer MUST return script-free HTML (the
    zero-script gate runs on the full projection, widgets included). It
    MUST be pure (no wall-clock, no network). It MAY read tokens from
    this module.
    """

    def __call__(self, kind: str, attrs: dict) -> str: ...


_widget_registry: list[tuple[str, WidgetRenderer]] = []
"""Ordered widget registry. List (not dict) so insertion order is the
deterministic dispatch order — a doc-model always resolves the same
widget for the same kind. SPR-03 populates this; SPR-02 leaves it empty."""


def register_widget(kind: str, renderer: WidgetRenderer) -> None:
    """Register a widget renderer for ``kind`` (SPR-03). No-op-safe to
    call; the registry is module-global and ordered."""
    _widget_registry.append((kind, renderer))


def render_widget(kind: str, attrs: dict) -> str:
    """Render a widget by kind. SPR-02: always returns the placeholder
    (no widgets registered). SPR-03 will resolve registered renderers.

    The placeholder is a visible, script-free ``unsupported widget``
    block — same honesty contract as unknown blocks: never silent, never
    a crash. It deliberately reuses the unsupported-block styling so the
    visual language is consistent.
    """
    for registered_kind, renderer in _widget_registry:
        if registered_kind == kind:
            return renderer(kind, attrs)
    # SPR-02 placeholder. Deterministic: no kind-dependent variance beyond
    # the (escaped) kind string itself.
    return (
        '<div class="antiek-unsupported">'
        f"unsupported widget ({_escape_widget_kind(kind)})"
        "</div>"
    )


def _escape_widget_kind(kind: str) -> str:
    """Escape a widget kind for inline display. Keeps the placeholder
    honest even if a future caller passes a hostile kind string."""
    return (
        kind.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


__all__ = [
    "TOKENS_CSS",
    "LEMON_PRIMARY",
    "LEMON_ACCENT",
    "LEMON_INK",
    "LEMON_SURFACE",
    "LEMON_SUCCESS",
    "LEMON_WARNING",
    "LEMON_DANGER",
    "LEMON_INFO",
    "LEMON_NEUTRALS",
    "LEMON_TAG_TINTS",
    "LEMON_CATEGORY_COLORS",
    "LEMON_BORDER_WIDTH",
    "LEMON_BORDER",
    "LEMON_SHADOW",
    "LEMON_RADIUS",
    "LEMON_SPACING",
    "LEMON_WIDGET_CSS",
    "WidgetRenderer",
    "register_widget",
    "render_widget",
]
