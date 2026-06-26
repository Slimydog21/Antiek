"""Reusable conformance harness for ``ResearchProvider``.

A provider-parameterized suite that asserts the normalized contract
holds on a given (provider, fixture) pair. Raises ``ConformanceError``
naming the violated invariant on any breach — never a bare
``AssertionError`` (a harness that fails with ``AssertionError`` makes
the failure opaque; the invariant that broke must be legible in the
message so the adapter author knows what to fix).

Usage
-----
    from research.providers.conformance import conformance
    conformance(my_provider, fixture={"sub_question": "...",
                                      "output_schema": {...},
                                      "expected_fields": {...}})

The harness calls ``provider.answer(...)`` against the fixture's
``sub_question`` and ``output_schema``, then validates the returned
``ResearchResult``. For deterministic round-trip, the fixture may carry
``expected_fields`` / ``expected_confidence``; when present the harness
checks the result matches (modulo explicitly-allowed non-determinism,
see ``allow_non_deterministic`` on the fixture).

What the harness asserts
------------------------
1. ``answer`` returns a ``ResearchResult`` with all required fields
   populated (no ``None`` for ``fields`` / ``field_citations`` /
   ``confidence`` / ``cost`` / ``latency`` / ``provider`` / ``tier`` /
   ``raw_ref``).
2. **INV-4 citation invariant:** every non-null, non-empty field in
   ``fields`` has ≥1 citation in ``field_citations``.
3. ``confidence`` is a float in ``[0.0, 1.0]``.
4. ``cost`` is a float ``≥ 0.0`` and is populated (not ``None``).
5. ``latency`` is an int ``≥ 0`` and is populated.
6. ``provider`` and ``tier`` are non-empty strings.
7. ``raw_ref`` is a ``RawRef`` with a non-empty ``handle`` and
   ``provider``.
8. ``tier`` is a member of ``provider.tiers``.
9. ``provider.provider_id`` is a non-empty string.
10. ``provider.cost_model`` has one ``CostModel`` per tier, same tiers.
11. Deterministic round-trip: when ``expected_fields`` is present, the
    result's non-null fields match (unless ``allow_non_deterministic``).
"""

from __future__ import annotations

from typing import Any

from research.providers.base import ResearchProvider
from research.providers.types import RawRef, ResearchResult, Source


class ConformanceError(Exception):
    """Raised when a provider breaches the normalized contract.

    The message always names the violated invariant (``INV-1`` / ``INV-4``)
    plus the specific field/check that failed, so a failure is legible
    in CI output without reading the harness source.
    """


def _fail(invariant: str, detail: str) -> None:
    raise ConformanceError(f"{invariant}: {detail}")


def conformance(
    provider: ResearchProvider,
    fixture: dict[str, Any],
) -> None:
    """Run the conformance suite against ``provider`` on ``fixture``.

    Raises ``ConformanceError`` on the first violation. Returns
    ``None`` on success (a pass is silent — the suite is called for its
    side effect of raising; a loud pass would just be noise in CI).

    ``fixture`` keys:
    * ``sub_question`` (str) — the question to ask.
    * ``output_schema`` (object) — the schema to pass to ``answer``.
    * ``tier`` (str | None) — optional tier override.
    * ``expected_fields`` (dict | None) — if present, the result's
      non-null fields must match these values (deterministic round-trip).
    * ``allow_non_deterministic`` (bool) — when True, the
      ``expected_fields`` check is skipped (for providers whose answers
      legitimately vary call-to-call). Default False.
    * ``expected_confidence`` (float | None) — if present, the result's
      confidence must equal this (deterministic round-trip).
    """
    # ── capability-metadata checks (the router trusts these) ───────
    _check_capability_metadata(provider)

    # ── call the provider ──────────────────────────────────────────
    sub_question = fixture["sub_question"]
    output_schema = fixture.get("output_schema")
    tier = fixture.get("tier")
    try:
        result = provider.answer(sub_question, output_schema, tier=tier)
    except Exception as e:
        _fail("INV-4", f"answer() raised instead of returning a ResearchResult: "
                        f"{type(e).__name__}: {e}")

    # ── result-type validity ───────────────────────────────────────
    if not isinstance(result, ResearchResult):
        _fail("INV-4", f"answer() returned {type(result).__name__}, "
                        f"not ResearchResult")
    _check_result_shape(result, provider)
    _check_citations(result)
    _check_confidence(result)
    _check_cost(result)
    _check_latency(result)
    _check_provider_tier(result, provider)
    _check_raw_ref(result)

    # ── deterministic round-trip (modulo allowed non-determinism) ──
    if not fixture.get("allow_non_deterministic", False):
        _check_deterministic_round_trip(result, fixture)


def _check_capability_metadata(p: ResearchProvider) -> None:
    # provider_id
    pid = getattr(p, "provider_id", None)
    if not isinstance(pid, str) or not pid.strip():
        _fail("INV-1", f"provider_id must be a non-empty string, got {pid!r}")
    # supports_async
    sa = getattr(p, "supports_async", None)
    if not isinstance(sa, bool):
        _fail("INV-1", f"supports_async must be bool, got {type(sa).__name__}")
    # tiers
    tiers = getattr(p, "tiers", None)
    if not isinstance(tiers, tuple) or not tiers or not all(
        isinstance(t, str) and t for t in tiers
    ):
        _fail("INV-1", f"tiers must be a non-empty tuple[str, ...], got {tiers!r}")
    # cost_model: one CostModel per tier, matching tiers, same order
    cm = getattr(p, "cost_model", None)
    if not isinstance(cm, tuple) or len(cm) != len(tiers):
        _fail("INV-1", f"cost_model must have one entry per tier "
                        f"({len(tiers)}), got {len(cm) if isinstance(cm, tuple) else cm!r}")
    for i, (tier, model) in enumerate(zip(tiers, cm)):
        from research.providers.types import CostModel
        if not isinstance(model, CostModel):
            _fail("INV-1", f"cost_model[{i}] must be a CostModel, got "
                            f"{type(model).__name__}")
        if model.tier != tier:
            _fail("INV-1", f"cost_model[{i}].tier={model.tier!r} does not match "
                            f"tiers[{i}]={tier!r}")
        if model.cost_usd_estimate < 0:
            _fail("INV-1", f"cost_model[{i}].cost_usd_estimate must be ≥ 0, "
                            f"got {model.cost_usd_estimate}")
        if model.latency_ms_estimate < 0:
            _fail("INV-1", f"cost_model[{i}].latency_ms_estimate must be ≥ 0, "
                            f"got {model.latency_ms_estimate}")


def _check_result_shape(r: ResearchResult, p: ResearchProvider) -> None:
    if not isinstance(r.fields, dict):
        _fail("INV-4", f"fields must be dict, got {type(r.fields).__name__}")
    # fields values are typed ``str | None`` (the contract). Enforce it so a
    # non-string, non-None value (e.g. an int or a nested dict smuggling
    # provider structure) cannot pass the harness — that would be both a
    # type-contract breach and an INV-4 leak vector (a dict value could carry
    # provider-specific structure). ``None`` and ``""`` are the documented
    # "unpopulated" sentinels; everything else must be a plain string.
    for k, v in r.fields.items():
        if not isinstance(k, str):
            _fail("INV-4", f"fields key {k!r} must be a string")
        if v is None:
            continue
        if not isinstance(v, str):
            _fail("INV-4", f"fields[{k!r}] must be str or None, got "
                            f"{type(v).__name__} — non-string field values are "
                            f"not part of the normalized contract")
    if not isinstance(r.field_citations, dict):
        _fail("INV-4", f"field_citations must be dict, got "
                        f"{type(r.field_citations).__name__}")
    for k, v in r.field_citations.items():
        if not isinstance(k, str):
            _fail("INV-4", f"field_citations key {k!r} must be a string")
        if not isinstance(v, list):
            _fail("INV-4", f"field_citations[{k!r}] must be a list, got "
                            f"{type(v).__name__}")
        for s in v:
            if not isinstance(s, Source):
                _fail("INV-4", f"field_citations[{k!r}] contains a non-Source: "
                                f"{type(s).__name__}")


def _check_citations(r: ResearchResult) -> None:
    """INV-4: every non-null, non-empty field MUST have ≥1 citation."""
    for fname, fval in r.fields.items():
        if fval is None:
            continue
        if isinstance(fval, str) and fval == "":
            continue
        cites = r.field_citations.get(fname, [])
        if len(cites) < 1:
            _fail("INV-4", f"field {fname!r} has a value ({fval!r}) but no "
                            f"citation — a populated field must cite ≥1 source")
        # every cited source must have a non-empty url
        for s in cites:
            if not s.url or not s.url.strip():
                _fail("INV-4", f"field {fname!r} cites a Source with an empty url")


def _check_confidence(r: ResearchResult) -> None:
    if not isinstance(r.confidence, (int, float)):
        _fail("INV-4", f"confidence must be a float, got "
                        f"{type(r.confidence).__name__}")
    if not (0.0 <= float(r.confidence) <= 1.0):
        _fail("INV-4", f"confidence {r.confidence} is out of range [0.0, 1.0]")


def _check_cost(r: ResearchResult) -> None:
    if not isinstance(r.cost, (int, float)):
        _fail("INV-4", f"cost must be a float, got {type(r.cost).__name__}")
    if r.cost < 0:
        _fail("INV-4", f"cost {r.cost} must be ≥ 0")


def _check_latency(r: ResearchResult) -> None:
    if not isinstance(r.latency, int) or isinstance(r.latency, bool):
        _fail("INV-4", f"latency must be an int (ms), got "
                        f"{type(r.latency).__name__}")
    if r.latency < 0:
        _fail("INV-4", f"latency {r.latency} must be ≥ 0")


def _check_provider_tier(r: ResearchResult, p: ResearchProvider) -> None:
    if not isinstance(r.provider, str) or not r.provider.strip():
        _fail("INV-4", f"result.provider must be a non-empty string, got "
                        f"{r.provider!r}")
    if not isinstance(r.tier, str) or not r.tier.strip():
        _fail("INV-4", f"result.tier must be a non-empty string, got {r.tier!r}")
    if r.tier not in p.tiers:
        _fail("INV-4", f"result.tier {r.tier!r} is not in provider.tiers "
                        f"{p.tiers}")


def _check_raw_ref(r: ResearchResult) -> None:
    if not isinstance(r.raw_ref, RawRef):
        _fail("INV-4", f"raw_ref must be a RawRef, got "
                        f"{type(r.raw_ref).__name__}")
    if not r.raw_ref.handle or not r.raw_ref.handle.strip():
        _fail("INV-4", f"raw_ref.handle must be a non-empty string, got "
                        f"{r.raw_ref.handle!r}")
    if not r.raw_ref.provider or not r.raw_ref.provider.strip():
        _fail("INV-4", f"raw_ref.provider must be a non-empty string, got "
                        f"{r.raw_ref.provider!r}")


def _check_deterministic_round_trip(
    r: ResearchResult, fixture: dict[str, Any]
) -> None:
    expected_fields = fixture.get("expected_fields")
    if expected_fields is not None:
        for k, expected in expected_fields.items():
            actual = r.fields.get(k)
            if actual != expected:
                _fail("INV-4", f"deterministic round-trip mismatch on field "
                                f"{k!r}: expected {expected!r}, got {actual!r}")
    expected_conf = fixture.get("expected_confidence")
    if expected_conf is not None:
        if abs(float(r.confidence) - float(expected_conf)) > 1e-9:
            _fail("INV-4", f"deterministic round-trip mismatch on confidence: "
                            f"expected {expected_conf}, got {r.confidence}")


__all__ = [
    "ConformanceError",
    "conformance",
]
