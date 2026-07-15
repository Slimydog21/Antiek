"""Profile B — ResearchArtifact HTML transport (ANT-AHT)."""

from .blocks import OutlineBlockRef, list_outline_blocks
from .compose import (
    ComposeResult,
    StaleComposePreview,
    compose_artifacts,
    compose_lock,
    create_compose_draft,
    delete_compose_draft,
    load_compose_draft,
    preview_artifacts,
)
from .compose_interrogate import (
    INTERROGATION_PREVIEW_SCHEMA_VERSION,
    MAX_INTERROGATION_CONTEXT_CHARS,
    MAX_INTERROGATION_PROMPT_CHARS,
    ComposeInterrogationIntegrityError,
    InterrogationPreviewPacket,
    InvalidInterrogationPrompt,
    build_interrogation_preview,
)
from .export import ExportResult, build_html_only, export_research_artifact
from .import_notes import ImportNotesResult, import_agent_notes, parse_body_from_html
from .schema import SCHEMA_VERSION, ResearchArtifactBody

__all__ = [
    "SCHEMA_VERSION",
    "ComposeResult",
    "ComposeInterrogationIntegrityError",
    "StaleComposePreview",
    "ExportResult",
    "INTERROGATION_PREVIEW_SCHEMA_VERSION",
    "InterrogationPreviewPacket",
    "InvalidInterrogationPrompt",
    "MAX_INTERROGATION_CONTEXT_CHARS",
    "MAX_INTERROGATION_PROMPT_CHARS",
    "ImportNotesResult",
    "OutlineBlockRef",
    "ResearchArtifactBody",
    "build_html_only",
    "build_interrogation_preview",
    "compose_artifacts",
    "compose_lock",
    "create_compose_draft",
    "delete_compose_draft",
    "export_research_artifact",
    "import_agent_notes",
    "list_outline_blocks",
    "load_compose_draft",
    "parse_body_from_html",
    "preview_artifacts",
]
