"""Reading workflow entry — ResearchArtifact HTML as first-class consumption."""

from __future__ import annotations

from pathlib import Path

from substrate.research_artifact.reading_surface import (
    ReadingCondensedView,
    consume_kb_artifact,
    condense_body_for_reading,
    kb_artifact_minimal_fixture_path,
    load_kb_artifact_html,
)

__all__ = [
    "ReadingCondensedView",
    "consume_kb_artifact",
    "condense_body_for_reading",
    "kb_artifact_minimal_fixture_path",
    "load_kb_artifact_html",
]