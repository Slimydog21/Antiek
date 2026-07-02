import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../../lib/api";
import { GateLedger } from "./GateLedger";
import type { CoordProduct, GateImpactView, GateView } from "./GateLedger";
import { Roadmap } from "./Roadmap";
import type {
  DependencyBlockerView,
  EngineeringDeferralView,
  EngineeringDeferralsSummaryView,
  ExecutionFocusView,
  OperatorActionView,
  OperatorActionsSummaryView,
  OperatorGateFocusView,
  Phase2AuditView,
  Phase2ExitCriteriaView,
  Phase2SprintScoreView,
  ReadActivationStatusView,
  RoadmapView,
  RosterView,
  SprintView,
  SubstrateLayerView,
} from "./Roadmap";

/**
 * Coordination mode — one operator surface for "what's blocked and why"
 * (antiek-unified SPR-05).
 *
 * Two read-only views, both derived on read from canonical sources this mode
 * never writes:
 *
 *  - Gate ledger: a view over docs/operator_gate_actions.md (GET
 *    /coordination/gates). The original G1-G8 activation gates, once, with a
 *    per-product impact column. Appended G9-G12 operator/legal follow-ons remain
 *    in the source doc; no per-product gate duplication.
 *  - Roadmap: the five specs' rosters + SPR-01's dependency DAG (GET
 *    /coordination/roadmap). 45 sprints reconciled, DRW critical path explicit,
 *    dependency-ready sprint state derived from the DAG.
 *
 * Slots into the SPR-04 shared/operator bucket. Read-only — there is no control
 * here that mutates a gate or a sprint; gate state changes only in the
 * operator's source markdown.
 */

interface GatesResponse {
  source_path: string;
  gates: GateView[];
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function nullableString(value: unknown): string | null {
  return value == null ? null : nonEmptyString(value);
}

function nonNegativeInteger(value: unknown): number {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(parsed) && parsed >= 0 ? Math.floor(parsed) : 0;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const text = nonEmptyString(item);
        return text ? [text] : [];
      })
    : [];
}

function gateStatus(value: unknown): GateView["status"] {
  return value === "closed" ||
    value === "calendar" ||
    value === "data_bound"
    ? value
    : "open";
}

function coordProduct(value: unknown): CoordProduct | null {
  return value === "research" ||
    value === "read" ||
    value === "write" ||
    value === "speak"
    ? value
    : null;
}

function safeGateImpact(value: unknown): GateImpactView | null {
  const impact = record(value);
  const product = coordProduct(impact?.product);
  const effect = nonEmptyString(impact?.effect);
  if (!impact || !product || !effect) return null;
  return { product, effect };
}

function safeGate(value: unknown): GateView | null {
  const gate = record(value);
  const gateId = nonEmptyString(gate?.gate_id);
  if (!gate || !gateId) return null;
  return {
    gate_id: gateId,
    title: nonEmptyString(gate.title) ?? gateId,
    status: gateStatus(gate.status),
    status_raw: nonEmptyString(gate.status_raw) ?? "",
    is_provisional: gate.is_provisional === true,
    owner: nullableString(gate.owner),
    blocks: nullableString(gate.blocks),
    closure_record: nullableString(gate.closure_record),
    impacts: Array.isArray(gate.impacts)
      ? gate.impacts.flatMap((item) => {
          const impact = safeGateImpact(item);
          return impact ? [impact] : [];
        })
      : [],
  };
}

function safeGatesResponse(value: unknown): GatesResponse {
  const body = record(value);
  const gates = Array.isArray(body?.gates)
    ? body.gates.flatMap((item) => {
        const gate = safeGate(item);
        return gate ? [gate] : [];
      })
    : [];
  return {
    source_path: nonEmptyString(body?.source_path) ?? "",
    gates,
  };
}

function safeSprint(value: unknown): SprintView | null {
  const sprint = record(value);
  const nodeId = nonEmptyString(sprint?.node_id);
  if (!sprint || !nodeId) return null;
  return {
    spec: nonEmptyString(sprint.spec) ?? "",
    spec_label: nonEmptyString(sprint.spec_label) ?? "",
    sprint: nonNegativeInteger(sprint.sprint),
    slug: nonEmptyString(sprint.slug) ?? nodeId,
    node_id: nodeId,
    status: nonEmptyString(sprint.status) ?? "unknown",
    on_critical_path: sprint.on_critical_path === true,
    blocked_on: stringList(sprint.blocked_on),
    unblocked: sprint.unblocked === true,
  };
}

function safeRoster(value: unknown): RosterView | null {
  const roster = record(value);
  const spec = nonEmptyString(roster?.spec);
  if (!roster || !spec) return null;
  const sprints = Array.isArray(roster.sprints)
    ? roster.sprints.flatMap((item) => {
        const sprint = safeSprint(item);
        return sprint ? [sprint] : [];
      })
    : [];
  return {
    spec,
    label: nonEmptyString(roster.label) ?? spec,
    directory: nonEmptyString(roster.directory) ?? "",
    count: nonNegativeInteger(roster.count),
    sprints,
  };
}

function safeSubstrateLayer(value: unknown): SubstrateLayerView | null {
  const layer = record(value);
  const name = nonEmptyString(layer?.name);
  if (!layer || !name) return null;
  return {
    name,
    owner: nonEmptyString(layer.owner) ?? "",
    status: nonEmptyString(layer.status) ?? "unknown",
  };
}

function safeDependencyBlocker(value: unknown): DependencyBlockerView | null {
  const blocker = record(value);
  const nodeId = nonEmptyString(blocker?.node_id);
  if (!blocker || !nodeId) return null;
  return {
    node_id: nodeId,
    blocked_sprints: stringList(blocker.blocked_sprints),
  };
}

function safeExecutionFocus(value: unknown): ExecutionFocusView | null {
  const focus = record(value);
  const kind =
    focus?.kind === "dependency_blocker" || focus?.kind === "dependency_ready"
      ? focus.kind
      : null;
  const nodeId = nonEmptyString(focus?.node_id);
  if (!focus || !kind || !nodeId) return null;
  return {
    kind,
    node_id: nodeId,
    blocked_sprints: stringList(focus.blocked_sprints),
  };
}

function safeOperatorGateFocus(value: unknown): OperatorGateFocusView | null {
  const focus = record(value);
  const gateId = nonEmptyString(focus?.gate_id);
  const title = nonEmptyString(focus?.title);
  if (!focus || !gateId || !title) return null;
  return {
    gate_id: gateId,
    title,
    status: gateStatus(focus.status),
    status_raw: nonEmptyString(focus.status_raw) ?? "",
    owner: nullableString(focus.owner),
    blocks: nullableString(focus.blocks),
    source_path: nonEmptyString(focus.source_path) ?? "",
  };
}

function numberRecord(value: unknown): Record<string, number> {
  const body = record(value);
  if (!body) return {};
  return Object.fromEntries(
    Object.entries(body).map(([key, raw]) => [key, nonNegativeInteger(raw)]),
  );
}

function safeReadActivationStatus(value: unknown): ReadActivationStatusView | null {
  const activation = record(value);
  if (!activation) return null;
  return {
    source_path: nonEmptyString(activation.source_path) ?? "",
    state: nonEmptyString(activation.state) ?? "not_started",
    total_sessions: nonNegativeInteger(activation.total_sessions),
    valid_sessions: nonNegativeInteger(activation.valid_sessions),
    invalid_session_count: nonNegativeInteger(activation.invalid_session_count),
    live_provider_sessions: nonNegativeInteger(activation.live_provider_sessions),
    citation_trace_sessions: nonNegativeInteger(activation.citation_trace_sessions),
    non_library_sessions: nonNegativeInteger(activation.non_library_sessions),
    final_verdict: nullableString(activation.final_verdict),
    closure_ready: activation.closure_ready === true,
    remaining_requirements: numberRecord(activation.remaining_requirements),
    failures: stringList(activation.failures),
  };
}

function safePhase2SprintScore(value: unknown): Phase2SprintScoreView | null {
  const score = record(value);
  const sprint = nonEmptyString(score?.sprint);
  if (!score || !sprint) return null;
  return {
    sprint,
    phases: nonNegativeInteger(score.phases),
    met: nonNegativeInteger(score.met),
    partial: nonNegativeInteger(score.partial),
    unmet: nonNegativeInteger(score.unmet),
    delta_vs_v3: nonEmptyString(score.delta_vs_v3) ?? "",
  };
}

function safePhase2ExitCriteria(value: unknown): Phase2ExitCriteriaView | null {
  const exit = record(value);
  if (!exit) return null;
  return {
    total: nonNegativeInteger(exit.total),
    met: nonNegativeInteger(exit.met),
    partial: nonNegativeInteger(exit.partial),
    unmet: nonNegativeInteger(exit.unmet),
    note: nonEmptyString(exit.note) ?? "",
  };
}

function nullableNumber(value: unknown): number | null {
  const parsed = nonNegativeInteger(value);
  return value == null || value === "" ? null : parsed;
}

function safePhase2Audit(value: unknown): Phase2AuditView | null {
  const audit = record(value);
  if (!audit) return null;
  return {
    source_path: nonEmptyString(audit.source_path) ?? "",
    scorecard_source_path: nonEmptyString(audit.scorecard_source_path) ?? "",
    current_commit_evidence: nullableString(audit.current_commit_evidence),
    engineering_blocked_count: nullableNumber(audit.engineering_blocked_count),
    status_summary: nullableString(audit.status_summary),
    next_action_ordering: stringList(audit.next_action_ordering),
    sprint_scorecard: Array.isArray(audit.sprint_scorecard)
      ? audit.sprint_scorecard.flatMap((item) => {
          const score = safePhase2SprintScore(item);
          return score ? [score] : [];
        })
      : [],
    total_score: safePhase2SprintScore(audit.total_score),
    exit_criteria: safePhase2ExitCriteria(audit.exit_criteria),
  };
}

function safeOperatorAction(value: unknown): OperatorActionView | null {
  const action = record(value);
  const actionId = nonEmptyString(action?.action_id);
  if (!action || !actionId) return null;
  return {
    action_id: actionId,
    title: nonEmptyString(action.title) ?? actionId,
    status: nonEmptyString(action.status) ?? "unknown",
    status_raw: nonEmptyString(action.status_raw) ?? "",
    blocks: nonEmptyString(action.blocks) ?? "—",
    owner: nonEmptyString(action.owner) ?? "Operator",
  };
}

function safeOperatorActionsSummary(
  value: unknown,
): OperatorActionsSummaryView | null {
  const summary = record(value);
  if (!summary) return null;
  return {
    source_path: nonEmptyString(summary.source_path) ?? "",
    total_actions: nonNegativeInteger(summary.total_actions),
    open_count: nonNegativeInteger(summary.open_count),
    closeable_count: nonNegativeInteger(summary.closeable_count),
    status_counts: numberRecord(summary.status_counts),
    next_action: safeOperatorAction(summary.next_action),
    closeable_action: safeOperatorAction(summary.closeable_action),
  };
}

function safeEngineeringDeferral(value: unknown): EngineeringDeferralView | null {
  const deferral = record(value);
  const deferralId = nonEmptyString(deferral?.deferral_id);
  if (!deferral || !deferralId) return null;
  return {
    deferral_id: deferralId,
    title: nonEmptyString(deferral.title) ?? deferralId,
    status: nonEmptyString(deferral.status) ?? "unknown",
    status_raw: nonEmptyString(deferral.status_raw) ?? "",
    unlock_criterion: nullableString(deferral.unlock_criterion),
    blocks: nullableString(deferral.blocks),
  };
}

function safeEngineeringDeferralsSummary(
  value: unknown,
): EngineeringDeferralsSummaryView | null {
  const summary = record(value);
  if (!summary) return null;
  return {
    source_path: nonEmptyString(summary.source_path) ?? "",
    total_deferrals: nonNegativeInteger(summary.total_deferrals),
    open_count: nonNegativeInteger(summary.open_count),
    status_counts: numberRecord(summary.status_counts),
    first_open: safeEngineeringDeferral(summary.first_open),
  };
}

function safeRoadmapView(value: unknown): RoadmapView {
  const body = record(value);
  const rosters = Array.isArray(body?.rosters)
    ? body.rosters.flatMap((item) => {
        const roster = safeRoster(item);
        return roster ? [roster] : [];
      })
    : [];
  return {
    total_sprints: nonNegativeInteger(body?.total_sprints),
    superseded_count: nonNegativeInteger(body?.superseded_count),
    superseded_note: nonEmptyString(body?.superseded_note) ?? "",
    activation_note: nonEmptyString(body?.activation_note) ?? "",
    reconciliation: nonEmptyString(body?.reconciliation) ?? "",
    critical_path: stringList(body?.critical_path),
    rosters,
    unblocked_now: stringList(body?.unblocked_now),
    dependency_blockers: Array.isArray(body?.dependency_blockers)
      ? body.dependency_blockers.flatMap((item) => {
          const blocker = safeDependencyBlocker(item);
          return blocker ? [blocker] : [];
        })
      : [],
    execution_focus: safeExecutionFocus(body?.execution_focus),
    operator_gate_focus: safeOperatorGateFocus(body?.operator_gate_focus),
    read_activation: safeReadActivationStatus(body?.read_activation),
    operator_actions: safeOperatorActionsSummary(body?.operator_actions),
    phase2_audit: safePhase2Audit(body?.phase2_audit),
    engineering_deferrals: safeEngineeringDeferralsSummary(
      body?.engineering_deferrals,
    ),
    substrate_layers: Array.isArray(body?.substrate_layers)
      ? body.substrate_layers.flatMap((item) => {
          const layer = safeSubstrateLayer(item);
          return layer ? [layer] : [];
        })
      : [],
  };
}

export default function Coordination() {
  const [gates, setGates] = useState<GatesResponse | null>(null);
  const [roadmap, setRoadmap] = useState<RoadmapView | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [gatesResp, roadmapResp] = await Promise.all([
        apiFetch("/coordination/gates"),
        apiFetch("/coordination/roadmap"),
      ]);
      if (!gatesResp.ok) {
        throw new Error(`GET /coordination/gates failed: HTTP ${gatesResp.status}`);
      }
      if (!roadmapResp.ok) {
        throw new Error(`GET /coordination/roadmap failed: HTTP ${roadmapResp.status}`);
      }
      setGates(safeGatesResponse(await gatesResp.json()));
      setRoadmap(safeRoadmapView(await roadmapResp.json()));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-10">
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Coordination
            </h1>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              What's blocked and why. The gate ledger is a read-only view over
              the canonical operator gate file; the roadmap reads the five
              specs' rosters and the dependency DAG. Nothing on this page can
              change a gate's state — that is an operator action in the source
              file.
            </p>
          </header>

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight">
              Loading coordination view…
            </p>
          )}
          {error && <p className="text-sm text-emperor">{error}</p>}

          {gates && (
            <GateLedger gates={gates.gates} sourcePath={gates.source_path} />
          )}
          {roadmap && <Roadmap roadmap={roadmap} />}
        </div>
      </main>
    </div>
  );
}
