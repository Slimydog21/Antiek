/**
 * Midnight Oil multi-goal swarm helpers (residual aof).
 * Operator sets goals + duration → recommended ceiling → approve.
 * One goal per line becomes one swarm sub-question; never invent goals.
 */

/** Professional research goal templates (append-only · operator edits free). */
export const MOIL_GOAL_TEMPLATES = [
  {
    id: "map_landscape",
    label: "Map landscape",
    text: "Map the competitive landscape and technical decisions of world-class deep research products",
  },
  {
    id: "evidence_chain",
    label: "Evidence chain",
    text: "Build a citation-required evidence chain for the core claims; note open questions",
  },
  {
    id: "twin_insights",
    label: "Twin insights",
    text: "Extract recursive twin insights and questions that should seed the note-taker substrate",
  },
  {
    id: "html_deliverable",
    label: "HTML deliverable",
    text: "Produce an HTML-first written analysis deliverable suitable for merge into reading assets",
  },
  // Residual (ara): north-star workstation swarm templates (Midnight Oil).
  {
    id: "knowledge_dense_refs",
    label: "Knowledge-dense refs",
    text: "Ground claims in arXiv, Substack, and other knowledge-dense publications; hydrate offline-honest by default",
  },
  {
    id: "multi_agent_analysis",
    label: "Multi-agent analysis",
    text: "Fan out sub-questions across agents then merge into a cohesive written analysis HTML deliverable",
  },
  {
    id: "budget_wrestle",
    label: "Budget wrestle",
    text: "Wrestle with the research question under the approved price ceiling; surface budget-before-fire risks honestly",
  },
  {
    id: "reading_merge",
    label: "Reading merge",
    text: "Deliver findings as HTML that can draft-combine or merge into the parent reading asset without PDF view",
  },
] as const;

export type MoilGoalTemplateId = (typeof MOIL_GOAL_TEMPLATES)[number]["id"];

/** Split goals textarea into non-empty lines (one swarm goal per line). */
export function parseMoilGoalLines(text: string | null | undefined): string[] {
  return String(text || "")
    .split(/\r?\n/)
    .map((g) => g.trim())
    .filter(Boolean);
}

/**
 * Append a template goal if not already present (dedupe exact line).
 * Returns original text when empty template or already present.
 */
export function appendMoilGoalTemplate(
  current: string | null | undefined,
  templateText: string | null | undefined,
): string {
  const t = String(templateText || "").trim();
  if (!t) return String(current || "");
  const lines = parseMoilGoalLines(current);
  if (lines.includes(t)) return String(current || "");
  const base = String(current || "").replace(/\s+$/u, "");
  return base ? `${base}\n${t}` : t;
}

/**
 * Residual (aow): recommended fan-out depth to cover N goals (operator Match
 * action). Clamped to [1, maxFanout]; never invents goals.
 */
export function recommendedFanoutForGoals(
  goalCount: number,
  maxFanout = 12,
  minFanout = 1,
): number {
  const n = Math.floor(Number(goalCount));
  if (!Number.isFinite(n) || n <= 0) return minFanout;
  const max = Math.max(minFanout, Math.floor(Number(maxFanout)) || 12);
  return Math.min(max, Math.max(minFanout, n));
}

/**
 * Residual (aox): true when goal_count exceeds fan-out depth (coverage gap).
 * Empty goals never "exceed" (no soft-hint spam).
 */
export function goalsExceedFanout(
  goalCount: number,
  fanoutDepth: number,
): boolean {
  const goals = Math.floor(Number(goalCount));
  const fanout = Math.floor(Number(fanoutDepth));
  if (!Number.isFinite(goals) || goals <= 0) return false;
  if (!Number.isFinite(fanout) || fanout <= 0) return true;
  return goals > fanout;
}

/**
 * Residual (ara): pure Midnight Oil plan readiness before create + ceiling.
 * Operator needs goals + positive duration; fan-out is advisory (Match).
 * Never invents goals or duration — empty → not ready.
 */
export type MoilPlanReadiness = {
  goal_count: number;
  duration_minutes: number;
  fanout_depth: number;
  recommended_fanout: number;
  goals_exceed_fanout: boolean;
  goals_ready: boolean;
  duration_ready: boolean;
  plan_ready: boolean;
  summary: string;
};

export function moilPlanReadiness(opts: {
  goalsText?: string | null;
  durationMinutes?: number | null;
  fanoutDepth?: number | null;
  maxFanout?: number;
}): MoilPlanReadiness {
  const lines = parseMoilGoalLines(opts.goalsText);
  const goal_count = lines.length;
  const durationRaw = Number(opts.durationMinutes);
  const duration_minutes =
    Number.isFinite(durationRaw) && durationRaw > 0
      ? Math.floor(durationRaw)
      : 0;
  const fanoutRaw = Number(opts.fanoutDepth);
  const fanout_depth =
    Number.isFinite(fanoutRaw) && fanoutRaw > 0 ? Math.floor(fanoutRaw) : 0;
  const recommended_fanout = recommendedFanoutForGoals(
    goal_count,
    opts.maxFanout ?? 12,
  );
  const goals_exceed_fanout = goalsExceedFanout(goal_count, fanout_depth);
  const goals_ready = goal_count >= 1;
  const duration_ready = duration_minutes >= 1;
  const plan_ready = goals_ready && duration_ready;

  let summary: string;
  if (!goals_ready && !duration_ready) {
    summary = "set goals + duration for recommended ceiling";
  } else if (!goals_ready) {
    summary = "add at least one goal line";
  } else if (!duration_ready) {
    summary = "set duration minutes > 0";
  } else if (goals_exceed_fanout) {
    summary = `${goal_count} goals · ${duration_minutes}m · fan-out ${fanout_depth} under-covers (recommend ${recommended_fanout})`;
  } else {
    summary = `${goal_count} goals · ${duration_minutes}m · plan ready for ceiling`;
  }

  return {
    goal_count,
    duration_minutes,
    fanout_depth,
    recommended_fanout,
    goals_exceed_fanout,
    goals_ready,
    duration_ready,
    plan_ready,
    summary,
  };
}

/**
 * Residual (ate): pure Midnight Oil deposit HTML open readiness.
 * Float|full|Write deposit CTAs require view_format=html · non-empty body ·
 * document_id. Never invents open when PDF / empty / missing id. L4 live step
 * remains dual-gate deferred (not part of this pure gate).
 */
export type MoilDepositHtmlReadiness = {
  view_format_html: boolean;
  has_html_body: boolean;
  has_document_id: boolean;
  deposit_html_ready: boolean;
  summary: string;
  open_title: string;
};

export function moilDepositHtmlReadiness(opts: {
  view_format?: string | null;
  html?: string | null;
  document_id?: string | null;
}): MoilDepositHtmlReadiness {
  const view_format_html =
    String(opts.view_format || "")
      .trim()
      .toLowerCase() === "html";
  const has_html_body = Boolean(String(opts.html || "").trim());
  const has_document_id = Boolean(String(opts.document_id || "").trim());
  const deposit_html_ready =
    view_format_html && has_html_body && has_document_id;

  let summary: string;
  let open_title: string;
  if (deposit_html_ready) {
    summary = "html deposit ready · open float|full|Write";
    open_title =
      "Open Midnight Oil deposit as HTML reading window (autonomous swarm deliverable · twin seed path · never PDF)";
  } else if (!view_format_html) {
    summary = "view_format must be html (never PDF open)";
    open_title = "Deposit view_format must be html (never PDF open)";
  } else if (!has_html_body) {
    summary = "deposit HTML body empty";
    open_title = "Deposit HTML body empty — cannot open reading window";
  } else {
    summary = "deposit document_id missing";
    open_title = "Deposit document_id missing — cannot open reading window";
  }

  return {
    view_format_html,
    has_html_body,
    has_document_id,
    deposit_html_ready,
    summary,
    open_title,
  };
}
