import { LemonCard, LemonTable, LemonTag } from "../../components/lemon";
import type { LemonColumn } from "../../components/lemon";

/**
 * Roadmap — read-only view over the five specs' sprint rosters + SPR-01's
 * dependency DAG (SPR-05 M3).
 *
 * Renders the reconciled 45-sprint count (DRW 10 + Read 9 + Write 9 + Speak 9 +
 * unified 8; shell's 6 superseded), the DRW critical path (drw:1 → drw:3 →
 * drw:10) made explicit, what's dependency-ready (derived from dependency
 * state, not hand-set), and the substrate-execution layer beneath the products.
 *
 * Presentational: renders the data the parent fetched from
 * GET /coordination/roadmap. It authors no roster and writes no state.
 */

export interface SprintView {
  spec: string;
  spec_label: string;
  sprint: number;
  slug: string;
  node_id: string;
  status: string;
  on_critical_path: boolean;
  blocked_on: string[];
  unblocked: boolean;
}

export interface RosterView {
  spec: string;
  label: string;
  directory: string;
  count: number;
  sprints: SprintView[];
}

export interface SubstrateLayerView {
  name: string;
  owner: string;
  status: string;
}

export interface DependencyBlockerView {
  node_id: string;
  blocked_sprints: string[];
}

export type ExecutionFocusView =
  | {
      kind: "dependency_blocker";
      node_id: string;
      blocked_sprints: string[];
    }
  | {
      kind: "dependency_ready";
      node_id: string;
      blocked_sprints?: string[];
    };

export interface OperatorGateFocusView {
  gate_id: string;
  title: string;
  status: string;
  status_raw: string;
  owner: string | null;
  blocks: string | null;
  source_path: string;
}

export interface ReadActivationStatusView {
  source_path: string;
  state: string;
  total_sessions: number;
  valid_sessions: number;
  invalid_session_count: number;
  live_provider_sessions: number;
  citation_trace_sessions: number;
  non_library_sessions: number;
  final_verdict: string | null;
  closure_ready: boolean;
  remaining_requirements: Record<string, number>;
  failures: string[];
}

export interface OperatorActionView {
  action_id: string;
  title: string;
  status: string;
  status_raw: string;
  blocks: string;
  owner: string;
}

export interface OperatorActionsSummaryView {
  source_path: string;
  total_actions: number;
  open_count: number;
  closeable_count: number;
  status_counts: Record<string, number>;
  next_action: OperatorActionView | null;
  closeable_action: OperatorActionView | null;
}

export interface Phase2SprintScoreView {
  sprint: string;
  phases: number;
  met: number;
  partial: number;
  unmet: number;
  delta_vs_v3: string;
}

export interface Phase2ExitCriteriaView {
  total: number;
  met: number;
  partial: number;
  unmet: number;
  note: string;
}

export interface Phase2AuditView {
  source_path: string;
  scorecard_source_path: string;
  current_commit_evidence: string | null;
  engineering_blocked_count: number | null;
  status_summary: string | null;
  next_action_ordering: string[];
  sprint_scorecard: Phase2SprintScoreView[];
  total_score: Phase2SprintScoreView | null;
  exit_criteria: Phase2ExitCriteriaView | null;
}

export interface EngineeringDeferralView {
  deferral_id: string;
  title: string;
  status: string;
  status_raw: string;
  unlock_criterion: string | null;
  blocks: string | null;
}

export interface EngineeringDeferralsSummaryView {
  source_path: string;
  total_deferrals: number;
  open_count: number;
  status_counts: Record<string, number>;
  first_open: EngineeringDeferralView | null;
}

export interface Loop3CriterionStatusView {
  criterion: string;
  manual_met: boolean;
  evidence_passed: boolean;
  evidence_status: string;
  evidence_summary: string;
}

export interface Loop3CoordinationView {
  criteria: Loop3CriterionStatusView[];
  manual_met_count: number;
  evidence_passed_count: number;
  total_criteria: number;
  all_criteria_met: boolean;
  all_evidence_passed: boolean;
  env_unlocked: boolean;
  fully_unlocked: boolean;
  first_failing_evidence: Loop3CriterionStatusView | null;
  events_dir: string;
  open_weight_policy_file: string;
}

export interface RoadmapView {
  total_sprints: number;
  superseded_count: number;
  superseded_note: string;
  activation_note: string;
  reconciliation: string;
  critical_path: string[];
  rosters: RosterView[];
  unblocked_now: string[];
  dependency_blockers: DependencyBlockerView[];
  execution_focus: ExecutionFocusView | null;
  operator_gate_focus: OperatorGateFocusView | null;
  read_activation: ReadActivationStatusView | null;
  operator_actions?: OperatorActionsSummaryView | null;
  phase2_audit?: Phase2AuditView | null;
  engineering_deferrals?: EngineeringDeferralsSummaryView | null;
  loop3?: Loop3CoordinationView | null;
  substrate_layers: SubstrateLayerView[];
}

interface ResolvedDependencyBlocker {
  node_id: string;
  blocker_sprint: SprintView | null;
  blocked_sprints: SprintView[];
}

type ResolvedExecutionFocus =
  | { kind: "dependency_blocker"; blocker: ResolvedDependencyBlocker }
  | { kind: "dependency_ready"; sprint: SprintView };

const sprintStatusColour = (s: string): "muted" | "sun" | "default" => {
  if (s === "live") return "muted";
  if (s === "provisional" || s === "transferred") return "sun";
  return "default";
};

const formatSprintLabel = (s: SprintView): string =>
  `${s.spec_label || s.spec} · SPR-${String(s.sprint).padStart(2, "0")}`;

function deriveDependencyBlockers(sprints: SprintView[]): ResolvedDependencyBlocker[] {
  const byBlocker = new Map<string, SprintView[]>();
  for (const sprint of sprints) {
    if (sprint.unblocked) continue;
    for (const blocker of new Set(sprint.blocked_on)) {
      const blocked = byBlocker.get(blocker) ?? [];
      blocked.push(sprint);
      byBlocker.set(blocker, blocked);
    }
  }
  return Array.from(byBlocker, ([node_id, blocked_sprints]) => ({
    node_id,
    blocker_sprint: null,
    blocked_sprints,
  })).sort(
    (a, b) =>
      b.blocked_sprints.length - a.blocked_sprints.length ||
      a.node_id.localeCompare(b.node_id),
  );
}

function resolveDependencyBlockers(
  rawBlockers: DependencyBlockerView[],
  sprintById: Map<string, SprintView>,
  allSprints: SprintView[],
): ResolvedDependencyBlocker[] {
  const derived = deriveDependencyBlockers(allSprints);
  const withBlockerSprints = (blockers: ResolvedDependencyBlocker[]) =>
    blockers.map((blocker) => ({
      ...blocker,
      blocker_sprint: sprintById.get(blocker.node_id) ?? blocker.blocker_sprint,
    }));
  const resolved = rawBlockers.flatMap((blocker) => {
    const seen = new Set<string>();
    const blocked_sprints = blocker.blocked_sprints.flatMap((nodeId) => {
      if (seen.has(nodeId)) return [];
      seen.add(nodeId);
      const sprint = sprintById.get(nodeId);
      return sprint &&
        !sprint.unblocked &&
        sprint.blocked_on.includes(blocker.node_id)
        ? [sprint]
        : [];
    });
    return blocked_sprints.length > 0
      ? [
          {
            node_id: blocker.node_id,
            blocker_sprint: sprintById.get(blocker.node_id) ?? null,
            blocked_sprints,
          },
        ]
      : [];
  });
  if (resolved.length === 0) return withBlockerSprints(derived);

  const sorted = resolved.sort(
    (a, b) =>
      b.blocked_sprints.length - a.blocked_sprints.length ||
      a.node_id.localeCompare(b.node_id),
  );
  const serialize = (blocker: ResolvedDependencyBlocker): string =>
    `${blocker.node_id}:${blocker.blocked_sprints
      .map((s) => s.node_id)
      .sort()
      .join(",")}`;
  const sortedSignature = sorted.map(serialize).join("|");
  const derivedSignature = derived.map(serialize).join("|");
  return withBlockerSprints(
    sortedSignature === derivedSignature ? sorted : derived,
  );
}

function resolveExecutionFocus(
  rawFocus: ExecutionFocusView | null,
  blockers: ResolvedDependencyBlocker[],
  dependencyReady: SprintView[],
): ResolvedExecutionFocus | null {
  const topBlocker = blockers[0];
  const fallbackReady = dependencyReady[0];

  if (
    rawFocus?.kind === "dependency_blocker" &&
    topBlocker &&
    rawFocus.node_id === topBlocker.node_id
  ) {
    const actualBlockedIds = new Set(
      topBlocker.blocked_sprints.map((s) => s.node_id),
    );
    const focusBlockedIds = new Set(rawFocus.blocked_sprints);
    if (
      actualBlockedIds.size === focusBlockedIds.size &&
      [...actualBlockedIds].every((nodeId) => focusBlockedIds.has(nodeId))
    ) {
      return { kind: "dependency_blocker", blocker: topBlocker };
    }
  }

  if (
    rawFocus?.kind === "dependency_ready" &&
    !topBlocker &&
    fallbackReady &&
    rawFocus.node_id === fallbackReady.node_id
  ) {
    return { kind: "dependency_ready", sprint: fallbackReady };
  }

  if (topBlocker) return { kind: "dependency_blocker", blocker: topBlocker };
  if (fallbackReady) return { kind: "dependency_ready", sprint: fallbackReady };
  return null;
}

export function Roadmap({ roadmap }: { roadmap: RoadmapView }) {
  const allSprints = roadmap.rosters.flatMap((r) => r.sprints);
  const sprintById = new Map(
    allSprints.map((s) => [s.node_id, s] as const),
  );
  const seenReadyIds = new Set<string>();
  const dependencyReady = roadmap.unblocked_now.flatMap((nodeId) => {
    if (seenReadyIds.has(nodeId)) return [];
    seenReadyIds.add(nodeId);
    const sprint = sprintById.get(nodeId);
    return sprint?.unblocked ? [sprint] : [];
  });
  const blockedCount = allSprints.filter((s) => !s.unblocked).length;
  const blockers = resolveDependencyBlockers(
    roadmap.dependency_blockers,
    sprintById,
    allSprints,
  );
  const executionFocus = resolveExecutionFocus(
    roadmap.execution_focus,
    blockers,
    dependencyReady,
  );

  return (
    <section className="space-y-5">
      <header className="space-y-1">
        <h2 className="text-lg font-serif text-ink dark:text-bright">
          Roadmap
        </h2>
        <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
          Every sprint across the five live specs + the SPR-01 dependency DAG.
          The count is summed from the real roster files, not trusted from
          prose.
        </p>
      </header>

      {/* Reconciliation banner — the count, summed out loud (rigor #1). */}
      <LemonCard colour="glacial" elevation="z1">
        <div className="p-4 space-y-1">
          <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
            Reconciled sprint count
          </p>
          <p className="text-sm font-mono text-ink dark:text-bright">
            {roadmap.reconciliation}
          </p>
          <p className="text-xs font-mono text-shadow-2 dark:text-moonlight">
            {dependencyReady.length} dependency-ready · {blockedCount} blocked by dependency state
          </p>
          {roadmap.activation_note ? (
            <p className="text-xs text-ink-soft dark:text-starlight leading-relaxed">
              {roadmap.activation_note}
            </p>
          ) : null}
          {roadmap.read_activation ? (
            <ActivationStatus activation={roadmap.read_activation} />
          ) : null}
          {roadmap.operator_actions ? (
            <OperatorActionsStatus operatorActions={roadmap.operator_actions} />
          ) : null}
          {roadmap.phase2_audit ? (
            <Phase2AuditStatus audit={roadmap.phase2_audit} />
          ) : null}
          {roadmap.engineering_deferrals ? (
            <EngineeringDeferralsStatus
              deferrals={roadmap.engineering_deferrals}
            />
          ) : null}
          {roadmap.loop3 ? <Loop3Status loop3={roadmap.loop3} /> : null}
        </div>
      </LemonCard>

      <CriticalPathSection
        criticalPath={roadmap.critical_path}
        sprintById={sprintById}
      />

      <ExecutionFocusSection
        focus={executionFocus}
        operatorGateFocus={roadmap.operator_gate_focus}
      />

      <ReadyNowSection sprints={dependencyReady} />
      <DependencyBlockersSection blockers={blockers} />

      {/* Per-spec rosters. */}
      <div className="space-y-4">
        {roadmap.rosters.map((r) => (
          <RosterTable key={r.spec} roster={r} criticalPath={roadmap.critical_path} />
        ))}
      </div>

      {/* Substrate-execution layer — the real foundation beneath the products. */}
      <SubstrateLayerSection layers={roadmap.substrate_layers} />
    </section>
  );
}

function ActivationStatus({
  activation,
}: {
  activation: ReadActivationStatusView;
}) {
  const remaining = activation.remaining_requirements ?? {};
  const remainingText = [
    ["valid", remaining.valid_sessions],
    ["live-provider", remaining.live_provider_sessions],
    ["citation-traced", remaining.citation_trace_sessions],
    ["non-library", remaining.non_library_sessions],
  ]
    .filter(([, value]) => Number(value) > 0)
    .map(([label, value]) => `${value} ${label}`)
    .join(", ");
  return (
    <div className="mt-2 rounded border border-rule dark:border-charcoal-1 bg-ice-0/70 dark:bg-charcoal-2/70 px-3 py-2">
      <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        Read activation dogfood
      </p>
      <p className="text-xs font-mono text-ink dark:text-bright">
        {activation.valid_sessions}/{activation.total_sessions} valid ·{" "}
        {activation.live_provider_sessions} live-provider ·{" "}
        {activation.citation_trace_sessions} citation-traced ·{" "}
        {activation.non_library_sessions} non-library · verdict=
        {activation.final_verdict || "missing"}
      </p>
      <p className="text-xs text-ink-soft dark:text-starlight leading-relaxed">
        {activation.closure_ready
          ? "Closure evidence is mechanically ready; operator verdict remains the product bar."
          : remainingText
            ? `Remaining: ${remainingText}.`
            : activation.state === "invalid_log"
              ? "Dogfood log is malformed; repair the JSONL before counting it."
              : "No dogfood closure evidence is ready yet."}{" "}
        Source: {activation.source_path || "reports/read-dogfood.jsonl"}.
      </p>
      {activation.invalid_session_count > 0 && (
        <p className="text-xs font-mono text-emperor">
          {activation.invalid_session_count} invalid session
          {activation.invalid_session_count === 1 ? "" : "s"} need repair.
        </p>
      )}
    </div>
  );
}

function Loop3Status({ loop3 }: { loop3: Loop3CoordinationView }) {
  const failing = loop3.first_failing_evidence;
  return (
    <div className="mt-2 rounded border border-rule dark:border-charcoal-1 bg-ice-0/70 dark:bg-charcoal-2/70 px-3 py-2">
      <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        Loop 3 / G8
      </p>
      <p className="text-xs font-mono text-ink dark:text-bright">
        manual {loop3.manual_met_count}/{loop3.total_criteria} · evidence{" "}
        {loop3.evidence_passed_count}/{loop3.total_criteria} · env=
        {loop3.env_unlocked ? "unlocked" : "locked"} · fully=
        {loop3.fully_unlocked ? "yes" : "no"}
      </p>
      {failing ? (
        <p className="text-xs text-ink-soft dark:text-starlight leading-relaxed">
          First failing evidence: {failing.criterion} — {failing.evidence_summary}.
        </p>
      ) : (
        <p className="text-xs text-ink-soft dark:text-starlight leading-relaxed">
          Verifier evidence passes; operator env authorization remains separate.
        </p>
      )}
    </div>
  );
}

function EngineeringDeferralsStatus({
  deferrals,
}: {
  deferrals: EngineeringDeferralsSummaryView;
}) {
  const counts = deferrals.status_counts ?? {};
  const countText = [
    ["deferred", counts.deferred],
    ["partial", counts.partial],
    ["substrate shipped", counts.substrate_shipped],
    ["closed", counts.closed],
  ]
    .filter(([, value]) => Number(value) > 0)
    .map(([label, value]) => `${value} ${label}`)
    .join(" · ");
  const firstOpen = deferrals.first_open;
  return (
    <div className="mt-2 rounded border border-rule dark:border-charcoal-1 bg-ice-0/70 dark:bg-charcoal-2/70 px-3 py-2">
      <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        Engineering deferrals
      </p>
      <p className="text-xs font-mono text-ink dark:text-bright">
        {deferrals.open_count}/{deferrals.total_deferrals} not closed
        {countText ? ` · ${countText}` : ""}
      </p>
      {firstOpen ? (
        <p className="text-xs text-ink-soft dark:text-starlight leading-relaxed">
          Do not pre-build {firstOpen.deferral_id} — {firstOpen.title}. Unlock:{" "}
          {firstOpen.unlock_criterion || "not specified"}. Source:{" "}
          {deferrals.source_path || "docs/engineering_deferrals.md"}.
        </p>
      ) : (
        <p className="text-xs text-ink-soft dark:text-starlight leading-relaxed">
          No open engineering deferrals in{" "}
          {deferrals.source_path || "docs/engineering_deferrals.md"}.
        </p>
      )}
    </div>
  );
}

function Phase2AuditStatus({ audit }: { audit: Phase2AuditView }) {
  const total = audit.total_score;
  const exit = audit.exit_criteria;
  const firstAction = audit.next_action_ordering[0];
  return (
    <div className="mt-2 rounded border border-rule dark:border-charcoal-1 bg-ice-0/70 dark:bg-charcoal-2/70 px-3 py-2">
      <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        Phase 2 execution audit
      </p>
      <p className="text-xs font-mono text-ink dark:text-bright">
        engineering-blocked={audit.engineering_blocked_count ?? "unknown"}
        {total
          ? ` · sprint phases ${total.met}/${total.phases} met · ${total.partial} partial · ${total.unmet} unmet`
          : ""}
        {exit
          ? ` · exit criteria ${exit.met}/${exit.total} met · ${exit.partial} partial · ${exit.unmet} unmet`
          : ""}
      </p>
      <p className="text-xs text-ink-soft dark:text-starlight leading-relaxed">
        {audit.status_summary ||
          "No reconciled audit summary was parsed from the current audit."}{" "}
        Source: {audit.source_path || "docs/phase2_execution_audit_v5_2026_07_01.md"}.
      </p>
      {firstAction ? (
        <p className="text-xs text-ink-soft dark:text-starlight leading-relaxed">
          Next audit action: {firstAction}
        </p>
      ) : null}
    </div>
  );
}

function OperatorActionsStatus({
  operatorActions,
}: {
  operatorActions: OperatorActionsSummaryView;
}) {
  const statusCounts = operatorActions.status_counts ?? {};
  const statusText = [
    ["open", statusCounts.open],
    ["partially done", statusCounts.partially_done],
    ["closed", statusCounts.closed],
  ]
    .filter(([, value]) => Number(value) > 0)
    .map(([label, value]) => `${value} ${label}`)
    .join(" · ");
  const focus = operatorActions.closeable_action ?? operatorActions.next_action;
  return (
    <div className="mt-2 rounded border border-rule dark:border-charcoal-1 bg-ice-0/70 dark:bg-charcoal-2/70 px-3 py-2">
      <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        Operator actions
      </p>
      <p className="text-xs font-mono text-ink dark:text-bright">
        {operatorActions.open_count}/{operatorActions.total_actions} not closed
        {operatorActions.closeable_count > 0
          ? ` · ${operatorActions.closeable_count} awaiting operator test`
          : ""}
        {statusText ? ` · ${statusText}` : ""}
      </p>
      {focus ? (
        <p className="text-xs text-ink-soft dark:text-starlight leading-relaxed">
          {operatorActions.closeable_action ? "Closeable now" : "Next action"}:{" "}
          {focus.action_id} — {focus.title}. Blocks: {focus.blocks}. Source:{" "}
          {operatorActions.source_path || "docs/OPERATOR_ACTIONS.md"}.
        </p>
      ) : (
        <p className="text-xs text-ink-soft dark:text-starlight leading-relaxed">
          No not-closed operator actions in{" "}
          {operatorActions.source_path || "docs/OPERATOR_ACTIONS.md"}.
        </p>
      )}
    </div>
  );
}

function ExecutionFocusSection({
  focus,
  operatorGateFocus,
}: {
  focus: ResolvedExecutionFocus | null;
  operatorGateFocus: OperatorGateFocusView | null;
}) {
  if (!focus && !operatorGateFocus) return null;

  return (
    <LemonCard colour="glacial" elevation="z1">
      <div className="p-4 space-y-2">
        <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
          Execution focus
        </p>
        {focus?.kind === "dependency_blocker" ? (
          <div className="space-y-1">
            <p className="text-sm font-serif text-ink dark:text-bright">
              Unblock {focus.blocker.node_id}
              {focus.blocker.blocker_sprint
                ? ` — ${formatSprintLabel(focus.blocker.blocker_sprint)}`
                : ""}
            </p>
            <p className="text-xs font-mono text-shadow-2 dark:text-moonlight">
              Clears dependency pressure for {focus.blocker.blocked_sprints.length}{" "}
              {focus.blocker.blocked_sprints.length === 1 ? "sprint" : "sprints"}.
            </p>
          </div>
        ) : focus?.kind === "dependency_ready" ? (
          <div className="space-y-1">
            <p className="text-sm font-serif text-ink dark:text-bright">
              Next dependency-ready sprint: {formatSprintLabel(focus.sprint)}
            </p>
            <p className="text-xs font-mono text-shadow-2 dark:text-moonlight">
              {focus.sprint.slug.replace(/-/g, " ")} · {focus.sprint.node_id}
            </p>
          </div>
        ) : operatorGateFocus ? (
          <div className="space-y-1">
            <p className="text-sm font-serif text-ink dark:text-bright">
              Close {operatorGateFocus.gate_id} — {operatorGateFocus.title}
            </p>
            <p className="text-xs font-mono text-shadow-2 dark:text-moonlight">
              {operatorGateFocus.status_raw || operatorGateFocus.status}
              {operatorGateFocus.owner ? ` · ${operatorGateFocus.owner}` : ""}
            </p>
            {operatorGateFocus.blocks && (
              <p className="text-xs text-ink-soft dark:text-starlight leading-relaxed">
                Blocks: {operatorGateFocus.blocks}
              </p>
            )}
            <p className="text-xs text-ink-soft dark:text-starlight leading-relaxed">
              Structural dependencies are clear; this focus is read from{" "}
              {operatorGateFocus.source_path || "docs/operator_gate_actions.md"}.
            </p>
          </div>
        ) : null}
      </div>
    </LemonCard>
  );
}

function CriticalPathSection({
  criticalPath,
  sprintById,
}: {
  criticalPath: string[];
  sprintById: Map<string, SprintView>;
}) {
  return (
    <div className="space-y-2">
      <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        DRW critical path
      </p>
      <div className="flex items-start gap-2 flex-wrap">
        {criticalPath.map((node, i) => {
          const sprint = sprintById.get(node);
          return (
            <span key={node} className="flex items-start gap-2">
              <span className="flex flex-col gap-1">
                <LemonTag colour="sun" dot>
                  {node}
                </LemonTag>
                {sprint && (
                  <span className="text-xs font-mono text-shadow-2 dark:text-moonlight">
                    {formatSprintLabel(sprint)} · {sprint.slug.replace(/-/g, " ")} ·{" "}
                    {sprint.status}
                  </span>
                )}
                {!sprint && (
                  <span className="text-xs font-mono text-shadow-2 dark:text-moonlight">
                    not found in sprint roster
                  </span>
                )}
              </span>
              {i < criticalPath.length - 1 && (
                <span
                  aria-hidden="true"
                  className="pt-0.5 text-shadow-1 dark:text-moonlight"
                >
                  →
                </span>
              )}
            </span>
          );
        })}
      </div>
      <p className="text-xs text-ink-soft dark:text-starlight">
        Read, Write and Speak all rest on this DRW spine. A slip here slips
        everything downstream.
      </p>
    </div>
  );
}

function DependencyBlockersSection({
  blockers,
}: {
  blockers: ResolvedDependencyBlocker[];
}) {
  if (blockers.length === 0) return null;
  return (
    <div className="space-y-2">
      <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        Dependency blockers
      </p>
      <LemonCard elevation="z1">
        <ul className="divide-y divide-rule dark:divide-charcoal-1">
          {blockers.map((blocker) => {
            const sample = blocker.blocked_sprints.slice(0, 3);
            const hidden = blocker.blocked_sprints.length - sample.length;
            return (
              <li
                key={blocker.node_id}
                className="flex flex-col gap-1 px-4 py-2.5 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <p className="text-sm font-serif text-ink dark:text-bright">
                    {blocker.node_id}
                  </p>
                  {blocker.blocker_sprint && (
                    <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
                      {formatSprintLabel(blocker.blocker_sprint)} ·{" "}
                      {blocker.blocker_sprint.slug.replace(/-/g, " ")} ·{" "}
                      {blocker.blocker_sprint.status}
                    </p>
                  )}
                  <p className="text-xs font-mono text-shadow-2 dark:text-moonlight">
                    {sample.map(formatSprintLabel).join(", ")}
                    {hidden > 0 ? ` +${hidden} more` : ""}
                  </p>
                </div>
                <LemonTag colour="default" dot>
                  blocks {blocker.blocked_sprints.length}{" "}
                  {blocker.blocked_sprints.length === 1 ? "sprint" : "sprints"}
                </LemonTag>
              </li>
            );
          })}
        </ul>
      </LemonCard>
    </div>
  );
}

function ReadyNowSection({ sprints }: { sprints: SprintView[] }) {
  return (
    <div className="space-y-2">
      <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        Dependency-ready
      </p>
      <LemonCard elevation="z1">
        {sprints.length > 0 ? (
          <ul className="divide-y divide-rule dark:divide-charcoal-1">
            {sprints.map((s) => (
              <li
                key={s.node_id}
                className="flex flex-col gap-1 px-4 py-2.5 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <p className="text-sm font-serif text-ink dark:text-bright">
                    {formatSprintLabel(s)}
                  </p>
                  <p className="text-xs font-mono text-shadow-2 dark:text-moonlight">
                    {s.slug.replace(/-/g, " ")}
                  </p>
                </div>
                <LemonTag colour="muted" dot>
                  {s.node_id}
                </LemonTag>
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-4 py-3 text-sm font-serif italic text-shadow-1 dark:text-moonlight">
            No sprint is dependency-ready under the current dependency state.
          </p>
        )}
      </LemonCard>
    </div>
  );
}

function RosterTable({
  roster,
  criticalPath,
}: {
  roster: RosterView;
  criticalPath: string[];
}) {
  const crit = new Set(criticalPath);
  const columns: LemonColumn<SprintView>[] = [
    {
      key: "sprint",
      header: "Sprint",
      width: "12%",
      render: (s) => (
        <span className="font-mono text-xs text-ink dark:text-bright">
          SPR-{String(s.sprint).padStart(2, "0")}
        </span>
      ),
    },
    {
      key: "slug",
      header: "Deliverable",
      render: (s) => (
        <span className="flex items-center gap-2">
          {crit.has(s.node_id) && (
            <LemonTag colour="sun" dot>
              critical path
            </LemonTag>
          )}
          <span className="text-sm text-ink dark:text-bright">
            {s.slug.replace(/-/g, " ")}
          </span>
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      width: "16%",
      render: (s) =>
        s.status === "unknown" ? (
          <span className="text-xs italic text-shadow-1 dark:text-moonlight">
            (product-owned)
          </span>
        ) : (
          <LemonTag colour={sprintStatusColour(s.status)}>{s.status}</LemonTag>
        ),
    },
    {
      key: "blocked",
      header: "Dependency state",
      width: "30%",
      render: (s) =>
        s.unblocked ? (
          <LemonTag colour="muted" dot>
            dependency-ready
          </LemonTag>
        ) : (
          <span className="text-xs font-mono text-shadow-2 dark:text-moonlight">
            waits on {s.blocked_on.join(", ")}
          </span>
        ),
    },
  ];

  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-2">
        <h3 className="text-base font-serif text-ink dark:text-bright">
          {roster.label}
        </h3>
        <span className="text-xs font-mono text-shadow-1 dark:text-moonlight">
          {roster.count} sprints
        </span>
      </div>
      <LemonTable<SprintView>
        rows={roster.sprints}
        columns={columns}
        rowKey={(s) => s.node_id}
        dense
        emptyState={
          <span className="text-xs italic text-shadow-1 dark:text-moonlight">
            No sprint files found for {roster.directory}/.
          </span>
        }
      />
    </div>
  );
}

function SubstrateLayerSection({ layers }: { layers: SubstrateLayerView[] }) {
  if (layers.length === 0) return null;
  return (
    <div className="space-y-2">
      <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        Substrate-execution layer (the foundation beneath the four workflows)
      </p>
      <LemonCard elevation="z1">
        <ul className="divide-y divide-rule dark:divide-charcoal-1">
          {layers.map((l) => (
            <li key={l.name} className="px-4 py-2.5 space-y-0.5">
              <p className="text-sm font-serif text-ink dark:text-bright">
                {l.name}
              </p>
              <p className="text-xs font-mono text-shadow-2 dark:text-moonlight">
                {l.owner} · {l.status}
              </p>
            </li>
          ))}
        </ul>
      </LemonCard>
    </div>
  );
}
