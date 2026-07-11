"""Profile B — ResearchArtifact HTML transport (ANT-AHT)."""

from .append_note import AppendNoteResult, StaleArtifactError, append_note
from .blocks import OutlineBlockRef, list_outline_blocks
from .compose import ComposeResult, compose_artifacts
from .export import ExportResult, build_html_only, export_research_artifact
from .import_notes import ImportNotesResult, import_agent_notes, parse_body_from_html
from .schema import SCHEMA_VERSION, ResearchArtifactBody

__all__ = [
    "SCHEMA_VERSION",
    "AppendNoteResult",
    "ComposeResult",
    "ExportResult",
    "ImportNotesResult",
    "OutlineBlockRef",
    "ResearchArtifactBody",
    "StaleArtifactError",
    "append_note",
    "build_html_only",
    "compose_artifacts",
    "export_research_artifact",
    "import_agent_notes",
    "list_outline_blocks",
    "parse_body_from_html",
]
