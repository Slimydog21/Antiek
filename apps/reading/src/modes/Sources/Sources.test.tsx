import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { apiFetchMock, ingestSourceMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  ingestSourceMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    apiFetch: apiFetchMock,
    ingestSource: ingestSourceMock,
  };
});

import Sources from "./index";

const okJson = (body: unknown) =>
  ({
    ok: true,
    json: async () => body,
  }) as Response;

beforeEach(() => {
  apiFetchMock.mockReset();
  ingestSourceMock.mockReset();
  apiFetchMock.mockResolvedValue(
    okJson({
      source_path: " reports/source_census.json ",
      state: " blocked ",
      reference_source: " arxiv ",
      source_count: "2",
      blocked_count: "1",
      rows: [
        {
          source: " web ",
          blocked: true,
          failures: [" metadata_complete_pct=94.0 < 95.0 "],
        },
        {
          source: " ",
          blocked: true,
          failures: ["leak"],
        },
      ],
      error: " ",
    }),
  );
});

afterEach(() => cleanup());

describe("Sources", () => {
  it("loads and sanitizes source-gate status for acquisition", async () => {
    render(<Sources />);

    expect(apiFetchMock).toHaveBeenCalledWith("/coordination/source-gate");
    expect(await screen.findByText("Source gate blocked · 1/2 blocked")).toBeTruthy();
    expect(
      screen.getByText("Reference: arxiv. Source: reports/source_census.json."),
    ).toBeTruthy();
    expect(screen.getByText("web: metadata_complete_pct=94.0 < 95.0")).toBeTruthy();
    expect(document.body.textContent).not.toContain("leak");
  });

  it("keeps ingestion wired through POST /sources/ingest", async () => {
    ingestSourceMock.mockResolvedValue({
      status: "ingested",
      detected_kind: "arxiv",
      document_id: "doc-1",
      title: "A Paper",
      chunks_written: 4,
      episodes_processed: 0,
      episodes_ingested: 0,
      document_loaded_event_id: "evt-1",
      skipped_reason: null,
      error_message: null,
    });

    render(<Sources />);
    fireEvent.change(screen.getByLabelText("URLs (one per line)"), {
      target: { value: "https://arxiv.org/abs/2401.00001" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ingest" }));

    await waitFor(() => expect(screen.getByText("A Paper")).toBeTruthy());
    expect(ingestSourceMock).toHaveBeenCalledWith({
      url: "https://arxiv.org/abs/2401.00001",
      kind: undefined,
      investigation_id: "__operator__",
      max_episodes: 10,
    });
    expect(screen.getByText("4 chunks")).toBeTruthy();
  });

  it("shows an honest source-gate load failure without disabling ingest", async () => {
    apiFetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      text: async () => "down",
    } as Response);
    ingestSourceMock.mockResolvedValue({
      status: "skipped",
      detected_kind: "url",
      document_id: null,
      title: null,
      chunks_written: 0,
      episodes_processed: 0,
      episodes_ingested: 0,
      document_loaded_event_id: null,
      skipped_reason: "already exists",
      error_message: null,
    });

    render(<Sources />);
    expect(await screen.findByText("Source gate unavailable")).toBeTruthy();
    expect(
      screen.getByText("GET /coordination/source-gate failed: HTTP 503"),
    ).toBeTruthy();

    fireEvent.change(screen.getByLabelText("URLs (one per line)"), {
      target: { value: "https://example.test/article" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ingest" }));

    await waitFor(() => expect(screen.getByText("skipped")).toBeTruthy());
    expect(ingestSourceMock).toHaveBeenCalledTimes(1);
  });
});
