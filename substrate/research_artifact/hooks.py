"""Optional hooks (env-gated) — ANT-AHT."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .authority import ArtifactAuthority

if TYPE_CHECKING:
    from .export import ExportResult


def maybe_export_after_investigation_complete(
    investigation_id: str,
    *,
    authority: ArtifactAuthority | None = None,
    source_coverage: object | None = None,
    inherited_reuse: object | None = None,
    terminal_provenance: object | None = None,
) -> ExportResult | None:
    """When ``ANTIEK_EXPORT_RESEARCH_ARTIFACT=1``, write artifact HTML after Loop 1 completes."""
    if os.environ.get("ANTIEK_EXPORT_RESEARCH_ARTIFACT", "").strip() not in (
        "1",
        "true",
        "yes",
    ):
        return None
    from .authority import operator_authority
    from .export import export_research_artifact

    return export_research_artifact(
        investigation_id,
        authority=authority or operator_authority(investigation_id),
        emit_event=True,
        source_coverage=source_coverage,
        inherited_reuse=inherited_reuse,
        terminal_provenance=terminal_provenance,
    )
