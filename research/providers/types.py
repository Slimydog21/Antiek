"""Normalized research-result type — the provider-agnostic answer shape.

This is the ONE shape every ``ResearchProvider`` returns from
``answer(...)``. It is deliberately a **pure-data frozen dataclass** (not a
Pydantic model) to match the Exa adapter's idiom (``DiscoveryProposed``,
``DiscoveryPromotionResult`` are frozen dataclasses) and to keep the
provider contract dependency-light: the conformance harness and any
adapter — including a hypothetical non-Pydantic one — can construct a
``ResearchResult`` without pulling Pydantic onto the import path. The
contracts layer (``substrate/contracts/reading_surface.py``) uses
``Protocol`` for behavioral shapes; here we need a *value* shape, and
frozen dataclasses are the codebase's chosen vehicle for those (see
``runtime/research_runner/protocol.py``: ``BudgetCap``, ``ResearchPlan``,
``StepEvent`` are all ``@dataclass(frozen=True)``).

Invariants (load-bearing — copied verbatim from the spec)
---------------------------------------------------------

INV-1 · One owner. The research-execution layer has exactly one owner — the ResearchRunner. Exa Deep and Parallel are tools behind ResearchProvider; no module outside the adapter package imports an engine SDK.

INV-4 · Normalized contract. Every provider returns the same normalized shape. The runner never branches on a raw provider payload above the adapter boundary.

Design note — why ``raw_ref`` is an opaque handle, not a provider dict
----------------------------------------------------------------------
INV-4 forbids the normalized type from embedding provider-specific
*structure*. If ``raw_ref`` were typed ``dict[str, Any]``, an adapter
could smuggle the raw Exa/Parallel payload into it and a caller above
the boundary could branch on ``raw_ref["grounding"]["confidence"]`` —
that is exactly the leak INV-4 exists to prevent. So ``raw_ref`` is a
``RawRef`` wrapper carrying only an opaque ``handle: str`` (an id the
adapter can resolve to the stored raw payload in its own side store)
plus the ``provider`` that owns it. The contract is: "the raw payload
exists and is auditable; ask the adapter, not the result, to read it."
The string is opaque by construction — it carries no provider-specific
keys a caller could branch on.

Confidence normalization rule (RIGOR #1 — UNVERIFIED ASSUMPTION)
---------------------------------------------------------------
Providers emit confidence on different scales:

* **Exa** emits a categorical ``grounding.confidence`` with values
  ``"high"`` / ``"medium"`` / ``"low"``. This is an opaque category, not
  a calibrated probability.
* **Parallel** emits a calibrated numeric score in [0.0, 1.0].

We map BOTH onto a single ``float`` in ``[0.0, 1.0]`` so the router
(SPR-07) and downstream consumers see one scale. The mapping is:

    Exa categorical → numeric:
        "high"   → 0.9
        "medium" → 0.6
        "low"    → 0.3
        (unknown / missing) → 0.3   # DELIBERATELY aliased to low (see note)

    NOTE on the unknown→0.3 alias (grok co-CEO D8): unknown/missing Exa
    confidence is mapped to the SAME value as "low". This is a deliberate
    conservative conflation, not an accident: a single ``float`` cannot
    distinguish "provider asserted low" from "provider returned no
    confidence", so we route both as the lowest actionable tier (do not
    trust the answer without corroboration). A downstream consumer that
    needs to distinguish them cannot do so from ``confidence`` alone —
    that distinguishability is deferred to SPR-07's ``confidence_kind``
    capability metadata (grok co-CEO D2), which will let the router mark
    ordinal-mapped scores as non-comparable to calibrated ones. Until
    then, treat 0.3 as "low-or-missing", not "calibrated 0.3".

    Parallel numeric → numeric:
        pass through, clamped to [0.0, 1.0].

**This is an unverified assumption.** The Exa category is NOT a
calibrated probability and the three anchors (0.9 / 0.6 / 0.3) are
engineering guesses, not measured equivalents of a calibrated score.
Pretending the two scales are commensurable is a known lie we accept
so the router has a single number to threshold on; the alternative
(two confidence fields, one per provider kind) would violate INV-4 by
forcing every consumer to branch on provider. What would reverse this
decision: Exa publishing a documented calibration curve for their
categories, or the router needing provider-specific thresholds (which
would itself be an INV-4 smell).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True)
class Source:
    """One supporting source for a result field.

    The minimal provenance a normalized result carries: a URL and a
    human-readable title. Adapters populate this from the provider's
    own citation objects (Exa result URLs/titles, Parallel source
    refs). Nothing provider-specific lives here — no Exa ``score``,
    no Parallel ``chunk_id``; those stay in the raw payload behind
    ``RawRef``.
    """

    url: str
    title: str | None = None


@dataclass(frozen=True)
class RawRef:
    """Opaque pointer to the stored raw provider payload.

    ``handle`` is an opaque string id (e.g. ``"exa:raw:abc123"``) the
    *adapter* can resolve to the stored raw payload in its own side
    store. It is NOT a dict and NOT the raw payload itself — by
    construction it carries no provider-specific structure a caller
    above the adapter boundary could branch on (INV-4). ``provider``
    records which adapter owns the handle so an audit path knows where
    to resolve it; it does NOT inject provider shape.
    """

    handle: str
    provider: str


@dataclass(frozen=True)
class ResearchResult:
    """The normalized answer shape every ``ResearchProvider`` returns.

    Fields
    ------
    fields:
        Structured answer fields, keyed by the sub-question's
        ``outputSchema`` keys. Values are strings (the canonical
        representation for a single answer field). A key with a
        ``None`` value denotes "the provider could not populate this
        field"; an empty string ``""`` is treated as unpopulated too
        (both are exempt from the citation requirement). Non-null,
        non-empty values MUST cite at least one source (INV-4). Typed
        as ``Mapping`` and frozen at construction (``__post_init__``
        wraps caller-supplied dicts in a read-only ``MappingProxyType``)
        so a caller cannot mutate fields post-return — the citation
        invariant cannot be broken without the adapter knowing.
    field_citations:
        Maps each non-null field name → the tuple of ``Source`` objects
        supporting it. A field with a value MUST have ≥1 citation; a
        null/empty field may have none. The conformance harness
        enforces this invariant. Frozen at construction (citation lists
        become immutable ``tuple``) for the same integrity reason as
        ``fields``.
    confidence:
        Normalized float in ``[0.0, 1.0]``. See the confidence-
        normalization rule in this module's docstring — the mapping is
        an unverified assumption, deliberately documented as such.
    cost:
        Observed USD spent on this call (``float ≥ 0.0``). This is the
        actual metered spend the adapter reports, not an estimate —
        estimates live on ``CostModel`` for routing, not on the result.
    latency:
        Observed wall-clock for the provider call, in **milliseconds**
        (``int ≥ 0``). Milliseconds (not seconds) because sub-second
        latencies matter for routing and seconds lose precision.
    provider:
        Provider identity string (e.g. ``"exa"``, ``"parallel"``).
        Present for audit/routing telemetry. The type does NOT embed
        provider-specific STRUCTURE — ``provider`` is a label, not a
        branch key; the normalized fields above are identical for
        every provider.
    tier:
        The provider tier used (e.g. ``"deep"``, ``"deep-reasoning"``,
        ``"basic"``, ``"ultra8x"``). Records which tier the router
        selected for this call.
    raw_ref:
        Opaque ``RawRef`` handle to the stored raw provider payload,
        for audit. See ``RawRef`` — never a provider-specific dict.
    """

    fields: Mapping[str, str | None]
    field_citations: Mapping[str, tuple[Source, ...]]
    confidence: float
    cost: float
    latency: int
    provider: str
    tier: str
    raw_ref: RawRef

    def __post_init__(self) -> None:
        # Defensive deep-freeze (grok co-CEO D4): ``@dataclass(frozen=True)``
        # freezes the field *bindings* but NOT nested ``dict``/``list`` — a
        # caller could mutate ``fields`` or ``field_citations`` after return
        # and break the "every non-null field has >=1 citation" invariant
        # without the adapter knowing. Wrap caller-supplied mutable mappings
        # in read-only ``MappingProxyType`` and freeze citation lists to
        # ``tuple`` so post-construction mutation raises ``TypeError``. This
        # is the integrity guarantee INV-4 audits rely on. ``object.__setattr__``
        # bypasses the frozen-dataclass setter guard for these fields.
        object.__setattr__(
            self, "fields", MappingProxyType(dict(self.fields))
        )
        object.__setattr__(
            self,
            "field_citations",
            MappingProxyType(
                {k: tuple(v) for k, v in self.field_citations.items()}
            ),
        )


@dataclass(frozen=True)
class CostModel:
    """Per-tier cost estimate for routing decisions.

    The router (SPR-07) selects a provider/tier from this metadata
    ALONE, without importing any adapter. ``cost_usd_estimate`` is a
    back-of-envelope estimate (the same idiom as
    ``acquisition/search/exa/client.py``'s ``COST_PER_SEARCH_USD``) —
    the authoritative cost is what ``ResearchResult.cost`` reports
    after the call. Estimates let the router budget; results let it
    reconcile.

    ``latency_ms_estimate`` is a p50-ish guess for the same purpose.
    """

    tier: str
    cost_usd_estimate: float
    latency_ms_estimate: int


__all__ = [
    "CostModel",
    "RawRef",
    "ResearchResult",
    "Source",
]
