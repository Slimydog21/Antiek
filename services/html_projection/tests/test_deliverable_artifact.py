"""SPR-06 M3: Write deliverable → artifact — mapping, placeholder, rights."""

from __future__ import annotations

import json

from services.html_projection.adapters.deliverable import (
    DeliverableBlock,
    DeliverableExport,
    DeliverableSection,
    adapt_deliverable,
    unsupported_block_kinds,
)
from services.html_projection.context import RenderContext
from services.html_projection.gate import assert_script_free
from services.html_projection.island import extract_island
from services.html_projection.renderer import render


def _render(export: DeliverableExport) -> str:
    return render(adapt_deliverable(export), RenderContext())


def test_known_block_kinds_render_their_text():
    export = DeliverableExport(
        title="My deliverable",
        sections=[
            DeliverableSection(
                heading="Findings",
                blocks=[
                    DeliverableBlock("claim", "A claim statement."),
                    DeliverableBlock("insight", "An insight."),
                    DeliverableBlock("open_question", "An open question?"),
                    DeliverableBlock("operator_note", "An operator note."),
                    DeliverableBlock("user_authored", "User prose."),
                    DeliverableBlock("synthesized", "A synthesized point."),
                ],
            )
        ],
    )
    html = _render(export)
    for text in (
        "Findings",
        "A claim statement.",
        "An insight.",
        "An open question?",
        "An operator note.",
        "User prose.",
        "A synthesized point.",
    ):
        assert text in html


def test_unknown_block_kind_shows_visible_placeholder_not_dropped():
    export = DeliverableExport(
        title="d",
        sections=[
            DeliverableSection(
                heading="S",
                blocks=[DeliverableBlock("write_only_widget", "payload")],
            )
        ],
    )
    doc_model = adapt_deliverable(export)
    html = render(doc_model, RenderContext())
    assert "unsupported" in html.lower()  # the renderer's visible placeholder
    # the unknown kind is named in metadata + the helper (the gap is surfaced).
    assert doc_model["metadata"]["unsupported_block_kinds"] == ["write_only_widget"]
    assert unsupported_block_kinds(export) == ["write_only_widget"]


def test_non_servable_source_block_is_cite_only_no_leak():
    export = DeliverableExport(
        title="d",
        sections=[
            DeliverableSection(
                heading="S",
                blocks=[
                    DeliverableBlock(
                        "claim",
                        "SECRET QUOTED PASSAGE",
                        content_class="personal_reading",
                        ip_holder_id="pg",
                        source_title="A PG essay",
                    )
                ],
            )
        ],
    )
    doc_model = adapt_deliverable(export)
    blob = json.dumps(doc_model)
    assert "SECRET QUOTED PASSAGE" not in blob  # withheld from the doc-model
    assert "cite-only" in blob
    assert "pg" in blob


def test_source_edges_use_document_id_with_title_label_and_tone():
    doc_model = adapt_deliverable(
        DeliverableExport(
            title="d",
            sections=[
                DeliverableSection(
                    heading="S",
                    blocks=[
                        DeliverableBlock(
                            "claim",
                            "Public text",
                            content_class="public_domain",
                            source_title="On Liberty",
                            source_document_id="doc-pd",
                        ),
                        DeliverableBlock(
                            "claim",
                            "SECRET",
                            content_class="personal_reading",
                            ip_holder_id="pg",
                            source_title="A PG essay",
                            source_document_id="doc-pr",
                        ),
                    ],
                )
            ],
        )
    )
    assert doc_model["edges"] == [
        {
            "kind": "cites",
            "to_document_id": "doc-pd",
            "to_title": "On Liberty",
            "tone": "success",
        },
        {
            "kind": "cites",
            "to_document_id": "doc-pr",
            "to_title": "A PG essay",
            "tone": "warning",
        },
    ]


def test_source_edges_fall_back_to_title_without_document_id():
    doc_model = adapt_deliverable(
        DeliverableExport(
            title="d",
            sections=[
                DeliverableSection(
                    heading="S",
                    blocks=[
                        DeliverableBlock(
                            "claim",
                            "Public text",
                            content_class="public_domain",
                            source_title="Legacy title",
                        ),
                    ],
                )
            ],
        )
    )
    assert doc_model["edges"] == [
        {
            "kind": "cites",
            "to_document_id": "Legacy title",
            "to_title": "Legacy title",
            "tone": "success",
        }
    ]


def test_deliverable_is_gate_clean_and_round_trips():
    export = DeliverableExport(
        title="d",
        sections=[
            DeliverableSection(
                heading="S",
                blocks=[DeliverableBlock("claim", "A claim."), DeliverableBlock("user_authored", "Prose.")],
            )
        ],
    )
    doc_model = adapt_deliverable(export)
    assert_script_free(render(doc_model, RenderContext()))
    assert extract_island(render(doc_model, RenderContext())) == doc_model
