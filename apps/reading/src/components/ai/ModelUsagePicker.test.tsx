import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ModelUsagePicker from "./ModelUsagePicker";
import { fetchUserModels } from "../../api/settingsModels";
import { fetchSettingsUsage, fetchSettingsBalance } from "../../api/settingsUsage";

vi.mock("../../api/settingsModels", () => ({
  fetchUserModels: vi.fn(),
}));
vi.mock("../../api/settingsUsage", () => ({
  fetchSettingsUsage: vi.fn(),
  fetchSettingsBalance: vi.fn(),
}));

const mockFetchUserModels = fetchUserModels as unknown as ReturnType<typeof vi.fn>;
const mockFetchUsage = fetchSettingsUsage as unknown as ReturnType<typeof vi.fn>;
const mockFetchBalance = fetchSettingsBalance as unknown as ReturnType<typeof vi.fn>;

const sampleModels = {
  models: [
    {
      id: "um-1",
      provider_kind: "openai_compat",
      provider_catalog_id: "deepseek",
      model_id: "deepseek-chat",
      display_name: "DeepSeek V4 Pro",
      base_url: null,
      enabled: true,
      key_present: true,
      registered: true,
      route_eligible: true,
      pricing_status: "known",
      hard_ceiling_eligible: true,
      execution_status: "executable",
      rate_snapshot: null,
    },
    {
      id: "um-2",
      provider_kind: "openai_compat",
      provider_catalog_id: "deepseek",
      model_id: "deepseek-chat",
      display_name: "DeepSeek V4 Flash",
      base_url: null,
      enabled: true,
      key_present: true,
      registered: true,
      route_eligible: true,
      pricing_status: "known",
      hard_ceiling_eligible: true,
      execution_status: "executable",
      rate_snapshot: null,
    },
  ],
  count: 2,
  stale_registered: [],
  source: "test",
};

const sampleUsage = {
  keys: [
    {
      api_key_id: "um-1",
      used_cents: 1234,
      limit_cents: 5000,
      remaining_cents: 3766,
      held_cents: 0,
      available_cents: 3766,
    },
  ],
  count: 1,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetchUserModels.mockResolvedValue(sampleModels);
  mockFetchUsage.mockResolvedValue(sampleUsage);
  mockFetchBalance.mockResolvedValue({
    api_key_id: "um-1",
    catalog_id: "deepseek",
    kind: "balance_native",
    balance_usd: 12.34,
    held_cents: 0,
    available_cents: 3766,
  });
});

/** A full 13-field balance body, as the backend actually shapes it. */
function balanceBody(
  overrides: Partial<{
    api_key_id: string;
    catalog_id: string;
    kind: "balance_native" | "spend_history" | "unavailable";
    balance_usd: number | null;
    granted_usd: number | null;
    spend_usd: number | null;
    budget_usd: number | null;
    note: string | null;
  }>,
) {
  return {
    api_key_id: "um-1",
    catalog_id: "deepseek",
    kind: "balance_native" as const,
    balance_usd: null,
    granted_usd: null,
    spend_usd: null,
    budget_usd: null,
    utilization: null,
    window_label: null,
    resets_at: null,
    note: null,
    held_cents: 0,
    available_cents: null,
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("ModelUsagePicker", () => {
  it("renders trigger and loads models", async () => {
    render(<ModelUsagePicker value={null} onChange={() => {}} triggerLabel="Choose model" />);
    // Initially shows loading ellipsis
    const container = screen.getByRole("button").parentElement as HTMLElement;
    await waitFor(() => {
      // After load, clicking shows content; trigger text updates on selection but label is in menu
      expect(mockFetchUserModels).toHaveBeenCalled();
    });
    const btn = within(container).getByRole("button");
    await userEvent.click(btn);
    await waitFor(() => {
      expect(document.body.textContent || "").toContain("DeepSeek V4 Pro");
    });
  });

  it("shows empty state when no keys", async () => {
    mockFetchUserModels.mockResolvedValue({ models: [], count: 0, stale_registered: [], source: "test" });
    render(<ModelUsagePicker value={null} onChange={() => {}} />);
    const btn = screen.getAllByRole("button")[0];
    await userEvent.click(btn);
    await waitFor(() => {
      expect(document.body.textContent || "").toContain("No API keys yet");
    });
  });

  it("calls onChange with selected id", async () => {
    const onChange = vi.fn();
    render(<ModelUsagePicker value={null} onChange={onChange} />);
    // Use the first button (our picker)
    const btn = screen.getAllByRole("button")[0];
    await userEvent.click(btn);
    await waitFor(() => {
      expect(document.body.textContent || "").toContain("DeepSeek V4 Pro");
    });
    const item = screen.getByText("DeepSeek V4 Pro");
    await userEvent.click(item);
    // The row id first; the row's primary model_id rides second so a
    // consumer that reads variants gets it and one that ignores it is unchanged.
    expect(onChange).toHaveBeenCalledWith("um-1", "deepseek-chat");
  });

  it("renders usage bar and balance chip when data present", async () => {
    render(<ModelUsagePicker value="um-1" onChange={() => {}} showUsage showBalance />);
    const btn = screen.getAllByRole("button")[0];
    await userEvent.click(btn);
    await waitFor(() => {
      const txt = document.body.textContent || "";
      expect(txt).toContain("$12.34");
    });
  });

  it("labels balance_native as provider credit and spend_history as Antiek's meter, never the same chip", async () => {
    // um-1 → the provider reported remaining credit; um-2 → no native
    // adapter, so the backend answered with Antiek's own spend meter.
    mockFetchBalance.mockImplementation(async (id: string) =>
      id === "um-1"
        ? balanceBody({ api_key_id: "um-1", kind: "balance_native", balance_usd: 42.5, granted_usd: 40 })
        : balanceBody({ api_key_id: "um-2", catalog_id: "xai", kind: "spend_history", spend_usd: 2.5, budget_usd: 50 }),
    );
    render(<ModelUsagePicker value={null} onChange={() => {}} showBalance />);
    await userEvent.click(screen.getAllByRole("button")[0]);

    const native = await waitFor(() => {
      const el = document.querySelector('[data-balance-kind="balance_native"]');
      expect(el).toBeTruthy();
      return el as HTMLElement;
    });
    const meter = await waitFor(() => {
      const el = document.querySelector('[data-balance-kind="spend_history"]');
      expect(el).toBeTruthy();
      return el as HTMLElement;
    });

    // Provider credit reads as credit, with the sign and the word.
    expect(native.textContent).toContain("+$42.50");
    expect(native.textContent).toContain("credit");
    expect(native.getAttribute("title")).toContain("Provider credit");
    // The meter reads as spend against a cap, says it is not credit, and is
    // styled differently — a meter presented as credit is a wrong number.
    expect(meter.textContent).toContain("spent $2.50");
    expect(meter.textContent).toContain("$50.00");
    expect(meter.textContent).not.toContain("credit");
    expect(meter.getAttribute("title")).toContain("not provider credit");
    expect(meter.className).not.toBe(native.className);
  });

  it("renders a dash, not a number, when the adapter reports unavailable", async () => {
    mockFetchBalance.mockResolvedValue(
      balanceBody({ kind: "unavailable", note: "schema drift: KeyError: 'data'" }),
    );
    // showUsage off so the only dollar figure that could appear is a balance.
    render(<ModelUsagePicker value={null} onChange={() => {}} showBalance showUsage={false} />);
    await userEvent.click(screen.getAllByRole("button")[0]);
    await waitFor(() => expect(mockFetchBalance).toHaveBeenCalled());
    await waitFor(() => {
      expect(document.body.textContent || "").toContain("DeepSeek V4 Pro");
      expect(document.querySelector("[data-balance-kind]")).toBeNull();
      expect(document.body.textContent || "").not.toContain("$");
    });
  });
});

describe("ModelUsagePicker includeDefault", () => {
  it("renders the default row and calls onChange('') when chosen", async () => {
    const onChange = vi.fn();
    render(<ModelUsagePicker value={null} onChange={onChange} includeDefault />);
    const container = screen.getByRole("button").parentElement as HTMLElement;
    await waitFor(() => expect(mockFetchUserModels).toHaveBeenCalled());
    await userEvent.click(within(container).getByRole("button"));
    await waitFor(() => {
      expect(document.body.textContent || "").toContain("Default (house route)");
    });
    const defaultRow = Array.from(document.querySelectorAll("button")).find(
      (b) => (b.textContent || "").includes("Default (house route)"),
    );
    expect(defaultRow).toBeTruthy();
    await userEvent.click(defaultRow as HTMLElement);
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("omits the default row when includeDefault is false", async () => {
    render(<ModelUsagePicker value={null} onChange={() => {}} />);
    const container = screen.getByRole("button").parentElement as HTMLElement;
    await waitFor(() => expect(mockFetchUserModels).toHaveBeenCalled());
    await userEvent.click(within(container).getByRole("button"));
    await waitFor(() => {
      expect(document.body.textContent || "").toContain("DeepSeek V4 Pro");
    });
    expect(document.body.textContent || "").not.toContain("Default (house route)");
  });
});

describe("ModelUsagePicker one key, many variants", () => {
  const twoVariantKey = {
    models: [
      {
        ...sampleModels.models[0],
        id: "um-multi",
        model_id: "deepseek-reasoner",
        model_ids: ["deepseek-reasoner", "deepseek-chat"],
        display_name: "My DeepSeek",
      },
    ],
    count: 1,
    stale_registered: [],
    source: "test",
  };

  it("renders one key row with a variant sub-row per model_id and reports the chosen variant", async () => {
    mockFetchUserModels.mockResolvedValue(twoVariantKey);
    mockFetchUsage.mockResolvedValue({
      keys: [{ ...sampleUsage.keys[0], api_key_id: "um-multi" }],
      count: 1,
    });
    mockFetchBalance.mockResolvedValue(
      balanceBody({ api_key_id: "um-multi", kind: "balance_native", balance_usd: 42.5 }),
    );
    const onChange = vi.fn();
    render(<ModelUsagePicker value={null} onChange={onChange} showUsage showBalance />);
    await userEvent.click(screen.getAllByRole("button")[0]);

    const keyRow = await waitFor(() => {
      const el = document.querySelector('[data-key-row="um-multi"]');
      expect(el).toBeTruthy();
      return el as HTMLElement;
    });
    // Two sub-rows, one per variant, under ONE key row.
    const subRows = Array.from(keyRow.querySelectorAll("[data-variant-row]")).map((el) =>
      el.getAttribute("data-variant-row"),
    );
    expect(subRows).toEqual(["deepseek-reasoner", "deepseek-chat"]);
    // The usage bar and the balance chip render ONCE for the key — the
    // ledger is keyed on the record id, not on the variant.
    await waitFor(() => {
      expect(keyRow.querySelectorAll("[data-balance-kind]").length).toBe(1);
    });
    expect((keyRow.textContent || "").match(/\$12\.34/g)?.length).toBe(1);

    const flash = Array.from(document.querySelectorAll("button")).find((b) =>
      (b.textContent || "").includes("deepseek-chat"),
    );
    expect(flash).toBeTruthy();
    await userEvent.click(flash as HTMLElement);
    expect(onChange).toHaveBeenCalledWith("um-multi", "deepseek-chat");
  });

  it("names the chosen non-primary variant on the trigger", async () => {
    mockFetchUserModels.mockResolvedValue(twoVariantKey);
    render(
      <ModelUsagePicker value="um-multi" valueModelId="deepseek-chat" onChange={() => {}} />,
    );
    await waitFor(() => {
      expect(screen.getAllByRole("button")[0].textContent).toContain("My DeepSeek · deepseek-chat");
    });
  });

  it("keeps a single-variant key flat and reports its primary model_id", async () => {
    const onChange = vi.fn();
    render(<ModelUsagePicker value={null} onChange={onChange} />);
    await userEvent.click(screen.getAllByRole("button")[0]);
    await waitFor(() => {
      expect(document.body.textContent || "").toContain("DeepSeek V4 Pro");
    });
    expect(document.querySelector("[data-key-row]")).toBeNull();
    await userEvent.click(screen.getByText("DeepSeek V4 Pro"));
    expect(onChange).toHaveBeenCalledWith("um-1", "deepseek-chat");
  });
});

describe("ModelUsagePicker variant grouping", () => {
  it("groups same-provider registrations under one header with display-name variants", async () => {
    render(<ModelUsagePicker value={null} onChange={() => {}} />);
    const container = screen.getByRole("button").parentElement as HTMLElement;
    await waitFor(() => expect(mockFetchUserModels).toHaveBeenCalled());
    await userEvent.click(within(container).getByRole("button"));
    const text = await waitFor(() => {
      const t = document.body.textContent || "";
      expect(t).toContain("deepseek"); // group header
      return t;
    });
    expect(text).toContain("DeepSeek V4 Pro"); // variant 1
    expect(text).toContain("DeepSeek V4 Flash"); // variant 2
  });
});
