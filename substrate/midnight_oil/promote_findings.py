"""Promote a completed Midnight Oil run's findings into the knowledge substrate (ask #13).

The operator's ask #13: *"...an autonomous research sub-agent swarm mode
('midnight oil') where users can engage in a deep research without needing to be
in the workstation; all they need to do is set a time of work and goals (and the
system provides a user a recommended price ceiling to approve) then the agent
goes off to execute that task."* The trust loop is built and complete:

  estimate (#1849) → approve (#1842 gate) → plan (#1854) → launch brief (#1876)
  → swarm → receipt (#1867)

But the receipt is the **delivery** surface — it carries each phase's findings as
opaque ``finding_refs`` (ids the execution layer resolves to real artifacts) and
stops there. **Nothing turns a finished unattended run into a first-class
knowledge artifact** the operator can merge into a reading asset (#1837), promote
into the graph (#1847), or distill into a twin (#1836). So the MO loop deposits
findings into a receipt and they never enter the knowledge substrate — the
operator's "the agent goes off to execute that task" implies the results come
BACK. **This module is that return path.** It is the loop-closer: completed run →
``ResearchArtifactBody`` (the canonical knowledge-asset format every merge/promote/
twin substrate already consumes).

**Why produce ``ResearchArtifactBody`` directly.** That schema lives on
``origin/main`` (``substrate/research_artifact/schema.py``) — it is the *stable
authority*, not an off-main sibling. Producing it directly is the
contract-complete API (CEO-DIRECTIVE §3): the merge/promote/twin substrates
consume ``ResearchArtifactBody`` verbatim, so the promotion output plugs in with
zero adaptation. Importing main's schema is correct; the import-free discipline
applies only to *off-main* siblings (which would stack PRs on frozen main).

**Why import-free of #1867.** The receipt ships in a separate off-main PR; hard-
importing ``RunReceipt`` would stack two PRs. Instead this module defines a
compatible :class:`CompletedRun` / :class:`PhaseOutcome` (same field semantics as
``RunReceipt`` / ``PhaseActual``) that the route layer adapts 1:1. The opaque
``finding_refs`` are resolved via an injectable :class:`FindingResolver` protocol
— the pure layer never touches the execution layer's artifact store.

**The load-bearing invariants (each is a test):**

1. **Findings come ONLY from phases that actually ran.** A phase with
   ``ran=False`` (denied by the gate, or skipped) contributes zero findings —
   never fabricated. The promotion is honest about what the swarm *did*, not what
   it was *planned* to do.
2. **An incomplete run withholds synthesis.** When ``completion`` is not
   ``"completed"`` (``stopped_early`` / ``unknown``) the artifact is emitted with
   ``synthesis_withheld=True`` — raw findings, no synthesis claim. An unattended
   run that halted early must not present its partial output as a finished synthesis.
3. **``node_id`` is content-addressed.** Deterministic over the finding's
   resolved text + source, so the same finding promotes to the same graph node
   (dedup, stable identity for #1847's promotion). Two refs resolving to the same
   content produce one insight, not two.
4. **Provenance is carried verbatim.** Every ``finding_ref`` (resolvable or not)
   survives in ``source_event_ids`` — the artifact never loses the link back to
   the execution layer's records, even when a ref can't be resolved to text.
5. **An unresolvable ref is noted, never fabricated.** If the resolver returns
   ``None`` for a ref (artifact not yet materialized, or deleted), no insight is
   invented from the opaque id; the ref stays in ``source_event_ids`` and a count
   of unresolved refs is recorded in ``agent_notes``.
6. **Cost/budget are surfaced verbatim, never fabricated.** ``within_budget`` /
   ``overage_usd`` are carried into ``agent_notes`` as-is; a ``None`` (unknown
   actual spend or unknown ceiling) is recorded as "unknown," never coerced to a
   numeric 0 or a boolean.
7. **Goals compose the ``problem_question``, deterministically.** Empty goals →
   a flagged placeholder, never an empty string (the artifact must state what it
   answered). Goal order is preserved.
8. **Deterministic + pure.** Same run + same resolved findings → byte-identical
   ``ResearchArtifactBody`` (verifiable via ``content_hash()``). No I/O, no clock,
   no dispatch — the resolver is the only external edge and it is injected.
9. **Authority is operator-side.** This module PRODUCES an artifact; it does not
   merge it into a parent, promote it to the graph, or mutate the knowledge base.
   Those are separate authority steps (#1837 / #1847) the operator gates.
10. **The output is a real ``ResearchArtifactBody``.** ``content_hash()`` works,
    the merge/promote/twin substrates consume it unchanged — contract-complete.

**Composition (the MO → knowledge return path):**

    receipt (#1867) ──RunReceipt──┐
                                  ├─→ [THIS] promote_run_findings → ResearchArtifactBody
    finding resolver (injected) ──┘                         │
                                                            ├─→ #1837 merge into reading asset
                                                            ├─→ #1847 promote to graph
                                                            └─→ #1836 distill twin
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)

_COMPLETED = "completed"


class PromoteFindingsError(ValueError):
    """A promotion input violates a load-bearing invariant."""


@dataclass(frozen=True)
class PhaseOutcome:
    """One phase's outcome (compatible with #1867 ``PhaseActual``).

    ``finding_refs`` are opaque ids the injected resolver turns into text.
    ``ran`` is whether the swarm executed this phase (a gate-denied phase has
    ``ran=False`` and must contribute no findings). ``goal_index`` maps the phase
    to its goal in the envelope.
    """

    ordinal: int
    goal_index: int
    ran: bool
    gate_authorized: bool
    finding_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompletedRun:
    """A finished MO run to promote (compatible with #1867 ``RunReceipt``).

    ``completion`` is ``completed`` / ``stopped_early`` / ``unknown``. Cost fields
    are ``None`` when unknown (the promotion never fabricates them). ``run_id`` is
    the stable id (becomes ``investigation_id`` on the artifact).
    """

    run_id: str
    run_label: str
    goals: tuple[str, ...]
    phase_outcomes: tuple[PhaseOutcome, ...]
    completion: str
    within_budget: bool | None = None
    actual_total_usd: float | None = None
    overage_usd: float | None = None


@dataclass(frozen=True)
class ResolvedFinding:
    """One finding's resolved content (the resolver returns this, or ``None``).

    ``text`` is the finding's claim; ``source_ids`` are the provenance ids the
    execution layer vouches for (carried into the insight's ``source_document_id``
    and the artifact's ``source_event_ids``); ``confidence`` is optional (``None``
    when the resolver does not assess it — never fabricated).
    """

    text: str
    source_ids: tuple[str, ...] = ()
    confidence: str | None = None
    open_question: str | None = None


class FindingResolver(Protocol):
    """Resolve an opaque ``finding_ref`` to resolved content, or ``None``.

    The ONE external edge. Implementations call the execution layer's artifact
    store; the pure promotion layer never does. Returning ``None`` means the ref
    is unresolvable (not-yet-materialized / deleted) — the promotion notes it and
    invents nothing.
    """

    def resolve(self, finding_ref: str) -> ResolvedFinding | None: ...


def _content_node_id(text: str, source_ids: tuple[str, ...]) -> str:
    """Deterministic content-addressed node id over (text, sources).

    Same finding content → same node id (dedup + stable graph identity). Uses
    sha256 truncated to 16 hex chars (matching the redaction-width convention;
    this is an identity hash, not a secret).
    """
    blob = text.strip() + "\x1f" + "\x1f".join(source_ids)
    return "mo:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _format_problem_question(goals: Sequence[str]) -> tuple[str, bool]:
    """Compose the artifact's problem_question from the run's goals.

    Returns ``(question, goals_were_empty)``. Empty goals → a flagged placeholder
    (never an empty string); non-empty → a deterministic joined question.
    """
    cleaned = [g.strip() for g in goals if g and g.strip()]
    if not cleaned:
        return "[Midnight Oil run: no goals recorded]", True
    if len(cleaned) == 1:
        return cleaned[0], False
    return " ; ".join(cleaned), False


def _format_budget_note(
    *, within_budget: bool | None, actual_total_usd: float | None, overage_usd: float | None
) -> str:
    """Surface cost/budget verbatim (None → 'unknown', never fabricated)."""
    wb = (
        "within budget"
        if within_budget is True
        else "OVER budget"
        if within_budget is False
        else "budget status unknown"
    )
    spend = (
        f"actual spend ${actual_total_usd:g}"
        if actual_total_usd is not None
        else "actual spend unknown"
    )
    over = (
        f"; overage ${overage_usd:g}"
        if overage_usd is not None and overage_usd > 0
        else "; no overage"
        if overage_usd is not None
        else "; overage unknown"
    )
    return f"{wb}; {spend}{over}"


def promote_run_findings(
    run: CompletedRun,
    resolver: FindingResolver,
) -> ResearchArtifactBody:
    """Promote a completed MO run's findings into a ``ResearchArtifactBody``.

    Findings are resolved from each *ran* phase's ``finding_refs`` via the injected
    ``resolver``; unresolvable refs are noted, not fabricated. An incomplete run
    (``completion != "completed"``) withholds synthesis. Every ref survives in
    ``source_event_ids`` (verbatim provenance). The output is a real
    ``ResearchArtifactBody`` the merge/promote/twin substrates consume unchanged.
    """
    run_id = (run.run_id or "").strip()
    if not run_id:
        raise PromoteFindingsError("CompletedRun.run_id must be non-empty")
    if run.completion not in {"completed", "stopped_early", "unknown"}:
        raise PromoteFindingsError(
            f"completion must be completed/stopped_early/unknown, got {run.completion!r}"
        )

    problem_question, goals_empty = _format_problem_question(run.goals)
    synthesis_withheld = run.completion != _COMPLETED

    insights: list[ArtifactInsight] = []
    questions: list[ArtifactQuestion] = []
    all_refs: list[str] = []
    unresolved = 0
    seen_node_ids: set[str] = set()

    for phase in run.phase_outcomes:
        all_refs.extend(phase.finding_refs)
        if not phase.ran:
            continue  # invariant 1: denied/skipped phase → no findings
        for ref in phase.finding_refs:
            resolved = resolver.resolve(ref)
            if resolved is None:
                unresolved += 1  # invariant 5: noted, not fabricated
                continue
            text = resolved.text.strip()
            if not text:
                unresolved += 1
                continue
            node_id = _content_node_id(text, resolved.source_ids)
            if node_id in seen_node_ids:
                continue  # invariant 3: content-addressed dedup
            seen_node_ids.add(node_id)
            insights.append(
                ArtifactInsight(
                    node_id=node_id,
                    text=text,
                    source_document_id=resolved.source_ids[0] if resolved.source_ids else ref,
                    confidence=resolved.confidence,
                )
            )
            if resolved.open_question and resolved.open_question.strip():
                qid = "mo-q:" + hashlib.sha256(
                    resolved.open_question.strip().encode("utf-8")
                ).hexdigest()[:16]
                questions.append(
                    ArtifactQuestion(
                        node_id=qid,
                        text=resolved.open_question.strip(),
                        escalated=False,
                        reserved_child_investigation_id=None,
                    )
                )

    # invariant 4: every ref survives verbatim (dedup preserves order + uniqueness)
    seen_refs: set[str] = set()
    source_event_ids: list[str] = []
    for ref in all_refs:
        if ref not in seen_refs:
            seen_refs.add(ref)
            source_event_ids.append(ref)

    agent_notes: list[str] = [
        f"produced_by=midnight_oil; run_id={run_id}; run_label={run.run_label!r}",
        f"completion={run.completion}; phase_count={len(run.phase_outcomes)}; "
        f"ran_phases={sum(1 for p in run.phase_outcomes if p.ran)}",
        _format_budget_note(
            within_budget=run.within_budget,
            actual_total_usd=run.actual_total_usd,
            overage_usd=run.overage_usd,
        ),
    ]
    if synthesis_withheld:
        agent_notes.append(
            f"synthesis_withheld=True: run completion={run.completion!r} (not 'completed') — "
            "findings are raw; no synthesis claim"
        )
    if goals_empty:
        agent_notes.append("goals were empty — problem_question is a flagged placeholder")
    if unresolved:
        agent_notes.append(
            f"{unresolved} finding_ref/s unresolvable — kept in source_event_ids; no insight "
            "fabricated from opaque ids"
        )

    return ResearchArtifactBody(
        investigation_id=run_id,
        problem_question=problem_question,
        insights=insights,
        open_questions=questions,
        synthesis_excerpt=None,
        synthesis_withheld=synthesis_withheld,
        source_event_ids=source_event_ids,
        agent_notes=agent_notes,
    )
