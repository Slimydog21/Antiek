"""Write informs: the ordered documents that inform one Write block.

THREAD-CONTRACT §1.11a "Write informs (S5)" (signed rev 8.10) and Part 2
"Saving". A PUT replaces one block's whole list by committing one §1.11
``revise`` (``operation: informs``) with compare-and-set on the current
revision. The block's text is unchanged; every other block's list is carried
forward, so a write to one block can never erase another's, and a writer
holding a stale revision gets ``revision_moved`` instead of overwriting.

The checks run in the signed order (A6 in
docs/decisions/derived-asset-revise-primitive.md): the asset is the
requester's, then an idempotent replay or conflict, then the block is in the
current revision, then the compare-and-set, then the list itself. Only a
commit writes the idempotency record, so a refusal never burns a key.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from runtime.db_lock import LockedConnection, ReadConnection
from substrate.books.servability import is_servable_full_text, servability_of
from substrate.contracts.html_projection import TextLocator
from substrate.derived_assets.repository import (
    Checkpoint,
    ChildPatch,
    Head,
    IdempotencyConflict,
    NotFound,
    StoredOperation,
    block_in_revision,
    canonical_json,
    check_expected,
    find_operation,
    load_owned_head,
    revise,
)
from substrate.feedback.domain import normalize_node_text
from substrate.graph.retrieval_gate import PERSONAL_ONLY_CONTENT_CLASSES
from substrate.rights.register import VALID_CONTENT_CLASSES

OPERATION = "informs"
MAX_INFORMS = 50
MAX_IDEMPOTENCY_KEY = 256
_BODY_FIELDS = frozenset({"informs", "expected_revision_id", "idempotency_key"})
_ENTRY_FIELDS = frozenset({"document_id", "anchor"})
_WRITE_PREFIX = "write:"
# ``write-<deliverable_id>`` must be a safe event-storage id (the pattern in
# substrate.event_log.events.investigation_event_lock, 200 characters).
_DELIVERABLE_ID = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,193}")

_Connection = ReadConnection | LockedConnection


class InformsBodyInvalid(ValueError):
    """The request body is not the signed envelope (a client programming error)."""


class InformsInvalid(ValueError):
    """``422 informs_invalid {index, detail}``: the lowest failing entry.

    ``detail`` is one of ``too_many_entries`` (at index 50),
    ``duplicate_document`` (at the second occurrence), ``document_not_readable``,
    ``anchor_other_document``, ``anchor_invalid``, ``entry_invalid``.
    """

    def __init__(self, index: int, detail: str) -> None:
        super().__init__(f"{detail} at {index}")
        self.index = index
        self.detail = detail


class InformsAnchor(BaseModel):
    """The §1.4 anchor shape, field for field. No ``anchor_id``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(min_length=1)
    source_locator: TextLocator | None = None
    region_id: str | None = None
    quote: str | None = None
    prefix: str | None = None
    suffix: str | None = None
    page_index: int | None = Field(default=None, ge=0)


@dataclass(frozen=True)
class InformsRequest:
    informs: list[Any]
    expected_revision_id: str
    idempotency_key: str
    request_sha256: str


@dataclass(frozen=True)
class ValidEntry:
    document_id: str
    anchor: dict[str, Any] | None


def deliverable_of(asset_id: str) -> str | None:
    """The deliverable a ``write:<deliverable_id>`` asset maps to (§1.11 "One
    canonical mapping"), or None: informs exist only for Write blocks."""
    if not asset_id.startswith(_WRITE_PREFIX):
        return None
    deliverable_id = asset_id[len(_WRITE_PREFIX):]
    return deliverable_id if _DELIVERABLE_ID.fullmatch(deliverable_id) else None


def write_log_id(asset_id: str) -> str | None:
    """The event log of a Write asset, ``write-<deliverable_id>`` (rev 8.11 D1),
    mirroring ``read-<document_id>``."""
    deliverable_id = deliverable_of(asset_id)
    return None if deliverable_id is None else f"write-{deliverable_id}"


def request_sha256(asset_id: str, block_id: str, body: Mapping[str, Any]) -> str:
    """The request identity (A4): sha256 of the canonical JSON of the path and
    the body as sent. No text normalization: a retry resends the same bytes."""
    encoded = canonical_json({"asset_id": asset_id, "block_id": block_id, "body": body}).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _refuse_constant(name: str) -> None:
    raise ValueError(f"{name} is not JSON")


def parse_body(asset_id: str, block_id: str, raw: bytes) -> InformsRequest:
    """Exactly ``{informs: [...], expected_revision_id, idempotency_key}``."""
    try:
        body = json.loads(raw, parse_constant=_refuse_constant)
    except (ValueError, RecursionError) as exc:
        raise InformsBodyInvalid("the body is not JSON") from exc
    if not isinstance(body, dict) or set(body) != _BODY_FIELDS:
        raise InformsBodyInvalid("the body is exactly informs, expected_revision_id and idempotency_key")
    informs, expected, key = body["informs"], body["expected_revision_id"], body["idempotency_key"]
    if not isinstance(informs, list):
        raise InformsBodyInvalid("informs is a list")
    if not isinstance(expected, str) or not expected:
        raise InformsBodyInvalid("expected_revision_id is a non-empty string")
    if not isinstance(key, str) or not 1 <= len(key) <= MAX_IDEMPOTENCY_KEY:
        raise InformsBodyInvalid("idempotency_key is 1..256 characters")
    try:
        identity = request_sha256(asset_id, block_id, body)
    except UnicodeEncodeError as exc:  # a lone surrogate cannot be stored either
        raise InformsBodyInvalid("the body is not valid UTF-8 text") from exc
    return InformsRequest(informs, expected, key, identity)


# ── the readability predicate ──────────────────────────────────────────────
#
# Private to informs, and a local copy on purpose: this module edits no rights
# or auth file. A06's planned substrate/rights/document_visibility.py replaces
# it, and informs become a row in A06's saved-reference ledger.
#
# Readable means all of: the document exists; its content_class is NULL
# (grandfathered legacy rows) or in the canonical vocabulary, so an unknown
# non-NULL class fails closed (user_authored_private included, until PA04);
# and an owner-only class belongs to the requester. Legacy user_owned keeps its
# current behaviour and reads as readable (OPEN until PA06). A gated class is
# readable as a reference: citing a source that is not servable is allowed.
# A missing document, another owner's private one, and an unknown class all
# get the same detail, so the answer never discloses which.


def _document_rights(con: _Connection, document_ids: Sequence[str]) -> dict[str, tuple[str | None, str]]:
    if not document_ids:
        return {}
    placeholders = ", ".join("?" for _ in document_ids)
    rows = con.execute(
        "SELECT document_id, content_class, owner_user_id FROM documents "
        f"WHERE document_id IN ({placeholders})",
        list(document_ids),
    ).fetchall()
    return {str(row[0]): (None if row[1] is None else str(row[1]), str(row[2])) for row in rows}


def _readable(content_class: str | None, document_owner: str, requester: str) -> bool:
    if content_class is not None and content_class not in VALID_CONTENT_CLASSES:
        return False
    return content_class not in PERSONAL_ONLY_CONTENT_CLASSES or document_owner == requester


def _entry_document_id(entry: object) -> str | None:
    if not isinstance(entry, dict) or not set(entry) <= _ENTRY_FIELDS:
        return None
    document_id = entry.get("document_id")
    return document_id if isinstance(document_id, str) and document_id else None


def _anchor(value: object, index: int) -> InformsAnchor | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise InformsInvalid(index, "anchor_invalid")
    try:
        return InformsAnchor.model_validate(value, strict=True)
    except ValidationError:
        raise InformsInvalid(index, "anchor_invalid") from None


def _stored_anchor(anchor: InformsAnchor, *, servable: bool) -> dict[str, Any]:
    """The anchor as persisted and answered. Cite-only: the quote, prefix and
    suffix are kept only when the document is servable, normalized to
    ``unicode-nfc-v1``; otherwise they are dropped (§1.4, the cite-only rule
    for anchors)."""
    stored: dict[str, Any] = {"document_id": anchor.document_id}
    if anchor.source_locator is not None:
        locator = anchor.source_locator
        stored["source_locator"] = {"start": locator.start, "end": locator.end, "text_sha256": locator.text_sha256}
    if anchor.region_id is not None:
        stored["region_id"] = anchor.region_id
    if anchor.page_index is not None:
        stored["page_index"] = anchor.page_index
    if servable:
        for field in ("quote", "prefix", "suffix"):
            value = getattr(anchor, field)
            if value is not None:
                stored[field] = normalize_node_text(value)
    return stored


def validate_entries(con: _Connection, owner_user_id: str, entries: Sequence[Any]) -> list[ValidEntry]:
    """Validate the list in order and report the lowest failing index. The
    cap is checked before any per-entry work; the list is never trimmed."""
    if len(entries) > MAX_INFORMS:
        raise InformsInvalid(MAX_INFORMS, "too_many_entries")
    candidates = sorted({d for d in (_entry_document_id(e) for e in entries) if d is not None})
    rights = _document_rights(con, candidates)
    seen: set[str] = set()
    valid: list[ValidEntry] = []
    for index, entry in enumerate(entries):
        document_id = _entry_document_id(entry)
        if document_id is None:
            raise InformsInvalid(index, "entry_invalid")
        if document_id in seen:
            raise InformsInvalid(index, "duplicate_document")
        anchor = _anchor(entry.get("anchor"), index)
        if anchor is not None and anchor.document_id != document_id:
            raise InformsInvalid(index, "anchor_other_document")
        right = rights.get(document_id)
        if right is None or not _readable(right[0], right[1], owner_user_id):
            raise InformsInvalid(index, "document_not_readable")
        seen.add(document_id)
        servable = is_servable_full_text(servability_of(right[0]))
        valid.append(ValidEntry(document_id, None if anchor is None else _stored_anchor(anchor, servable=servable)))
    return valid


# ── answers ─────────────────────────────────────────────────────────────────


def informs_answer(
    revision_id: str, block_id: str, entries: Sequence[tuple[int, str, dict[str, Any] | None]]
) -> dict[str, Any]:
    """``{revision_id, block_id, informs: [{ordinal, document_id, anchor?}]}``;
    ``anchor`` is left out when absent."""
    listed: list[dict[str, Any]] = []
    for ordinal, document_id, anchor in entries:
        item: dict[str, Any] = {"ordinal": ordinal, "document_id": document_id}
        if anchor is not None:
            item["anchor"] = anchor
        listed.append(item)
    return {"revision_id": revision_id, "block_id": block_id, "informs": listed}


def replace_block_informs(
    con: LockedConnection,
    *,
    head: Head,
    owner_user_id: str,
    block_id: str,
    entries: Sequence[ValidEntry],
    expected_revision_id: str,
    idempotency_key: str,
    request_sha256: str,
    checkpoint: Checkpoint | None = None,
) -> StoredOperation:
    """One ``revise`` whose patch replaces this block's rows; every other
    block's rows are carried forward. ``ordinal`` is the list position."""
    event_log_id = write_log_id(head.derived_asset_id)
    if event_log_id is None:
        raise NotFound()
    rows = [
        {
            "block_id": block_id,
            "ordinal": ordinal,
            "document_id": entry.document_id,
            "anchor": None if entry.anchor is None else canonical_json(entry.anchor),
        }
        for ordinal, entry in enumerate(entries)
    ]
    listed = [(ordinal, entry.document_id, entry.anchor) for ordinal, entry in enumerate(entries)]
    return revise(
        con,
        head=head,
        expected_revision_id=expected_revision_id,
        owner_user_id=owner_user_id,
        idempotency_key=idempotency_key,
        request_sha256=request_sha256,
        operation=OPERATION,
        patches={"derived_asset_block_informs": ChildPatch(match={"block_id": block_id}, rows=rows)},
        block_ids=[block_id],
        build_answer=lambda revision_id: informs_answer(revision_id, block_id, listed),
        event_log_id=event_log_id,
        checkpoint=checkpoint,
    )


def put_block_informs(
    con: LockedConnection,
    *,
    owner_user_id: str,
    asset_id: str,
    block_id: str,
    request: InformsRequest,
    checkpoint: Checkpoint | None = None,
) -> StoredOperation:
    """The PUT, inside the caller's transaction, in the signed check order:
    owner 404, replay or 409 ``idempotency_conflict``, block 404, 409
    ``revision_moved``, 422 ``informs_invalid``, then the revise."""
    if deliverable_of(asset_id) is None:
        raise NotFound()
    head = load_owned_head(con, asset_id, owner_user_id=owner_user_id)
    stored = find_operation(con, owner_user_id=owner_user_id, idempotency_key=request.idempotency_key)
    if stored is not None:
        if stored.operation == OPERATION and stored.request_sha256 == request.request_sha256:
            return stored
        raise IdempotencyConflict()
    if not block_in_revision(con, head, block_id):
        raise NotFound()
    check_expected(head, request.expected_revision_id)
    entries = validate_entries(con, owner_user_id, request.informs)
    return replace_block_informs(
        con,
        head=head,
        owner_user_id=owner_user_id,
        block_id=block_id,
        entries=entries,
        expected_revision_id=request.expected_revision_id,
        idempotency_key=request.idempotency_key,
        request_sha256=request.request_sha256,
        checkpoint=checkpoint,
    )


def read_block_informs(con: _Connection, asset_id: str, block_id: str, owner_user_id: str) -> dict[str, Any]:
    """One block's informs at the current revision. Read-only; 404 exactly as
    the PUT. The rows are keyed by the immutable revision the head names, so
    the two SELECTs cannot disagree."""
    if deliverable_of(asset_id) is None:
        raise NotFound()
    head = load_owned_head(con, asset_id, owner_user_id=owner_user_id)
    if not block_in_revision(con, head, block_id):
        raise NotFound()
    rows = con.execute(
        "SELECT ordinal, document_id, anchor FROM derived_asset_block_informs "
        "WHERE derived_asset_id = ? AND revision_id = ? AND block_id = ? ORDER BY ordinal",
        [asset_id, head.revision_id, block_id],
    ).fetchall()
    return informs_answer(
        head.revision_id,
        block_id,
        [(int(row[0]), str(row[1]), None if row[2] is None else json.loads(row[2])) for row in rows],
    )


__all__ = [
    "MAX_INFORMS",
    "OPERATION",
    "InformsAnchor",
    "InformsBodyInvalid",
    "InformsInvalid",
    "InformsRequest",
    "ValidEntry",
    "deliverable_of",
    "informs_answer",
    "parse_body",
    "put_block_informs",
    "read_block_informs",
    "replace_block_informs",
    "request_sha256",
    "validate_entries",
    "write_log_id",
]
