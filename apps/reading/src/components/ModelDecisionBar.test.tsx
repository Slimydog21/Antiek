/**
 * Tests for ModelDecisionBar — asks #8/#10 Slice C.
 * Each test maps to one honesty rule.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";

import ModelDecisionBar from "./ModelDecisionBar";
import type { ComposerModelProjection } from "../api/composerProjection";

function baseProjection(overrides: Partial<ComposerModelProjection> = {}): ComposerModelProjection {
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

describe("ModelDecisionBar", () => {
  // vitest runs with globals:false, so @testing-library/react auto-cleanup
  // (which relies on a global afterEach) never fires. Without this, each
  // render accumulates in document.body and screen.getByTestId collides on
  // stale DOM from prior tests (getMultipleElementsFoundError).
  afterEach(cleanup);

  it("renders the model selector with ranked candidates", () => {
    render(<ModelDecisionBar projection={baseProjection()} />);
    const select = screen.getByTestId("model-decision-select") as HTMLSelectElement;
    expect(select.options.length).toBe(2);
  });

  // I2 — unknown pricing renders "unknown", never "$0.00"
  it("labels unknown pricing distinctly (never $0.00)", () => {
    const proj = baseProjection({
      chosen_model: "gpt-flash",
      chosen_provider: "openai",
      pricing_status: "unknown",
    });
    render(<ModelDecisionBar projection={proj} />);
    expect(screen.getByTestId("pricing-unknown")).toBeTruthy();
    // The flash candidate's pricing label must not be "$0.00"
    const select = screen.getByTestId("model-decision-select") as HTMLSelectElement;
    const flashOption = Array.from(select.options).find((o) =>
      o.value.includes("gpt-flash"),
    );
    expect(flashOption?.label).toContain("pricing unknown");
    expect(flashOption?.label).not.toContain("$0.00");
  });

  // I3 — would_exceed three distinct states never collapse
  it("shows the over-budget verdict when would_exceed is true", () => {
    const proj = baseProjection({ would_exceed_budget: true });
    render(<ModelDecisionBar projection={proj} />);
    const verdict = screen.getByTestId("exceed-verdict");
    expect(verdict.textContent).toContain("over budget");
  });

  it("shows within-ceiling when would_exceed is false", () => {
    const proj = baseProjection({ would_exceed_budget: false });
    render(<ModelDecisionBar projection={proj} />);
    expect(screen.getByTestId("exceed-verdict").textContent).toContain("within the ceiling");
  });

  it("shows unmeasurable when would_exceed is null", () => {
    const proj = baseProjection({ would_exceed_budget: null });
    render(<ModelDecisionBar projection={proj} />);
    expect(screen.getByTestId("exceed-verdict").textContent).toContain("unmeasurable");
  });

  // I4 — quality basis carried (measured vs static_prior)
  it("distinguishes measured vs static_prior in the selector labels", () => {
    render(<ModelDecisionBar projection={baseProjection()} />);
    const select = screen.getByTestId("model-decision-select") as HTMLSelectElement;
    const proOption = Array.from(select.options).find((o) => o.value.includes("gpt-pro"));
    const flashOption = Array.from(select.options).find((o) => o.value.includes("gpt-flash"));
    expect(proOption?.label).toContain("measured");
    expect(flashOption?.label).toContain("prior");
  });

  // budget bar honesty — null cap or spent → "budget unknown", never fabricated 0%
  it("renders 'budget unknown' when cap is null", () => {
    const proj = baseProjection({
      budget: { daily_cap_usd: null, spent_usd: 3.0 },
      remaining_usd: null,
    });
    render(<ModelDecisionBar projection={proj} />);
    expect(screen.getByText("budget unknown")).toBeTruthy();
    expect(screen.queryByTestId("budget-bar-fill")).toBeNull();
  });

  it("renders the budget bar fill when cap and spent are known", () => {
    render(<ModelDecisionBar projection={baseProjection()} />);
    const fill = screen.getByTestId("budget-bar-fill") as HTMLDivElement;
    // jsdom/browsers normalize the CSS percentage (30.0% -> 30%); assert the
    // normalized rendered value, not the pre-normalization toFixed(1) string.
    expect(fill.style.width).toBe("30%"); // 3.0 / 10.0
  });

  it("clamps the fill to 100% when over cap", () => {
    const proj = baseProjection({
      budget: { daily_cap_usd: 10.0, spent_usd: 12.0 },
    });
    render(<ModelDecisionBar projection={proj} />);
    const fill = screen.getByTestId("budget-bar-fill") as HTMLDivElement;
    // 120% unclamped would render as "120%"; "100%" proves the clamp fired.
    expect(fill.style.width).toBe("100%");
  });

  // onSelect is advisory — reports the choice up, never dispatches
  it("reports the selected choice via onSelect (advisory)", () => {
    const onSelect = vi.fn();
    render(<ModelDecisionBar projection={baseProjection()} onSelect={onSelect} />);
    const select = screen.getByTestId("model-decision-select") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "openai::gpt-flash" } });
    expect(onSelect).toHaveBeenCalledWith("openai", "gpt-flash");
  });

  it("renders loading state", () => {
    render(<ModelDecisionBar projection={null} loading />);
    expect(screen.getByTestId("model-decision-bar-loading")).toBeTruthy();
  });

  it("renders error state", () => {
    render(<ModelDecisionBar projection={null} error="boom" />);
    expect(screen.getByTestId("model-decision-bar-error").textContent).toBe("boom");
  });

  it("renders nothing when no projection, not loading, no error", () => {
    const { container } = render(<ModelDecisionBar projection={null} />);
    expect(container.firstChild).toBeNull();
  });
});
