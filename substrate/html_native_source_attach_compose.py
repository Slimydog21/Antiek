"""HTML-native source attach compose (pure).

Attach arxiv/substack/etc HTML source refs to a research session.
remote_fetched, pdf_view_authorized, store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.source_publication_registry import (
    DEFAULT_PUBLICATION_CATALOG,
    PublicationFamily,
    SourceSelectionPack,
    select_publication_sources,
)

VALID_FAMILIES: frozenset[str] = frozenset(
    ("arxiv", "substack", "openalex", "web", "custom")
)


class HtmlNativeSourceAttachComposeError(ValueError):
    """Fail-closed validation for HTML-native source attach."""


@dataclass(frozen=True)
class HtmlNativeSourceAttachCompose:
    session_id: str
    parent_asset_id: str
    selection: SourceSelectionPack
    source_ids: tuple[str, ...]
    source_count: int
    html_ready_count: int
    attach_ready: bool
    remote_fetched: bool
    pdf_view_authorized: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "selection": self.selection.to_dict(),
            "source_ids": list(self.source_ids),
            "source_count": self.source_count,
            "html_ready_count": self.html_ready_count,
            "attach_ready": self.attach_ready,
            "remote_fetched": False,
            "pdf_view_authorized": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": "html_native_source_attach_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HtmlNativeSourceAttachComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_html_native_source_attach(
    *,
    session_id: object,
    parent_asset_id: object,
    requested_families: object,
    sources: object,
    operator_ack: object,
) -> HtmlNativeSourceAttachCompose:
    """Attach HTML-native sources. Never remote-fetches; never PDF; never mutates store."""
    if not isinstance(operator_ack, bool):
        raise HtmlNativeSourceAttachComposeError(
            "operator_ack must be an explicit boolean"
        )
    sid = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    if not isinstance(requested_families, list) or len(requested_families) == 0:
        raise HtmlNativeSourceAttachComposeError(
            "requested_families must be a non-empty array"
        )
    if not isinstance(sources, list):
        raise HtmlNativeSourceAttachComposeError("sources must be an array")

    notes: list[str] = [
        "remote_fetched=false — no live arxiv/substack fetch in pure layer",
        "pdf_view_authorized=false — HTML-native doctrine",
        "store_mutated=false — attach is advisory pack only",
    ]

    for f in requested_families:
        if f not in VALID_FAMILIES:
            raise HtmlNativeSourceAttachComposeError(
                f"requested_families contains invalid family: {f}"
            )

    selection = select_publication_sources(
        requested_families=requested_families,
        enabled_only=True,
        catalog=DEFAULT_PUBLICATION_CATALOG,
    )
    notes.append(f"selection families={len(selection.families)}")

    source_ids: list[str] = []
    seen: set[str] = set()
    html_ready_count = 0
    req_set = set(requested_families)

    for i, s in enumerate(sources):
        if not isinstance(s, dict):
            raise HtmlNativeSourceAttachComposeError(
                f"sources[{i}] must be an object"
            )
        sid_s = _require_nonempty(s.get("source_id"), field=f"sources[{i}].source_id")
        if sid_s in seen:
            raise HtmlNativeSourceAttachComposeError(f"duplicate source_id: {sid_s}")
        seen.add(sid_s)
        fam = s.get("family")
        if fam not in VALID_FAMILIES:
            raise HtmlNativeSourceAttachComposeError(
                f"sources[{i}].family invalid"
            )
        if fam not in req_set:
            raise HtmlNativeSourceAttachComposeError(
                f"sources[{i}].family {fam} not in requested_families"
            )
        _require_nonempty(s.get("title"), field=f"sources[{i}].title")
        if s.get("external_id") is not None:
            _require_nonempty(
                s.get("external_id"), field=f"sources[{i}].external_id"
            )
        if s.get("url") is not None:
            _require_nonempty(s.get("url"), field=f"sources[{i}].url")
        frag = s.get("html_fragment")
        if frag is not None:
            if not isinstance(frag, str) or not frag.strip():
                raise HtmlNativeSourceAttachComposeError(
                    f"sources[{i}].html_fragment must be non-empty string when set"
                )
            html_ready_count += 1
        source_ids.append(sid_s)

    source_count = len(source_ids)
    notes.append(
        f"source_count={source_count} · html_ready_count={html_ready_count}"
    )

    attach_ready = (
        operator_ack and source_count >= 1 and len(requested_families) >= 1
    )
    if not operator_ack:
        notes.append("attach_ready=false — operator_ack required")
    elif source_count == 0:
        notes.append("attach_ready=false — no sources (no invent)")
    else:
        notes.append(
            "attach_ready=true · all sources have HTML fragments"
            if html_ready_count == source_count
            else f"attach_ready=true · {html_ready_count}/{source_count} sources have HTML (rest proposed without body)"
        )

    notes.extend(
        (
            "remote_fetched=false",
            "pdf_view_authorized=false",
            "store_mutated=false",
        )
    )

    return HtmlNativeSourceAttachCompose(
        session_id=sid,
        parent_asset_id=parent,
        selection=selection,
        source_ids=tuple(source_ids),
        source_count=source_count,
        html_ready_count=html_ready_count,
        attach_ready=attach_ready,
        remote_fetched=False,
        pdf_view_authorized=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="html_native_source_attach_compose_advisory",
    )


def format_html_native_source_attach_summary(
    c: HtmlNativeSourceAttachCompose,
) -> str:
    return (
        f"attach_ready={c.attach_ready} · sources={c.source_count} · "
        f"html_ready={c.html_ready_count} · remote_fetched=false · "
        f"pdf_view_authorized=false"
    )


__all__ = [
    "HtmlNativeSourceAttachCompose",
    "HtmlNativeSourceAttachComposeError",
    "compose_html_native_source_attach",
    "format_html_native_source_attach_summary",
]
