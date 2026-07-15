"""Profile B — ResearchArtifact HTML transport (ANT-AHT)."""

from .blocks import OutlineBlockRef, list_outline_blocks
from .compose import (
    ComposeResult,
    StaleComposePreview,
    compose_artifacts,
    create_compose_draft,
    delete_compose_draft,
    load_compose_draft,
    preview_artifacts,
)
from .export import ExportResult, build_html_only, export_research_artifact
from .import_notes import ImportNotesResult, import_agent_notes, parse_body_from_html
from .schema import SCHEMA_VERSION, ResearchArtifactBody

__all__ = [
    "SCHEMA_VERSION",
    "ComposeResult",
    "StaleComposePreview",
    "ExportResult",
    "ImportNotesResult",
    "OutlineBlockRef",
    "ResearchArtifactBody",
    "build_html_only",
    "compose_artifacts",
    "create_compose_draft",
    "delete_compose_draft",
    "export_research_artifact",
    "import_agent_notes",
    "list_outline_blocks",
    "load_compose_draft",
    "parse_body_from_html",
    "preview_artifacts",
]
