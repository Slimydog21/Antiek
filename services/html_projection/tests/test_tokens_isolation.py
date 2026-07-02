"""M1 isolation gate (HPRJ SPR-03).

``tokens.py`` is the shared visual contract: SPR-02's renderer inlines it,
and every SPR-03 widget reads its palette from it. For that contract to be
the *single source of truth* it must sit at the bottom of the import graph —
it may not import any other module from the html_projection package
(widgets, renderer, partials, gate, island, …). If it did, "the tokens are
the source of truth" would be a lie the moment a widget's import cycle
reordered evaluation.

This test parses ``tokens.py`` statically (so it never executes a partially
constructed package) and asserts none of its imports reference the
``services.html_projection`` package.
"""

from __future__ import annotations

import ast
import pathlib

_TOKENS = pathlib.Path(__file__).resolve().parents[1] / "tokens.py"
_PKG = "services.html_projection"


def _imported_modules(source: str) -> list[str]:
    tree = ast.parse(source)
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # node.level > 0 is a relative import (from . / from .foo) — also
            # an intra-package dependency we forbid.
            base = node.module or ""
            if node.level and node.level > 0:
                mods.append(f"<relative level={node.level}>:{base}")
            else:
                mods.append(base)
    return mods


def test_tokens_imports_nothing_from_the_html_projection_package() -> None:
    imported = _imported_modules(_TOKENS.read_text(encoding="utf-8"))
    offenders = [
        m
        for m in imported
        if m.startswith(_PKG)
        or "html_projection" in m
        or "widgets" in m
        or m.startswith("<relative")
    ]
    assert not offenders, (
        "tokens.py must be import-isolated (the single visual source of "
        f"truth), but it imports: {offenders}"
    )


def test_tokens_imports_standalone() -> None:
    # A fresh import must succeed with no side effects from the rest of the
    # package — i.e. importing tokens does not require any widget module to
    # be importable first.
    import importlib

    mod = importlib.import_module("services.html_projection.tokens")
    assert hasattr(mod, "LEMON_WIDGET_CSS")
    assert hasattr(mod, "TOKENS_CSS")
