import { describe, expect, it } from "vitest";

import {
  formatBudgetDescription,
  formatBudgetLabel,
  formatComplianceLabel,
  formatSensitivityLabel,
  formatSystemControl,
  formatTrainingCriterion,
  sensitivityForBudget,
} from "./trustCopy";

describe("trustCopy", () => {
  it("translates production trust-center keys into user-facing labels", () => {
    expect(formatBudgetLabel("skill_invocation_frequency")).toBe(
      "Skill Use Frequency",
    );
    expect(formatBudgetLabel("source_tier_preference_signals")).toBe(
      "Source Preference Signals",
    );
    expect(formatBudgetDescription("source_tier_preference_signals")).toContain(
      "opt into",
    );
    expect(formatTrainingCriterion("sft_readiness")).toBe(
      "Training data quality review",
    );
  });

  it("translates production controls and compliance strings", () => {
    expect(formatSystemControl("access logging (append-only)")).toBe(
      "Append-only access logs",
    );
    expect(formatSystemControl("retrieval-time policy_tag gating (§9.0)")).toBe(
      "Access checks run before retrieved content is shown",
    );
    expect(formatComplianceLabel("CCPA notice + opt-out")).toBe(
      "CCPA notice and opt-out",
    );
    expect(
      formatComplianceLabel(
        "SOC 2 Type II — deferred (not required for consumer Phase 1)",
      ),
    ).toBe("SOC 2 Type II is not required for the consumer preview");
  });

  it("uses registry sensitivity semantics for default categories", () => {
    expect(sensitivityForBudget("skill_invocation_frequency", 2)).toBe("low");
    expect(sensitivityForBudget("source_tier_preference_signals", 1)).toBe(
      "medium",
    );
    expect(sensitivityForBudget("query_content_telemetry", 0)).toBe(
      "forbidden",
    );
    expect(formatSensitivityLabel("forbidden")).toBe("Not collected");
  });

  it("sanitizes unknown backend phrases instead of echoing raw handles", () => {
    expect(formatSystemControl("future_policy_tag_control (§7.4)")).toBe(
      "Future policy tag control",
    );
    expect(formatComplianceLabel("future_framework (§3.1)")).toBe(
      "Future framework",
    );
  });
});
