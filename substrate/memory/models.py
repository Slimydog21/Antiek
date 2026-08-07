"""Typed account-memory records projected onto graph nodes and edges."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

_REFERENCE_KEYS = {
    "chunk_id",
    "document_id",
    "event_id",
    "id",
    "investigation_id",
    "note_id",
    "provenance_id",
    "ref",
    "source",
    "source_document_id",
    "source_id",
    "source_ref",
    "thread_id",
}


class MemoryItem(BaseModel):
    """One owner-private, provenance-bearing, bi-temporal graph memory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_id: str = Field(min_length=1)
    edge_id: str = Field(min_length=1)
    owner_user_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str = Field(min_length=1)
    provenance: dict[str, JsonValue]
    valid_from: datetime
    valid_to: datetime | None = None
    superseded_by: str | None = None
    created_at: datetime

    @field_validator(
        "memory_id",
        "edge_id",
        "owner_user_id",
        "subject",
        "predicate",
        "object",
    )
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("memory identity and triple fields cannot be blank")
        return normalized

    @field_validator("provenance")
    @classmethod
    def _require_provenance_reference(
        cls, value: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        if not value or not any(
            _is_reference(key, candidate) for key, candidate in value.items()
        ):
            raise ValueError("memory provenance must carry a source reference")
        return value


def _is_reference(key: str, value: JsonValue) -> bool:
    normalized_key = key.strip().lower()
    return (
        normalized_key in _REFERENCE_KEYS
        and isinstance(value, str)
        and bool(value.strip())
    )


__all__ = ["MemoryItem"]
