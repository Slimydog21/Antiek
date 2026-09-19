"""Closed, account-authorized resolvers for resumable HTML windows."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from typing import Literal

from fastapi import Request

from substrate.engagement_spine.authority import EngagementAuthority
from substrate.engagement_spine.store import (
    AuthorizedEngagementStore,
    EngagementStore,
    InMemoryEngagementStore,
    authorized_store,
)
from substrate.marketplace_host.library import HostStore, InMemoryHostStore

HtmlDocumentResolver = Literal["hosted_document", "engagement_document"]
HTML_DOCUMENT_RESOLVERS: frozenset[str] = frozenset(
    {"hosted_document", "engagement_document"}
)


class HtmlDocumentReferenceNotFound(LookupError):
    """The reference is malformed, unsupported, or denied by current authority."""


class HtmlDocumentReferenceUnavailable(RuntimeError):
    """The configured canonical store cannot currently answer safely."""


@dataclass(frozen=True)
class HydratedHtmlDocument:
    resolver: HtmlDocumentResolver
    document_id: str
    title: str
    html: str


def validate_html_document_identifier(value: object) -> str:
    """Validate the exact UTF-8 identifier contract shared by both resolvers."""

    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > 512
        or any(unicodedata.category(character) == "Cc" for character in value)
    ):
        raise ValueError("HTML document identifier is invalid")
    return value


def validate_html_document_resolver(value: object) -> HtmlDocumentResolver:
    if value not in HTML_DOCUMENT_RESOLVERS:
        raise ValueError("HTML document resolver is invalid")
    return value  # type: ignore[return-value]


def _host_store(request: Request) -> HostStore:
    try:
        from .marketplace_host_routes import get_marketplace_host_store

        store = get_marketplace_host_store(request)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise HtmlDocumentReferenceUnavailable from exc
    if not isinstance(store, HostStore):
        raise HtmlDocumentReferenceUnavailable
    return store


def _engagement_store(request: Request) -> EngagementStore:
    missing = object()
    configured = getattr(request.app.state, "engagement_store", missing)
    if configured is missing:
        try:
            from .engagement_routes import get_engagement_store

            configured = get_engagement_store()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise HtmlDocumentReferenceUnavailable from exc
    if not isinstance(configured, EngagementStore):
        raise HtmlDocumentReferenceUnavailable
    return configured


def _operator_owner_aliases(account_id: str) -> frozenset[str]:
    if account_id == "__operator__":
        return frozenset({"__operator__", "operator"})
    return frozenset({account_id})


def _read_host_document(store: HostStore, document_id: str) -> dict[str, object] | None:
    try:
        strict = getattr(store, "get_document_strict", None)
        row = strict(document_id) if callable(strict) else store.get_document(document_id)
    except Exception as exc:
        raise HtmlDocumentReferenceUnavailable from exc
    if row is not None and not isinstance(row, dict):
        raise HtmlDocumentReferenceUnavailable
    return row


def _has_host_membership(
    store: HostStore, aliases: frozenset[str], document_id: str
) -> bool:
    try:
        strict = getattr(store, "list_membership_strict", None)
        for alias in aliases:
            membership = (
                strict(alias) if callable(strict) else store.list_membership(alias)
            )
            if not isinstance(membership, list) or not all(
                isinstance(item, str) for item in membership
            ):
                raise HtmlDocumentReferenceUnavailable
            if document_id in membership:
                return True
        return False
    except Exception as exc:
        raise HtmlDocumentReferenceUnavailable from exc


def _resolve_hosted_document(
    request: Request, account_id: str, document_id: str
) -> HydratedHtmlDocument:
    from substrate.marketplace_host import project_hosted_book_html

    store = _host_store(request)
    try:
        row = _read_host_document(store, document_id)
        if row is None:
            raise HtmlDocumentReferenceNotFound
        owner = row.get("owner_id")
        aliases = _operator_owner_aliases(account_id)
        if (
            not isinstance(owner, str)
            or owner not in aliases
            or row.get("document_id") != document_id
            or row.get("state") != "ready"
            or row.get("view_format") != "html"
        ):
            raise HtmlDocumentReferenceNotFound
        if not _has_host_membership(store, aliases, document_id):
            raise HtmlDocumentReferenceNotFound
        snapshot = deepcopy(row)
        title = snapshot.get("title")
        if not isinstance(title, str) or not title.strip():
            raise HtmlDocumentReferenceNotFound
        snapshot_store = InMemoryHostStore()
        snapshot_store.put_document(document_id, snapshot)
        html = project_hosted_book_html(document_id, store=snapshot_store)
        current = _read_host_document(store, document_id)
        if current != snapshot or not _has_host_membership(store, aliases, document_id):
            raise HtmlDocumentReferenceNotFound
    except HtmlDocumentReferenceNotFound:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise HtmlDocumentReferenceNotFound from exc
    except (OSError, RuntimeError) as exc:
        raise HtmlDocumentReferenceUnavailable from exc
    if not html.strip() or html.lstrip().lower().startswith("%pdf"):
        raise HtmlDocumentReferenceNotFound
    return HydratedHtmlDocument("hosted_document", document_id, title.strip(), html)


_AUTHORITY_ROW_FIELDS = frozenset(
    {
        "engagement_authority_version",
        "owner_account_digest",
        "engagement_key_id",
        "display_document_id",
    }
)
_DOC_MODEL_ROW_FIELDS = frozenset(
    {
        "document_id",
        "parent_asset_id",
        "title",
        "body_text",
        "mode",
        "source_spawn_ids",
        "doc_model",
        "draft_sha256",
    }
)
_DOC_MODEL_MODES = frozenset({"draft_combined", "into_parent", "midnight_oil_deposit"})
_PROGRESS_ROW_FIELDS = frozenset(
    {"document_id", "spawn_id", "events", "latest_stage", "view_format", "mode"}
)
_PROGRESS_EVENT_FIELDS = frozenset({"spawn_id", "stage", "message", "ts", "sequence"})
_PROGRESS_STAGES = frozenset({"plan", "gather", "synthesize", "cite", "complete", "failed"})


def _doc_model_html(row: dict[str, object], document_id: str) -> tuple[str, str] | None:
    from services.html_projection.contract import known_tiptap_types
    from substrate.engagement_spine.project import project_to_html

    if set(row) != _DOC_MODEL_ROW_FIELDS | _AUTHORITY_ROW_FIELDS:
        return None
    title = row.get("title")
    parent_asset_id = row.get("parent_asset_id")
    body_text = row.get("body_text")
    source_spawn_ids = row.get("source_spawn_ids")
    doc_model = row.get("doc_model")
    draft_sha256 = row.get("draft_sha256")
    model_keys = set(doc_model) if isinstance(doc_model, dict) else set()
    canonical_model = bool(
        isinstance(doc_model, dict)
        and doc_model.get("type") == "doc"
        and model_keys.issubset({"type", "content", "title", "edges"})
    )
    merge_meta = doc_model.get("meta") if isinstance(doc_model, dict) else None
    merge_model = bool(
        isinstance(doc_model, dict)
        and model_keys == {"title", "content", "edges", "meta"}
        and isinstance(doc_model.get("title"), str)
        and isinstance(merge_meta, dict)
        and set(merge_meta) == {"parent_asset_id", "merge_mode", "spawn_ids"}
        and merge_meta.get("parent_asset_id") == parent_asset_id
        and merge_meta.get("merge_mode") == row.get("mode")
        and merge_meta.get("spawn_ids") == source_spawn_ids
    )
    if (
        row.get("document_id") != document_id
        or row.get("display_document_id") != document_id
        or row.get("mode") not in _DOC_MODEL_MODES
        or not isinstance(title, str)
        or not title.strip()
        or not isinstance(parent_asset_id, str)
        or not parent_asset_id.strip()
        or not isinstance(body_text, str)
        or not isinstance(source_spawn_ids, list)
        or not all(isinstance(item, str) and item for item in source_spawn_ids)
        or not isinstance(doc_model, dict)
        or not (canonical_model or merge_model)
        or not isinstance(doc_model.get("content"), list)
        or not doc_model["content"]
        or not isinstance(draft_sha256, str)
        or len(draft_sha256) != 64
    ):
        return None
    supported_types = known_tiptap_types() | {"heading"}
    if any(
        not isinstance(node, dict)
        or not isinstance(node.get("type"), str)
        or node.get("type") not in supported_types
        for node in doc_model["content"]
    ):
        return None
    if "title" in doc_model and not isinstance(doc_model["title"], str):
        return None
    edges = doc_model.get("edges", [])
    if not isinstance(edges, list) or any(not isinstance(edge, dict) for edge in edges):
        return None
    digest = hashlib.sha256(
        json.dumps(
            doc_model,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    if not hmac.compare_digest(draft_sha256, digest):
        return None
    try:
        html = project_to_html(
            doc_model,
            document_id=document_id,
            creator="engagement_spine.reference_hydration",
        )
    except (RuntimeError, TypeError, ValueError):
        return None
    if not html.strip() or html.lstrip().lower().startswith("%pdf"):
        return None
    return title.strip(), html


def _progress_html(
    row: dict[str, object], document_id: str, store: EngagementStore
) -> tuple[str, str] | None:
    from substrate.engagement_spine.progress import progress_payload, project_progress_html

    if set(row) != _PROGRESS_ROW_FIELDS | _AUTHORITY_ROW_FIELDS:
        return None
    spawn_id = row.get("spawn_id")
    events = row.get("events")
    if (
        not isinstance(spawn_id, str)
        or not spawn_id
        or document_id != f"_progress:{spawn_id}"
        or row.get("document_id") != document_id
        or row.get("display_document_id") != document_id
        or row.get("view_format") != "html"
        or row.get("mode") != "research_progress"
        or not isinstance(events, list)
        or not events
        or store.get_spawn(spawn_id) is None
    ):
        return None
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or set(event) != _PROGRESS_EVENT_FIELDS:
            return None
        timestamp = event.get("ts")
        if (
            event.get("spawn_id") != spawn_id
            or event.get("stage") not in _PROGRESS_STAGES
            or not isinstance(event.get("message"), str)
            or isinstance(timestamp, bool)
            or not isinstance(timestamp, int | float)
            or not math.isfinite(timestamp)
            or event.get("sequence") != sequence
        ):
            return None
    if row.get("latest_stage") != events[-1]["stage"]:
        return None
    payload = progress_payload(spawn_id, store=store, include_html=False)
    html = project_progress_html(payload)
    if not html.strip() or html.lstrip().lower().startswith("%pdf"):
        return None
    return "Deep research progress", html


def _progress_snapshot_store(
    store: AuthorizedEngagementStore,
    *,
    document_id: str,
    row: dict[str, object],
) -> tuple[AuthorizedEngagementStore, dict[str, object]] | None:
    spawn_id = row.get("spawn_id")
    if not isinstance(spawn_id, str):
        return None
    spawn = store.get_spawn_strict(spawn_id)
    if spawn is None:
        return None
    base = InMemoryEngagementStore()
    snapshot = authorized_store(base, store.authority)
    snapshot.put_spawn(deepcopy(spawn))
    snapshot.put_document(document_id, deepcopy(row))
    return snapshot, deepcopy(spawn)


def _resolve_engagement_document(
    request: Request, account_id: str, document_id: str
) -> HydratedHtmlDocument:
    try:
        store = authorized_store(_engagement_store(request), EngagementAuthority(account_id))
        current_row = store.get_document_strict(document_id)
    except PermissionError as exc:
        raise HtmlDocumentReferenceNotFound from exc
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise HtmlDocumentReferenceUnavailable from exc
    if current_row is None:
        raise HtmlDocumentReferenceNotFound
    row = deepcopy(current_row)
    progress_spawn: tuple[str, dict[str, object]] | None = None
    try:
        projected = _doc_model_html(row, document_id)
        if projected is None:
            progress_snapshot = _progress_snapshot_store(
                store,
                document_id=document_id,
                row=row,
            )
            if progress_snapshot is not None:
                snapshot_store, spawn = progress_snapshot
                projected = _progress_html(row, document_id, snapshot_store)
                spawn_id = row.get("spawn_id")
                if not isinstance(spawn_id, str):
                    projected = None
                else:
                    progress_spawn = (spawn_id, spawn)
        if store.get_document_strict(document_id) != row:
            projected = None
        if progress_spawn is not None:
            spawn_id, spawn = progress_spawn
            if store.get_spawn_strict(spawn_id) != spawn:
                projected = None
    except (AttributeError, KeyError, TypeError, ValueError):
        projected = None
    except (OSError, RuntimeError) as exc:
        raise HtmlDocumentReferenceUnavailable from exc
    if projected is None:
        raise HtmlDocumentReferenceNotFound
    title, html = projected
    return HydratedHtmlDocument("engagement_document", document_id, title, html)


def resolve_html_document_reference(
    request: Request,
    *,
    account_id: str,
    resolver: object,
    document_id: object,
) -> HydratedHtmlDocument:
    """Resolve one exact reference under claims-derived current account authority."""

    try:
        checked_resolver = validate_html_document_resolver(resolver)
        checked_document_id = validate_html_document_identifier(document_id)
    except ValueError as exc:
        raise HtmlDocumentReferenceNotFound from exc
    if checked_resolver == "hosted_document":
        return _resolve_hosted_document(request, account_id, checked_document_id)
    return _resolve_engagement_document(request, account_id, checked_document_id)


__all__ = [
    "HTML_DOCUMENT_RESOLVERS",
    "HtmlDocumentReferenceNotFound",
    "HtmlDocumentReferenceUnavailable",
    "HtmlDocumentResolver",
    "HydratedHtmlDocument",
    "resolve_html_document_reference",
    "validate_html_document_identifier",
    "validate_html_document_resolver",
]
