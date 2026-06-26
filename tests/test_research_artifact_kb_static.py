"""KB-static HTML export (script-free condensation formfactor)."""

from __future__ import annotations

from substrate.research_artifact.projection_verify import has_executable_scripts
from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ResearchArtifactBody


def test_kb_static_render_has_no_executable_scripts():
    body = ResearchArtifactBody(
        investigation_id="inv-kb",
        problem_question="KB fixture",
    )
    html = render_html(body, interactive=False)
    assert has_executable_scripts(html) is False
    assert 'id="antiek-artifact-v1"' in html