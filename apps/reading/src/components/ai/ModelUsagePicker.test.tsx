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
    kind: "spend_history",
    balance_usd: 12.34,
    held_cents: 0,
    available_cents: 3766,
  });
});

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
    expect(onChange).toHaveBeenCalledWith("um-1");
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
