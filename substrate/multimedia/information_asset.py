"""Deterministic HTML knowledge-asset projection for multimedia revisions."""

from __future__ import annotations

import hashlib
import html
import json
import re
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from services.html_projection.gate import ScriptViolation, assert_script_free
from substrate.contracts.multimedia import MultimediaStatus, ScriptLine
from substrate.multimedia.read_model import MultimediaAssetRecord

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_HTML_BYTES = 16 * 1024 * 1024


class MultimediaInformationAssetError(RuntimeError):
    """Projection or canonical registration could not be proven."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MultimediaSourceReference(_FrozenModel):
    citation_id: str = Field(pattern=_DIGEST.pattern)
    line_id: str
    chunk_id: str
    document_id: str
    locator: str | None = None
    quote_sha256: str | None = Field(default=None, pattern=_DIGEST.pattern)


class MultimediaInformationAsset(_FrozenModel):
    schema_version: Literal["antiek.multimedia-information-asset.v1"] = (
        "antiek.multimedia-information-asset.v1"
    )
    owner_identity_digest: str = Field(pattern=_DIGEST.pattern)
    asset_id: str
    revision_id: str
    title: str
    html: str
    html_sha256: str = Field(pattern=_DIGEST.pattern)
    source_references: tuple[MultimediaSourceReference, ...]


class MultimediaKnowledgeRegistrationReceipt(_FrozenModel):
    schema_version: Literal["antiek.multimedia-knowledge-registration.v1"] = (
        "antiek.multimedia-knowledge-registration.v1"
    )
    owner_identity_digest: str = Field(pattern=_DIGEST.pattern)
    asset_id: str
    revision_id: str
    html_sha256: str = Field(pattern=_DIGEST.pattern)
    graph_node_id: str
    twin_document_id: str


class MultimediaKnowledgeRegistrar(Protocol):
    def register(
        self, asset: MultimediaInformationAsset
    ) -> MultimediaKnowledgeRegistrationReceipt: ...


def project_multimedia_information_asset(
    record: MultimediaAssetRecord, *, owner_id: str
) -> MultimediaInformationAsset:
    """Project one ready, owner-consistent revision to inert standalone HTML."""
    normalized_owner = _normalized_owner(owner_id)
    owner_digest = _owner_digest(normalized_owner)
    if record.asset.owner_user_id != owner_digest:
        raise MultimediaInformationAssetError("multimedia owner identity conflicts")
    if record.asset.status != MultimediaStatus.READY:
        raise MultimediaInformationAssetError("multimedia revision is not ready")
    _verify_projection_inputs(record)

    references = _source_references(record)
    rendered = _render_html(record, normalized_owner, references)
    raw = rendered.encode("utf-8")
    if len(raw) > _MAX_HTML_BYTES:
        raise MultimediaInformationAssetError("multimedia HTML exceeds its byte bound")
    try:
        assert_script_free(rendered)
    except ScriptViolation as exc:
        raise MultimediaInformationAssetError("multimedia HTML is not inert") from exc
    return MultimediaInformationAsset(
        owner_identity_digest=owner_digest,
        asset_id=record.asset.asset_id,
        revision_id=record.asset.revision_id,
        title=record.asset.title,
        html=rendered,
        html_sha256=hashlib.sha256(raw).hexdigest(),
        source_references=references,
    )


def register_multimedia_information_asset(
    asset: MultimediaInformationAsset,
    *,
    registrar: MultimediaKnowledgeRegistrar,
) -> MultimediaKnowledgeRegistrationReceipt:
    """Register through canonical graph/twin authority and verify its receipt."""
    if asset.schema_version != "antiek.multimedia-information-asset.v1":
        raise MultimediaInformationAssetError("multimedia information schema conflicts")
    if hashlib.sha256(asset.html.encode("utf-8")).hexdigest() != asset.html_sha256:
        raise MultimediaInformationAssetError("multimedia HTML digest conflicts")
    receipt = registrar.register(asset)
    if receipt.schema_version != "antiek.multimedia-knowledge-registration.v1":
        raise MultimediaInformationAssetError("knowledge registration schema conflicts")
    expected = (
        asset.owner_identity_digest,
        asset.asset_id,
        asset.revision_id,
        asset.html_sha256,
    )
    actual = (
        receipt.owner_identity_digest,
        receipt.asset_id,
        receipt.revision_id,
        receipt.html_sha256,
    )
    if actual != expected:
        raise MultimediaInformationAssetError("knowledge registration receipt conflicts")
    if not _IDENTIFIER.fullmatch(receipt.graph_node_id) or not _IDENTIFIER.fullmatch(
        receipt.twin_document_id
    ):
        raise MultimediaInformationAssetError("knowledge registration identity is invalid")
    return receipt


def _source_references(
    record: MultimediaAssetRecord,
) -> tuple[MultimediaSourceReference, ...]:
    return tuple(
        MultimediaSourceReference(
            citation_id=_citation_id(
                line.line_id,
                citation.chunk_id,
                citation.document_id,
                citation.locator,
                citation.quote_sha256,
            ),
            line_id=line.line_id,
            chunk_id=citation.chunk_id,
            document_id=citation.document_id,
            locator=citation.locator,
            quote_sha256=citation.quote_sha256,
        )
        for line in record.asset.manifest.script_lines
        for citation in line.citations
    )


def _verify_projection_inputs(record: MultimediaAssetRecord) -> None:
    manifest = record.asset.manifest
    line_ids = [line.line_id for line in manifest.script_lines]
    if len(line_ids) != len(set(line_ids)):
        raise MultimediaInformationAssetError("multimedia transcript identity conflicts")
    ordered_lines = [line.line_id for line in sorted(manifest.script_lines, key=lambda row: row.sequence)]
    segments = sorted(manifest.segments, key=lambda row: row.sequence)
    if [segment.sequence for segment in segments] != list(range(len(segments))):
        raise MultimediaInformationAssetError("multimedia chapter sequence conflicts")
    projected_lines = [line_id for segment in segments for line_id in segment.script_line_ids]
    if projected_lines != ordered_lines:
        raise MultimediaInformationAssetError("multimedia transcript coverage conflicts")
    expected_claims = {
        line.line_id: tuple(citation.chunk_id for citation in line.citations)
        for line in manifest.script_lines
        if line.citations
    }
    actual_claims: dict[str, tuple[str, ...]] = {}
    for claim in manifest.claim_to_chunk:
        if claim.script_line_id in actual_claims:
            raise MultimediaInformationAssetError("multimedia grounding map conflicts")
        actual_claims[claim.script_line_id] = claim.chunk_ids
    if actual_claims != expected_claims:
        raise MultimediaInformationAssetError("multimedia grounding map conflicts")
    citation_by_chunk: dict[str, tuple[str, str | None, str | None]] = {}
    for line in manifest.script_lines:
        for citation in line.citations:
            identity = (citation.document_id, citation.locator, citation.quote_sha256)
            previous = citation_by_chunk.setdefault(citation.chunk_id, identity)
            if previous != identity:
                raise MultimediaInformationAssetError("multimedia citation identity conflicts")
    if any(
        citation.quote_sha256 is None
        for line in manifest.script_lines
        for citation in line.citations
    ):
        raise MultimediaInformationAssetError("multimedia source digest is missing")


def _render_html(
    record: MultimediaAssetRecord,
    owner_id: str,
    references: tuple[MultimediaSourceReference, ...],
) -> str:
    asset = record.asset
    lines = {line.line_id: line for line in asset.manifest.script_lines}
    chapters: list[str] = []
    for segment in sorted(asset.manifest.segments, key=lambda item: item.sequence):
        transcript = "".join(
            _line_html(lines[line_id]) for line_id in segment.script_line_ids if line_id in lines
        )
        source_ids = " ".join(_esc(chunk_id) for chunk_id in segment.source_chunk_ids)
        chapters.append(
            f'<section class="chapter" data-segment-id="{_esc(segment.segment_id)}" '
            f'data-source-chunk-ids="{source_ids}"><h2>{_esc(segment.title)}</h2>{transcript}</section>'
        )
    sources = "".join(
        f'<li data-citation-id="{ref.citation_id}" data-chunk-id="{_esc(ref.chunk_id)}" '
        f'data-document-id="{_esc(ref.document_id)}" data-line-id="{_esc(ref.line_id)}" '
        f'data-quote-sha256="{_esc(ref.quote_sha256 or "")}"><strong>{_esc(ref.document_id)}</strong>'
        f'{f" <span>{_esc(ref.locator)}</span>" if ref.locator else ""}</li>'
        for ref in references
    ) or '<li class="empty">No source references are attached.</li>'
    files = "".join(
        f'<li data-file-id="{_esc(item.file_id)}" data-sha256="{_esc(item.sha256)}">'
        f'<strong>{_esc(item.kind)}</strong> <code>{_esc(item.storage_uri)}</code> '
        f'<span>{_esc(item.mime)}</span></li>'
        for item in asset.manifest.files
    ) or '<li class="empty">No media files are attached.</li>'
    cost = sum(row.cost_usd for row in asset.manifest.cost_rows)
    metadata = json.dumps(
        {
            "schema_version": "antiek.multimedia-information-metadata.v1",
            "owner_identity_digest": _owner_digest(owner_id),
            "asset_id": asset.asset_id,
            "revision_id": asset.revision_id,
            "route_policy": asset.route_policy,
            "source_references": [ref.model_dump(mode="json") for ref in references],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(asset.title)}</title><style>body{{max-width:760px;margin:auto;padding:28px;font:16px/1.6 system-ui;color:#18181b;background:#fafafa}}h1,h2{{line-height:1.2}}.meta,footer{{color:#52525b}}section{{border-top:1px solid #d4d4d8;padding:18px 0}}code{{overflow-wrap:anywhere}}.empty{{font-style:italic}}</style></head>
<body><main data-asset-id="{_esc(asset.asset_id)}" data-revision-id="{_esc(asset.revision_id)}" data-owner-digest="{_owner_digest(owner_id)}">
<p class="meta">Antiek multimedia knowledge asset</p><h1>{_esc(asset.title)}</h1>
<p>{_esc(asset.user_prompt)}</p><dl><dt>Format</dt><dd>{_esc(asset.kind)}</dd><dt>Duration</dt><dd>{asset.requested_duration_minutes} minutes</dd><dt>Route</dt><dd>{_esc(asset.route_policy)}</dd><dt>Recorded cost</dt><dd>${cost:.4f}</dd></dl>
<section><h2>Transcript</h2>{''.join(chapters)}</section>
<section><h2>Sources</h2><ol>{sources}</ol></section>
<section><h2>Media manifest</h2><ul>{files}</ul></section>
<template id="antiek-multimedia-metadata">{_esc(metadata)}</template>
<footer>Asset {_esc(asset.asset_id)} · revision {_esc(asset.revision_id)} · generated media may contain synthetic narration or visuals.</footer>
</main></body></html>'''


def _line_html(line: ScriptLine) -> str:
    cited = " ".join(_esc(citation.chunk_id) for citation in line.citations)
    citation_ids = " ".join(
        _citation_id(
            line.line_id,
            citation.chunk_id,
            citation.document_id,
            citation.locator,
            citation.quote_sha256,
        )
        for citation in line.citations
    )
    return (
        f'<p data-line-id="{_esc(line.line_id)}" data-kind="{_esc(line.kind)}" '
        f'data-cited-chunk-ids="{cited}" data-citation-ids="{citation_ids}" '
        f'data-unsourced-reason="{_esc(line.unsourced_reason or "")}">{_esc(line.text)}</p>'
    )


def _normalized_owner(owner_id: str) -> str:
    if not isinstance(owner_id, str):
        raise MultimediaInformationAssetError("multimedia owner identity is invalid")
    normalized = owner_id.strip()
    encoded = normalized.encode("utf-8")
    if not encoded or len(encoded) > 512 or any(byte < 32 or byte == 127 for byte in encoded):
        raise MultimediaInformationAssetError("multimedia owner identity is invalid")
    return normalized


def _owner_digest(owner_id: str) -> str:
    return hashlib.sha256(owner_id.encode("utf-8")).hexdigest()


def _citation_id(
    line_id: str,
    chunk_id: str,
    document_id: str,
    locator: str | None,
    quote_sha256: str | None,
) -> str:
    payload = json.dumps(
        [line_id, chunk_id, document_id, locator, quote_sha256], separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


__all__ = [
    "MultimediaInformationAsset",
    "MultimediaInformationAssetError",
    "MultimediaKnowledgeRegistrar",
    "MultimediaKnowledgeRegistrationReceipt",
    "MultimediaSourceReference",
    "project_multimedia_information_asset",
    "register_multimedia_information_asset",
]
