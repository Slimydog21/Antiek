"""Context-pack assembly.

Builds the layered prompt the dispatch router sends to a provider. Two
discipline rules govern this module:

1. **It does not import from ``substrate.dispatch``.** The two modules
   meet at the caller (a role's call site), not by mutual import. The
   role builds a ``ContextPack`` here, then passes ``pack.text`` and
   ``pack.event_id`` to ``dispatch(...)``. An ast-based test in
   ``tests/test_context_pack.py`` enforces the invariant.

2. **The pack itself is a typed event.** Every successful assembly
   emits ``CONTEXT_PACK_ASSEMBLED`` so a downstream query can answer
   "what did the model see when it made this call" — the architecture
   notes §2.5 property. The returned ``ContextPack.event_id`` is the
   value the role passes as ``dispatch(..., context_pack_event_id=...)``.

Layer kinds (matching ``substrate.schemas.events.ContextLayer.kind``):

- ``param_version_stamp`` — ANTIEK_PARAM_VERSION. Mandatory; never dropped.
- ``phase_metadata`` — investigation_id / phase / role markers.
  Mandatory; never dropped.
- ``style_guide`` — per-corpus sector style guide from the
  ``style_extractor`` role (Sprint 11). Feature-flagged OFF by default;
  injected only for qualitative investigations. Priority equals
  ``long_term_skill`` (background conditioning, truncatable).
- ``long_term_skill`` — accumulated knowledge from compounding skills.
- ``reuse`` — prior INVESTIGATIONS' knowledge units retrieved + injected at
  investigation start (AFF SPR-06, the flywheel's reuse half). Distinct kind
  from ``graph_evidence`` so an audit can tell prior-investigation reuse apart
  from THIS investigation's own retrieved evidence; same evidence-level
  priority (60, background but truncatable), rendered just before
  ``graph_evidence``.
- ``working_memory`` — prior notes and open questions from this investigation.
- ``graph_evidence`` — retrieved facts from the knowledge graph.
- ``session`` — current investigation state, the role-specific task.
  Highest non-mandatory priority — preserved before evidence and skills.

Rendering order in the final prompt:
``param_version_stamp → phase_metadata → style_guide → long_term_skill → reuse → graph_evidence → working_memory → session``

The user's action-relevant content (``session``) goes last so it is
closest to the model's response — standard LLM prompt-tail attention.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

try:
    from ..constants import (
        DEFAULT_CONTEXT_BUDGET_TOKENS,
        SYNTHESIS_CONTEXT_BUDGET_TOKENS,
    )
    from ..event_log import emit_typed
    from ..schemas import ContextLayer, ContextPackAssembledPayload
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(_here))  # substrate/
    from constants import (  # type: ignore[no-redef]
        DEFAULT_CONTEXT_BUDGET_TOKENS,
        SYNTHESIS_CONTEXT_BUDGET_TOKENS,
    )
    from event_log import emit_typed  # type: ignore[no-redef]
    from schemas import ContextLayer, ContextPackAssembledPayload  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Layer kind metadata
# ---------------------------------------------------------------------------


LayerKind = Literal[
    "session", "working_memory", "long_term_skill", "reuse", "graph_evidence",
    "style_guide", "phase_metadata", "param_version_stamp",
]

TruncationStrategy = Literal["smart", "head", "tail"]


# Priority for the ``smart`` truncation strategy.
# Higher = preserved longer. 90+ is mandatory (never dropped or truncated).
DEFAULT_KIND_PRIORITY: dict[str, int] = {
    "param_version_stamp": 100,  # tiny, always
    "phase_metadata":       95,  # small, always
    "session":              80,  # current task — almost always keep
    "working_memory":       90,  # bounded, audit-digested, never truncated
    "reuse":                60,  # prior-investigation reuse (AFF SPR-06) — evidence-level
    "graph_evidence":       60,  # retrieved facts — important but truncatable
    "long_term_skill":      40,  # background — easiest to truncate
    "style_guide":          40,  # sector voice conditioning — same as skill
}

MANDATORY_PRIORITY_FLOOR = 90  # priorities >= this are never dropped


# Canonical render order in the final prompt text. Whatever subset of
# layers survives truncation is emitted in this order.
CANONICAL_RENDER_ORDER: tuple[str, ...] = (
    "param_version_stamp",
    "phase_metadata",
    "style_guide",
    "long_term_skill",
    "reuse",
    "graph_evidence",
    "working_memory",
    "session",
)


# Roles that get the SYNTHESIS budget (the big one). Everything else
# uses DEFAULT_CONTEXT_BUDGET_TOKENS.
SYNTHESIS_BUDGET_ROLES: frozenset[str] = frozenset({"synthesizer"})

# Marker inserted at the truncation cut point so the model knows a
# layer was abbreviated and downstream observers can spot truncation.
TRUNCATION_MARKER = "\n…[truncated to fit pack budget]…\n"


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------


class TokenCounter(Protocol):
    """Inject a real tokenizer for exact accounting; default heuristic is
    chars/4 (roughly within ±20% of GPT-4 / Claude tokenizers on English
    text). Cost reports computed from approximate token counts are
    approximate — for billing-grade accounting, inject the provider's
    tokenizer."""

    def count(self, text: str) -> int: ...


class DefaultTokenCounter:
    """Char-count / 4 heuristic. Fast, no dependencies, good enough for
    budget enforcement that is itself approximate."""

    def count(self, text: str) -> int:
        if not text:
            return 0
        return max(1, (len(text) + 3) // 4)


# ---------------------------------------------------------------------------
# Input + output types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayerSource:
    """One layer the caller wants included in the pack.

    ``priority`` is consulted by the ``smart`` truncation strategy.
    If unset, falls back to ``DEFAULT_KIND_PRIORITY[kind]`` (50 if the
    kind is unknown). Pass an explicit priority to lift or lower a
    layer relative to its kind default.
    """

    kind: LayerKind
    source: str
    content: str
    priority: int | None = None

    @property
    def effective_priority(self) -> int:
        if self.priority is not None:
            return self.priority
        return DEFAULT_KIND_PRIORITY.get(self.kind, 50)


@dataclass(frozen=True)
class AssembledLayer:
    """A layer post-render, post-truncation. Embedded in ``ContextPack.layers``
    and converted to a ``ContextLayer`` for the emitted event."""

    kind: str
    source: str
    tokens: int
    rendered: str


@dataclass(frozen=True)
class ContextPack:
    """A fully assembled pack, ready to be passed to ``dispatch(...)``.

    Use ``pack.text`` as the prompt prefix (the role may append its own
    role-specific tail), and pass ``pack.event_id`` as
    ``dispatch(..., context_pack_event_id=pack.event_id)`` so the
    DispatchCall event links back to the pack provenance.
    """

    role: str
    text: str
    layers: tuple[AssembledLayer, ...]
    target_tokens: int
    actual_tokens: int
    budget_overrun: bool
    truncation_strategy_applied: TruncationStrategy | None
    event_id: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def default_budget_for(role: str) -> int:
    """Tier-equivalent budget defaulting by role. Synthesizers get the
    long-context budget; everything else uses the short-context default."""
    if role in SYNTHESIS_BUDGET_ROLES:
        return SYNTHESIS_CONTEXT_BUDGET_TOKENS
    return DEFAULT_CONTEXT_BUDGET_TOKENS


def _layer_header(layer: LayerSource) -> str:
    return f"## {layer.kind}: {layer.source}\n"


def _render_layer_full(layer: LayerSource) -> str:
    """The full rendering of a layer (no truncation). Concatenation of
    these in canonical order is what the model sees when there is no
    budget pressure."""
    return _layer_header(layer) + layer.content.rstrip() + "\n\n"


def _truncate_layer(
    layer: LayerSource,
    *,
    max_tokens: int,
    counter: TokenCounter,
) -> tuple[str, int]:
    """Truncate ONE layer's rendered text to fit at most ``max_tokens``.

    Strategy: keep the header (so the model can identify the layer),
    truncate the body by character-count using the counter's
    char-per-token ratio (approximated as 4 by the default counter; for
    custom counters we binary-search to fit).

    Returns ``(rendered_text, actual_tokens)``. ``actual_tokens`` is
    guaranteed to be ≤ ``max_tokens``.
    """
    header = _layer_header(layer)
    marker = TRUNCATION_MARKER
    header_tokens = counter.count(header)
    marker_tokens = counter.count(marker)

    # If even the header + marker don't fit, just emit the header alone.
    if header_tokens + marker_tokens >= max_tokens:
        # Return just the header (best we can do without breaking the
        # structure); accept that we may slightly exceed max_tokens for
        # mandatory layers (which shouldn't hit this path in practice).
        return header, header_tokens

    body_budget = max_tokens - header_tokens - marker_tokens
    body = layer.content.rstrip()

    # Binary-search the longest body prefix that fits within body_budget
    # tokens. This works for any monotonic TokenCounter — including the
    # chars/4 default and any real tokenizer.
    if counter.count(body) <= body_budget:
        rendered = header + body + "\n\n"
        return rendered, counter.count(rendered)

    lo, hi = 0, len(body)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if counter.count(body[:mid]) <= body_budget:
            lo = mid
        else:
            hi = mid - 1
    kept_body = body[:lo]
    rendered = header + kept_body + marker
    return rendered, counter.count(rendered)


def _canonical_sort_key(layer_kind: str) -> int:
    """Order layers by CANONICAL_RENDER_ORDER. Unknown kinds sort last."""
    try:
        return CANONICAL_RENDER_ORDER.index(layer_kind)
    except ValueError:
        return len(CANONICAL_RENDER_ORDER) + 1


# ---------------------------------------------------------------------------
# Truncation strategies
# ---------------------------------------------------------------------------


def _smart_truncate(
    rendered: list[tuple[LayerSource, str, int]],
    target: int,
    counter: TokenCounter,
) -> tuple[list[tuple[LayerSource, str, int]], int]:
    """Priority-aware truncation.

    1. Mandatory layers (priority >= 90) are kept in full. If the
       mandatory set alone exceeds the budget, return them anyway —
       the model needs them even if we overshoot. This is logged via
       ``budget_overrun=True`` so the operator can investigate.
    2. Remaining layers are added in priority order (highest first).
       Each fits-in-full or gets truncated to fit; once a layer is
       truncated, subsequent (lower-priority) layers are dropped.
    """
    mandatory = [r for r in rendered if r[0].effective_priority >= MANDATORY_PRIORITY_FLOOR]
    optional = [r for r in rendered if r[0].effective_priority < MANDATORY_PRIORITY_FLOOR]

    used = sum(t for _, _, t in mandatory)
    kept: list[tuple[LayerSource, str, int]] = list(mandatory)

    # Sort optional by priority desc; secondary by canonical position so
    # ordering is deterministic when priorities tie.
    optional.sort(
        key=lambda r: (-r[0].effective_priority, _canonical_sort_key(r[0].kind))
    )

    for layer, full_text, full_tokens in optional:
        remaining = target - used
        if remaining <= 0:
            break
        if full_tokens <= remaining:
            kept.append((layer, full_text, full_tokens))
            used += full_tokens
        else:
            truncated_text, truncated_tokens = _truncate_layer(
                layer, max_tokens=remaining, counter=counter,
            )
            kept.append((layer, truncated_text, truncated_tokens))
            used += truncated_tokens
            break  # subsequent (lower-priority) layers dropped

    return kept, used


def _head_truncate(
    rendered: list[tuple[LayerSource, str, int]],
    target: int,
    counter: TokenCounter,
) -> tuple[list[tuple[LayerSource, str, int]], int]:
    """Keep the head of the canonical sequence. Drops or truncates the
    tail (so the most action-adjacent layer, ``session``, is dropped
    first — usually NOT what you want; prefer ``smart`` or ``tail``)."""
    canonical = sorted(rendered, key=lambda r: _canonical_sort_key(r[0].kind))
    return _accumulate_until_budget(canonical, target, counter)


def _tail_truncate(
    rendered: list[tuple[LayerSource, str, int]],
    target: int,
    counter: TokenCounter,
) -> tuple[list[tuple[LayerSource, str, int]], int]:
    """Keep the tail of the canonical sequence (drops from the head)."""
    canonical = sorted(rendered, key=lambda r: _canonical_sort_key(r[0].kind), reverse=True)
    kept_reversed, used = _accumulate_until_budget(canonical, target, counter)
    return list(reversed(kept_reversed)), used


def _accumulate_until_budget(
    ordered: Sequence[tuple[LayerSource, str, int]],
    target: int,
    counter: TokenCounter,
) -> tuple[list[tuple[LayerSource, str, int]], int]:
    """Walk layers in order; include each fully if it fits, truncate the
    boundary layer to fit, drop the rest. Used by head/tail strategies."""
    kept: list[tuple[LayerSource, str, int]] = []
    used = 0
    for layer, full_text, full_tokens in ordered:
        remaining = target - used
        if remaining <= 0:
            break
        if full_tokens <= remaining:
            kept.append((layer, full_text, full_tokens))
            used += full_tokens
        else:
            truncated_text, truncated_tokens = _truncate_layer(
                layer, max_tokens=remaining, counter=counter,
            )
            kept.append((layer, truncated_text, truncated_tokens))
            used += truncated_tokens
            break
    return kept, used


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def assemble_context_pack(
    *,
    role: str,
    investigation_id: str,
    layers: Iterable[LayerSource],
    target_tokens: int | None = None,
    truncation: TruncationStrategy = "smart",
    counter: TokenCounter | None = None,
    parent_event_id: str | None = None,
) -> ContextPack:
    """Assemble a context pack.

    Args:
        role: The role this pack is for. Determines the default budget
            via ``default_budget_for(role)`` if ``target_tokens`` is None.
        investigation_id: Scope key for the emitted CONTEXT_PACK_ASSEMBLED
            event.
        layers: The layers to include. Order does not matter — the
            assembler renders in canonical order regardless.
        target_tokens: Override the default budget. Required for
            non-standard call paths (e.g., a tier-aware caller that
            wants to size the pack to ``TierConfig.context_budget_tokens``).
        truncation: Which strategy to use when total exceeds budget.
            ``smart`` is the default and almost always correct; ``head``
            and ``tail`` exist for diagnostic use.
        counter: Inject a real tokenizer; defaults to chars/4.
        parent_event_id: Optional parent for the emitted event.

    Returns:
        ContextPack with ``text`` (the prompt prefix), ``event_id``, and
        breakdown metadata. The text concatenates surviving layers in
        canonical order; the role appends its own task-specific tail
        before passing to ``dispatch``.
    """
    counter = counter or DefaultTokenCounter()
    target = target_tokens if target_tokens is not None else default_budget_for(role)

    materialized = list(layers)

    # Render each layer fully and measure.
    rendered: list[tuple[LayerSource, str, int]] = []
    for layer in materialized:
        full_text = _render_layer_full(layer)
        rendered.append((layer, full_text, counter.count(full_text)))

    total = sum(t for _, _, t in rendered)

    if total <= target:
        kept = rendered
        actual = total
        budget_overrun = False
        strategy_applied: TruncationStrategy | None = None
    else:
        budget_overrun = True
        if truncation == "smart":
            kept, actual = _smart_truncate(rendered, target, counter)
        elif truncation == "head":
            kept, actual = _head_truncate(rendered, target, counter)
        elif truncation == "tail":
            kept, actual = _tail_truncate(rendered, target, counter)
        else:  # pragma: no cover — Literal exhausted
            raise ValueError(f"unknown truncation strategy: {truncation!r}")
        strategy_applied = truncation

    # Render the final prompt in canonical order.
    kept_canonical = sorted(kept, key=lambda r: _canonical_sort_key(r[0].kind))
    text = "".join(rt for _, rt, _ in kept_canonical)

    assembled = tuple(
        AssembledLayer(kind=layer.kind, source=layer.source, tokens=tokens, rendered=text)
        for layer, text, tokens in kept_canonical
    )

    # Emit the typed event so the pack provenance is queryable.
    event_id = emit_typed(
        investigation_id,
        ContextPackAssembledPayload(
            target_role=role,
            target_tokens=target,
            actual_tokens=actual,
            layers=[
                ContextLayer(kind=a.kind, source=a.source, tokens=a.tokens)  # type: ignore[arg-type]
                for a in assembled
            ],
            budget_overrun=budget_overrun,
            truncation_strategy_applied=strategy_applied,
        ),
        parent_event_id=parent_event_id,
        role=role,
    )

    return ContextPack(
        role=role,
        text=text,
        layers=assembled,
        target_tokens=target,
        actual_tokens=actual,
        budget_overrun=budget_overrun,
        truncation_strategy_applied=strategy_applied,
        event_id=event_id,
    )
