"""Canonical HTML projection persistence/input contract.

This is the typed boundary consumed by the still-provisional, DRW-owned
``ReaderSurfaceContract``.  It does not define another reading surface.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,255}$")
_COORD_INPUT_RE = re.compile(r"^(?:0(?:\.\d{1,9})?|1(?:\.0{1,9})?)$")

ReasonCode = Literal[
    "conversion_failed",
    "conversion_unsupported",
    "ocr_failed",
    "ocr_unavailable",
    "sanitization_failed",
    "sanitization_rejected",
    "anchor_review_required",
    "storage_failed",
]


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PdfPageLocator(_FrozenModel):
    kind: Literal["pdf_page_bbox"] = "pdf_page_bbox"
    page: int = Field(ge=1)
    x0: str
    y0: str
    x1: str
    y1: str

    @field_validator("x0", "y0", "x1", "y1", mode="before")
    @classmethod
    def canonicalize_coordinate(cls, value: object) -> str:
        if not isinstance(value, str) or not _COORD_INPUT_RE.fullmatch(value):
            raise ValueError("bbox coordinates must be decimals in [0,1] with at most 9 places")
        try:
            decimal = Decimal(value)
        except InvalidOperation as exc:  # defensive; the regex normally catches this
            raise ValueError("invalid bbox coordinate") from exc
        canonical = format(decimal.normalize(), "f")
        return "0" if canonical in {"-0", "0E+0"} else canonical

    @model_validator(mode="after")
    def validate_bbox(self) -> PdfPageLocator:
        if Decimal(self.x0) >= Decimal(self.x1) or Decimal(self.y0) >= Decimal(self.y1):
            raise ValueError("bbox must have positive width and height")
        return self


class SemanticLocator(_FrozenModel):
    kind: Literal["semantic"] = "semantic"
    semantic_id: str = Field(min_length=1, max_length=512)


class TextLocator(_FrozenModel):
    kind: Literal["text"] = "text"
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text_sha256: str

    @model_validator(mode="after")
    def validate_text_locator(self) -> TextLocator:
        if self.end <= self.start:
            raise ValueError("text locator end must be greater than start")
        _validate_sha256(self.text_sha256, "text_sha256")
        return self


SourceLocator = Annotated[
    PdfPageLocator | SemanticLocator | TextLocator, Field(discriminator="kind")
]


class AnchorMapping(_FrozenModel):
    source_locator: SourceLocator
    state: Literal["resolved", "ambiguous", "unresolved"]
    html_anchor_id: str | None = None
    candidates: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_state(self) -> AnchorMapping:
        if self.state == "resolved":
            if self.html_anchor_id is None or not _ID_RE.fullmatch(self.html_anchor_id):
                raise ValueError("resolved mapping requires an HTML-safe anchor id")
            if self.candidates:
                raise ValueError("resolved mapping cannot carry candidates")
        elif self.html_anchor_id is not None:
            raise ValueError("ambiguous/unresolved mapping cannot claim an anchor")
        if self.state == "ambiguous" and len(self.candidates) < 2:
            raise ValueError("ambiguous mapping requires at least two candidates")
        if self.state == "unresolved" and self.candidates:
            raise ValueError("unresolved mapping cannot carry candidates")
        if any(not _ID_RE.fullmatch(candidate) for candidate in self.candidates):
            raise ValueError("candidate anchor ids must be HTML-safe")
        if len(set(self.candidates)) != len(self.candidates):
            raise ValueError("candidate anchor ids must be unique")
        return self


ProjectionStatus = Literal[
    "queued", "extracting", "ocr_required", "sanitizing", "review_required", "ready", "failed"
]


class HtmlProjectionContract(_FrozenModel):
    source_asset_id: str = Field(min_length=1, max_length=512)
    source_document_id: str = Field(min_length=1, max_length=512)
    source_sha256: str
    converter_id: str = Field(min_length=1, max_length=255)
    converter_version: str = Field(min_length=1, max_length=255)
    sanitizer_policy: str = Field(min_length=1, max_length=255)
    sanitizer_version: str = Field(min_length=1, max_length=255)
    projection_id: str
    status: ProjectionStatus
    hosted_html_locator: str | None = None
    hosted_html_sha256: str | None = None
    reason_code: ReasonCode | None = None
    anchor_mappings: tuple[AnchorMapping, ...] = ()

    @model_validator(mode="after")
    def validate_contract(self) -> HtmlProjectionContract:
        _validate_sha256(self.source_sha256, "source_sha256")
        if self.projection_id != derive_projection_id(**self.identity()):
            raise ValueError("projection_id does not match canonical identity")
        hosted = self.hosted_html_locator is not None or self.hosted_html_sha256 is not None
        if self.status == "ready":
            if self.hosted_html_locator is None or self.hosted_html_sha256 is None:
                raise ValueError("ready projection requires hosted HTML locator and hash")
            _validate_object_key(self.hosted_html_locator)
            _validate_sha256(self.hosted_html_sha256, "hosted_html_sha256")
            if any(mapping.state != "resolved" for mapping in self.anchor_mappings):
                raise ValueError("ready projection mappings must all be resolved")
            for mapping in self.anchor_mappings:
                expected_anchor = derive_anchor_id(self.projection_id, mapping.source_locator)
                if mapping.html_anchor_id != expected_anchor:
                    raise ValueError("resolved mapping must use its canonical derived anchor id")
        elif hosted:
            raise ValueError("hosted HTML is allowed only for ready projections")
        if self.status in {"review_required", "failed"}:
            if self.reason_code is None:
                raise ValueError("review/failed projection requires a reason code")
        elif self.reason_code is not None:
            raise ValueError("reason_code is allowed only for review_required/failed")
        if self.status != "ready" and any(m.state == "resolved" for m in self.anchor_mappings):
            raise ValueError("resolved HTML anchors are allowed only for ready projections")
        if self.status == "review_required" and any(
            m.state not in {"ambiguous", "unresolved"} for m in self.anchor_mappings
        ):
            raise ValueError("review_required mappings must be ambiguous or unresolved")
        locator_keys = [m.source_locator.model_dump_json() for m in self.anchor_mappings]
        if len(set(locator_keys)) != len(locator_keys):
            raise ValueError("duplicate source locators are not allowed")
        anchor_ids = [
            anchor
            for mapping in self.anchor_mappings
            for anchor in ((mapping.html_anchor_id,) if mapping.html_anchor_id else mapping.candidates)
        ]
        if len(set(anchor_ids)) != len(anchor_ids):
            raise ValueError("resolved/candidate anchor ids must be unique")
        return self

    def identity(self) -> dict[str, str]:
        return {
            key: getattr(self, key)
            for key in (
                "source_asset_id", "source_document_id", "source_sha256", "converter_id",
                "converter_version", "sanitizer_policy", "sanitizer_version",
            )
        }


def derive_projection_id(**identity: str) -> str:
    """Return a stable id from the complete canonical projection identity."""
    _validate_sha256(identity["source_sha256"], "source_sha256")
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"hproj-{hashlib.sha256(payload.encode()).hexdigest()}"


def derive_anchor_id(projection_id: str, locator: SourceLocator) -> str:
    """Return an HTML-safe anchor id for a resolved immutable locator."""
    payload = locator.model_dump_json(exclude_none=True)
    digest = hashlib.sha256(f"{projection_id}\x00{payload}".encode()).hexdigest()
    return f"antiek-anchor-{digest}"


def _validate_object_key(value: str) -> None:
    split = urlsplit(value)
    path = PurePosixPath(value)
    if (
        not value
        or split.scheme
        or split.netloc
        or split.query
        or split.fragment
        or value.startswith("/")
        or "\\" in value
        or "%" in value
        or any(part in {".", ".."} for part in value.split("/"))
        or path.is_absolute()
    ):
        raise ValueError("hosted_html_locator must be a safe relative object key")


def _validate_sha256(value: str, field: str) -> None:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be exact lowercase SHA-256 hex")


__all__ = [
    "AnchorMapping", "HtmlProjectionContract", "PdfPageLocator", "ProjectionStatus",
    "ReasonCode", "SemanticLocator", "SourceLocator", "TextLocator", "derive_anchor_id",
    "derive_projection_id",
]
