import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AddModelPanel from "./AddModelPanel";
import { addUserModel, fetchUserModels } from "../../api/settingsModels";

const SECRET = "sk-test-super-secret-key-000111222";

const existingRow = {
  id: "user-my-deepseek",
  provider_kind: "openai_compat" as const,
  provider_catalog_id: "deepseek" as const,
  model_id: "deepseek-chat",
  display_name: "My DeepSeek",
  base_url: "https://api.deepseek.com/v1",
  enabled: true,
  key_present: true,
  registered: true,
  route_eligible: true,
  pricing_status: "known" as const,
  hard_ceiling_eligible: false,
  execution_status: "blocked_idempotency_unproven",
  rate_snapshot: "deepseek-v4-flash-2026-08-spec",
};

vi.mock("../../api/settingsModels", () => ({
  fetchUserModels: vi.fn(async () => ({
    models: [existingRow],
    count: 1,
    stale_registered: [],
    source: "test",
  })),
  addUserModel: vi.fn(async () => ({ ...existingRow, id: "user-added" })),
  removeUserModel: vi.fn(async () => ({
    removed: "user-my-deepseek",
    notes: [],
  })),
}));

describe("AddModelPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // vitest.config.ts sets globals:false, so RTL's auto-cleanup (which
  // hooks a global afterEach) never registers — clean up explicitly.
  afterEach(cleanup);

  it("renders the inventory with key-present badge and no key material", async () => {
    render(<AddModelPanel />);
    await waitFor(() => expect(screen.getByText("My DeepSeek")).toBeTruthy());
    expect(screen.getByText("key stored")).toBeTruthy();
    expect(screen.getByText("registered")).toBeTruthy();
    // Inventory rows carry no key field; nothing key-shaped may render.
    expect(document.body.textContent).not.toContain("sk-");
  });

  it("submits a named provider and pinned variant without a user-entered endpoint", async () => {
    const user = userEvent.setup();
    render(<AddModelPanel />);
    await waitFor(() => expect(screen.getByText("My DeepSeek")).toBeTruthy());

    const name = screen.getByPlaceholderText("My DeepSeek");
    const key = screen.getByPlaceholderText("sk-…") as HTMLInputElement;

    // The key field is a masked, write-only input.
    expect(key.type).toBe("password");

    await user.type(name, "Research DeepSeek");
    await user.type(key, SECRET);

    await user.click(screen.getByRole("button", { name: /add model/i }));

    await waitFor(() =>
      expect(vi.mocked(addUserModel)).toHaveBeenCalledWith({
        provider_kind: "openai_compat",
        provider_catalog_id: "deepseek",
        model_id: "deepseek-reasoner",
        display_name: "Research DeepSeek",
        api_key: SECRET,
      }),
    );
    // Key field cleared after submit; the key never renders anywhere.
    expect(key.value).toBe("");
    expect(document.body.textContent).not.toContain(SECRET);
    // Inventory refreshed after a successful add.
    expect(vi.mocked(fetchUserModels).mock.calls.length).toBeGreaterThan(1);
  });

  it("keeps the add button disabled until the form is complete", async () => {
    const user = userEvent.setup();
    render(<AddModelPanel />);
    await waitFor(() => expect(screen.getByText("My DeepSeek")).toBeTruthy());

    const button = screen.getByRole("button", { name: /add model/i });
    expect(button.hasAttribute("disabled")).toBe(true);

    await user.type(screen.getByPlaceholderText("My DeepSeek"), "X");
    await user.type(screen.getByPlaceholderText("sk-…"), "k-123456789");
    expect(button.hasAttribute("disabled")).toBe(false);
  });

  it("switches variants while preserving named-provider authority", async () => {
    const user = userEvent.setup();
    render(<AddModelPanel />);
    await waitFor(() => expect(screen.getByText("My DeepSeek")).toBeTruthy());

    const selector = screen.getByRole("combobox", { name: "Model variant" });
    await user.click(selector.querySelector("button") as HTMLButtonElement);
    await user.click(screen.getByRole("option", { name: "DeepSeek V4 Flash" }));
    await user.type(screen.getByPlaceholderText("My DeepSeek"), "My Flash");
    await user.type(screen.getByPlaceholderText("sk-…"), SECRET);
    await user.click(screen.getByRole("button", { name: /add model/i }));

    await waitFor(() =>
      expect(vi.mocked(addUserModel)).toHaveBeenCalledWith({
        provider_kind: "openai_compat",
        provider_catalog_id: "deepseek",
        model_id: "deepseek-chat",
        display_name: "My Flash",
        api_key: SECRET,
      }),
    );
  });

  it("does not carry a custom endpoint into Anthropic", async () => {
    const user = userEvent.setup();
    render(<AddModelPanel />);
    await waitFor(() => expect(screen.getByText("My DeepSeek")).toBeTruthy());

    const provider = screen.getByRole("combobox", { name: "Provider" });
    await user.click(provider.querySelector("button") as HTMLButtonElement);
    await user.click(
      screen.getByRole("option", { name: "Custom OpenAI-compatible" }),
    );
    await user.type(
      screen.getByPlaceholderText("https://provider.example/v1"),
      "https://stale.example/v1",
    );
    await user.click(provider.querySelector("button") as HTMLButtonElement);
    await user.click(screen.getByRole("option", { name: "Anthropic" }));
    await user.type(screen.getByPlaceholderText("My Anthropic"), "My Claude");
    await user.type(screen.getByPlaceholderText("model-id"), "claude-opus-4-8");
    await user.type(screen.getByPlaceholderText("sk-…"), SECRET);
    await user.click(screen.getByRole("button", { name: /add model/i }));

    await waitFor(() =>
      expect(vi.mocked(addUserModel)).toHaveBeenCalledWith({
        provider_kind: "anthropic",
        model_id: "claude-opus-4-8",
        display_name: "My Claude",
        api_key: SECRET,
      }),
    );
  });
});
