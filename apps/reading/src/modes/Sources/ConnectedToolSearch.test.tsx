import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { inventory, search } = vi.hoisted(() => ({ inventory: vi.fn(), search: vi.fn() }));
vi.mock("../../api/toolConnections", () => ({ fetchToolConnections: inventory }));
vi.mock("../../api/researchToolSearch", () => ({ searchResearchTool: search }));
import ConnectedToolSearch from "./ConnectedToolSearch";

describe("ConnectedToolSearch", () => {
  beforeEach(() => {
    inventory.mockReset(); search.mockReset();
    inventory.mockResolvedValue([{ vendor: "x", credential_present: true, status: "configured_unverified" }]);
    vi.stubGlobal("crypto", { randomUUID: () => "12345678-1234-1234-1234-123456789abc" });
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("labels results as candidates and never offers implicit ingestion", async () => {
    search.mockResolvedValue({ operation_id: "tool-search-12345678-1234-1234-1234-123456789abc", vendor: "x", status: "completed", candidates: [{
      external_id: "1", title_or_text: "A source", url: "https://x.com/a/status/1", published_at: null, author: "a",
    }] });
    render(<ConnectedToolSearch />);
    await screen.findByRole("option", { name: "X" });
    fireEvent.change(screen.getByLabelText("What sources are you looking for?"), { target: { value: "battery" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("Candidate · not ingested")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /ingest/i })).toBeNull();
    expect(search).toHaveBeenCalledWith(expect.objectContaining({ vendor: "x", query: "battery" }));
  });

  it("keeps the connected-tools recovery path visible", async () => {
    inventory.mockResolvedValue([]);
    render(<ConnectedToolSearch />);
    expect(await screen.findByText("Connect YouTube or X in Settings to search with your own account.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Manage tools" }).getAttribute("href")).toBe("/settings");
  });

  it("announces inventory failure and retries", async () => {
    inventory.mockRejectedValueOnce(new Error("SECRET")).mockResolvedValueOnce([]);
    render(<ConnectedToolSearch />);
    expect((await screen.findByRole("alert")).textContent).toContain("Tool inventory is unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(inventory).toHaveBeenCalledTimes(2));
  });

  it("shows a useful empty result state", async () => {
    search.mockResolvedValue({ operation_id: "tool-search-12345678-1234-1234-1234-123456789abc", vendor: "x", status: "completed", candidates: [] });
    render(<ConnectedToolSearch />);
    await screen.findByRole("option", { name: "X" });
    fireEvent.change(screen.getByLabelText("What sources are you looking for?"), { target: { value: "rare topic" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("No candidates yet. Try a more specific query or another connected provider.")).toBeTruthy();
  });

  it("reuses the exact authority after response loss", async () => {
    search.mockRejectedValueOnce(new TypeError("network lost")).mockResolvedValueOnce({
      operation_id: "tool-search-12345678-1234-1234-1234-123456789abc", vendor: "x", status: "replayed", candidates: [],
    });
    render(<ConnectedToolSearch />);
    await screen.findByRole("option", { name: "X" });
    fireEvent.change(screen.getByLabelText("What sources are you looking for?"), { target: { value: "battery" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(search).toHaveBeenCalledTimes(2));
    expect(search.mock.calls[0][0].operationId).toBe(search.mock.calls[1][0].operationId);
  });
});
