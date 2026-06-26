"""In-memory ``StubResearchProvider`` for tests and the runner seam.

Deterministic: constructed with a fixture map ``sub_question →
ResearchResult``. ``answer`` looks up the sub-question (exact match)
and returns the recorded result. Passes the conformance harness.

This is the reference adapter — it shows the minimal shape a real
adapter (Exa SPR-03, Parallel SPR-04) satisfies and is the provider the
runner-seam test drives to prove the interface is callable without
leaking provider identity.

Not a real provider: no network, no SDK, no cost. The ``cost`` on the
recorded results is whatever the fixture set (usually 0.0); the stub
itself charges nothing.
"""

from __future__ import annotations

from research.providers.base import OutputSchema, ResearchProvider
from research.providers.types import CostModel, ResearchResult


class StubResearchProvider:
    """Deterministic in-memory provider.

    Construct with ``fixtures``: a ``dict[str, ResearchResult]`` keyed by
    the exact ``sub_question`` string ``answer`` will be called with.
    A call for an unrecorded sub-question raises ``KeyError`` (loud — a
    silent fallback would hide test wiring mistakes).
    """

    # ── capability metadata ────────────────────────────────────────
    provider_id: str = "stub"
    supports_async: bool = False
    tiers: tuple[str, ...] = ("basic",)
    cost_model: tuple[CostModel, ...] = (
        CostModel(tier="basic", cost_usd_estimate=0.0, latency_ms_estimate=0),
    )

    def __init__(self, fixtures: dict[str, ResearchResult]) -> None:
        # Copy to prevent the caller mutating the fixture map post-construction.
        self._fixtures = dict(fixtures)

    def answer(
        self,
        sub_question: str,
        output_schema: OutputSchema,
        *,
        tier: str | None = None,
    ) -> ResearchResult:
        if tier is not None and tier not in self.tiers:
            raise ValueError(
                f"stub: tier {tier!r} not in supported tiers {self.tiers}"
            )
        try:
            result = self._fixtures[sub_question]
        except KeyError as e:
            raise KeyError(
                f"stub: no fixture recorded for sub_question {sub_question!r}"
            ) from e
        # Return the recorded result verbatim — the fixture is responsible
        # for being conformant (the conformance harness enforces this).
        return result


__all__ = ["StubResearchProvider"]
