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
