import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { inventory, search, ingest } = vi.hoisted(() => ({ inventory: vi.fn(), search: vi.fn(), ingest: vi.fn() }));
vi.mock("../../api/toolConnections", () => ({ fetchToolConnections: inventory }));
vi.mock("../../api/researchToolSearch", () => ({ searchResearchTool: search, ingestResearchToolCandidate: ingest }));
import ConnectedToolSearch from "./ConnectedToolSearch";

const candidate = { external_id: "1", title_or_text: "A source", url: "https://x.com/a/status/1", published_at: null, author: "a" };
const ingestResult = {
  operation_id: "tool-ingest-12345678-1234-1234-1234-123456789abc",
  vendor: "x",
  external_id: "1",
  status: "completed",
  ingest_status: "ingested",
  document_id: "document-1",
  chunks_written: 2,
  skipped_reason: null,
  title: "A source",
  content_class: "personal_reading",
  source_tier: 4,
};

async function searchForCandidate() {
  search.mockResolvedValue({
    operation_id: "tool-search-12345678-1234-1234-1234-123456789abc", vendor: "x", status: "completed", candidates: [candidate],
  });
  render(<ConnectedToolSearch />);
  await screen.findByRole("option", { name: "X" });
  fireEvent.change(screen.getByLabelText("What sources are you looking for?"), { target: { value: "battery" } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await screen.findByText("Candidate · not ingested");
}

describe("ConnectedToolSearch", () => {
  beforeEach(() => {
    inventory.mockReset(); search.mockReset(); ingest.mockReset();
    inventory.mockResolvedValue([{ vendor: "x", credential_present: true, status: "configured_unverified" }]);
    vi.stubGlobal("crypto", { randomUUID: () => "12345678-1234-1234-1234-123456789abc" });
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("offers an explicit ingest per candidate and calls the route once per operation_id", async () => {
    ingest.mockResolvedValue(ingestResult);
    await searchForCandidate();
    expect(screen.getByText("Candidate · not ingested")).toBeTruthy();
    expect(screen.getByRole("button", { name: /ingest/i })).toBeTruthy();
    expect(ingest).not.toHaveBeenCalled();
    expect(search).toHaveBeenCalledWith(expect.objectContaining({ vendor: "x", query: "battery" }));
    fireEvent.click(screen.getByRole("button", { name: /ingest/i }));
    await waitFor(() => expect(ingest).toHaveBeenCalledTimes(1));
    expect(ingest).toHaveBeenCalledWith({
      operationId: "tool-ingest-12345678-1234-1234-1234-123456789abc", vendor: "x", externalId: "1",
    });
    expect(await screen.findByText("Ingested · personal reading")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /ingest/i })).toBeNull();
  });

  it("retries a failed ingest with the same operation_id", async () => {
    ingest.mockRejectedValueOnce(new Error("This ingest has an unresolved outcome. Check your library before trying again."))
      .mockResolvedValueOnce({ ...ingestResult, status: "replayed" });
    await searchForCandidate();
    fireEvent.click(screen.getByRole("button", { name: /ingest/i }));
    expect((await screen.findByRole("alert")).textContent).toContain("This ingest has an unresolved outcome");
    fireEvent.click(screen.getByRole("button", { name: /ingest/i }));
    await screen.findByText("Ingested · personal reading");
    expect(ingest).toHaveBeenCalledTimes(2);
    expect(ingest.mock.calls[0][0].operationId).toBe(ingest.mock.calls[1][0].operationId);
  });

  it("shows why a skipped ingest wrote nothing", async () => {
    ingest.mockResolvedValue({ ...ingestResult, ingest_status: "skipped", chunks_written: 0, skipped_reason: "no_transcript" });
    await searchForCandidate();
    fireEvent.click(screen.getByRole("button", { name: /ingest/i }));
    expect(await screen.findByText("Not ingested · no captions available")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /ingest/i })).toBeNull();
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
