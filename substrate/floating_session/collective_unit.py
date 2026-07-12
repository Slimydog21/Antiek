"""Owner-native confirmation and descendants for collective research previews."""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import re
from datetime import UTC, datetime
from typing import Any

from substrate.engagement_spine.store import EngagementStore

_UNIT_ID = re.compile(r"^cunit_[0-9a-f]{24}$")
_SESSION_ID = re.compile(r"^fsess_[0-9a-f]{16}$")
_DRAFT_ID = re.compile(r"^collective_draft_[0-9a-f]{24}$")


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
    if _UNIT_ID.fullmatch(unit_id) is None:
        return None
    row = store.get_owned_document(unit_id, owner_id)
    if (
        row is None
        or row.get("document_type") != "collective_research_unit"
        or row.get("collective_unit_id") != unit_id
    ):
        return None
    _validate_collective_unit_row(row, owner_id)
    return row


def _lineage_id(unit_id: str) -> str:
    if _UNIT_ID.fullmatch(unit_id) is None:
        raise ValueError("collective unit identity is outside the canonical contract")
    return f"collective_lineage_{unit_id}"


def append_collective_lineage(
    *,
    store: EngagementStore,
    owner_id: str,
    unit: dict[str, Any],
    child_kind: str,
    child_id: str,
    initial_state: str,
    created_at: str,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Append a derived edge without mutating the immutable collective unit."""
    if child_kind not in {"research_session", "written_analysis"}:
        raise ValueError("collective lineage child kind is outside the contract")
    if (child_kind == "research_session" and _SESSION_ID.fullmatch(child_id) is None) or (
        child_kind == "written_analysis" and _DRAFT_ID.fullmatch(child_id) is None
    ):
        raise ValueError("collective lineage child identity is outside the contract")
    unit_id = str(unit.get("collective_unit_id") or "")
    lineage_id = _lineage_id(unit_id)
    edge_id = f"cedge_{_digest('antiek:collective-lineage-edge:v1', [unit_id, child_kind, child_id])[:24]}"
    edge = {
        "edge_id": edge_id,
        "parent_collective_id": unit_id,
        "parent_preview_sha256": str(unit.get("preview_sha256") or ""),
        "child_kind": child_kind,
        "child_id": child_id,
        "initial_state": initial_state,
        "created_at": created_at,
        "provenance": provenance,
    }
    _validate_lineage_edge(edge, unit)

    def append(current: dict[str, Any] | None) -> dict[str, Any]:
        if current is None:
            updated = {
                "document_type": "collective_lineage",
                "lineage_id": lineage_id,
                "collective_unit_id": unit_id,
                "preview_sha256": unit.get("preview_sha256"),
                "edges": [edge],
            }
        else:
            if (
                current.get("document_type") != "collective_lineage"
                or current.get("collective_unit_id") != unit_id
                or current.get("preview_sha256") != unit.get("preview_sha256")
                or not isinstance(current.get("edges"), list)
            ):
                raise ValueError("collective lineage authority requires reconciliation")
            edges = list(current["edges"])
            for existing in edges:
                if not isinstance(existing, dict):
                    raise ValueError("collective lineage edge requires reconciliation")
                if existing.get("child_id") == child_id:
                    if existing != edge:
                        raise ValueError(
                            "collective lineage child conflicts with durable provenance"
                        )
                    return current
            if len(edges) >= 1_000:
                raise ValueError("collective lineage descendant limit reached")
            updated = {
                **current,
                "edges": sorted([*edges, edge], key=lambda row: str(row.get("edge_id") or "")),
            }
        if len(_canonical(updated).encode("utf-8")) > 1_000_000:
            raise ValueError("collective lineage exceeds durable document cap")
        return updated

    return store.mutate_owned_document(lineage_id, owner_id, append)


def list_collective_lineage(
    *,
    store: EngagementStore,
    owner_id: str,
    unit: dict[str, Any],
    after_edge_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    unit_id = str(unit.get("collective_unit_id") or "")
    if after_edge_id is not None and re.fullmatch(r"cedge_[0-9a-f]{24}", after_edge_id) is None:
        raise ValueError("collective lineage cursor is outside the canonical contract")
    if not 1 <= limit <= 101:
        raise ValueError("collective lineage page limit is outside the contract")
    lineage = store.get_owned_document(_lineage_id(unit_id), owner_id)
    if lineage is None:
        return []
    if (
        lineage.get("document_type") != "collective_lineage"
        or lineage.get("collective_unit_id") != unit_id
        or lineage.get("preview_sha256") != unit.get("preview_sha256")
        or not isinstance(lineage.get("edges"), list)
        or len(lineage["edges"]) > 1_000
        or len(_canonical(lineage).encode("utf-8")) > 1_000_000
    ):
        raise ValueError("collective lineage authority requires reconciliation")
    edges = sorted(lineage["edges"], key=lambda row: str(row.get("edge_id") or ""))
    seen_edge_ids: set[str] = set()
    seen_child_ids: set[str] = set()
    for row in edges:
        if not isinstance(row, dict):
            raise ValueError("collective lineage authority requires reconciliation")
        _validate_lineage_edge(row, unit)
        edge_id = str(row["edge_id"])
        child_id = str(row["child_id"])
        if edge_id in seen_edge_ids or child_id in seen_child_ids:
            raise ValueError("collective lineage contains duplicate authority")
        seen_edge_ids.add(edge_id)
        seen_child_ids.add(child_id)
    if after_edge_id is not None:
        try:
            cursor_index = next(
                index for index, row in enumerate(edges) if row.get("edge_id") == after_edge_id
            )
        except StopIteration as exc:
            raise ValueError("collective lineage cursor is not available") from exc
        edges = edges[cursor_index + 1 :]
    out: list[dict[str, Any]] = []
    out.extend(edges[:limit])
    return out


def _validate_lineage_edge(edge: dict[str, Any], unit: dict[str, Any]) -> None:
    kind = edge.get("child_kind")
    child_id = edge.get("child_id")
    created_at = edge.get("created_at")
    provenance = edge.get("provenance")
    expected_edge_id = f"cedge_{_digest('antiek:collective-lineage-edge:v1', [unit.get('collective_unit_id'), kind, child_id])[:24]}"
    if (
        not hmac.compare_digest(str(edge.get("edge_id") or ""), expected_edge_id)
        or edge.get("parent_collective_id") != unit.get("collective_unit_id")
        or edge.get("parent_preview_sha256") != unit.get("preview_sha256")
        or kind not in {"research_session", "written_analysis"}
        or not isinstance(child_id, str)
        or (kind == "research_session" and _SESSION_ID.fullmatch(child_id) is None)
        or (kind == "written_analysis" and _DRAFT_ID.fullmatch(child_id) is None)
        or (kind == "research_session" and edge.get("initial_state") != "reserved")
        or (kind == "written_analysis" and edge.get("initial_state") != "draft")
        or not isinstance(created_at, str)
        or len(created_at) > 64
        or not isinstance(provenance, dict)
        or len(_canonical(provenance).encode("utf-8")) > 10_000
    ):
        raise ValueError("collective lineage edge requires reconciliation")


def list_collective_units(
    *,
    store: EngagementStore,
    owner_id: str,
    after_unit_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if after_unit_id is not None and _UNIT_ID.fullmatch(after_unit_id) is None:
        raise ValueError("collective cursor is outside the canonical contract")
    rows = store.list_owned_documents(
        owner_id,
        logical_prefix="cunit_",
        after_logical_id=after_unit_id,
        limit=limit,
    )
    out: list[dict[str, Any]] = []
    for logical_id, row in rows:
        unit_id = str(row.get("collective_unit_id") or "")
        if (
            logical_id != unit_id
            or _UNIT_ID.fullmatch(unit_id) is None
            or row.get("document_type") != "collective_research_unit"
            or row.get("state") != "confirmed"
        ):
            raise ValueError("collective unit listing requires reconciliation")
        _validate_collective_unit_row(row, owner_id)
        out.append(row)
    return out


def _validate_collective_unit_row(row: dict[str, Any], owner_id: str) -> None:
    preview = row.get("preview_sha256")
    created_at = row.get("created_at")
    material = row.get("material")
    rendered = row.get("html")
    if (
        not isinstance(preview, str)
        or re.fullmatch(r"[0-9a-f]{64}", preview) is None
        or not isinstance(created_at, str)
        or not 1 <= len(created_at) <= 64
        or not isinstance(material, dict)
        or material.get("owner_id") != owner_id
        or collective_preview_sha256(material) != preview
        or row.get("collective_unit_id") != f"cunit_{preview[:24]}"
        or row.get("state") != "confirmed"
        or row.get("view_format") != "html"
        or not isinstance(rendered, str)
        or len(rendered.encode("utf-8")) > 4_000_000
        or len(_canonical(material).encode("utf-8")) > 2_000_000
    ):
        raise ValueError("collective unit material requires reconciliation")
    sessions = material.get("source_session_ids")
    source = material.get("unit")
    query = material.get("query")
    if (
        not isinstance(sessions, list)
        or not 1 <= len(sessions) <= 32
        or any(
            not isinstance(value, str) or _SESSION_ID.fullmatch(value) is None for value in sessions
        )
        or not isinstance(source, dict)
        or (query is not None and (not isinstance(query, str) or len(query) > 8_000))
    ):
        raise ValueError("collective unit source authority requires reconciliation")
    assets = source.get("asset_ids")
    if (
        not isinstance(assets, list)
        or not 1 <= len(assets) <= 32
        or any(not isinstance(value, str) or not 1 <= len(value) <= 512 for value in assets)
        or source.get("recommended_research_tier") not in {"fast", "deep", "wrestle"}
    ):
        raise ValueError("collective unit summary requires reconciliation")
    for field in ("spawn_count", "twin_count", "ref_count", "output_count"):
        value = source.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100_000:
            raise ValueError("collective unit count requires reconciliation")


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
            "created_at": datetime.now(UTC).isoformat(),
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
        "created_at": datetime.now(UTC).isoformat(),
    }

    def persist(current: dict[str, Any] | None) -> dict[str, Any]:
        if current is not None:
            if current.get("request_sha256") != request_sha:
                raise ValueError("written-analysis idempotency conflict")
            return current
        return row

    return store.mutate_owned_document(draft_id, owner_id, persist)
