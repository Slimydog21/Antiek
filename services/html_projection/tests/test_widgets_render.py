"""Widget behavior gates (HPRJ SPR-03 M2): no-crash, determinism, script-free.

These run over the 21 golden size-shapes (no frozen bytes needed) plus the
adversarial set. They are the contract every widget implementation must meet
regardless of its internal SVG choices: render without crashing at every
shape, produce byte-identical output for identical input, and emit nothing the
zero-script gate rejects — including when the input is hostile.
"""

from __future__ import annotations

import importlib
import os
import pathlib
import subprocess
import sys

import pytest

from services.html_projection import gate
from services.html_projection.widgets._fixtures import (
    FIXTURES,
    HOSTILE_FIXTURES,
    HOSTILE_RAW_NEEDLES,
)

KINDS = sorted(FIXTURES)
SHAPES = ("empty", "typical", "degenerate")

# Repo root: tests/ -> html_projection/ -> services/ -> <root>.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _render(kind: str, data: dict) -> str:
    """Import the widget module by kind and call its ``render``. Using
    importlib (not a package attribute) makes this robust to however the
    package ``__init__`` re-exports the seven renderers."""
    mod = importlib.import_module(f"services.html_projection.widgets.{kind}")
    return mod.render(data)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("shape", SHAPES)
def test_renders_nonempty_string(kind: str, shape: str) -> None:
    out = _render(kind, FIXTURES[kind][shape])
    assert isinstance(out, str) and out.strip(), (
        f"{kind}/{shape} must render a non-empty string"
    )


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("shape", SHAPES)
def test_deterministic(kind: str, shape: str) -> None:
    data = FIXTURES[kind][shape]
    assert _render(kind, data) == _render(kind, data), (
        f"{kind}/{shape} is not byte-deterministic"
    )


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("shape", SHAPES)
def test_script_free(kind: str, shape: str) -> None:
    # assert_script_free raises ScriptViolation on any violation.
    gate.assert_script_free(_render(kind, FIXTURES[kind][shape]))


@pytest.mark.parametrize("kind,data", HOSTILE_FIXTURES)
def test_neutralizes_hostile_input(kind: str, data: dict) -> None:
    out = _render(kind, data)
    # 1. The authoritative security bar.
    gate.assert_script_free(out)
    # 2. No active-tag opening survived unescaped.
    low = out.lower()
    for needle in HOSTILE_RAW_NEEDLES:
        assert needle not in low, (
            f"{kind} echoed an unescaped active tag {needle!r}"
        )


def test_every_contract_kind_has_a_module() -> None:
    # WIDGET_KINDS (the frozen contract order) and the fixtures must agree,
    # and every kind must import + expose render — catches a missing widget.
    from services.html_projection import widgets

    assert set(widgets.WIDGET_KINDS) == set(KINDS)
    for kind in widgets.WIDGET_KINDS:
        mod = importlib.import_module(
            f"services.html_projection.widgets.{kind}"
        )
        assert callable(getattr(mod, "render", None)), (
            f"{kind}.render must be callable"
        )


@pytest.mark.parametrize(
    "url,should_link",
    [
        ("https://ok.example/cite", True),
        ("http://ok.example", True),
        ("mailto:a@b.com", True),
        ("javascript:alert(1)", False),
        ("java\tscript:alert(1)", False),  # embedded control char
        ("JAVA SCRIPT:alert(1)", False),  # embedded space + case
        ("\x00javascript:alert(1)", False),  # leading control char
        ("vbscript:msgbox(1)", False),
        ("data:text/html,<script>alert(1)</script>", False),  # click-XSS vector
    ],
)
def test_cite_block_url_scheme_guard(url: str, should_link: bool) -> None:
    # The cite_block href is the one place a widget emits a clickable URL.
    # It must drop dangerous schemes even when obfuscated with embedded
    # control chars / whitespace / case — a plain startswith() check is not
    # enough. (Defends the link target, beyond what the zero-script gate sees.)
    out = _render("cite_block", {"title": "Source", "url": url})
    gate.assert_script_free(out)
    assert ("<a href=" in out) is should_link, (
        f"cite_block link presence wrong for {url!r}"
    )


def test_plotting_widgets_drop_non_finite() -> None:
    # float("nan")/float("inf") parse successfully, so a metrics pipeline can
    # smuggle them through `value`/`points`. The plotting widgets must treat
    # them as absent (sparkline) or zero (bar_chart, donut), never emitting a
    # "nan"/"inf" token into the SVG. Asserted by behavioral equivalence — no
    # brittle substring match.
    nan, pinf, ninf = float("nan"), float("inf"), float("-inf")

    spark_nf = _render("sparkline", {"points": [1.0, nan, pinf, 2.0, ninf, 3.0]})
    spark_clean = _render("sparkline", {"points": [1.0, 2.0, 3.0]})
    assert spark_nf == spark_clean

    bar_nf = _render(
        "bar_chart",
        {"bars": [{"label": "a", "value": pinf}, {"label": "b", "value": 5}]},
    )
    bar_zero = _render(
        "bar_chart",
        {"bars": [{"label": "a", "value": 0}, {"label": "b", "value": 5}]},
    )
    assert bar_nf == bar_zero

    donut_nf = _render(
        "donut",
        {"categories": [{"label": "a", "value": nan}, {"label": "b", "value": 3}]},
    )
    donut_zero = _render(
        "donut",
        {"categories": [{"label": "a", "value": 0}, {"label": "b", "value": 3}]},
    )
    assert donut_nf == donut_zero


# ── sketch (V1-CONNECT SPR-02): the eighth kind ────────────────────────
#
# The sketch widget is the first product importer of
# ``substrate/agent_skills``. Its whole value is that it REUSES the agent
# kernel skill rather than owning a second SVG generator, so these gates
# aim at the ways that reuse can silently rot: a forked renderer, a
# "fixed" seed contract, a hoisted import that deadlocks, an off-palette
# override, and an unbounded series reaching the skill's hard cap.


def _sketch_skill():
    from substrate.agent_skills.sketch_svg import sketch_svg

    return sketch_svg


def test_sketch_output_is_the_kernel_skill_byte_for_byte() -> None:
    # THE reuse invariant. The widget must be a parameter adapter and
    # nothing more: its bytes have to equal a direct call to the skill
    # with the widget's resolved defaults. This goes red the moment
    # anyone hand-rolls SVG in sketch.py, which is the one thing the
    # task forbids — a second renderer would fork the guarantee that an
    # agent's sketch and a projection's sketch are the same artifact.
    from services.html_projection import tokens
    from services.html_projection.widgets.sketch import LEMON_SKETCH_PALETTE

    direct = _sketch_skill()(
        width=480,
        height=300,
        seed=9,
        title="Qubit counts",
        data=[127.0, 1121.0, 105.0],
        palette=LEMON_SKETCH_PALETTE,
        ink=tokens.LEMON_INK,
    )
    through_widget = _render(
        "sketch",
        {"seed": 9, "title": "Qubit counts", "data": [127.0, 1121.0, 105.0]},
    )
    assert through_widget == direct


def test_sketch_data_mode_is_seed_invariant_by_design() -> None:
    # NOT A DEFECT, pinned so nobody "fixes" it. In data mode the sketch
    # is a deterministic VIEW OF THE DATA, so the seed cannot move it —
    # only the generative body consumes the PRNG. Both halves are
    # asserted: without the second, the first would also pass for a
    # generator that ignored the seed everywhere, which IS a defect.
    base = {"title": "residuals", "data": [3.0, 1.0, 4.0, 1.0, 5.0]}
    assert _render("sketch", {**base, "seed": 42}) == _render(
        "sketch", {**base, "seed": 43}
    )
    assert _render("sketch", {"title": "g", "seed": 7}) != _render(
        "sketch", {"title": "g", "seed": 8}
    )


def test_sketch_data_mode_never_silently_falls_back_to_generative() -> None:
    # A caller that asked for a data sketch and got abstract circles
    # would be misled about what it is looking at. An unusable series
    # renders the visible placeholder instead.
    generative = _render("sketch", {"title": "t"})
    for unusable in ([], "not-a-list", [None, "x"], [float("nan"), float("inf")]):
        out = _render("sketch", {"title": "t", "data": unusable})
        assert "no sketch" in out, f"{unusable!r} must render the placeholder"
        assert out != generative
        gate.assert_script_free(out)


def test_sketch_bounds_an_oversized_series_below_the_skill_cap() -> None:
    # The widget's MAX_VALUES must stay strictly under the skill's own
    # 500-value ceiling, so an over-cap series is SAMPLED here and the
    # skill's ValueError is unreachable from this path. Asserted, not
    # assumed: a later bump of either constant that inverts the
    # relationship turns this red.
    from services.html_projection.widgets.sketch import MAX_VALUES

    # importlib, not `import substrate.agent_skills.sketch_svg as skill`:
    # the package __init__ rebinds the `sketch_svg` ATTRIBUTE to the
    # function, so the plain import form hands back a function with no
    # module globals on it. Same shadowing the widgets package does.
    skill = importlib.import_module("substrate.agent_skills.sketch_svg")
    assert MAX_VALUES < skill._MAX_BARS

    out = _render("sketch", {"title": "wide", "data": list(range(1200))})
    gate.assert_script_free(out)
    assert out.startswith("<svg")
    # The dropped count is surfaced in the caption, never swallowed.
    assert f"+{1200 - MAX_VALUES} more" in out
    # And the skill really was handed a legal series: the caption reports
    # the sampled n, not the raw one.
    assert f"n {MAX_VALUES}" in out


def test_sketch_rejects_an_off_palette_override_whole() -> None:
    # Invariant 4 (no color that does not trace to an atomic LEMON_*
    # token) has to survive a hostile or merely sloppy caller. A palette
    # with even one non-LEMON entry falls back WHOLE, because index
    # position carries meaning and a patched palette would render a
    # composition nobody asked for.
    from services.html_projection.widgets.sketch import LEMON_SKETCH_PALETTE

    default = _render("sketch", {"title": "p", "seed": 2})
    assert (
        _render("sketch", {"title": "p", "seed": 2, "palette": ["#ff00ff", "#000000"]})
        == default
    )
    assert (
        _render(
            "sketch",
            {"title": "p", "seed": 2, "palette": [LEMON_SKETCH_PALETTE[0], "#ff00ff"]},
        )
        == default
    )
    # A fully-LEMON override IS honored — otherwise both checks above
    # would pass for a widget that ignored `palette` entirely.
    swapped = list(LEMON_SKETCH_PALETTE)
    swapped[2], swapped[4] = swapped[4], swapped[2]
    assert _render("sketch", {"title": "p", "seed": 2, "palette": swapped}) != default


def test_sketch_import_order_independence() -> None:
    # Regression gate for a circular import that is easy to reintroduce.
    # `substrate.agent_skills.sketch_svg` imports this package's `gate`,
    # and `services.html_projection.__init__` eagerly imports the
    # renderer -> the widget partial -> this widgets package. Hoisting
    # sketch.py's skill import to module scope therefore raises
    # "cannot import name 'sketch_svg' from partially initialized
    # module" in any process that imports substrate.agent_skills FIRST,
    # which tests/test_agent_skills.py:33 does. A subprocess is
    # required: in-process, sys.modules is already warm and the cycle
    # cannot form.
    program = (
        "import substrate.agent_skills\n"
        "from services.html_projection.tokens import render_widget\n"
        "out = render_widget('sketch', {'seed': 1, 'title': 't'})\n"
        "assert out.startswith('<svg'), out[:60]\n"
        "print('OK')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    assert proc.returncode == 0, (
        "importing substrate.agent_skills before services.html_projection "
        f"must work; stderr:\n{proc.stderr}"
    )
    assert proc.stdout.strip() == "OK"


def test_sketch_golden_is_stable_across_processes() -> None:
    # Determinism a same-process comparison cannot prove: a fresh
    # interpreter (fresh hash seed, fresh module state) must reproduce
    # the committed golden byte for byte. If a set/dict iteration ever
    # leaks into the sketch path, this is the test that sees it.
    golden = (
        pathlib.Path(__file__).parent / "widget_goldens" / "sketch__degenerate.html"
    ).read_text(encoding="utf-8")
    program = (
        "import importlib, sys\n"
        "from services.html_projection.widgets._fixtures import FIXTURES\n"
        "m = importlib.import_module('services.html_projection.widgets.sketch')\n"
        "sys.stdout.write(m.render(FIXTURES['sketch']['degenerate']))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        env={**os.environ, "PYTHONHASHSEED": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == golden
