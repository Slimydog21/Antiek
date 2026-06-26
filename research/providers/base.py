"""The ``ResearchProvider`` interface — the adapter boundary for engines.

This is the contract every deep-research engine (Exa Deep, Parallel,
future providers) implements. It is a ``Protocol`` with
``runtime_checkable`` to match the codebase idiom
(``substrate/contracts/reading_surface.py``: ``ReaderSurfaceContract``;
``runtime/research_runner/protocol.py``: ``ResearchRunner``). A
``Protocol`` is the right choice over ``abc.ABC`` here because the
contract layer already uses structural typing for seams — adapters are
checked for *shape conformance* (does it have ``answer`` + the
capability attributes) rather than *inheritance* (does it subclass a
base), which keeps adapters decoupled from a base class and matches how
``ResearchRunner`` is already declared.

Invariants (load-bearing — copied verbatim from the spec)
---------------------------------------------------------

INV-1 · One owner. The research-execution layer has exactly one owner — the ResearchRunner. Exa Deep and Parallel are tools behind ResearchProvider; no module outside the adapter package imports an engine SDK.

INV-4 · Normalized contract. Every provider returns the same normalized shape. The runner never branches on a raw provider payload above the adapter boundary.

What this module does NOT do
----------------------------
* No provider SDK import anywhere in this file (INV-1). ``base.py``
  imports only ``types`` from this package and stdlib. A grep for
  ``exa`` or ``parallel`` in this module returns nothing.
* No provider name in a conditional. There is no ``if provider ==
  "exa"`` anywhere here — provider selection is the router's job
  (SPR-07), and it chooses from the capability metadata below.
* No retry / timeout / budget wrapping (SPR-05/06). The interface
  defines the call; it does not wrap it in resilience.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from research.providers.types import CostModel, ResearchResult

# A sub-question's output schema. Typed loosely (``object``) rather than
# pinned to a specific schema class so the interface does not couple to
# one schema library (the codebase uses Pydantic v2 for events but the
# cascade planner's outputSchema is a plain JSON-schema dict today).
# Adapters receive it verbatim and map its keys to ``ResearchResult.fields``.
OutputSchema = object


@runtime_checkable
class ResearchProvider(Protocol):
    """The adapter boundary a research engine implements.

    Call contract
    -------------
    ``answer(self, sub_question: str, output_schema: OutputSchema, *,
    tier: str | None = None) -> ResearchResult``

    * ``sub_question`` — the focused question this call answers. One
      sub-question → one ``ResearchResult`` (one set of fields keyed by
      ``output_schema``).
    * ``output_schema`` — the sub-question's output schema (a JSON-schema
      dict today). Its keys map to ``ResearchResult.fields`` keys. The
      adapter does NOT validate the result against the schema (that is a
      downstream concern); it populates the keys it can.
    * ``tier`` — optional override of the provider tier. When ``None``,
      the adapter picks a default from its own ``tiers``. Must be a
      member of ``self.tiers`` or the adapter raises ``ValueError``.
    * Returns a ``ResearchResult`` — the normalized shape (INV-4).

    Capability metadata
    -------------------
    The router (SPR-07) selects provider/tier from these attributes
    ALONE, without importing any adapter:

    * ``provider_id: str`` — stable identity (e.g. ``"exa"``,
      ``"parallel"``).
    * ``supports_async: bool`` — whether the adapter offers an async
      call (``answer_async``). Sync ``answer`` is always present.
    * ``tiers: tuple[str, ...]`` — the tiers this provider offers
      (e.g. ``("deep", "deep-reasoning")``). The router picks from
      this; ``tier=`` to ``answer`` must be one of these.
    * ``cost_model: tuple[CostModel, ...]`` — per-tier cost +
      latency estimates for routing. One ``CostModel`` per tier in
      ``tiers``, same order.
    """

    # ── capability metadata (class attrs or properties) ────────────
    provider_id: str
    supports_async: bool
    tiers: tuple[str, ...]
    cost_model: tuple[CostModel, ...]

    # ── the call ───────────────────────────────────────────────────
    def answer(
        self,
        sub_question: str,
        output_schema: OutputSchema,
        *,
        tier: str | None = None,
    ) -> ResearchResult: ...


__all__ = [
    "OutputSchema",
    "ResearchProvider",
]
