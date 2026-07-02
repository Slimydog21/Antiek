"""Widget seam wired into the renderer — antiek_widget renders SPR-03 widgets.

Closes the gap where the seven widgets were built + registered into the tokens
seam but unreachable from the renderer (no block type used `contract.widget`).
"""

from __future__ import annotations

from services.html_projection.context import RenderContext
from services.html_projection.contract import contract_for_tiptap_type
from services.html_projection.gate import assert_script_free
from services.html_projection.island import extract_island
from services.html_projection.renderer import render


def _doc(nodes, title="t"):
    return {"content": nodes, "title": title, "edges": []}


def test_widget_block_type_is_in_contract():
    c = contract_for_tiptap_type("antiek_widget")
    assert c is not None
    assert c.partial == "widget" and c.widget is True
    assert contract_for_tiptap_type("widget") is c  # bare alias maps too


def test_stat_chip_widget_renders_in_a_document():
    node = {
        "type": "antiek_widget",
        "attrs": {"kind": "stat_chip", "label": "Latency", "value": "42ms", "tone": "success"},
    }
    html = render(_doc([node]), RenderContext())
    assert "Latency" in html and "42ms" in html
    assert_script_free(html)


def test_bar_chart_widget_via_data_attr():
    node = {
        "type": "antiek_widget",
        "attrs": {
            "kind": "bar_chart",
            "data": {"title": "Sources", "bars": [{"label": "a", "value": 3}, {"label": "b", "value": 5}]},
        },
    }
    html = render(_doc([node]), RenderContext())
    assert "Sources" in html
    assert_script_free(html)


def test_unknown_widget_kind_is_placeholder_not_crash():
    html = render(_doc([{"type": "antiek_widget", "attrs": {"kind": "nope_widget"}}]), RenderContext())
    assert "unsupported widget" in html.lower()


def test_kindless_widget_is_placeholder():
    html = render(_doc([{"type": "antiek_widget", "attrs": {}}]), RenderContext())
    assert "unsupported widget" in html.lower()


def test_widget_block_island_round_trips():
    dm = _doc([{"type": "antiek_widget", "attrs": {"kind": "stat_chip", "label": "X", "value": "1"}}])
    assert extract_island(render(dm, RenderContext())) == dm
