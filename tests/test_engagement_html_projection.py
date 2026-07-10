"""HTML-first projection path for engagement-spine assets.

Proves a representative asset round-trips through project_to_html with
non-empty HTML body; PDF is not the view format.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.engagement_spine import (  # noqa: E402
    HighlightSelection,
    InMemoryEngagementStore,
    complete_spawn,
    merge_spawn_outputs,
    project_to_html,
    record_twin_insight,
    spawn_from_highlight,
)


def test_project_merged_asset_to_nonempty_html():
    store = InMemoryEngagementStore()
    asset = "html-asset-1"
    spawn = spawn_from_highlight(
        HighlightSelection(
            asset_id=asset,
            selection_text="HTML is the controllable reading surface.",
            region_id="h1",
        ),
        store=store,
    )
    complete_spawn(
        spawn.spawn_id,
        store=store,
        output_text=(
            "Projecting research and books as HTML keeps agent edits "
            "deterministic and script-free."
        ),
        insights=["Agents edit HTML more reliably than PDF."],
        questions=["What gate enforces script-free output?"],
    )
    record_twin_insight(
        asset,
        "Canonical view surface is HTML, never PDF.",
        store=store,
        source_spawn_id=spawn.spawn_id,
    )
    merged = merge_spawn_outputs(
        asset,
        [spawn.spawn_id],
        store=store,
        mode="into_parent",
        parent_title="HTML-first reading",
        parent_body="We read books and papers as HTML projections.",
    )
    html = project_to_html(merged.doc_model, document_id=merged.document_id)
    assert isinstance(html, str)
    assert len(html) > 100
    assert "<html" in html.lower() or "<!doctype" in html.lower()
    # Content from the spine must surface in the human view
    assert "HTML" in html or "html" in html
    # Not a PDF
    assert not html.startswith("%PDF")
    assert "application/pdf" not in html.lower()


def test_project_rejects_empty_doc_model():
    with pytest.raises(ValueError, match="content"):
        project_to_html({"title": "empty", "content": []})


def test_project_direct_doc_model():
    doc = {
        "title": "Representative research note",
        "content": [
            {
                "type": "paragraph",
                "attrs": {"block_id": "p1"},
                "content": [
                    {
                        "type": "text",
                        "text": "A short non-empty research paragraph for projection.",
                    }
                ],
            }
        ],
    }
    html = project_to_html(doc, document_id="rep-1")
    assert "short non-empty research paragraph" in html
    assert len(html) > 50
