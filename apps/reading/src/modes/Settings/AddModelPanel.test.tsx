import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AddModelPanel from "./AddModelPanel";
import { addUserModel, fetchUserModels } from "../../api/settingsModels";

const SECRET = "sk-test-super-secret-key-000111222";

const existingRow = {
  id: "user-my-deepseek",
  provider_kind: "openai_compat" as const,
  model_id: "deepseek-chat",
  display_name: "My DeepSeek",
  base_url: "https://api.deepseek.com/v1",
  enabled: true,
  key_present: true,
  registered: true,
};

vi.mock("../../api/settingsModels", () => ({
  fetchUserModels: vi.fn(async () => ({
    models: [existingRow],
    count: 1,
    stale_registered: [],
    source: "test",
  })),
  addUserModel: vi.fn(async () => ({ ...existingRow, id: "user-added" })),
  removeUserModel: vi.fn(async () => ({ removed: "user-my-deepseek", notes: [] })),
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

  it("submits the form through the client and clears the key field", async () => {
    const user = userEvent.setup();
    render(<AddModelPanel />);
    await waitFor(() => expect(screen.getByText("My DeepSeek")).toBeTruthy());

    const name = screen.getByPlaceholderText("My DeepSeek");
    const model = screen.getByPlaceholderText("deepseek-chat");
    const base = screen.getByPlaceholderText("https://api.deepseek.com/v1");
    const key = screen.getByPlaceholderText("sk-…") as HTMLInputElement;

    // The key field is a masked, write-only input.
    expect(key.type).toBe("password");

    await user.type(name, "My OpenAI");
    await user.type(model, "gpt-5.5");
    await user.type(base, "https://api.openai.com/v1");
    await user.type(key, SECRET);

    await user.click(screen.getByRole("button", { name: /add model/i }));

    await waitFor(() =>
      expect(vi.mocked(addUserModel)).toHaveBeenCalledWith({
        provider_kind: "openai_compat",
        model_id: "gpt-5.5",
        display_name: "My OpenAI",
        base_url: "https://api.openai.com/v1",
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
    await user.type(screen.getByPlaceholderText("deepseek-chat"), "m");
    await user.type(
      screen.getByPlaceholderText("https://api.deepseek.com/v1"),
      "https://x.test/v1",
    );
    await user.type(screen.getByPlaceholderText("sk-…"), "k-123456789");
    expect(button.hasAttribute("disabled")).toBe(false);
  });
});
