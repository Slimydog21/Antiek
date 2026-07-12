"""Owner-scoped idempotency receipts for confirmed twin graph promotion."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any

from .store import EngagementStore

_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


def _sha256(domain: bytes, value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(domain + b"\0" + encoded).hexdigest()


def promotion_preview_sha256(
    *, owner_id: str, session_id: str, payload: dict[str, Any]
) -> str:
    """Pin exactly the owner/session twin units shown before confirmation."""
    promoted = [
        {
            "twin_note_id": row.get("twin_note_id"),
            "graph_node_id": row.get("graph_node_id"),
            "kind": row.get("kind"),
            "text": row.get("text"),
            "canonical_text": row.get("canonical_text"),
            "asset_id": row.get("asset_id"),
            "investigation_id": row.get("investigation_id"),
        }
        for row in payload.get("promoted", [])
        if isinstance(row, dict)
    ]
    return _sha256(
        b"antiek.twin-promotion.preview.v1",
        {"owner_id": owner_id, "session_id": session_id, "promoted": promoted},
    )


def promotion_material_sha256(material: dict[str, Any]) -> str:
    return _sha256(b"antiek.twin-promotion.material.v1", material)


def promotion_result_sha256(result: dict[str, Any]) -> str:
    return _sha256(b"antiek.twin-promotion.result.v1", result)


def promotion_receipt_id(owner_id: str, idempotency_key: str) -> str:
    if _KEY.fullmatch(idempotency_key) is None:
        raise ValueError("invalid twin promotion idempotency key")
    digest = hashlib.sha256(
        f"antiek.twin-promotion.receipt.v1\0{owner_id}\0{idempotency_key}".encode()
    ).hexdigest()[:24]
    return f"tpr_{digest}"


def claim_promotion_receipt(
    *,
    store: EngagementStore,
    owner_id: str,
    idempotency_key: str,
    material: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    receipt_id = promotion_receipt_id(owner_id, idempotency_key)
    material_sha = promotion_material_sha256(material)
    created = False

    def claim(current: dict[str, Any] | None) -> dict[str, Any]:
        nonlocal created
        if current is not None:
            if current.get("receipt_id") != receipt_id or not hmac.compare_digest(
                str(current.get("material_sha256") or ""), material_sha
            ):
                raise ValueError(
                    "idempotency key was already used for different twin promotion material"
                )
            return current
        created = True
        return {
            "document_id": receipt_id,
            "receipt_id": receipt_id,
            "state": "claimed",
            "material_sha256": material_sha,
            "material": material,
        }

    return store.mutate_owned_document(receipt_id, owner_id, claim), created


def settle_promotion_receipt(
    *,
    store: EngagementStore,
    owner_id: str,
    receipt_id: str,
    material_sha256: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    result_sha = promotion_result_sha256(result)

    def settle(current: dict[str, Any] | None) -> dict[str, Any]:
        if current is None or current.get("receipt_id") != receipt_id:
            raise KeyError(receipt_id)
        if not hmac.compare_digest(
            str(current.get("material_sha256") or ""), material_sha256
        ):
            raise ValueError("twin promotion receipt material changed before settlement")
        if current.get("state") == "applied":
            if not hmac.compare_digest(
                str(current.get("result_sha256") or ""), result_sha
            ):
                raise ValueError("twin promotion replay result conflicts with receipt")
            return current
        if current.get("state") != "claimed":
            raise ValueError("twin promotion receipt has an invalid state")
        return {
            **current,
            "state": "applied",
            "result_sha256": result_sha,
            "result": result,
        }

    return store.mutate_owned_document(receipt_id, owner_id, settle)

