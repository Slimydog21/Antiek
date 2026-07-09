import { describe, expect, it, vi, afterEach, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import ChatInputArea from "./ChatInputArea";

const startInvestigation = vi.fn();
const hydratePublicationRefs = vi.fn();
const parsePublicationRefs = vi.fn();
const questionWithPublicationRefs = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    startInvestigation: (...args: unknown[]) => startInvestigation(...args),
  };
});

vi.mock("./publicationRefs", () => ({
  parsePublicationRefs: (...args: unknown[]) => parsePublicationRefs(...args),
  hydratePublicationRefs: (...args: unknown[]) => hydratePublicationRefs(...args),
  questionWithPublicationRefs: (...args: unknown[]) =>
    questionWithPublicationRefs(...args),
}));

vi.mock("../../api/settings", () => ({
  fetchSettingsBudget: vi.fn(async () => ({
    daily_cap_usd: 10,
    spent_usd: 1,
    remaining_usd: 9,
    spent_status: "known",
    cap_env: null,
    notes: [],
  })),
  estimatePromptCost: vi.fn(async () => ({
    estimated_usd_low: 0.01,
    estimated_usd_high: 0.02,
    would_exceed_budget: false,
    pricing_known: true,
    notes: [],
    assumed_input_tokens: 10,
    assumed_output_tokens: 100,
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

vi.mock("../../lib/analytics", () => ({
  track: vi.fn(),
  trackException: vi.fn(),
}));

describe("ChatInputArea publication refs (ct)", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    startInvestigation.mockReset();
    hydratePublicationRefs.mockReset();
    parsePublicationRefs.mockReset();
    questionWithPublicationRefs.mockReset();
    startInvestigation.mockResolvedValue({
      investigation_id: "inv_chat_1",
      status: "in_progress",
      start_event_id: "ev_1",
    });
  });

  it("mounts publication refs panel", () => {
    render(
      <MemoryRouter>
        <ChatInputArea />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("chat-input-publication-refs")).toBeTruthy();
    expect(
      screen
        .getByTestId("chat-input-publication-refs")
        .getAttribute("data-view-format"),
    ).toBe("html");
    expect(screen.getByTestId("chat-publication-refs-input")).toBeTruthy();
  });

  it("hydrates refs and grounds question on Ask", async () => {
    parsePublicationRefs.mockReturnValue(["arxiv:1706.03762"]);
    hydratePublicationRefs.mockResolvedValue({
      ok: [
        {
          asset_id: "pub_1",
          title: "Attention",
          view_format: "html",
        },
      ],
      failed: [],
      view_format: "html",
    });
    questionWithPublicationRefs.mockReturnValue(
      "What is attention?\n\nPublication references to ground this research:\n- arxiv:1706.03762",
    );

    render(
      <MemoryRouter>
        <ChatInputArea />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByPlaceholderText(/What do you want to research/), {
      target: { value: "What is attention?" },
    });
    fireEvent.change(screen.getByTestId("chat-publication-refs-input"), {
      target: { value: "arxiv:1706.03762" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Ask$/i }));

    await waitFor(() => {
      expect(hydratePublicationRefs).toHaveBeenCalledWith(["arxiv:1706.03762"]);
    });
    await waitFor(() => {
      expect(startInvestigation).toHaveBeenCalled();
    });
    const call = startInvestigation.mock.calls.at(-1)?.[0] as {
      question: string;
    };
    expect(call.question).toMatch(/Publication references/);
    expect(call.question).toMatch(/arxiv:1706\.03762/);
    await waitFor(() => {
      expect(screen.getByTestId("chat-publication-refs-status").textContent).toMatch(
        /Hydrated 1/,
      );
    });
  });
});
