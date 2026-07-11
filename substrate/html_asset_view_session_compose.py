"""HTML asset view session compose (pure).

pdf_view_authorized and store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class HtmlAssetViewSessionComposeError(ValueError):
    """Fail-closed validation for HTML asset view session."""


@dataclass(frozen=True)
class HtmlAssetViewSessionCompose:
    session_id: str
    asset_id: str
    html_projection_sha: str | None
    html_view_ready: bool
    twin_ready: bool
    session_ready: bool
    pdf_view_authorized: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "asset_id": self.asset_id,
            "html_projection_sha": self.html_projection_sha,
            "html_view_ready": self.html_view_ready,
            "twin_ready": self.twin_ready,
            "session_ready": self.session_ready,
            "pdf_view_authorized": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": "html_asset_view_session_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HtmlAssetViewSessionComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_html_asset_view_session(
    *,
    session_id: object,
    asset_id: object,
    html_projection_sha: object,
    view_requested: object,
    twin_bound: object,
    twin_substrate_ready: object | None = None,
    claimed_format: object | None = None,
) -> HtmlAssetViewSessionCompose:
    """Compose HTML-native view session. Never authorizes PDF."""
    if not isinstance(view_requested, bool):
        raise HtmlAssetViewSessionComposeError(
            "view_requested must be an explicit boolean"
        )
    if not isinstance(twin_bound, bool):
        raise HtmlAssetViewSessionComposeError(
            "twin_bound must be an explicit boolean"
        )
    sid = _require_nonempty(session_id, field="session_id")
    aid = _require_nonempty(asset_id, field="asset_id")

    notes: list[str] = [
        "pdf_view_authorized=false — HTML-native doctrine for all assets",
        "store_mutated=false — view session is advisory readiness only",
    ]

    is_pdf_claim = False
    if claimed_format is not None:
        fmt = _require_nonempty(claimed_format, field="claimed_format").lower()
        if fmt in ("pdf", "application/pdf"):
            is_pdf_claim = True
            notes.append(
                "claimed_format=pdf — hard deny PDF view; require HTML projection first"
            )
        else:
            notes.append(f"claimed_format={fmt}")

    sha: str | None = None
    if html_projection_sha is not None:
        sha = _require_nonempty(
            html_projection_sha, field="html_projection_sha"
        )

    html_view_ready = (
        view_requested is True and sha is not None and not is_pdf_claim
    )
    if not view_requested:
        notes.append("html_view_ready=false — view_requested=false")
    elif is_pdf_claim:
        notes.append(
            "html_view_ready=false — PDF claim blocked until HTML projection"
        )
    elif sha is None:
        notes.append(
            "html_view_ready=false — html_projection_sha absent (no invent projection)"
        )
    else:
        notes.append("html_view_ready=true — ready HTML projection present")

    twin_substrate = False if twin_substrate_ready is None else twin_substrate_ready
    if not isinstance(twin_substrate, bool):
        raise HtmlAssetViewSessionComposeError(
            "twin_substrate_ready must be boolean when set"
        )
    twin_ready = twin_bound or twin_substrate
    notes.append(
        f"twin_ready=true · bound={twin_bound} · substrate={twin_substrate}"
        if twin_ready
        else "twin_ready=false — twin not bound and no substrate signal"
    )

    session_ready = html_view_ready
    notes.append(
        "session_ready=true — open as HTML-native view"
        if session_ready
        else "session_ready=false — need ready HTML projection + view_requested"
    )
    notes.extend(("pdf_view_authorized=false", "store_mutated=false"))

    return HtmlAssetViewSessionCompose(
        session_id=sid,
        asset_id=aid,
        html_projection_sha=sha,
        html_view_ready=html_view_ready,
        twin_ready=twin_ready,
        session_ready=session_ready,
        pdf_view_authorized=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="html_asset_view_session_compose_advisory",
    )


__all__ = [
    "HtmlAssetViewSessionCompose",
    "HtmlAssetViewSessionComposeError",
    "compose_html_asset_view_session",
]
