/**
 * Tests for ModelDecisionTree — asks #8/#10 Slice D (the decision-tree tab, G3).
 * Each test maps to one honesty rule.
 */

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";

// vitest runs with globals:false, so @testing-library/react auto-cleanup (which
// relies on a global afterEach) never fires — without this each render accumulates
// in document.body and screen queries collide on stale DOM.
import ModelDecisionTree from "./ModelDecisionTree";
import type { ComposerModelProjection } from "../api/composerProjection";

function baseProjection(
  overrides: Partial<ComposerModelProjection> = {},
): ComposerModelProjection {
  return {
    task: "deep_research",
    recommended_tier: "pro",
    ranked_candidates: [
      {
        rank: 1,
        tier: "pro",
        provider: "openai",
        model: "gpt-pro",
        quality_score: 0.9,
        quality_basis: "measured",
        eligible: true,
        pricing_status: "known",
        estimated_usd_low: 0.1,
        estimated_usd_high: 0.2,
      },
      {
        rank: 2,
        tier: "pro",
        provider: "anthropic",
        model: "claude-pro",
        quality_score: 0.85,
        quality_basis: "measured",
        eligible: true,
        pricing_status: "known",
        estimated_usd_low: 0.12,
        estimated_usd_high: 0.22,
      },
      {
        rank: 3,
        tier: "flash",
        provider: "openai",
        model: "gpt-flash",
        quality_score: 0.5,
        quality_basis: "static_prior",
        eligible: true,
        pricing_status: "unknown",
        estimated_usd_low: null,
        estimated_usd_high: null,
      },
      {
        rank: 4,
        tier: "flash",
        provider: "byok",
        model: "deepseek-r1",
        quality_score: 0.4,
        quality_basis: "static_prior",
        eligible: false,
        pricing_status: "unknown",
        estimated_usd_low: null,
        estimated_usd_high: null,
      },
    ],
    budget: { daily_cap_usd: 10.0, spent_usd: 3.0 },
    remaining_usd: 7.0,
    chosen_provider: "openai",
    chosen_model: "gpt-pro",
    chosen_projection: {
      seam_id: "s",
      provider: "openai",
      model: "gpt-pro",
      operation: "deep_research",
      maximum_cost_usd: 0.2,
      reservation_cents: 20,
      disposition: "hold_eligible",
      ineligibility: null,
    },
    would_exceed_budget: false,
    pricing_status: "known",
    authority: "advisory_explanatory",
    notes: ["authority=advisory_explanatory — server re-validates at execution"],
    ...overrides,
  };
}

describe("ModelDecisionTree", () => {
  afterEach(cleanup);

  // Task root — anchors every candidate to the decision context.
  it("renders the task root with the task name and recommended tier", () => {
    render(<ModelDecisionTree projection={baseProjection()} />);
    const task = screen.getByTestId("decision-tree-task");
    expect(task.textContent).toContain("deep_research");
    expect(task.textContent).toContain("pro");
  });

  // Groups candidates by tier, preserving rank order within each tier.
  it("groups ranked candidates by tier", () => {
    render(<ModelDecisionTree projection={baseProjection()} />);
    expect(screen.getByTestId("decision-tree-tier-pro")).toBeTruthy();
    expect(screen.getByTestId("decision-tree-tier-flash")).toBeTruthy();
    // pro tier holds the two rank-1/2 candidates
    expect(screen.getByTestId("decision-tree-candidate-1")).toBeTruthy();
    expect(screen.getByTestId("decision-tree-candidate-2")).toBeTruthy();
    expect(screen.getByTestId("decision-tree-candidate-3")).toBeTruthy();
    expect(screen.getByTestId("decision-tree-candidate-4")).toBeTruthy();
  });

  // Measured vs static_prior are distinct visible badges.
  it("distinguishes measured vs static_prior quality basis", () => {
    render(<ModelDecisionTree projection={baseProjection()} />);
    expect(screen.getByTestId("candidate-1-quality").textContent).toContain(
      "measured",
    );
    expect(screen.getByTestId("candidate-3-quality").textContent).toContain(
      "prior",
    );
    // a prior must never carry the "measured" label
    expect(screen.getByTestId("candidate-3-quality").textContent).not.toContain(
      "measured",
    );
  });

  // Unknown pricing renders "pricing unknown", never a fabricated range or $0.00.
  it("labels unknown pricing distinctly (never $0.00)", () => {
    render(<ModelDecisionTree projection={baseProjection()} />);
    const flashPricing = screen.getByTestId("candidate-3-pricing");
    expect(flashPricing.textContent).toContain("pricing unknown");
    expect(flashPricing.textContent).not.toContain("$0.00");
  });

  // Known pricing renders the honest range.
  it("renders the cost range when pricing is known", () => {
    render(<ModelDecisionTree projection={baseProjection()} />);
    const proPricing = screen.getByTestId("candidate-1-pricing");
    expect(proPricing.textContent).toContain("$0.10");
    expect(proPricing.textContent).toContain("$0.20");
  });

  // Ineligible candidates are rendered distinctly, never collapsed with eligible.
  it("marks ineligible candidates distinctly from eligible", () => {
    render(<ModelDecisionTree projection={baseProjection()} />);
    expect(screen.getByTestId("candidate-1-eligibility").textContent).toContain(
      "eligible",
    );
    const ineligible = screen.getByTestId(
      "candidate-4-eligibility",
    ) as HTMLElement;
    expect(ineligible.textContent).toContain("ineligible");
    expect(ineligible.className).toContain("line-through");
  });

  // would_exceed_budget three states never collapse.
  it("shows the over-budget verdict when would_exceed is true", () => {
    render(<ModelDecisionTree projection={baseProjection({ would_exceed_budget: true })} />);
    expect(screen.getByTestId("decision-tree-verdict").textContent).toContain(
      "over budget",
    );
  });

  it("shows within-ceiling when would_exceed is false", () => {
    render(<ModelDecisionTree projection={baseProjection({ would_exceed_budget: false })} />);
    expect(screen.getByTestId("decision-tree-verdict").textContent).toContain(
      "within the ceiling",
    );
  });

  it("shows unmeasurable when would_exceed is null", () => {
    render(<ModelDecisionTree projection={baseProjection({ would_exceed_budget: null })} />);
    expect(screen.getByTestId("decision-tree-verdict").textContent).toContain(
      "unmeasurable",
    );
  });

  // Navigable — tier nodes collapse and expand.
  it("collapses and expands a tier on toggle", () => {
    render(<ModelDecisionTree projection={baseProjection()} />);
    const toggle = screen.getByTestId(
      "decision-tree-tier-flash-toggle",
    ) as HTMLButtonElement;
    // expanded by default — candidate present
    expect(screen.getByTestId("decision-tree-candidate-3")).toBeTruthy();
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByTestId("decision-tree-candidate-3")).toBeNull();
    // re-expand
    fireEvent.click(toggle);
    expect(screen.getByTestId("decision-tree-candidate-3")).toBeTruthy();
  });

  it("renders loading state", () => {
    render(<ModelDecisionTree projection={null} loading />);
    expect(screen.getByTestId("model-decision-tree-loading")).toBeTruthy();
  });

  it("renders error state", () => {
    render(<ModelDecisionTree projection={null} error="boom" />);
    expect(screen.getByTestId("model-decision-tree-error").textContent).toBe(
      "boom",
    );
  });

  it("renders nothing when no projection, not loading, no error", () => {
    const { container } = render(<ModelDecisionTree projection={null} />);
    expect(container.firstChild).toBeNull();
  });
});
