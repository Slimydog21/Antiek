"""ResearchArtifact v0 — canonical JSON body (HTML is a rendered view)."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION: Literal[2] = 2
MAX_ARTIFACT_CLAIMS = 100
MAX_CITATIONS_PER_CLAIM = 100


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


class ArtifactCitation(BaseModel):
    citation_id: str = Field(min_length=1, max_length=512)
    resolution: Literal["graph", "federated", "unresolved"]
    document_id: str | None = Field(default=None, max_length=512)
    external_source_id: str | None = Field(default=None, max_length=512)
    title: str | None = Field(default=None, max_length=4096)
    source_kind: str | None = Field(default=None, max_length=128)
    rights_class: str | None = Field(default=None, max_length=256)
    retrieved_at: str | None = Field(default=None, max_length=64)
    source_tier: int | None = Field(default=None, ge=1, le=5)
    locator: str | None = Field(default=None, max_length=2048)


class ArtifactClaim(BaseModel):
    statement: str = Field(min_length=1, max_length=20_000)
    cited_ids: list[str] = Field(default_factory=list, max_length=MAX_CITATIONS_PER_CLAIM)
    citations: list[ArtifactCitation] = Field(
        default_factory=list, max_length=MAX_CITATIONS_PER_CLAIM
    )


class ResearchArtifactBody(BaseModel):
    """Machine channel for Profile B transport (ANT-AHT)."""

    schema_version: Literal[2] = SCHEMA_VERSION
    investigation_id: str
    problem_question: str
    insights: list[ArtifactInsight] = Field(default_factory=list)
    open_questions: list[ArtifactQuestion] = Field(default_factory=list)
    synthesis_excerpt: str | None = None
    synthesis_withheld: bool = False
    claims: list[ArtifactClaim] = Field(default_factory=list, max_length=MAX_ARTIFACT_CLAIMS)
    source_event_ids: list[str] = Field(default_factory=list)
    # Append-only agent transport (import via import_agent_notes; never graph insights).
    agent_notes: list[str] = Field(default_factory=list)

    def content_hash(self) -> str:
        canonical = self.model_dump(mode="json")
        blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()
