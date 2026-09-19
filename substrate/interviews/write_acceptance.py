"""Immutable owner review and reversible private Write revisions."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections import Counter
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
from typing import Any, Literal
from urllib.parse import urlsplit

from runtime.db_lock import connect_read, connect_write
from services.html_projection.gate import ScriptViolation, assert_script_free

from .authority import InterviewAccountAuthority
from .composition import get_private_draft
from .composition_proposals import get_proposal


class WriteAcceptanceConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class WriteReviewDecision:
    event_id: str
    action: str
    write_document_id: str
    project_id: str
    proposal_id: str
    revision: int | None
    prior_revision: int | None
    result_html_sha256: str
    replayed: bool = False


@dataclass(frozen=True)
class PrivateWriteDocument:
    write_document_id: str
    project_id: str
    title: str
    revision: int
    body_html: str
    body_sha256: str | None
    visibility: str
    origin_kind: str = "ai_composition"


@dataclass(frozen=True)
class PrivateWriteDocumentSummary:
    write_document_id: str
    project_id: str
    title: str
    revision: int
    body_sha256: str
    visibility: str
    updated_at: str
    origin_kind: str


@dataclass(frozen=True)
class NativeWriteCreateDecision:
    event_id: str
    write_document_id: str
    project_id: str
    title: str
    revision: int
    body_sha256: str
    replayed: bool = False


@dataclass(frozen=True)
class WriteEditDecision:
    event_id: str
    write_document_id: str
    project_id: str
    revision: int
    prior_revision: int
    body_sha256: str
    replayed: bool = False
    operation: str = "edit"


@dataclass(frozen=True)
class EvidenceInsertionSource:
    citation_receipt_sha256: str
    source_asset_id: str
    claim_id: str
    source_document_id: str
    chunk_ids: tuple[str, ...]
    source_title: str
    source_content_sha256: str
    excerpt_text: str


@dataclass(frozen=True)
class EvidenceInsertionPreview:
    write_document_id: str
    project_id: str
    base_revision: int
    base_body_sha256: str
    proposed_html: str
    proposed_html_sha256: str
    excerpt_sha256: str
    source_title: str
    citation_receipt_sha256: str
    preview_sha256: str


@dataclass(frozen=True)
class EvidenceBundleItem:
    source: EvidenceInsertionSource
    relationship: Literal["supports", "contradicts", "context", "unresolved"]
    operator_label: str | None = None


@dataclass(frozen=True)
class EvidenceBundlePreview:
    write_document_id: str
    project_id: str
    base_revision: int
    base_body_sha256: str
    proposed_html: str
    proposed_html_sha256: str
    manifest_sha256: str
    preview_sha256: str
    items: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class PrivateWriteRevision:
    revision: int
    operation: str
    event_id: str
    body_sha256: str
    prior_body_sha256: str | None
    root_acceptance_event_id: str | None
    proposal_id: str | None
    target_revision: int | None
    target_body_sha256: str | None
    created_at: str
    has_summary: bool
    body_html: str | None = None
    origin_kind: str = "ai_composition"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _event_sha(
    *, event_id: str, action: str, write_document_id: str, project_id: str,
    proposal_id: str, target_event_id: str | None, revision: int | None,
    prior_revision: int | None, prior_body_sha256: str | None,
    source_manifest_sha256: str, source_body_sha256: str, result_html_sha256: str,
) -> str:
    return _sha(_canonical({
        "schema_version": 1, "event_id": event_id, "action": action,
        "write_document_id": write_document_id, "project_id": project_id,
        "proposal_id": proposal_id, "target_event_id": target_event_id,
        "revision": revision, "prior_revision": prior_revision,
        "prior_body_sha256": prior_body_sha256,
        "source_manifest_sha256": source_manifest_sha256,
        "source_body_sha256": source_body_sha256,
        "result_html_sha256": result_html_sha256,
    }))


def _edit_event_sha(
    *, event_id: str, write_document_id: str, project_id: str,
    base_revision: int, revision: int, prior_body_sha256: str,
    body_sha256: str, root_acceptance_event_id: str, proposal_id: str,
    source_manifest_sha256: str, source_body_sha256: str,
    result_html_sha256: str, summary: str | None, operation: str = "edit",
    target_revision: int | None = None, target_body_sha256: str | None = None,
) -> str:
    value = {
        "schema_version": 1 if operation == "edit" else 2, "event_id": event_id,
        "write_document_id": write_document_id, "project_id": project_id,
        "base_revision": base_revision, "revision": revision,
        "prior_body_sha256": prior_body_sha256, "body_sha256": body_sha256,
        "root_acceptance_event_id": root_acceptance_event_id,
        "proposal_id": proposal_id,
        "source_manifest_sha256": source_manifest_sha256,
        "source_body_sha256": source_body_sha256,
        "result_html_sha256": result_html_sha256, "summary": summary,
    }
    if operation != "edit":
        value.update({
            "operation": operation, "target_revision": target_revision,
            "target_body_sha256": target_body_sha256,
        })
    return _sha(_canonical(value))


def _native_event_sha(
    *, event_id: str, write_document_id: str, project_id: str,
    mutation_key: str, request_sha256: str,
    operation: str, base_revision: int, revision: int,
    prior_body_sha256: str | None, body_sha256: str, title: str | None,
    summary: str | None, target_revision: int | None = None,
    target_body_sha256: str | None = None,
) -> str:
    return _sha(_canonical({
        "schema_version": 1, "event_id": event_id,
        "write_document_id": write_document_id, "project_id": project_id,
        "mutation_key": mutation_key, "request_sha256": request_sha256,
        "origin_kind": "owner_native", "operation": operation,
        "base_revision": base_revision, "revision": revision,
        "prior_body_sha256": prior_body_sha256, "body_sha256": body_sha256,
        "title": title, "summary": summary,
        "target_revision": target_revision,
        "target_body_sha256": target_body_sha256,
    }))


def _evidence_receipt_sha(value: dict[str, object]) -> str:
    return _sha(_canonical({"schema_version": 1, **value}))


def _validate_evidence_source(source: EvidenceInsertionSource) -> None:
    for value, label in (
        (source.citation_receipt_sha256, "citation receipt"),
        (source.source_content_sha256, "source content hash"),
    ):
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(f"evidence insertion {label} is invalid")
    for value, label, limit in (
        (source.source_asset_id, "source asset", 512),
        (source.claim_id, "claim", 512),
        (source.source_document_id, "source document", 512),
        (source.source_title, "source title", 500),
    ):
        if (not isinstance(value, str) or not value or value != value.strip()
                or len(value.encode()) > limit):
            raise ValueError(f"evidence insertion {label} is invalid")
    if (not source.chunk_ids or len(source.chunk_ids) > 64
            or len(set(source.chunk_ids)) != len(source.chunk_ids)):
        raise ValueError("evidence insertion chunks are invalid")
    for chunk_id in source.chunk_ids:
        if (not isinstance(chunk_id, str) or not chunk_id or chunk_id != chunk_id.strip()
                or len(chunk_id.encode()) > 512):
            raise ValueError("evidence insertion chunks are invalid")
    if (not isinstance(source.excerpt_text, str) or not source.excerpt_text.strip()
            or len(source.excerpt_text.encode()) > 512_000):
        raise ValueError("evidence insertion excerpt is invalid")


_FETCH_ELEMENT_RE = re.compile(
    r"<\s*(?:img|audio|video|source|iframe|embed|object|link|svg|use|form)\b",
    re.IGNORECASE,
)

_ALLOWED_TAGS = {
    "html", "head", "meta", "title", "style", "body", "header", "main", "footer",
    "section", "article", "aside", "nav", "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "div", "span", "strong", "em", "b", "i", "u", "s", "mark", "small",
    "sub", "sup", "blockquote", "q", "cite", "pre", "code", "kbd", "samp", "var",
    "ul", "ol", "li", "dl", "dt", "dd", "table", "caption", "thead", "tbody",
    "tfoot", "tr", "th", "td", "a", "br", "hr", "time", "details", "summary",
}
_VOID_TAGS = {"meta", "br", "hr"}
_GLOBAL_ATTRS = {"class", "id", "lang", "dir", "title", "role"}
_TAG_ATTRS = {
    "meta": {"charset", "name", "content"},
    "a": {"href", "rel", "target"},
    "ol": {"start", "reversed", "type"},
    "li": {"value"},
    "th": {"scope", "colspan", "rowspan"},
    "td": {"colspan", "rowspan"},
    "time": {"datetime"},
    "details": {"open"},
}


class _InertHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []

    def handle_decl(self, decl: str) -> None:
        if decl.strip().lower() != "doctype html":
            raise ValueError("private Write HTML declaration is invalid")

    def unknown_decl(self, data: str) -> None:
        raise ValueError("private Write HTML declaration is invalid")

    def handle_pi(self, data: str) -> None:
        raise ValueError("private Write HTML processing instruction is invalid")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _ALLOWED_TAGS:
            raise ValueError("private Write HTML tag is not allowed")
        names = [name for name, _value in attrs]
        if len(names) != len(set(names)):
            raise ValueError("private Write HTML has duplicate attributes")
        for name, value in attrs:
            if (
                name not in _GLOBAL_ATTRS
                and not name.startswith("data-")
                and not name.startswith("aria-")
                and name not in _TAG_ATTRS.get(tag, set())
            ):
                raise ValueError("private Write HTML attribute is not allowed")
            if name.startswith("on") or name == "style":
                raise ValueError("private Write HTML active attribute is not allowed")
            if tag == "a" and name == "href" and value is not None:
                scheme = urlsplit(value.strip()).scheme.lower()
                if scheme not in {"", "http", "https", "mailto"}:
                    raise ValueError("private Write HTML link scheme is not allowed")
            if tag == "a" and name == "target" and value not in {None, "_self", "_blank"}:
                raise ValueError("private Write HTML link target is not allowed")
        attr_map = dict(attrs)
        if tag == "a" and attr_map.get("target") == "_blank":
            rel = set((attr_map.get("rel") or "").lower().split())
            if not {"noopener", "noreferrer"}.issubset(rel):
                raise ValueError("private Write HTML external tab isolation is missing")
        if tag not in _VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_TAGS or not self.stack or self.stack[-1] != tag:
            raise ValueError("private Write HTML nesting is invalid")
        self.stack.pop()

    def close(self) -> None:
        super().close()
        if self.stack:
            raise ValueError("private Write HTML nesting is invalid")


def _bounded_edit_html(value: str) -> tuple[str, str]:
    if not isinstance(value, str) or any(
        ord(char) < 32 and char not in "\t\n\r" for char in value
    ):
        raise ValueError("private Write HTML is invalid")
    if len(value.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("private Write HTML exceeds 2 MiB")
    return value, _sha(value)


def _validated_edit_html(value: str, *, base_html: str) -> tuple[str, str]:
    value, value_sha = _bounded_edit_html(value)
    try:
        assert_script_free(value)
    except ScriptViolation as exc:
        raise ValueError("private Write HTML is not inert") from exc
    # The shared zero-script gate permits some same-origin/data fetch forms.
    # Private authored prose has no fetch authority, so reject fetch-capable
    # elements wholesale until an admitted asset-reference contract exists.
    if _FETCH_ELEMENT_RE.search(value):
        raise ValueError("private Write HTML contains a fetch-capable element")
    style_pattern = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.IGNORECASE | re.DOTALL)
    submitted_styles = Counter(style_pattern.findall(value))
    admitted_styles = Counter(style_pattern.findall(base_html))
    if submitted_styles - admitted_styles:
        raise ValueError("private Write HTML contains an unadmitted stylesheet")
    parser = _InertHtmlParser()
    try:
        parser.feed(value)
        parser.close()
    except (ValueError, AssertionError) as exc:
        raise ValueError("private Write HTML structure is invalid") from exc
    return value, value_sha


def _document_id(authority: InterviewAccountAuthority, project_id: str) -> str:
    return "ivwd-" + _sha(f"antiek-private-write-v1\0{authority.account_digest}\0{project_id}")[:32]


def _bounded(value: str, label: str, limit: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > limit:
        raise ValueError(f"write review {label} is invalid")
    return value


def _ready_result(
    con: Any, authority: InterviewAccountAuthority, proposal_id: str
) -> tuple[Any, Any, str, str]:
    proposal = get_proposal(con, authority, proposal_id=proposal_id)
    draft = get_private_draft(con, authority, draft_id=proposal.draft_id)
    row = con.execute(
        "SELECT state, result_html, result_html_sha256, raw_result_json, raw_result_sha256 "
        "FROM interview_composition_execution_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND proposal_id = ?",
        [authority.account_digest, authority.account_id, proposal_id],
    ).fetchone()
    if row is None or str(row[0]) != "ready_for_review":
        raise WriteAcceptanceConflict("composition result is not ready for review")
    result_html, result_sha = str(row[1]), str(row[2])
    if _sha(result_html) != result_sha or _sha(str(row[3])) != str(row[4]):
        raise WriteAcceptanceConflict("composition result receipt integrity failed")
    return proposal, draft, result_html, result_sha


def _decision_from_row(row: tuple[Any, ...], *, replayed: bool) -> WriteReviewDecision:
    return WriteReviewDecision(
        event_id=str(row[0]), action=str(row[1]), write_document_id=str(row[2]),
        project_id=str(row[3]), proposal_id=str(row[4]),
        revision=None if row[5] is None else int(row[5]),
        prior_revision=None if row[6] is None else int(row[6]),
        result_html_sha256=str(row[7]), replayed=replayed,
    )


def _decision_row(con: Any, authority: InterviewAccountAuthority, mutation_key: str):
    return con.execute(
        "SELECT event_id, action, write_document_id, project_id, proposal_id, revision, "
        "prior_revision, result_html_sha256, request_sha256 "
        "FROM interview_write_review_events_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND mutation_key = ?",
        [authority.account_digest, authority.account_id, mutation_key],
    ).fetchone()


def review_result(
    db_path: str,
    authority: InterviewAccountAuthority,
    *,
    proposal_id: str,
    mutation_key: str,
    action: Literal["accept", "reject"],
    base_revision: int,
    rationale: str | None = None,
) -> WriteReviewDecision:
    proposal_id = _bounded(proposal_id, "proposal id", 512)
    mutation_key = _bounded(mutation_key, "mutation key", 512)
    if action not in {"accept", "reject"}:
        raise ValueError("write review action is invalid")
    if type(base_revision) is not int or base_revision < 0:
        raise ValueError("write review base revision is invalid")
    if rationale is not None and (rationale != rationale.strip() or len(rationale) > 5_000):
        raise ValueError("write review rationale is invalid")
    with connect_write(db_path, purpose="interview/write_review", log_on_close=False) as con:
        proposal, draft, result_html, result_sha = _ready_result(con, authority, proposal_id)
        request_sha = _sha(_canonical({
            "schema_version": 1, "proposal_id": proposal_id, "action": action,
            "base_revision": base_revision, "rationale": rationale,
        }))
        replay = _decision_row(con, authority, mutation_key)
        if replay is not None:
            if str(replay[8]) != request_sha:
                raise WriteAcceptanceConflict("write review key was reused with different input")
            return _decision_from_row(tuple(replay[:8]), replayed=True)
        write_document_id = _document_id(authority, proposal.project_id)
        current = con.execute(
            "SELECT current_revision, current_body_sha256 FROM "
            "interview_write_documents_authority WHERE account_digest = ? "
            "AND owner_user_id = ? AND write_document_id = ?",
            [authority.account_digest, authority.account_id, write_document_id],
        ).fetchone()
        current_revision = 0 if current is None else int(current[0])
        current_sha = None if current is None else current[1]
        if current_revision != base_revision:
            raise WriteAcceptanceConflict("stale private Write revision")
        if action == "accept" and con.execute(
            "SELECT 1 FROM interview_write_review_events_authority WHERE account_digest = ? "
            "AND proposal_id = ? AND action = 'accept'",
            [authority.account_digest, proposal_id],
        ).fetchone() is not None:
            raise WriteAcceptanceConflict("composition result was already accepted")
        event_id = "ivwe-" + _sha(authority.account_digest + "\0" + mutation_key + "\0" + request_sha)[:32]
        revision = current_revision + 1 if action == "accept" else None
        event_sha = _event_sha(
            event_id=event_id, action=action, write_document_id=write_document_id,
            project_id=proposal.project_id, proposal_id=proposal_id,
            target_event_id=None, revision=revision,
            prior_revision=current_revision if action == "accept" else None,
            prior_body_sha256=current_sha, source_manifest_sha256=proposal.source_manifest_sha256,
            source_body_sha256=proposal.source_body_sha256, result_html_sha256=result_sha,
        )
        con.execute("BEGIN TRANSACTION")
        try:
            if action == "accept":
                if current is None:
                    con.execute(
                        "INSERT INTO interview_write_documents_authority "
                        "(account_digest, write_document_id, project_id, owner_user_id, title) "
                        "VALUES (?, ?, ?, ?, ?)",
                        [authority.account_digest, write_document_id, proposal.project_id,
                         authority.account_id, draft.title],
                    )
                con.execute(
                    "INSERT INTO interview_write_revisions_authority "
                    "(account_digest, write_document_id, revision, owner_user_id, event_id, "
                    "review_event_sha256, action, proposal_id, source_manifest_sha256, "
                    "source_body_sha256, result_html_sha256, body_html, body_sha256, "
                    "prior_revision, prior_body_sha256) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'accept', ?, ?, ?, ?, ?, ?, ?, ?)",
                    [authority.account_digest, write_document_id, revision, authority.account_id,
                     event_id, event_sha, proposal_id, proposal.source_manifest_sha256,
                     proposal.source_body_sha256, result_sha, result_html, result_sha,
                     current_revision, current_sha],
                )
                advanced = con.execute(
                    "UPDATE interview_write_documents_authority SET current_revision = ?, "
                    "current_body_sha256 = ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE account_digest = ? AND write_document_id = ? AND current_revision = ? "
                    "AND current_body_sha256 IS NOT DISTINCT FROM ? RETURNING 1",
                    [revision, result_sha, authority.account_digest, write_document_id,
                     current_revision, current_sha],
                ).fetchone()
                if advanced is None:
                    raise WriteAcceptanceConflict("stale private Write revision")
            con.execute(
                "INSERT INTO interview_write_review_events_authority "
                "(account_digest, event_id, write_document_id, project_id, owner_user_id, "
                "mutation_key, request_sha256, action, proposal_id, acceptance_key, rationale, revision, "
                "prior_revision, prior_body_sha256, source_manifest_sha256, "
                "source_body_sha256, result_html_sha256, event_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [authority.account_digest, event_id, write_document_id, proposal.project_id,
                 authority.account_id, mutation_key, request_sha, action, proposal_id,
                 proposal_id if action == "accept" else None, rationale, revision,
                 current_revision if action == "accept" else None,
                 current_sha, proposal.source_manifest_sha256, proposal.source_body_sha256,
                 result_sha, event_sha],
            )
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        row = _decision_row(con, authority, mutation_key)
        return _decision_from_row(tuple(row[:8]), replayed=False)


def undo_acceptance(
    db_path: str,
    authority: InterviewAccountAuthority,
    *,
    target_event_id: str,
    mutation_key: str,
    base_revision: int,
) -> WriteReviewDecision:
    target_event_id = _bounded(target_event_id, "target event", 512)
    mutation_key = _bounded(mutation_key, "mutation key", 512)
    if type(base_revision) is not int or base_revision < 1:
        raise ValueError("write undo base revision is invalid")
    with connect_write(db_path, purpose="interview/write_undo", log_on_close=False) as con:
        target = con.execute(
            "SELECT write_document_id, project_id, proposal_id, revision, prior_revision, "
            "prior_body_sha256, source_manifest_sha256, source_body_sha256, result_html_sha256, "
            "event_sha256 "
            "FROM interview_write_review_events_authority WHERE account_digest = ? "
            "AND owner_user_id = ? AND event_id = ? AND action = 'accept'",
            [authority.account_digest, authority.account_id, target_event_id],
        ).fetchone()
        if target is None:
            raise ValueError("accepted Write review event not found")
        if str(target[9]) != _event_sha(
            event_id=target_event_id, action="accept", write_document_id=str(target[0]),
            project_id=str(target[1]), proposal_id=str(target[2]), target_event_id=None,
            revision=int(target[3]), prior_revision=int(target[4]),
            prior_body_sha256=None if target[5] is None else str(target[5]),
            source_manifest_sha256=str(target[6]), source_body_sha256=str(target[7]),
            result_html_sha256=str(target[8]),
        ):
            raise WriteAcceptanceConflict("accepted Write review receipt is corrupt")
        proposal, _draft, _result, result_sha = _ready_result(con, authority, str(target[2]))
        request_sha = _sha(_canonical({
            "schema_version": 1, "target_event_id": target_event_id,
            "base_revision": base_revision,
        }))
        replay = _decision_row(con, authority, mutation_key)
        if replay is not None:
            if str(replay[8]) != request_sha:
                raise WriteAcceptanceConflict("write review key was reused with different input")
            return _decision_from_row(tuple(replay[:8]), replayed=True)
        doc = con.execute(
            "SELECT current_revision, current_body_sha256 FROM "
            "interview_write_documents_authority WHERE account_digest = ? "
            "AND owner_user_id = ? AND write_document_id = ?",
            [authority.account_digest, authority.account_id, str(target[0])],
        ).fetchone()
        if doc is None or int(doc[0]) != base_revision or int(target[3]) != base_revision:
            raise WriteAcceptanceConflict("accepted revision is not the current Write revision")
        previous_revision = int(target[4])
        if previous_revision == 0:
            previous_body, previous_sha = "", _sha("")
        else:
            previous = con.execute(
                "SELECT body_html, body_sha256 FROM interview_write_revisions_authority "
                "WHERE account_digest = ? AND write_document_id = ? AND revision = ?",
                [authority.account_digest, str(target[0]), previous_revision],
            ).fetchone()
            if previous is None or _sha(str(previous[0])) != str(previous[1]):
                raise WriteAcceptanceConflict("prior Write revision integrity failed")
            previous_body, previous_sha = str(previous[0]), str(previous[1])
        revision = base_revision + 1
        event_id = "ivwe-" + _sha(authority.account_digest + "\0" + mutation_key + "\0" + request_sha)[:32]
        event_sha = _event_sha(
            event_id=event_id, action="undo", write_document_id=str(target[0]),
            project_id=str(target[1]), proposal_id=str(target[2]),
            target_event_id=target_event_id, revision=revision,
            prior_revision=base_revision, prior_body_sha256=str(doc[1]),
            source_manifest_sha256=str(target[6]), source_body_sha256=str(target[7]),
            result_html_sha256=result_sha,
        )
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute(
                "INSERT INTO interview_write_revisions_authority "
                "(account_digest, write_document_id, revision, owner_user_id, event_id, "
                "review_event_sha256, action, proposal_id, source_manifest_sha256, "
                "source_body_sha256, result_html_sha256, body_html, body_sha256, "
                "prior_revision, prior_body_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, 'undo', ?, ?, ?, ?, ?, ?, ?, ?)",
                [authority.account_digest, str(target[0]), revision, authority.account_id,
                 event_id, event_sha, str(target[2]), str(target[6]), str(target[7]),
                 result_sha, previous_body, previous_sha, base_revision, str(doc[1])],
            )
            advanced = con.execute(
                "UPDATE interview_write_documents_authority SET current_revision = ?, "
                "current_body_sha256 = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE account_digest = ? AND write_document_id = ? AND current_revision = ? "
                "AND current_body_sha256 = ? RETURNING 1",
                [revision, previous_sha, authority.account_digest, str(target[0]),
                 base_revision, str(doc[1])],
            ).fetchone()
            if advanced is None:
                raise WriteAcceptanceConflict("stale private Write revision")
            con.execute(
                "INSERT INTO interview_write_review_events_authority "
                "(account_digest, event_id, write_document_id, project_id, owner_user_id, "
                "mutation_key, request_sha256, action, proposal_id, acceptance_key, "
                "target_event_id, revision, "
                "prior_revision, prior_body_sha256, source_manifest_sha256, "
                "source_body_sha256, result_html_sha256, event_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'undo', ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
                [authority.account_digest, event_id, str(target[0]), str(target[1]),
                 authority.account_id, mutation_key, request_sha, str(target[2]),
                 target_event_id, revision, base_revision, str(doc[1]), str(target[6]),
                 str(target[7]), result_sha, event_sha],
            )
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        row = _decision_row(con, authority, mutation_key)
        return _decision_from_row(tuple(row[:8]), replayed=False)


def _read_native_document(
    con: Any, authority: InterviewAccountAuthority, write_document_id: str,
    doc: tuple[Any, ...],
) -> PrivateWriteDocument:
    if con.execute(
        "SELECT (SELECT count(*) FROM interview_write_revisions_authority WHERE "
        "account_digest = ? AND owner_user_id = ? AND write_document_id = ?) + "
        "(SELECT count(*) FROM interview_write_edit_revisions_authority WHERE "
        "account_digest = ? AND owner_user_id = ? AND write_document_id = ?) + "
        "(SELECT count(*) FROM interview_write_review_events_authority WHERE "
        "account_digest = ? AND owner_user_id = ? AND write_document_id = ?) + "
        "(SELECT count(*) FROM interview_write_edit_events_authority WHERE "
        "account_digest = ? AND owner_user_id = ? AND write_document_id = ?)",
        [authority.account_digest, authority.account_id, write_document_id,
         authority.account_digest, authority.account_id, write_document_id,
         authority.account_digest, authority.account_id, write_document_id,
         authority.account_digest, authority.account_id, write_document_id],
    ).fetchone()[0]:
        raise WriteAcceptanceConflict("private Write origin ledgers are mixed")
    rows = con.execute(
        "SELECT revision, event_id, event_sha256, operation, target_revision, "
        "target_body_sha256, body_html, body_sha256, prior_revision, "
        "prior_body_sha256, created_at FROM interview_write_native_revisions_authority "
        "WHERE account_digest = ? AND owner_user_id = ? AND write_document_id = ? "
        "ORDER BY revision",
        [authority.account_digest, authority.account_id, write_document_id],
    ).fetchall()
    prior_revision, prior_sha, prior_html = 0, None, None
    event_count = con.execute(
        "SELECT count(*) FROM interview_write_native_events_authority WHERE "
        "account_digest = ? AND owner_user_id = ? AND write_document_id = ?",
        [authority.account_digest, authority.account_id, write_document_id],
    ).fetchone()[0]
    if event_count != len(rows):
        raise WriteAcceptanceConflict("private Write native ledger is incomplete")
    insertion_rows = con.execute(
        "SELECT insertion_id, native_event_id, native_event_sha256, revision, "
        "citation_receipt_sha256, source_asset_id, claim_id, source_document_id, "
        "chunk_ids_json, source_title, source_content_sha256, excerpt_sha256, "
        "preview_sha256, receipt_sha256, operation FROM "
        "interview_write_evidence_insertions_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND write_document_id = ? ORDER BY revision",
        [authority.account_digest, authority.account_id, write_document_id],
    ).fetchall()
    insertions = {str(item[1]): item for item in insertion_rows}
    if len(insertions) != len(insertion_rows):
        raise WriteAcceptanceConflict("private Write evidence ledger is corrupt")
    bundle_rows = con.execute(
        "SELECT bundle_id, native_event_id, native_event_sha256, operation, revision, "
        "item_count, manifest_sha256, preview_sha256, receipt_sha256 FROM "
        "interview_write_evidence_bundles_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND write_document_id = ? ORDER BY revision",
        [authority.account_digest, authority.account_id, write_document_id],
    ).fetchall()
    bundles = {str(item[1]): item for item in bundle_rows}
    if len(bundles) != len(bundle_rows):
        raise WriteAcceptanceConflict("private Write evidence bundle ledger is corrupt")
    synthesis_rows = con.execute(
        "SELECT acceptance_id, native_event_id, native_event_sha256, proposal_id, "
        "bundle_id, execution_run_id, base_revision, base_html_sha256, revision, "
        "html_sha256, source_manifest_sha256, source_content_sha256, "
        "source_receipt_sha256, prompt_sha256, route_sha256, result_html_sha256, "
        "preview_sha256, receipt_sha256, operation FROM "
        "interview_write_synthesis_acceptances_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND write_document_id = ? ORDER BY revision",
        [authority.account_digest, authority.account_id, write_document_id],
    ).fetchall()
    syntheses = {str(item[1]): item for item in synthesis_rows}
    if len(syntheses) != len(synthesis_rows):
        raise WriteAcceptanceConflict("private Write synthesis acceptance ledger is corrupt")
    body_hashes: dict[int, str] = {}
    for row in rows:
        event = con.execute(
            "SELECT project_id, mutation_key, request_sha256, operation, base_revision, "
            "revision, prior_body_sha256, body_sha256, title, summary, target_revision, "
            "target_body_sha256, event_sha256 "
            "FROM interview_write_native_events_authority WHERE account_digest = ? "
            "AND owner_user_id = ? AND write_document_id = ? AND event_id = ?",
            [authority.account_digest, authority.account_id, write_document_id, str(row[1])],
        ).fetchone()
        if event is None:
            raise WriteAcceptanceConflict("private Write native event is missing")
        expected = _native_event_sha(
            event_id=str(row[1]), write_document_id=write_document_id,
            project_id=str(event[0]), mutation_key=str(event[1]),
            request_sha256=str(event[2]), operation=str(event[3]),
            base_revision=int(event[4]), revision=int(event[5]),
            prior_body_sha256=None if event[6] is None else str(event[6]),
            body_sha256=str(event[7]), title=None if event[8] is None else str(event[8]),
            summary=None if event[9] is None else str(event[9]),
            target_revision=None if event[10] is None else int(event[10]),
            target_body_sha256=None if event[11] is None else str(event[11]),
        )
        if not (
            int(row[0]) == prior_revision + 1 == int(event[5])
            and int(row[8]) == prior_revision == int(event[4])
            and (None if row[9] is None else str(row[9])) == prior_sha
            and (None if event[6] is None else str(event[6])) == prior_sha
            and _sha(str(row[6])) == str(row[7]) == str(event[7])
            and str(row[2]) == str(event[12]) == expected
            and str(row[3]) == str(event[3])
            and (None if row[4] is None else int(row[4])) == (
                None if event[10] is None else int(event[10]))
            and (None if row[5] is None else str(row[5])) == (
                None if event[11] is None else str(event[11]))
            and str(event[0]) == str(doc[0])
            and ((prior_revision == 0 and str(event[8]) == str(doc[1]))
                 or (prior_revision > 0 and event[8] is None))
        ):
            raise WriteAcceptanceConflict("private Write native receipt is corrupt")
        operation = str(event[3])
        insertion = insertions.pop(str(row[1]), None)
        bundle = bundles.pop(str(row[1]), None)
        synthesis = syntheses.pop(str(row[1]), None)
        bundle_marker = str(event[9]).startswith("antiek:evidence_bundle:") if event[9] is not None else False
        synthesis_marker = str(event[9]).startswith("antiek:synthesis_accept:") if event[9] is not None else False
        if bundle_marker != (bundle is not None):
            raise WriteAcceptanceConflict("private Write evidence bundle ledger is incomplete")
        if synthesis_marker != (synthesis is not None):
            raise WriteAcceptanceConflict("private Write synthesis acceptance ledger is incomplete")
        if sum(item is not None for item in (insertion, bundle, synthesis)) > 1:
            raise WriteAcceptanceConflict("private Write companion ledgers are mixed")
        if insertion is not None:
            try:
                chunk_ids = json.loads(str(insertion[8]))
            except json.JSONDecodeError as exc:
                raise WriteAcceptanceConflict(
                    "private Write evidence receipt is corrupt"
                ) from exc
            receipt_value: dict[str, object] = {
                "insertion_id": str(insertion[0]),
                "write_document_id": write_document_id,
                "project_id": str(event[0]), "native_event_id": str(row[1]),
                "native_event_sha256": str(row[2]), "revision": int(row[0]),
                "operation": "evidence_insert",
                "citation_receipt_sha256": str(insertion[4]),
                "source_asset_id": str(insertion[5]), "claim_id": str(insertion[6]),
                "source_document_id": str(insertion[7]), "chunk_ids": chunk_ids,
                "source_title": str(insertion[9]),
                "source_content_sha256": str(insertion[10]),
                "excerpt_sha256": str(insertion[11]),
                "preview_sha256": str(insertion[12]),
            }
            if (operation != "edit" or str(insertion[14]) != "evidence_insert"
                    or int(insertion[3]) != int(row[0])
                    or str(insertion[2]) != str(row[2])
                    or not isinstance(chunk_ids, list) or not chunk_ids
                    or _evidence_receipt_sha(receipt_value) != str(insertion[13])):
                raise WriteAcceptanceConflict("private Write evidence receipt is corrupt")
        if bundle is not None:
            units = con.execute(
                "SELECT ordinal, relationship, operator_label, citation_receipt_sha256, "
                "source_asset_id, claim_id, source_document_id, chunk_ids_json, "
                "source_title, source_content_sha256, excerpt_sha256, unit_receipt_sha256 "
                "FROM interview_write_evidence_bundle_units_authority WHERE "
                "account_digest = ? AND owner_user_id = ? AND bundle_id = ? "
                "ORDER BY ordinal",
                [authority.account_digest, authority.account_id, str(bundle[0])],
            ).fetchall()
            manifest: list[dict[str, object]] = []
            for expected_ordinal, unit in enumerate(units):
                try:
                    chunk_ids = json.loads(str(unit[7]))
                except json.JSONDecodeError as exc:
                    raise WriteAcceptanceConflict(
                        "private Write evidence bundle unit is corrupt"
                    ) from exc
                value: dict[str, object] = {
                    "bundle_id": str(bundle[0]), "ordinal": int(unit[0]),
                    "relationship": str(unit[1]),
                    "operator_label": None if unit[2] is None else str(unit[2]),
                    "citation_receipt_sha256": str(unit[3]),
                    "source_asset_id": str(unit[4]), "claim_id": str(unit[5]),
                    "source_document_id": str(unit[6]), "chunk_ids": chunk_ids,
                    "source_title": str(unit[8]),
                    "source_content_sha256": str(unit[9]),
                    "excerpt_sha256": str(unit[10]),
                }
                if (int(unit[0]) != expected_ordinal
                        or _evidence_receipt_sha(value) != str(unit[11])):
                    raise WriteAcceptanceConflict(
                        "private Write evidence bundle unit is corrupt"
                    )
                manifest.append({key: item for key, item in value.items() if key != "bundle_id"})
            bundle_value: dict[str, object] = {
                "bundle_id": str(bundle[0]), "write_document_id": write_document_id,
                "project_id": str(event[0]), "native_event_id": str(row[1]),
                "native_event_sha256": str(row[2]), "operation": "evidence_bundle",
                "revision": int(row[0]), "item_count": len(units),
                "manifest_sha256": str(bundle[6]), "preview_sha256": str(bundle[7]),
            }
            if (operation != "edit" or str(bundle[3]) != "evidence_bundle"
                    or str(event[9]) != "antiek:evidence_bundle:" + str(bundle[6])
                    or int(bundle[4]) != int(row[0]) or int(bundle[5]) != len(units)
                    or str(bundle[2]) != str(row[2]) or not 2 <= len(units) <= 32
                    or _sha(_canonical(manifest)) != str(bundle[6])
                    or _evidence_receipt_sha(bundle_value) != str(bundle[8])):
                raise WriteAcceptanceConflict("private Write evidence bundle is corrupt")
        if synthesis is not None:
            receipt_value: dict[str, object] = {
                "acceptance_id": str(synthesis[0]), "proposal_id": str(synthesis[3]),
                "bundle_id": str(synthesis[4]), "execution_run_id": str(synthesis[5]),
                "source_manifest_sha256": str(synthesis[10]),
                "source_content_sha256": str(synthesis[11]),
                "source_receipt_sha256": str(synthesis[12]),
                "prompt_sha256": str(synthesis[13]), "route_sha256": str(synthesis[14]),
                "result_html_sha256": str(synthesis[15]),
                "preview_sha256": str(synthesis[16]),
                "write_document_id": write_document_id, "project_id": str(event[0]),
                "native_event_id": str(row[1]), "native_event_sha256": str(row[2]),
                "operation": "synthesis_accept", "base_revision": int(synthesis[6]),
                "base_html_sha256": str(synthesis[7]), "revision": int(synthesis[8]),
                "html_sha256": str(synthesis[9]),
            }
            if (operation != "edit" or str(synthesis[18]) != "synthesis_accept"
                    or str(event[9]) != "antiek:synthesis_accept:" + str(synthesis[3])
                    or str(synthesis[2]) != str(row[2])
                    or int(synthesis[6]) != int(row[8])
                    or str(synthesis[7]) != str(row[9])
                    or int(synthesis[8]) != int(row[0])
                    or str(synthesis[9]) != str(row[7])
                    or _evidence_receipt_sha(receipt_value) != str(synthesis[17])):
                raise WriteAcceptanceConflict("private Write synthesis acceptance is corrupt")
            from .composition_execution import _prompt, _render, _validated_result
            from .evidence_bundle_synthesis import get_evidence_bundle_synthesis_proposal
            from .evidence_synthesis_acceptance import _synthesis_section

            proposal = get_evidence_bundle_synthesis_proposal(
                con, authority, proposal_id=str(synthesis[3]),
            )
            execution = con.execute(
                "SELECT run_id, state, prompt_sha256, route_sha256, raw_result_json, "
                "raw_result_sha256, result_html, result_html_sha256, provider, model, "
                "dispatch_event_id, receipt_prompt_sha256 FROM "
                "interview_composition_execution_authority WHERE account_digest = ? "
                "AND owner_user_id = ? AND proposal_id = ?",
                [authority.account_digest, authority.account_id, proposal.proposal_id],
            ).fetchone()
            try:
                expected_prompt = _sha(_prompt(proposal, proposal.inputs))
                regenerated = _render(
                    _validated_result(str(execution[4]), proposal, proposal.inputs),
                    proposal, proposal.inputs,
                )
            except (IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise WriteAcceptanceConflict(
                    "private Write synthesis source receipt is corrupt"
                ) from exc
            execution_value = {
                "run_id": str(execution[0]), "prompt_sha256": str(execution[2]),
                "route_sha256": str(execution[3]), "result_html": str(execution[6]),
                "result_html_sha256": str(execution[7]),
            }
            if (proposal.bundle_id != str(synthesis[4])
                    or proposal.write_document_id != write_document_id
                    or proposal.project_id != str(event[0])
                    or proposal.source_manifest_sha256 != str(synthesis[10])
                    or proposal.source_content_sha256 != str(synthesis[11])
                    or proposal.source_receipt_sha256 != str(synthesis[12])
                    or execution is None or str(execution[1]) != "ready_for_review"
                    or str(execution[0]) != str(synthesis[5])
                    or expected_prompt != str(execution[2])
                    or expected_prompt != str(execution[11])
                    or str(execution[3]) != str(synthesis[14])
                    or str(execution[8]) != proposal.provider_id
                    or str(execution[9]) != proposal.model_id
                    or not isinstance(execution[10], str) or not str(execution[10]).strip()
                    or _sha(str(execution[4])) != str(execution[5])
                    or regenerated != str(execution[6])
                    or _sha(regenerated) != str(execution[7])
                    or str(execution[7]) != str(synthesis[15])
                    or expected_prompt != str(synthesis[13])
                    or prior_html is None):
                raise WriteAcceptanceConflict(
                    "private Write synthesis source receipt is corrupt"
                )
            closing = re.search(r"</article>\s*$", prior_html, re.IGNORECASE)
            expected_body = (
                "" if closing is None else
                prior_html[:closing.start()] + _synthesis_section(proposal, execution_value)
                + prior_html[closing.start():]
            )
            if expected_body != str(row[6]):
                raise WriteAcceptanceConflict(
                    "private Write synthesis body receipt is corrupt"
                )
        target_revision = None if event[10] is None else int(event[10])
        target_sha = None if event[11] is None else str(event[11])
        if operation == "restore" and (
            target_revision not in body_hashes or target_sha != body_hashes[target_revision]
            or str(row[7]) != target_sha
        ):
            raise WriteAcceptanceConflict("private Write native restore target is corrupt")
        prior_revision, prior_sha = int(row[0]), str(row[7])
        prior_html = str(row[6])
        body_hashes[prior_revision] = prior_sha
    if insertions or bundles or syntheses:
        raise WriteAcceptanceConflict("private Write evidence ledger is orphaned")
    if not rows or prior_revision != int(doc[2]) or prior_sha != str(doc[3]):
        raise WriteAcceptanceConflict("private Write current pointer is corrupt")
    return PrivateWriteDocument(
        write_document_id=write_document_id, project_id=str(doc[0]), title=str(doc[1]),
        revision=int(doc[2]), body_html=str(rows[-1][6]), body_sha256=str(doc[3]),
        visibility=str(doc[4]), origin_kind="owner_native",
    )


def _read_document(
    con: Any, authority: InterviewAccountAuthority, write_document_id: str
) -> PrivateWriteDocument:
        doc = con.execute(
            "SELECT project_id, title, current_revision, current_body_sha256, visibility, "
            "origin_kind "
            "FROM interview_write_documents_authority WHERE account_digest = ? "
            "AND owner_user_id = ? AND write_document_id = ?",
            [authority.account_digest, authority.account_id, write_document_id],
        ).fetchone()
        if doc is None:
            raise ValueError("private Write document not found")
        if str(doc[5]) == "owner_native":
            return _read_native_document(con, authority, write_document_id, tuple(doc))
        if str(doc[5]) != "ai_composition":
            raise WriteAcceptanceConflict("private Write origin is corrupt")
        if con.execute(
            "SELECT (SELECT count(*) FROM interview_write_native_revisions_authority WHERE "
            "account_digest = ? AND owner_user_id = ? AND write_document_id = ?) + "
            "(SELECT count(*) FROM interview_write_native_events_authority WHERE "
            "account_digest = ? AND owner_user_id = ? AND write_document_id = ?) + "
            "(SELECT count(*) FROM interview_write_evidence_insertions_authority WHERE "
            "account_digest = ? AND owner_user_id = ? AND write_document_id = ?) + "
            "(SELECT count(*) FROM interview_write_evidence_bundles_authority WHERE "
            "account_digest = ? AND owner_user_id = ? AND write_document_id = ?) + "
            "(SELECT count(*) FROM interview_write_synthesis_acceptances_authority WHERE "
            "account_digest = ? AND owner_user_id = ? AND write_document_id = ?)",
            [authority.account_digest, authority.account_id, write_document_id,
             authority.account_digest, authority.account_id, write_document_id,
             authority.account_digest, authority.account_id, write_document_id,
             authority.account_digest, authority.account_id, write_document_id,
             authority.account_digest, authority.account_id, write_document_id],
        ).fetchone()[0]:
            raise WriteAcceptanceConflict("private Write origin ledgers are mixed")
        review_rows = con.execute(
            "SELECT revision, body_html, body_sha256, prior_revision, prior_body_sha256, "
            "event_id, action, review_event_sha256, proposal_id, source_manifest_sha256, "
            "source_body_sha256, result_html_sha256 "
            "FROM interview_write_revisions_authority WHERE account_digest = ? "
            "AND owner_user_id = ? AND write_document_id = ? ORDER BY revision",
            [authority.account_digest, authority.account_id, write_document_id],
        ).fetchall()
        edit_rows = con.execute(
            "SELECT revision, body_html, body_sha256, prior_revision, prior_body_sha256, "
            "event_id, edit_event_sha256, root_acceptance_event_id, proposal_id, "
            "source_manifest_sha256, source_body_sha256, result_html_sha256 "
            "FROM interview_write_edit_revisions_authority WHERE account_digest = ? "
            "AND owner_user_id = ? AND write_document_id = ? ORDER BY revision",
            [authority.account_digest, authority.account_id, write_document_id],
        ).fetchall()
        rows = [("review", row) for row in review_rows] + [
            ("edit", row) for row in edit_rows
        ]
        rows.sort(key=lambda item: int(item[1][0]))
        prior_revision, prior_sha = 0, None
        for kind, row in rows:
            if int(row[0]) != prior_revision + 1 or int(row[3]) != prior_revision:
                raise WriteAcceptanceConflict("private Write revision chain is corrupt")
            if row[4] != prior_sha or _sha(str(row[1])) != str(row[2]):
                raise WriteAcceptanceConflict("private Write revision integrity failed")
            if kind == "review":
                event = con.execute(
                    "SELECT action, write_document_id, project_id, proposal_id, target_event_id, "
                    "revision, prior_revision, prior_body_sha256, source_manifest_sha256, "
                    "source_body_sha256, result_html_sha256, event_sha256 "
                    "FROM interview_write_review_events_authority WHERE account_digest = ? "
                    "AND owner_user_id = ? AND event_id = ?",
                    [authority.account_digest, authority.account_id, str(row[5])],
                ).fetchone()
                if event is None:
                    raise WriteAcceptanceConflict("private Write review event is missing")
                expected_event_sha = _event_sha(
                    event_id=str(row[5]), action=str(event[0]),
                    write_document_id=str(event[1]), project_id=str(event[2]),
                    proposal_id=str(event[3]),
                    target_event_id=None if event[4] is None else str(event[4]),
                    revision=None if event[5] is None else int(event[5]),
                    prior_revision=None if event[6] is None else int(event[6]),
                    prior_body_sha256=None if event[7] is None else str(event[7]),
                    source_manifest_sha256=str(event[8]), source_body_sha256=str(event[9]),
                    result_html_sha256=str(event[10]),
                )
                if not (
                    str(row[6]) == str(event[0])
                    and str(row[7]) == str(event[11]) == expected_event_sha
                    and str(row[8]) == str(event[3])
                    and str(row[9]) == str(event[8])
                    and str(row[10]) == str(event[9])
                    and str(row[11]) == str(event[10])
                    and write_document_id == str(event[1])
                    and int(row[0]) == int(event[5])
                ):
                    raise WriteAcceptanceConflict("private Write review receipt is corrupt")
            else:
                event = con.execute(
                    "SELECT write_document_id, project_id, base_revision, revision, "
                    "prior_body_sha256, body_sha256, root_acceptance_event_id, proposal_id, "
                    "source_manifest_sha256, source_body_sha256, result_html_sha256, summary, "
                    "operation, target_revision, target_body_sha256, event_sha256 "
                    "FROM interview_write_edit_events_authority "
                    "WHERE account_digest = ? AND owner_user_id = ? AND event_id = ?",
                    [authority.account_digest, authority.account_id, str(row[5])],
                ).fetchone()
                if event is None:
                    raise WriteAcceptanceConflict("private Write edit event is missing")
                expected_event_sha = _edit_event_sha(
                    event_id=str(row[5]), write_document_id=str(event[0]),
                    project_id=str(event[1]), base_revision=int(event[2]),
                    revision=int(event[3]), prior_body_sha256=str(event[4]),
                    body_sha256=str(event[5]), root_acceptance_event_id=str(event[6]),
                    proposal_id=str(event[7]), source_manifest_sha256=str(event[8]),
                    source_body_sha256=str(event[9]), result_html_sha256=str(event[10]),
                    summary=None if event[11] is None else str(event[11]),
                    operation=str(event[12]),
                    target_revision=None if event[13] is None else int(event[13]),
                    target_body_sha256=None if event[14] is None else str(event[14]),
                )
                root = con.execute(
                    "SELECT proposal_id, source_manifest_sha256, source_body_sha256, "
                    "result_html_sha256, action FROM interview_write_review_events_authority "
                    "WHERE account_digest = ? AND owner_user_id = ? "
                    "AND write_document_id = ? AND event_id = ?",
                    [authority.account_digest, authority.account_id,
                     write_document_id, str(row[7])],
                ).fetchone()
                if not (
                    str(row[6]) == str(event[15]) == expected_event_sha
                    and write_document_id == str(event[0])
                    and int(row[0]) == int(event[3])
                    and int(row[3]) == int(event[2])
                    and str(row[2]) == str(event[5])
                    and str(row[4]) == str(event[4])
                    and str(row[7]) == str(event[6])
                    and tuple(map(str, row[8:12])) == tuple(map(str, event[7:11]))
                    and (
                        (str(event[12]) == "edit" and event[13] is None
                         and event[14] is None)
                        or (str(event[12]) == "restore" and event[13] is not None
                            and 0 <= int(event[13]) < int(event[2])
                            and event[14] is not None
                            and len(str(event[14])) == 64)
                    )
                    and root is not None and str(root[4]) == "accept"
                    and tuple(map(str, root[:4])) == tuple(map(str, row[8:12]))
                ):
                    raise WriteAcceptanceConflict("private Write edit receipt is corrupt")
                if str(event[12]) == "restore":
                    target_revision = int(event[13])
                    if target_revision == 0:
                        target_sha = _sha("")
                    else:
                        target = con.execute(
                            "SELECT body_sha256 FROM ("
                            "SELECT revision, body_sha256 FROM "
                            "interview_write_revisions_authority WHERE account_digest = ? "
                            "AND owner_user_id = ? AND write_document_id = ? UNION ALL "
                            "SELECT revision, body_sha256 FROM "
                            "interview_write_edit_revisions_authority WHERE account_digest = ? "
                            "AND owner_user_id = ? AND write_document_id = ?) history "
                            "WHERE revision = ?",
                            [authority.account_digest, authority.account_id, write_document_id,
                             authority.account_digest, authority.account_id, write_document_id,
                             target_revision],
                        ).fetchone()
                        if target is None:
                            raise WriteAcceptanceConflict(
                                "private Write restore target is missing"
                            )
                        target_sha = str(target[0])
                    if str(event[14]) != target_sha or str(row[2]) != target_sha:
                        raise WriteAcceptanceConflict(
                            "private Write restore target is corrupt"
                        )
            proposal, draft, result_html, result_sha = _ready_result(
                con, authority, str(row[8])
            )
            if (
                proposal.project_id != str(doc[0])
                or proposal.source_manifest_sha256 != str(row[9])
                or proposal.source_body_sha256 != str(row[10])
                or result_sha != str(row[11])
                or (kind == "review" and str(row[6]) == "accept"
                    and result_html != str(row[1]))
                or draft.project_id != str(doc[0])
            ):
                raise WriteAcceptanceConflict("private Write source receipt is corrupt")
            prior_revision, prior_sha = int(row[0]), str(row[2])
        if prior_revision != int(doc[2]) or prior_sha != doc[3]:
            raise WriteAcceptanceConflict("private Write current pointer is corrupt")
        body = "" if not rows else str(rows[-1][1][1])
        return PrivateWriteDocument(
            write_document_id=write_document_id, project_id=str(doc[0]), title=str(doc[1]),
            revision=int(doc[2]), body_html=body,
            body_sha256=None if doc[3] is None else str(doc[3]), visibility=str(doc[4]),
            origin_kind="ai_composition",
        )


def get_private_write_document(
    db_path: str, authority: InterviewAccountAuthority, *, write_document_id: str
) -> PrivateWriteDocument:
    with connect_read(db_path) as con:
        return _read_document(con, authority, write_document_id)


def create_native_private_write(
    db_path: str, authority: InterviewAccountAuthority, *, title: str,
    mutation_key: str,
) -> NativeWriteCreateDecision:
    title = _bounded(title, "title", 300)
    mutation_key = _bounded(mutation_key, "mutation key", 512)
    body_html, body_sha = _validated_edit_html(
        "<article></article>", base_html="<article></article>"
    )
    request_sha = _sha(_canonical({
        "schema_version": 1, "origin_kind": "owner_native", "title": title,
        "initial_body_sha256": body_sha,
    }))
    project_id = "ivwp-" + _sha(
        authority.account_digest + "\0" + mutation_key + "\0" + request_sha
    )[:32]
    write_document_id = "ivwd-" + _sha(
        authority.account_digest + "\0" + project_id + "\0owner-native"
    )[:32]
    event_id = "ivwn-create-" + _sha(
        authority.account_digest + "\0" + mutation_key + "\0" + request_sha
    )[:25]
    event_sha = _native_event_sha(
        event_id=event_id, write_document_id=write_document_id,
        project_id=project_id, mutation_key=mutation_key,
        request_sha256=request_sha, operation="create", base_revision=0, revision=1,
        prior_body_sha256=None, body_sha256=body_sha, title=title, summary=None,
    )
    with connect_write(db_path, purpose="interview/write_native_create", log_on_close=False) as con:
        replay = con.execute(
            "SELECT event_id, write_document_id, project_id, title, body_sha256, "
            "request_sha256 FROM interview_write_native_events_authority WHERE "
            "account_digest = ? AND owner_user_id = ? AND mutation_key = ?",
            [authority.account_digest, authority.account_id, mutation_key],
        ).fetchone()
        if replay is not None:
            if str(replay[5]) != request_sha or not str(replay[0]).startswith("ivwn-create-"):
                raise WriteAcceptanceConflict(
                    "private Write create key was reused with different input"
                )
            replay_document = _read_document(con, authority, str(replay[1]))
            if (replay_document.origin_kind != "owner_native" or
                    replay_document.project_id != str(replay[2]) or
                    replay_document.title != str(replay[3]) or
                    replay_document.revision < 1 or
                    not replay_document.body_sha256):
                raise WriteAcceptanceConflict("private Write create receipt is corrupt")
            return NativeWriteCreateDecision(
                event_id=str(replay[0]), write_document_id=str(replay[1]),
                project_id=str(replay[2]), title=str(replay[3]), revision=1,
                body_sha256=str(replay[4]), replayed=True,
            )
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute(
                "INSERT INTO interview_write_documents_authority "
                "(account_digest, write_document_id, project_id, owner_user_id, title, "
                "origin_kind, current_revision, current_body_sha256) "
                "VALUES (?, ?, ?, ?, ?, 'owner_native', 1, ?)",
                [authority.account_digest, write_document_id, project_id,
                 authority.account_id, title, body_sha],
            )
            con.execute(
                "INSERT INTO interview_write_native_events_authority "
                "(account_digest, event_id, write_document_id, project_id, owner_user_id, "
                "mutation_key, request_sha256, operation, base_revision, revision, "
                "body_sha256, title, event_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'create', 0, 1, ?, ?, ?)",
                [authority.account_digest, event_id, write_document_id, project_id,
                 authority.account_id, mutation_key, request_sha, body_sha, title, event_sha],
            )
            con.execute(
                "INSERT INTO interview_write_native_revisions_authority "
                "(account_digest, write_document_id, revision, owner_user_id, event_id, "
                "event_sha256, operation, body_html, body_sha256, prior_revision) "
                "VALUES (?, ?, 1, ?, ?, ?, 'create', ?, ?, 0)",
                [authority.account_digest, write_document_id, authority.account_id,
                 event_id, event_sha, body_html, body_sha],
            )
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
    return NativeWriteCreateDecision(
        event_id=event_id, write_document_id=write_document_id, project_id=project_id,
        title=title, revision=1, body_sha256=body_sha, replayed=False,
    )


def _evidence_preview(
    authority: InterviewAccountAuthority, document: PrivateWriteDocument,
    source: EvidenceInsertionSource, *, preview_secret: str,
) -> EvidenceInsertionPreview:
    _validate_evidence_source(source)
    if document.origin_kind != "owner_native":
        raise WriteAcceptanceConflict("evidence insertion requires an owner-native manuscript")
    closing = re.search(r"</article>\s*$", document.body_html, re.IGNORECASE)
    if closing is None:
        raise WriteAcceptanceConflict("owner-native manuscript has no append boundary")
    excerpt_sha = _sha(source.excerpt_text)
    block = (
        '<blockquote data-antiek-evidence="true" '
        f'data-citation-receipt-sha256="{source.citation_receipt_sha256}" '
        f'data-source-document-id="{escape(source.source_document_id, quote=True)}" '
        f'data-source-content-sha256="{source.source_content_sha256}" '
        f'data-excerpt-sha256="{excerpt_sha}">'
        f'<p>{escape(source.excerpt_text)}</p>'
        f'<cite>{escape(source.source_title)}</cite></blockquote>'
    )
    proposed = document.body_html[:closing.start()] + block + document.body_html[closing.start():]
    proposed, proposed_sha = _validated_edit_html(proposed, base_html=document.body_html)
    if not isinstance(preview_secret, str) or len(preview_secret.encode()) < 32:
        raise ValueError("evidence insertion preview authority is unavailable")
    preview_material = _canonical({
        "schema_version": 1, "account_digest": authority.account_digest,
        "write_document_id": document.write_document_id,
        "project_id": document.project_id, "base_revision": document.revision,
        "base_body_sha256": document.body_sha256,
        "citation_receipt_sha256": source.citation_receipt_sha256,
        "source_asset_id": source.source_asset_id, "claim_id": source.claim_id,
        "source_document_id": source.source_document_id,
        "chunk_ids": list(source.chunk_ids),
        "source_content_sha256": source.source_content_sha256,
        "excerpt_sha256": excerpt_sha, "proposed_html_sha256": proposed_sha,
    })
    preview_sha = hmac.new(
        preview_secret.encode(), preview_material.encode(), hashlib.sha256,
    ).hexdigest()
    return EvidenceInsertionPreview(
        write_document_id=document.write_document_id, project_id=document.project_id,
        base_revision=document.revision, base_body_sha256=str(document.body_sha256),
        proposed_html=proposed, proposed_html_sha256=proposed_sha,
        excerpt_sha256=excerpt_sha, source_title=source.source_title,
        citation_receipt_sha256=source.citation_receipt_sha256,
        preview_sha256=preview_sha,
    )


def preview_native_evidence_insertion(
    db_path: str, authority: InterviewAccountAuthority, *, write_document_id: str,
    base_revision: int, base_body_sha256: str, source: EvidenceInsertionSource,
    preview_secret: str,
) -> EvidenceInsertionPreview:
    with connect_read(db_path) as con:
        document = _read_document(con, authority, write_document_id)
    if document.revision != base_revision or document.body_sha256 != base_body_sha256:
        raise WriteAcceptanceConflict("stale private Write revision")
    return _evidence_preview(
        authority, document, source, preview_secret=preview_secret,
    )


def _evidence_bundle_preview(
    authority: InterviewAccountAuthority, document: PrivateWriteDocument,
    items: tuple[EvidenceBundleItem, ...], *, preview_secret: str,
) -> EvidenceBundlePreview:
    if document.origin_kind != "owner_native":
        raise WriteAcceptanceConflict("evidence bundle requires an owner-native manuscript")
    if not 2 <= len(items) <= 32:
        raise ValueError("evidence bundle requires between 2 and 32 items")
    receipts = [item.source.citation_receipt_sha256 for item in items]
    if len(set(receipts)) != len(receipts):
        raise ValueError("evidence bundle receipts must be unique")
    if not isinstance(preview_secret, str) or len(preview_secret.encode()) < 32:
        raise ValueError("evidence bundle preview authority is unavailable")
    closing = re.search(r"</article>\s*$", document.body_html, re.IGNORECASE)
    if closing is None:
        raise WriteAcceptanceConflict("owner-native manuscript has no append boundary")
    manifest: list[dict[str, object]] = []
    articles: list[str] = []
    for ordinal, item in enumerate(items):
        _validate_evidence_source(item.source)
        if item.relationship not in {"supports", "contradicts", "context", "unresolved"}:
            raise ValueError("evidence bundle relationship is invalid")
        label = item.operator_label
        if label is not None and (
            not isinstance(label, str) or not label or label != label.strip()
            or len(label) > 200
        ):
            raise ValueError("evidence bundle operator label is invalid")
        excerpt_sha = _sha(item.source.excerpt_text)
        unit = {
            "ordinal": ordinal, "relationship": item.relationship,
            "operator_label": label,
            "citation_receipt_sha256": item.source.citation_receipt_sha256,
            "source_asset_id": item.source.source_asset_id,
            "claim_id": item.source.claim_id,
            "source_document_id": item.source.source_document_id,
            "chunk_ids": list(item.source.chunk_ids),
            "source_title": item.source.source_title,
            "source_content_sha256": item.source.source_content_sha256,
            "excerpt_sha256": excerpt_sha,
        }
        manifest.append(unit)
        label_html = "" if label is None else (
            f'<p data-antiek-operator-framing="true">{escape(label)}</p>'
        )
        articles.append(
            f'<article data-antiek-evidence-unit="{ordinal}" '
            f'data-relationship="{item.relationship}">'
            f'<header><h3>Evidence unit {ordinal + 1}: {item.relationship}</h3>'
            f'{label_html}</header><blockquote '
            f'data-citation-receipt-sha256="{item.source.citation_receipt_sha256}" '
            f'data-source-document-id="{escape(item.source.source_document_id, quote=True)}" '
            f'data-source-content-sha256="{item.source.source_content_sha256}" '
            f'data-excerpt-sha256="{excerpt_sha}"><p>'
            f'{escape(item.source.excerpt_text)}</p><cite>'
            f'{escape(item.source.source_title)}</cite></blockquote></article>'
        )
    manifest_sha = _sha(_canonical(manifest))
    section = (
        f'<section data-antiek-evidence-bundle="{manifest_sha}"><header>'
        f'<h2>Research evidence bundle</h2><p>{len(items)} operator-arranged units; '
        'relationships are explicit, not inferred.</p></header>'
        + "".join(articles) + "</section>"
    )
    proposed = document.body_html[:closing.start()] + section + document.body_html[closing.start():]
    proposed, proposed_sha = _validated_edit_html(proposed, base_html=document.body_html)
    material = _canonical({
        "schema_version": 1, "account_digest": authority.account_digest,
        "write_document_id": document.write_document_id,
        "project_id": document.project_id, "base_revision": document.revision,
        "base_body_sha256": document.body_sha256,
        "manifest_sha256": manifest_sha, "proposed_html_sha256": proposed_sha,
    })
    preview_sha = hmac.new(
        preview_secret.encode(), material.encode(), hashlib.sha256,
    ).hexdigest()
    return EvidenceBundlePreview(
        write_document_id=document.write_document_id, project_id=document.project_id,
        base_revision=document.revision, base_body_sha256=str(document.body_sha256),
        proposed_html=proposed, proposed_html_sha256=proposed_sha,
        manifest_sha256=manifest_sha, preview_sha256=preview_sha,
        items=tuple(manifest),
    )


def _evidence_bundle_manifest_sha(items: tuple[EvidenceBundleItem, ...]) -> str:
    if not 2 <= len(items) <= 32:
        raise ValueError("evidence bundle requires between 2 and 32 items")
    receipts: set[str] = set()
    manifest: list[dict[str, object]] = []
    for ordinal, item in enumerate(items):
        _validate_evidence_source(item.source)
        if item.source.citation_receipt_sha256 in receipts:
            raise ValueError("evidence bundle receipts must be unique")
        receipts.add(item.source.citation_receipt_sha256)
        if item.relationship not in {"supports", "contradicts", "context", "unresolved"}:
            raise ValueError("evidence bundle relationship is invalid")
        label = item.operator_label
        if label is not None and (
            not isinstance(label, str) or not label or label != label.strip()
            or len(label) > 200
        ):
            raise ValueError("evidence bundle operator label is invalid")
        manifest.append({
            "ordinal": ordinal, "relationship": item.relationship,
            "operator_label": label,
            "citation_receipt_sha256": item.source.citation_receipt_sha256,
            "source_asset_id": item.source.source_asset_id,
            "claim_id": item.source.claim_id,
            "source_document_id": item.source.source_document_id,
            "chunk_ids": list(item.source.chunk_ids),
            "source_title": item.source.source_title,
            "source_content_sha256": item.source.source_content_sha256,
            "excerpt_sha256": _sha(item.source.excerpt_text),
        })
    return _sha(_canonical(manifest))


def preview_native_evidence_bundle(
    db_path: str, authority: InterviewAccountAuthority, *, write_document_id: str,
    base_revision: int, base_body_sha256: str, items: tuple[EvidenceBundleItem, ...],
    preview_secret: str,
) -> EvidenceBundlePreview:
    with connect_read(db_path) as con:
        document = _read_document(con, authority, write_document_id)
    if document.revision != base_revision or document.body_sha256 != base_body_sha256:
        raise WriteAcceptanceConflict("stale private Write revision")
    return _evidence_bundle_preview(
        authority, document, items, preview_secret=preview_secret,
    )


def list_private_write_documents(
    db_path: str, authority: InterviewAccountAuthority, *,
    after_document_id: str = "", limit: int = 100,
) -> tuple[PrivateWriteDocumentSummary, ...]:
    """List verified owner documents without returning manuscript bytes."""
    if not isinstance(after_document_id, str) or (
        after_document_id != "" and re.fullmatch(r"ivwd-[0-9a-f]{32}", after_document_id) is None
    ):
        raise ValueError("invalid private Write cursor")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("private Write limit must be between 1 and 100")
    with connect_read(db_path) as con:
        rows = con.execute(
            "SELECT write_document_id, updated_at FROM "
            "interview_write_documents_authority WHERE account_digest = ? "
            "AND owner_user_id = ? AND write_document_id > ? "
            "ORDER BY write_document_id LIMIT ?",
            [authority.account_digest, authority.account_id, after_document_id, limit],
        ).fetchall()
        result: list[PrivateWriteDocumentSummary] = []
        for write_document_id, updated_at in rows:
            document = _read_document(con, authority, str(write_document_id))
            if (document.body_sha256 is None or len(document.body_sha256) != 64 or
                    document.visibility != "private"):
                raise WriteAcceptanceConflict("private Write current pointer is corrupt")
            result.append(PrivateWriteDocumentSummary(
                write_document_id=document.write_document_id,
                project_id=document.project_id,
                title=document.title,
                revision=document.revision,
                body_sha256=document.body_sha256,
                visibility=document.visibility,
                updated_at=str(updated_at),
                origin_kind=document.origin_kind,
            ))
        return tuple(result)


def _edit_decision(row: tuple[Any, ...], replayed: bool) -> WriteEditDecision:
    return WriteEditDecision(
        event_id=str(row[0]), write_document_id=str(row[1]), project_id=str(row[2]),
        prior_revision=int(row[3]), revision=int(row[4]), body_sha256=str(row[5]),
        replayed=replayed,
    )


def _root_lineage_for_revision(
    con: Any, authority: InterviewAccountAuthority, write_document_id: str, revision: int
) -> tuple[str, str, str, str, str]:
    edit = con.execute(
        "SELECT root_acceptance_event_id, proposal_id, source_manifest_sha256, "
        "source_body_sha256, result_html_sha256 FROM "
        "interview_write_edit_revisions_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND write_document_id = ? AND revision = ?",
        [authority.account_digest, authority.account_id, write_document_id, revision],
    ).fetchone()
    if edit is not None:
        return tuple(map(str, edit))  # type: ignore[return-value]
    review = con.execute(
        "SELECT event_id, proposal_id, source_manifest_sha256, source_body_sha256, "
        "result_html_sha256, action, target_event_id FROM "
        "interview_write_review_events_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND write_document_id = ? AND revision = ?",
        [authority.account_digest, authority.account_id, write_document_id, revision],
    ).fetchone()
    if review is None:
        raise WriteAcceptanceConflict("private Write source lineage is missing")
    if str(review[5]) == "accept":
        return tuple(map(str, review[:5]))  # type: ignore[return-value]
    if str(review[5]) != "undo" or review[6] is None:
        raise WriteAcceptanceConflict("private Write source lineage is corrupt")
    target = con.execute(
        "SELECT prior_revision, event_id, proposal_id, source_manifest_sha256, "
        "source_body_sha256, result_html_sha256 FROM "
        "interview_write_review_events_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND write_document_id = ? AND event_id = ? "
        "AND action = 'accept'",
        [authority.account_digest, authority.account_id,
         write_document_id, str(review[6])],
    ).fetchone()
    if target is None:
        raise WriteAcceptanceConflict("private Write source lineage is corrupt")
    restored_revision = int(target[0])
    if restored_revision == 0:
        return tuple(map(str, target[1:6]))  # type: ignore[return-value]
    return _root_lineage_for_revision(
        con, authority, write_document_id, restored_revision
    )


def _edit_native_private_write(
    con: Any, authority: InterviewAccountAuthority, document: PrivateWriteDocument, *,
    mutation_key: str, request_sha: str, base_revision: int,
    base_body_sha256: str, body_html: str, summary: str | None,
    operation: Literal["edit", "restore"], target_revision: int | None,
    target_body_sha256: str | None,
    evidence_source: EvidenceInsertionSource | None = None,
    preview_sha256: str | None = None,
    evidence_bundle: tuple[EvidenceBundleItem, ...] | None = None,
    bundle_manifest_sha256: str | None = None,
    synthesis_acceptance: dict[str, object] | None = None,
) -> WriteEditDecision:
    if sum(item is not None for item in (
        evidence_source, evidence_bundle, synthesis_acceptance,
    )) > 1:
        raise WriteAcceptanceConflict("private Write companion ledgers are mixed")
    replay = con.execute(
        "SELECT event_id, write_document_id, project_id, base_revision, revision, "
        "body_sha256, request_sha256, operation FROM "
        "interview_write_native_events_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND mutation_key = ?",
        [authority.account_digest, authority.account_id, mutation_key],
    ).fetchone()
    if replay is not None:
        if str(replay[6]) != request_sha or str(replay[7]) not in {"edit", "restore"}:
            raise WriteAcceptanceConflict(
                "private Write edit key was reused with different input"
            )
        receipt = con.execute(
            "SELECT receipt_sha256 FROM interview_write_evidence_insertions_authority "
            "WHERE account_digest = ? AND owner_user_id = ? AND native_event_id = ?",
            [authority.account_digest, authority.account_id, str(replay[0])],
        ).fetchone()
        bundle_receipt = con.execute(
            "SELECT receipt_sha256 FROM interview_write_evidence_bundles_authority "
            "WHERE account_digest = ? AND owner_user_id = ? AND native_event_id = ?",
            [authority.account_digest, authority.account_id, str(replay[0])],
        ).fetchone()
        synthesis_receipt = con.execute(
            "SELECT receipt_sha256 FROM interview_write_synthesis_acceptances_authority "
            "WHERE account_digest = ? AND owner_user_id = ? AND native_event_id = ?",
            [authority.account_digest, authority.account_id, str(replay[0])],
        ).fetchone()
        if ((evidence_source is None) != (receipt is None)
                or (evidence_bundle is None) != (bundle_receipt is None)
                or (synthesis_acceptance is None) != (synthesis_receipt is None)
                or sum(item is not None for item in (
                    receipt, bundle_receipt, synthesis_receipt,
                )) > 1):
            raise WriteAcceptanceConflict("private Write evidence replay is corrupt")
        return _edit_decision(tuple(replay[:6]), True)
    if document.revision != base_revision or document.body_sha256 != base_body_sha256:
        raise WriteAcceptanceConflict("stale private Write revision")
    body_html, body_sha = _validated_edit_html(
        body_html, base_html=(body_html if operation == "restore" else document.body_html),
    )
    revision = base_revision + 1
    event_id = "ivwn-" + operation + "-" + _sha(
        authority.account_digest + "\0" + mutation_key + "\0" + request_sha
    )[:27]
    persisted_summary = (
        "antiek:evidence_bundle:" + bundle_manifest_sha256
        if evidence_bundle is not None and bundle_manifest_sha256 is not None
        else "antiek:synthesis_accept:" + str(synthesis_acceptance["proposal_id"])
        if synthesis_acceptance is not None
        else summary
    )
    event_sha = _native_event_sha(
        event_id=event_id, write_document_id=document.write_document_id,
        project_id=document.project_id, mutation_key=mutation_key,
        request_sha256=request_sha, operation=operation,
        base_revision=base_revision, revision=revision,
        prior_body_sha256=base_body_sha256, body_sha256=body_sha,
        title=None, summary=persisted_summary, target_revision=target_revision,
        target_body_sha256=target_body_sha256,
    )
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(
            "INSERT INTO interview_write_native_events_authority "
            "(account_digest, event_id, write_document_id, project_id, owner_user_id, "
            "mutation_key, request_sha256, operation, target_revision, "
            "target_body_sha256, base_revision, revision, prior_body_sha256, "
            "body_sha256, summary, event_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [authority.account_digest, event_id, document.write_document_id,
             document.project_id, authority.account_id, mutation_key, request_sha,
             operation, target_revision, target_body_sha256, base_revision, revision,
             base_body_sha256, body_sha, persisted_summary, event_sha],
        )
        con.execute(
            "INSERT INTO interview_write_native_revisions_authority "
            "(account_digest, write_document_id, revision, owner_user_id, event_id, "
            "event_sha256, operation, target_revision, target_body_sha256, body_html, "
            "body_sha256, prior_revision, prior_body_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [authority.account_digest, document.write_document_id, revision,
             authority.account_id, event_id, event_sha, operation, target_revision,
             target_body_sha256, body_html, body_sha, base_revision, base_body_sha256],
        )
        if evidence_source is not None:
            if preview_sha256 is None:
                raise WriteAcceptanceConflict("private Write evidence preview is missing")
            excerpt_sha = _sha(evidence_source.excerpt_text)
            receipt_value: dict[str, object] = {
                "insertion_id": "ivwi-" + event_id.removeprefix("ivwn-edit-"),
                "write_document_id": document.write_document_id,
                "project_id": document.project_id, "native_event_id": event_id,
                "native_event_sha256": event_sha, "revision": revision,
                "operation": "evidence_insert",
                "citation_receipt_sha256": evidence_source.citation_receipt_sha256,
                "source_asset_id": evidence_source.source_asset_id,
                "claim_id": evidence_source.claim_id,
                "source_document_id": evidence_source.source_document_id,
                "chunk_ids": list(evidence_source.chunk_ids),
                "source_title": evidence_source.source_title,
                "source_content_sha256": evidence_source.source_content_sha256,
                "excerpt_sha256": excerpt_sha, "preview_sha256": preview_sha256,
            }
            receipt_sha = _evidence_receipt_sha(receipt_value)
            con.execute(
                "INSERT INTO interview_write_evidence_insertions_authority "
                "(account_digest, insertion_id, write_document_id, project_id, "
                "owner_user_id, native_event_id, native_event_sha256, operation, revision, "
                "citation_receipt_sha256, source_asset_id, claim_id, source_document_id, "
                "chunk_ids_json, source_title, source_content_sha256, excerpt_sha256, "
                "preview_sha256, receipt_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, "
                "'evidence_insert', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [authority.account_digest, receipt_value["insertion_id"],
                 document.write_document_id, document.project_id, authority.account_id,
                 event_id, event_sha, revision, evidence_source.citation_receipt_sha256,
                 evidence_source.source_asset_id, evidence_source.claim_id,
                 evidence_source.source_document_id,
                 _canonical(list(evidence_source.chunk_ids)), evidence_source.source_title,
                 evidence_source.source_content_sha256, excerpt_sha, preview_sha256,
                 receipt_sha],
            )
        if evidence_bundle is not None:
            if preview_sha256 is None or bundle_manifest_sha256 is None:
                raise WriteAcceptanceConflict("private Write evidence bundle preview is missing")
            bundle_id = "ivwb-" + event_id.removeprefix("ivwn-edit-")
            bundle_value: dict[str, object] = {
                "bundle_id": bundle_id, "write_document_id": document.write_document_id,
                "project_id": document.project_id, "native_event_id": event_id,
                "native_event_sha256": event_sha, "operation": "evidence_bundle",
                "revision": revision, "item_count": len(evidence_bundle),
                "manifest_sha256": bundle_manifest_sha256,
                "preview_sha256": preview_sha256,
            }
            bundle_receipt_sha = _evidence_receipt_sha(bundle_value)
            con.execute(
                "INSERT INTO interview_write_evidence_bundles_authority "
                "(account_digest, bundle_id, write_document_id, project_id, owner_user_id, "
                "native_event_id, native_event_sha256, operation, revision, item_count, "
                "manifest_sha256, preview_sha256, receipt_sha256) VALUES (?, ?, ?, ?, ?, "
                "?, ?, 'evidence_bundle', ?, ?, ?, ?, ?)",
                [authority.account_digest, bundle_id, document.write_document_id,
                 document.project_id, authority.account_id, event_id, event_sha, revision,
                 len(evidence_bundle), bundle_manifest_sha256, preview_sha256,
                 bundle_receipt_sha],
            )
            for ordinal, item in enumerate(evidence_bundle):
                excerpt_sha = _sha(item.source.excerpt_text)
                unit_value: dict[str, object] = {
                    "bundle_id": bundle_id, "ordinal": ordinal,
                    "relationship": item.relationship,
                    "operator_label": item.operator_label,
                    "citation_receipt_sha256": item.source.citation_receipt_sha256,
                    "source_asset_id": item.source.source_asset_id,
                    "claim_id": item.source.claim_id,
                    "source_document_id": item.source.source_document_id,
                    "chunk_ids": list(item.source.chunk_ids),
                    "source_title": item.source.source_title,
                    "source_content_sha256": item.source.source_content_sha256,
                    "excerpt_sha256": excerpt_sha,
                }
                unit_sha = _evidence_receipt_sha(unit_value)
                con.execute(
                    "INSERT INTO interview_write_evidence_bundle_units_authority "
                    "(account_digest, bundle_id, owner_user_id, ordinal, relationship, "
                    "operator_label, citation_receipt_sha256, source_asset_id, claim_id, "
                    "source_document_id, chunk_ids_json, source_title, "
                    "source_content_sha256, excerpt_sha256, unit_receipt_sha256) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [authority.account_digest, bundle_id, authority.account_id, ordinal,
                     item.relationship, item.operator_label,
                     item.source.citation_receipt_sha256, item.source.source_asset_id,
                     item.source.claim_id, item.source.source_document_id,
                     _canonical(list(item.source.chunk_ids)), item.source.source_title,
                     item.source.source_content_sha256, excerpt_sha, unit_sha],
                )
        if synthesis_acceptance is not None:
            required = {
                "acceptance_id", "proposal_id", "bundle_id", "execution_run_id",
                "source_manifest_sha256", "source_content_sha256", "source_receipt_sha256",
                "prompt_sha256", "route_sha256", "result_html_sha256", "preview_sha256",
            }
            if set(synthesis_acceptance) != required:
                raise WriteAcceptanceConflict("private Write synthesis acceptance is invalid")
            receipt_value: dict[str, object] = {
                **synthesis_acceptance, "write_document_id": document.write_document_id,
                "project_id": document.project_id, "native_event_id": event_id,
                "native_event_sha256": event_sha, "operation": "synthesis_accept",
                "base_revision": base_revision, "base_html_sha256": base_body_sha256,
                "revision": revision, "html_sha256": body_sha,
            }
            receipt_sha = _evidence_receipt_sha(receipt_value)
            con.execute(
                "INSERT INTO interview_write_synthesis_acceptances_authority "
                "(account_digest, acceptance_id, write_document_id, project_id, "
                "owner_user_id, native_event_id, native_event_sha256, operation, "
                "proposal_id, bundle_id, execution_run_id, base_revision, "
                "base_html_sha256, revision, html_sha256, source_manifest_sha256, "
                "source_content_sha256, source_receipt_sha256, prompt_sha256, "
                "route_sha256, result_html_sha256, preview_sha256, receipt_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'synthesis_accept', ?, ?, ?, ?, ?, ?, ?, "
                "?, ?, ?, ?, ?, ?, ?, ?)",
                [authority.account_digest, synthesis_acceptance["acceptance_id"],
                 document.write_document_id, document.project_id, authority.account_id,
                 event_id, event_sha, synthesis_acceptance["proposal_id"],
                 synthesis_acceptance["bundle_id"], synthesis_acceptance["execution_run_id"],
                 base_revision, base_body_sha256, revision, body_sha,
                 synthesis_acceptance["source_manifest_sha256"],
                 synthesis_acceptance["source_content_sha256"],
                 synthesis_acceptance["source_receipt_sha256"],
                 synthesis_acceptance["prompt_sha256"], synthesis_acceptance["route_sha256"],
                 synthesis_acceptance["result_html_sha256"],
                 synthesis_acceptance["preview_sha256"], receipt_sha],
            )
        advanced = con.execute(
            "UPDATE interview_write_documents_authority SET current_revision = ?, "
            "current_body_sha256 = ?, updated_at = CURRENT_TIMESTAMP WHERE "
            "account_digest = ? AND owner_user_id = ? AND write_document_id = ? "
            "AND origin_kind = 'owner_native' AND current_revision = ? "
            "AND current_body_sha256 = ? RETURNING 1",
            [revision, body_sha, authority.account_digest, authority.account_id,
             document.write_document_id, base_revision, base_body_sha256],
        ).fetchone()
        if advanced is None:
            raise WriteAcceptanceConflict("stale private Write revision")
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    return WriteEditDecision(
        event_id=event_id, write_document_id=document.write_document_id,
        project_id=document.project_id, revision=revision,
        prior_revision=base_revision, body_sha256=body_sha, replayed=False,
    )


def apply_native_evidence_insertion(
    db_path: str, authority: InterviewAccountAuthority, *, write_document_id: str,
    mutation_key: str, base_revision: int, base_body_sha256: str,
    source: EvidenceInsertionSource, preview_sha256: str,
    proposed_html_sha256: str, preview_secret: str,
) -> WriteEditDecision:
    mutation_key = _bounded(mutation_key, "mutation key", 512)
    for value, label in (
        (preview_sha256, "preview hash"),
        (proposed_html_sha256, "proposed HTML hash"),
        (base_body_sha256, "base hash"),
    ):
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(f"evidence insertion {label} is invalid")
    _validate_evidence_source(source)
    request_sha = _sha(_canonical({
        "schema_version": 1, "write_document_id": write_document_id,
        "base_revision": base_revision, "base_body_sha256": base_body_sha256,
        "preview_sha256": preview_sha256,
        "proposed_html_sha256": proposed_html_sha256,
        "citation_receipt_sha256": source.citation_receipt_sha256,
        "source_content_sha256": source.source_content_sha256,
        "excerpt_sha256": _sha(source.excerpt_text),
    }))
    with connect_write(db_path, purpose="interview/write_evidence_insert", log_on_close=False) as con:
        replay = con.execute(
            "SELECT event_id, write_document_id, project_id, base_revision, revision, "
            "body_sha256, request_sha256 FROM interview_write_native_events_authority "
            "WHERE account_digest = ? AND owner_user_id = ? AND mutation_key = ?",
            [authority.account_digest, authority.account_id, mutation_key],
        ).fetchone()
        if replay is not None:
            if str(replay[6]) != request_sha:
                raise WriteAcceptanceConflict(
                    "private Write edit key was reused with different input"
                )
            _read_document(con, authority, str(replay[1]))
            receipt = con.execute(
                "SELECT preview_sha256 FROM interview_write_evidence_insertions_authority "
                "WHERE account_digest = ? AND owner_user_id = ? AND native_event_id = ?",
                [authority.account_digest, authority.account_id, str(replay[0])],
            ).fetchone()
            if receipt is None or str(receipt[0]) != preview_sha256:
                raise WriteAcceptanceConflict("private Write evidence replay is corrupt")
            return WriteEditDecision(
                event_id=str(replay[0]), write_document_id=str(replay[1]),
                project_id=str(replay[2]), prior_revision=int(replay[3]),
                revision=int(replay[4]), body_sha256=str(replay[5]),
                replayed=True, operation="evidence_insert",
            )
        document = _read_document(con, authority, write_document_id)
        if document.revision != base_revision or document.body_sha256 != base_body_sha256:
            raise WriteAcceptanceConflict("stale private Write revision")
        preview = _evidence_preview(
            authority, document, source, preview_secret=preview_secret,
        )
        if (preview.preview_sha256 != preview_sha256
                or preview.proposed_html_sha256 != proposed_html_sha256):
            raise WriteAcceptanceConflict("private Write evidence preview is stale")
        decision = _edit_native_private_write(
            con, authority, document, mutation_key=mutation_key,
            request_sha=request_sha, base_revision=base_revision,
            base_body_sha256=base_body_sha256, body_html=preview.proposed_html,
            summary=None, operation="edit", target_revision=None,
            target_body_sha256=None, evidence_source=source,
            preview_sha256=preview_sha256,
        )
        return WriteEditDecision(
            **{**decision.__dict__, "operation": "evidence_insert"}
        )


def apply_native_evidence_bundle(
    db_path: str, authority: InterviewAccountAuthority, *, write_document_id: str,
    mutation_key: str, base_revision: int, base_body_sha256: str,
    items: tuple[EvidenceBundleItem, ...], preview_sha256: str,
    manifest_sha256: str, proposed_html_sha256: str, preview_secret: str,
) -> WriteEditDecision:
    mutation_key = _bounded(mutation_key, "mutation key", 512)
    for value, label in (
        (preview_sha256, "preview hash"), (manifest_sha256, "manifest hash"),
        (proposed_html_sha256, "proposed HTML hash"),
        (base_body_sha256, "base hash"),
    ):
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(f"evidence bundle {label} is invalid")
    if _evidence_bundle_manifest_sha(items) != manifest_sha256:
        raise WriteAcceptanceConflict("private Write evidence bundle manifest is stale")
    request_sha = _sha(_canonical({
        "schema_version": 1, "write_document_id": write_document_id,
        "base_revision": base_revision, "base_body_sha256": base_body_sha256,
        "manifest_sha256": manifest_sha256, "preview_sha256": preview_sha256,
        "proposed_html_sha256": proposed_html_sha256,
    }))
    with connect_write(db_path, purpose="interview/write_evidence_bundle", log_on_close=False) as con:
        replay = con.execute(
            "SELECT event_id, write_document_id, project_id, base_revision, revision, "
            "body_sha256, request_sha256 FROM interview_write_native_events_authority "
            "WHERE account_digest = ? AND owner_user_id = ? AND mutation_key = ?",
            [authority.account_digest, authority.account_id, mutation_key],
        ).fetchone()
        if replay is not None:
            if str(replay[6]) != request_sha:
                raise WriteAcceptanceConflict(
                    "private Write edit key was reused with different input"
                )
            _read_document(con, authority, str(replay[1]))
            receipt = con.execute(
                "SELECT manifest_sha256, preview_sha256 FROM "
                "interview_write_evidence_bundles_authority WHERE account_digest = ? "
                "AND owner_user_id = ? AND native_event_id = ?",
                [authority.account_digest, authority.account_id, str(replay[0])],
            ).fetchone()
            if receipt is None or tuple(map(str, receipt)) != (
                manifest_sha256, preview_sha256,
            ):
                raise WriteAcceptanceConflict("private Write evidence bundle replay is corrupt")
            return WriteEditDecision(
                event_id=str(replay[0]), write_document_id=str(replay[1]),
                project_id=str(replay[2]), prior_revision=int(replay[3]),
                revision=int(replay[4]), body_sha256=str(replay[5]), replayed=True,
                operation="evidence_bundle",
            )
        document = _read_document(con, authority, write_document_id)
        if document.revision != base_revision or document.body_sha256 != base_body_sha256:
            raise WriteAcceptanceConflict("stale private Write revision")
        preview = _evidence_bundle_preview(
            authority, document, items, preview_secret=preview_secret,
        )
        if (preview.preview_sha256 != preview_sha256
                or preview.manifest_sha256 != manifest_sha256
                or preview.proposed_html_sha256 != proposed_html_sha256):
            raise WriteAcceptanceConflict("private Write evidence bundle preview is stale")
        decision = _edit_native_private_write(
            con, authority, document, mutation_key=mutation_key,
            request_sha=request_sha, base_revision=base_revision,
            base_body_sha256=base_body_sha256, body_html=preview.proposed_html,
            summary=None, operation="edit", target_revision=None,
            target_body_sha256=None, preview_sha256=preview_sha256,
            evidence_bundle=items, bundle_manifest_sha256=manifest_sha256,
        )
        return WriteEditDecision(
            **{**decision.__dict__, "operation": "evidence_bundle"}
        )


def edit_private_write(
    db_path: str, authority: InterviewAccountAuthority, *, write_document_id: str,
    mutation_key: str, base_revision: int, base_body_sha256: str,
    body_html: str, summary: str | None = None,
    _operation: Literal["edit", "restore"] = "edit",
    _target_revision: int | None = None,
    _target_body_sha256: str | None = None,
    _lineage_revision: int | None = None,
) -> WriteEditDecision:
    write_document_id = _bounded(write_document_id, "document id", 512)
    mutation_key = _bounded(mutation_key, "mutation key", 512)
    if type(base_revision) is not int or base_revision < 1:
        raise ValueError("private Write edit base revision is invalid")
    if not isinstance(base_body_sha256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", base_body_sha256
    ):
        raise ValueError("private Write edit base hash is invalid")
    if summary is not None and (summary != summary.strip() or len(summary) > 5_000):
        raise ValueError("private Write edit summary is invalid")
    if _operation not in {"edit", "restore"}:
        raise ValueError("private Write operation is invalid")
    if _operation == "restore" and (
        type(_target_revision) is not int or _target_revision < 0
        or not isinstance(_target_body_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", _target_body_sha256)
    ):
        raise ValueError("private Write restore target is invalid")
    body_html, body_sha = _bounded_edit_html(body_html)
    request_value: dict[str, object] = {
        "schema_version": 1, "write_document_id": write_document_id,
        "base_revision": base_revision, "base_body_sha256": base_body_sha256,
        "body_sha256": body_sha, "body_html": body_html, "summary": summary,
    }
    if _operation == "restore":
        request_value.update({
            "schema_version": 2, "operation": "restore",
            "target_revision": _target_revision,
            "target_body_sha256": _target_body_sha256,
        })
    elif _target_revision is not None or _target_body_sha256 is not None:
        raise ValueError("private Write edit target is invalid")
    request_sha = _sha(_canonical(request_value))
    with connect_write(db_path, purpose="interview/write_edit", log_on_close=False) as con:
        document = _read_document(con, authority, write_document_id)
        if document.origin_kind == "owner_native":
            if _operation == "restore" and (_target_revision is None or _target_revision < 1):
                raise ValueError("private Write native restore target is invalid")
            return _edit_native_private_write(
                con, authority, document, mutation_key=mutation_key,
                request_sha=request_sha, base_revision=base_revision,
                base_body_sha256=base_body_sha256, body_html=body_html,
                summary=summary, operation=_operation, target_revision=_target_revision,
                target_body_sha256=_target_body_sha256,
            )
        replay = con.execute(
            "SELECT event_id, write_document_id, project_id, base_revision, revision, "
            "body_sha256, request_sha256 FROM interview_write_edit_events_authority "
            "WHERE account_digest = ? AND owner_user_id = ? AND mutation_key = ?",
            [authority.account_digest, authority.account_id, mutation_key],
        ).fetchone()
        if replay is not None:
            if str(replay[6]) != request_sha:
                raise WriteAcceptanceConflict("private Write edit key was reused with different input")
            return _edit_decision(tuple(replay[:6]), True)
        body_html, body_sha = _validated_edit_html(
            body_html,
            base_html=(body_html if _operation == "restore" else document.body_html),
        )
        if document.revision != base_revision or document.body_sha256 != base_body_sha256:
            raise WriteAcceptanceConflict("stale private Write revision")
        lineage = _root_lineage_for_revision(
            con, authority, write_document_id,
            base_revision if _lineage_revision is None else _lineage_revision,
        )
        root_event_id = lineage[0]
        root = con.execute(
            "SELECT proposal_id, source_manifest_sha256, source_body_sha256, "
            "result_html_sha256 FROM interview_write_review_events_authority "
            "WHERE account_digest = ? AND owner_user_id = ? AND write_document_id = ? "
            "AND event_id = ? AND action = 'accept'",
            [authority.account_digest, authority.account_id,
             write_document_id, root_event_id],
        ).fetchone()
        if root is None or tuple(map(str, root)) != lineage[1:5]:
            raise WriteAcceptanceConflict("private Write source lineage is corrupt")
        revision = base_revision + 1
        event_id = "ivwe-edit-" + _sha(
            authority.account_digest + "\0" + mutation_key + "\0" + request_sha
        )[:27]
        event_sha = _edit_event_sha(
            event_id=event_id, write_document_id=write_document_id,
            project_id=document.project_id, base_revision=base_revision,
            revision=revision, prior_body_sha256=base_body_sha256,
            body_sha256=body_sha, root_acceptance_event_id=root_event_id,
            proposal_id=str(root[0]), source_manifest_sha256=str(root[1]),
            source_body_sha256=str(root[2]), result_html_sha256=str(root[3]),
            summary=summary, operation=_operation,
            target_revision=_target_revision,
            target_body_sha256=_target_body_sha256,
        )
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute(
                "INSERT INTO interview_write_edit_events_authority "
                "(account_digest, event_id, write_document_id, project_id, owner_user_id, "
                "mutation_key, request_sha256, operation, target_revision, "
                "target_body_sha256, base_revision, revision, prior_body_sha256, "
                "body_sha256, root_acceptance_event_id, proposal_id, source_manifest_sha256, "
                "source_body_sha256, result_html_sha256, summary, event_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [authority.account_digest, event_id, write_document_id, document.project_id,
                 authority.account_id, mutation_key, request_sha, _operation,
                 _target_revision, _target_body_sha256, base_revision, revision,
                 base_body_sha256, body_sha, root_event_id, str(root[0]), str(root[1]),
                 str(root[2]), str(root[3]), summary, event_sha],
            )
            con.execute(
                "INSERT INTO interview_write_edit_revisions_authority "
                "(account_digest, write_document_id, revision, owner_user_id, event_id, "
                "edit_event_sha256, root_acceptance_event_id, proposal_id, "
                "source_manifest_sha256, source_body_sha256, result_html_sha256, body_html, "
                "body_sha256, prior_revision, prior_body_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [authority.account_digest, write_document_id, revision, authority.account_id,
                 event_id, event_sha, root_event_id, str(root[0]), str(root[1]), str(root[2]),
                 str(root[3]), body_html, body_sha, base_revision, base_body_sha256],
            )
            advanced = con.execute(
                "UPDATE interview_write_documents_authority SET current_revision = ?, "
                "current_body_sha256 = ?, updated_at = CURRENT_TIMESTAMP WHERE "
                "account_digest = ? AND owner_user_id = ? AND write_document_id = ? "
                "AND current_revision = ? AND current_body_sha256 = ? RETURNING 1",
                [revision, body_sha, authority.account_digest, authority.account_id,
                 write_document_id, base_revision, base_body_sha256],
            ).fetchone()
            if advanced is None:
                raise WriteAcceptanceConflict("stale private Write revision")
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        return WriteEditDecision(
            event_id=event_id, write_document_id=write_document_id,
            project_id=document.project_id, revision=revision,
            prior_revision=base_revision, body_sha256=body_sha, replayed=False,
        )


def _revision_metadata(
    con: Any, authority: InterviewAccountAuthority, write_document_id: str,
    revision: int, *, include_body: bool,
) -> PrivateWriteRevision:
    native = con.execute(
        "SELECT r.operation, r.event_id, r.body_html, r.body_sha256, "
        "r.prior_body_sha256, r.target_revision, r.target_body_sha256, "
        "e.created_at, e.summary, EXISTS(SELECT 1 FROM "
        "interview_write_evidence_insertions_authority i WHERE "
        "i.account_digest = r.account_digest AND i.native_event_id = r.event_id), "
        "EXISTS(SELECT 1 FROM interview_write_evidence_bundles_authority b WHERE "
        "b.account_digest = r.account_digest AND b.native_event_id = r.event_id), "
        "EXISTS(SELECT 1 FROM interview_write_synthesis_acceptances_authority s WHERE "
        "s.account_digest = r.account_digest AND s.native_event_id = r.event_id) "
        "FROM interview_write_native_revisions_authority r "
        "JOIN interview_write_native_events_authority e ON "
        "e.account_digest = r.account_digest AND e.event_id = r.event_id WHERE "
        "r.account_digest = ? AND r.owner_user_id = ? AND r.write_document_id = ? "
        "AND r.revision = ?",
        [authority.account_digest, authority.account_id, write_document_id, revision],
    ).fetchone()
    if native is not None:
        return PrivateWriteRevision(
            revision=revision,
            operation=("synthesis_accept" if bool(native[11]) else
                       "evidence_bundle" if bool(native[10]) else
                       "evidence_insert" if bool(native[9]) else str(native[0])),
            event_id=str(native[1]),
            body_sha256=str(native[3]),
            prior_body_sha256=None if native[4] is None else str(native[4]),
            root_acceptance_event_id=None, proposal_id=None,
            target_revision=None if native[5] is None else int(native[5]),
            target_body_sha256=None if native[6] is None else str(native[6]),
            created_at=str(native[7]), has_summary=native[8] is not None,
            body_html=str(native[2]) if include_body else None,
            origin_kind="owner_native",
        )
    review = con.execute(
        "SELECT r.action, r.event_id, r.body_html, r.body_sha256, "
        "r.prior_body_sha256, r.proposal_id, e.rationale, e.target_event_id, e.created_at "
        "FROM interview_write_revisions_authority r JOIN "
        "interview_write_review_events_authority e ON e.account_digest = r.account_digest "
        "AND e.event_id = r.event_id WHERE r.account_digest = ? AND r.owner_user_id = ? "
        "AND r.write_document_id = ? AND r.revision = ?",
        [authority.account_digest, authority.account_id, write_document_id, revision],
    ).fetchone()
    if review is not None:
        lineage = _root_lineage_for_revision(
            con, authority, write_document_id, revision
        )
        target_revision: int | None = None
        target_sha: str | None = None
        if str(review[0]) == "undo":
            target = con.execute(
                "SELECT prior_revision FROM interview_write_review_events_authority "
                "WHERE account_digest = ? AND owner_user_id = ? AND write_document_id = ? "
                "AND event_id = ? AND action = 'accept'",
                [authority.account_digest, authority.account_id,
                 write_document_id, str(review[7])],
            ).fetchone()
            if target is None:
                raise WriteAcceptanceConflict("private Write undo target is missing")
            target_revision, target_sha = int(target[0]), str(review[3])
        return PrivateWriteRevision(
            revision=revision, operation=str(review[0]), event_id=str(review[1]),
            body_sha256=str(review[3]),
            prior_body_sha256=None if review[4] is None else str(review[4]),
            root_acceptance_event_id=lineage[0], proposal_id=lineage[1],
            target_revision=target_revision, target_body_sha256=target_sha,
            created_at=str(review[8]), has_summary=review[6] is not None,
            body_html=str(review[2]) if include_body else None,
        )
    edit = con.execute(
        "SELECT e.operation, r.event_id, r.body_html, r.body_sha256, "
        "r.prior_body_sha256, r.root_acceptance_event_id, r.proposal_id, "
        "e.target_revision, e.target_body_sha256, e.created_at, e.summary "
        "FROM interview_write_edit_revisions_authority r JOIN "
        "interview_write_edit_events_authority e ON e.account_digest = r.account_digest "
        "AND e.event_id = r.event_id WHERE r.account_digest = ? AND r.owner_user_id = ? "
        "AND r.write_document_id = ? AND r.revision = ?",
        [authority.account_digest, authority.account_id, write_document_id, revision],
    ).fetchone()
    if edit is None:
        raise ValueError("private Write revision not found")
    return PrivateWriteRevision(
        revision=revision, operation=str(edit[0]), event_id=str(edit[1]),
        body_sha256=str(edit[3]), prior_body_sha256=str(edit[4]),
        root_acceptance_event_id=str(edit[5]), proposal_id=str(edit[6]),
        target_revision=None if edit[7] is None else int(edit[7]),
        target_body_sha256=None if edit[8] is None else str(edit[8]),
        created_at=str(edit[9]), has_summary=edit[10] is not None,
        body_html=str(edit[2]) if include_body else None,
    )


def list_private_write_revisions(
    db_path: str, authority: InterviewAccountAuthority, *, write_document_id: str,
    after_revision: int = 0, limit: int = 100,
) -> tuple[PrivateWriteRevision, ...]:
    if type(after_revision) is not int or after_revision < 0:
        raise ValueError("private Write history cursor is invalid")
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("private Write history limit is invalid")
    with connect_read(db_path) as con:
        document = _read_document(con, authority, write_document_id)
        upper = min(document.revision, after_revision + limit)
        return tuple(
            _revision_metadata(
                con, authority, write_document_id, revision, include_body=False
            )
            for revision in range(after_revision + 1, upper + 1)
        )


def get_private_write_revision(
    db_path: str, authority: InterviewAccountAuthority, *, write_document_id: str,
    revision: int,
) -> PrivateWriteRevision:
    if type(revision) is not int or revision < 1:
        raise ValueError("private Write revision not found")
    with connect_read(db_path) as con:
        document = _read_document(con, authority, write_document_id)
        if revision > document.revision:
            raise ValueError("private Write revision not found")
        return _revision_metadata(
            con, authority, write_document_id, revision, include_body=True
        )


def restore_private_write_revision(
    db_path: str, authority: InterviewAccountAuthority, *, write_document_id: str,
    mutation_key: str, base_revision: int, base_body_sha256: str,
    target_revision: int,
) -> WriteEditDecision:
    if type(target_revision) is not int or target_revision < 0:
        raise ValueError("private Write restore target is invalid")
    with connect_read(db_path) as con:
        document = _read_document(con, authority, write_document_id)
        if target_revision >= document.revision or (
            document.origin_kind == "owner_native" and target_revision < 1
        ):
            raise ValueError("private Write restore target is not historical")
        if target_revision == 0:
            target_body, target_sha = "", _sha("")
        else:
            target = _revision_metadata(
                con, authority, write_document_id, target_revision, include_body=True
            )
            target_body, target_sha = str(target.body_html), target.body_sha256
    return edit_private_write(
        db_path, authority, write_document_id=write_document_id,
        mutation_key=mutation_key, base_revision=base_revision,
        base_body_sha256=base_body_sha256, body_html=target_body,
        _operation="restore", _target_revision=target_revision,
        _target_body_sha256=target_sha,
        _lineage_revision=None if target_revision == 0 else target_revision,
    )


__all__ = [
    "EvidenceBundleItem", "EvidenceBundlePreview", "EvidenceInsertionPreview",
    "EvidenceInsertionSource", "NativeWriteCreateDecision", "PrivateWriteDocument",
    "PrivateWriteDocumentSummary", "PrivateWriteRevision",
    "WriteAcceptanceConflict",
    "WriteEditDecision", "WriteReviewDecision", "apply_native_evidence_bundle",
    "apply_native_evidence_insertion",
    "create_native_private_write",
    "edit_private_write",
    "get_private_write_document", "get_private_write_revision",
    "list_private_write_documents",
    "list_private_write_revisions", "preview_native_evidence_bundle",
    "preview_native_evidence_insertion",
    "restore_private_write_revision",
    "review_result", "undo_acceptance",
]
