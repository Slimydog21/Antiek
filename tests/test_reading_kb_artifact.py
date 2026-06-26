"""Reading workflow — KB HTML ResearchArtifact consumption (interfaces/reading)."""

from __future__ import annotations

from pathlib import Path

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_SHARED_KB_HTML = _FIXTURES / "kb_artifact_minimal.html"

from interfaces.reading.kb_artifact import (
    condense_body_for_reading,
    consume_kb_artifact,
    load_kb_artifact_html,
)
from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ArtifactInsight, ResearchArtifactBody


def test_load_and_condense_preserves_graph_node_ids(tmp_path: Path):
    body = ResearchArtifactBody(
        investigation_id="inv-rd-1",
        problem_question="Q",
        insights=[ArtifactInsight(node_id="ins-9", text="Finding", confidence="high")],
        open_questions=[],
    )
    path = tmp_path / "a.html"
    path.write_text(render_html(body, interactive=False), encoding="utf-8")
    raw = load_kb_artifact_html(path)
    assert "ins-9" in raw
    condensed = consume_kb_artifact(path)
    assert condensed.findings[0][0] == "ins-9"
    direct = condense_body_for_reading(body)
    assert direct.content_hash == condensed.content_hash


def test_consume_shared_kb_fixture_contract():
    """Same HTML file as vitest kbArtifactCondense (cross-language contract)."""
    assert _SHARED_KB_HTML.is_file()
    condensed = consume_kb_artifact(_SHARED_KB_HTML)
    assert condensed.investigation_id == "inv-ui"
    assert condensed.findings[0][0] == "n-1"
    assert condensed.findings[0][1] == "Finding"
    assert condensed.synthesis_excerpt == "Synth"
    assert condensed.script_free is True