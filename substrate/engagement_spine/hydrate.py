"""Hydrate arxiv/substack/url references into HTML-first information assets.

Product path for competitive residual (aq): operators attach knowledge-dense
publication handles and want a **human-viewable HTML asset** in the engagement
library — not a PDF-required view.

Network is **injectable**. Default path is offline-safe: builds a minimal
honest asset from the parsed identity (title/id/url) with a note that full
body was not fetched. Callers may inject ``fetch_publication`` to land
abstracts or article bodies without this module owning arxiv/substack clients.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from .project import project_to_html
from .source_refs import SourceReference, parse_source_reference
from .store import EngagementStore

PublicationKind = Literal["arxiv", "substack", "url", "unknown"]
HydrationStatus = Literal[
    "identity_only",
    "metadata_only",
    "abstract_only",
    "body_complete",
    "body_unavailable",
]

# (ref) -> dict with optional title, body_text/body_markdown, canonical_url, abstract
FetchPublication = Callable[[SourceReference], dict[str, Any]]
_CANONICAL_BODY_TOKEN = object()


def mark_canonical_body_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Mark a payload produced by the canonical host/extraction boundary.

    This process-local capability is intentionally not serializable and is
    removed before persistence. Arbitrary publication adapters cannot promote
    their own prose to ``body_complete`` merely by copying receipt fields.
    """
    return {**payload, "_canonical_body_token": _CANONICAL_BODY_TOKEN}


@dataclass(frozen=True)
class HydratedAsset:
    asset_id: str
    ref: SourceReference
    title: str
    body_text: str
    fetched: bool
    view_format: str
    html: str | None
    notes: tuple[str, ...]
    twins: dict[str, Any] | None = None
    # Residual (gz): true when identity-only (no live body) — competitive aq honesty.
    offline_honest: bool = True
    hydration_status: HydrationStatus = "identity_only"
    hydration_receipt: dict[str, Any] | None = None

    @property
    def hydrated(self) -> bool:
        """True only when a genuine, extracted publication body is servable."""
        return self.hydration_status == "body_complete"

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "asset_id": self.asset_id,
            "ref": self.ref.to_dict(),
            "title": self.title,
            "body_text": self.body_text,
            "fetched": self.fetched,
            "hydrated": self.hydrated,
            "hydration_status": self.hydration_status,
            "offline_honest": self.offline_honest,
            "view_format": self.view_format,
            "html": self.html,
            "notes": list(self.notes),
            "product_panel": "engagement_hydrate",
            "source": "engagement_spine.hydrate",
        }
        if self.twins is not None:
            out["twins"] = self.twins
        if self.hydration_receipt is not None:
            out["hydration_receipt"] = self.hydration_receipt
        return out


def asset_id_for_ref(ref: SourceReference) -> str:
    """Stable asset id from kind + external_id/canonical/raw (content-addressed)."""
    identity = ref.external_id or ref.canonical_url or ref.raw
    digest = hashlib.sha256(f"hydrate:v1:{ref.kind}:{identity}".encode()).hexdigest()[:12]
    return f"pub_{ref.kind}_{digest}"


def hydrate_reference(
    raw: str,
    *,
    store: EngagementStore,
    fetch_publication: FetchPublication | None = None,
    include_html: bool = True,
    attach_spawn_id: str | None = None,
    seed_twins: bool = True,
) -> HydratedAsset:
    """Parse a publication handle and land an HTML-first asset in the store.

    * With ``fetch_publication``: body/title come from the injector (tests or
      acquisition adapters).
    * Without: honest identity-only asset (no fabricated paper abstract).
    * ``seed_twins`` (default True): offline recursive note-taker seed
      (insight + question) via ``seed_twins_for_asset`` — residual (bu).
    """
    ref = parse_source_reference(raw)
    asset_id = asset_id_for_ref(ref)
    notes: list[str] = []
    fetched = False
    hydration_status: HydrationStatus = "identity_only"
    hydration_receipt: dict[str, Any] | None = None
    identity = ref.external_id or ref.canonical_url or ref.raw
    title = ref.title_hint or f"{ref.kind}: {identity}"
    body = f"Publication reference ({ref.kind}).\nIdentity: {identity}\nRaw: {ref.raw}\n"
    if ref.canonical_url:
        body += f"URL: {ref.canonical_url}\n"

    if fetch_publication is not None:
        try:
            remote = fetch_publication(ref) or {}
        except Exception as exc:  # honest failure — still land identity asset
            notes.append(f"fetch_publication failed: {exc}")
            remote = {}
        else:
            if remote:
                claimed_status = str(remote.get("hydration_status") or "metadata_only")
                if claimed_status not in {
                    "metadata_only",
                    "abstract_only",
                    "body_complete",
                    "body_unavailable",
                }:
                    claimed_status = "metadata_only"
                if remote.get("title"):
                    title = str(remote["title"]).strip() or title
                body_remote = (
                    remote.get("body_text")
                    or remote.get("body_markdown")
                    or remote.get("abstract")
                    or ""
                )
                if body_remote:
                    body = str(body_remote).strip()
                # A transport response, metadata record, or abstract is not a
                # hydrated publication.  Only an explicitly classified body
                # with non-empty extracted text may cross this boundary.
                receipt = remote.get("hydration_receipt")
                verified_receipt = (
                    remote.get("_canonical_body_token") is _CANONICAL_BODY_TOKEN
                    and isinstance(receipt, dict)
                    and receipt.get("verified_body") is True
                    and bool(receipt.get("canonical_hosted_document_id"))
                    and bool(receipt.get("source_sha256"))
                    and bool(receipt.get("canonical_content_hash"))
                    and receipt.get("owner_bound") is True
                    and receipt.get("view_format") == "html"
                )
                if (
                    claimed_status == "body_complete"
                    and str(body_remote).strip()
                    and verified_receipt
                ):
                    hydration_status = "body_complete"
                    fetched = True
                else:
                    hydration_status = (
                        "body_unavailable" if claimed_status == "body_complete" else claimed_status
                    )  # type: ignore[assignment]
                if isinstance(receipt, dict):
                    hydration_receipt = dict(receipt)
                if remote.get("canonical_url") and not ref.canonical_url:
                    # keep body note of remote url
                    body = body + f"\n\nSource: {remote.get('canonical_url')}"
                notes.append("Publication injector returned " + hydration_status + ".")
    else:
        notes.append(
            "No fetch_publication injector — identity-only HTML asset "
            "(offline-safe). Inject acquisition adapters for abstracts/full text."
        )

    if ref.kind not in ("arxiv", "substack", "url"):
        notes.append(f"Kind {ref.kind!r} is low-confidence; treat as url-like.")

    html: str | None = None
    if include_html:
        html = project_hydrated_html(
            title=title,
            body_text=body,
            ref=ref,
            asset_id=asset_id,
            fetched=fetched,
        )

    offline_honest = not fetched
    store.put_document(
        asset_id,
        {
            "document_id": asset_id,
            "title": title,
            "body_text": body,
            "view_format": "html",
            "source_ref": ref.to_dict(),
            "fetched": fetched,
            "hydrated": hydration_status == "body_complete",
            "hydration_status": hydration_status,
            "hydration_receipt": hydration_receipt,
            # Residual (gz): identity-only path is offline-honest (no invented abstract).
            "offline_honest": offline_honest,
            "mode": "publication_hydrate",
            "html": html,
        },
    )

    if attach_spawn_id:
        from .source_refs import attach_source_references

        try:
            attach_source_references(attach_spawn_id, [raw], store=store)
            notes.append(f"Attached reference to spawn {attach_spawn_id}.")
        except Exception as exc:
            notes.append(f"attach to spawn failed: {exc}")

    twins_payload: dict[str, Any] | None = None
    if seed_twins:
        from .twin import seed_twins_for_asset

        try:
            twins_payload = seed_twins_for_asset(
                asset_id,
                store=store,
                title=title,
                body_text=body,
                source_spawn_id=attach_spawn_id,
                include_html=include_html,
                source_provenance=hydration_receipt,
            )
            if twins_payload.get("seeded"):
                notes.append(
                    "Seeded offline twin notes (insight + question) — recursive note-taker."
                )
            else:
                notes.append(f"Twin seed skipped: {twins_payload.get('seed_skipped')}")
        except Exception as exc:
            notes.append(f"twin seed failed: {exc}")

    return HydratedAsset(
        asset_id=asset_id,
        ref=ref,
        title=title,
        body_text=body,
        fetched=fetched,
        view_format="html",
        html=html,
        notes=tuple(notes),
        twins=twins_payload,
        offline_honest=offline_honest,
        hydration_status=hydration_status,
        hydration_receipt=hydration_receipt,
    )


def project_hydrated_html(
    *,
    title: str,
    body_text: str,
    ref: SourceReference,
    asset_id: str,
    fetched: bool,
) -> str:
    """HTML-first human view of a hydrated publication asset (never PDF)."""
    honesty = (
        "offline-honest identity (no live body)" if not fetched else "body landed via injector"
    )
    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": title}],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Asset {asset_id} · kind={ref.kind} · "
                        f"fetched={fetched} · {honesty} · "
                        f"view: HTML (not PDF)"
                    ),
                }
            ],
        },
    ]
    if ref.canonical_url:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": f"Canonical: {ref.canonical_url}"}],
            }
        )
    for para in body_text.split("\n\n"):
        text = para.strip()
        if not text:
            continue
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        )
    html = project_to_html(
        {"type": "doc", "content": blocks},
        document_id=asset_id,
        creator="engagement_spine.hydrate",
    )
    if html.lstrip().lower().startswith("%pdf"):
        raise RuntimeError("PDF is not a valid hydrate view surface")
    return html
