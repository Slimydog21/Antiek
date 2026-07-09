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
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { BookCitation, MetaReadingResponse } from "../../../api/books";
import MetaReading from "./index";

const { generateMock, navigateMock, acceptPromotionMock, fetchDepthTiersMock } =
  vi.hoisted(() => ({
    generateMock: vi.fn(),
    navigateMock: vi.fn(),
    acceptPromotionMock: vi.fn(),
    fetchDepthTiersMock: vi.fn(async () => ({
      active_depth_tier: null as string | null,
      active_preset: null,
      tiers: [],
    })),
  }));

vi.mock("../../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../../api/books")>();
  return { ...actual, generateMetaReading: generateMock };
});

vi.mock("../../../api/settings", () => ({
  fetchDepthTiers: (...args: unknown[]) => fetchDepthTiersMock(...args),
  fetchDecisionTreeSelection: vi.fn(async () => ({
    model_id: null,
    provider_id: null,
    installed: false,
    notes: [],
    source: "test",
  })),
  fetchSettingsBudget: vi.fn(async () => null),
}));

vi.mock("../../../components/engagement/DecisionTreeDriverBadge", () => ({
  DecisionTreeDriverBadge: (props: {
    researchTier?: string | null;
  }) => (
    <div
      data-testid="decision-tree-driver-badge-stub"
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
    >
      driver badge
    </div>
  ),
}));

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

beforeEach(() => {
  generateMock.mockReset();
  navigateMock.mockReset();
  acceptPromotionMock.mockReset();
  fetchDepthTiersMock.mockReset().mockResolvedValue({
    active_depth_tier: null,
    active_preset: null,
    tiers: [],
  });
  window.sessionStorage.clear();
});
afterEach(cleanup);

async function generate(over: Partial<MetaReadingResponse> = {}, prompt = "free will across my books") {
  generateMock.mockResolvedValue(deliverable(over));
  render(<MetaReading />);
  await waitFor(() => {
    expect(
      screen.getByTestId("meta-reading-root").getAttribute("data-depth-prefill"),
    ).toBe("none");
  });
  fireEvent.change(screen.getByPlaceholderText(/What should this reading be about/), {
    target: { value: prompt },
  });
  fireEvent.click(screen.getByRole("button", { name: "Make the reading" }));
  await screen.findByTestId("meta-reading-deliverable");
}

describe("MetaReading (M4)", () => {
  it("renders behind the proposed (sign-off pending) banner", () => {
    render(<MetaReading />);
    const banner = screen.getByTestId("meta-reading-proposed-banner");
    expect(banner.textContent?.toLowerCase()).toContain("proposed");
    expect(banner.textContent?.toLowerCase()).toContain("owned");
  });

  it("mounts DecisionTreeDriverBadge with researchTier (lh)", async () => {
    render(<MetaReading />);
    await waitFor(() => {
      expect(screen.getByTestId("meta-reading-driver-badge-mount")).toBeTruthy();
    });
    expect(
      screen
        .getByTestId("meta-reading-driver-badge-mount")
        .getAttribute("data-research-tier"),
    ).toBe("deep");
    expect(
      screen
        .getByTestId("decision-tree-driver-badge-stub")
        .getAttribute("data-research-tier"),
    ).toBe("deep");
  });

  it("a cited passage opens the SPR-07 reader at the resolved page", async () => {
    await generate();
    fireEvent.click(screen.getByRole("button", { name: "open at p.12" }));
    // Seeds the usePosition locator + routes to the reader (no parallel nav).
    expect(window.sessionStorage.getItem("antiek.read.pos.doc-mr")).toBe("11");
    expect(navigateMock).toHaveBeenCalledWith("/read/doc-mr");
  });

  it("an unresolved cite opens the book without a fabricated page", async () => {
    await generate({ citations: [cite({ page_index: null, page_resolved: false })] });
    fireEvent.click(screen.getByRole("button", { name: "open the book" }));
    expect(window.sessionStorage.getItem("antiek.read.pos.doc-mr")).toBeNull();
    expect(navigateMock).toHaveBeenCalledWith("/read/doc-mr");
  });

  it("the deliverable is generated + saved (the endpoint persists it); the surface shows it read-only", async () => {
    await generate();
    // The report renders; there is NO editable input for it (read-only).
    expect(screen.getByText("A synthesis of your books on free will.")).toBeTruthy();
    // generate was called with the HARD length-box (built-to-size).
    // Residual (jy): research_tier defaults deep when Settings unset.
    expect(generateMock).toHaveBeenCalledWith({
      prompt: "free will across my books",
      length_unit: "pages",
      length_amount: 3,
      research_tier: "deep",
    });
  });

  it("forwards Settings wrestle research_tier on generate (jy)", async () => {
    fetchDepthTiersMock.mockResolvedValue({
      active_depth_tier: "wrestle",
      active_preset: null,
      tiers: [],
    });
    generateMock.mockResolvedValue(deliverable());
    render(<MetaReading />);
    await waitFor(() => {
      expect(
        screen.getByTestId("meta-reading-root").getAttribute("data-depth-prefill"),
      ).toBe("installed");
    });
    expect(
      screen.getByTestId("meta-reading-root").getAttribute("data-research-tier"),
    ).toBe("wrestle");
    fireEvent.change(
      screen.getByPlaceholderText(/What should this reading be about/),
      { target: { value: "wrestle owned corpus" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Make the reading" }));
    await screen.findByTestId("meta-reading-deliverable");
    expect(generateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        research_tier: "wrestle",
        prompt: "wrestle owned corpus",
      }),
    );
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
});
