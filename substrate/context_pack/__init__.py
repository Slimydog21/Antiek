"""Context-pack assembly — meticulously orchestrated context for dispatch.

See ``assembler.py`` for the implementation and the discipline rules
that keep this module decoupled from ``substrate.dispatch``.
"""

from .assembler import (
    CANONICAL_RENDER_ORDER,
    DEFAULT_KIND_PRIORITY,
    MANDATORY_PRIORITY_FLOOR,
    SYNTHESIS_BUDGET_ROLES,
    TRUNCATION_MARKER,
    AssembledLayer,
    ContextPack,
    DefaultTokenCounter,
    LayerKind,
    LayerSource,
    TokenCounter,
    TruncationStrategy,
    assemble_context_pack,
    default_budget_for,
)
from .style_guide import (
    QUANTITATIVE_SKIP_THRESHOLD,
    STYLE_EXTRACTOR_FLAG,
    STYLE_GUIDE_LAYER_KIND,
    STYLE_GUIDE_LAYER_SOURCE,
    maybe_style_guide_layer,
    should_run_style_extractor,
    style_extractor_enabled,
)
from .working_memory import (
    MAX_WORKING_MEMORY_ITEM_BYTES,
    MAX_WORKING_MEMORY_ITEM_CHARS,
    MAX_WORKING_MEMORY_ITEMS,
    MAX_WORKING_MEMORY_RENDERED_BYTES,
    MAX_WORKING_MEMORY_RENDERED_CHARS,
    WorkingMemoryIntegrityError,
    build_working_memory_layer,
)

__all__ = [
    "assemble_context_pack",
    "ContextPack",
    "LayerSource",
    "AssembledLayer",
    "TokenCounter",
    "DefaultTokenCounter",
    "LayerKind",
    "TruncationStrategy",
    "CANONICAL_RENDER_ORDER",
    "DEFAULT_KIND_PRIORITY",
    "MANDATORY_PRIORITY_FLOOR",
    "SYNTHESIS_BUDGET_ROLES",
    "TRUNCATION_MARKER",
    "default_budget_for",
    # style-guide wiring (Sprint 11)
    "STYLE_EXTRACTOR_FLAG",
    "QUANTITATIVE_SKIP_THRESHOLD",
    "STYLE_GUIDE_LAYER_KIND",
    "STYLE_GUIDE_LAYER_SOURCE",
    "style_extractor_enabled",
    "should_run_style_extractor",
    "maybe_style_guide_layer",
    "MAX_WORKING_MEMORY_ITEMS",
    "MAX_WORKING_MEMORY_ITEM_BYTES",
    "MAX_WORKING_MEMORY_ITEM_CHARS",
    "MAX_WORKING_MEMORY_RENDERED_BYTES",
    "MAX_WORKING_MEMORY_RENDERED_CHARS",
    "WorkingMemoryIntegrityError",
    "build_working_memory_layer",
]
