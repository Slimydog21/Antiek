import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ResearchRunCeilingApproval } from "./ResearchRunCeilingApproval";

const { estimatePromptCost } = vi.hoisted(() => ({
  estimatePromptCost: vi.fn(),
}));

vi.mock("../../api/settings", () => ({
  fetchSettingsBudget: vi.fn(async () => ({
    daily_cap_usd: 10,
    spent_usd: 0,
    remaining_usd: 10,
    spent_status: "known",
    cap_env: null,
    notes: [],
  })),
  fetchDecisionTreeSelection: vi.fn(async () => ({
    model_id: null,
    provider_id: null,
    installed: false,
    source: "test",
    notes: [],
  })),
  fetchAntiekBenchLeaderboard: vi.fn(async () => ({ models: [] })),
  installDecisionTreeSelection: vi.fn(),
  estimatePromptCost,
}));

describe("ResearchRunCeilingApproval", () => {
  beforeEach(() => estimatePromptCost.mockReset());
  afterEach(cleanup);

  it("cannot approve unknown pricing and emits no authority", async () => {
    estimatePromptCost.mockResolvedValue({
      estimated_usd_low: null,
      estimated_usd_high: null,
      would_exceed_budget: null,
      pricing_known: false,
      notes: ["pricing unavailable"],
      assumed_input_tokens: 10,
      assumed_output_tokens: 2500,
      tier: "pro",
      provider: "zai",
      model: "glm-5.2",
    });
    const changed = vi.fn();
    render(
      <ResearchRunCeilingApproval
        promptText="A real research question"
        researchTier="deep"
        onAuthorizationChange={changed}
      />,
    );
    fireEvent.change(screen.getByLabelText("Initial-run hard ceiling (USD)"), {
      target: { value: "2.00" },
    });
    const checkbox = screen.getByLabelText("Approve initial-run hard ceiling") as HTMLInputElement;
    await waitFor(() => expect(checkbox.disabled).toBe(true));
    expect(changed.mock.calls.at(-1)?.[0]).toMatchObject({ approved: false, ceilingUsd: 2 });
  });

  it("requires an exact entered ceiling and explicit confirmation", async () => {
    estimatePromptCost.mockResolvedValue({
      estimated_usd_low: 0.01,
      estimated_usd_high: 0.02,
      would_exceed_budget: false,
      pricing_known: true,
      notes: [],
      assumed_input_tokens: 10,
      assumed_output_tokens: 2500,
      tier: "pro",
      provider: "provider",
      model: "model",
      pricing_fingerprint: "price-v1",
    });
    const changed = vi.fn();
    const view = render(
      <ResearchRunCeilingApproval
        promptText="A real research question"
        researchTier="deep"
        onAuthorizationChange={changed}
      />,
    );
    const input = screen.getByLabelText("Initial-run hard ceiling (USD)");
    fireEvent.change(input, { target: { value: "1.75" } });
    const checkbox = screen.getByLabelText("Approve initial-run hard ceiling") as HTMLInputElement;
    await waitFor(() => expect(checkbox.disabled).toBe(false));
    fireEvent.click(checkbox);
    await waitFor(() =>
      expect(changed.mock.calls.at(-1)?.[0]).toMatchObject({
        approved: true,
        ceilingUsd: 1.75,
      }),
    );
    view.rerender(
      <ResearchRunCeilingApproval
        promptText="A changed research question"
        researchTier="deep"
        onAuthorizationChange={changed}
      />,
    );
    expect(checkbox.checked).toBe(false);
    expect(changed.mock.calls.at(-1)?.[0]).toMatchObject({ approved: false });
    fireEvent.change(input, { target: { value: "1.76" } });
    expect(checkbox.checked).toBe(false);
    expect(changed.mock.calls.at(-1)?.[0]).toMatchObject({ approved: false });
  });

  it("invalidates confirmation when the pricing generation changes", async () => {
    estimatePromptCost
      .mockResolvedValueOnce({
        estimated_usd_low: 0.01,
        estimated_usd_high: 0.02,
        would_exceed_budget: false,
        pricing_known: true,
        pricing_fingerprint: "price-v1",
        notes: [],
        assumed_input_tokens: 10,
        assumed_output_tokens: 2500,
        tier: "pro",
        provider: "provider",
        model: "model",
      })
      .mockResolvedValueOnce({
        estimated_usd_low: 0.02,
        estimated_usd_high: 0.03,
        would_exceed_budget: false,
        pricing_known: true,
        pricing_fingerprint: "price-v2",
        notes: [],
        assumed_input_tokens: 10,
        assumed_output_tokens: 2500,
        tier: "pro",
        provider: "provider",
        model: "model",
      });
    const changed = vi.fn();
    const view = render(
      <ResearchRunCeilingApproval
        promptText="First command"
        researchTier="deep"
        onAuthorizationChange={changed}
      />,
    );
    fireEvent.change(screen.getByLabelText("Initial-run hard ceiling (USD)"), {
      target: { value: "1.00" },
    });
    const checkbox = screen.getByLabelText("Approve initial-run hard ceiling") as HTMLInputElement;
    await waitFor(() => expect(checkbox.disabled).toBe(false));
    fireEvent.click(checkbox);
    await waitFor(() => expect(changed.mock.calls.at(-1)?.[0].approved).toBe(true));

    view.rerender(
      <ResearchRunCeilingApproval
        promptText="Second command"
        researchTier="deep"
        onAuthorizationChange={changed}
      />,
    );
    await waitFor(() => expect(checkbox.disabled).toBe(false));
    expect(checkbox.checked).toBe(false);
    expect(changed.mock.calls.at(-1)?.[0].approved).toBe(false);
  });
});
