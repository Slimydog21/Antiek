import { describe, expect, it } from "vitest";
import {
  composeCompetitionGapResidualExecute,
  formatCompetitionGapResidualExecuteSummary,
} from "./competitionGapResidualExecuteCompose";
import type { ResidualPlanItem } from "./competitionGapResidualPlan";

const residual: ResidualPlanItem = {
  residual_id: "res-citation-1",
  area: "citation_grounding",
  competitor: "perplexity",
  residual_text: "Span-level citations in DR output",
  antiek_status: "behind",
  priority: "P0",
  execution_hint: "Wire citation spans into DR quality floor pure modules",
};

describe("composeCompetitionGapResidualExecute", () => {
  it("packages residual without authorizing execution", () => {
    const c = composeCompetitionGapResidualExecute({
      residual,
      operator_ack: true,
      proposed_owned_files: [
        "apps/reading/src/api/deepResearchCitationSpans.ts",
      ],
    });
    expect(c.package_ready).toBe(true);
    expect(c.execution_authorized).toBe(false);
    expect(c.backlog_mutated).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.acceptance_gates).toContain("pure_module");
    expect(c.acceptance_gates).toContain("no_app_py_race");
    expect(c.authority).toBe(
      "competition_gap_residual_execute_compose_advisory",
    );
    expect(formatCompetitionGapResidualExecuteSummary(c)).toMatch(
      /execution_authorized=false/,
    );
  });

  it("not ready without ack", () => {
    const c = composeCompetitionGapResidualExecute({
      residual,
      operator_ack: false,
    });
    expect(c.package_ready).toBe(false);
    expect(c.execution_authorized).toBe(false);
  });

  it("rejects app.py ownership proposals", () => {
    expect(() =>
      composeCompetitionGapResidualExecute({
        residual,
        operator_ack: true,
        proposed_owned_files: ["interfaces/research/api/app.py"],
      }),
    ).toThrow(/app\.py/);
  });
});
