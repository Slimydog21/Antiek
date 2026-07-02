"""SPR-AHT-01 — ResearchArtifact template anti-fiction."""

from __future__ import annotations

from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ResearchArtifactBody


def test_empty_body_renders_honest_empty_state():
    body = ResearchArtifactBody(
        investigation_id="inv-empty",
        problem_question="What is unknown?",
    )
    html = render_html(body)
    assert "No insights in the graph yet" in html
    assert "No open questions in the graph yet" in html
    assert "No synthesis yet" in html
    assert 'id="antiek-artifact-v1"' in html
    assert "inv-empty" in html
    assert 'id="copy-json"' in html
    assert 'id="add-note"' in html


def test_content_hash_stable():
    body = ResearchArtifactBody(
        investigation_id="inv-1",
        problem_question="Q",
    )
    assert body.content_hash() == body.content_hash()