"""Exact-text validity for Write paragraph provenance."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Literal

SCHEMA_VERSION = 1
ParagraphStatus = Literal[
    "current", "stale", "unsupported", "ungrounded", "legacy_unverified"
]
MutationOrigin = Literal["generated", "manual", "ai_assisted", "legacy"]


def paragraphs(prose_text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n", prose_text.strip()) if part.strip()]


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _aggregate(items: list[dict[str, Any]]) -> str:
    statuses = {item["status"] for item in items}
    if not statuses:
        return "ungrounded"
    if statuses == {"current"}:
        return "current"
    if "current" in statuses:
        return "partial"
    if "stale" in statuses:
        return "stale"
    if "legacy_unverified" in statuses:
        return "legacy_unverified"
    if "unsupported" in statuses:
        return "unsupported"
    return "ungrounded"


def _document(prose_text: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "prose_sha256": text_sha256(prose_text),
        "status": _aggregate(items),
        "paragraphs": {str(index): item for index, item in enumerate(items)},
    }


def generated_validity(
    prose_text: str,
    provenance: dict[str, list[str]],
    *,
    unsupported_paragraphs: set[int] | None = None,
) -> dict[str, Any]:
    unsupported = unsupported_paragraphs or set()
    items: list[dict[str, Any]] = []
    for index, paragraph in enumerate(paragraphs(prose_text)):
        block_ids = provenance.get(str(index), [])
        if index in unsupported:
            status: ParagraphStatus = "unsupported"
        elif block_ids:
            status = "current"
        else:
            status = "ungrounded"
        items.append(
            {
                "text_sha256": text_sha256(paragraph),
                "status": status,
                "origin": "generated",
            }
        )
    return _document(prose_text, items)


def read_validity(
    prose_text: str | None,
    provenance: dict[str, list[str]] | None,
    raw_validity: str | dict[str, Any] | None,
) -> dict[str, Any]:
    prose = prose_text or ""
    paras = paragraphs(prose)
    fallback_status: ParagraphStatus = (
        "legacy_unverified" if provenance else "ungrounded"
    )

    try:
        value = json.loads(raw_validity) if isinstance(raw_validity, str) else raw_validity
        if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported validity document")
        if value.get("prose_sha256") != text_sha256(prose):
            raise ValueError("validity is not bound to current prose")
        raw_paragraphs = value.get("paragraphs")
        if not isinstance(raw_paragraphs, dict) or len(raw_paragraphs) != len(paras):
            raise ValueError("paragraph validity cardinality mismatch")
        items: list[dict[str, Any]] = []
        for index, paragraph in enumerate(paras):
            item = raw_paragraphs.get(str(index))
            if not isinstance(item, dict):
                raise ValueError("missing paragraph validity")
            status = item.get("status")
            origin = item.get("origin")
            if status not in {
                "current", "stale", "unsupported", "ungrounded", "legacy_unverified"
            } or origin not in {"generated", "manual", "ai_assisted", "legacy"}:
                raise ValueError("unknown paragraph validity value")
            if item.get("text_sha256") != text_sha256(paragraph):
                raise ValueError("paragraph validity hash mismatch")
            items.append(
                {"text_sha256": item["text_sha256"], "status": status, "origin": origin}
            )
        return _document(prose, items)
    except (TypeError, ValueError, json.JSONDecodeError):
        return _document(
            prose,
            [
                {
                    "text_sha256": text_sha256(paragraph),
                    "status": fallback_status,
                    "origin": "legacy",
                }
                for paragraph in paras
            ],
        )


def edited_provenance(
    *,
    old_prose: str,
    new_prose: str,
    old_provenance: dict[str, list[str]] | None,
    old_validity: dict[str, Any],
    origin: Literal["manual", "ai_assisted"],
) -> tuple[dict[str, list[str]] | None, dict[str, Any]]:
    old_paras = paragraphs(old_prose)
    new_paras = paragraphs(new_prose)
    old_counts = Counter(old_paras)
    new_counts = Counter(new_paras)
    matcher = SequenceMatcher(a=old_paras, b=new_paras, autojunk=False)
    exact_matches: dict[int, int] = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            old_index = block.a + offset
            new_index = block.b + offset
            text = old_paras[old_index]
            if old_counts[text] == 1 and new_counts[text] == 1:
                exact_matches[new_index] = old_index

    stale_new_indices: set[int] = set()
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "insert":
            continue
        for new_index in range(new_start, new_end):
            if new_index in exact_matches:
                continue
            if any(str(old_index) in (old_provenance or {}) for old_index in range(old_start, old_end)):
                stale_new_indices.add(new_index)

    old_items = old_validity.get("paragraphs", {})
    new_provenance: dict[str, list[str]] = {}
    items: list[dict[str, Any]] = []
    for new_index, paragraph in enumerate(new_paras):
        old_index = exact_matches.get(new_index)
        old_item = old_items.get(str(old_index)) if old_index is not None else None
        if isinstance(old_item, dict):
            status = old_item["status"]
            item_origin = old_item["origin"]
            block_ids = (old_provenance or {}).get(str(old_index), [])
            if status == "current" and block_ids:
                new_provenance[str(new_index)] = list(block_ids)
        else:
            status = "stale" if new_index in stale_new_indices else "ungrounded"
            item_origin = origin
        items.append(
            {
                "text_sha256": text_sha256(paragraph),
                "status": status,
                "origin": item_origin,
            }
        )
    return (new_provenance or None), _document(new_prose, items)
