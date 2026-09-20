"""HTML projection renderer (HPRJ SPR-02).

Pure, deterministic, script-free renderer: turns canonical doc-model JSON
into self-contained HTML with an inert data island. The Thariq thesis —
HTML as the reading experience AND the artifact formfactor.

Public API:

- ``render(doc_model, ctx) -> str`` — render a doc-model to HTML.
- ``RenderContext`` / ``Provenance`` — render-time inputs (resolver +
  footer data). No wall-clock.
- ``embed_island`` / ``extract_island`` — data-island round-trip.
- ``gate.assert_script_free`` — zero-script gate (stdlib-only; SPR-07
  reuses it on the ingest side).
- ``CONTRACT_TABLE`` — the block taxonomy (file:line-cited).

INVARIANTS (master-spec): script-free, derived-only, byte-identical
determinism, self-contained, provenance footer in every render.
"""

from __future__ import annotations

from . import gate, tokens
from .context import (
    DictRefResolver,
    Provenance,
    RefResolver,
    RenderContext,
    ResolvedRef,
    Tombstone,
)
from .contract import (
    CONTRACT_TABLE,
    BlockContract,
    contract_for_tiptap_type,
    known_block_types,
    known_tiptap_types,
)
from .island import (
    ISLAND_SCHEMA_VERSION,
    IslandError,
    IslandNotFound,
    MalformedIsland,
    UnknownIslandSchemaVersion,
    embed_island,
    extract_island,
)
from .renderer import render, restyle_artifact
from .styles import (
    BUILTIN_STYLES,
    DEFAULT_STYLE_NAME,
    ProjectionStyle,
    StyleError,
    StyleRegistry,
    default_registry,
    resolve_style,
    validate_style,
)

__all__ = [
    "CONTRACT_TABLE",
    "BlockContract",
    "DictRefResolver",
    "ISLAND_SCHEMA_VERSION",
    "IslandError",
    "IslandNotFound",
    "MalformedIsland",
    "Provenance",
    "RefResolver",
    "RenderContext",
    "ResolvedRef",
    "Tombstone",
    "UnknownIslandSchemaVersion",
    "contract_for_tiptap_type",
    "embed_island",
    "extract_island",
    "restyle_artifact",
    "ProjectionStyle",
    "StyleRegistry",
    "StyleError",
    "validate_style",
    "default_registry",
    "resolve_style",
    "BUILTIN_STYLES",
    "DEFAULT_STYLE_NAME",
    "gate",
    "known_block_types",
    "known_tiptap_types",
    "render",
    "tokens",
]
