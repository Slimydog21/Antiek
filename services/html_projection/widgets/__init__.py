"""Lemon-UI widget library (HPRJ SPR-03).

Seven pure-function widgets, each ``widget(data) -> str``: a stat_chip,
bar_chart, sparkline, donut, timeline, dep_graph, and cite_block. Each
takes a plain ``dict`` (the "input contract" below), returns a single
script-free HTML/SVG string, and reads its palette + geometry from
``services.html_projection.tokens`` (the Lemon-UI constants:
``LEMON_PRIMARY`` #1d4aff, ``LEMON_ACCENT`` #F9BD2B, the semantic set,
``LEMON_BORDER`` 2px solid ink, ``LEMON_SHADOW`` 4px offset hard
shadow). The fan-out builders implement each widget to its contract.

INVARIANTS (master-spec, enforced by the gate on every widget output):

1. SCRIPT-FREE. No ``<script>``, no ``on*=`` attribute, no
   ``javascript:``/``vbscript:`` scheme, no external ``src``/``href``
   asset, no CSS ``expression()`` or ``url(http...)``. The zero-script
   gate (``services.html_projection.gate.assert_script_free``) MUST
   pass on every widget's return value — widget tests run it. A widget
   is pure SVG/CSS; the §7 daemon ingests artifacts autonomously, so a
   script in a widget is an RCE vector.

2. DETERMINISTIC. Same ``data`` -> byte-identical output. No wall-clock,
   no randomness, no dict/set iteration whose order varies. Categorical
   color assignment walks ``tokens.LEMON_CATEGORY_COLORS`` in index
   order (a tuple, not a set/dict) so a category list always maps to the
   same color sequence. Any optional field absent from ``data`` is
   omitted deterministically (never a random placeholder).

3. SELF-CONTAINED. No external src/href. Inline SVG + inline CSS only.
   A widget MAY inline ``tokens.LEMON_WIDGET_CSS`` (or emit inline
   ``style=`` attributes drawn from the same constants); it MUST NOT
   ``@import`` or ``url()`` an external resource.

4. LEMON-UI PALETTE. 2px solid black borders (``LEMON_BORDER``), 4px
   offset hard shadows (``LEMON_SHADOW``), yellow accent #F9BD2B,
   blue primary #1d4aff. A widget reads colors from ``tokens`` — never
   a bare hex literal — so the palette is the single source of truth.

ESCAPING. All caller-supplied strings (labels, values, URLs, quotes,
node ids) are HTML-escaped via ``services.html_projection.escape``
(``escape_text`` for element text, ``escape_attr`` for attribute
values) before insertion. A widget never trusts its input to be markup-
free. URLs that may appear in an ``href`` are additionally checked to
carry no ``javascript:``/``vbscript:`` scheme (the gate catches this
too, but a widget rejects early with a deterministic fallback rather
than emitting bytes the gate would flag).

NULLABILITY CONVENTION. "Optional" means the key MAY be absent OR
``None``; both are treated identically (the field is omitted from the
output). A widget never raises on a missing optional field. A missing
REQUIRED field renders a visible, deterministic placeholder (never a
crash, never a silent empty string) — the same honesty contract as the
renderer's unsupported-block fallback.

INPUT CONTRACTS
---------------
Each contract below names the ``data`` dict shape: required keys,
optional keys, types, and nullability. Types are Python runtime types
(JSON-decoded); a widget coerces with ``str()``/``int()``/``float()``
defensively and never assumes a hostile caller's types.

1. stat_chip(data) -> str
   A labeled stat with an optional delta. Renders a compact Lemon-UI
   chip: a small-caps label, a large value, and (if present) a colored
   delta pill.
   ``data`` shape:
     - ``label``   : str  — REQUIRED. The stat name (e.g. "Latency").
     - ``value``   : str | int | float — REQUIRED. The stat value;
                       coerced to str for display.
     - ``delta``   : str | int | float | None — OPTIONAL. A change
                       since the prior period. When present AND numeric
                       (or a string beginning with ``+``/``-``), the
                       pill is tinted success (up) / danger (down);
                       a non-numeric delta renders as a neutral pill.
     - ``delta_label`` : str | None — OPTIONAL. Overrides the pill text
                       (e.g. "vs last week"); defaults to the delta
                       value itself.
     - ``tone``    : str | None — OPTIONAL. One of
                       ``"primary"|"accent"|"success"|"warning"|"danger"|"info"|"neutral"``;
                       sets the chip's accent edge. Default ``"accent"``.
                       Unknown tones fall back to ``"neutral"``.

2. bar_chart(data) -> str
   Categorical bars: one bar per category, lengths scaled to the max
   value. Pure SVG (no <script>). Horizontal bars, label below each.
   ``data`` shape:
     - ``bars``    : list[dict] — REQUIRED. Each dict:
                       ``{"label": str, "value": int|float}``.
                       ``label`` REQUIRED; ``value`` REQUIRED (coerced
                       to float; non-numeric -> 0). Empty list -> a
                       deterministic "no data" placeholder.
     - ``unit``    : str | None — OPTIONAL. A suffix rendered on the
                       axis/value (e.g. "ms", "%"). Default none.
     - ``max``     : int | float | None — OPTIONAL. Overrides the
                       scale max. Default: the max bar value (or 1 if
                       all-zero/empty so bars aren't div-by-zero).
     - ``title``   : str | None — OPTIONAL. A heading above the chart.

3. sparkline(data) -> str
   A numeric trend line. Pure SVG polyline scaled to the data range;
   no axis labels (it's a glance, not a read). The stroke is
   ``LEMON_ACCENT``.
   ``data`` shape:
     - ``points``  : list[int|float] — REQUIRED. The series. Coerced
                       to float; non-numeric entries dropped. Fewer
                       than 2 points -> a deterministic "no trend"
                       placeholder (a single point has no line).
     - ``width``   : int | None — OPTIONAL. SVG viewBox width in px.
                       Default 120.
     - ``height``  : int | None — OPTIONAL. SVG viewBox height in px.
                       Default 32.
     - ``stroke``  : str | None — OPTIONAL. Override stroke color
                       (a palette constant). Default ``LEMON_ACCENT``.

4. donut(data) -> str
   A proportional donut: one arc segment per category, sized by
   fraction of the total. Pure SVG ``<circle>`` with ``stroke-dasharray``
   segments (no <script>, no animation). Categories colored by walking
   ``LEMON_CATEGORY_COLORS`` in order.
   ``data`` shape:
     - ``categories`` : list[dict] — REQUIRED. Each dict:
                          ``{"label": str, "value": int|float}``.
                          ``label`` REQUIRED; ``value`` REQUIRED
                          (coerced to float; non-numeric -> 0; negative
                          clamped to 0). Empty list OR all-zero total ->
                          a deterministic "no data" placeholder.
     - ``size``       : int | None — OPTIONAL. SVG viewBox px (square).
                          Default 120.
     - ``thickness``  : int | None — OPTIONAL. Donut ring stroke width
                          in px. Default 16.
     - ``title``      : str | None — OPTIONAL. Heading above the donut.

5. timeline(data) -> str
   Ordered events rendered as a vertical Lemon-UI timeline: a 2px ink
   spine, a node per event (filled circle in the event's tone), the
   label + ``at`` + optional ``detail``. Events render in LIST ORDER —
   the list IS the deterministic order (oldest first by convention, but
   the widget does not sort).
   ``data`` shape:
     - ``events``  : list[dict] — REQUIRED. Each dict:
                       ``{"label": str, "at": str, "detail": str|None,
                         "tone": str|None}``.
                       ``label`` REQUIRED. ``at`` REQUIRED (a display
                       string, e.g. "2026-05-21" or "T+3d"; the widget
                       does NOT parse dates). ``detail`` OPTIONAL
                       (rendered as muted secondary text). ``tone``
                       OPTIONAL (same vocabulary as stat_chip; default
                       ``"accent"``). Empty list -> "no events"
                       placeholder.
     - ``title``   : str | None — OPTIONAL. Heading.

6. dep_graph(data) -> str
   A dependency graph as script-free SVG: nodes as Lemon-UI rectangles
   (2px ink border, 4px offset shadow), edges as straight/bent ink
   lines with arrowheads. Laid out on a deterministic grid (rows by
   topological rank; ties broken by the node's LIST INDEX, never by
   dict/set order) so the same graph always renders the same geometry.
   ``data`` shape:
     - ``nodes``   : list[dict] — REQUIRED. Each dict:
                       ``{"id": str, "label": str, "tone": str|None}``.
                       ``id`` REQUIRED (unique; duplicates keep first
                       occurrence). ``label`` REQUIRED (falls back to
                       ``id`` if absent). ``tone`` OPTIONAL (default
                       ``"primary"``; root nodes may use ``"accent"``).
                       Empty list -> "no nodes" placeholder.
     - ``edges``   : list[dict] — OPTIONAL (default []). Each dict:
                       ``{"from": str, "to": str}`` — both REQUIRED,
                       referencing node ``id``s. Edges to/from unknown
                       ids are dropped deterministically (never a
                       crash). Edges render in LIST ORDER.
     - ``direction`` : str | None — OPTIONAL. ``"down"`` (default) or
                       ``"right"`` — the layout axis.
     - ``title``   : str | None — OPTIONAL. Heading.

7. cite_block(data) -> str
   A citation block: the source title, a link (the URL, rendered as
   the link text or a "source" tag — never an external asset fetch, the
   gate allows non-javascript hrefs as references), and an optional
   pull-quote. Renders as a Lemon-UI card with a left accent rule.
   ``data`` shape:
     - ``title``   : str — REQUIRED. The source title (e.g. "PostHog
                       docs §3").
     - ``url``     : str | None — OPTIONAL. The source URL. If present
                       AND not a ``javascript:``/``vbscript:`` scheme,
                       rendered as an ``<a href="...">`` (escaped). A
                       javascript:/vbscript: URL is dropped (gate would
                       flag it; the widget rejects early). Absent ->
                       no link, title only.
     - ``quote``   : str | None — OPTIONAL. A pull-quote from the
                       source, rendered as italic indented prose.
     - ``accessed``: str | None — OPTIONAL. A display "accessed on"
                       string (the widget does NOT parse dates).
     - ``tone``    : str | None — OPTIONAL. Accent rule tone (default
                       ``"accent"``).

PUBLIC API
----------
Each widget is exposed as a submodule with a ``render(data) -> str``
function (e.g. ``services.html_projection.widgets.stat_chip.render``).
The package ``__init__`` re-exports each ``render`` under the widget
name for convenience once the fan-out lands the implementations; until
then this module is the shared SPEC the builders implement to.

The tokens module is the single visual contract:
``services.html_projection.tokens`` (``LEMON_*`` constants). Widgets
import from there; they do NOT redefine palette values.
"""

from __future__ import annotations

from services.html_projection import tokens

from . import bar_chart as _bar_chart_module
from . import cite_block as _cite_block_module
from . import dep_graph as _dep_graph_module
from . import donut as _donut_module
from . import sparkline as _sparkline_module
from . import stat_chip as _stat_chip_module
from . import timeline as _timeline_module

# The seven widget kinds, in the canonical order the spec lists them.
# Used by the fan-out builders + any registry/dispatch. A tuple (not a
# set) so the order is deterministic.
WIDGET_KINDS = (
    "stat_chip",
    "bar_chart",
    "sparkline",
    "donut",
    "timeline",
    "dep_graph",
    "cite_block",
)

stat_chip = _stat_chip_module.render
bar_chart = _bar_chart_module.render
sparkline = _sparkline_module.render
donut = _donut_module.render
timeline = _timeline_module.render
dep_graph = _dep_graph_module.render
cite_block = _cite_block_module.render


def _stat_chip_adapter(kind: str, attrs: dict) -> str:
    return _stat_chip_module.render(attrs)


def _bar_chart_adapter(kind: str, attrs: dict) -> str:
    return _bar_chart_module.render(attrs)


def _sparkline_adapter(kind: str, attrs: dict) -> str:
    return _sparkline_module.render(attrs)


def _donut_adapter(kind: str, attrs: dict) -> str:
    return _donut_module.render(attrs)


def _timeline_adapter(kind: str, attrs: dict) -> str:
    return _timeline_module.render(attrs)


def _dep_graph_adapter(kind: str, attrs: dict) -> str:
    return _dep_graph_module.render(attrs)


def _cite_block_adapter(kind: str, attrs: dict) -> str:
    return _cite_block_module.render(attrs)


tokens.register_widget("stat_chip", _stat_chip_adapter)
tokens.register_widget("bar_chart", _bar_chart_adapter)
tokens.register_widget("sparkline", _sparkline_adapter)
tokens.register_widget("donut", _donut_adapter)
tokens.register_widget("timeline", _timeline_adapter)
tokens.register_widget("dep_graph", _dep_graph_adapter)
tokens.register_widget("cite_block", _cite_block_adapter)

__all__ = [
    "WIDGET_KINDS",
    "stat_chip",
    "bar_chart",
    "sparkline",
    "donut",
    "timeline",
    "dep_graph",
    "cite_block",
]
