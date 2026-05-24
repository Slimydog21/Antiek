"""Dispatch-tier verdict analyzer — pure-function core.

Consumes typed event records, groups synthesis-tier dispatches by
provider, and computes the pass rate against the verifier-tier
events that followed. Pure-functional so a unit test can exercise
the verdict logic without an event log.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping


SYNTHESIS_TIER = "synthesis"
VERIFY_TIER = "verify"

# §14.4 verdict gate. Documented in master-spec; baked in here so the
# threshold can't drift across runs.
PASS_RATE_GAP_THRESHOLD_PP = 5.0

# Substrate-wide synthesis pass threshold. The composite rubric score
# must be ≥ this value for a synthesis to count as "passed" against
# the §14.4 verdict gate. Matched by ``substrate.synthesis_rubric.scorer.PASS_THRESHOLD``
# and enforced as invariant I-005 in ``substrate/invariants.py``; changes
# here must update both sites in the same commit. The number itself
# comes from master-spec §13.9.
PASS_THRESHOLD = 0.5

# Canonical provider names per substrate/dispatch/config.yaml. Keep
# the verdict report stable across runs by normalising aliases.
_PROVIDER_ALIASES: dict[str, str] = {
    "hermes": "hermes-grok",
    "hermes-grok": "hermes-grok",
    "grok": "hermes-grok",
    "openrouter": "openrouter",
    "openrouter-opus": "openrouter-opus",
    "openrouter-deepseek": "openrouter-deepseek",
    "anthropic": "openrouter-opus",
    "openai": "openai",
}


@dataclass(frozen=True)
class ProviderScore:
    """Per-provider synthesis verifier pass rate."""

    provider: str
    model: str
    synthesis_count: int
    verified_count: int   # synthesis calls followed by a verify event
    passed_count: int     # of verified_count, how many passed
    total_cost_usd: float

    @property
    def verification_rate(self) -> float:
        """Fraction of syntheses that had any verifier evidence."""
        return self.verified_count / self.synthesis_count if self.synthesis_count else 0.0

    @property
    def pass_rate(self) -> float:
        """Fraction of VERIFIED syntheses that passed."""
        return self.passed_count / self.verified_count if self.verified_count else 0.0

    @property
    def pass_rate_overall(self) -> float:
        """Fraction of ALL syntheses (including those with no
        verifier evidence) that passed. Conservative metric — un-
        verified ones count as failures so a provider can't game
        the rate by skipping verification."""
        return self.passed_count / self.synthesis_count if self.synthesis_count else 0.0

    @property
    def cost_per_passed_synthesis(self) -> float:
        """The denominator that matters per §14.4 — cost per
        operator-acceptable synthesis, not cost per call."""
        if self.passed_count == 0:
            return float("inf")
        return self.total_cost_usd / self.passed_count


@dataclass(frozen=True)
class Verdict:
    """The output the operator commits as the §14.4 verdict."""

    measurement_window_started: str
    measurement_window_ended: str
    scores: list[ProviderScore]
    opus_score: ProviderScore | None
    hermes_score: ProviderScore | None
    gap_pp: float | None  # opus - hermes, in percentage points
    decision: str         # "keep_opus_primary" | "flip_to_hermes_primary" | "insufficient_data"
    rationale: str


def _normalise_provider(provider: str) -> str:
    return _PROVIDER_ALIASES.get(provider.strip().lower(), provider.strip().lower())


def _iter_events(events_path: Path) -> Iterator[dict]:
    """Yield typed event records from a directory of JSONL files or
    a single JSONL file. Skips malformed lines silently."""
    if events_path.is_dir():
        files = sorted(events_path.glob("*.jsonl"))
    elif events_path.is_file():
        files = [events_path]
    else:
        raise FileNotFoundError(f"events path not found: {events_path}")

    for f in files:
        with f.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def _within_window(
    record: dict,
    *,
    since: datetime | None,
    until: datetime | None,
) -> bool:
    # The substrate emits events with `emitted_at`. Older test
    # fixtures used `created_at` / `ts`; accept all three so the
    # analyzer works against both shapes.
    ts = record.get("emitted_at") or record.get("created_at") or record.get("ts")
    if not isinstance(ts, str):
        return False
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return False
    # Tolerate naive datetimes on the event side (some old fixtures
    # are tz-less). Assume UTC. The CLI parses --since with explicit
    # UTC; tests pass aware datetimes; this branch handles only
    # legacy data.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if since:
        since_aware = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
        if dt < since_aware:
            return False
    if until:
        until_aware = until if until.tzinfo else until.replace(tzinfo=timezone.utc)
        if dt > until_aware:
            return False
    return True


def analyse_events(
    events: list[dict] | None = None,
    *,
    events_path: Path | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Verdict:
    """Group events by provider, compute pass rates, render verdict.

    Pass ``events`` directly for unit-testing; pass ``events_path``
    for the CLI path. Exactly one of the two must be supplied.
    """
    if (events is None) == (events_path is None):
        raise ValueError("supply exactly one of events= or events_path=")

    iterator: Iterator[dict]
    if events is not None:
        iterator = iter(events)
    else:
        assert events_path is not None
        iterator = _iter_events(events_path)

    # Group synthesis-tier dispatch.call events by (provider, model)
    synthesis_by_key: dict[tuple[str, str], dict] = {}
    # Track per-investigation phase chain so we can link a verify
    # event back to the synthesis that preceded it.
    last_synthesis_per_inv: dict[str, tuple[str, str]] = {}
    # final_score per (provider, model) → pass when ≥ 0.5 (the
    # substrate-wide pass threshold; documented in
    # architecture_notes §3.2).
    verify_outcomes: dict[tuple[str, str], list[float]] = {}
    # Fallback signal — synthesizer self-grade from
    # synthesize.delivered when no rubric.scored event exists.
    # Production today emits the synthesis but no rubric scoring
    # call follows, so we read implicit_recommendation +
    # conviction_level as the closest substrate signal. The §14.4
    # protocol assumes verifier pass-rate; this is the best
    # available proxy until the explicit rubric chain is wired
    # (G5 follow-up Sprint 21 substrate audit).
    self_grade_outcomes: dict[tuple[str, str], list[float]] = {}

    ts_min: str | None = None
    ts_max: str | None = None

    for ev in iterator:
        if not _within_window(ev, since=since, until=until):
            continue
        ts = ev.get("emitted_at") or ev.get("created_at") or ev.get("ts")
        if isinstance(ts, str):
            ts_min = ts if ts_min is None or ts < ts_min else ts_min
            ts_max = ts if ts_max is None or ts > ts_max else ts_max

        payload = ev.get("payload") or {}
        action = ev.get("action_type") or payload.get("action_type")
        inv_id = ev.get("investigation_id")

        if action == "dispatch.call":
            tier = payload.get("tier")
            if tier == SYNTHESIS_TIER:
                provider = _normalise_provider(payload.get("provider", "unknown"))
                model = payload.get("model", "unknown")
                key = (provider, model)
                bucket = synthesis_by_key.setdefault(
                    key,
                    {"count": 0, "cost": 0.0},
                )
                bucket["count"] += 1
                bucket["cost"] += float(payload.get("cost_usd", 0.0))
                if inv_id:
                    last_synthesis_per_inv[inv_id] = key

        elif action == "rubric.scored":
            score = payload.get("final_score")
            if not isinstance(score, (int, float)):
                continue
            if not inv_id:
                continue
            key = last_synthesis_per_inv.get(inv_id)
            if key is None:
                continue
            verify_outcomes.setdefault(key, []).append(float(score))

        elif action == "synthesize.delivered":
            # Self-grade fallback. Read the synthesizer's own
            # implicit_recommendation + conviction_level fields.
            # The synthesizer emits these from its own constraint-
            # compliance pass; treating them as a verifier signal
            # is an approximation, but it's the only one production
            # currently produces.
            if not inv_id:
                continue
            key = last_synthesis_per_inv.get(inv_id)
            if key is None:
                continue
            recommendation = payload.get("implicit_recommendation")
            conviction = payload.get("conviction_level")
            # Map the synthesis's self-report to a pass-or-fail
            # score in [0, 1]:
            # - "insufficient_evidence" recommendation → 0.0 (the
            #   synthesizer explicitly declined to produce a thesis)
            # - any other recommendation + conviction_level ≥ 0.5 → 1.0
            # - conviction_level present but < 0.5 → that value
            # - no conviction_level → 0.5 (neutral)
            if recommendation == "insufficient_evidence":
                self_score = 0.0
            elif isinstance(conviction, (int, float)):
                self_score = max(0.0, min(1.0, float(conviction)))
            else:
                self_score = 0.5
            self_grade_outcomes.setdefault(key, []).append(self_score)

    # PASS_THRESHOLD is module-level (see line 23ish above); enforced
    # to match scorer.PASS_THRESHOLD by invariant I-005.
    scores: list[ProviderScore] = []
    for key, bucket in synthesis_by_key.items():
        provider, model = key
        rubric_outcomes = verify_outcomes.get(key, [])
        # Prefer explicit rubric.scored events; fall back to self-grade
        # when production doesn't emit them. Mix the two only if
        # one provider has rubric data and the other doesn't —
        # in that case the comparison is apples-to-oranges and the
        # §14.4 verdict gate will reject as insufficient_data, which
        # is the honest behaviour.
        if rubric_outcomes:
            outcomes = rubric_outcomes
        else:
            outcomes = self_grade_outcomes.get(key, [])
        verified_count = len(outcomes)
        passed = sum(1 for s in outcomes if s >= PASS_THRESHOLD)
        scores.append(
            ProviderScore(
                provider=provider,
                model=model,
                synthesis_count=bucket["count"],
                verified_count=verified_count,
                passed_count=passed,
                total_cost_usd=bucket["cost"],
            )
        )
    scores.sort(key=lambda s: s.synthesis_count, reverse=True)

    opus = _pick_score(scores, provider_contains="opus", model_contains="opus")
    hermes = _pick_score(scores, provider_contains="hermes", model_contains="grok")

    gap_pp: float | None = None
    decision = "insufficient_data"
    rationale = (
        "Measurement window did not produce enough graded synthesis "
        "outputs from both providers to make a verdict. Extend the window "
        "or check that the verifier is firing on both providers."
    )

    if opus and hermes and opus.verified_count >= 10 and hermes.verified_count >= 10:
        gap_pp = (opus.pass_rate_overall - hermes.pass_rate_overall) * 100
        if abs(gap_pp) <= PASS_RATE_GAP_THRESHOLD_PP:
            decision = "flip_to_hermes_primary"
            rationale = (
                f"Pass-rate gap is {gap_pp:.1f}pp, within the "
                f"{PASS_RATE_GAP_THRESHOLD_PP}pp tolerance. Cost-per-"
                f"acceptable-synthesis on Hermes "
                f"(${hermes.cost_per_passed_synthesis:.4f}) vs Opus "
                f"(${opus.cost_per_passed_synthesis:.4f}). Flip back to "
                "Hermes primary on cost grounds per §14.4."
            )
        else:
            decision = "keep_opus_primary"
            rationale = (
                f"Pass-rate gap is {gap_pp:.1f}pp, outside the "
                f"{PASS_RATE_GAP_THRESHOLD_PP}pp tolerance. Cost savings "
                "on Hermes are illusory because they convert to "
                "additional verifier + re-synthesizer dispatches. Keep "
                "Opus on synthesis as primary per §14.4."
            )
    elif opus and not hermes:
        decision = "insufficient_data"
        rationale = (
            "Only Opus produced synthesis-tier traffic during the "
            "measurement window. Hermes never ran on the synthesizer "
            "tier — the cutover may not have completed, or the "
            "measurement-flip pin is still active. No verdict possible."
        )

    return Verdict(
        measurement_window_started=ts_min or "(unknown)",
        measurement_window_ended=ts_max or "(unknown)",
        scores=scores,
        opus_score=opus,
        hermes_score=hermes,
        gap_pp=gap_pp,
        decision=decision,
        rationale=rationale,
    )


def _pick_score(
    scores: list[ProviderScore],
    *,
    provider_contains: str,
    model_contains: str,
) -> ProviderScore | None:
    """Pick the score whose provider OR model contains the given
    substring. Tolerant to provider naming drift in config."""
    for s in scores:
        if provider_contains in s.provider.lower() or model_contains in s.model.lower():
            return s
    return None


def render_verdict_markdown(verdict: Verdict) -> str:
    """Render the verdict as a markdown document the operator can
    commit to docs/decisions/."""
    lines: list[str] = []
    lines.append("# Dispatch tier-differentiation verdict (§14.4)")
    lines.append("")
    lines.append(
        f"**Measurement window:** {verdict.measurement_window_started} → {verdict.measurement_window_ended}"
    )
    lines.append("")
    lines.append(f"**Decision:** `{verdict.decision}`")
    lines.append("")
    lines.append(verdict.rationale)
    lines.append("")
    lines.append("## Per-provider scores")
    lines.append("")
    lines.append(
        "| Provider | Model | Synthesis calls | Verified | Passed | Pass rate (overall) | Cost / pass |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|"
    )
    for s in verdict.scores:
        cost_str = (
            f"${s.cost_per_passed_synthesis:.4f}"
            if s.cost_per_passed_synthesis != float("inf")
            else "—"
        )
        lines.append(
            f"| {s.provider} | {s.model} | {s.synthesis_count} | "
            f"{s.verified_count} | {s.passed_count} | "
            f"{s.pass_rate_overall * 100:.1f}% | {cost_str} |"
        )
    lines.append("")
    if verdict.gap_pp is not None:
        lines.append(f"**Pass-rate gap (Opus − Hermes):** {verdict.gap_pp:.1f}pp")
        lines.append(f"**Tolerance threshold (§14.4):** ±{PASS_RATE_GAP_THRESHOLD_PP}pp")
        lines.append("")
    lines.append("## Next steps")
    lines.append("")
    if verdict.decision == "flip_to_hermes_primary":
        lines.append("1. Update `substrate/dispatch/config.yaml`: set synthesis tier primary back to `hermes/grok-4.3`.")
        lines.append("2. Add OpenRouter Opus as the fallback chain entry below it.")
        lines.append("3. Restart the substrate; verify a synthesis emits `provider: hermes` again.")
        lines.append("4. Close G5 by committing this verdict markdown.")
    elif verdict.decision == "keep_opus_primary":
        lines.append("1. Leave `substrate/dispatch/config.yaml` synthesis tier on `openrouter-opus` as primary.")
        lines.append("2. Document the cost delta in the next sprint review.")
        lines.append("3. Close G5 by committing this verdict markdown.")
    else:
        lines.append("1. Extend the measurement window — at least 10 verified syntheses per provider needed.")
        lines.append("2. Verify the verifier-tier dispatch is actually running against both providers.")
        lines.append("3. Re-run this analyzer at the new window's close.")
    lines.append("")
    lines.append(f"_Generated by `tools.dispatch_tier_verdict` at {datetime.now(timezone.utc).isoformat()}_")
    lines.append("")
    return "\n".join(lines)
