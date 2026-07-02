"""Notebook EXPORT adapter — pre-resolve into a self-contained doc-model (SPR-06).

The live-view notebook adapter (`notebook.py`) keeps ref_ids and resolves chunk
text at RENDER time via a rights-aware resolver. An exported `.antiek` container
cannot depend on a live resolver — it must be SELF-CONTAINED. So this adapter
resolves every ref NOW and inlines the result:

- a servable ref  -> its resolved payload inlined under the same node type
  (no ref_id), so the container carries the text directly;
- a non-servable ref (personal_reading / restricted / NULL per the SPR-05
  contract, reused via the same `RightsAwareResolver`) -> a CITE-ONLY inline
  payload built from identity only — the passage NEVER enters the doc-model;
- a deleted/missing ref -> a visible "[<kind> unavailable]" marker.

The output carries NO ref_ids, so it renders identically offline
(`resolver=None`) and emits through the routing map as a portable, signed,
rights-safe artifact. The leak surface — unlike the live-view path — is the
doc-model itself (it now carries resolved content), so the rights test asserts
on the serialized doc-model AND the rendered HTML.
"""

from __future__ import annotations

from substrate.constants import SERVABLE_CONTENT_CLASSES

from ..context import Tombstone
from .notebook import ResolvedRefData, RightsAwareResolver

# Node bare-type -> the attr that carries its substrate ref_id (mirrors the
# renderer partials' ref reads + substrate/notebooks/tiptap_codec.py).
_REF_ATTR: dict[str, str] = {
    "claim_card": "claim_id",
    "note": "note_id",
    "note_block": "note_id",
    "question_card": "question_id",
    "master_md_section": "synthesis_id",
    "region_embed": "region_id",
}


def _bare(node_type: str) -> str:
    return node_type[len("antiek_"):] if node_type.startswith("antiek_") else node_type


def _inline(node: dict, resolver: RightsAwareResolver) -> dict:
    node_type = str(node.get("type", ""))
    bare = _bare(node_type)
    attrs = node.get("attrs") if isinstance(node.get("attrs"), dict) else {}
    ref_attr = _REF_ATTR.get(bare)
    ref_id = attrs.get(ref_attr) if ref_attr else None
    if not ref_id:
        return node  # a non-ref node (prose, an inline widget, ...) kept verbatim
    resolved = resolver(str(ref_id), bare)
    if isinstance(resolved, Tombstone):
        when = f" (deleted {resolved.deleted_at})" if resolved.deleted_at else ""
        return {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": f"[{resolved.kind or bare} unavailable{when}]"}
            ],
        }
    # ResolvedRef: inline the (possibly cite-only) payload under the same node
    # type, WITHOUT a ref_id -> the container is self-contained. The payload is
    # the rights-filtered content (cite-only payloads carry no original text).
    return {"type": node_type, "attrs": dict(resolved.payload)}


def collect_ref_ids(content_tiptap: dict) -> list[str]:
    """Every substrate ref_id a notebook's top-level nodes cite, in document
    order, deduped. This is the INPUT to the substrate ref-resolver: the export
    resolver fetches exactly the refs the notebook references, then hands the
    resolved map to ``adapt_notebook_for_export``."""
    nodes = (
        content_tiptap.get("content", [])
        if isinstance(content_tiptap, dict)
        else []
    )
    seen: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        ref_attr = _REF_ATTR.get(_bare(str(node.get("type", ""))))
        attrs = node.get("attrs") if isinstance(node.get("attrs"), dict) else {}
        ref_id = attrs.get(ref_attr) if ref_attr else None
        if ref_id and str(ref_id) not in seen:
            seen.append(str(ref_id))
    return seen


def adapt_notebook_for_export(
    content_tiptap: dict,
    *,
    title: str | None,
    resolved_refs: dict[str, ResolvedRefData],
) -> dict:
    """Pre-resolve a notebook into a self-contained, rights-filtered doc-model
    ready for container emission (no ref_ids; renders identically offline)."""
    resolver = RightsAwareResolver(resolved_refs)
    nodes = (
        content_tiptap.get("content", [])
        if isinstance(content_tiptap, dict)
        else []
    )
    out = [_inline(n, resolver) for n in nodes if isinstance(n, dict)]
    # Knowledge-graph edges: the unique resolved sources, keyed by the source
    # document id when known (a stable identity — title alone collides across
    # same-named docs), labelled by the title (a rights-safe citation), toned by
    # servability.
    cited: dict[str, tuple[str, bool]] = {}
    for ref in resolved_refs.values():
        if not ref.title:
            continue
        node_id = ref.source_document_id or ref.title
        if node_id not in cited:
            cited[node_id] = (
                ref.title,
                ref.content_class in SERVABLE_CONTENT_CLASSES,
            )
    return {
        "content": out,
        "title": title,
        "edges": [
            {
                "kind": "cites",
                "to_document_id": node_id,
                "to_title": label,
                "tone": "success" if servable else "warning",
            }
            for node_id, (label, servable) in cited.items()
        ],
    }


__all__ = ["adapt_notebook_for_export", "collect_ref_ids"]
