import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AISidecar from "./AISidecar";
import { thoughtPartnerLaunchKey } from "../api/thoughtPartner";

const apiFetch = vi.fn();
const fetchUserModels = vi.fn();
const fetchSettingsUsage = vi.fn();
const fetchSettingsBalance = vi.fn();

vi.mock("../lib/api", () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));
vi.mock("../api/settingsModels", () => ({
  fetchUserModels: (...args: unknown[]) => fetchUserModels(...args),
}));
vi.mock("../api/settingsUsage", () => ({
  fetchSettingsUsage: (...args: unknown[]) => fetchSettingsUsage(...args),
  fetchSettingsBalance: (...args: unknown[]) => fetchSettingsBalance(...args),
}));
vi.mock("../brand/werner/animated", () => ({ WernerThinking: () => null }));
vi.mock("../hooks/useReplyMode", () => ({
  useReplyMode: () => ({ mode: "text", setMode: () => undefined }),
}));
vi.mock("./SpokenReply", () => ({ default: () => null }));
vi.mock("./ai/ContextPicker", () => ({ default: () => null }));
vi.mock("./ai/aiActions", () => ({
  dispatchAiAction: vi.fn(),
  parseAssistantReply: (text: string) => ({ prose: text, actions: [], parseErrors: [] }),
  workspaceContextPrompt: () => "workspace context",
}));

const model = {
  id: "owner-key-1",
  provider_kind: "openai_compat",
  provider_catalog_id: "deepseek",
  model_id: "deepseek-chat",
  display_name: "DeepSeek V4",
  base_url: null,
  enabled: true,
  key_present: true,
  registered: true,
  route_eligible: true,
  pricing_status: "known",
  hard_ceiling_eligible: true,
  execution_status: "executable",
  rate_snapshot: null,
};

function thoughtPartnerBody(): Record<string, unknown> {
  const call = apiFetch.mock.calls.find(([url]) => url === "/thought-partner");
  return JSON.parse(call?.[1]?.body as string) as Record<string, unknown>;
}

describe("AISidecar owner model choice", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchUserModels.mockResolvedValue({ models: [model], count: 1, stale_registered: [], source: "test" });
    fetchSettingsUsage.mockResolvedValue({ keys: [], count: 0 });
    fetchSettingsBalance.mockResolvedValue({ kind: "unavailable", balance_usd: null });
    apiFetch.mockImplementation((url: string) => {
      if (url === "/thought-partner") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            text: "answer",
            shape: "SYNTHESIS",
            model_receipt: {
              authority: "owner_byot",
              requested_provider_id: "owner-key-1",
              requested_model_id: "deepseek-chat",
              actual_provider_id: "deepseek",
              actual_model_id: "deepseek-chat-202609",
              authority_digest: "digest",
            },
          }),
        });
      }
      return Promise.resolve({ ok: false, status: 404, json: async () => ({}) });
    });
  });
  afterEach(cleanup);

  it("sends the selected owner route with its operation id and shows actual execution", async () => {
    const user = userEvent.setup();
    render(<AISidecar />);

    const picker = await screen.findByRole("button", { name: "Thought partner model" });
    await waitFor(() => expect(picker.textContent).toContain("Default"));
    await user.click(picker);
    await user.click(await screen.findByText("DeepSeek V4"));

    fireEvent.change(screen.getByPlaceholderText("What's the question?"), {
      target: { value: "Compare the evidence" },
    });
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(apiFetch.mock.calls.some(([url]) => url === "/thought-partner")).toBe(true));
    expect(thoughtPartnerBody()).toMatchObject({
      investigation_id: "__sidecar__",
      prompt: "Compare the evidence",
      history: [],
      system_context: "workspace context",
      model_choice: {
        authority: "user_model",
        provider_id: "owner-key-1",
        model_id: "deepseek-chat",
      },
    });
    expect(thoughtPartnerBody().operation_id).toMatch(/^thought-sidecar-/);
    expect((await screen.findByTestId("thought-partner-model-receipt")).textContent).toContain(
      "Used DeepSeek V4 · deepseek-chat-202609",
    );
  });

  it("omits both owner-routing fields on the default route", async () => {
    render(<AISidecar />);
    fireEvent.change(screen.getByPlaceholderText("What's the question?"), {
      target: { value: "Use the house route" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(apiFetch.mock.calls.some(([url]) => url === "/thought-partner")).toBe(true));
    expect(thoughtPartnerBody()).not.toHaveProperty("model_choice");
    expect(thoughtPartnerBody()).not.toHaveProperty("operation_id");
  });

  it("includes history, context, and investigation scope in launch identity", () => {
    const base = {
      prompt: "same prompt",
      history: [{ question: "earlier", answer: "answer" }],
      system_context: "context-a",
      investigation_id: "investigation-a",
    };
    const key = thoughtPartnerLaunchKey(base);
    expect(thoughtPartnerLaunchKey({ ...base, history: [] })).not.toBe(key);
    expect(thoughtPartnerLaunchKey({ ...base, system_context: "context-b" })).not.toBe(key);
    expect(thoughtPartnerLaunchKey({ ...base, investigation_id: "investigation-b" })).not.toBe(key);
  });

  it("explains an unknown provider outcome without retrying", async () => {
    apiFetch.mockImplementation((url: string) => {
      if (url === "/thought-partner") {
        return Promise.resolve({
          ok: false,
          status: 503,
          json: async () => ({ detail: "owner_model_outcome_unknown" }),
        });
      }
      return Promise.resolve({ ok: false, status: 404, json: async () => ({}) });
    });
    render(<AISidecar />);
    fireEvent.change(screen.getByPlaceholderText("What's the question?"), {
      target: { value: "Was this completed?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(
      await screen.findByText(
        "The provider response could not be confirmed. Check usage before starting another turn.",
      ),
    ).toBeTruthy();
    expect(apiFetch.mock.calls.filter(([url]) => url === "/thought-partner")).toHaveLength(1);
  });
});
