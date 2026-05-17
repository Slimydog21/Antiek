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
]
