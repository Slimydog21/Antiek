"""Deterministic provider-free briefing over one derived evidence pack."""

from __future__ import annotations

import hashlib
import html
import json
import re
from typing import Any, Final

from .derived_companion import EVIDENCE_PACK_VERSION

SCHEMA_VERSION: Final = "antiek.derived-evidence-briefing.v1"
MAX_BRIEFING_BYTES: Final = 256 * 1024
_SHA = re.compile(r"[0-9a-f]{64}")
_CITATION = re.compile(r"dchunk_[0-9a-f]{64}")
_ASSET = re.compile(r"ast_[0-9a-f]{32}")
_REVISION = re.compile(r"rev_[0-9a-f]{32}")
_PACK_KEYS = {
    "version", "derived_asset_id", "revision_id", "content_sha256", "generation",
    "is_current", "index_sha256", "chunker", "retrieval", "citations", "pack_sha256",
}
_CITATION_KEYS = {
    "citation_id", "chunk_ordinal", "member_index", "section_anchor", "section_path",
    "text", "text_sha256",
}


class EvidenceBriefingError(RuntimeError):
    pass


def build_evidence_briefing(question: str, pack: dict[str, Any]) -> dict[str, Any]:
    try:
        return _build_evidence_briefing(question, pack)
    except EvidenceBriefingError:
        raise
    except (TypeError, ValueError, UnicodeError, OverflowError) as exc:
        raise EvidenceBriefingError("briefing input is malformed") from exc


def _build_evidence_briefing(question: str, pack: dict[str, Any]) -> dict[str, Any]:
    normalized_question = question.strip() if isinstance(question, str) else ""
    if not normalized_question or len(normalized_question.encode("utf-8")) > 8 * 1024:
        raise EvidenceBriefingError("briefing question is invalid")
    _validate_pack(pack, normalized_question)
    groups: list[dict[str, Any]] = []
    group_by_path: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for citation in pack["citations"]:
        citation_id = str(citation["citation_id"])
        if citation_id in seen:
            raise EvidenceBriefingError("briefing citation identity is duplicated")
        seen.add(citation_id)
        path = str(citation["section_path"])
        group = group_by_path.get(path)
        if group is None:
            group = {"section_path": path, "passages": []}
            group_by_path[path] = group
            groups.append(group)
        group["passages"].append({key: citation[key] for key in (
            "citation_id", "chunk_ordinal", "member_index", "section_anchor",
            "section_path", "text", "text_sha256",
        )})
    body = {
        "schema_version": SCHEMA_VERSION,
        "question": normalized_question,
        "question_sha256": _sha(normalized_question),
        "derived_asset_id": pack["derived_asset_id"],
        "revision_id": pack["revision_id"],
        "content_sha256": pack["content_sha256"],
        "generation": pack["generation"],
        "evidence_pack_sha256": pack["pack_sha256"],
        "section_count": len(groups),
        "passage_count": len(pack["citations"]),
        "sections": groups,
    }
    body["briefing_json_sha256"] = _sha(_json(body))
    _enforce_limit(_json(body), "briefing JSON")
    rendered = _render(body)
    _enforce_limit(rendered, "briefing HTML")
    body["briefing_html"] = rendered
    body["briefing_html_sha256"] = _sha(rendered)
    body["artifact_sha256"] = _sha(_json(body))
    _enforce_limit(_json(body), "briefing artifact")
    return body


def _validate_pack(pack: object, question: str) -> None:
    if not isinstance(pack, dict) or set(pack) != _PACK_KEYS:
        raise EvidenceBriefingError("evidence pack shape is invalid")
    if pack.get("version") != EVIDENCE_PACK_VERSION:
        raise EvidenceBriefingError("evidence pack version is invalid")
    pack_sha = pack.get("pack_sha256")
    payload = {key: value for key, value in pack.items() if key != "pack_sha256"}
    if not isinstance(pack_sha, str) or not _SHA.fullmatch(pack_sha) or _sha(_json(payload)) != pack_sha:
        raise EvidenceBriefingError("evidence pack digest conflicts")
    retrieval = pack.get("retrieval")
    if not isinstance(retrieval, dict) or retrieval.get("query_sha256") != _sha(question):
        raise EvidenceBriefingError("briefing question does not bind the evidence pack")
    chunker = pack.get("chunker")
    if (not isinstance(chunker, dict) or set(chunker) != {"policy", "version"}
            or not isinstance(chunker.get("policy"), str) or not chunker["policy"]
            or not _valid_version(chunker.get("version"))):
        raise EvidenceBriefingError("evidence pack chunker is invalid")
    if not isinstance(pack.get("citations"), list) or not pack["citations"]:
        raise EvidenceBriefingError("briefing requires evidence citations")
    if not _positive_int(pack.get("generation")):
        raise EvidenceBriefingError("evidence pack generation is invalid")
    if not isinstance(pack.get("derived_asset_id"), str) or not _ASSET.fullmatch(
        pack["derived_asset_id"]
    ):
        raise EvidenceBriefingError("evidence pack scope is invalid")
    if not isinstance(pack.get("revision_id"), str) or not _REVISION.fullmatch(
        pack["revision_id"]
    ):
        raise EvidenceBriefingError("evidence pack scope is invalid")
    if not isinstance(pack.get("content_sha256"), str) or not _SHA.fullmatch(pack["content_sha256"]):
        raise EvidenceBriefingError("evidence pack content digest is invalid")
    if not isinstance(pack.get("index_sha256"), str) or not _SHA.fullmatch(pack["index_sha256"]):
        raise EvidenceBriefingError("evidence pack index digest is invalid")
    if not isinstance(pack.get("is_current"), bool):
        raise EvidenceBriefingError("evidence pack current state is invalid")
    if (set(retrieval) != {"mode", "query_sha256", "top_k"}
            or retrieval.get("mode") != "deterministic_lexical_v1"
            or not _positive_int(retrieval.get("top_k"))):
        raise EvidenceBriefingError("evidence pack retrieval is invalid")
    for citation in pack["citations"]:
        if not isinstance(citation, dict) or set(citation) != _CITATION_KEYS:
            raise EvidenceBriefingError("evidence citation shape is invalid")
        if not _CITATION.fullmatch(str(citation["citation_id"])):
            raise EvidenceBriefingError("evidence citation identity is invalid")
        text = citation["text"]
        if not isinstance(text, str) or not text or _sha(text) != citation["text_sha256"]:
            raise EvidenceBriefingError("evidence citation text conflicts")
        if (not isinstance(citation["section_anchor"], str) or not citation["section_anchor"]
                or not isinstance(citation["section_path"], str)):
            raise EvidenceBriefingError("evidence citation section is invalid")
        if not all(isinstance(citation[key], int) and not isinstance(citation[key], bool)
                   and citation[key] >= 0
                   for key in ("chunk_ordinal", "member_index")):
            raise EvidenceBriefingError("evidence citation ordinal is invalid")


def _render(body: dict[str, Any]) -> str:
    sections = []
    for section in body["sections"]:
        label = section["section_path"] or "Untitled section"
        passages = "".join(
            '<blockquote data-citation-id="{}" data-section-anchor="{}"><p>{}</p></blockquote>'.format(
                html.escape(item["citation_id"], quote=True),
                html.escape(item["section_anchor"], quote=True),
                html.escape(item["text"]),
            )
            for item in section["passages"]
        )
        sections.append(f"<section><h3>{html.escape(label)}</h3>{passages}</section>")
    return (
        f'<article data-schema-version="{SCHEMA_VERSION}">'
        f"<header><h2>Evidence briefing</h2><p>{html.escape(body['question'])}</p></header>"
        + "".join(sections)
        + "</article>"
    )


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _valid_version(value: object) -> bool:
    return _positive_int(value) or isinstance(value, str) and bool(value)


def _enforce_limit(value: str, label: str) -> None:
    if len(value.encode("utf-8")) > MAX_BRIEFING_BYTES:
        raise EvidenceBriefingError(f"{label} exceeds its byte limit")


__all__ = ["EvidenceBriefingError", "SCHEMA_VERSION", "build_evidence_briefing"]
