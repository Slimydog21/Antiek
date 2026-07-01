/**
 * MetaReading.test.tsx — Read SPR-08 M4 (+ M3 narrate scope).
 *
 * The one-shot READ-ONLY cited report over the owned corpus: it renders behind
 * the "proposed (sign-off pending)" banner; citations OPEN the SPR-07 reader
 * (seeding the usePosition locator, no fake page for an unresolved cite); the
 * promote-into-Research suggestion APPEARS but NEVER auto-fires (the user must
 * click); a truncated synthesis is labelled; and a minute-boxed asset hands its
 * minutes to the narrate control (M3 scope wiring).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { BookCitation, MetaReadingResponse, SavedMetaReading } from "../../../api/books";
import MetaReading from "./index";

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
};

const { generateMock, getSavedMetaReadingMock, navigateMock, acceptPromotionMock } = vi.hoisted(() => ({
  generateMock: vi.fn(),
  getSavedMetaReadingMock: vi.fn(),
  navigateMock: vi.fn(),
  acceptPromotionMock: vi.fn(),
}));

vi.mock("../../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../../api/books")>();
  return {
    ...actual,
    generateMetaReading: generateMock,
    getSavedMetaReading: getSavedMetaReadingMock,
  };
});

vi.mock("../../../lib/researchSuggestion", async (orig) => {
  const actual = await orig<typeof import("../../../lib/researchSuggestion")>();
  // Keep the REAL suggestPromotion (pure); stub only acceptPromotion (the
  // explicit mutation) so the test can prove it is NEVER called without a click.
  return { ...actual, acceptPromotion: acceptPromotionMock };
});

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("../../../components/voice/ReadAloud", () => ({
  default: ({ text, minutes }: { text: string; minutes?: number }) => (
    <button type="button" data-testid="read-aloud" data-text={text} data-minutes={minutes ?? ""}>
      Narrate
    </button>
  ),
}));

const cite = (over: Partial<BookCitation> = {}): BookCitation => ({
  chunk_id: "c1",
  document_id: "doc-mr",
  page_index: 11,
  page_resolved: true,
  snippet: "a cited passage",
  ...over,
});

function deliverable(over: Partial<MetaReadingResponse> = {}): MetaReadingResponse {
  return {
    asset_id: "mr-abc123",
    report: "A synthesis of your books on free will.",
    citations: [cite()],
    length_unit: "pages",
    length_amount: 3,
    word_budget: 900,
    truncated: false,
    corpus_scope: "hard",
    corpus_document_ids: ["doc-mr"],
    empty: false,
    context_chunk_count: 4,
    ...over,
  };
}

function savedMetaReading(over: Partial<SavedMetaReading> = {}): SavedMetaReading {
  return {
    asset_id: "mr-saved",
    prompt: "saved free will prompt",
    report: "A saved synthesis of your books.",
    citations: [cite()],
    length_unit: "minutes",
    length_amount: 8,
    truncated: false,
    corpus_scope: "hard",
    corpus_document_ids: ["doc-mr"],
    ...over,
  };
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  generateMock.mockReset();
  getSavedMetaReadingMock.mockReset();
  navigateMock.mockReset();
  acceptPromotionMock.mockReset();
  window.sessionStorage.clear();
});
afterEach(cleanup);

async function generate(over: Partial<MetaReadingResponse> = {}, prompt = "free will across my books") {
  generateMock.mockResolvedValue(deliverable(over));
  render(<MetaReading />);
  fireEvent.change(screen.getByPlaceholderText(/What should this reading be about/), {
    target: { value: prompt },
  });
  fireEvent.click(screen.getByRole("button", { name: "Make the reading" }));
  await screen.findByTestId("meta-reading-deliverable");
}

async function reopenSaved(over: Partial<SavedMetaReading> = {}) {
  getSavedMetaReadingMock.mockResolvedValue(savedMetaReading(over));
  render(
    <MemoryRouter initialEntries={["/read/meta-reading/mr-saved"]}>
      <Routes>
        <Route path="/read/meta-reading/:assetId" element={<MetaReading />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByTestId("meta-reading-deliverable");
}

describe("MetaReading (M4)", () => {
  it("renders behind the proposed (sign-off pending) banner", () => {
    render(<MetaReading />);
    const banner = screen.getByTestId("meta-reading-proposed-banner");
    expect(banner.textContent?.toLowerCase()).toContain("proposed");
    expect(banner.textContent?.toLowerCase()).toContain("owned");
  });

  it("a cited passage opens the SPR-07 reader at the resolved page (via openDocument)", async () => {
    await generate();
    fireEvent.click(screen.getByRole("button", { name: "open at p.12" }));
    // SPR-05 one door: openDocument seeds the usePosition locator + navigates to
    // the ONE Reader route with the page (and the cited chunk) on the URL.
    expect(window.sessionStorage.getItem("antiek.read.pos.doc-mr")).toBe("11");
    expect(navigateMock).toHaveBeenCalledWith("/read/doc-mr?page=11&chunk=c1");
  });

  it("an unresolved cite opens the book without a fabricated page (via openDocument)", async () => {
    await generate({ citations: [cite({ page_index: null, page_resolved: false })] });
    fireEvent.click(screen.getByRole("button", { name: "open the book" }));
    // No page seeded (honest — no fabricated page); still routes through the one
    // door, carrying the cited chunk so the Reader can resolve its region.
    expect(window.sessionStorage.getItem("antiek.read.pos.doc-mr")).toBeNull();
    expect(navigateMock).toHaveBeenCalledWith("/read/doc-mr?chunk=c1");
  });

  it("the deliverable is generated + saved (the endpoint persists it); the surface shows it read-only", async () => {
    await generate();
    // The report renders; there is NO editable input for it (read-only).
    expect(screen.getByText("A synthesis of your books on free will.")).toBeTruthy();
    // generate was called with the HARD length-box (built-to-size).
    expect(generateMock).toHaveBeenCalledWith({
      prompt: "free will across my books",
      length_unit: "pages",
      length_amount: 3,
    });
  });

  it("the promote-into-Research suggestion APPEARS but never auto-ships", async () => {
    await generate();
    // The suggestion is shown…
    expect(screen.getByTestId("promote-suggestion")).toBeTruthy();
    // …but acceptPromotion is NEVER called without an explicit click.
    expect(acceptPromotionMock).not.toHaveBeenCalled();
  });

  it("promotion happens ONLY on explicit user accept", async () => {
    acceptPromotionMock.mockResolvedValue({ investigation_id: "inv-xyz" });
    await generate();
    fireEvent.click(screen.getByRole("button", { name: /Chase it as a research/ }));
    await screen.findByTestId("promote-done");
    expect(acceptPromotionMock).toHaveBeenCalledWith({
      assetId: "mr-abc123",
      prompt: "free will across my books",
      documentId: "doc-mr",
    });
  });

  it("a truncated synthesis is labelled honestly", async () => {
    await generate({ truncated: true });
    expect(screen.getByTestId("meta-reading-truncated")).toBeTruthy();
  });

  it("a minute-boxed asset hands its minutes to the narrate control (M3 scope)", async () => {
    await generate({ length_unit: "minutes", length_amount: 10 });
    const narrate = screen.getByTestId("read-aloud");
    expect(narrate.getAttribute("data-minutes")).toBe("10");
  });

  it("a pages-boxed asset does NOT pass minutes to narrate (only minute-boxes scope by time)", async () => {
    await generate({ length_unit: "pages", length_amount: 3 });
    expect(screen.getByTestId("read-aloud").getAttribute("data-minutes")).toBe("");
  });

  it("an empty owned corpus shows an honest empty state, no report", async () => {
    generateMock.mockResolvedValue(
      deliverable({ empty: true, report: "", citations: [], corpus_document_ids: [] }),
    );
    render(<MetaReading />);
    fireEvent.change(screen.getByPlaceholderText(/What should this reading be about/), {
      target: { value: "anything" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Make the reading" }));
    expect(await screen.findByText(/readable corpus is empty/)).toBeTruthy();
    // No deliverable section, no report.
    expect(screen.queryByTestId("meta-reading-deliverable")).toBeNull();
  });

  it("reopens a saved asset as read-only, not as a generator", async () => {
    await reopenSaved();
    expect(getSavedMetaReadingMock).toHaveBeenCalledWith("mr-saved");
    expect(generateMock).not.toHaveBeenCalled();
    expect(screen.getByText("A saved synthesis of your books.")).toBeTruthy();
    expect(screen.queryByPlaceholderText(/What should this reading be about/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Make the reading" })).toBeNull();
    expect(screen.getByTestId("read-aloud").getAttribute("data-minutes")).toBe("8");
  });

  it("saved-asset promotion uses the saved prompt and remains explicit", async () => {
    acceptPromotionMock.mockResolvedValue({ investigation_id: "inv-from-saved" });
    await reopenSaved();
    expect(acceptPromotionMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Chase it as a research/ }));
    await screen.findByTestId("promote-done");
    expect(acceptPromotionMock).toHaveBeenCalledWith({
      assetId: "mr-saved",
      prompt: "saved free will prompt",
      documentId: "doc-mr",
    });
  });

  it("clears stale saved-asset report and promotion state while loading a different saved asset", async () => {
    const next = deferred<SavedMetaReading>();
    getSavedMetaReadingMock.mockImplementation((id: string) => {
      if (id === "mr-saved-a") {
        return Promise.resolve(
          savedMetaReading({
            asset_id: "mr-saved-a",
            prompt: "first prompt",
            report: "First saved synthesis.",
            corpus_document_ids: ["doc-a"],
          }),
        );
      }
      return next.promise;
    });
    acceptPromotionMock.mockResolvedValue({ investigation_id: "inv-from-first" });

    const view = render(
      <MemoryRouter>
        <Routes location="/read/meta-reading/mr-saved-a">
          <Route path="/read/meta-reading/:assetId" element={<MetaReading />} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByText("First saved synthesis.");
    fireEvent.click(screen.getByRole("button", { name: /Chase it as a research/ }));
    await screen.findByTestId("promote-done");

    view.rerender(
      <MemoryRouter>
        <Routes location="/read/meta-reading/mr-saved-b">
          <Route path="/read/meta-reading/:assetId" element={<MetaReading />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.queryByText("First saved synthesis.")).toBeNull();
    expect(screen.queryByTestId("promote-done")).toBeNull();

    next.resolve(
      savedMetaReading({
        asset_id: "mr-saved-b",
        prompt: "second prompt",
        report: "Second saved synthesis.",
        corpus_document_ids: ["doc-b"],
      }),
    );
    expect(await screen.findByText("Second saved synthesis.")).toBeTruthy();
  });
});
