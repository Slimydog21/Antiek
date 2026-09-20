/**
 * Tests for ModelDecisionBar — asks #8/#10 Slice C.
 * Each test maps to one honesty rule.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";

import ModelDecisionBar from "./ModelDecisionBar";
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
      maximum_cost_usd: "0.2",
      reservation_cents: 20,
      disposition: "hold_eligible",
      ineligibility: null,
    },
    would_exceed_budget: false,
    pricing_status: "known",
    authority: "advisory_explanatory",
    notes: [
      "authority=advisory_explanatory — server re-validates at execution",
    ],
    fallback_plan: null,
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
    const select = screen.getByTestId(
      "model-decision-select",
    ) as HTMLSelectElement;
    expect(select.options.length).toBe(2);
  });

  it("renders the integer-cent reservation without coercing the exact Decimal", () => {
    const projection = baseProjection({
      chosen_projection: {
        ...baseProjection().chosen_projection!,
        maximum_cost_usd: "1E-1000",
        reservation_cents: 1,
      },
    });
    render(<ModelDecisionBar projection={projection} />);
    expect(screen.getByTestId("projection-summary").textContent).toBe(
      "$0.01 maximum reservation",
    );
    expect(screen.getByTestId("projection-summary").textContent).not.toContain(
      "$0.00",
    );
  });

  it("does not describe an ineligible projection as a free reservation", () => {
    const projection = baseProjection({
      chosen_projection: {
        ...baseProjection().chosen_projection!,
        maximum_cost_usd: "0",
        reservation_cents: 0,
        disposition: "ineligible",
        ineligibility: "unknown_price",
      },
    });
    render(<ModelDecisionBar projection={projection} />);
    expect(screen.getByTestId("projection-summary").textContent).toBe(
      "projection ineligible",
    );
    expect(screen.getByTestId("projection-summary").textContent).not.toContain(
      "$0.00",
    );
  });

  it("labels an authoritative zero-cost receipt distinctly", () => {
    const projection = baseProjection({
      chosen_projection: {
        ...baseProjection().chosen_projection!,
        maximum_cost_usd: "0",
        reservation_cents: 0,
        disposition: "zero_cost_receipt",
      },
    });
    render(<ModelDecisionBar projection={projection} />);
    expect(screen.getByTestId("projection-summary").textContent).toBe(
      "zero-cost route",
    );
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
    const select = screen.getByTestId(
      "model-decision-select",
    ) as HTMLSelectElement;
    const flashOption = Array.from(select.options).find((o) =>
      o.label.includes("gpt-flash"),
    );
    expect(flashOption?.label).toContain("pricing unknown");
    expect(flashOption?.label).not.toContain("$0.00");
  });

  it("fails non-finite candidate pricing closed as unknown", () => {
    const projection = baseProjection({
      ranked_candidates: [
        {
          ...baseProjection().ranked_candidates[0],
          estimated_usd_high: Number.POSITIVE_INFINITY,
        },
      ],
    });
    render(<ModelDecisionBar projection={projection} />);
    const option = screen
      .getByTestId("model-decision-select")
      .querySelector("option");
    expect(option?.label).toContain("pricing unknown");
    expect(option?.label).not.toContain("Infinity");
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
    expect(screen.getByTestId("exceed-verdict").textContent).toContain(
      "within the ceiling",
    );
  });

  it("shows unmeasurable when would_exceed is null", () => {
    const proj = baseProjection({ would_exceed_budget: null });
    render(<ModelDecisionBar projection={proj} />);
    expect(screen.getByTestId("exceed-verdict").textContent).toContain(
      "unmeasurable",
    );
  });

  // I4 — quality basis carried (measured vs static_prior)
  it("distinguishes measured vs static_prior in the selector labels", () => {
    render(<ModelDecisionBar projection={baseProjection()} />);
    const select = screen.getByTestId(
      "model-decision-select",
    ) as HTMLSelectElement;
    const proOption = Array.from(select.options).find((o) =>
      o.label.includes("gpt-pro"),
    );
    const flashOption = Array.from(select.options).find((o) =>
      o.label.includes("gpt-flash"),
    );
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

  it("fails an invalid non-finite budget closed instead of rendering NaN", () => {
    const proj = baseProjection({
      budget: { daily_cap_usd: Number.POSITIVE_INFINITY, spent_usd: 3.0 },
    });
    render(<ModelDecisionBar projection={proj} />);
    expect(screen.getByText("budget unknown")).toBeTruthy();
    expect(screen.queryByTestId("budget-bar-fill")).toBeNull();
  });

  // onSelect is advisory — reports the choice up, never dispatches
  it("reports the selected choice via onSelect (advisory)", () => {
    const onSelect = vi.fn();
    render(
      <ModelDecisionBar projection={baseProjection()} onSelect={onSelect} />,
    );
    const select = screen.getByTestId(
      "model-decision-select",
    ) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "1" } });
    expect(onSelect).toHaveBeenCalledWith("openai", "gpt-flash");
  });

  it("preserves provider and model identifiers containing delimiter text", () => {
    const onSelect = vi.fn();
    const projection = baseProjection({
      ranked_candidates: [
        {
          ...baseProjection().ranked_candidates[0],
          provider: "provider::region",
          model: "model::version",
        },
      ],
      chosen_provider: "provider::region",
      chosen_model: "model::version",
    });
    render(<ModelDecisionBar projection={projection} onSelect={onSelect} />);
    fireEvent.change(screen.getByTestId("model-decision-select"), {
      target: { value: "0" },
    });
    expect(onSelect).toHaveBeenCalledWith("provider::region", "model::version");
  });

  it("does not allow an ineligible candidate to be selected", () => {
    const onSelect = vi.fn();
    const projection = baseProjection({
      ranked_candidates: [
        {
          ...baseProjection().ranked_candidates[0],
          eligible: false,
        },
      ],
    });
    render(<ModelDecisionBar projection={projection} onSelect={onSelect} />);
    const select = screen.getByTestId(
      "model-decision-select",
    ) as HTMLSelectElement;
    expect(select.options[0].disabled).toBe(true);
    fireEvent.change(select, { target: { value: "0" } });
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("renders the ordered blocked fallback plan without fabricating zero cost", () => {
    render(
      <ModelDecisionBar
        projection={baseProjection({
          fallback_plan: {
            authority: "advisory_fallback_plan",
            tier: "pro",
            status: "blocked",
            maximum_chain_exposure_cents: null,
            would_exceed_budget: null,
            routes: [
              {
                fallback_index: 0,
                provider: "primary",
                model: "model-a",
                registered: true,
                projection: {
                  maximum_cost_usd: "0",
                  reservation_cents: 0,
                  disposition: "ineligible",
                  ineligibility: "unknown_pricing",
                  rate_snapshot: "unverified-v1",
                },
                hard_ceiling_eligible: false,
                execution_status: "blocked_selection_authority",
              },
              {
                fallback_index: 1,
                provider: "fallback",
                model: "model-b",
                registered: false,
                projection: {
                  maximum_cost_usd: "0",
                  reservation_cents: 0,
                  disposition: "ineligible",
                  ineligibility: "unknown_pricing",
                  rate_snapshot: "unverified-v1",
                },
                hard_ceiling_eligible: false,
                execution_status: "blocked_selection_authority",
              },
            ],
          },
        })}
      />,
    );
    expect(screen.getByTestId("fallback-plan-exposure").textContent).toBe(
      "execution blocked",
    );
    expect(screen.getByTestId("fallback-route-0").textContent).toContain(
      "Primary",
    );
    expect(screen.getByTestId("fallback-route-1").textContent).toContain(
      "Fallback 1",
    );
    expect(screen.getByTestId("fallback-route-1").textContent).toContain(
      "not registered",
    );
    expect(screen.getByTestId("fallback-plan").textContent).not.toContain(
      "$0.00",
    );
  });

  it("renders peak exposure rather than summing route reservations", () => {
    const routes = [20, 10].map((reservation_cents, fallback_index) => ({
      fallback_index,
      provider: `provider-${fallback_index}`,
      model: `model-${fallback_index}`,
      registered: true,
      projection: {
        maximum_cost_usd: String(reservation_cents / 100),
        reservation_cents,
        disposition: "hold_eligible" as const,
        ineligibility: null,
        rate_snapshot: "rates-v1",
      },
      hard_ceiling_eligible: true,
      execution_status: "executable",
    }));
    render(
      <ModelDecisionBar
        projection={baseProjection({
          fallback_plan: {
            authority: "advisory_fallback_plan",
            tier: "pro",
            status: "executable",
            maximum_chain_exposure_cents: 20,
            would_exceed_budget: false,
            routes,
          },
        })}
      />,
    );
    expect(screen.getByTestId("fallback-plan-exposure").textContent).toBe(
      "$0.20 peak · within budget",
    );
    expect(
      screen.getByTestId("fallback-plan-exposure").textContent,
    ).not.toContain("0.30");
  });

  it("surfaces an executable chain that exceeds the remaining budget", () => {
    const projection = baseProjection({
      fallback_plan: {
        authority: "advisory_fallback_plan",
        tier: "pro",
        status: "executable",
        maximum_chain_exposure_cents: 20,
        would_exceed_budget: true,
        routes: [
          {
            fallback_index: 0,
            provider: "provider",
            model: "model",
            registered: true,
            projection: {
              maximum_cost_usd: "0.2",
              reservation_cents: 20,
              disposition: "hold_eligible",
              ineligibility: null,
              rate_snapshot: "rates-v1",
            },
            hard_ceiling_eligible: true,
            execution_status: "executable",
          },
        ],
      },
    });
    render(<ModelDecisionBar projection={projection} />);
    expect(screen.getByTestId("fallback-plan-exposure").textContent).toBe(
      "$0.20 peak · over budget",
    );
  });

  it("renders loading state", () => {
    render(<ModelDecisionBar projection={null} loading />);
    expect(screen.getByTestId("model-decision-bar-loading")).toBeTruthy();
  });

  it("renders error state", () => {
    render(<ModelDecisionBar projection={null} error="boom" />);
    expect(screen.getByTestId("model-decision-bar-error").textContent).toBe(
      "boom",
    );
  });

  it("renders nothing when no projection, not loading, no error", () => {
    const { container } = render(<ModelDecisionBar projection={null} />);
    expect(container.firstChild).toBeNull();
  });
});
