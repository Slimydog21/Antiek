"""Profile B — ResearchArtifact HTML transport (ANT-AHT)."""

from .blocks import OutlineBlockRef, list_outline_blocks
from .compose import (
    ComposeResult,
    VerifiedComposition,
    VerifiedCompositionMember,
    compose_artifacts,
    load_verified_composition,
    read_composition_store_file,
    validate_investigation_ids,
    verify_composition_index,
)
from .export import ExportResult, build_html_only, export_research_artifact
from .import_notes import ImportNotesResult, import_agent_notes, parse_body_from_html
from .schema import SCHEMA_VERSION, ResearchArtifactBody

__all__ = [
    "SCHEMA_VERSION",
    "ComposeResult",
    "ExportResult",
    "ImportNotesResult",
    "OutlineBlockRef",
    "ResearchArtifactBody",
    "VerifiedComposition",
    "VerifiedCompositionMember",
    "build_html_only",
    "compose_artifacts",
    "export_research_artifact",
    "import_agent_notes",
    "list_outline_blocks",
    "load_verified_composition",
    "parse_body_from_html",
    "read_composition_store_file",
    "validate_investigation_ids",
    "verify_composition_index",
]
