"""Skill 3 of 3 — ``sketch_svg``: Processing/p5-inspired deterministic SVG.

A research agent wants a *visual sketch* of what it mined — a seeded
generative composition, or a faithful little chart of a distribution —
as an artifact that can be embedded in an Antiek HTML asset. This skill
emits a self-contained, SCRIPT-FREE SVG, pure function of its inputs.

P5 INSPIRATION, DETERMINISM INSTEAD OF RANDOMNESS: the composition model
is p5-style (a canvas, a palette, circles/lines driven by a PRNG, the
"nested circles in a grid" tutorial energy) but ``random()`` is replaced
by a seeded splitmix64 PRNG (``SeededRng``) — the same seed always
renders the same bytes. Nothing here reads the clock, the environment,
or the filesystem; the SVG is a pure function of ``(seed, width, height,
title, data, palette)``, which is what makes it testable and stable
across regenerations.

THE GATE IS REUSED, NOT REIMPLEMENTED: every emitted SVG is validated
against ``services.html_projection.gate`` (the zero-script gate every
Antiek projection must pass — master-spec SCRIPT-FREE invariant) before
it is returned. The generator only ever emits elements the gate passes
by construction (no ``<script>``, no ``on*`` attributes, no external
``src``/``href``, no ``style`` attributes at all, presentation
attributes only), so the gate call is a backstop — but a live one: if a
future edit ever introduces a violation, the skill raises
``ScriptViolation`` loudly at generation time instead of shipping a
poisoned artifact to the autonomous-ingest daemon. One consequence,
documented: a ``title`` containing gate-flagged byte sequences (e.g.
``src=javascript:``) raises — the gate is deliberately
position-conservative, and failing at generation beats failing at
ingest.

SCULPT BOUNDS: ``data`` (when given) must be non-empty and finite, and
is capped at 500 values — a sketch with more bars than that is
unreadable, and the skill's mandate is a sketch, not a plot engine.
``palette`` colors must be ``#RRGGBB``; ``width``/``height`` must be
positive. Every violation is a loud ``ValueError`` naming the offending
input — this is the bounded-sculpting contract the kernel-skills spec
asks for.
"""

from __future__ import annotations

import math
import re
import statistics
from collections.abc import Sequence
from html import escape

from services.html_projection.gate import assert_script_free
from substrate.agent_skills.manifest import SkillManifest, SkillParameter

__all__ = ["SeededRng", "sketch_svg"]

# Canvas bounds for a sketch: 500 bars is already far past readable;
# anything bigger is a plot-engine request, not a sketch request.
_MAX_BARS = 500

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# p5-tutorial-adjacent palette: dark ground + four saturated voices +
# one pale accent. User palettes may override; only the first (ground)
# and the remaining voice colors are load-bearing (>= 2 colors).
DEFAULT_PALETTE: tuple[str, ...] = (
    "#20212c",  # ground
    "#ff6b6b",  # coral
    "#4ecdc4",  # teal
    "#ffe66d",  # butter
    "#a8e6cf",  # mint
    "#d8b4fe",  # lilac
)


class SeededRng:
    """Deterministic splitmix64 PRNG (pure Python, no ``random`` import).

    splitmix64 is a well-characterized 64-bit PRNG with good statistical
    quality for generative-art jitter and a trivial pure-Python
    implementation. The same seed always yields the same stream — this
    is the ``random()`` of the p5 sketch, minus the nondeterminism.
    """

    def __init__(self, seed: int) -> None:
        self._state = seed & 0xFFFFFFFFFFFFFFFF

    def next_u64(self) -> int:
        """Next 64-bit value; advances the state."""
        self._state = (self._state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self._state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return (z ^ (z >> 31)) & 0xFFFFFFFFFFFFFFFF

    def uniform(self, lo: float = 0.0, hi: float = 1.0) -> float:
        """Uniform float in [lo, hi), deterministic given the seed."""
        return lo + (hi - lo) * (self.next_u64() >> 11) * (1.0 / (1 << 53))

    def randint(self, lo: int, hi: int) -> int:
        """Uniform int in [lo, hi], deterministic given the seed."""
        return lo + int(self.next_u64() % (hi - lo + 1))


def _num(value: float) -> str:
    """Deterministic, locale-independent float rendering for attributes."""
    return f"{value:.2f}"


def _attrs(pairs: Sequence[tuple[str, str]]) -> str:
    """Render attribute pairs as one tag-interior string, values escaped."""
    return " ".join(f'{k}="{escape(v, quote=True)}"' for k, v in pairs)


def _el(tag: str, attrs: Sequence[tuple[str, str]], content: str = "") -> str:
    """One SVG element with presentation attributes only (never ``style``)."""
    interior = _attrs(attrs)
    if content:
        return f"<{tag} {interior}>{content}</{tag}>"
    return f"<{tag} {interior} />"


def _validate_canvas(width: int, height: int) -> None:
    if isinstance(width, bool) or isinstance(height, bool) or width < 1 or height < 1:
        raise ValueError(
            f"sketch_svg: width and height must be positive ints, got ({width}, {height})"
        )


def _validate_data(data: Sequence[float]) -> None:
    if not data:
        raise ValueError("sketch_svg: data must be non-empty")
    if len(data) > _MAX_BARS:
        raise ValueError(
            f"sketch_svg: data is capped at {_MAX_BARS} values, got {len(data)}"
        )
    for i, v in enumerate(data):
        if not math.isfinite(v):
            raise ValueError(f"sketch_svg: data[{i}] must be finite, got {v!r}")


def _validate_palette(palette: Sequence[str]) -> None:
    if len(palette) < 2:
        raise ValueError("sketch_svg: palette needs >= 2 colors (ground + voices)")
    for c in palette:
        if not _COLOR_RE.fullmatch(c):
            raise ValueError(f"sketch_svg: palette colors must be #RRGGBB, got {c!r}")


def _svg_document(
    body: str,
    *,
    width: int,
    height: int,
    title: str,
    description: str,
) -> str:
    """Assemble the full SVG document around ``body``.

    Text is escaped (``<title>``/``<desc>`` carry the caption, never an
    ``aria-label`` attribute, so no attribute surface exists for
    handler-shaped names). The gate runs on the assembled document — the
    same bytes a consumer would embed.
    """
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        'role="img">'
        f"<title>{escape(title)}</title>"
        f"<desc>{escape(description)}</desc>"
        f"{body}</svg>"
    )
    # The zero-script gate, live: an SVG that would fail ingest never
    # leaves this function.
    assert_script_free(svg)
    return svg


def _generative_body(
    *,
    width: int,
    height: int,
    seed: int,
    palette: Sequence[str],
) -> str:
    """p5-flavored generative body: a jittered grid of nested-circle nodes.

    The composition is the classic "nested circles in a grid" sketch:
    one node per cell, seeded position jitter, three concentric rings in
    the voice colors, and a sparse set of connecting lines between
    neighbors. Everything derives from ``SeededRng(seed)``.
    """
    rng = SeededRng(seed)
    parts: list[str] = [
        _el(
            "rect",
            (("x", "0"), ("y", "0"), ("width", str(width)), ("height", str(height)), ("fill", palette[0])),
        )
    ]
    cols, rows = 5, 4
    cell_w = width / cols
    cell_h = height / rows
    voice_count = len(palette) - 1  # palette[0] is the ground

    nodes: list[tuple[float, float, float]] = []
    for r in range(rows):
        for c in range(cols):
            cx = (c + 0.5) * cell_w + rng.uniform(-1.0, 1.0) * cell_w * 0.12
            cy = (r + 0.5) * cell_h + rng.uniform(-1.0, 1.0) * cell_h * 0.12
            radius = min(cell_w, cell_h) * 0.32 * (0.6 + 0.4 * rng.uniform())
            nodes.append((cx, cy, radius))

    # Sparse connecting lines (seeded subset of neighbors).
    for i in range(len(nodes) - 1):
        if rng.uniform() < 0.32:
            x1, y1, _ = nodes[i]
            x2, y2, _ = nodes[i + 1]
            parts.append(
                _el(
                    "line",
                    (
                        ("x1", _num(x1)),
                        ("y1", _num(y1)),
                        ("x2", _num(x2)),
                        ("y2", _num(y2)),
                        ("stroke", palette[1]),
                        ("stroke-width", "1.5"),
                        ("stroke-opacity", "0.35"),
                    ),
                )
            )

    # Nested rings per node: three shrinking circles in voice colors +
    # one outer outline ring.
    for cx, cy, radius in nodes:
        for i in range(3):
            parts.append(
                _el(
                    "circle",
                    (
                        ("cx", _num(cx)),
                        ("cy", _num(cy)),
                        ("r", _num(radius * (1.0 - 0.3 * i))),
                        ("fill", palette[1 + (i % voice_count)]),
                        ("fill-opacity", "0.85"),
                    ),
                )
            )
        parts.append(
            _el(
                "circle",
                (
                    ("cx", _num(cx)),
                    ("cy", _num(cy)),
                    ("r", _num(radius)),
                    ("fill", "none"),
                    ("stroke", palette[1]),
                    ("stroke-width", "2"),
                    ("stroke-opacity", "0.6"),
                ),
            )
        )
    return "".join(parts)


def _data_body(
    *,
    width: int,
    height: int,
    data: Sequence[float],
    palette: Sequence[str],
    title: str,
) -> str:
    """Data-driven body: a faithful bar sketch of ``data``.

    Bars sit on a floor line; when the data goes negative the baseline
    moves to the zero line and bars draw in both directions (negative
    bars in the accent color). Value dots mark each bar top; a caption
    carries min/max/mean/n. All text is escaped; no labels when there
    are more bars than readable (the caption still tells the story).
    """
    floor_y = height * 0.86
    top_y = height * 0.12
    n = len(data)
    vmin = min(data)
    vmax = max(data)
    span = vmax - vmin
    scale = (floor_y - top_y) / span if span > 0 else 0.0
    zero_y = floor_y - (0.0 - vmin) * scale if vmin < 0 else floor_y
    slot = width / n
    bar_w = max(slot * 0.72, 1.0)

    parts: list[str] = [
        _el(
            "rect",
            (("x", "0"), ("y", "0"), ("width", str(width)), ("height", str(height)), ("fill", palette[0])),
        ),
        _el(
            "line",
            (
                ("x1", "0"),
                ("y1", _num(zero_y)),
                ("x2", str(width)),
                ("y2", _num(zero_y)),
                ("stroke", palette[1]),
                ("stroke-width", "2"),
            ),
        ),
    ]
    show_labels = n <= 20
    voice_count = len(palette) - 1
    dot_color = palette[1 + (2 % voice_count)]
    for i, v in enumerate(data):
        x = i * slot + slot * 0.14
        # Bars measure from the zero line (vmin < 0) or the floor: the
        # height is |v| * scale in both branches.
        height_v = abs(v) * scale
        if vmin < 0:
            y = zero_y - v * scale if v >= 0 else zero_y
            color = palette[2] if v >= 0 else palette[3]
        else:
            y = floor_y - v * scale
            color = palette[2]
        parts.append(
            _el(
                "rect",
                (
                    ("x", _num(x)),
                    ("y", _num(y)),
                    ("width", _num(bar_w)),
                    ("height", _num(max(height_v, 1.0))),
                    ("fill", color),
                ),
            )
        )
        parts.append(
            _el(
                "circle",
                (
                    ("cx", _num(x + bar_w / 2)),
                    ("cy", _num(y)),
                    ("r", "2"),
                    ("fill", dot_color),
                ),
            )
        )
        if show_labels:
            label_y = y - 6 if v >= 0 else y + 14
            parts.append(
                _el(
                    "text",
                    (
                        ("x", _num(x + bar_w / 2)),
                        ("y", _num(label_y)),
                        ("font-family", "system-ui, sans-serif"),
                        ("font-size", "9"),
                        ("fill", "#e8e8f0"),
                        ("text-anchor", "middle"),
                    ),
                    _num(v),
                )
            )

    mean = statistics.fmean(data)
    parts.append(
        _el(
            "text",
            (
                ("x", _num(width / 2)),
                ("y", _num(height - 10)),
                ("font-family", "system-ui, sans-serif"),
                ("font-size", "11"),
                ("fill", "#e8e8f0"),
                ("text-anchor", "middle"),
            ),
            f"{escape(title)} — n {n} · min {_num(vmin)} · max {_num(vmax)} · mean {_num(mean)}",
        )
    )
    return "".join(parts)


def sketch_svg(
    *,
    width: int = 640,
    height: int = 400,
    seed: int = 0,
    title: str = "untitled sketch",
    data: Sequence[float] | None = None,
    palette: Sequence[str] | None = None,
) -> str:
    """Emit a deterministic, script-free SVG sketch.

    Parameters
    ----------
    width, height:
        Canvas size in px; positive ints.
    seed:
        PRNG seed. Same seed + same inputs = identical bytes.
    title:
        Sketch title; rendered in the ``<title>`` element and the data
        caption. Note the gate runs on the final document: a title
        containing gate-flagged byte sequences raises ``ScriptViolation``
        (failing at generation beats failing at ingest).
    data:
        When given, a finite, non-empty series (<= 500 values) rendered
        as a faithful bar sketch with a zero-aware baseline. When None,
        a generative nested-circle composition on the seed.
    palette:
        ``#RRGGBB`` colors, >= 2: palette[0] is the ground, the rest are
        voice colors.

    Returns
    -------
    str
        The complete SVG document, verified by the zero-script gate
        (``services.html_projection.gate.assert_script_free``) before
        return — embedding it in an Antiek HTML asset cannot introduce
        a script violation.

    Raises
    ------
    ValueError
        On invalid canvas/data/palette inputs (loud, names the input).
    services.html_projection.gate.ScriptViolation
        If the assembled document ever trips the gate (a backstop that
        should be unreachable; a bug in this module if it fires).
    """
    _validate_canvas(width, height)
    effective_palette = tuple(palette) if palette is not None else DEFAULT_PALETTE
    _validate_palette(effective_palette)
    if data is None:
        body = _generative_body(width=width, height=height, seed=seed, palette=effective_palette)
        description = f"Generative sketch (seed {seed}): nested-circle nodes in a grid"
        return _svg_document(
            body, width=width, height=height, title=title, description=description
        )
    _validate_data(data)
    body = _data_body(width=width, height=height, data=data, palette=effective_palette, title=title)
    description = (
        f"Data sketch of {len(data)} values: min {_num(min(data))} "
        f"max {_num(max(data))} mean {_num(statistics.fmean(data))}"
    )
    return _svg_document(
        body, width=width, height=height, title=title, description=description
    )


MANIFEST = SkillManifest(
    name="sketch_svg",
    summary="Deterministic Processing/p5-inspired generative SVG, verified script-free.",
    description=(
        "One call gets a self-contained SVG: a seeded p5-style generative composition "
        "(nested circles, sparse connectors, palette discipline) or a faithful bar "
        "sketch of a mined distribution. Same seed + inputs = identical bytes; the "
        "output is always passed through the zero-script gate before it is returned."
    ),
    entrypoint=sketch_svg,
    functions=("sketch_svg",),
    parameters=(
        SkillParameter("width", "int = 640", "Canvas width px; positive.", required=False, default="640"),
        SkillParameter("height", "int = 400", "Canvas height px; positive.", required=False, default="400"),
        SkillParameter("seed", "int = 0", "PRNG seed; same seed + inputs = same bytes.", required=False, default="0"),
        SkillParameter("title", "str = 'untitled sketch'", "Sketch title (escaped into <title>/caption).", required=False, default="'untitled sketch'"),
        SkillParameter("data", "Sequence[float] | None", "Series to sketch as bars (finite, non-empty, <= 500).", required=False, default="None"),
        SkillParameter("palette", "Sequence[str] | None", ">= 2 #RRGGBB colors; [0] is ground, rest are voices.", required=False, default="default palette"),
    ),
    returns=(
        "str — the complete SVG document, verified via "
        "services.html_projection.gate.assert_script_free before return (embedding it "
        "cannot introduce a script violation)."
    ),
    safety=(
        "SCRIPT-FREE by construction AND by the live gate: the zero-script gate is "
        "reused (not reimplemented) on every emitted document before it is returned.",
        "Deterministic: pure function of (seed, width, height, title, data, palette) "
        "— no clock, no environment, no filesystem.",
        "Self-contained: presentation attributes only, no external src/href/style, no "
        "network fetch surface.",
        "Bounded sculpt: data capped at 500 values, palette validated as #RRGGBB, "
        "inputs named in loud ValueErrors.",
    ),
    examples=(
        "svg = sketch_svg(seed=7, title='price distribution', data=[1.5, 2.0, 2.5, 1.0])",
        "svg = sketch_svg(seed=42, width=800, height=500, title='generative study')",
        "sketch_svg(seed=1, data=[-3, -1, 2, 4])  # negative values draw a zero baseline",
    ),
)
