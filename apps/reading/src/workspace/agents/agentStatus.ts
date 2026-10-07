/**
 * agents/agentStatus.ts — SPR-10 M1: the five agent states, herdr's
 * attention order, the investigation-status mapping table, the derivation
 * of "done", the run-entry census over the context tree, and the toast
 * transition rule. PURE: no React, no storage, no store; one value import
 * (`isUnseen`, itself pure) so the unread comparison has ONE home.
 *
 * ── Vocabulary and order (refs/omarchy-herdr.md:328-343, R15/R16) ───────
 *   blocked (4)  needs input / approval / decision
 *   done    (3)  finished and NOT yet viewed
 *   working (2)  actively running
 *   idle    (1)  finished (or waiting) and seen
 *   unknown (0)  cannot classify
 * A badge over many agents shows the max (R16, `rollup`).
 *
 * ── The mapping table (InvestigationSummary.status → phase) ─────────────
 *   in_progress → working
 *   completed   → finished
 *   failed      → finished (detail failed)
 *   stopped     → finished (detail stopped)
 *   not_found   → unknown  (detail not_found)
 *   anything else, "" and undefined → unknown. NEVER idle by default
 *   (herdr's strict-blocked rule, refs/omarchy-herdr.md:412-416, applied to
 *   every unmatched value): a status the table does not know is shown as
 *   unknown, not quietly settled.
 * The table is a Map, so prototype keys ("constructor", "__proto__", ...)
 * cannot alias a row the way `obj[key]` would.
 *
 * ── The derivation of done (R17) ────────────────────────────────────────
 *   done  = finished ∧ ¬viewed-since-finish
 *   idle  = finished ∧ viewed-since-finish, and every `stopped` run
 *   The timestamp compared is `completed_at` (for failed, `completed_at ??
 *   since`) against workspace/seen.ts `lastSeenAt(investigationId)`, through
 *   shared/researchState.ts `isUnseen` verbatim: no finish timestamp reads
 *   as not finished (idle), an unparsable one as unread (done), no seen
 *   timestamp as unread (done). Focusing marks seen (the store's
 *   markFocused); reading the pane does not.
 *
 * ── The only road to blocked ────────────────────────────────────────────
 *   `RawObservation.needsInput === true`. No wire sets it today
 *   (lib/api.ts:389 InvestigationSummary.status has no approval value); it
 *   is the SPR-B seam. See BLOCKED_ROUTE.
 *
 * ── Two vocabularies, deliberately ──────────────────────────────────────
 *   shared/researchState.ts:72-74 maps `failed` to its "blocked" (NavRail,
 *   attention.ts:28 ranks it 4). This module does NOT: a failed run is
 *   done-until-seen, then idle, with reason "failed". One owner of the word
 *   is an SPR-B/operator ruling (handoff §6.4).
 */
import type { AgentNode, ContextTree, ProjectNode } from "../contracts/tree";
import { isUnseen } from "../../shared/researchState";

export type AgentStatus = "blocked" | "working" | "done" | "idle" | "unknown";

/** Attention order (herdr R16), NOT the R15 list order. */
export const AGENT_STATUSES = ["blocked", "done", "working", "idle", "unknown"] as const;

export const ATTENTION_RANK: Readonly<Record<AgentStatus, number>> = Object.freeze({
  blocked: 4,
  done: 3,
  working: 2,
  idle: 1,
  unknown: 0,
});

export function rankOf(s: AgentStatus): number {
  return ATTENTION_RANK[s];
}

/** The max by rank; null for no members (never a phantom state). */
export function rollup(xs: readonly AgentStatus[]): AgentStatus | null {
  let best: AgentStatus | null = null;
  for (const x of xs) if (best === null || rankOf(x) > rankOf(best)) best = x;
  return best;
}

/** What a source observed about one run. `status` is `string` on purpose:
 *  it is the untrusted wire value, mapped through the table at read time. */
export interface RawObservation {
  status: string | undefined;
  completedAt: string | null;
  /** completed_at ?? started_at. */
  since: string | null;
  title: string | null;
  observedAt: number;
  /** The SPR-B seam: the only way to `blocked`. */
  needsInput?: true;
}

export type Phase = "working" | "finished" | "unknown";
export type PhaseDetail = "failed" | "stopped" | "not_found";
export interface PhaseRow {
  phase: Phase;
  detail?: PhaseDetail;
}

export const INVESTIGATION_PHASE_TABLE: ReadonlyMap<string, PhaseRow> = new Map<string, PhaseRow>([
  ["in_progress", { phase: "working" }],
  ["completed", { phase: "finished" }],
  ["failed", { phase: "finished", detail: "failed" }],
  ["stopped", { phase: "finished", detail: "stopped" }],
  ["not_found", { phase: "unknown", detail: "not_found" }],
]);

const UNKNOWN_ROW: PhaseRow = Object.freeze({ phase: "unknown" });

/** Total: every string, "" and undefined have a row (unknown by default). */
export function phaseOf(status: string | undefined): PhaseRow {
  if (status === undefined) return UNKNOWN_ROW;
  return INVESTIGATION_PHASE_TABLE.get(status) ?? UNKNOWN_ROW;
}

/** Documentation constant: the one field that produces `blocked`. */
export const BLOCKED_ROUTE = "needsInput" as const;

/** Unread since the finish, through the ONE comparison in researchState.ts. */
export function isUnseenSince(finishedAtIso: string | null, lastSeenIso: string | null): boolean {
  return isUnseen({ status: "completed", completed_at: finishedAtIso }, lastSeenIso);
}

/** The inverse: viewed since the finish (a missing finish counts as viewed,
 *  i.e. there is nothing unread to show). */
export function isViewedSince(finishedAtIso: string | null, lastSeenIso: string | null): boolean {
  return !isUnseenSince(finishedAtIso, lastSeenIso);
}

export type AttentionReason = PhaseDetail | "no-run" | "outside-window";

export interface Attention {
  state: AgentStatus;
  reason?: AttentionReason;
}

/**
 * The state one observation reads as. Never idle by default, never throws,
 * never consults researchStateFor/attentionScore.
 *   needsInput        → blocked
 *   in_progress       → working
 *   completed         → done if unseen since completedAt, else idle
 *   failed            → done if unseen since completedAt ?? since, else idle (reason failed)
 *   stopped           → idle (reason stopped)
 *   not_found         → unknown (reason not_found)
 *   undefined raw     → unknown (reason: the caller's absentReason)
 *   anything else     → unknown
 */
export function attentionOf(
  raw: RawObservation | undefined,
  lastSeenIso: string | null,
  absentReason: "no-run" | "outside-window" = "outside-window",
): Attention {
  if (raw === undefined) return { state: "unknown", reason: absentReason };
  if (raw.needsInput === true) return { state: "blocked" };
  const row = phaseOf(raw.status);
  if (row.phase === "working") return { state: "working" };
  if (row.phase === "unknown") return row.detail ? { state: "unknown", reason: row.detail } : { state: "unknown" };
  // finished
  if (row.detail === "stopped") return { state: "idle", reason: "stopped" };
  const finishedAt = row.detail === "failed" ? (raw.completedAt ?? raw.since) : raw.completedAt;
  const state: AgentStatus = isUnseenSince(finishedAt, lastSeenIso) ? "done" : "idle";
  return row.detail ? { state, reason: row.detail } : { state };
}

/** One run the monitor knows about: a tree AgentNode, a tree investigation
 *  RunDescriptor, or both collapsed into one (same runId). */
export interface RunEntry {
  runId: string;
  viewId: string;
  viewOpen: boolean;
  kind: "research-thread" | "dialogue";
  investigationId?: string;
  title: string;
  /** Owning ProjectNode.id (null for a cross-project agent). */
  projectId: string | null;
  /** Ids of every ProjectNode from the root down to the node the entry hangs
   *  on, inclusive. [] for a cross-project agent. */
  groupPath: readonly string[];
  /** The root's title (the picker's group heading); "" for []. */
  rootTitle: string;
  /** AgentNode.status.state / RunDescriptor.state, when the tree carries one. */
  treeState?: string;
  treeSince?: string;
}

function entryOfAgent(a: AgentNode, path: readonly ProjectNode[]): RunEntry {
  return {
    runId: a.id,
    viewId: a.viewId,
    viewOpen: a.viewOpen,
    kind: a.kind,
    ...(a.investigationId !== undefined ? { investigationId: a.investigationId } : {}),
    title: a.title,
    projectId: a.projectId,
    groupPath: path.map((n) => n.id),
    rootTitle: path[0]?.title ?? "",
    ...(a.status?.state !== undefined ? { treeState: a.status.state } : {}),
    ...(a.status?.since ? { treeSince: a.status.since } : {}),
  };
}

/**
 * Every run in the tree, keyed by runId: each `node.agents[*]` (viewOpen
 * true) and each `source.kind === "investigation"` node's RunDescriptor
 * (viewOpen false), plus `crossProjectAgents` (groupPath []). An AgentNode
 * and a RunDescriptor with the same runId collapse into ONE entry; the
 * AgentNode's fields win and viewOpen is true. A tree in status "error"
 * with populated roots is walked as-is; "unfed" yields an empty map.
 */
export function collectRuns(tree: ContextTree): ReadonlyMap<string, RunEntry> {
  const out = new Map<string, RunEntry>();
  const put = (e: RunEntry) => {
    const prev = out.get(e.runId);
    if (!prev) {
      out.set(e.runId, e);
      return;
    }
    // Collapse: the AgentNode (viewOpen) wins over the RunDescriptor.
    if (e.viewOpen && !prev.viewOpen) out.set(e.runId, { ...e, viewOpen: true });
    else if (!e.viewOpen && prev.viewOpen) out.set(e.runId, { ...prev, viewOpen: true });
  };
  const walk = (n: ProjectNode, ancestors: readonly ProjectNode[]) => {
    const path = [...ancestors, n];
    if (n.source.kind === "investigation") {
      const run = n.source.run;
      put({
        runId: n.id,
        viewId: run.agentViewId,
        viewOpen: false,
        kind: "research-thread",
        investigationId: n.id,
        title: n.title,
        projectId: n.parentId,
        groupPath: path.map((p) => p.id),
        rootTitle: path[0]?.title ?? "",
        ...(run.state !== undefined ? { treeState: run.state } : {}),
        ...(run.since ? { treeSince: run.since } : {}),
      });
    }
    for (const a of n.agents) put(entryOfAgent(a, path));
    for (const c of n.children) walk(c, path);
  };
  for (const r of tree.roots) walk(r, []);
  for (const a of tree.crossProjectAgents) put(entryOfAgent(a, []));
  return out;
}

export type Transition = { kind: "needs-you" } | { kind: "finished" } | null;

/**
 * herdr R18: a toast fires only on a transition INTO blocked ("needs you")
 * or a background completion ("finished"), never for the active tab, never
 * during the startup grace, never on a first observation.
 */
export function toastFor(
  prev: AgentStatus | undefined,
  next: AgentStatus,
  ctx: { isActiveView: boolean; inStartupGrace: boolean },
): Transition {
  if (ctx.inStartupGrace || prev === undefined || prev === next) return null;
  if (next === "blocked") return { kind: "needs-you" };
  if (prev === "working" && next === "done" && !ctx.isActiveView) return { kind: "finished" };
  return null;
}
