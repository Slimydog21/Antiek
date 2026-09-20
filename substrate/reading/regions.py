"""Canonical source-to-HTML regions and their append-only DuckDB store."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import duckdb
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from substrate.contracts.html_projection import SourceLocator, derive_anchor_id
from substrate.reading.projection.store import ProjectionStore

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CanonicalDocumentRegion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1, max_length=512)
    projection_id: str = Field(min_length=1, max_length=512)
    source_locator: SourceLocator
    html_anchor_id: str = Field(min_length=1, max_length=512)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, gt=0)
    exact_text_sha256: str | None = None
    created_event_id: str | None = Field(default=None, min_length=1, max_length=512)
    region_id: str = Field(pattern=r"^region-[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_region(self) -> CanonicalDocumentRegion:
        has_span = self.char_start is not None or self.char_end is not None
        if (self.char_start is None) != (self.char_end is None):
            raise ValueError("char_start and char_end must be supplied together")
        if has_span:
            if self.char_start is None or self.char_end is None:  # type-safe invariant guard
                raise ValueError("char_start and char_end must be supplied together")
            if self.char_end <= self.char_start:
                raise ValueError("char_end must be greater than char_start")
            if self.exact_text_sha256 is None:
                raise ValueError("exact_text_sha256 is required with a character span")
        elif self.exact_text_sha256 is not None:
            raise ValueError("exact_text_sha256 is allowed only with a character span")
        if self.exact_text_sha256 is not None and not _SHA256.fullmatch(self.exact_text_sha256):
            raise ValueError("exact_text_sha256 must be exact lowercase SHA-256 hex")
        if self.html_anchor_id != derive_anchor_id(self.projection_id, self.source_locator):
            raise ValueError("html_anchor_id must equal the canonical derived anchor")
        if self.region_id != derive_region_id(**self.identity()):
            raise ValueError("region_id does not match canonical identity")
        return self

    def identity(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "projection_id": self.projection_id,
            "source_locator": self.source_locator.model_dump(exclude_none=True),
            "html_anchor_id": self.html_anchor_id,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "exact_text_sha256": self.exact_text_sha256,
        }


def derive_region_id(**identity: object) -> str:
    payload = _json(identity)
    return f"region-{hashlib.sha256(payload.encode()).hexdigest()}"


class RegionConflict(ValueError):
    """A claim conflicts with stored identity or its ready projection."""


class RegionStore:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def ensure_tables(self) -> None:
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS document_regions (
                region_id TEXT PRIMARY KEY,
                projection_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                html_anchor_id TEXT NOT NULL,
                identity_json JSON NOT NULL UNIQUE,
                region_json JSON NOT NULL
            )
        """)

    def claim(self, region: CanonicalDocumentRegion) -> CanonicalDocumentRegion:
        # `model_copy(update=...)` does not re-run Pydantic validators. Treat the
        # store as a trust boundary and canonicalize again before any lookup or
        # insert so a forged typed instance cannot bypass identity/anchor checks.
        try:
            region = CanonicalDocumentRegion.model_validate(region.model_dump())
        except ValidationError as exc:
            raise RegionConflict("region failed canonical validation") from exc
        self.ensure_tables()
        rows = self._connection.execute(
            "SELECT region_json FROM document_regions "
            "WHERE region_id = ? OR identity_json = ?",
            [region.region_id, _json(region.identity())],
        ).fetchall()
        if rows:
            if len(rows) == 1:
                stored = CanonicalDocumentRegion.model_validate_json(str(rows[0][0]))
                if stored == region:
                    return stored
            raise RegionConflict("region id or canonical identity conflicts with stored data")

        try:
            projection = ProjectionStore(self._connection).load(region.projection_id)
        except KeyError as exc:
            raise RegionConflict("projection does not exist") from exc
        if projection.status != "ready":
            raise RegionConflict("projection must be ready")
        if projection.source_document_id != region.document_id:
            raise RegionConflict("region document does not match projection source document")
        matches = [
            mapping
            for mapping in projection.anchor_mappings
            if mapping.source_locator == region.source_locator
        ]
        if len(matches) != 1 or matches[0].state != "resolved":
            raise RegionConflict("source locator is not exactly resolved in projection")
        if matches[0].html_anchor_id != region.html_anchor_id:
            raise RegionConflict("region anchor does not match resolved projection mapping")

        try:
            self._connection.execute(
                "INSERT INTO document_regions VALUES (?, ?, ?, ?, ?, ?)",
                [
                    region.region_id,
                    region.projection_id,
                    region.document_id,
                    region.html_anchor_id,
                    _json(region.identity()),
                    _json(region.model_dump()),
                ],
            )
        except duckdb.ConstraintException as exc:
            # A concurrent exact replay may win after the lookup above. Preserve
            # idempotency, but never leak storage exceptions across this boundary.
            rows = self._connection.execute(
                "SELECT region_json FROM document_regions "
                "WHERE region_id = ? OR identity_json = ?",
                [region.region_id, _json(region.identity())],
            ).fetchall()
            if len(rows) == 1:
                stored = CanonicalDocumentRegion.model_validate_json(str(rows[0][0]))
                if stored == region:
                    return stored
            raise RegionConflict(
                "region id or canonical identity conflicts with stored data"
            ) from exc
        return region

    def load(self, region_id: str) -> CanonicalDocumentRegion:
        row = self._connection.execute(
            "SELECT region_json FROM document_regions WHERE region_id = ?", [region_id]
        ).fetchone()
        if row is None:
            raise KeyError(region_id)
        return CanonicalDocumentRegion.model_validate_json(str(row[0]))

    def list(
        self, *, projection_id: str | None = None, document_id: str | None = None
    ) -> tuple[CanonicalDocumentRegion, ...]:
        clauses: list[str] = []
        values: list[str] = []
        if projection_id is not None:
            clauses.append("projection_id = ?")
            values.append(projection_id)
        if document_id is not None:
            clauses.append("document_id = ?")
            values.append(document_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._connection.execute(
            f"SELECT region_json FROM document_regions{where} ORDER BY region_id", values
        ).fetchall()
        return tuple(CanonicalDocumentRegion.model_validate_json(str(row[0])) for row in rows)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


__all__ = ["CanonicalDocumentRegion", "RegionConflict", "RegionStore", "derive_region_id"]
