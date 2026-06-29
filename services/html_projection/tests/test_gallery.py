"""Gallery gates (HPRJ SPR-03 M3): gate-clean, complete, never-drifts.

The gallery is the visual-review surface; these keep it honest:
- it passes the zero-script gate (it is itself a projection artifact);
- it renders all 7x3 = 21 cells (no silent drop);
- the committed ``gallery.html`` byte-matches a fresh regeneration.

Regenerate the committed file (orchestrator, after review):

    ANTIEK_UPDATE_GOLDENS=1 ./.venv/bin/python -m pytest \\
        services/html_projection/tests/test_gallery.py -q
"""

from __future__ import annotations

import os

import pytest

from services.html_projection import gate
from services.html_projection.widgets import gallery


def test_gallery_is_script_free() -> None:
    gate.assert_script_free(gallery.build_gallery())


def test_gallery_renders_all_cells() -> None:
    html = gallery.build_gallery()
    # 7 widgets x 3 shapes; one <figcaption> per cell.
    assert html.count("<figcaption>") == 21


def test_gallery_matches_committed() -> None:
    fresh = gallery.build_gallery()
    path = gallery._GALLERY_PATH

    if os.environ.get("ANTIEK_UPDATE_GOLDENS") == "1":
        path.write_text(fresh, encoding="utf-8")
        pytest.skip(f"updated {path.name}")

    assert path.exists(), (
        "gallery.html missing; regenerate with ANTIEK_UPDATE_GOLDENS=1"
    )
    assert fresh == path.read_text(encoding="utf-8"), (
        "committed gallery.html drifted from freshly generated output; "
        "regenerate with ANTIEK_UPDATE_GOLDENS=1 and review"
    )
