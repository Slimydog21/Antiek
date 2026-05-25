/**
 * workflowTaxonomy — the single source of truth that maps every mode to
 * exactly one of the four workflows (Research · Read · Write · Speak) or an
 * explicit shared/operator bucket.
 *
 * Functional rationale (frontend-design spec, SPR-02): naming is a functional
 * act. A mode exists in the product to do work; the taxonomy records *which*
 * work, so the rail can present four workflows, the launcher can group the
 * rest, and the content tree can scope to the active workflow. Nothing may
 * exist in the product without a stated job — an unmapped mode fails the
 * completeness test. The four workflows hold the modes that *are* the work;
 * the shared bucket holds the infrastructure the work runs on (money,
 * governance, system), reachable from the launcher + ⌘K, never the rail.
 *
 * Real count on `main`: 34 mode directories + the `shared/` dir = 35.
 */

export type Workflow = "research" | "read" | "write" | "speak" | "shared";

/** The four workflows that earn a rail entry — in display order. */
export const WORKFLOWS: readonly Exclude<Workflow, "shared">[] = [
  "research",
  "read",
  "write",
  "speak",
] as const;

export const WORKFLOW_LABEL: Record<Exclude<Workflow, "shared">, string> = {
  research: "Research",
  read: "Read",
  write: "Write",
  speak: "Speak",
};

export interface ModeEntry {
  /** Which workflow this mode's work belongs to, or `shared` for infra. */
  workflow: Workflow;
  /** One-line job. For `shared`, why it spans workflows rather than owning one. */
  reason: string;
  /** Whether the mode is built today or a planned stub (drives honest stubs). */
  builtState: "built" | "stub";
}

/**
 * Every mode directory under apps/reading/src/modes/ → its entry.
 * Candidate-shared judgment calls (Stats/Outcomes/Map/Replay; Notebook) are
 * decided here with a reason; flip them only with a documented rationale.
 */
export const WORKFLOW_TAXONOMY: Record<string, ModeEntry> = {
  // ---- Research (10): the deep-research workspace + its analytics ----
  ResearchWorkstation: { workflow: "research", reason: "the chat-first investigation surface", builtState: "built" },
  InvestigationsIndex: { workflow: "research", reason: "browse all investigations + chase trees", builtState: "built" },
  WrestleApp: { workflow: "research", reason: "single-document deep read is a research mode", builtState: "built" },
  BrainstormStation: { workflow: "research", reason: "ideation feeds the same insight/question graph", builtState: "built" },
  Map: { workflow: "research", reason: "spatial view of the research graph", builtState: "built" },
  Replay: { workflow: "research", reason: "trajectory replay of an investigation", builtState: "built" },
  Outcomes: { workflow: "research", reason: "operator-graded research outcome", builtState: "built" },
  OutcomesIndex: { workflow: "research", reason: "browse graded outcomes", builtState: "built" },
  Backtest: { workflow: "research", reason: "synthesis backtest over a research result", builtState: "built" },
  Stats: { workflow: "research", reason: "compounding-graph metrics (research analytics)", builtState: "built" },

  // ---- Read (4): the corpus + literate analysis ----
  DocumentsIndex: { workflow: "read", reason: "the source corpus", builtState: "built" },
  Sources: { workflow: "read", reason: "acquisition + ingestion of readable sources", builtState: "built" },
  Notebook: { workflow: "read", reason: "literate-analysis surface; Write authors into it via the shared editor", builtState: "built" },
  NotebooksIndex: { workflow: "read", reason: "browse notebooks", builtState: "built" },

  // ---- Write (1): authoring ----
  CreationStudio: { workflow: "write", reason: "compose deliverables from insight blocks", builtState: "built" },

  // ---- Speak (2): interview-as-acquisition ----
  Interview: { workflow: "speak", reason: "conduct an interview", builtState: "built" },
  InterviewIndex: { workflow: "speak", reason: "browse interviews", builtState: "built" },

  // ---- Shared / operator (18): infra the four workflows run on ----
  Login: { workflow: "shared", reason: "auth — precedes every workflow", builtState: "built" },
  Settings: { workflow: "shared", reason: "account + config spanning all workflows", builtState: "built" },
  OperatorDashboard: { workflow: "shared", reason: "internal operations", builtState: "built" },
  TrustCenter: { workflow: "shared", reason: "public privacy posture (logged-out reachable)", builtState: "built" },
  PrivacyDashboard: { workflow: "shared", reason: "partition/privacy controls", builtState: "built" },
  Billing: { workflow: "shared", reason: "pay-as-you-go account billing", builtState: "built" },
  Pricing: { workflow: "shared", reason: "pricing surface", builtState: "built" },
  CreatorPayouts: { workflow: "shared", reason: "IP-attribution payouts (money infra)", builtState: "built" },
  PayoutDashboard: { workflow: "shared", reason: "payout state (money infra)", builtState: "built" },
  PayoutsAudit: { workflow: "shared", reason: "payout audit (money infra)", builtState: "built" },
  MarketplaceMetrics: { workflow: "shared", reason: "ad-economics metrics (money infra)", builtState: "built" },
  AdvertiserConsole: { workflow: "shared", reason: "advertiser onboarding (money infra)", builtState: "built" },
  Federation: { workflow: "shared", reason: "cross-graph federation (system)", builtState: "built" },
  CrossGraphCitations: { workflow: "shared", reason: "cross-graph citation view (system)", builtState: "built" },
  Loop3: { workflow: "shared", reason: "self-iteration / RL governance (system)", builtState: "built" },
  SkillRules: { workflow: "shared", reason: "harness rule editor (system)", builtState: "built" },
  SkillRuleDetail: { workflow: "shared", reason: "harness rule detail (system)", builtState: "built" },
  shared: { workflow: "shared", reason: "shared components/util directory, not a mode", builtState: "built" },
};

/** Workflow → its mapped mode ids. */
export function modesForWorkflow(w: Workflow): string[] {
  return Object.entries(WORKFLOW_TAXONOMY)
    .filter(([, e]) => e.workflow === w)
    .map(([id]) => id);
}

/** Mode id → workflow (undefined if unmapped — the completeness test forbids that). */
export function workflowForMode(id: string): Workflow | undefined {
  return WORKFLOW_TAXONOMY[id]?.workflow;
}

/**
 * Route pathname → the workflow it belongs to. Used to derive the active
 * workflow from the URL (so a deep link sets the rail correctly). Ordered
 * most-specific-first; falls back to `research` (the home workflow).
 *
 * Functional rationale: the active workflow is a property of *what the user is
 * looking at*, so it must be recoverable from the route, not only from a rail
 * click — otherwise a refresh or a shared link would lose it.
 */
const ROUTE_WORKFLOW: ReadonlyArray<readonly [RegExp, Exclude<Workflow, "shared">]> = [
  [/^\/(inv|investigations|wrestle|brainstorm|map|replay|outcomes|backtest|stats)(\/|$)/, "research"],
  [/^\/(documents|notebooks?|sources)(\/|$)/, "read"],
  [/^\/(create|write)(\/|$)/, "write"],
  [/^\/(interview|interviews)(\/|$)/, "speak"],
];

/** Derive the active workflow from a route; `null` for shared/operator routes. */
export function workflowForRoute(pathname: string): Exclude<Workflow, "shared"> | null {
  if (pathname === "/" || pathname === "") return "research";
  for (const [re, w] of ROUTE_WORKFLOW) if (re.test(pathname)) return w;
  return null; // shared/operator route (billing, settings, trust, …): no active workflow
}

/** The route a rail click on a workflow lands on (its default scene). */
export const WORKFLOW_HOME: Record<Exclude<Workflow, "shared">, string> = {
  research: "/",
  read: "/documents",
  write: "/create",
  speak: "/interviews",
};
