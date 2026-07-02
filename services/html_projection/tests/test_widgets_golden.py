"""Golden-file byte tests (HPRJ SPR-03 M2): 7 widgets x 3 shapes = 21 goldens.

Each widget output is byte-compared against a committed golden under
``widget_goldens/<kind>__<shape>.html``. The goldens are GENERATED from the
code (never hand-written), then human-reviewed, then frozen — so a golden that
"needs updating" forces the honest question (did the output improve or break?)
rather than a silent regeneration.

Regenerate (orchestrator only, after reviewing the diff):

    ANTIEK_UPDATE_GOLDENS=1 ./.venv/bin/python -m pytest \\
        services/html_projection/tests/test_widgets_golden.py -q

A missing golden in non-update mode is a hard failure (not an auto-write) so
CI can never pass by minting goldens for code it has never seen.
"""

from __future__ import annotations

import importlib
import os
import pathlib

import pytest

from services.html_projection.widgets._fixtures import FIXTURES

_GOLDENS = pathlib.Path(__file__).parent / "widget_goldens"
_UPDATE = os.environ.get("ANTIEK_UPDATE_GOLDENS") == "1"
KINDS = sorted(FIXTURES)
SHAPES = ("empty", "typical", "degenerate")


def _render(kind: str, data: dict) -> str:
    mod = importlib.import_module(f"services.html_projection.widgets.{kind}")
    return mod.render(data)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("shape", SHAPES)
def test_golden(kind: str, shape: str) -> None:
    out = _render(kind, FIXTURES[kind][shape])
    path = _GOLDENS / f"{kind}__{shape}.html"

    if _UPDATE:
        _GOLDENS.mkdir(parents=True, exist_ok=True)
        path.write_text(out, encoding="utf-8")
        pytest.skip(f"updated golden {path.name}")

    assert path.exists(), (
        f"missing golden {path.name}; generate with ANTIEK_UPDATE_GOLDENS=1 "
        f"then review the diff before committing"
    )
    expected = path.read_text(encoding="utf-8")
    assert out == expected, (
        f"{kind}/{shape} output drifted from its frozen golden. If the new "
        f"output is correct, regenerate with ANTIEK_UPDATE_GOLDENS=1 and "
        f"explain the change; do not blindly accept it."
    )
