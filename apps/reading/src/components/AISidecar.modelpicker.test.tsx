import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// SPR-03 Task 3 — the driver dropdown on the AI sidecar. Mocks mirror
// AISidecar.context-wiring.test.tsx so only the picker wiring is under test;
// lib/api is spread from the original because the inventory fetch reads
// API_BASE off it, and vitest throws on an export a factory mock omits.
vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn(),
  composeContext: vi.fn(),
}));
vi.mock("../brand/mascot/animated", () => ({
  BrainThinking: () => null,
}));
vi.mock("../hooks/useReplyMode", () => ({
  useReplyMode: () => ({ mode: "text", setMode: () => undefined }),
}));
vi.mock("./SpokenReply", () => ({
  __esModule: true,
  default: () => null,
}));
vi.mock("./ai/aiActions", () => ({
  dispatchAiAction: vi.fn(),
  parseAssistantReply: () => ({ prose: "ok", actions: [], parseErrors: [] }),
  workspaceContextPrompt: () => "OPAQUE-WORKSPACE-CTX",
}));

import { apiFetch } from "../lib/api";
import AISidecar from "./AISidecar";
import { THOUGHT_PARTNER_SEED_EVENT } from "./ai/thoughtPartnerSeed";

const apiFetchMock = apiFetch as unknown as ReturnType<typeof vi.fn>;

/** One executable key carrying two variants, in the exact 15-key row shape
 *  the inventory parser accepts. */
const inventory = {
  models: [
    {
      id: "um-1",
      provider_kind: "openai_compat",
      provider_catalog_id: "deepseek",
      model_id: "deepseek-reasoner",
      model_ids: ["deepseek-reasoner", "deepseek-chat"],
      display_name: "My DeepSeek",
      base_url: "https://api.deepseek.com",
      enabled: true,
      key_present: true,
      registered: true,
      route_eligible: true,
      pricing_status: "known",
      hard_ceiling_eligible: true,
      execution_status: "executable",
      rate_snapshot: "deepseek-v4-pro-2026-08-spec",
    },
  ],
  count: 1,
  stale_registered: [],
  source: "test",
};

function mockApiFetch(): void {
  apiFetchMock.mockImplementation((url: string) => {
    if (typeof url === "string" && url.includes("/thought-partner")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ text: "reply", shape: "SYNTHESIS" }),
      });
    }
    if (typeof url === "string" && url.endsWith("/settings/models/user")) {
      return Promise.resolve({ ok: true, status: 200, json: async () => inventory });
    }
    // Usage/balance/trajectory/billing: benign 404s, nothing under test.
    return Promise.resolve({ ok: false, status: 404 });
  });
}

function thoughtPartnerBody(): Record<string, unknown> | undefined {
  for (const [url, init] of apiFetchMock.mock.calls) {
    if (typeof url === "string" && url.includes("/thought-partner")) {
      return JSON.parse((init as RequestInit).body as string);
    }
  }
  return undefined;
}

describe("AISidecar driver dropdown (SPR-03 Task 3)", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    mockApiFetch();
  });
  afterEach(cleanup);

  it("mounts the ModelUsagePicker in the sidecar tree", async () => {
    render(<AISidecar />);
    const trigger = await screen.findByLabelText("Model for the thought partner");
    expect(trigger).toBeTruthy();
    // It reads the house route until a key is chosen.
    await waitFor(() => expect(trigger.textContent).toContain("Default"));
  });

  it("carries the chosen key and variant on the thought-partner request as model_choice + operation_id", async () => {
    const user = userEvent.setup();
    render(<AISidecar />);
    const trigger = await screen.findByLabelText("Model for the thought partner");
    await waitFor(() => expect(trigger.textContent).toContain("Default"));
    await waitFor(() =>
      expect(apiFetchMock.mock.calls.some(([u]) => String(u).endsWith("/settings/models/user"))).toBe(true),
    );
    await user.click(trigger);
    const flash = await waitFor(() => {
      const el = Array.from(document.querySelectorAll("button")).find((b) =>
        (b.textContent || "").includes("deepseek-chat"),
      );
      expect(el).toBeTruthy();
      return el as HTMLElement;
    });
    await user.click(flash);
    await waitFor(() => expect(trigger.textContent).toContain("My DeepSeek · deepseek-chat"));

    fireEvent.change(screen.getByPlaceholderText("What's the question?"), {
      target: { value: "summarize this" },
    });
    fireEvent.click(screen.getByText("Send"));

    await waitFor(() => expect(thoughtPartnerBody()).toBeDefined());
    const body = thoughtPartnerBody() as Record<string, unknown>;
    expect(body.model_choice).toEqual({
      authority: "user_model",
      provider_id: "um-1",
      model_id: "deepseek-chat",
    });
    expect(String(body.operation_id)).toMatch(/^sidecar-/);
  });

  it("sends neither field while the house route is in force", async () => {
    render(<AISidecar />);
    fireEvent.change(screen.getByPlaceholderText("What's the question?"), {
      target: { value: "summarize this" },
    });
    fireEvent.click(screen.getByText("Send"));
    await waitFor(() => expect(thoughtPartnerBody()).toBeDefined());
    const body = thoughtPartnerBody() as Record<string, unknown>;
    expect("model_choice" in body).toBe(false);
    expect("operation_id" in body).toBe(false);
  });

  it("adopts a driver chosen elsewhere via the seed bus (the CommandPalette's picker)", async () => {
    render(<AISidecar />);
    const trigger = await screen.findByLabelText("Model for the thought partner");
    await waitFor(() =>
      expect(apiFetchMock.mock.calls.some(([u]) => String(u).endsWith("/settings/models/user"))).toBe(true),
    );
    await waitFor(() => expect(trigger.textContent).toContain("Default"));
    window.dispatchEvent(
      new CustomEvent(THOUGHT_PARTNER_SEED_EVENT, {
        detail: { owner_model: { row_id: "um-1", model_id: "deepseek-chat" } },
      }),
    );
    await waitFor(() => expect(trigger.textContent).toContain("My DeepSeek · deepseek-chat"));
  });
});
