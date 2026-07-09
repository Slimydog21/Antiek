"""Profile B — ResearchArtifact HTML transport (ANT-AHT)."""

from .blocks import OutlineBlockRef, list_outline_blocks
from .compose import ComposeMember, ComposeResult, compose_artifacts
from .export import ExportResult, build_html_only, export_research_artifact
from .import_notes import ImportNotesResult, import_agent_notes, parse_body_from_html
from .schema import SCHEMA_VERSION, ResearchArtifactBody
from .source_merge import (
    SourceMergeApplyReceipt,
    SourceMergePreviewReceipt,
    apply_source_merge_review,
    preview_source_merge_review,
)
from .twin_notes import render_twin_notes_html, write_twin_notes

__all__ = [
    "SCHEMA_VERSION",
    "ComposeResult",
    "ComposeMember",
    "ExportResult",
    "ImportNotesResult",
    "OutlineBlockRef",
    "ResearchArtifactBody",
    "SourceMergeApplyReceipt",
    "SourceMergePreviewReceipt",
    "apply_source_merge_review",
    "build_html_only",
    "compose_artifacts",
    "export_research_artifact",
    "import_agent_notes",
    "list_outline_blocks",
    "parse_body_from_html",
    "preview_source_merge_review",
    "render_twin_notes_html",
    "write_twin_notes",
]
