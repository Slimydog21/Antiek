/**
 * PersonalSpace.test.tsx — Read SPR-13 M1/M2/M3/M4.
 *
 *  M1 — created deliverables + saved reads listed; each opens back into the
 *       reader/meta-doc view; ZERO assets → an empty state guides (no crash).
 *  M2 — system-named categories render with section headings; the ordering
 *       label SAYS theme vs recency (honest fallback shown, never faked).
 *  M3 — a related doc surfaces a suggestion naming the matched project; ACCEPT
 *       files it (the explicit mutator fires once); DECLINE leaves it (the
 *       mutator NEVER fires without a click — the no-auto-ship invariant).
 *  M4 — metaDocsOnly filters to created deliverables, distinguished from books.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type {
  CategorizedSpaceResponse,
  PersonalSpaceResponse,
} from "../../../api/books";
import PersonalSpace from "./index";

const {
  listMock,
  categoriesMock,
  suggestionMock,
  navigateMock,
  acceptFilingMock,
} = vi.hoisted(() => ({
  listMock: vi.fn(),
  categoriesMock: vi.fn(),
  suggestionMock: vi.fn(),
  navigateMock: vi.fn(),
  acceptFilingMock: vi.fn(),
}));

vi.mock("../../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../../api/books")>();
  return {
    ...actual,
    listPersonalSpace: listMock,
    listPersonalSpaceCategories: categoriesMock,
    getFileSuggestion: suggestionMock,
  };
});

vi.mock("../../../lib/researchSuggestion", async (orig) => {
  const actual = await orig<typeof import("../../../lib/researchSuggestion")>();
  // Keep the REAL suggestFiling (pure); stub only acceptFiling (the explicit
  // mutator) so the test proves it is NEVER called without a click.
  return { ...actual, acceptFiling: acceptFilingMock };
});

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const space = (over: Partial<PersonalSpaceResponse> = {}): PersonalSpaceResponse => ({
  assets: [
    {
      asset_id: "a1",
      kind: "meta_reading",
      title: "How my books treat free will",
      prompt: "free will across my reading",
      document_ids: ["doc-1"],
      emitted_at: "2026-05-05T00:00:00Z",
      open_route: "/read/meta-reading/a1",
    },
    {
      asset_id: "read:doc-2",
      kind: "saved_read",
      title: "Meditations",
      prompt: null,
      document_ids: ["doc-2"],
      emitted_at: "2026-05-04T00:00:00Z",
      open_route: "/read/doc-2",
    },
  ],
  count: 2,
  ...over,
});

const cats = (over: Partial<CategorizedSpaceResponse> = {}): CategorizedSpaceResponse => ({
  categories: [
    { category_id: "cat:a1", label: "free · will", asset_ids: ["a1"], ordering: "theme" },
    { category_id: "cat:read:doc-2", label: "stoicism", asset_ids: ["read:doc-2"], ordering: "theme" },
  ],
  ordering: "theme",
  stability_bound: 4,
  ...over,
});

beforeEach(() => {
  listMock.mockResolvedValue(space());
  categoriesMock.mockResolvedValue(cats());
  // No suggestion by default (most rows show none).
  suggestionMock.mockResolvedValue({ document_id: "doc-1", matches: [] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("M1 — list + open + empty", () => {
  it("lists created deliverables and saved reads", async () => {
    render(<PersonalSpace />);
    expect(await screen.findByText("How my books treat free will")).toBeTruthy();
    expect(screen.getByText("Meditations")).toBeTruthy();
    // Living-TV densify: session brand chrome on personal bed surface.
    expect(screen.getByTestId("personal-space-werner-brand")).toBeTruthy();
    const livingTv = screen.getByTestId(
      "personal-space-living-tv-art",
    ) as HTMLImageElement;
    expect(livingTv.getAttribute("src") ?? "").toMatch(
      /werner_living_tv_session_v1/,
    );
  });

  it("opens an asset back into its reader/meta-doc route", async () => {
    render(<PersonalSpace />);
    const opener = (await screen.findAllByTestId("personal-asset-open"))[0];
    fireEvent.click(opener);
    expect(navigateMock).toHaveBeenCalledWith("/read/meta-reading/a1");
  });

  it("shows a guiding empty state with zero assets (no crash, no phantom)", async () => {
    listMock.mockResolvedValue({ assets: [], count: 0 });
    categoriesMock.mockResolvedValue({ categories: [], ordering: "recency", stability_bound: 4 });
    render(<PersonalSpace />);
    expect(await screen.findByTestId("personal-space-empty")).toBeTruthy();
    expect(screen.queryByTestId("personal-space-category")).toBeNull();
  });
});

describe("M2 — system categories + honest ordering label", () => {
  it("renders system-named category sections", async () => {
    render(<PersonalSpace />);
    await screen.findByText("How my books treat free will");
    const sections = screen.getAllByTestId("personal-space-category");
    expect(sections.length).toBe(2);
    expect(screen.getByText("free · will")).toBeTruthy();
    expect(screen.getByText("stoicism")).toBeTruthy();
  });

  it("renders two categories that share a label (keyed by category_id, not label)", async () => {
    // Regression: two distinct clusters can carry the same human label; the
    // section must key on the unique category_id so neither is dropped/merged.
    categoriesMock.mockResolvedValue({
      categories: [
        { category_id: "cat:a1", label: "free · will", asset_ids: ["a1"], ordering: "theme" },
        { category_id: "cat:read:doc-2", label: "free · will", asset_ids: ["read:doc-2"], ordering: "theme" },
      ],
      ordering: "theme",
      stability_bound: 4,
    });
    render(<PersonalSpace />);
    await screen.findByText("How my books treat free will");
    // Both same-labelled sections survive, each with its own asset.
    expect(screen.getAllByTestId("personal-space-category").length).toBe(2);
    expect(screen.getByText("Meditations")).toBeTruthy();
  });

  it("SAYS recency when the corpus is below the stability bound (honest fallback)", async () => {
    categoriesMock.mockResolvedValue({
      categories: [{ category_id: "recency", label: "Recently read & created", asset_ids: ["a1", "read:doc-2"], ordering: "recency" }],
      ordering: "recency",
      stability_bound: 4,
    });
    render(<PersonalSpace />);
    const label = await screen.findByTestId("personal-space-ordering");
    expect(label.textContent).toMatch(/recency/i);
    expect(label.textContent).toMatch(/4\+/);
  });
});

describe("M3 — suggest-not-autoship filing", () => {
  it("surfaces a suggestion naming the matched project; accept files it once", async () => {
    suggestionMock.mockImplementation(async (docId: string) =>
      docId === "doc-1"
        ? { document_id: docId, matches: [{ investigation_id: "inv-x", question: "free will and determinism", score: 0.7 }] }
        : { document_id: docId, matches: [] },
    );
    acceptFilingMock.mockResolvedValue({ investigation_id: "inv-x" });
    render(<PersonalSpace />);

    const sugg = await screen.findByTestId("personal-asset-suggestion");
    expect(sugg.textContent).toMatch(/free will and determinism/);
    // Until the user clicks, the mutator NEVER fires (no auto-ship).
    expect(acceptFilingMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /File into/ }));
    await waitFor(() => expect(acceptFilingMock).toHaveBeenCalledTimes(1));
    expect(acceptFilingMock.mock.calls[0][0]).toMatchObject({
      documentId: "doc-1",
      investigationId: "inv-x",
    });
    expect(await screen.findByTestId("personal-asset-filed")).toBeTruthy();
  });

  it("decline leaves it — dismissing never fires the mutator", async () => {
    suggestionMock.mockImplementation(async (docId: string) =>
      docId === "doc-1"
        ? { document_id: docId, matches: [{ investigation_id: "inv-x", question: "free will", score: 0.7 }] }
        : { document_id: docId, matches: [] },
    );
    render(<PersonalSpace />);
    await screen.findByTestId("personal-asset-suggestion");
    fireEvent.click(screen.getByTestId("personal-asset-decline"));
    await waitFor(() =>
      expect(screen.queryByTestId("personal-asset-suggestion")).toBeNull(),
    );
    // Declining files NOTHING.
    expect(acceptFilingMock).not.toHaveBeenCalled();
  });
});

describe("M4 — meta-docs tab", () => {
  it("filters to created deliverables only, distinguished from source books", async () => {
    render(<PersonalSpace metaDocsOnly />);
    expect(await screen.findByText("How my books treat free will")).toBeTruthy();
    // The source-book read is NOT in the meta-docs tab.
    expect(screen.queryByText("Meditations")).toBeNull();
    // The created-asset tag distinguishes it (the M4 visible distinction).
    expect(screen.getByText("reading")).toBeTruthy();
  });
});
