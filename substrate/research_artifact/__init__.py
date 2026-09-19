"""Profile B — ResearchArtifact HTML transport (ANT-AHT)."""

from .blocks import OutlineBlockRef, list_outline_blocks
from .build_body import build_body
from .compose import ComposeResult, compose_artifacts
from .export import (
    ExportResult,
    build_html_only,
    export_research_artifact,
    research_projection_doc_model,
)
from .import_notes import ImportNotesResult, import_agent_notes, parse_body_from_html
from .schema import SCHEMA_VERSION, ResearchArtifactBody

__all__ = [
    "SCHEMA_VERSION",
    "ComposeResult",
    "build_body",
    "ExportResult",
    "ImportNotesResult",
    "OutlineBlockRef",
    "ResearchArtifactBody",
    "build_html_only",
    "research_projection_doc_model",
    "compose_artifacts",
    "export_research_artifact",
    "import_agent_notes",
    "list_outline_blocks",
    "parse_body_from_html",
]