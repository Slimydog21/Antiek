/**
 * Competition gap residual → execution package compose (pure).
 *
 * Operator vision: after studying competition and writing residual plans,
 * package one residual for perfect agent execution (spec pointers, acceptance
 * gates, free-file doctrine) without live product mutation.
 *
 * execution_authorized always false.
 * backlog_mutated always false.
 * store_mutated always false.
 */

import type { ResidualPlanItem, ResidualPriority } from "./competitionGapResidualPlan";
import type { DecisionArea, GapStatus } from "./competitionDeepResearchGap";

export type AcceptanceGate =
  | "pure_module"
  | "red_proof_tests_x2"
  | "heterogeneous_critic"
  | "honesty_flags"
  | "no_app_py_race"
  | "registerable_routes_or_free_file"
  | "operator_merge_only";

export interface CompetitionGapResidualExecuteInput {
  residual: ResidualPlanItem;
  operator_ack: boolean;
  /** Optional extra acceptance gates beyond defaults. */
  extra_gates?: AcceptanceGate[] | null;
  /** Optional free-file paths future agents should own. */
  proposed_owned_files?: string[] | null;
}

export interface CompetitionGapResidualExecuteCompose {
  residual_id: string;
  area: DecisionArea;
  competitor: string;
  priority: ResidualPriority;
  antiek_status: GapStatus;
  residual_text: string;
  execution_hint: string;
  acceptance_gates: AcceptanceGate[];
  proposed_owned_files: string[];
  /** True when operator_ack and residual_id non-empty. Still not authorized. */
  package_ready: boolean;
  /** Always false — pure layer never authorizes product execution. */
  execution_authorized: false;
  /** Always false — plan package does not mutate backlog. */
  backlog_mutated: false;
  /** Always false — no store mutation. */
  store_mutated: false;
  notes: string[];
  authority: "competition_gap_residual_execute_compose_advisory";
}

const DEFAULT_GATES: AcceptanceGate[] = [
  "pure_module",
  "red_proof_tests_x2",
  "heterogeneous_critic",
  "honesty_flags",
  "no_app_py_race",
  "registerable_routes_or_free_file",
  "operator_merge_only",
];

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function requireResidual(r: unknown): ResidualPlanItem {
  if (!r || typeof r !== "object") {
    throw new Error("residual must be an object");
  }
  const residual = r as ResidualPlanItem;
  requireNonEmpty(residual.residual_id, "residual.residual_id");
  requireNonEmpty(residual.competitor, "residual.competitor");
  requireNonEmpty(residual.residual_text, "residual.residual_text");
  requireNonEmpty(residual.execution_hint, "residual.execution_hint");
  if (
    residual.priority !== "P0" &&
    residual.priority !== "P1" &&
    residual.priority !== "P2" &&
    residual.priority !== "P3"
  ) {
    throw new Error("residual.priority must be P0|P1|P2|P3");
  }
  if (
    residual.antiek_status !== "behind" &&
    residual.antiek_status !== "unknown" &&
    residual.antiek_status !== "parity" &&
    residual.antiek_status !== "ahead"
  ) {
    throw new Error("residual.antiek_status invalid");
  }
  return residual;
}

/**
 * Package one competition residual for future agent execution.
 * Never authorizes live product changes.
 */
export function composeCompetitionGapResidualExecute(
  input: CompetitionGapResidualExecuteInput,
): CompetitionGapResidualExecuteCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const residual = requireResidual(input.residual);

  const notes: string[] = [
    "execution_authorized=false — package is advisory for future agents",
    "backlog_mutated=false — residual plan package only",
    "store_mutated=false",
    "free-file doctrine: pure modules + registerable routes; no app.py race",
  ];

  const gates = new Set<AcceptanceGate>(DEFAULT_GATES);
  if (input.extra_gates != null) {
    if (!Array.isArray(input.extra_gates)) {
      throw new Error("extra_gates must be an array when set");
    }
    for (let i = 0; i < input.extra_gates.length; i++) {
      const g = input.extra_gates[i];
      if (!DEFAULT_GATES.includes(g as AcceptanceGate) && typeof g !== "string") {
        throw new Error(`extra_gates[${i}] invalid`);
      }
      // Only allow known gate strings
      if (
        g !== "pure_module" &&
        g !== "red_proof_tests_x2" &&
        g !== "heterogeneous_critic" &&
        g !== "honesty_flags" &&
        g !== "no_app_py_race" &&
        g !== "registerable_routes_or_free_file" &&
        g !== "operator_merge_only"
      ) {
        throw new Error(`extra_gates[${i}] must be a known AcceptanceGate`);
      }
      gates.add(g);
    }
  }
  const acceptance_gates = Array.from(gates);

  const proposed_owned_files: string[] = [];
  if (input.proposed_owned_files != null) {
    if (!Array.isArray(input.proposed_owned_files)) {
      throw new Error("proposed_owned_files must be an array when set");
    }
    const seen = new Set<string>();
    for (let i = 0; i < input.proposed_owned_files.length; i++) {
      const f = requireNonEmpty(
        input.proposed_owned_files[i],
        `proposed_owned_files[${i}]`,
      );
      if (f.includes("app.py") || f.endsWith("/app.py")) {
        throw new Error(
          "proposed_owned_files must not include app.py (ready-html ownership)",
        );
      }
      if (seen.has(f)) {
        throw new Error(`duplicate proposed_owned_files: ${f}`);
      }
      seen.add(f);
      proposed_owned_files.push(f);
    }
  }

  notes.push(
    `residual_id=${residual.residual_id} · priority=${residual.priority} · area=${residual.area}`,
  );
  notes.push(`execution_hint=${residual.execution_hint}`);
  notes.push(`acceptance_gates=${acceptance_gates.length}`);

  const package_ready = input.operator_ack === true;
  if (!package_ready) {
    notes.push("package_ready=false — operator_ack required");
  } else {
    notes.push(
      "package_ready=true — future agents may claim free residual under free-file doctrine",
    );
  }

  notes.push("execution_authorized=false");
  notes.push("backlog_mutated=false");
  notes.push("store_mutated=false");

  return {
    residual_id: residual.residual_id,
    area: residual.area,
    competitor: residual.competitor,
    priority: residual.priority,
    antiek_status: residual.antiek_status,
    residual_text: residual.residual_text,
    execution_hint: residual.execution_hint,
    acceptance_gates,
    proposed_owned_files,
    package_ready,
    execution_authorized: false,
    backlog_mutated: false,
    store_mutated: false,
    notes,
    authority: "competition_gap_residual_execute_compose_advisory",
  };
}

export function formatCompetitionGapResidualExecuteSummary(
  c: CompetitionGapResidualExecuteCompose,
): string {
  return (
    `package_ready=${c.package_ready} · ${c.residual_id} · ${c.priority} · ` +
    `execution_authorized=false · backlog_mutated=false`
  );
}
