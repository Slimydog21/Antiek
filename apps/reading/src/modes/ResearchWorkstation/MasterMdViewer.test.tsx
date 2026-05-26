/**
 * MasterMdViewer.test.tsx — the named-source synthesis read (SPR-04 M1).
 *
 * Pins the gates:
 *   - claim support renders as a NAMED source ("from <Title>, p.12")
 *     resolved through the provenance chain — never "[N chunks]" or a raw
 *     chunk id;
 *   - many chunks of ONE document collapse to ONE named source (the
 *     chunk→source translation, not "[3 chunks]");
 *   - a RESTRICTED source (servable=false) is NOT opened: it shows the
 *     honest "not available to open" state and never the body (§9.0);
 *   - a claim whose chunks all fail to resolve shows an honest
 *     "source unavailable", never a fabricated title (rigor #1).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

import type { ChunkResponse } from "../../lib/api";
import type { ParsedSynthesis } from "../../lib/synthesisParser";

const { getChunkMock } = vi.hoisted(() => ({ getChunkMock: vi.fn() }));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, getChunk: getChunkMock };
});
// Workspace actions + toast are side-effectful; stub them so the render is
// pure. We assert on what the reader SEES, not on panel side effects.
vi.mock("../../workspace/actions", () => ({
  openNotebook: vi.fn(),
  openPdfPanel: vi.fn(),
}));
vi.mock("../../components/lemon/LemonToast", () => ({
  toast: { ok: vi.fn(), err: vi.fn() },
}));

import MasterMdViewer from "./MasterMdViewer";

afterEach(() => {
  cleanup();
  getChunkMock.mockReset();
});

function chunk(over: Partial<ChunkResponse>): ChunkResponse {
  return {
    chunk_id: "c",
    text: "body",
    section_path: "p.12",
    token_count: 10,
    document_id: "doc-1",
    document_title: "On Growth and Form",
    source_tier: 2,
    servable: true,
    servability: null,
    ...over,
  };
}

function synth(over: Partial<ParsedSynthesis> = {}): ParsedSynthesis {
  return {
    thesisSummary: "A thesis.",
    components: [
      {
        index: 1,
        claim: "The claim holds.",
        confidence: "high",
        effectiveSourceTier: 2,
        hedgingRequired: false,
        chunkIds: ["c1"],
        supportingPathIndices: [],
      },
    ],
    falsificationConditions: [],
    executionRisks: [],
    recommendation: "proceed",
    hardConstraintsSatisfied: true,
    totalCostUsd: 0.01,
    question: "Why?",
    masterMdPath: null,
    domainsPatched: [],
    chunkCitations: { c1: [1] },
    ...over,
  };
}

describe("MasterMdViewer — named-source read (M1)", () => {
  it("renders the source as a named title + locator, never [N chunks]", async () => {
    getChunkMock.mockResolvedValue(
      chunk({ chunk_id: "c1", document_title: "On Growth and Form", section_path: "p.12" }),
    );
    render(<MasterMdViewer synthesis={synth()} />);
    await waitFor(() =>
      expect(screen.getByText(/On Growth and Form/)).toBeTruthy(),
    );
    expect(screen.getByText(/from On Growth and Form/)).toBeTruthy();
    expect(screen.getByText(/p\.12/)).toBeTruthy();
    // The jargon must be gone.
    expect(screen.queryByText(/\[.*chunk.*\]/i)).toBeNull();
    expect(screen.queryByText("c1")).toBeNull();
  });

  it("collapses many chunks of one document into one named source", async () => {
    getChunkMock.mockImplementation(async (id: string) =>
      chunk({ chunk_id: id, document_id: "doc-1", document_title: "One Paper" }),
    );
    render(
      <MasterMdViewer
        synthesis={synth({
          components: [
            {
              index: 1,
              claim: "Backed by three chunks of one paper.",
              confidence: "high",
              effectiveSourceTier: 2,
              hedgingRequired: false,
              chunkIds: ["c1", "c2", "c3"],
              supportingPathIndices: [],
            },
          ],
          chunkCitations: { c1: [1], c2: [1], c3: [1] },
        })}
      />,
    );
    await waitFor(() =>
      expect(screen.getAllByText(/from One Paper/).length).toBe(1),
    );
  });

  it("does NOT open a restricted source — shows 'not available to open'", async () => {
    getChunkMock.mockResolvedValue(
      chunk({
        chunk_id: "c1",
        document_title: "A Restricted Book",
        text: "", // body withheld by the endpoint
        servable: false,
        servability: "restricted",
      }),
    );
    render(<MasterMdViewer synthesis={synth()} />);
    await waitFor(() =>
      expect(screen.getByText(/A Restricted Book/)).toBeTruthy(),
    );
    expect(screen.getByText(/not available to open/)).toBeTruthy();
    // It is NOT a button (can't be clicked to open). The named source is a
    // plain span in the not-servable branch.
    expect(screen.queryByTitle(/Click to preview/)).toBeNull();
  });

  it("shows 'source unavailable' when no chunk resolves, never a fake title", async () => {
    getChunkMock.mockRejectedValue(new Error("404"));
    render(<MasterMdViewer synthesis={synth()} />);
    await waitFor(() =>
      expect(screen.getByText(/source unavailable/)).toBeTruthy(),
    );
  });

  // ── SPR-10 M1 — the IP-holder dimension ("whose work grounds this") ──

  it("shows 'published by X' when the source has a resolved IP holder", async () => {
    getChunkMock.mockResolvedValue(
      chunk({ chunk_id: "c1", document_title: "On Growth and Form", ip_holder_name: "MIT Press" }),
    );
    render(<MasterMdViewer synthesis={synth()} />);
    await waitFor(() => expect(screen.getByText(/On Growth and Form/)).toBeTruthy());
    expect(screen.getByText(/published by MIT Press/)).toBeTruthy();
  });

  it("invents no owner when ip_holder_name is null (honest unknown)", async () => {
    getChunkMock.mockResolvedValue(
      chunk({ chunk_id: "c1", document_title: "On Growth and Form", ip_holder_name: null }),
    );
    render(<MasterMdViewer synthesis={synth()} />);
    await waitFor(() => expect(screen.getByText(/On Growth and Form/)).toBeTruthy());
    // No fabricated "published by …" when the owner is unknown.
    expect(screen.queryByText(/published by/)).toBeNull();
  });

  it("does NOT expose the owner of a restricted source (§9.0 protected attribution)", async () => {
    // The endpoint withholds ip_holder_name for a non-servable source; the
    // surface must not show "published by …" on the restricted branch.
    getChunkMock.mockResolvedValue(
      chunk({
        chunk_id: "c1",
        document_title: "A Restricted Book",
        text: "",
        servable: false,
        servability: "restricted",
        ip_holder_name: null,
      }),
    );
    render(<MasterMdViewer synthesis={synth()} />);
    await waitFor(() => expect(screen.getByText(/A Restricted Book/)).toBeTruthy());
    expect(screen.getByText(/not available to open/)).toBeTruthy();
    expect(screen.queryByText(/published by/)).toBeNull();
  });
});
