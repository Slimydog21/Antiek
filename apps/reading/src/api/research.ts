/**
 * Deep Research Workspace API client (DRW SPR-06 transport → SPR-09 UI).
 *
 * Mirrors `interfaces/research/api/cascade_routes.py` (prefix `/research`).
 * The cascade lifecycle: plan → edit → approve → launch → watch → steer.
 * The frontend never decides launchability or cost — it renders what the
 * backend's glass-box gate + runner report.
 */

import { API_BASE, ApiError, apiFetch } from "../lib/api";

export const PLAN_MAX_NODE_DEPTH = 6;

// ── Plan tree (mirrors roles/cascade_planner PlanTree.to_dict) ──────────

export interface PlanNode {
  local_id: string;
  question: string;
  rationale: string;
  focus_boundary: string;
  budget_usd: number | null;
  max_depth: number | null;
  graph_node_id: string | null;
  children: PlanNode[];
}

export interface PlanApproval {
  state: "draft" | "approved";
  approved_at: string | null;
  approved_by: string | null;
  plan_version: number;
}

export interface PlanTree {
  root: PlanNode;
  seed_kind: string;
  seed_provenance: Record<string, unknown>;
  approval: PlanApproval;
  root_investigation_id: string | null;
}

export interface CreatePlanResponse {
  root_node_id: string;
  tree: PlanTree;
  capped_nodes: string[];
  over_broad_leaves: string[];
}

export interface PlanResponse {
  root_node_id: string;
  tree: PlanTree;
  launchable: boolean;
}

export interface ApproveResponse {
  root_node_id: string;
  approval: PlanApproval;
  launchable: boolean;
}

// ── Session (mirrors CascadeSession status/cost) ────────────────────────

export type ResearchRunState =
  | "pending" | "running" | "paused" | "stopping"
  | "done" | "stopped" | "failed" | "budget_halted";

export const TERMINAL_STATES: ReadonlySet<ResearchRunState> = new Set<ResearchRunState>([
  "done", "stopped", "failed", "budget_halted",
]);

export interface ResearchStatus {
  investigation_id: string;
  sub_question: string;
  state: ResearchRunState;
  question_node_id?: string | null;
}

export interface SessionCost {
  per_research: Record<string, number>;
  session_total_usd: number;
  aggregate_spent_usd: number;
  aggregate_cap_usd: number;
}

export interface SessionStatus {
  session_id: string;
  live: boolean;
  researches: ResearchStatus[];
  cost?: SessionCost | null;
  all_terminal?: boolean;
}

export interface LaunchResponse {
  session_id: string;
  researches: { investigation_id: string; sub_question: string; question_node_id: string | null }[];
  aggregate_cap_usd: number | null;
}

export type SteerKind = "pause" | "resume" | "stop" | "redirect" | "deepen";

/** The per-research spend ceiling the runner applies when launch omits one
 * (mirrors runtime/research_runner protocol.BudgetCap). The entry UI reads
 * this to show "estimated up to $X for N researches" — never a hardcoded
 * number that would drift from the contract. */
export interface BudgetDefaults {
  per_research_cost_usd: number;
  per_research_max_steps: number;
  /** The host-local runner's real bounded-semaphore concurrency cap
   * (mirrors runtime/research_runner/host_local.DEFAULT_MAX_CONCURRENCY). The
   * multi-research monitor reads this to show an honest "N running, M queued"
   * — the surplus past the cap is queued behind the semaphore, never a number
   * the UI invents. */
  host_local_max_concurrency: number;
}

// ── Suggested next researches (SPR-09 — the compounding flywheel) ───────
//
// The §7 continuous daemon already computes scored evidentiary gaps. This is
// the read-only surface over its output: each suggestion is a plain-language
// "thread worth chasing", grounded in the research it came from. The client
// never sees the daemon's vocabulary (evidentiary_gap / chase score /
// policy_id) — those are translated server-side. `key` is the opaque dedupe
// handle, never rendered.

export interface Suggestion {
  key: string;
  question: string;
  suggested_retrieval: string | null;
  seen_in_research_count: number;
  source_investigation_id: string | null;
}

export interface SuggestionsResponse {
  count: number;
  suggestions: Suggestion[];
}

// ── Request helpers ─────────────────────────────────────────────────────

async function jsonOrThrow(resp: Response, what: string): Promise<unknown> {
  if (!resp.ok) {
    throw new ApiError(`${what} failed: HTTP ${resp.status}`, resp.status, await resp.text());
  }
  return resp.json();
}

function post(path: string, body: unknown): Promise<unknown> {
  return apiFetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => jsonOrThrow(r, `POST ${path}`));
}

function get(path: string): Promise<unknown> {
  return apiFetch(`${API_BASE}${path}`).then((r) => jsonOrThrow(r, `GET ${path}`));
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

function finiteNonNegativeNumber(value: unknown): number | null {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function positiveSafeInteger(value: unknown): number | null {
  const parsed = finiteNonNegativeNumber(value);
  return parsed !== null && Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function nonNegativeSafeInteger(value: unknown): number | null {
  const parsed = finiteNonNegativeNumber(value);
  return parsed !== null && Number.isSafeInteger(parsed) ? parsed : null;
}

function safeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const text = nonEmptyString(item);
    return text ? [text] : [];
  });
}

function uniqueStringArray(value: unknown): string[] {
  return Array.from(new Set(safeStringArray(value)));
}

function requireString(value: unknown, field: string): string {
  const text = nonEmptyString(value);
  if (!text) throw new Error(`Malformed research response: ${field}.`);
  return text;
}

function requireRequestString(value: unknown, field: string): string {
  const text = nonEmptyString(value);
  if (!text) throw new TypeError(`${field} must be a non-empty string`);
  return text;
}

function optionalRequestStrings(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const items = safeStringArray(value);
  return items.length > 0 ? items : undefined;
}

function optionalNonNegativeBudget(value: unknown, field: string): number | undefined {
  if (value == null) return undefined;
  const amount = finiteNonNegativeNumber(value);
  if (amount === null) throw new TypeError(`${field} must be a non-negative number`);
  return amount;
}

function optionalNonNegativeDepth(value: unknown, field: string): number | undefined {
  if (value == null) return undefined;
  const depth = nonNegativeSafeInteger(value);
  if (depth === null) throw new TypeError(`${field} must be a non-negative safe integer`);
  return depth;
}

function requirePositiveRequestInteger(value: unknown, field: string): number {
  const amount = positiveSafeInteger(value);
  if (amount === null) throw new RangeError(`${field} must be a positive safe integer`);
  return amount;
}

function safePlanApproval(value: unknown): PlanApproval {
  const approval = record(value);
  return {
    state: approval?.state === "approved" ? "approved" : "draft",
    approved_at: nullableString(approval?.approved_at),
    approved_by: nullableString(approval?.approved_by),
    plan_version: positiveSafeInteger(approval?.plan_version) ?? 1,
  };
}

function safePlanNode(value: unknown, fallbackLocalId: string): PlanNode | null {
  const node = record(value);
  if (!node) return null;
  const localId = nonEmptyString(node.local_id) ?? fallbackLocalId;
  const question = nonEmptyString(node.question);
  if (!question) return null;
  const children = Array.isArray(node.children)
    ? node.children.flatMap((child, index) => {
        const safe = safePlanNode(child, `${localId}.${index + 1}`);
        return safe ? [safe] : [];
      })
    : [];
  const maxDepth = nonNegativeSafeInteger(node.max_depth);
  return {
    local_id: localId,
    question,
    rationale: nonEmptyString(node.rationale) ?? "",
    focus_boundary: nonEmptyString(node.focus_boundary) ?? "",
    budget_usd: finiteNonNegativeNumber(node.budget_usd),
    max_depth: maxDepth !== null && maxDepth >= 1 && maxDepth <= PLAN_MAX_NODE_DEPTH
      ? maxDepth
      : null,
    graph_node_id: nullableString(node.graph_node_id),
    children,
  };
}

function safePlanTree(value: unknown): PlanTree {
  const tree = record(value);
  const root = safePlanNode(tree?.root, "root");
  if (!root) throw new Error("Malformed research response: tree.root.");
  return {
    root,
    seed_kind: nonEmptyString(tree?.seed_kind) ?? "problem",
    seed_provenance: record(tree?.seed_provenance) ?? {},
    approval: safePlanApproval(tree?.approval),
    root_investigation_id: nullableString(tree?.root_investigation_id),
  };
}

function safeCreatePlanResponse(value: unknown): CreatePlanResponse {
  const body = record(value);
  if (!body) throw new Error("Malformed research response: body.");
  return {
    root_node_id: requireString(body.root_node_id, "root_node_id"),
    tree: safePlanTree(body.tree),
    capped_nodes: uniqueStringArray(body.capped_nodes),
    over_broad_leaves: uniqueStringArray(body.over_broad_leaves),
  };
}

function safePlanResponse(value: unknown): PlanResponse {
  const body = record(value);
  if (!body) throw new Error("Malformed research response: body.");
  return {
    root_node_id: requireString(body.root_node_id, "root_node_id"),
    tree: safePlanTree(body.tree),
    launchable: body.launchable === true,
  };
}

function safeApproveResponse(value: unknown): ApproveResponse {
  const body = record(value);
  if (!body) throw new Error("Malformed research response: body.");
  return {
    root_node_id: requireString(body.root_node_id, "root_node_id"),
    approval: safePlanApproval(body.approval),
    launchable: body.launchable === true,
  };
}

function safeBudgetDefaults(value: unknown): BudgetDefaults {
  const body = record(value);
  return {
    per_research_cost_usd: finiteNonNegativeNumber(body?.per_research_cost_usd) ?? 0,
    per_research_max_steps: positiveSafeInteger(body?.per_research_max_steps) ?? 1,
    host_local_max_concurrency: positiveSafeInteger(body?.host_local_max_concurrency) ?? 1,
  };
}

function safeSuggestion(value: unknown): Suggestion | null {
  const suggestion = record(value);
  if (!suggestion) return null;
  const key = nonEmptyString(suggestion.key);
  const question = nonEmptyString(suggestion.question);
  if (!key || !question) return null;
  return {
    key,
    question,
    suggested_retrieval: nullableString(suggestion.suggested_retrieval),
    seen_in_research_count: nonNegativeSafeInteger(suggestion.seen_in_research_count) ?? 0,
    source_investigation_id: nullableString(suggestion.source_investigation_id),
  };
}

function safeSuggestionsResponse(value: unknown): SuggestionsResponse {
  const body = record(value);
  const suggestions = Array.isArray(body?.suggestions)
    ? body.suggestions.flatMap((item) => {
        const suggestion = safeSuggestion(item);
        return suggestion ? [suggestion] : [];
      })
    : [];
  return {
    count: nonNegativeSafeInteger(body?.count) ?? suggestions.length,
    suggestions,
  };
}

function safeResearchState(value: unknown): ResearchRunState {
  return typeof value === "string" && TERMINAL_STATES.has(value as ResearchRunState)
    ? (value as ResearchRunState)
    : value === "pending" || value === "running" || value === "paused" || value === "stopping"
      ? value
      : "failed";
}

function safeResearchStatus(value: unknown): ResearchStatus | null {
  const research = record(value);
  if (!research) return null;
  const investigationId = nonEmptyString(research.investigation_id);
  if (!investigationId) return null;
  return {
    investigation_id: investigationId,
    sub_question: nonEmptyString(research.sub_question) ?? "Untitled research",
    state: safeResearchState(research.state),
    question_node_id: nullableString(research.question_node_id),
  };
}

function safeSessionCost(value: unknown): SessionCost {
  const body = record(value);
  const perResearchRaw = record(body?.per_research);
  const per_research = perResearchRaw
    ? Object.fromEntries(
        Object.entries(perResearchRaw).flatMap(([key, raw]) => {
          const id = nonEmptyString(key);
          const amount = finiteNonNegativeNumber(raw);
          return id && amount !== null ? [[id, amount]] : [];
        }),
      )
    : {};
  return {
    per_research,
    session_total_usd: finiteNonNegativeNumber(body?.session_total_usd) ?? 0,
    aggregate_spent_usd: finiteNonNegativeNumber(body?.aggregate_spent_usd) ?? 0,
    aggregate_cap_usd: finiteNonNegativeNumber(body?.aggregate_cap_usd) ?? 0,
  };
}

function safeSessionStatus(value: unknown): SessionStatus {
  const body = record(value);
  if (!body) throw new Error("Malformed research response: body.");
  const researches = Array.isArray(body.researches)
    ? body.researches.flatMap((item) => {
        const research = safeResearchStatus(item);
        return research ? [research] : [];
      })
    : [];
  return {
    session_id: requireString(body.session_id, "session_id"),
    live: body.live === true,
    researches,
    cost: body.cost == null ? null : safeSessionCost(body.cost),
    all_terminal:
      typeof body.all_terminal === "boolean" ? body.all_terminal : undefined,
  };
}

function safeLaunchResponse(value: unknown): LaunchResponse {
  const body = record(value);
  if (!body) throw new Error("Malformed research response: body.");
  const researches = Array.isArray(body.researches)
    ? body.researches.flatMap((item) => {
        const research = record(item);
        const investigationId = nonEmptyString(research?.investigation_id);
        if (!investigationId) return [];
        return [{
          investigation_id: investigationId,
          sub_question: nonEmptyString(research?.sub_question) ?? "Untitled research",
          question_node_id: nullableString(research?.question_node_id),
        }];
      })
    : [];
  return {
    session_id: requireString(body.session_id, "session_id"),
    researches,
    aggregate_cap_usd: finiteNonNegativeNumber(body.aggregate_cap_usd),
  };
}

function safeSteerResponse(value: unknown): {
  session_id: string;
  investigation_id: string;
  state: ResearchRunState | null;
} {
  const body = record(value);
  if (!body) throw new Error("Malformed research response: body.");
  return {
    session_id: requireString(body.session_id, "session_id"),
    investigation_id: requireString(body.investigation_id, "investigation_id"),
    state: body.state == null ? null : safeResearchState(body.state),
  };
}

// ── Plan lifecycle (SPR-05 over HTTP) ───────────────────────────────────

export function getBudgetDefaults(): Promise<BudgetDefaults> {
  return get("/research/budget-defaults").then(safeBudgetDefaults);
}

/** SPR-09: the daemon's scored gaps as suggested next researches. READ-ONLY —
 * a plain GET that costs nothing; the only spend is an explicit chase, which
 * goes through `startInvestigation` (the existing capped launch path), not
 * here. `limit` bounds the displayed count (rank + cap, never a flood). */
export function getSuggestions(limit = 8): Promise<SuggestionsResponse> {
  const resolvedLimit = requirePositiveRequestInteger(limit, "limit");
  return get(`/research/suggestions?limit=${encodeURIComponent(String(resolvedLimit))}`)
    .then(safeSuggestionsResponse);
}

export function createPlan(req: {
  problem: string;
  sub_questions?: string[];
  max_depth?: number;
}): Promise<CreatePlanResponse> {
  const body: {
    problem: string;
    sub_questions?: string[];
    max_depth?: number;
  } = {
    problem: requireRequestString(req.problem, "problem"),
  };
  const subQuestions = optionalRequestStrings(req.sub_questions);
  if (subQuestions) body.sub_questions = subQuestions;
  const maxDepth = optionalNonNegativeDepth(req.max_depth, "max_depth");
  if (maxDepth !== undefined) body.max_depth = maxDepth;
  return post("/research/plans", body).then(safeCreatePlanResponse);
}

export function getPlan(rootId: string): Promise<PlanResponse> {
  const resolvedRootId = requireRequestString(rootId, "rootId");
  return get(`/research/plans/${encodeURIComponent(resolvedRootId)}`).then(safePlanResponse);
}

export function editPlan(rootId: string, edit: {
  op: "add_child" | "remove" | "reword" | "set_budget" | "split";
  target_local_id: string;
  question?: string;
  budget_usd?: number;
  max_depth?: number;
  into?: string[];
}): Promise<PlanResponse> {
  const resolvedRootId = requireRequestString(rootId, "rootId");
  const body: {
    op: "add_child" | "remove" | "reword" | "set_budget" | "split";
    target_local_id: string;
    question?: string;
    budget_usd?: number;
    max_depth?: number;
    into?: string[];
  } = {
    op: edit.op,
    target_local_id: requireRequestString(edit.target_local_id, "target_local_id"),
  };
  if (edit.question !== undefined) {
    body.question = requireRequestString(edit.question, "question");
  }
  const budget = optionalNonNegativeBudget(edit.budget_usd, "budget_usd");
  if (budget !== undefined) body.budget_usd = budget;
  const maxDepth = optionalNonNegativeDepth(edit.max_depth, "max_depth");
  if (maxDepth !== undefined) body.max_depth = maxDepth;
  const into = optionalRequestStrings(edit.into);
  if (into) body.into = into;
  return post(`/research/plans/${encodeURIComponent(resolvedRootId)}/edit`, body)
    .then(safePlanResponse);
}

export function approvePlan(rootId: string, approver = "__operator__"): Promise<ApproveResponse> {
  const resolvedRootId = requireRequestString(rootId, "rootId");
  const resolvedApprover = requireRequestString(approver, "approver");
  return post(`/research/plans/${encodeURIComponent(resolvedRootId)}/approve`, { approver: resolvedApprover })
    .then(safeApproveResponse);
}

// ── Launch + session (SPR-06) ───────────────────────────────────────────

export function launchPlan(rootId: string, req: {
  per_research_budget_usd?: number;
  aggregate_budget_usd?: number | null;
} = {}): Promise<LaunchResponse> {
  const resolvedRootId = requireRequestString(rootId, "rootId");
  const body: {
    per_research_budget_usd?: number;
    aggregate_budget_usd?: number | null;
  } = {};
  const perResearchBudget = optionalNonNegativeBudget(
    req.per_research_budget_usd,
    "per_research_budget_usd",
  );
  if (perResearchBudget !== undefined) body.per_research_budget_usd = perResearchBudget;
  if (req.aggregate_budget_usd === null) {
    body.aggregate_budget_usd = null;
  } else {
    const aggregateBudget = optionalNonNegativeBudget(
      req.aggregate_budget_usd,
      "aggregate_budget_usd",
    );
    if (aggregateBudget !== undefined) body.aggregate_budget_usd = aggregateBudget;
  }
  return post(`/research/plans/${encodeURIComponent(resolvedRootId)}/launch`, body)
    .then(safeLaunchResponse);
}

export function getSession(sessionId: string): Promise<SessionStatus> {
  const resolvedSessionId = requireRequestString(sessionId, "sessionId");
  return get(`/research/sessions/${encodeURIComponent(resolvedSessionId)}`)
    .then(safeSessionStatus);
}

export function getSessionCost(sessionId: string): Promise<SessionCost> {
  const resolvedSessionId = requireRequestString(sessionId, "sessionId");
  return get(`/research/sessions/${encodeURIComponent(resolvedSessionId)}/cost`)
    .then(safeSessionCost);
}

export function steerResearch(
  sessionId: string,
  investigationId: string,
  kind: SteerKind,
  payload?: Record<string, unknown>,
): Promise<{ session_id: string; investigation_id: string; state: ResearchRunState | null }> {
  const resolvedSessionId = requireRequestString(sessionId, "sessionId");
  const resolvedInvestigationId = requireRequestString(investigationId, "investigationId");
  return post(
    `/research/sessions/${encodeURIComponent(resolvedSessionId)}/researches/${encodeURIComponent(resolvedInvestigationId)}/steer`,
    { kind, payload: payload ?? null },
  ).then(safeSteerResponse);
}

/** SSE endpoint URL — the finer-grained per-step stream. The SPR-09 monitor
 * polls `getSession` (the durable, authoritative source) for robustness;
 * this is here for a future EventSource upgrade to step-level liveness. */
export function sessionStreamUrl(sessionId: string): string {
  const resolvedSessionId = requireRequestString(sessionId, "sessionId");
  return `${API_BASE}/research/sessions/${encodeURIComponent(resolvedSessionId)}/stream`;
}
