"""HTML-native book host port (pure, fail-closed).

Operator doctrine: after free-copy or purchase-intent allowance, host the
asset in the operator account as **HTML** (not PDF) for the reading surface.

This module never:
* downloads EPUB/PDF
* converts formats
* invents HTML body bytes
* executes purchase charges

It only decides whether an HTML host receipt may be minted given:
* acquisition path (free_copy | purchase_intent_allowed)
* injected HTML projection readiness (sha256 + optional size)
* account / operator binding

Returns a structured host decision for store/API layers to persist.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

MAX_TITLE = 512
MAX_ASSET_ID = 256
MAX_SHA = 64

AcquisitionPath = Literal["free_copy", "purchase_intent", "unknown"]


class HtmlHostPortError(ValueError):
    """Fail-closed validation for HTML host port."""


@dataclass(frozen=True)
class HtmlHostReceipt:
    host_allowed: bool
    hosted: bool
    acquisition_path: AcquisitionPath
    parent_asset_id: str | None
    title: str
    html_sha256: str | None
    html_bytes: int | None
    view_mode: str
    reasons: tuple[str, ...]
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "host_allowed": self.host_allowed,
            "hosted": False,  # gate never claims durable host complete
            "acquisition_path": self.acquisition_path,
            "parent_asset_id": self.parent_asset_id,
            "title": self.title,
            "html_sha256": self.html_sha256,
            "html_bytes": self.html_bytes,
            "view_mode": self.view_mode,
            "reasons": list(self.reasons),
            "notes": list(self.notes),
            "authority": "html_host_port_advisory",
            "purchase_executed": False,
        }


def _require_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise HtmlHostPortError(f"{field} must be an explicit boolean")
    return value


def _clean_title(value: object) -> str:
    if not isinstance(value, str):
        raise HtmlHostPortError("title must be a string")
    text = value.strip()
    if not text:
        raise HtmlHostPortError("title must be non-empty")
    if len(text) > MAX_TITLE:
        raise HtmlHostPortError(f"title exceeds {MAX_TITLE} chars")
    return text


def _clean_sha(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HtmlHostPortError("html_sha256 must be a string or null")
    text = value.strip().lower()
    if not text:
        return None
    if len(text) != MAX_SHA or any(c not in "0123456789abcdef" for c in text):
        raise HtmlHostPortError("html_sha256 must be 64-char lowercase hex")
    return text


def _clean_asset_id(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HtmlHostPortError("parent_asset_id must be a string or null")
    text = value.strip()
    if not text:
        return None
    if len(text) > MAX_ASSET_ID:
        raise HtmlHostPortError(f"parent_asset_id exceeds {MAX_ASSET_ID} chars")
    return text


def evaluate_html_host_port(
    *,
    title: object,
    free_copy_freely_available: object | None = None,
    purchase_intent_allowed: object | None = None,
    html_projection_ready: object = False,
    html_sha256: object | None = None,
    html_bytes: object | None = None,
    parent_asset_id: object | None = None,
    operator_id: object | None = None,
) -> HtmlHostReceipt:
    """Decide whether HTML host port may proceed (does not persist host)."""
    title_s = _clean_title(title)
    parent = _clean_asset_id(parent_asset_id)
    sha = _clean_sha(html_sha256)
    ready = _require_bool(html_projection_ready, field="html_projection_ready")

    if free_copy_freely_available is not None and not isinstance(
        free_copy_freely_available, bool
    ):
        raise HtmlHostPortError(
            "free_copy_freely_available must be boolean or null"
        )
    if purchase_intent_allowed is not None and not isinstance(
        purchase_intent_allowed, bool
    ):
        raise HtmlHostPortError(
            "purchase_intent_allowed must be boolean or null"
        )

    if operator_id is not None:
        if not isinstance(operator_id, str) or not operator_id.strip():
            raise HtmlHostPortError("operator_id must be non-empty string when set")

    size: int | None
    if html_bytes is None:
        size = None
    elif isinstance(html_bytes, bool) or not isinstance(html_bytes, int):
        raise HtmlHostPortError("html_bytes must be an int or null")
    elif html_bytes < 0:
        raise HtmlHostPortError("html_bytes must be nonnegative")
    else:
        size = html_bytes

    notes: list[str] = [
        "hosted=false — port gate does not claim durable host complete",
        "purchase_executed=false — never executes charges",
        "authority=html_host_port_advisory",
        "view_mode doctrine: HTML-native (not PDF)",
    ]
    reasons: list[str] = []

    # Acquisition path honesty
    free = free_copy_freely_available
    purchase = purchase_intent_allowed
    if free is True:
        path: AcquisitionPath = "free_copy"
        acquisition_ok = True
        notes.append("acquisition via free_copy")
    elif purchase is True:
        path = "purchase_intent"
        acquisition_ok = True
        notes.append("acquisition via purchase_intent_allowed")
    else:
        path = "unknown"
        acquisition_ok = False
        reasons.append(
            "no free_copy hit and purchase_intent_allowed is not true"
        )

    # HTML projection required for host
    if not ready:
        reasons.append("html_projection_ready=false — cannot host non-HTML asset")
    if ready and sha is None:
        reasons.append("html_sha256 required when html_projection_ready=true")
    if ready and size is not None and size == 0:
        reasons.append("html_bytes=0 is not a hostable projection")

    host_allowed = acquisition_ok and ready and sha is not None and (
        size is None or size > 0
    )
    if host_allowed:
        view_mode = "html"
        notes.append("host_allowed=true — store layer may persist HTML asset")
    else:
        view_mode = "unavailable" if not ready else "metadata_only"
        if not reasons:
            reasons.append("host not allowed")

    return HtmlHostReceipt(
        host_allowed=host_allowed,
        hosted=False,
        acquisition_path=path,
        parent_asset_id=parent,
        title=title_s,
        html_sha256=sha if host_allowed else sha,
        html_bytes=size,
        view_mode=view_mode,
        reasons=tuple(reasons) if not host_allowed else (),
        notes=tuple(notes),
        authority="html_host_port_advisory",
    )


def evaluate_html_host_port_from_maps(
    *,
    title: object,
    free_copy_preflight: Mapping[str, Any] | None = None,
    purchase_gate: Mapping[str, Any] | None = None,
    html_projection: Mapping[str, Any] | None = None,
    parent_asset_id: object | None = None,
    operator_id: object | None = None,
) -> HtmlHostReceipt:
    """Convenience: pull fields from free-copy / purchase-gate / projection maps."""
    free: bool | None = None
    if free_copy_preflight is not None:
        if not isinstance(free_copy_preflight, Mapping):
            raise HtmlHostPortError("free_copy_preflight must be an object")
        if "freely_available" not in free_copy_preflight:
            raise HtmlHostPortError(
                "free_copy_preflight.freely_available required when preflight provided"
            )
        fa = free_copy_preflight["freely_available"]
        if not isinstance(fa, bool):
            raise HtmlHostPortError(
                "free_copy_preflight.freely_available must be boolean"
            )
        free = fa

    purchase: bool | None = None
    if purchase_gate is not None:
        if not isinstance(purchase_gate, Mapping):
            raise HtmlHostPortError("purchase_gate must be an object")
        if "purchase_intent_allowed" not in purchase_gate:
            raise HtmlHostPortError(
                "purchase_gate.purchase_intent_allowed required when gate provided"
            )
        pia = purchase_gate["purchase_intent_allowed"]
        if not isinstance(pia, bool):
            raise HtmlHostPortError(
                "purchase_gate.purchase_intent_allowed must be boolean"
            )
        purchase = pia
        if purchase_gate.get("purchase_executed") is True:
            raise HtmlHostPortError(
                "purchase_gate.purchase_executed=true not accepted by host port"
            )

    ready = False
    sha: object | None = None
    nbytes: object | None = None
    if html_projection is not None:
        if not isinstance(html_projection, Mapping):
            raise HtmlHostPortError("html_projection must be an object")
        if "ready" not in html_projection:
            raise HtmlHostPortError("html_projection.ready required")
        ready = _require_bool(html_projection["ready"], field="html_projection.ready")
        sha = html_projection.get("html_sha256")
        nbytes = html_projection.get("html_bytes")

    return evaluate_html_host_port(
        title=title,
        free_copy_freely_available=free,
        purchase_intent_allowed=purchase,
        html_projection_ready=ready,
        html_sha256=sha,
        html_bytes=nbytes,
        parent_asset_id=parent_asset_id,
        operator_id=operator_id,
    )


__all__ = [
    "HtmlHostPortError",
    "HtmlHostReceipt",
    "evaluate_html_host_port",
    "evaluate_html_host_port_from_maps",
]
