import { describe, expect, it, vi, afterEach, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { startInvestigation } from "../../lib/api";
import ChatInputArea from "./ChatInputArea";

const {
  fetchSettingsBudget,
  estimatePromptCost,
  fetchDecisionTreeSelection,
} = vi.hoisted(() => ({
  fetchSettingsBudget: vi.fn(async () => ({
    daily_cap_usd: 10,
    spent_usd: 2,
    remaining_usd: 8,
    spent_status: "known" as const,
    cap_env: null,
    notes: [],
  })),
  estimatePromptCost: vi.fn(async () => ({
    estimated_usd_low: 0.05,
    estimated_usd_high: 0.07,
    would_exceed_budget: false,
    pricing_known: true,
    notes: [],
    assumed_input_tokens: 20,
    assumed_output_tokens: 2500,
    tier: "pro",
    provider: null,
    model: null,
  })),
  fetchDecisionTreeSelection: vi.fn(async () => ({
    model_id: null,
    provider_id: null,
    installed: false,
    notes: [],
    source: "test",
  })),
}));

const fetchDepthTiers = vi.hoisted(() =>
  vi.fn(async () => ({
    active_depth_tier: null as string | null,
    active_preset: null,
    presets: [],
    projection_hints: null,
    view_format: "html" as const,
    settings_panel: "depth_tier_presets",
    source: "test",
    notes: [] as string[],
  })),
);

vi.mock("../../api/settings", () => ({
  fetchSettingsBudget,
  estimatePromptCost,
  fetchDecisionTreeSelection,
  fetchDepthTiers: (...args: unknown[]) => fetchDepthTiers(...args),
}));

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    startInvestigation: vi.fn(),
  };
});

const startInvestigationMock = vi.mocked(startInvestigation);

describe("ChatInputArea budget projection (bq)", () => {
  beforeEach(() => {
    fetchSettingsBudget.mockClear();
    estimatePromptCost.mockClear();
    fetchDecisionTreeSelection.mockClear();
    fetchDepthTiers.mockReset().mockResolvedValue({
      active_depth_tier: null,
      active_preset: null,
      presets: [],
      projection_hints: null,
      view_format: "html",
      settings_panel: "depth_tier_presets",
      source: "test",
      notes: [],
    });
    startInvestigationMock.mockReset().mockResolvedValue({
      investigation_id: "inv-chat-1",
    } as Awaited<ReturnType<typeof startInvestigation>>);
  });

  afterEach(() => {
    cleanup();
  });

  it("mounts ResearchLaunchBudgetPanel and retires static cost copy", async () => {
    render(
      <MemoryRouter>
        <ChatInputArea />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("chat-input-budget-mount")).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByTestId("research-launch-budget-panel")).toBeTruthy();
    });
    expect(fetchSettingsBudget).toHaveBeenCalled();
    // Static ~$0.08-$0.16 retired
    expect(document.body.textContent || "").not.toMatch(
      /~\$0\.08-\$0\.16/,
    );
    expect(document.body.textContent || "").toMatch(/live projection above/);
  });

  it("budget-panel wrestle pick submits research_tier wrestle (gr)", async () => {
    render(
      <MemoryRouter>
        <ChatInputArea />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("research-launch-tier-wrestle")).toBeTruthy();
    });
    const ta = screen.getByPlaceholderText(/what do you want to research/i);
    await userEvent.type(ta, "Follow-up wrestle across the open investigation");
    fireEvent.click(screen.getByTestId("research-launch-tier-wrestle"));
    // Ask enables once question is ≥3 chars.
    await waitFor(() => {
      expect(
        (screen.getByRole("button", { name: /ask/i }) as HTMLButtonElement)
          .disabled,
      ).toBe(false);
    });
    fireEvent.click(screen.getByRole("button", { name: /ask/i }));
    await waitFor(() => {
      expect(startInvestigationMock).toHaveBeenCalledWith(
        expect.objectContaining({
          research_tier: "wrestle",
          question: expect.stringMatching(/Follow-up wrestle/),
        }),
      );
    });
  });

  it("prefills launch tier from Settings active_depth_tier (gu)", async () => {
    fetchDepthTiers.mockResolvedValueOnce({
      active_depth_tier: "wrestle",
      active_preset: null,
      presets: [],
      projection_hints: null,
      view_format: "html",
      settings_panel: "depth_tier_presets",
      source: "test",
      notes: [],
    });
    render(
      <MemoryRouter>
        <ChatInputArea />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(fetchDepthTiers).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(
        screen.getByTestId("chat-input-budget-mount").getAttribute(
          "data-research-tier",
        ),
      ).toBe("wrestle");
    });
    expect(
      screen.getByTestId("chat-input-budget-mount").getAttribute(
        "data-depth-prefill",
      ),
    ).toBe("settings");
    const ta = screen.getByPlaceholderText(/what do you want to research/i);
    await userEvent.type(ta, "Chat follow-up inherits Settings wrestle depth");
    await waitFor(() => {
      expect(
        (screen.getByRole("button", { name: /ask/i }) as HTMLButtonElement)
          .disabled,
      ).toBe(false);
    });
    fireEvent.click(screen.getByRole("button", { name: /ask/i }));
    await waitFor(() => {
      expect(startInvestigationMock).toHaveBeenCalledWith(
        expect.objectContaining({ research_tier: "wrestle" }),
      );
    });
  });
});
