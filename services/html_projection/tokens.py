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
    "WidgetRenderer",
    "register_widget",
    "render_widget",
]
