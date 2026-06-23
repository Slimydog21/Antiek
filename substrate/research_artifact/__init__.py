"""Profile B — ResearchArtifact HTML transport (ANT-AHT)."""

from .blocks import OutlineBlockRef, list_outline_blocks
from .compose import ComposeResult, compose_artifacts
from .export import ExportResult, build_html_only, export_research_artifact
from .import_notes import ImportNotesResult, import_agent_notes, parse_body_from_html
from .schema import ResearchArtifactBody, SCHEMA_VERSION

__all__ = [
    "SCHEMA_VERSION",
    "ComposeResult",
    "ExportResult",
    "ImportNotesResult",
    "OutlineBlockRef",
    "ResearchArtifactBody",
    "build_html_only",
    "compose_artifacts",
    "export_research_artifact",
    "import_agent_notes",
    "list_outline_blocks",
    "parse_body_from_html",
]