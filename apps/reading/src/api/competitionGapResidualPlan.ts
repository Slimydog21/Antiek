/**
 * Competition gap → residual execution plan (pure).
 *
 * Operator vision: study competition technical decisions, then set future
 * agents up for perfect execution with precision. This module turns an
 * advisory gap matrix (caller-supplied behind/unknown rows + residuals)
 * into an ordered residual plan. Never mutates product backlog.
 */

import type {
  CompetitorDecision,
  DecisionArea,
  GapStatus,
} from "./competitionDeepResearchGap";

export type ResidualPriority = "P0" | "P1" | "P2" | "P3";

export interface ResidualPlanItem {
  residual_id: string;
  area: DecisionArea;
  competitor: string;
  residual_text: string;
  antiek_status: GapStatus;
  priority: ResidualPriority;
  /** Suggested free-file / pure-module execution hint for future agents. */
  execution_hint: string;
}

export interface CompetitionGapResidualPlan {
  items: ResidualPlanItem[];
  item_count: number;
  p0_count: number;
  behind_planned: number;
  unknown_planned: number;
  /** Always false — plan is advisory only. */
  backlog_mutated: false;
  notes: string[];
  authority: "competition_gap_residual_plan_advisory";
}

const PRIORITY_BY_STATUS: Record<GapStatus, ResidualPriority | null> = {
  behind: "P0",
  unknown: "P1",
  parity: null,
  ahead: null,
};

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function hintFor(area: DecisionArea, status: GapStatus): string {
  if (status === "unknown") {
    return `Investigate operator-supplied evidence for ${area}; do not invent competitor claims`;
  }
  switch (area) {
    case "source_acquisition":
      return "Ship pure source pack preflight (arxiv/substack registry) without live scrape";
    case "citation_grounding":
      return "Wire citation spans into DR quality floor pure modules";
    case "multi_agent_orchestration":
      return "Extend collective floating cohesive prompt + MO swarm readiness free modules";
    case "budget_controls":
      return "Harden model decision + prompt projection honesty (would_exceed null)";
    case "html_native_reading":
      return "Enforce html-native view authority; PDF never primary";
    case "model_routing":
      return "Keep NotDiamond advisory/shadow only; decision tree remains operator authority";
    case "evaluation_harness":
      return "Extend Antiek-bench recursive rewrite + usage-learn pure surfaces";
    case "unattended_swarm":
      return "Compose MO brief + readiness + price ceiling; live_execution_authorized=false";
    default:
      return "Free pure residual: pure module + registerable routes + red-proof tests";
  }
}

/**
 * Build ordered residual plan from gap decisions.
 * Only behind + unknown rows produce plan items; never invents residual text
 * when residual is missing (uses status-tagged fallback string).
 */
export function buildCompetitionGapResidualPlan(input: {
  decisions: CompetitorDecision[];
  /** Optional max items (must be positive finite when set). */
  max_items?: number | null;
}): CompetitionGapResidualPlan {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (!Array.isArray(input.decisions)) {
    throw new Error("decisions must be an array");
  }

  let maxItems: number | null = null;
  if (input.max_items !== undefined && input.max_items !== null) {
    if (
      typeof input.max_items !== "number" ||
      !Number.isFinite(input.max_items) ||
      input.max_items <= 0
    ) {
      throw new Error("max_items must be a positive finite number when set");
    }
    maxItems = Math.floor(input.max_items);
  }

  const notes: string[] = [
    "backlog_mutated=false — residual plan is advisory only",
    "plan items derived from caller-supplied decisions only (no invent competitors)",
  ];

  const items: ResidualPlanItem[] = [];
  let behind_planned = 0;
  let unknown_planned = 0;
  let seq = 0;

  // First pass: behind (P0), then unknown (P1) — stable order by input index
  const phases: GapStatus[] = ["behind", "unknown"];
  for (const phase of phases) {
    for (let i = 0; i < input.decisions.length; i++) {
      const d = input.decisions[i];
      if (!d || typeof d !== "object") {
        throw new Error(`decisions[${i}] must be an object`);
      }
      if (d.antiek_status !== phase) continue;

      const competitor = requireNonEmpty(
        d.competitor,
        `decisions[${i}].competitor`,
      );
      const area = d.area;
      if (typeof area !== "string" || !area.trim()) {
        throw new Error(`decisions[${i}].area must be a non-empty string`);
      }
      let residual_text: string;
      if (d.residual == null) {
        residual_text = `[${area}] ${competitor}: gap recorded without residual text`;
        notes.push(
          `decisions[${i}] missing residual — synthetic residual_text only (not backlog write)`,
        );
      } else {
        residual_text = requireNonEmpty(
          d.residual,
          `decisions[${i}].residual`,
        );
      }

      const priority = PRIORITY_BY_STATUS[phase];
      if (priority == null) continue;

      if (maxItems !== null && items.length >= maxItems) {
        notes.push(`max_items=${maxItems} reached — remaining rows not planned`);
        break;
      }

      seq += 1;
      items.push({
        residual_id: `cgrp_${String(seq).padStart(3, "0")}`,
        area: area as DecisionArea,
        competitor,
        residual_text,
        antiek_status: phase,
        priority,
        execution_hint: hintFor(area as DecisionArea, phase),
      });
      if (phase === "behind") behind_planned += 1;
      else unknown_planned += 1;
    }
    if (maxItems !== null && items.length >= maxItems) break;
  }

  if (items.length === 0) {
    notes.push("no behind/unknown residuals — empty plan (no invent items)");
  }
  notes.push(
    `planned behind=${behind_planned} unknown=${unknown_planned} total=${items.length}`,
  );
  notes.push("backlog_mutated=false");

  return {
    items,
    item_count: items.length,
    p0_count: behind_planned,
    behind_planned,
    unknown_planned,
    backlog_mutated: false,
    notes,
    authority: "competition_gap_residual_plan_advisory",
  };
}

export function formatCompetitionGapResidualPlanSummary(
  plan: CompetitionGapResidualPlan,
): string {
  return (
    `residual plan · items=${plan.item_count} · P0=${plan.p0_count} · ` +
    `unknown=${plan.unknown_planned} · backlog_mutated=false`
  );
}
