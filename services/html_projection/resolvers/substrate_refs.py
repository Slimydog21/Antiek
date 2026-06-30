"""Resolve notebook/deliverable ref_ids against the live substrate graph.

Each ref_id is a graph node (claim, insight, question, etc.). This resolver
fetches the node's text, traces its source document (via metadata first, then
a ``supported_by`` edge fallback), and reports that document's rights fields
(``content_class``, ``ip_holder_id``, ``title``) faithfully.

Rights discipline: this resolver REPORTS rights, it does NOT FILTER them.
The caller (``RightsAwareResolver`` in the notebook adapter) decides whether
to serve or cite-only based on ``content_class``. Pre-filtering here would
double-apply the gate and hide the cite-only attribution the adapter builds.

Provenance discipline: uses ``connect_read`` from ``runtime/db_lock`` — the
only sanctioned read handle. Never writes; never opens a second store.
"""

from __future__ import annotations

import json
from typing import Optional

from runtime.db_lock import connect_read
from services.html_projection.adapters.notebook import ResolvedRefData

# The payload key each renderer partial reads as displayable text.
_PAYLOAD_KEY_MAP: dict[str, str] = {
    "claim": "statement",
    "insight": "statement",
    "question": "question",
}


def _payload_key(node_type: str) -> str:
    """Return the kind-specific payload key for *node_type*."""
    return _PAYLOAD_KEY_MAP.get(node_type, "body")


def _safe_json_loads(raw: Optional[str]) -> dict:
    """Parse *raw* as JSON; return ``{}`` on any failure."""
    if not raw:
        return {}
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
        return {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def resolve_refs(
    ref_ids: list[str], *, db_path: str
) -> dict[str, ResolvedRefData]:
    """Resolve *ref_ids* against the substrate graph at *db_path*.

    Returns a dict mapping each successfully resolved ref_id to its
    ``ResolvedRefData``.  Missing nodes are **omitted** (the export adapter
    renders a visible ``[... unavailable]`` marker for absent keys).

    For each ref_id:
    1. Look up the node.  Absent → omit.
    2. Derive ``source_document_id`` from ``metadata`` JSON; fall back to a
       ``supported_by`` edge if metadata has none.
    3. If a source document exists, read its ``title``, ``content_class``,
       ``ip_holder_id``.  Otherwise all three are ``None`` (which the
       adapter treats as servable — user/graph-owned content).
    4. Build ``ResolvedRefData`` with both the kind-specific and generic
       ``"text"`` payload keys set to the node's ``canonical_label``.
    """
    if not ref_ids:
        return {}

    con = connect_read(db_path)
    try:
        result: dict[str, ResolvedRefData] = {}
        for ref_id in ref_ids:
            resolved = _resolve_one(con, ref_id)
            if resolved is not None:
                result[ref_id] = resolved
        return result
    finally:
        con.close()


def _resolve_one(
    con, ref_id: str
) -> Optional[ResolvedRefData]:
    """Resolve a single *ref_id*.  Returns ``None`` if the node is absent."""

    # ── Step 1: fetch the node ──────────────────────────────────────────
    row = con.execute(
        "SELECT node_id, canonical_label, node_type, metadata "
        "FROM nodes WHERE node_id = ?",
        [ref_id],
    ).fetchone()
    if row is None:
        return None

    _node_id, canonical_label, node_type, raw_metadata = row

    # ── Step 2: determine source_document_id ────────────────────────────
    meta = _safe_json_loads(raw_metadata)
    source_document_id: Optional[str] = meta.get("source_document_id")

    if source_document_id is None:
        # Fallback: walk a supported_by edge.
        edge_row = con.execute(
            "SELECT source_document_id FROM edges "
            "WHERE source_node_id = ? "
            "AND relation = 'supported_by' "
            "AND source_document_id IS NOT NULL "
            "LIMIT 1",
            [ref_id],
        ).fetchone()
        if edge_row is not None:
            source_document_id = edge_row[0]

    # ── Step 3: fetch document rights (if any) ──────────────────────────
    content_class: Optional[str] = None
    ip_holder_id: Optional[str] = None
    title: Optional[str] = None

    if source_document_id is not None:
        doc_row = con.execute(
            "SELECT title, content_class, ip_holder_id "
            "FROM documents WHERE document_id = ?",
            [source_document_id],
        ).fetchone()
        if doc_row is not None:
            title, content_class, ip_holder_id = doc_row

    # ── Step 4: build the payload ───────────────────────────────────────
    kind_specific_key = _payload_key(node_type)
    payload: dict = {
        kind_specific_key: canonical_label,
        "text": canonical_label,
    }

    return ResolvedRefData(
        kind=node_type,
        content_class=content_class,
        ip_holder_id=ip_holder_id,
        title=title,
        payload=payload,
    )
