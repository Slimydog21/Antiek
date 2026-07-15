import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ModelEvidenceInstrument from "./ModelEvidenceInstrument";
import type { ModelEvidenceInstrumentProps } from "./ModelEvidenceInstrument";
import type { ModelDecisionResponse } from "../../api/settings";

afterEach(cleanup);

const baseProps: Omit<
  ModelEvidenceInstrumentProps,
  "decision" | "loading" | "error"
> = {
  onCompare: vi.fn(),
  task: "deep_research",
  onTaskChange: vi.fn(),
  inputChars: 2000,
  onInputCharsChange: vi.fn(),
  outputTokens: 500,
  onOutputTokensChange: vi.fn(),
};

function twoMeasuredCohort(): ModelDecisionResponse {
  return {
    authority: "advisory",
    task: "deep_research",
    recommended_tier: "synthesis",
    benchmark_status: "measured",
    benchmark_generated_at: "2026-07-07T00:00:00Z",
    candidates: [
      {
        rank: 1,
        tier: "synthesis",
        provider: "zai",
        model: "glm-5.2",
        ready: true,
        operationally_eligible: true,
        quality_score: 0.95,
        quality_basis: "measured",
        benchmark_samples: 40,
        estimated_usd_low: 0.012,
        estimated_usd_high: 0.019,
        would_exceed_budget: false,
      },
      {
        rank: 2,
        tier: "pro",
        provider: "deepseek",
        model: "deepseek-v4-pro",
        ready: true,
        operationally_eligible: true,
        quality_score: 0.82,
        quality_basis: "measured",
        benchmark_samples: 35,
        estimated_usd_low: 0.008,
        estimated_usd_high: 0.013,
        would_exceed_budget: false,
      },
    ],
    notes: [],
  };
}

describe("ModelEvidenceInstrument", () => {
  it("renders the title and compare button", () => {
    render(
      <ModelEvidenceInstrument {...baseProps} decision={null} loading={false} error={null} />,
    );
    expect(screen.getByText("Model evidence")).toBeTruthy();
    expect(screen.getByRole("button", { name: /compare models/i })).toBeTruthy();
  });

  it("shows recommended tier when ≥2 eligible measured", () => {
    const decision = twoMeasuredCohort();
    render(
      <ModelEvidenceInstrument {...baseProps} decision={decision} loading={false} error={null} />,
    );
    expect(screen.getByText("synthesis", { selector: "strong" })).toBeTruthy();
    expect(screen.getByText(/2\/2 routes measured/i)).toBeTruthy();
  });

  it("shows no recommendation for partial cohort", () => {
    const decision: ModelDecisionResponse = {
      authority: "advisory",
      task: "writing",
      recommended_tier: null,
      benchmark_status: "measured",
      benchmark_generated_at: "2026-07-07T00:00:00Z",
      candidates: [
        {
          rank: 1,
          tier: "flash",
          provider: "zai",
          model: "glm-5.2",
          ready: true,
          operationally_eligible: true,
          quality_score: 0.91,
          quality_basis: "measured",
          benchmark_samples: 12,
          estimated_usd_low: 0.005,
          estimated_usd_high: 0.009,
          would_exceed_budget: false,
        },
        {
          rank: 2,
          tier: "pro",
          provider: "deepseek",
          model: "deepseek-v4-pro",
          ready: true,
          operationally_eligible: true,
          quality_score: null,
          quality_basis: "absent",
          benchmark_samples: null,
          estimated_usd_low: 0.008,
          estimated_usd_high: 0.013,
          would_exceed_budget: false,
        },
      ],
      notes: ["Only one measured route — no comparative cohort available."],
    };
    render(
      <ModelEvidenceInstrument {...baseProps} decision={decision} loading={false} error={null} />,
    );
    expect(screen.getByText("No measured pick")).toBeTruthy();
    expect(screen.getByText(/NOT MEASURED/)).toBeTruthy();
  });

  it("shows NOT MEASURED for no benchmark report", () => {
    const decision: ModelDecisionResponse = {
      authority: "advisory",
      task: "reading",
      recommended_tier: null,
      benchmark_status: "unavailable",
      benchmark_generated_at: null,
      candidates: [
        {
          rank: 1,
          tier: "flash",
          provider: "zai",
          model: "glm-5.2",
          ready: true,
          operationally_eligible: true,
          quality_score: null,
          quality_basis: "absent",
          benchmark_samples: null,
          estimated_usd_low: null,
          estimated_usd_high: null,
          would_exceed_budget: null,
        },
      ],
      notes: ["Antiek-bench report is not configured."],
    };
    render(
      <ModelEvidenceInstrument {...baseProps} decision={decision} loading={false} error={null} />,
    );
    expect(screen.getByText("No measured pick")).toBeTruthy();
    expect(screen.getAllByText(/NOT MEASURED/).length).toBeGreaterThanOrEqual(1);
  });

  it("shows budget unknown status", () => {
    const decision: ModelDecisionResponse = {
      authority: "advisory",
      task: "general",
      recommended_tier: null,
      benchmark_status: "unavailable",
      benchmark_generated_at: null,
      candidates: [
        {
          rank: 1,
          tier: "pro",
          provider: "zai",
          model: "glm-5.2",
          ready: true,
          operationally_eligible: false,
          quality_score: null,
          quality_basis: "absent",
          benchmark_samples: null,
          estimated_usd_low: null,
          estimated_usd_high: null,
          would_exceed_budget: null,
        },
      ],
      notes: ["Remaining budget is unknown."],
    };
    render(
      <ModelEvidenceInstrument {...baseProps} decision={decision} loading={false} error={null} />,
    );
    expect(screen.getByText("Budget unknown")).toBeTruthy();
  });

  it("shows provider unavailable status", () => {
    const decision: ModelDecisionResponse = {
      authority: "advisory",
      task: "deep_research",
      recommended_tier: null,
      benchmark_status: "unavailable",
      benchmark_generated_at: null,
      candidates: [
        {
          rank: 1,
          tier: "pro",
          provider: "zai",
          model: "glm-5.2",
          ready: false,
          operationally_eligible: false,
          quality_score: null,
          quality_basis: "absent",
          benchmark_samples: null,
          estimated_usd_low: null,
          estimated_usd_high: null,
          would_exceed_budget: null,
        },
      ],
      notes: [],
    };
    render(
      <ModelEvidenceInstrument {...baseProps} decision={decision} loading={false} error={null} />,
    );
    expect(screen.getByText("Unavailable")).toBeTruthy();
  });

  it("shows over budget status", () => {
    const decision: ModelDecisionResponse = {
      authority: "advisory",
      task: "general",
      recommended_tier: null,
      benchmark_status: "unavailable",
      benchmark_generated_at: null,
      candidates: [
        {
          rank: 1,
          tier: "pro",
          provider: "zai",
          model: "glm-5.2",
          ready: true,
          operationally_eligible: false,
          quality_score: null,
          quality_basis: "absent",
          benchmark_samples: null,
          estimated_usd_low: 0.05,
          estimated_usd_high: 0.08,
          would_exceed_budget: true,
        },
      ],
      notes: [],
    };
    render(
      <ModelEvidenceInstrument {...baseProps} decision={decision} loading={false} error={null} />,
    );
    expect(screen.getByText("Over budget")).toBeTruthy();
  });

  it("shows measured pick disc for winning candidate", () => {
    const decision = twoMeasuredCohort();
    render(
      <ModelEvidenceInstrument {...baseProps} decision={decision} loading={false} error={null} />,
    );
    const pick = screen.getByRole("img", { name: "Measured pick" });
    expect(pick).toBeTruthy();
    expect(pick.classList.contains("bg-amber-500")).toBe(true);
  });

  it("shows empty disc for non-winning candidate", () => {
    const decision = twoMeasuredCohort();
    render(
      <ModelEvidenceInstrument {...baseProps} decision={decision} loading={false} error={null} />,
    );
    const noPick = screen.getByRole("img", { name: "No measured pick" });
    expect(noPick).toBeTruthy();
  });

  it("displays benchmark provenance stamp", () => {
    const decision = twoMeasuredCohort();
    render(
      <ModelEvidenceInstrument {...baseProps} decision={decision} loading={false} error={null} />,
    );
    expect(screen.getAllByText(/BENCH/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/W28/).length).toBeGreaterThanOrEqual(1);
  });

  it("displays NOT MEASURED stamp when no benchmark", () => {
    const decision: ModelDecisionResponse = {
      authority: "advisory",
      task: "reading",
      recommended_tier: null,
      benchmark_status: "unavailable",
      benchmark_generated_at: null,
      candidates: [],
      notes: [],
    };
    render(
      <ModelEvidenceInstrument {...baseProps} decision={decision} loading={false} error={null} />,
    );
    expect(screen.getByText(/NOT MEASURED/)).toBeTruthy();
  });

  it("renders error alert", () => {
    render(
      <ModelEvidenceInstrument
        {...baseProps}
        decision={null}
        loading={false}
        error="Connection failed"
      />,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("Connection failed")).toBeTruthy();
  });

  it("disables compare button while loading", () => {
    render(
      <ModelEvidenceInstrument {...baseProps} decision={null} loading={true} error={null} />,
    );
    const btn = screen.getByRole("button", { name: /comparing/i });
    expect(btn).toHaveProperty("disabled", true);
  });

  it("calls onCompare when compare button clicked", async () => {
    const onCompare = vi.fn();
    const user = userEvent.setup();
    render(
      <ModelEvidenceInstrument
        {...baseProps}
        onCompare={onCompare}
        decision={null}
        loading={false}
        error={null}
      />,
    );
    await user.click(screen.getByRole("button", { name: /compare models/i }));
    expect(onCompare).toHaveBeenCalledTimes(1);
  });
});
