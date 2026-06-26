"""Optional hooks (env-gated) — ANT-AHT."""

from __future__ import annotations

import os


def maybe_export_after_investigation_complete(investigation_id: str) -> None:
    """When ``ANTIEK_EXPORT_RESEARCH_ARTIFACT=1``, write artifact HTML after Loop 1 completes."""
    if os.environ.get("ANTIEK_EXPORT_RESEARCH_ARTIFACT", "").strip() not in (
        "1",
        "true",
        "yes",
    ):
        return
    from .export import export_research_artifact

    kb_static = os.environ.get("ANTIEK_KB_STATIC_HTML", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    export_research_artifact(
        investigation_id, emit_event=True, kb_static=kb_static
    )