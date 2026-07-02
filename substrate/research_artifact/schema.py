"""ResearchArtifact v0 — canonical JSON body (HTML is a rendered view)."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION: Literal[1] = 1


class ArtifactInsight(BaseModel):
    node_id: str
    text: str
    source_document_id: str | None = None
    confidence: str | None = None


class ArtifactQuestion(BaseModel):
    node_id: str
    text: str
    escalated: bool = False
    reserved_child_investigation_id: str | None = None


class ResearchArtifactBody(BaseModel):
    """Machine channel for Profile B transport (ANT-AHT)."""

    schema_version: Literal[1] = SCHEMA_VERSION
    investigation_id: str
    problem_question: str
    insights: list[ArtifactInsight] = Field(default_factory=list)
    open_questions: list[ArtifactQuestion] = Field(default_factory=list)
    synthesis_excerpt: str | None = None
    synthesis_withheld: bool = False
    source_event_ids: list[str] = Field(default_factory=list)
    # Append-only agent transport (import via import_agent_notes; never graph insights).
    agent_notes: list[str] = Field(default_factory=list)

    def content_hash(self) -> str:
        canonical = self.model_dump(mode="json")
        blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()