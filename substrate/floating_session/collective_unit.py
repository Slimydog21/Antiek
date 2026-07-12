"""Owner-native confirmation and descendants for collective research previews."""

from __future__ import annotations

import hashlib
import hmac
import html
import json
from datetime import UTC, datetime
from typing import Any

from substrate.engagement_spine.store import EngagementStore


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(domain: str, value: Any) -> str:
    return hashlib.sha256(f"{domain}\0{_canonical(value)}".encode()).hexdigest()


def collective_preview_material(
    *,
    owner_id: str,
    source_session_ids: list[str],
    query: str | None,
    allow_cross_asset: bool,
    include_twin_preview: bool,
    unit: dict[str, Any],
    prompt_block: str,
) -> dict[str, Any]:
    """Canonical reviewed material; presentation-only HTML is intentionally excluded."""
    return {
        "owner_id": owner_id,
        "source_session_ids": source_session_ids,
        "query": query,
        "allow_cross_asset": allow_cross_asset,
        "include_twin_preview": include_twin_preview,
        "unit": unit,
        "prompt_block": prompt_block,
    }


def collective_preview_sha256(material: dict[str, Any]) -> str:
    return _digest("antiek:collective-preview:v1", material)


def _key_id(domain: str, owner_id: str, key: str) -> str:
    if not 8 <= len(key) <= 128:
        raise ValueError("idempotency_key must contain 8 to 128 characters")
    return f"{domain}_{_digest(f'antiek:{domain}:key:v1', [owner_id, key])[:24]}"


def confirm_collective_unit(
    *,
    store: EngagementStore,
    owner_id: str,
    idempotency_key: str,
    material: dict[str, Any],
    expected_preview_sha256: str,
    rendered_html: str,
) -> dict[str, Any]:
    actual = collective_preview_sha256(material)
    if len(rendered_html.encode("utf-8")) > 4_000_000:
        raise ValueError("collective HTML exceeds durable document cap")
    if not hmac.compare_digest(actual, expected_preview_sha256):
        raise ValueError("collective preview changed")
    unit_id = f"cunit_{actual[:24]}"
    receipt_id = _key_id("collective_confirm", owner_id, idempotency_key)
    request_sha = _digest("antiek:collective-confirm-request:v1", [unit_id, actual])

    def claim(current: dict[str, Any] | None) -> dict[str, Any]:
        if current is not None:
            if not hmac.compare_digest(str(current.get("request_sha256") or ""), request_sha):
                raise ValueError("idempotency key was already used for another collective")
            return current
        return {
            "document_type": "collective_confirmation_receipt",
            "receipt_id": receipt_id,
            "request_sha256": request_sha,
            "collective_unit_id": unit_id,
            "preview_sha256": actual,
            "state": "claimed",
        }

    store.mutate_owned_document(receipt_id, owner_id, claim)
    row = {
        "document_type": "collective_research_unit",
        "collective_unit_id": unit_id,
        "preview_sha256": actual,
        "created_at": datetime.now(UTC).isoformat(),
        "state": "confirmed",
        "material": material,
        "html": rendered_html,
        "view_format": "html",
    }

    def persist(current: dict[str, Any] | None) -> dict[str, Any]:
        if current is None:
            return row
        if current.get("preview_sha256") != actual or current.get("material") != material:
            raise ValueError("collective unit identity conflicts with durable material")
        return current

    durable = store.mutate_owned_document(unit_id, owner_id, persist)

    def settle(current: dict[str, Any] | None) -> dict[str, Any]:
        if current is None or current.get("request_sha256") != request_sha:
            raise ValueError("collective confirmation receipt changed")
        return {**current, "state": "applied"}

    store.mutate_owned_document(receipt_id, owner_id, settle)
    return durable


def get_collective_unit(
    unit_id: str, *, store: EngagementStore, owner_id: str
) -> dict[str, Any] | None:
    if not unit_id.startswith("cunit_"):
        return None
    row = store.get_owned_document(unit_id, owner_id)
    if row is None or row.get("document_type") != "collective_research_unit":
        return None
    return row


def claim_collective_action(
    *,
    store: EngagementStore,
    owner_id: str,
    unit_id: str,
    action: str,
    idempotency_key: str,
    material: dict[str, Any],
) -> dict[str, Any]:
    """Pin descendant intent before its idempotent canonical writer runs."""
    if not 8 <= len(idempotency_key) <= 128:
        raise ValueError("idempotency_key must contain 8 to 128 characters")
    domain = f"collective_{action}"
    receipt_id = (
        f"{domain}_{_digest(f'antiek:{domain}:key:v1', [owner_id, unit_id, idempotency_key])[:24]}"
    )
    material_sha = _digest(f"antiek:collective-{action}:v1", material)

    def claim(current: dict[str, Any] | None) -> dict[str, Any]:
        if current is not None:
            if not hmac.compare_digest(str(current.get("material_sha256") or ""), material_sha):
                raise ValueError(f"{action} idempotency key conflicts with prior intent")
            return current
        return {
            "document_type": "collective_action_receipt",
            "receipt_id": receipt_id,
            "collective_unit_id": unit_id,
            "action": action,
            "material_sha256": material_sha,
            "material": material,
            "state": "claimed",
        }

    return store.mutate_owned_document(receipt_id, owner_id, claim)


def settle_collective_action(
    *,
    store: EngagementStore,
    owner_id: str,
    receipt_id: str,
    material_sha256: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    def settle(current: dict[str, Any] | None) -> dict[str, Any]:
        if current is None or not hmac.compare_digest(
            str(current.get("material_sha256") or ""), material_sha256
        ):
            raise ValueError("collective action receipt changed before settlement")
        if current.get("state") == "applied":
            if current.get("result") != result:
                raise ValueError("collective action result conflicts with applied receipt")
            return current
        return {**current, "state": "applied", "result": result}

    return store.mutate_owned_document(receipt_id, owner_id, settle)


def create_written_analysis(
    *,
    store: EngagementStore,
    owner_id: str,
    unit: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    unit_id = str(unit["collective_unit_id"])
    if not 8 <= len(idempotency_key) <= 128:
        raise ValueError("idempotency_key must contain 8 to 128 characters")
    draft_id = (
        "collective_draft_"
        + _digest("antiek:collective_draft:key:v1", [owner_id, unit_id, idempotency_key])[:24]
    )
    material = dict(unit.get("material") or {})
    source = dict(material.get("unit") or {})
    outputs = list(source.get("research_outputs") or [])
    sections = []
    for output in outputs:
        if not isinstance(output, dict):
            continue
        text = str(output.get("output_text") or "").strip()
        if text:
            sections.append(
                f"<section><h2>Research output — {html.escape(str(output.get('spawn_id') or 'source'))}</h2>"
                f"<p>{html.escape(text).replace(chr(10), '<br />')}</p></section>"
            )
    refs = "".join(
        f"<li>{html.escape(str(ref.get('canonical_url') or ref.get('raw') or ''))}</li>"
        for ref in source.get("source_references") or []
        if isinstance(ref, dict)
    )
    twins = "".join(
        f"<li><strong>{html.escape(str(twin.get('kind') or 'note'))}</strong> — "
        f"{html.escape(str(twin.get('text') or ''))}</li>"
        for twin in source.get("twin_units") or []
        if isinstance(twin, dict)
    )
    rendered = (
        "<article><h1>Collective research analysis draft</h1>"
        f"<p>Source unit: {html.escape(unit_id)}</p>{''.join(sections)}"
        f"<section><h2>Twin insights and questions</h2><ul>{twins}</ul></section>"
        f"<section><h2>Sources</h2><ul>{refs}</ul></section></article>"
    )
    if len(rendered.encode("utf-8")) > 4_000_000:
        raise ValueError("written analysis exceeds durable document cap")
    request_sha = _digest("antiek:collective-draft:v1", [unit_id, unit["preview_sha256"]])
    row = {
        "document_type": "collective_written_analysis",
        "document_id": draft_id,
        "source_collective_id": unit_id,
        "source_preview_sha256": unit["preview_sha256"],
        "source_session_ids": list(material.get("source_session_ids") or []),
        "source_spawn_ids": list(source.get("spawn_ids") or []),
        "source_twin_ids": [
            str(twin.get("unit_id") or "")
            for twin in source.get("twin_units") or []
            if isinstance(twin, dict) and twin.get("unit_id")
        ],
        "request_sha256": request_sha,
        "html": rendered,
        "view_format": "html",
        "state": "draft",
    }

    def persist(current: dict[str, Any] | None) -> dict[str, Any]:
        if current is not None:
            if current.get("request_sha256") != request_sha:
                raise ValueError("written-analysis idempotency conflict")
            return current
        return row

    return store.mutate_owned_document(draft_id, owner_id, persist)
