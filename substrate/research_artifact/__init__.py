"""Profile B — ResearchArtifact HTML transport (ANT-AHT)."""

from .authority import ArtifactAuthority, operator_authority
from .blocks import OutlineBlockRef, list_outline_blocks
from .compose import ComposeResult, compose_artifacts
from .export import ExportResult, build_html_only, export_research_artifact
from .import_notes import (
    ImportNotesResult,
    import_agent_notes,
    import_agent_notes_html,
    parse_body_from_html,
)
from .schema import SCHEMA_VERSION, ResearchArtifactBody

__all__ = [
    "SCHEMA_VERSION",
    "ArtifactAuthority",
    "ComposeResult",
    "ExportResult",
    "ImportNotesResult",
    "OutlineBlockRef",
    "ResearchArtifactBody",
    "build_html_only",
    "compose_artifacts",
    "export_research_artifact",
    "import_agent_notes",
    "import_agent_notes_html",
    "list_outline_blocks",
    "parse_body_from_html",
    "operator_authority",
]
