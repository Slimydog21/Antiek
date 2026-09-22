import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ToolConnectionsPanel from "./ToolConnectionsPanel";
import {
  fetchToolConnections,
  removeToolConnection,
  saveToolConnection,
  type ToolConnection,
} from "../../api/toolConnections";

const SECRET = "AIza-secret-never-render";

const rows: ToolConnection[] = [
  {
    vendor: "youtube",
    display_name: "YouTube Data API",
    credential_kind: "api_key",
    auth: "api_key_query",
    docs_url: "https://example.test/youtube",
    status: "configured_unverified",
    credential_present: true,
    status_note: null,
    quota: {
      kind: "youtube_units",
      remaining: 9900,
      limit: 10000,
      reset_at: "2026-08-13T00:00:00-07:00",
      hard_exhausted: false,
      note: "Local Antiek meter",
      estimated_cost_usd: null,
      cost_note: null,
    },
  },
  {
    vendor: "polygon",
    display_name: "Polygon.io",
    credential_kind: "api_key",
    auth: "api_key_query",
    docs_url: "https://example.test/polygon",
    status: "unconfigured",
    credential_present: false,
    status_note: null,
    quota: {
      kind: "unavailable",
      remaining: null,
      limit: null,
      reset_at: null,
      hard_exhausted: null,
      note: "Provider quota is not available to Antiek",
      estimated_cost_usd: null,
      cost_note: null,
    },
  },
  {
    vendor: "fmp",
    display_name: "Financial Modeling Prep",
    credential_kind: "api_key",
    auth: "api_key_query",
    docs_url: "https://example.test/fmp",
    status: "degraded",
    credential_present: false,
    status_note: "Stored credential metadata is unavailable",
    quota: {
      kind: "unavailable",
      remaining: null,
      limit: null,
      reset_at: null,
      hard_exhausted: null,
      note: "Provider quota is not available to Antiek",
      estimated_cost_usd: null,
      cost_note: null,
    },
  },
  {
    vendor: "edgar",
    display_name: "SEC EDGAR",
    credential_kind: "contact",
    auth: "none",
    docs_url: "https://example.test/edgar",
    status: "unconfigured",
    credential_present: false,
    status_note: null,
    quota: {
      kind: "rate_ceiling",
      remaining: null,
      limit: 8,
      reset_at: null,
      hard_exhausted: null,
      note: "Local ceiling: 8 requests per second",
      estimated_cost_usd: null,
      cost_note: null,
    },
  },
  {
    vendor: "x",
    display_name: "X Developer API",
    credential_kind: "api_key",
    auth: "bearer_token",
    docs_url: "https://example.test/x",
    status: "configured_unverified",
    credential_present: true,
    status_note: null,
    quota: {
      kind: "rate_ceiling",
      remaining: null,
      limit: 25,
      reset_at: null,
      hard_exhausted: null,
      note: "Antiek's own host-global brake across all owners and keys: 25 requests per 15 minutes. It is not a provider allowance.",
      estimated_cost_usd: 0.125,
      cost_note: "X bills pay-per-use credits, not a flat monthly tier: about $0.005 per post returned.",
    },
  },
];

vi.mock("../../api/toolConnections", () => ({
  fetchToolConnections: vi.fn(),
  saveToolConnection: vi.fn(),
  removeToolConnection: vi.fn(),
}));

describe("ToolConnectionsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchToolConnections).mockResolvedValue(rows);
    vi.mocked(saveToolConnection).mockImplementation(async (vendor) => ({
      ...rows.find((row) => row.vendor === vendor)!,
      status: "configured_unverified",
      credential_present: true,
    }));
    vi.mocked(removeToolConnection).mockResolvedValue();
  });
  afterEach(cleanup);

  it("renders honest provider-specific states without secret material", async () => {
    render(<ToolConnectionsPanel />);
    await screen.findByText("YouTube Data API");
    expect(screen.getByText(/9,900 of 10,000 local units remain/)).toBeTruthy();
    expect(screen.getAllByText("Provider quota is not available to Antiek")).toHaveLength(2);
    expect(screen.getByText("Local ceiling: 8 requests per second")).toBeTruthy();
    expect(screen.getByText("Needs attention")).toBeTruthy();
    expect(document.body.textContent).not.toContain(SECRET);
  });

  it("submits and immediately clears a write-only password", async () => {
    const user = userEvent.setup();
    render(<ToolConnectionsPanel />);
    const youtube = (await screen.findByText("YouTube Data API")).closest("li")!;
    await user.click(within(youtube).getByRole("button", { name: "Replace" }));
    const input = within(youtube).getByLabelText("API key (write-only)") as HTMLInputElement;
    expect(input.type).toBe("password");
    await user.type(input, SECRET);
    await user.click(within(youtube).getByRole("button", { name: "Save connection" }));
    expect(input.value).toBe("");
    await waitFor(() => expect(saveToolConnection).toHaveBeenCalledWith("youtube", SECRET));
    expect(document.body.textContent).not.toContain(SECRET);
  });

  it("clears the credential even when saving fails", async () => {
    vi.mocked(saveToolConnection).mockRejectedValueOnce(new Error("Tool settings API 503"));
    const user = userEvent.setup();
    render(<ToolConnectionsPanel />);
    const polygon = (await screen.findByText("Polygon.io")).closest("li")!;
    await user.click(within(polygon).getByRole("button", { name: "Connect" }));
    const input = within(polygon).getByLabelText("API key (write-only)") as HTMLInputElement;
    await user.type(input, SECRET);
    await user.click(within(polygon).getByRole("button", { name: "Save connection" }));
    expect(input.value).toBe("");
    await screen.findByText("Tool settings API 503");
    expect(document.body.textContent).not.toContain(SECRET);
  });

  it("uses an email field rather than an API-key field for EDGAR", async () => {
    const user = userEvent.setup();
    render(<ToolConnectionsPanel />);
    const edgar = (await screen.findByText("SEC EDGAR")).closest("li")!;
    await user.click(within(edgar).getByRole("button", { name: "Connect" }));
    const input = within(edgar).getByLabelText("SEC contact email (write-only)") as HTMLInputElement;
    expect(input.type).toBe("email");
    expect(within(edgar).queryByLabelText("API key (write-only)")).toBeNull();
  });

  it("requires an explicit named disconnect confirmation", async () => {
    const user = userEvent.setup();
    render(<ToolConnectionsPanel />);
    const youtube = (await screen.findByText("YouTube Data API")).closest("li")!;
    await user.click(within(youtube).getByRole("button", { name: "Disconnect" }));
    const dialog = within(youtube).getByRole("alertdialog", { name: "Disconnect YouTube Data API?" });
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBe(document.activeElement);
    await user.click(within(dialog).getByRole("button", { name: "Disconnect" }));
    await waitFor(() => expect(removeToolConnection).toHaveBeenCalledWith("youtube"));
  });

  it("clears an open credential when another provider action starts", async () => {
    const user = userEvent.setup();
    render(<ToolConnectionsPanel />);
    const polygon = (await screen.findByText("Polygon.io")).closest("li")!;
    const youtube = screen.getByText("YouTube Data API").closest("li")!;
    await user.click(within(polygon).getByRole("button", { name: "Connect" }));
    await user.type(within(polygon).getByLabelText("API key (write-only)"), SECRET);
    await user.click(within(youtube).getByRole("button", { name: "Disconnect" }));
    expect(within(polygon).queryByLabelText("API key (write-only)")).toBeNull();
    expect(document.body.textContent).not.toContain(SECRET);
  });

  it("returns focus when edit or disconnect actions are cancelled", async () => {
    const user = userEvent.setup();
    render(<ToolConnectionsPanel />);
    const youtube = (await screen.findByText("YouTube Data API")).closest("li")!;
    const replace = within(youtube).getByRole("button", { name: "Replace" });
    await user.click(replace);
    expect(within(youtube).getByLabelText("API key (write-only)")).toBe(document.activeElement);
    await user.click(within(youtube).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(replace).toBe(document.activeElement));

    const disconnect = within(youtube).getByRole("button", { name: "Disconnect" });
    await user.click(disconnect);
    const dialog = within(youtube).getByRole("alertdialog");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(disconnect).toBe(document.activeElement));
    expect(within(youtube).queryByRole("alertdialog")).toBeNull();
    expect(dialog.isConnected).toBe(false);
  });

  it("traps tab focus inside the disconnect alertdialog", async () => {
    const user = userEvent.setup();
    render(<ToolConnectionsPanel />);
    const youtube = (await screen.findByText("YouTube Data API")).closest("li")!;
    await user.click(within(youtube).getByRole("button", { name: "Disconnect" }));
    const dialog = within(youtube).getByRole("alertdialog");
    const cancel = within(dialog).getByRole("button", { name: "Cancel" });
    const confirm = within(dialog).getByRole("button", { name: "Disconnect" });
    expect(cancel).toBe(document.activeElement);
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(confirm).toBe(document.activeElement);
    await user.keyboard("{Tab}");
    expect(cancel).toBe(document.activeElement);
  });

  it("keeps an optimistic disconnected state when refresh fails", async () => {
    const user = userEvent.setup();
    render(<ToolConnectionsPanel />);
    const youtube = (await screen.findByText("YouTube Data API")).closest("li")!;
    vi.mocked(fetchToolConnections).mockRejectedValueOnce(new Error("Tool settings API 503"));
    await user.click(within(youtube).getByRole("button", { name: "Disconnect" }));
    await user.click(within(within(youtube).getByRole("alertdialog")).getByRole("button", { name: "Disconnect" }));
    await within(youtube).findByText(/disconnected, but current tool status could not be refreshed/i);
    expect(within(youtube).getByRole("button", { name: "Connect" })).toBeTruthy();
    expect(within(youtube).getByText("Not configured")).toBeTruthy();
  });

  it("locks other provider actions while a save is pending", async () => {
    let resolveSave!: (value: ToolConnection) => void;
    vi.mocked(saveToolConnection).mockReturnValueOnce(new Promise((resolve) => {
      resolveSave = resolve;
    }));
    const user = userEvent.setup();
    render(<ToolConnectionsPanel />);
    const youtube = (await screen.findByText("YouTube Data API")).closest("li")!;
    const polygon = screen.getByText("Polygon.io").closest("li")!;
    await user.click(within(youtube).getByRole("button", { name: "Replace" }));
    await user.type(within(youtube).getByLabelText("API key (write-only)"), SECRET);
    await user.click(within(youtube).getByRole("button", { name: "Save connection" }));
    expect(within(polygon).getByRole("button", { name: "Connect" }).hasAttribute("disabled")).toBe(true);
    resolveSave({ ...rows[0], credential_present: true });
    await waitFor(() => expect(within(polygon).getByRole("button", { name: "Connect" }).hasAttribute("disabled")).toBe(false));
  });

  it("uses form validation for EDGAR and supports Enter submission", async () => {
    const user = userEvent.setup();
    render(<ToolConnectionsPanel />);
    const edgar = (await screen.findByText("SEC EDGAR")).closest("li")!;
    await user.click(within(edgar).getByRole("button", { name: "Connect" }));
    const input = within(edgar).getByLabelText("SEC contact email (write-only)") as HTMLInputElement;
    await user.type(input, "not-an-email{Enter}");
    expect(saveToolConnection).not.toHaveBeenCalled();
    await user.clear(input);
    await user.type(input, "research@example.com{Enter}");
    await waitFor(() => expect(saveToolConnection).toHaveBeenCalledWith("edgar", "research@example.com"));
  });

  it("announces hard quota exhaustion and its reset", async () => {
    vi.mocked(fetchToolConnections).mockResolvedValueOnce(rows.map((row) => row.vendor === "youtube" ? {
      ...row,
      quota: { ...row.quota, remaining: 0, hard_exhausted: true },
    } : row));
    render(<ToolConnectionsPanel />);
    await screen.findByText("Quota exhausted");
    expect(screen.getByText(/Local quota exhausted · resets/)).toBeTruthy();
    expect(screen.getByRole("meter", { name: "YouTube local quota remaining" }).getAttribute("value")).toBe("0");
  });

  it("shows what a pay-per-use provider costs rather than only its ceiling", async () => {
    render(<ToolConnectionsPanel />);
    const x = (await screen.findByText("X Developer API")).closest("li")!;
    // The dollar figure, composed from the sourced per-post rate.
    expect(within(x).getByText(/Costs you up to \$0\.125 per full-size search/)).toBeTruthy();
    // And its provenance, so the number is never shown bare.
    expect(within(x).getByText(/pay-per-use credits, not a flat monthly tier/)).toBeTruthy();
    // A vendor with no sourced rate says nothing rather than guessing.
    const youtube = screen.getByText("YouTube Data API").closest("li")!;
    expect(within(youtube).queryByText(/Costs you up to/)).toBeNull();
  });

  it("uses full-width 44px controls at the mobile breakpoint", async () => {
    render(<ToolConnectionsPanel />);
    const polygon = (await screen.findByText("Polygon.io")).closest("li")!;
    const connect = within(polygon).getByRole("button", { name: "Connect" });
    expect(connect.className).toContain("h-11");
    expect(connect.className).toContain("w-full");
    expect(connect.className).toContain("sm:h-9");
  });
});
