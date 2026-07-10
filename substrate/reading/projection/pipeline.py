"""Pure preparation and explicit short-write lifecycle orchestration."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Literal

from substrate.contracts.html_projection import AnchorMapping, HtmlProjectionContract
from substrate.reading.projection.pdf_adapter import convert_pdf
from substrate.reading.projection.store import ProjectionConflict, ProjectionStore


@dataclass(frozen=True)
class PreparedProjection:
    lifecycle_targets: tuple[HtmlProjectionContract, ...]
    html_bytes: bytes | None
    html_sha256: str | None
    anchor_mappings: tuple[AnchorMapping, ...]
    terminal_status: Literal["ready", "ocr_required", "failed"]
    machine_detail: Literal[
        "conversion_ready", "no_meaningful_text", "invalid_pdf",
        "page_extraction_failed", "script_gate_rejected",
        "resource_limit_exceeded",
    ]
    evidence_count: int = 0


def prepare_projection(
    queued: HtmlProjectionContract, source_bytes: bytes,
) -> PreparedProjection:
    """Prepare conversion fully off-lock; reject identity mistakes before parsing."""
    if queued.status != "queued":
        raise ValueError("projection must be queued")
    actual_sha = hashlib.sha256(source_bytes).hexdigest()
    if actual_sha != queued.source_sha256:
        raise ValueError("source SHA-256 mismatch")

    extracting = _target(queued, "extracting")
    result = convert_pdf(source_bytes, queued)
    if result.outcome == "ready":
        if result.html_bytes is None:
            raise ValueError("ready conversion omitted HTML bytes")
        sanitizing = _target(queued, "sanitizing")
        return PreparedProjection(
            lifecycle_targets=(extracting, sanitizing), html_bytes=result.html_bytes,
            html_sha256=hashlib.sha256(result.html_bytes).hexdigest(),
            anchor_mappings=result.anchor_mappings, terminal_status="ready",
            machine_detail="conversion_ready",
        )
    if result.outcome == "ocr_required":
        ocr = _target(queued, "ocr_required")
        return PreparedProjection(
            lifecycle_targets=(extracting, ocr), html_bytes=None, html_sha256=None,
            anchor_mappings=(), terminal_status="ocr_required",
            machine_detail="no_meaningful_text", evidence_count=result.page_count,
        )
    failed = _target(queued, "failed", reason_code="conversion_failed")
    return PreparedProjection(
        lifecycle_targets=(extracting, failed), html_bytes=None, html_sha256=None,
        anchor_mappings=(), terminal_status="failed",
        machine_detail=result.reason or "invalid_pdf",
        evidence_count=result.failed_page_count,
    )


def finalize_projection(
    prepared: PreparedProjection, hosted_html_locator: str,
) -> PreparedProjection:
    """Add `ready` only after the caller has stored the prepared HTML off-lock."""
    if prepared.terminal_status != "ready" or prepared.html_sha256 is None:
        raise ValueError("only a successful prepared projection can be finalized")
    if prepared.lifecycle_targets[-1].status == "ready":
        ready = prepared.lifecycle_targets[-1]
        if ready.hosted_html_locator != hosted_html_locator:
            raise ValueError("projection already finalized with a different locator")
        return prepared
    ready = _target(
        prepared.lifecycle_targets[-1], "ready", hosted_html_locator=hosted_html_locator,
        hosted_html_sha256=prepared.html_sha256, anchor_mappings=prepared.anchor_mappings,
    )
    return replace(prepared, lifecycle_targets=(*prepared.lifecycle_targets, ready))


def persist_prepared_projection(
    store: ProjectionStore, queued: HtmlProjectionContract, prepared: PreparedProjection,
) -> HtmlProjectionContract:
    """Apply precomputed targets only; caller owns the transaction and store."""
    store.ensure_tables()
    try:
        current = store.load(queued.projection_id)
    except KeyError:
        current = store.claim(queued)
    states = (queued, *prepared.lifecycle_targets)
    try:
        current_index = states.index(current)
    except ValueError as exc:
        raise ProjectionConflict("stored projection conflicts with prepared lifecycle") from exc
    for target in states[current_index + 1:]:
        current = store.transition(target)
    return current


def _target(base: HtmlProjectionContract, status: str, **updates: object) -> HtmlProjectionContract:
    values = base.model_dump()
    values.update(
        status=status, hosted_html_locator=None, hosted_html_sha256=None,
        reason_code=None, anchor_mappings=(),
    )
    values.update(updates)
    return HtmlProjectionContract.model_validate(values)


__all__ = [
    "PreparedProjection", "finalize_projection", "persist_prepared_projection",
    "prepare_projection",
]
