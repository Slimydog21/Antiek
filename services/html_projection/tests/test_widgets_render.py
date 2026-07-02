"""Widget behavior gates (HPRJ SPR-03 M2): no-crash, determinism, script-free.

These run over the 21 golden size-shapes (no frozen bytes needed) plus the
adversarial set. They are the contract every widget implementation must meet
regardless of its internal SVG choices: render without crashing at every
shape, produce byte-identical output for identical input, and emit nothing the
zero-script gate rejects — including when the input is hostile.
"""

from __future__ import annotations

import importlib

import pytest

from services.html_projection import gate
from services.html_projection.widgets._fixtures import (
    FIXTURES,
    HOSTILE_FIXTURES,
    HOSTILE_RAW_NEEDLES,
)

KINDS = sorted(FIXTURES)
SHAPES = ("empty", "typical", "degenerate")


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
