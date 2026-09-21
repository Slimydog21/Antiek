import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ThoughtPartnerPanel from "./ThoughtPartnerPanel";

const apiFetch = vi.fn();
const fetchUserModels = vi.fn();
const fetchSettingsUsage = vi.fn();
const fetchSettingsBalance = vi.fn();

vi.mock("../../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  composeContext: vi.fn(),
  searchBlocks: vi.fn().mockResolvedValue({ count: 0, hits: [] }),
}));
vi.mock("../../api/settingsModels", () => ({
  fetchUserModels: (...args: unknown[]) => fetchUserModels(...args),
}));
vi.mock("../../api/settingsUsage", () => ({
  fetchSettingsUsage: (...args: unknown[]) => fetchSettingsUsage(...args),
  fetchSettingsBalance: (...args: unknown[]) => fetchSettingsBalance(...args),
}));
vi.mock("../../brand/werner/animated", () => ({ WernerThinking: () => null }));
vi.mock("../../components/ai/ContextPicker", () => ({ default: () => null }));
vi.mock("../../components/ai/aiActions", () => ({
  dispatchAiAction: vi.fn(),
  parseAssistantReply: (text: string) => ({ prose: text, actions: [] }),
  workspaceContextPrompt: () => "brainstorm workspace",
}));

const model = {
  id: "owner-key-2",
  provider_kind: "anthropic",
  provider_catalog_id: "anthropic",
  model_id: "claude-sonnet",
  display_name: "Claude Sonnet",
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

describe("Brainstorm thought-partner owner model choice", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    fetchUserModels.mockResolvedValue({ models: [model], count: 1, stale_registered: [], source: "test" });
    fetchSettingsUsage.mockResolvedValue({ keys: [], count: 0 });
    fetchSettingsBalance.mockResolvedValue({ kind: "unavailable", balance_usd: null });
    apiFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        text: "brainstorm answer",
        shape: "CHALLENGE",
        model_receipt: {
          authority: "owner_byot",
          requested_provider_id: "owner-key-2",
          requested_model_id: "claude-sonnet",
          actual_provider_id: "anthropic",
          actual_model_id: "claude-sonnet-4-5",
          authority_digest: "digest",
        },
      }),
    });
  });
  afterEach(cleanup);

  it("uses the real picker control, sends paired routing fields, and renders the receipt", async () => {
    const user = userEvent.setup();
    render(<ThoughtPartnerPanel />);

    const picker = await screen.findByRole("button", { name: "Thought partner model" });
    await user.click(picker);
    await user.click(await screen.findByText("Claude Sonnet"));
    fireEvent.change(screen.getByLabelText("Thought partner prompt"), {
      target: { value: "Challenge the current synthesis" },
    });
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith("/thought-partner", expect.anything()));
    const call = apiFetch.mock.calls.find(([url]) => url === "/thought-partner");
    const body = JSON.parse(call?.[1]?.body as string);
    expect(body).toMatchObject({
      prompt: "Challenge the current synthesis",
      history: [],
      system_context: "brainstorm workspace",
      model_choice: {
        authority: "user_model",
        provider_id: "owner-key-2",
        model_id: "claude-sonnet",
      },
    });
    expect(body.operation_id).toMatch(/^thought-brainstorm-/);
    expect((await screen.findByTestId("thought-partner-model-receipt")).textContent).toContain(
      "Used Claude Sonnet · claude-sonnet-4-5",
    );
  });

  it("keeps an unavailable model selected and explains the failure", async () => {
    const user = userEvent.setup();
    apiFetch.mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: "owner_model_unavailable" }),
    });
    render(<ThoughtPartnerPanel />);

    const picker = await screen.findByRole("button", { name: "Thought partner model" });
    await user.click(picker);
    await user.click(await screen.findByText("Claude Sonnet"));
    fireEvent.change(screen.getByLabelText("Thought partner prompt"), {
      target: { value: "Try this model" },
    });
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(
      await screen.findByText(
        "Claude Sonnet is unavailable. Choose another model or try again later.",
      ),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Thought partner model" }).textContent).toContain(
      "Claude Sonnet",
    );
    expect(apiFetch.mock.calls.filter(([url]) => url === "/thought-partner")).toHaveLength(1);
  });
});
