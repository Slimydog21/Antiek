"""Writer: notebook → .antiek bytes (SPR-09 / M2).

Substrate-derived artifacts STAY OUT OF THE FILE.
====================================================
Chunks, embeddings, substrate-derived graph edges, attribution
weights, reward-proxy columns — none of them enter a ``.antiek``. The
reason is a load-bearing master-spec invariant ("Key invariants"):

    Chunkers and embedders evolve. In-file copies go stale. We'd have
    to choose between freezing the substrate to match the in-file
    copy, or wasting the in-file copy when the substrate moves on.
    Both are bad. The file therefore carries CANONICAL TEXT (TipTap
    JSON), USER-ASSERTED BLOCKS, USER-ASSERTED EDGES, and a CREATOR
    SIGNATURE — nothing the substrate computes.

If a future maintainer wants to "add embeddings for performance",
that is the exact mistake this comment exists to prevent. The
``_FORBIDDEN_SUBSTRATE_FIELDS`` set below + the M7 test
``test_no_substrate_data`` enforce this mechanically — flip one of
those tests off and you've broken the invariant.

Wire shape
----------
See ``SPEC.md``. In short: a deterministic zip with manifest.json +
content.tiptap.json (+ optional edges.jsonl + blocks/*.audio) +
signature.bin.

Determinism
-----------
The writer SORTS file entries by full path and uses fixed timestamps
+ ZIP_STORED so the same notebook produces byte-identical bytes. The
M7 test ``test_deterministic_write`` writes a fixture twice and
asserts bytes equality. If that test ever flips false, the zip is
silently non-deterministic — fix the zip writer, do not relax the
test.
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import os
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

try:
    from .signature import (
        Keypair,
        build_signing_input,
        canonical_edges_bytes,
        canonical_json_bytes,
        sign_bytes,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from services.antiek_format.signature import (  # type: ignore[no-redef]
        Keypair,
        build_signing_input,
        canonical_edges_bytes,
        canonical_json_bytes,
        sign_bytes,
    )


# ── Format constants ──

SCHEMA_VERSION: str = "1.0.0"
"""Writer-side schema version. Bump the MAJOR component on incompatible
shape changes; bump MINOR on additive changes a reader can fall back
from; bump PATCH on docs/test-only fixes."""

# Zip entry-name constants. Cross-checked by the reader.
ENTRY_MANIFEST: str = "manifest.json"
ENTRY_CONTENT: str = "content.tiptap.json"
ENTRY_EDGES: str = "edges.jsonl"
ENTRY_SIGNATURE: str = "signature.bin"
BLOCKS_PREFIX: str = "blocks/"

# Closed set of content classes. Mirrors manifest.schema.json.
# ``pdf_sidecar`` (SPR-10) shares the zip envelope + signing scheme
# but writes user data into highlights.jsonl + anchors.jsonl rather
# than the TipTap body — see SPEC.md §11.
CONTENT_CLASSES: frozenset[str] = frozenset(
    {"notebook", "theme_notebook", "deliverable", "pdf_sidecar"}
)

# Fixed zip-entry timestamp. 1980-01-01 is zip's minimum representable
# date_time. Using a fixed value is what makes ``.antiek`` deterministic.
_FIXED_DATE_TIME: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0)

# create_system = 3 ("unix"), external_attr = 0o644 << 16. Both fixed
# to remove platform-dependent variance.
_FIXED_CREATE_SYSTEM: int = 3
_FIXED_EXTERNAL_ATTR: int = 0o644 << 16


# ── Master-spec invariant: forbidden substrate-derived fields ──

_FORBIDDEN_SUBSTRATE_FIELDS: tuple[str, ...] = (
    # Chunks (substrate-resident; recomputable)
    "chunks",
    "document_chunks",
    "chunk_text",
    "chunk_embedding",
    "chunk_id",  # we don't carry substrate chunk identifiers
    # Embeddings
    "embedding",
    "embeddings",
    "embedding_vector",
    "vector_embedding",
    # Substrate-derived (auto-discovered) edges
    "graph_edges_auto",
    "auto_edges",
    "discovered_edges",
    # Attribution / scoring
    "attribution_weights",
    "attribution_scores",
    "attribution_vector",
    # Reward proxies
    "reward_proxy_immediate",
    "reward_proxy_medium",
    "reward_proxy_long",
    "reward_signal",
)
"""Field names that MUST NOT appear in any serialised section. The M7
test greps the produced bytes against this list. If you find a real
need to carry one of these, the answer is no — the substrate
recomputes them. See module docstring."""


# ── Inputs ──


@dataclass
class WriterInput:
    """The minimum information the writer needs from a notebook
    record. Decoupled from ``services.notebooks.persistence.NotebookRecord``
    so the antiek-format module has no upward dependency on the
    notebook surface — only the persistence layer composes them
    together. (Same protocol/implementation split SPR-08 set up.)
    """

    notebook_id: str
    user_id: str
    document_id: str
    parent_document_id: Optional[str]
    content_class: str  # "notebook" | "theme_notebook" | "deliverable"
    title: Optional[str]

    # The canonical TipTap document. This IS the source of truth.
    content_tiptap: dict

    # Block index — denormalised for reader convenience. Each entry:
    #   {block_id, block_type, position, source_event_ids,
    #    audio_path?, audio_sha256?, demoted}
    # Populated from notebook.blocks at the call site (persistence
    # layer). The audio_sha256 + audio_path entries are added by the
    # writer when it embeds binaries; callers should NOT pre-fill them.
    blocks_index: list[dict] = dataclasses.field(default_factory=list)

    # User-asserted edges. Empty list = no edges.jsonl entry written.
    edges: list[dict] = dataclasses.field(default_factory=list)

    # Optional voice-block audio bytes, keyed on block_id. The writer
    # embeds these as blocks/<block_id>.audio. Callers fetch from
    # substrate-resident audio storage; the writer does NOT re-encode.
    audio_blobs: dict[str, bytes] = dataclasses.field(default_factory=dict)

    # Optional first-save timestamp. When None, the writer uses now().
    # Pinning enables deterministic byte-output for tests.
    created_at: Optional[datetime] = None

    # Optional notebook-id stamp (carried back to substrate on read).
    format_version: Optional[int] = None


# ── Public API ──


def write_antiek(
    inp: WriterInput,
    *,
    keypair: Keypair,
) -> bytes:
    """Produce a `.antiek` file as bytes.

    The same ``inp`` + the same ``keypair`` MUST yield byte-identical
    output. Determinism is a precondition for content addressing and
    is mechanically tested by M7's ``test_deterministic_write``.

    Parameters
    ----------
    inp : WriterInput
        Notebook content + provenance + optional audio blobs.
    keypair : Keypair
        Creator's Ed25519 keypair from
        ``services.antiek_format.signature.ensure_keypair``.

    Returns
    -------
    bytes
        The full .antiek archive bytes.

    Raises
    ------
    ValueError
        On unknown content_class, forbidden-substrate-field detection,
        or audio blob keyed on an unknown block_id.
    """
    if inp.content_class not in CONTENT_CLASSES:
        raise ValueError(
            f"write_antiek: unknown content_class {inp.content_class!r}; "
            f"valid: {sorted(CONTENT_CLASSES)}"
        )

    # Defensive: refuse to serialise a doc that contains forbidden
    # substrate fields. The pre-flight check is cheap, the failure
    # mode it prevents (substrate data leaking into a signed file) is
    # the master-spec invariant.
    _assert_no_forbidden_fields(inp.content_tiptap, where="content_tiptap")
    for i, entry in enumerate(inp.blocks_index):
        _assert_no_forbidden_fields(entry, where=f"blocks_index[{i}]")
    for i, edge in enumerate(inp.edges):
        _assert_no_forbidden_fields(edge, where=f"edges[{i}]")

    # ── Compute deterministic blocks_index + audio bytes ──

    # Sort blocks_index by position then by block_id so two writers
    # with the same blocks-in-different-order produce identical bytes.
    sorted_blocks: list[dict] = sorted(
        (dict(b) for b in inp.blocks_index),
        key=lambda b: (float(b.get("position", 0.0)), b["block_id"]),
    )

    # Audio embedding pass.
    audio_entries: list[tuple[str, bytes]] = []  # [(path_in_zip, bytes), ...]
    known_block_ids = {b["block_id"] for b in sorted_blocks}
    for block_id, audio_bytes in inp.audio_blobs.items():
        if block_id not in known_block_ids:
            raise ValueError(
                f"write_antiek: audio_blobs has block_id {block_id!r} "
                f"that is not in blocks_index. The blocks_index list is the "
                f"authoritative inventory; add the block row first."
            )
        path = f"{BLOCKS_PREFIX}{block_id}.audio"
        audio_entries.append((path, audio_bytes))
        # Stamp the manifest with the path + integrity hash.
        for b in sorted_blocks:
            if b["block_id"] == block_id:
                b["audio_path"] = path
                b["audio_sha256"] = hashlib.sha256(audio_bytes).hexdigest()
                break
    # Audio blobs sorted by path for deterministic zip layout.
    audio_entries.sort(key=lambda kv: kv[0])

    # ── Build manifest ──

    created_at_iso = (inp.created_at or datetime.now(timezone.utc)).astimezone(
        timezone.utc
    ).isoformat()

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "content_class": inp.content_class,
        "document_id": inp.document_id,
        "parent_document_id": inp.parent_document_id,
        "created_at": created_at_iso,
        "creator_user_id": inp.user_id,
        "creator_pubkey": keypair.public_key_b64,
        "notebook_id": inp.notebook_id,
        "title": inp.title,
        "format_version": inp.format_version,
        "edges_present": bool(inp.edges),
        "blocks_index": sorted_blocks,
    }

    # ── Canonical bytes for signing ──

    manifest_bytes = canonical_json_bytes(manifest)
    content_bytes = canonical_json_bytes(_canonical_tiptap_node(inp.content_tiptap))
    edges_bytes = canonical_edges_bytes(inp.edges)

    signing_input = build_signing_input(
        manifest_bytes=manifest_bytes,
        content_bytes=content_bytes,
        edges_bytes=edges_bytes,
    )
    signature = sign_bytes(keypair, signing_input)

    # ── Assemble the zip ──

    # Build (name, payload) list in canonical order.
    # Order: manifest → content → edges (if any) → blocks/* sorted →
    # signature. Last so a streaming reader can verify after collecting
    # everything before it; ordering is also deterministic.
    entries: list[tuple[str, bytes]] = [
        (ENTRY_MANIFEST, manifest_bytes),
        (ENTRY_CONTENT, content_bytes),
    ]
    if edges_bytes:
        entries.append((ENTRY_EDGES, edges_bytes))
    entries.extend(audio_entries)
    entries.append((ENTRY_SIGNATURE, signature))

    return _build_deterministic_zip(entries)


# ── Internals ──


def _canonical_tiptap_node(node: Any) -> Any:
    """Apply the TipTap canonicalisation rules from SPEC.md §5.

    Recursive — the output dict is a key-ordering-stable copy. The
    JSON serialiser then sorts keys again (belt + braces); the
    ordering work here is for the cases JSON serialisation alone
    doesn't cover (marks array ordering, null-attr dropping, empty
    content arrays).
    """
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        # Copy + canonicalise nested structures.
        for key, value in node.items():
            if key == "attrs" and isinstance(value, dict):
                # Drop null-valued attrs; TipTap treats absent and
                # null as equivalent for many marks per its
                # serialization docs.
                kept = {k: v for k, v in value.items() if v is not None}
                if kept:
                    out["attrs"] = {
                        k: _canonical_tiptap_node(v) for k, v in kept.items()
                    }
                # Else drop the attrs key entirely.
            elif key == "marks" and isinstance(value, list):
                if value:
                    canon_marks = [
                        _canonical_tiptap_node(m) for m in value
                    ]
                    # Stable sort by (type, stringified attrs).
                    out["marks"] = sorted(
                        canon_marks,
                        key=lambda m: (
                            str(m.get("type", "")),
                            json.dumps(
                                m.get("attrs", {}),
                                sort_keys=True,
                                ensure_ascii=False,
                            ),
                        ),
                    )
                # Else drop empty marks array.
            elif key == "content" and isinstance(value, list):
                if value:
                    out["content"] = [
                        _canonical_tiptap_node(c) for c in value
                    ]
                # Else drop empty content array.
            else:
                out[key] = _canonical_tiptap_node(value)
        return out
    if isinstance(node, list):
        return [_canonical_tiptap_node(x) for x in node]
    return node


def _assert_no_forbidden_fields(obj: Any, *, where: str) -> None:
    """Walk an object tree; raise ValueError if any key matches a
    forbidden substrate-derived field.

    Why a runtime check, not a typecheck? Because the writer accepts
    raw dicts (content_json straight from the substrate). A typecheck
    would catch known-bad keys at write-call sites but not at
    "operator pasted weird JSON into a block" sites. The runtime check
    is the backstop.
    """
    if isinstance(obj, dict):
        for key in obj.keys():
            if key in _FORBIDDEN_SUBSTRATE_FIELDS:
                raise ValueError(
                    f"write_antiek: forbidden substrate-derived field "
                    f"{key!r} found in {where}. The .antiek file MUST NOT "
                    f"carry substrate-derived artifacts (chunks, embeddings, "
                    f"auto-edges, attribution, reward signals). See SPEC.md "
                    f"§9 and the master spec's Key Invariants."
                )
        for k, v in obj.items():
            _assert_no_forbidden_fields(v, where=f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _assert_no_forbidden_fields(v, where=f"{where}[{i}]")


def _build_deterministic_zip(entries: list[tuple[str, bytes]]) -> bytes:
    """Pack entries into a byte-identical zip. See SPEC.md §6.

    Entries arrive pre-sorted in the canonical order. We do NOT sort
    again here — caller order determines layout. (The caller knows
    the manifest must come first, signature last, etc.)
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_STORED) as zf:
        for name, payload in entries:
            info = zipfile.ZipInfo(filename=name, date_time=_FIXED_DATE_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = _FIXED_CREATE_SYSTEM
            info.external_attr = _FIXED_EXTERNAL_ATTR
            # No extra fields, no comments.
            info.extra = b""
            info.comment = b""
            zf.writestr(info, payload)
    return buf.getvalue()


__all__ = [
    "BLOCKS_PREFIX",
    "CONTENT_CLASSES",
    "ENTRY_CONTENT",
    "ENTRY_EDGES",
    "ENTRY_MANIFEST",
    "ENTRY_SIGNATURE",
    "SCHEMA_VERSION",
    "WriterInput",
    "write_antiek",
]
