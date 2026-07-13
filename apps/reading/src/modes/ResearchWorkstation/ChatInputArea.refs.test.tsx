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
  fetchDepthTiers: vi.fn(async () => ({
    active_depth_tier: null,
    active_preset: null,
    presets: [],
    projection_hints: null,
    view_format: "html",
    settings_panel: "depth_tier_presets",
    source: "test",
    notes: [],
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

  it("mounts dual-gate L1/L2 checklist prep on chat pub refs (agg)", () => {
    render(
      <MemoryRouter>
        <ChatInputArea />
      </MemoryRouter>,
    );
    const prep = screen.getByTestId("chat-input-pub-refs-dual-gate");
    expect(prep.getAttribute("data-view-format")).toBe("html");
    expect(prep.getAttribute("data-l1-arxiv")).toBe("deferred");
    expect(prep.getAttribute("data-l2-substack")).toBe("deferred");
    const l1 = screen.getByTestId("chat-input-l1-checklist-link");
    expect(l1.getAttribute("href")).toBe("/settings#hydrate-live-status");
    const l2 = screen.getByTestId("chat-input-l2-checklist-link");
    expect(l2.getAttribute("href")).toBe("/settings#hydrate-live-status");
  });

  it("inserts knowledge-dense quick-call presets on chase follow-ups (agz)", () => {
    render(
      <MemoryRouter>
        <ChatInputArea />
      </MemoryRouter>,
    );
    const panel = screen.getByTestId("chat-input-publication-refs");
    expect(panel.getAttribute("data-seamless-pub-quick-call")).toBe("true");
    expect(
      Number(panel.getAttribute("data-knowledge-dense-presets") || 0),
    ).toBeGreaterThanOrEqual(4);
    const chips = screen.getByTestId("chat-input-publication-quick-call");
    expect(chips.getAttribute("data-auto-hydrate")).toBe("false");
    fireEvent.click(
      screen.getByTestId("chat-input-preset-attention-is-all-you-need"),
    );
    expect(
      (screen.getByTestId("chat-publication-refs-input") as HTMLTextAreaElement)
        .value,
    ).toMatch(/arxiv:1706\.03762/);
    fireEvent.click(screen.getByTestId("chat-input-preset-scaling-laws"));
    const value = (
      screen.getByTestId("chat-publication-refs-input") as HTMLTextAreaElement
    ).value;
    expect(value).toMatch(/arxiv:2001\.08361/);
    expect(value).toMatch(/arxiv:1706\.03762/);
  });

  it("stamps budget foresight pub-ref count after quick-call (ahh)", () => {
    render(
      <MemoryRouter>
        <ChatInputArea />
      </MemoryRouter>,
    );
    const mount = screen.getByTestId("chat-input-budget-mount");
    expect(mount.getAttribute("data-pub-ref-count")).toBe("0");
    expect(mount.getAttribute("data-has-pub-refs")).toBe("false");
    fireEvent.click(
      screen.getByTestId("chat-input-preset-attention-is-all-you-need"),
    );
    fireEvent.click(screen.getByTestId("chat-input-preset-scaling-laws"));
    const after = screen.getByTestId("chat-input-budget-mount");
    expect(after.getAttribute("data-pub-ref-count")).toBe("2");
    expect(after.getAttribute("data-has-pub-refs")).toBe("true");
    expect(Number(after.getAttribute("data-prompt-chars") || 0)).toBeGreaterThan(
      10,
    );
    expect(
      screen
        .getByTestId("chat-input-driver-badge-mount")
        .getAttribute("data-pub-ref-count"),
    ).toBe("2");
    // Residual (aid): operator-visible pub-ref foresight chrome.
    expect(
      screen.getByTestId("chat-input-pub-ref-foresight-chrome").textContent,
    ).toMatch(/2 refs/i);
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
