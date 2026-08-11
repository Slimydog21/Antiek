import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AddModelPanel from "./AddModelPanel";
import {
  addUserModel,
  fetchSettingsModelCatalog,
  fetchUserModels,
  removeUserModel,
} from "../../api/settingsModels";

const SECRET = "sk-test-super-secret-key-000111222";

const existingRow = {
  id: "user-openai",
  provider_kind: "openai_compat" as const,
  provider_catalog_id: "openai" as const,
  model_id: "gpt-5.6-sol",
  display_name: "OpenAI model",
  base_url: "https://api.openai.com",
  enabled: true,
  key_present: true,
  registered: true,
  route_eligible: true,
  pricing_status: "known" as const,
  hard_ceiling_eligible: false,
  execution_status: "blocked_idempotency_unproven" as const,
  rate_snapshot: "openai-gpt-5.6-sol-2026-08-12",
};

const secondRow = {
  ...existingRow,
  id: "user-anthropic",
  provider_kind: "anthropic" as const,
  provider_catalog_id: "anthropic" as const,
  model_id: "claude-opus-5",
  display_name: "Anthropic model",
  base_url: "https://api.anthropic.com",
};

const catalogResponse = {
  providers: [
    {
      catalog_id: "openai",
      display: "OpenAI",
      provider_kind: "openai_compat" as const,
      default_base_url: "https://api.openai.com",
      models: [
        { id: "gpt-5.6-sol", label: "GPT-5.6 Sol", snapshot: "openai-sol" },
        { id: "gpt-5.6-luna", label: "GPT-5.6 Luna", snapshot: "openai-luna" },
      ],
      pricing_source: "https://developers.openai.com/api/docs/models",
    },
    {
      catalog_id: "anthropic",
      display: "Anthropic",
      provider_kind: "anthropic" as const,
      default_base_url: "https://api.anthropic.com",
      models: [
        {
          id: "claude-opus-5",
          label: "Claude Opus 5",
          snapshot: "anthropic-opus",
        },
      ],
      pricing_source: "https://platform.claude.com/docs/models",
    },
  ],
  count: 2,
};

vi.mock("../../api/settingsModels", () => ({
  fetchUserModels: vi.fn(async () => ({
    models: [existingRow],
    count: 1,
    stale_registered: [],
    source: "test",
  })),
  fetchSettingsModelCatalog: vi.fn(async () => catalogResponse),
  addUserModel: vi.fn(async () => ({ ...existingRow, id: "user-added" })),
  removeUserModel: vi.fn(async () => ({ removed: existingRow.id, notes: [] })),
}));

async function ready() {
  await waitFor(() => expect(screen.getByText("OpenAI model")).toBeTruthy());
  await waitFor(() =>
    expect(screen.getByRole("radio", { name: "OpenAI" })).toBeTruthy(),
  );
}

describe("AddModelPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchUserModels).mockResolvedValue({
      models: [existingRow],
      count: 1,
      stale_registered: [],
      source: "test",
    });
  });
  afterEach(cleanup);

  it("shows actual execution status without rendering key material", async () => {
    render(<AddModelPanel />);
    await ready();
    expect(screen.getByText("Blocked: idempotency unproven")).toBeTruthy();
    expect(document.body.textContent).not.toContain("sk-");
  });

  it("shows catalog loading and offers a value-free retry after failure", async () => {
    let rejectCatalog!: () => void;
    vi.mocked(fetchSettingsModelCatalog)
      .mockImplementationOnce(
        () =>
          new Promise((_resolve, reject) => {
            rejectCatalog = () => reject(new Error(`catalog echoed ${SECRET}`));
          }),
      )
      .mockResolvedValueOnce(catalogResponse);
    const user = userEvent.setup();
    render(<AddModelPanel />);
    expect(screen.getByRole("status").textContent).toContain(
      "Loading provider presets",
    );
    rejectCatalog();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Can't load provider presets");
    expect(document.body.textContent).not.toContain(SECRET);
    await user.click(screen.getByRole("button", { name: "Retry presets" }));
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "OpenAI" })).toBeTruthy(),
    );
    expect(fetchSettingsModelCatalog).toHaveBeenCalledTimes(2);
  });

  it("submits the exact trusted OpenAI payload and clears the key before await", async () => {
    let resolve!: () => void;
    vi.mocked(addUserModel).mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = () => done(existingRow);
        }),
    );
    const user = userEvent.setup();
    render(<AddModelPanel />);
    await ready();
    const key = screen.getByPlaceholderText("sk-…") as HTMLInputElement;
    await user.type(key, SECRET);
    await user.click(screen.getByRole("button", { name: "Add model" }));
    expect(key.value).toBe("");
    expect(addUserModel).toHaveBeenCalledWith({
      provider_kind: "openai_compat",
      provider_catalog_id: "openai",
      model_id: "gpt-5.6-sol",
      display_name: "GPT-5.6 Sol",
      base_url: "https://api.openai.com",
      api_key: SECRET,
    });
    resolve();
    await waitFor(() => expect(fetchUserModels).toHaveBeenCalledTimes(2));
    expect(document.body.textContent).not.toContain(SECRET);
  });

  it("submits Anthropic without base_url", async () => {
    const user = userEvent.setup();
    render(<AddModelPanel />);
    await ready();
    await user.click(screen.getByRole("radio", { name: "Anthropic" }));
    await user.type(screen.getByPlaceholderText("sk-…"), SECRET);
    await user.click(screen.getByRole("button", { name: "Add model" }));
    await waitFor(() =>
      expect(addUserModel).toHaveBeenCalledWith({
        provider_kind: "anthropic",
        provider_catalog_id: "anthropic",
        model_id: "claude-opus-5",
        display_name: "Claude Opus 5",
        api_key: SECRET,
      }),
    );
  });

  it("keeps generic OpenAI-compatible setup under Advanced with its exact payload", async () => {
    const user = userEvent.setup();
    render(<AddModelPanel />);
    await ready();
    await user.click(screen.getByRole("radio", { name: "Advanced" }));
    await user.type(
      screen.getByPlaceholderText("My DeepSeek"),
      "Private gateway",
    );
    await user.type(
      screen.getByPlaceholderText("deepseek-chat"),
      "private-model",
    );
    await user.type(
      screen.getByPlaceholderText("https://api.deepseek.com/v1"),
      "https://models.example/v1",
    );
    await user.type(screen.getByPlaceholderText("sk-…"), SECRET);
    fireEvent.submit(
      screen.getByRole("button", { name: "Add model" }).closest("form")!,
    );
    await waitFor(() =>
      expect(addUserModel).toHaveBeenCalledWith({
        provider_kind: "openai_compat",
        model_id: "private-model",
        display_name: "Private gateway",
        base_url: "https://models.example/v1",
        api_key: SECRET,
      }),
    );
  });

  it("clears credentials on provider switch, model switch, and cancel, then focuses the key", async () => {
    const user = userEvent.setup();
    render(<AddModelPanel />);
    await ready();
    const key = screen.getByPlaceholderText("sk-…") as HTMLInputElement;
    await user.type(key, SECRET);
    await user.click(screen.getByRole("radio", { name: "Anthropic" }));
    expect(key.value).toBe("");
    await waitFor(() => expect(document.activeElement).toBe(key));
    await user.click(screen.getByRole("radio", { name: "OpenAI" }));
    await user.type(key, SECRET);
    await user.selectOptions(screen.getByLabelText("Model"), "gpt-5.6-luna");
    expect(key.value).toBe("");
    await user.type(key, SECRET);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(key.value).toBe("");
  });

  it("keeps a global mutation lock while allowing editor changes and announces the late result", async () => {
    let resolve!: () => void;
    vi.mocked(addUserModel).mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = () => done(existingRow);
        }),
    );
    const user = userEvent.setup();
    render(<AddModelPanel />);
    await ready();
    const key = screen.getByPlaceholderText("sk-…") as HTMLInputElement;
    await user.type(key, SECRET);
    await user.click(screen.getByRole("button", { name: "Add model" }));
    expect(screen.getByRole("form").getAttribute("aria-busy")).toBe("true");
    await user.click(screen.getByRole("radio", { name: "Anthropic" }));
    expect(key.value).toBe("");
    expect(
      (screen.getByRole("button", { name: "Adding…" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(
      (screen.getByRole("button", { name: "Adding…" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(addUserModel).toHaveBeenCalledTimes(1);
    resolve();
    await waitFor(() => expect(fetchUserModels).toHaveBeenCalledTimes(2));
    expect((await screen.findByRole("status")).textContent).toContain(
      "Model added",
    );
    await waitFor(() =>
      expect(screen.getByRole("form").getAttribute("aria-busy")).toBe("false"),
    );
  });

  it("surfaces a value-free error even when the editor changed", async () => {
    let reject!: (reason: Error) => void;
    vi.mocked(addUserModel).mockImplementationOnce(
      () =>
        new Promise((_done, fail) => {
          reject = fail;
        }),
    );
    const user = userEvent.setup();
    render(<AddModelPanel />);
    await ready();
    await user.type(screen.getByPlaceholderText("sk-…"), SECRET);
    await user.click(screen.getByRole("button", { name: "Add model" }));
    await user.click(screen.getByRole("radio", { name: "Anthropic" }));
    reject(new Error(`server echoed ${SECRET}`));
    const alert = await screen.findByRole("alert");
    expect(document.body.textContent).not.toContain(SECRET);
    expect(alert.textContent).toContain("Can't add this model");
  });

  it("supports keyboard submission and exposes 44px full-width mobile controls", async () => {
    const user = userEvent.setup();
    render(<AddModelPanel />);
    await ready();
    const key = screen.getByPlaceholderText("sk-…");
    await user.type(key, `${SECRET}{Enter}`);
    await waitFor(() => expect(addUserModel).toHaveBeenCalledTimes(1));
    expect(
      screen.getByRole("button", { name: "Add model" }).className,
    ).toContain("h-11");
    expect(
      screen.getByRole("button", { name: "Add model" }).className,
    ).toContain("w-full");
    expect(
      screen.getByRole("radio", { name: "OpenAI" }).closest("label")?.className,
    ).toContain("min-h-11");
  });

  it("uses a narrow-safe saved-row DOM policy at a 390px viewport", async () => {
    Object.defineProperty(window, "innerWidth", {
      value: 390,
      configurable: true,
    });
    vi.mocked(fetchUserModels).mockResolvedValueOnce({
      models: [
        {
          ...existingRow,
          model_id: "provider/model-with-an-extremely-long-unbroken-identifier",
        },
      ],
      count: 1,
      stale_registered: [],
      source: "test",
    });
    render(<AddModelPanel />);
    await ready();
    const row = screen
      .getByText(/provider\/model-with-an-extremely-long/)
      .closest("li")!;
    expect(window.innerWidth).toBe(390);
    expect(row.className).toContain("min-w-0");
    expect(row.className).toContain("flex-col");
    expect(
      screen.getByText(/provider\/model-with-an-extremely-long/).className,
    ).toContain("break-all");
    const actions = screen.getByRole("button", {
      name: "Remove",
    }).parentElement!;
    expect(actions.className).toContain("w-full");
    expect(actions.className).toContain("grid-cols-2");
  });

  it("restores focus to the next saved row after removal", async () => {
    vi.mocked(fetchUserModels)
      .mockResolvedValueOnce({
        models: [existingRow, secondRow],
        count: 2,
        stale_registered: [],
        source: "test",
      })
      .mockResolvedValueOnce({
        models: [secondRow],
        count: 1,
        stale_registered: [],
        source: "test",
      });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    render(<AddModelPanel />);
    await ready();
    const removeButtons = await screen.findAllByRole("button", {
      name: "Remove",
    });
    await user.click(removeButtons[0]);
    await waitFor(() =>
      expect(removeUserModel).toHaveBeenCalledWith(existingRow.id),
    );
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole("button", { name: "Remove" }),
      ),
    );
  });
});
