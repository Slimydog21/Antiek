"""Unified cost view — per-workflow + aggregate inference cost (SPR-07 M1/M3).

Canonical gate: ``./scripts/canonical_verify.sh unified-cost-consent-surface``
proves cost grouping, margin honesty, no-disbursement separation, and the
Coordination cost/consent UI tests. Live provider billing reconciliation remains
operator proof, not a JSONL fixture claim.

The operator's money question has two halves; this module is the first. It reads
the **canonical cost source** — ``DispatchCall`` events on the investigation
JSONL trajectories — and groups realized spend per workflow (Research / Read /
Write / Speak) and in aggregate. It writes nothing, stores no second copy of
cost, and invents no number: every cent comes off a ``DispatchCallPayload``'s
``cost_usd``, which the dispatch path (and the SPR-02 remote-exec path, via
``runtime/remote_exec/cost.py::record_remote_dispatch``) populates from the
provider's realized cost.

Where the cost comes from (diligence — the exact symbols read):

* ``substrate.event_log.events.trajectory`` / ``action_counts`` — the JSONL
  reader. We enumerate every investigation's events and keep the
  ``DISPATCH_CALL`` rows.
* Each row's ``payload.cost_usd`` is the realized USD spend; ``payload.provider``
  distinguishes a remote-exec leaf (``"daytona"`` / ``"remote_exec"``) from a
  host-local call — *information, not a divergence* (see the SPR-02 cost module's
  docstring). Both are summed; remote-exec is therefore included by construction,
  not special-cased.
* ``payload.target_role`` is the workflow signal. The role→workflow map is the
  Python mirror of the SPR-04 frontend ``workflowTaxonomy.ts`` grouping (Research
  owns the investigation pipeline; Speak owns interviewer capture; Read owns
  wrestling/note-taking roles that bring sources into the substrate). A role we
  cannot classify is bucketed honestly as ``unmapped`` — never silently dropped,
  which would make the aggregate understate spend (rigor #3).

Margins (M1, honesty #1): the Speak economics matrix
(``substrate.speak.economics_mode``) defines the only built external margin —
public output ⇒ 10% inference margin (the algorithmic 70% contributor split is
an *accrual* concern, surfaced by :mod:`substrate.coordination.consent_view`, not
a cost margin), private-published ⇒ 50% margin. The cost event does not carry
project policy, so callers must pass an explicit investigation→Speak-policy map
to apply it. Without that context the view stubs the Speak margin honestly; with
complete context it applies the real matrix per dispatch event. Read's
ad-economics margin is a planned product deliverable; where it is not built we
**stub it honestly** and do NOT fabricate a margined figure on a money screen.

Idle posture (honesty): cost is strictly proportional to emitted ``DispatchCall``
events. An idle instance emits none, so every workflow and the aggregate read
``$0`` — not a fabricated baseline. The zero-event fixture in the tests proves
this.

Invariants this module upholds: single source of truth (reads the event log,
never a second cost store); accrual ≠ disbursement (this module touches no escrow
and imports no payout path — it is *spend*, the other side of the ledger from
accrual); DuckDB single-writer is untouched (read-only over JSONL).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from substrate.event_log.events import (
    default_events_dir,
)
from substrate.event_log.events import (
    trajectory as _trajectory,
)
from substrate.schemas.events import ActionType
from substrate.speak.economics_mode import (
    EconomicsPolicy,
    MARGIN_PRIVATE_PUBLISHED,
    MARGIN_PUBLIC,
    resolve_policy,
)

# ── Workflow enum (mirrors the SPR-04 taxonomy's four workflows) ─────────────

class Workflow(str, Enum):
    """The four product workflows, plus an honest ``UNMAPPED`` bucket for a
    dispatch role the taxonomy does not yet classify. ``UNMAPPED`` is the
    rigor-#3 guard: an unclassified role's cost is still summed into the
    aggregate (so spend is never understated), but it is shown apart so the
    operator can see classification is incomplete rather than silently wrong."""

    RESEARCH = "research"
    READ = "read"
    WRITE = "write"
    SPEAK = "speak"
    UNMAPPED = "unmapped"


# ── role → workflow map (the Python mirror of workflowTaxonomy.ts) ───────────
#
# The frontend taxonomy classifies MODES; dispatch events carry ROLES. This map
# is the role-level mirror of that same product decision, grounded in
# substrate/constants.py::ROLES + the one out-of-catalog role Speak emits
# (``interviewer``, used in substrate/speak/interviewer_capture.py with
# role='interviewer'). Each entry is editorial (which workflow story does this
# role serve?), exactly as the frontend map is editorial; the *coverage* is
# mechanical — a role not here lands in UNMAPPED and the cost is still counted.
#
#   • RESEARCH — the investigation pipeline (decompose → retrieve → connect →
#     synthesize → verify), the user agent driving it, and the rule-based
#     tier_assigner / constraint_checker that gate it. This is the bulk of
#     today's spend.
#   • READ — the wrestling-loop roles that bring sources INTO the substrate and
#     think about them: note_taker (background note-emergence during wrestling),
#     challenger (adversarial questioner during wrestling), grounder
#     (grounding-check). The frontend taxonomy puts the wrestling surface in
#     Read; these are its inference roles.
#   • SPEAK — interview-as-acquisition. ``interviewer`` is the capture role
#     (out of the ROLES catalog by design — it is a Speak product role).
#   • WRITE — creative_writer generates section prose from attached lego blocks.
#     It shares the synthesis tier for quality, but spend belongs to Write.

_ROLE_WORKFLOW: dict[str, Workflow] = {
    # Research investigation pipeline.
    "decomposer": Workflow.RESEARCH,
    "evidence_retriever": Workflow.RESEARCH,
    "parameter_extractor": Workflow.RESEARCH,
    "connector": Workflow.RESEARCH,
    "synthesizer": Workflow.RESEARCH,
    "user_agent": Workflow.RESEARCH,
    "tier_assigner": Workflow.RESEARCH,
    "constraint_checker": Workflow.RESEARCH,
    "verifier": Workflow.RESEARCH,
    # Write composition.
    "creative_writer": Workflow.WRITE,
    # Read wrestling-loop roles.
    "note_taker": Workflow.READ,
    "challenger": Workflow.READ,
    "grounder": Workflow.READ,
    # Speak interview-as-acquisition.
    "interviewer": Workflow.SPEAK,
}


def workflow_for_role(role: str | None) -> Workflow:
    """Classify a dispatch ``target_role`` to a workflow. An unknown or missing
    role → :attr:`Workflow.UNMAPPED` (counted, not dropped)."""
    if role is None:
        return Workflow.UNMAPPED
    return _ROLE_WORKFLOW.get(role, Workflow.UNMAPPED)


# ── Margin status (honesty #1 — stub the economics you can't compute) ────────

class MarginStatus(str, Enum):
    """Whether a margin figure is real (the policy is built) or honestly
    stubbed (the product sprint hasn't landed). A stubbed margin is NEVER
    rendered as a dollar figure — only the raw realized cost is."""

    APPLIED = "applied"      # margin policy is built and applied
    STUBBED = "stubbed"      # margin policy not built yet — raw cost only


@dataclass(frozen=True)
class WorkflowCost:
    """Realized inference cost for one workflow over the read window.

    ``raw_cost_usd`` is the sum of ``DispatchCall.cost_usd`` — always real.
    ``margined_cost_usd`` applies the economics-matrix margin where it is built
    and fully contextualized, else is ``None`` with ``margin_status=STUBBED``
    (honesty #1).
    ``remote_exec_cost_usd`` is the slice of ``raw_cost_usd`` that came from a
    remote-exec provider — surfaced so a runaway fan-out is visible (rigor #3)."""

    workflow: Workflow
    raw_cost_usd: Decimal
    call_count: int
    remote_exec_cost_usd: Decimal
    margin_status: MarginStatus
    margin_rate: Decimal | None       # the single applied rate, or None if mixed
    margined_cost_usd: Decimal | None # raw * (1 + rate), when APPLIED
    margin_note: str


@dataclass(frozen=True)
class CostView:
    """Per-workflow + aggregate realized inference cost. A VIEW — derived on
    read from the event log; stores nothing.

    The load-bearing rigor property: ``aggregate_raw_cost_usd`` equals the sum
    of every :class:`WorkflowCost`'s ``raw_cost_usd`` exactly — no double count,
    no dropped workflow (UNMAPPED is included). Asserted in the cost-view test."""

    per_workflow: tuple[WorkflowCost, ...]
    aggregate_raw_cost_usd: Decimal
    aggregate_call_count: int
    aggregate_remote_exec_cost_usd: Decimal
    events_dir: str

    def workflow(self, wf: Workflow) -> WorkflowCost:
        for w in self.per_workflow:
            if w.workflow is wf:
                return w
        raise KeyError(f"{wf} not in cost view")

    def has_unmapped_spend(self) -> bool:
        """True when some realized cost could not be attributed to one of the
        four product workflows — a signal the role→workflow map needs an entry,
        surfaced rather than hidden."""
        return self.workflow(Workflow.UNMAPPED).raw_cost_usd > 0


# ── Provider classification ──────────────────────────────────────────────────

# Providers the SPR-02 remote-exec path stamps onto its DispatchCall events.
# Matched against ``payload.provider`` to slice out remote-exec spend. Kept a
# small reviewed set; the default remote sentinel is "remote_exec" and the one
# implemented provider is "daytona" (per the §16 research-fanout exemption).
_REMOTE_EXEC_PROVIDERS: frozenset[str] = frozenset({"remote_exec", "daytona"})


def _is_remote_exec(provider: str | None) -> bool:
    return bool(provider) and provider in _REMOTE_EXEC_PROVIDERS


# ── The reader ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _DispatchCostEntry:
    investigation_id: str
    payload: Mapping[str, object]


def _iter_dispatch_entries(
    events_dir: str,
    *,
    investigation_ids: Iterable[str] | None = None,
) -> Iterable[_DispatchCostEntry]:
    """Yield every ``DISPATCH_CALL`` payload with its trajectory id.

    The investigation id is the only stable join key the event log gives the
    cost view for external context such as Speak project policy. Reads via the
    canonical :func:`substrate.event_log.events.trajectory` — never a second
    store.
    """
    import os

    dispatch = ActionType.DISPATCH_CALL.value
    if investigation_ids is None:
        if not os.path.isdir(events_dir):
            return
        ids: list[str] = []
        for fn in sorted(os.listdir(events_dir)):
            if fn.endswith(".jsonl"):
                ids.append(fn[: -len(".jsonl")])
            elif fn.endswith(".parquet"):
                ids.append(fn[: -len(".parquet")])
        # De-dup (an investigation may have both a JSONL and a sealed Parquet;
        # trajectory() prefers the Parquet, so reading the id once is correct).
        investigation_ids = sorted(set(ids))

    seen: set[str] = set()
    for iid in investigation_ids:
        if iid in seen:
            continue
        seen.add(iid)
        for row in _trajectory(iid, events_dir=events_dir):
            if row.get("action_type") != dispatch:
                continue
            payload = row.get("payload")
            if isinstance(payload, dict):
                yield _DispatchCostEntry(investigation_id=iid, payload=payload)


def _to_decimal_usd(value: object) -> Decimal:
    """Coerce a cost_usd field to Decimal without float drift. The event stores
    it as a JSON number; we stringify before Decimal so 0.0001 stays exact-ish
    at the ledger's cent/micro-cent granularity."""
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _margin_for_workflow(wf: Workflow) -> tuple[MarginStatus, Decimal | None, str]:
    """The economics-matrix margin for a workflow, honestly stubbed where the
    policy isn't built (honesty #1).

    Only Speak's matrix is built (``substrate.speak.economics_mode``). It is a
    *per-project* policy (public ⇒ 10%, private-published ⇒ 50%); without a
    project context the cost view cannot pick a cell, so it reports the matrix's
    two rates as the bounded range and marks the figure STUBBED rather than
    inventing a single margined number. Read's ad-economics margin is a planned
    product deliverable — stubbed. Research/Write carry no economics-matrix
    margin (no external monetization), so their raw cost is the operator's
    actual spend with no margin to apply."""
    if wf is Workflow.SPEAK:
        return (
            MarginStatus.STUBBED,
            None,
            (
                f"Speak economics matrix is per-project (public {MARGIN_PUBLIC:.0%} / "
                f"private-published {MARGIN_PRIVATE_PUBLISHED:.0%}); a margined total "
                f"needs a project context the cost view does not have — raw cost shown, "
                f"margin not fabricated."
            ),
        )
    if wf is Workflow.READ:
        return (
            MarginStatus.STUBBED,
            None,
            "Read ad-economics margin ships in the Read product sprint — raw cost only.",
        )
    if wf is Workflow.UNMAPPED:
        return (
            MarginStatus.STUBBED,
            None,
            "Unclassified dispatch role — counted in aggregate, no workflow margin applies.",
        )
    # Research / Write — no economics-matrix margin (no external monetization).
    return (
        MarginStatus.APPLIED,
        Decimal("0"),
        "No economics-matrix margin (internal spend) — raw cost is the actual spend.",
    )


def _speak_applied_note(rates: set[Decimal]) -> tuple[Decimal | None, str]:
    if len(rates) == 1:
        rate = next(iter(rates))
        return (
            rate,
            f"Speak economics matrix applied from investigation policy context at {rate:.0%}.",
        )
    rendered = " / ".join(f"{rate:.0%}" for rate in sorted(rates))
    return (
        None,
        f"Speak economics matrix applied per dispatch from mixed policy context ({rendered}).",
    )


def speak_policy_by_investigation_from_db(
    con: object,
) -> dict[str, EconomicsPolicy]:
    """Resolve Speak dispatch investigation ids to their project economics.

    Production Speak interviewer dispatches are logged as
    ``speak-followup-{interview_id}`` (see ``substrate.speak.async_interview``).
    The read-only join from ``interviews`` to ``speak_projects`` gives the
    project policy. We also map ``project_id`` itself because other Speak
    acquisition paths use the project id as their investigation scope.

    Missing Speak tables mean no context has landed in that database yet; return
    an empty mapping and let :func:`build_cost_view` keep Speak margins stubbed.
    """
    try:
        rows = con.execute(
            """
            SELECT i.interview_id, i.project_id, p.invitation_mode, p.publish_intent
            FROM interviews i
            JOIN speak_projects p ON p.project_id = i.project_id
            """
        ).fetchall()
    except Exception as exc:
        msg = str(exc).lower()
        if (
            "interviews" in msg
            or "speak_projects" in msg
            or "does not exist" in msg
            or "not found" in msg
        ):
            return {}
        raise

    out: dict[str, EconomicsPolicy] = {}
    for interview_id, project_id, invitation_mode, publish_intent in rows:
        publishing = "public" if publish_intent == "will_be_public" else "never_published"
        policy = resolve_policy(str(invitation_mode), publishing)
        out[f"speak-followup-{interview_id}"] = policy
        out[str(project_id)] = policy
    return out


def build_cost_view(
    *,
    events_dir: str | None = None,
    investigation_ids: Iterable[str] | None = None,
    speak_policy_by_investigation: Mapping[str, EconomicsPolicy] | None = None,
) -> CostView:
    """Aggregate realized ``DispatchCall`` cost per workflow + in aggregate.

    Reads the canonical event log (``trajectory``); sums ``payload.cost_usd``;
    groups by ``workflow_for_role(payload.target_role)``; slices the remote-exec
    portion by ``payload.provider``. When every Speak dispatch has an explicit
    ``speak_policy_by_investigation`` entry, the Speak row applies the built
    economics matrix; missing context keeps it stubbed. Idle ⇒ every figure is
    ``$0`` (no fabricated baseline). The aggregate equals the sum of the
    per-workflow raw costs by construction (asserted in the test)."""
    d = events_dir or default_events_dir()

    raw: dict[Workflow, Decimal] = {wf: Decimal("0") for wf in Workflow}
    counts: dict[Workflow, int] = {wf: 0 for wf in Workflow}
    remote: dict[Workflow, Decimal] = {wf: Decimal("0") for wf in Workflow}
    margined: dict[Workflow, Decimal | None] = {wf: None for wf in Workflow}
    applied_rates: dict[Workflow, set[Decimal]] = {wf: set() for wf in Workflow}
    missing_speak_context = False

    for entry in _iter_dispatch_entries(d, investigation_ids=investigation_ids):
        payload = entry.payload
        role = payload.get("target_role")
        wf = workflow_for_role(role if isinstance(role, str) else None)
        cost = _to_decimal_usd(payload.get("cost_usd"))
        raw[wf] += cost
        counts[wf] += 1
        provider = payload.get("provider")
        if _is_remote_exec(provider if isinstance(provider, str) else None):
            remote[wf] += cost
        if wf is Workflow.SPEAK:
            policy = (
                speak_policy_by_investigation or {}
            ).get(entry.investigation_id)
            if policy is None:
                missing_speak_context = True
            else:
                rate = policy.inference_margin
                applied_rates[wf].add(rate)
                current = margined[wf] or Decimal("0")
                margined[wf] = current + (cost * (Decimal("1") + rate))

    per_workflow: list[WorkflowCost] = []
    for wf in Workflow:
        status, rate, note = _margin_for_workflow(wf)
        margined_cost: Decimal | None = None
        if wf is Workflow.SPEAK and raw[wf] > 0 and not missing_speak_context:
            status = MarginStatus.APPLIED
            rate, note = _speak_applied_note(applied_rates[wf])
            margined_cost = margined[wf]
        elif status is MarginStatus.APPLIED and rate is not None:
            margined_cost = raw[wf] * (Decimal("1") + rate)
        per_workflow.append(
            WorkflowCost(
                workflow=wf,
                raw_cost_usd=raw[wf],
                call_count=counts[wf],
                remote_exec_cost_usd=remote[wf],
                margin_status=status,
                margin_rate=rate if status is MarginStatus.APPLIED else None,
                margined_cost_usd=margined_cost,
                margin_note=note,
            )
        )

    aggregate = sum(raw.values(), Decimal("0"))
    aggregate_calls = sum(counts.values())
    aggregate_remote = sum(remote.values(), Decimal("0"))

    return CostView(
        per_workflow=tuple(per_workflow),
        aggregate_raw_cost_usd=aggregate,
        aggregate_call_count=aggregate_calls,
        aggregate_remote_exec_cost_usd=aggregate_remote,
        events_dir=d,
    )


__all__ = [
    "Workflow",
    "MarginStatus",
    "WorkflowCost",
    "CostView",
    "workflow_for_role",
    "speak_policy_by_investigation_from_db",
    "build_cost_view",
]
