/**
 * Competition deep research gap matrix (pure client).
 *
 * Operator vision: highest quality deep research product in the world —
 * study technical decisions made by competition, record gaps, set agents up
 * for perfect execution. This pure layer only accepts caller-supplied
 * competitor decision records — never invents competitor claims or scrapes.
 */

export type DecisionArea =
  | "source_acquisition"
  | "citation_grounding"
  | "multi_agent_orchestration"
  | "budget_controls"
  | "html_native_reading"
  | "model_routing"
  | "evaluation_harness"
  | "unattended_swarm";

export type GapStatus = "ahead" | "parity" | "behind" | "unknown";

export interface CompetitorDecision {
  competitor: string;
  area: DecisionArea;
  /** Operator-authored summary of their technical choice. */
  decision_summary: string;
  /** Antiek status relative to that decision. */
  antiek_status: GapStatus;
  /** Optional actionable gap residual for future agents. */
  residual?: string;
}

export interface CompetitionGapMatrixInput {
  decisions: CompetitorDecision[];
  /** Optional focus areas; empty means all. */
  focus_areas?: DecisionArea[];
}

export interface CompetitionGapMatrix {
  decisions: CompetitorDecision[];
  behind_count: number;
  unknown_count: number;
  parity_count: number;
  ahead_count: number;
  /** Residuals for areas where Antiek is behind (caller-supplied only). */
  residuals: string[];
  /** Always false — pure matrix does not write product backlog. */
  backlog_mutated: false;
  notes: string[];
  authority: "competition_deep_research_gap_advisory";
}

const VALID_AREAS = new Set<DecisionArea>([
  "source_acquisition",
  "citation_grounding",
  "multi_agent_orchestration",
  "budget_controls",
  "html_native_reading",
  "model_routing",
  "evaluation_harness",
  "unattended_swarm",
]);

const VALID_STATUS = new Set<GapStatus>([
  "ahead",
  "parity",
  "behind",
  "unknown",
]);

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Build competition gap matrix from operator-supplied decision records.
 * Never invents competitor facts.
 */
export function buildCompetitionDeepResearchGap(
  input: CompetitionGapMatrixInput,
): CompetitionGapMatrix {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (!Array.isArray(input.decisions)) {
    throw new Error("decisions must be an array");
  }

  const notes: string[] = [
    "backlog_mutated=false — advisory gap matrix only",
    "competitor decisions are caller-supplied only (no invent / no scrape)",
  ];

  let focus: Set<DecisionArea> | null = null;
  if (input.focus_areas !== undefined && input.focus_areas !== null) {
    if (!Array.isArray(input.focus_areas)) {
      throw new Error("focus_areas must be an array when set");
    }
    focus = new Set();
    for (let i = 0; i < input.focus_areas.length; i++) {
      const a = input.focus_areas[i];
      if (!VALID_AREAS.has(a)) {
        throw new Error(`focus_areas[${i}] invalid DecisionArea`);
      }
      focus.add(a);
    }
  }

  const decisions: CompetitorDecision[] = [];
  let behind_count = 0;
  let unknown_count = 0;
  let parity_count = 0;
  let ahead_count = 0;
  const residuals: string[] = [];

  for (let i = 0; i < input.decisions.length; i++) {
    const d = input.decisions[i];
    if (!d || typeof d !== "object") {
      throw new Error(`decisions[${i}] must be an object`);
    }
    const competitor = requireNonEmpty(
      d.competitor,
      `decisions[${i}].competitor`,
    );
    if (!VALID_AREAS.has(d.area)) {
      throw new Error(`decisions[${i}].area invalid DecisionArea`);
    }
    if (focus && !focus.has(d.area)) {
      continue;
    }
    const decision_summary = requireNonEmpty(
      d.decision_summary,
      `decisions[${i}].decision_summary`,
    );
    if (!VALID_STATUS.has(d.antiek_status)) {
      throw new Error(
        `decisions[${i}].antiek_status must be ahead|parity|behind|unknown`,
      );
    }
    let residual: string | undefined;
    if (d.residual !== undefined && d.residual !== null) {
      if (typeof d.residual !== "string" || !d.residual.trim()) {
        throw new Error(
          `decisions[${i}].residual must be non-empty string when set`,
        );
      }
      residual = d.residual.trim();
    }

    const row: CompetitorDecision = {
      competitor,
      area: d.area,
      decision_summary,
      antiek_status: d.antiek_status,
      residual,
    };
    decisions.push(row);

    if (d.antiek_status === "behind") {
      behind_count += 1;
      if (residual) residuals.push(residual);
      else {
        residuals.push(
          `[${d.area}] ${competitor}: gap recorded without residual text`,
        );
      }
    } else if (d.antiek_status === "unknown") {
      unknown_count += 1;
    } else if (d.antiek_status === "parity") {
      parity_count += 1;
    } else {
      ahead_count += 1;
    }
  }

  if (input.decisions.length === 0) {
    notes.push("no decisions supplied — empty matrix (no invent competitors)");
  }
  notes.push(
    `counts ahead=${ahead_count} parity=${parity_count} behind=${behind_count} unknown=${unknown_count}`,
  );
  notes.push("backlog_mutated=false");

  return {
    decisions,
    behind_count,
    unknown_count,
    parity_count,
    ahead_count,
    residuals,
    backlog_mutated: false,
    notes,
    authority: "competition_deep_research_gap_advisory",
  };
}

export function formatCompetitionGapSummary(m: CompetitionGapMatrix): string {
  return (
    `behind=${m.behind_count} · unknown=${m.unknown_count} · ` +
    `parity=${m.parity_count} · ahead=${m.ahead_count} · backlog_mutated=false`
  );
}
