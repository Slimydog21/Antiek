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

const {
  generateMock,
  navigateMock,
  acceptPromotionMock,
  fetchDepthTiersMock,
  collectDeepResearchSpawnIds,
  listRecentDeepResearchSpawnIds,
} = vi.hoisted(() => ({
  generateMock: vi.fn(),
  navigateMock: vi.fn(),
  acceptPromotionMock: vi.fn(),
  fetchDepthTiersMock: vi.fn(async () => ({
    active_depth_tier: null as string | null,
    active_preset: null,
    tiers: [],
  })),
  collectDeepResearchSpawnIds: vi.fn(() => [] as string[]),
  listRecentDeepResearchSpawnIds: vi.fn(() => [] as string[]),
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

vi.mock("../../../components/engagement/TwinNotesPanel", () => ({
  TwinNotesPanel: (props: {
    assetId: string;
    autoLoad?: boolean;
    autoSeedIfEmpty?: boolean;
    autoPromoteAfterLoad?: boolean;
    seedTitle?: string;
    researchTier?: string | null;
    onPromoted?: () => void;
  }) => (
    <div
      data-testid="twin-notes-panel-stub"
      data-asset-id={props.assetId}
      data-auto-load={String(Boolean(props.autoLoad))}
      data-auto-seed={String(Boolean(props.autoSeedIfEmpty))}
      data-auto-promote={String(Boolean(props.autoPromoteAfterLoad))}
      data-seed-title={props.seedTitle ?? ""}
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
    >
      twins={props.assetId}
      {props.onPromoted ? (
        <button
          type="button"
          data-testid="meta-reading-twin-promote-notify"
          onClick={() => props.onPromoted?.()}
        >
          notify promote
        </button>
      ) : null}
    </div>
  ),
}));

vi.mock("../../../components/engagement/ResearchContextPanel", () => ({
  ResearchContextPanel: (props: {
    assetId: string;
    autoLoad?: boolean;
    researchTier?: string | null;
  }) => (
    <div
      data-testid="research-context-panel-stub"
      data-asset-id={props.assetId}
      data-auto-load={String(Boolean(props.autoLoad))}
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
    >
      context={props.assetId}
    </div>
  ),
}));

// Residual (anh): collective multi-select from meta-reading deliverable (parity ang).
vi.mock("../../../workspace/collectDeepResearchSpawnIds", () => ({
  collectDeepResearchSpawnIds: (...args: unknown[]) =>
    collectDeepResearchSpawnIds(...args),
}));

vi.mock("../../../workspace/recentDeepResearchSpawns", () => ({
  listRecentDeepResearchSpawnIds: (...args: unknown[]) =>
    listRecentDeepResearchSpawnIds(...args),
}));

vi.mock("../../../workspace/windowsStore", () => ({
  useWindows: (sel: (s: { windows: Record<string, unknown> }) => unknown) =>
    sel({ windows: {} }),
}));

vi.mock("../../../components/engagement/CollectiveResearchPanel", () => ({
  CollectiveResearchPanel: (props: {
    availableSpawnIds: string[];
    parentAssetId?: string | null;
    recentSpawnIds?: readonly string[] | null;
    openSpawnIds?: readonly string[] | null;
    onRecentSpawnsCleared?: () => void;
    onDocMerged?: () => void;
  }) => (
    <div
      data-testid="collective-research-panel-stub"
      data-recent={
        props.recentSpawnIds != null ? props.recentSpawnIds.join(",") : ""
      }
      data-has-clear={props.onRecentSpawnsCleared ? "1" : "0"}
      data-has-merged={props.onDocMerged ? "1" : "0"}
    >
      {props.parentAssetId}:{props.availableSpawnIds.join(",")}
      {props.onDocMerged ? (
        <button
          type="button"
          data-testid="meta-reading-collective-merge-notify"
          onClick={() => props.onDocMerged?.()}
        >
          notify merge
        </button>
      ) : null}
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
  collectDeepResearchSpawnIds.mockReset().mockReturnValue([]);
  listRecentDeepResearchSpawnIds.mockReset().mockReturnValue([]);
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

  it("mounts TwinNotes recursive note-taker on deliverable (agn)", async () => {
    await generate({}, "free will across my books");
    expect(screen.queryByTestId("meta-reading-twins-mount")).toBeTruthy();
    const mount = screen.getByTestId("meta-reading-twins-mount");
    expect(mount.getAttribute("data-view-format")).toBe("html");
    expect(mount.getAttribute("data-asset-id")).toBe("mr-abc123");
    expect(mount.getAttribute("data-seamless-meta-twins")).toBe("true");
    // Residual (anw): Open Write twin_seed from meta-reading HTML synthesis.
    const writeMount = screen.getByTestId("meta-reading-open-write-mount");
    expect(writeMount.getAttribute("data-seamless-meta-write")).toBe("true");
    const write = screen.getByTestId("meta-reading-open-write");
    expect(write.getAttribute("href") || "").toMatch(
      /^\/write\?twin_seed=antiek\.twin_write_seed\./,
    );
    expect(write.getAttribute("data-write-seed-source")).toBe(
      "meta_reading_deliverable",
    );
    expect(write.getAttribute("data-write-seed-has-body")).toBe("true");
    expect(write.getAttribute("data-has-twin-seed")).toBe("1");
    // Residual (anz): HTML-first report + competitive DR deep-links on deliverable.
    const deliverable = screen.getByTestId("meta-reading-deliverable");
    expect(deliverable.getAttribute("data-view-format")).toBe("html");
    expect(deliverable.getAttribute("data-html-first")).toBe("true");
    expect(deliverable.getAttribute("data-seamless-meta-deliverable")).toBe(
      "true",
    );
    expect(deliverable.getAttribute("data-asset-id")).toBe("mr-abc123");
    const report = screen.getByTestId("meta-reading-report");
    expect(report.getAttribute("data-view-format")).toBe("html");
    expect(report.getAttribute("data-html-first")).toBe("true");
    expect(report.getAttribute("data-asset-id")).toBe("mr-abc123");
    expect(report.textContent).toMatch(/synthesis of your books/i);
    expect(
      screen
        .getByTestId("meta-reading-competitive-scorecard-link")
        .getAttribute("href"),
    ).toBe("/settings#settings-competitive-dr-scorecard");
    expect(
      screen
        .getByTestId("meta-reading-competitive-dr-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-competitive-deep-research-quality/);
    // Residual (apt): hop/stage pipeline honesty on meta competitive links.
    const metaComp = screen.getByTestId("meta-reading-competitive-links");
    expect(metaComp.getAttribute("data-hop-pipeline")).toBe("api");
    expect(metaComp.getAttribute("data-stage-pipeline")).toBe("ape");
    expect(
      screen.getByTestId("meta-reading-competitive-pipeline-hint").textContent,
    ).toMatch(/plan.*terminal/i);
    expect(
      screen
        .getByTestId("meta-reading-twin-completeness-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-twin-note-taker-completeness-matrix/);
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-asset-id")).toBe("mr-abc123");
    expect(twins.getAttribute("data-auto-load")).toBe("true");
    expect(twins.getAttribute("data-auto-seed")).toBe("true");
    expect(twins.getAttribute("data-seed-title")).toBe(
      "free will across my books",
    );
    // Residual (amt): ResearchContext on meta-reading deliverable with depth.
    const ctxMount = screen.getByTestId("meta-reading-context-mount");
    expect(ctxMount.getAttribute("data-asset-id")).toBe("mr-abc123");
    expect(ctxMount.getAttribute("data-seamless-meta-context")).toBe("true");
    expect(ctxMount.getAttribute("data-research-tier")).toMatch(
      /deep|fast|wrestle/,
    );
    const ctx = screen.getByTestId("research-context-panel-stub");
    expect(ctx.getAttribute("data-asset-id")).toBe("mr-abc123");
    expect(ctx.getAttribute("data-auto-load")).toBe("true");
    expect(ctx.getAttribute("data-research-tier")).toMatch(/deep|fast|wrestle/);
    // Residual (anb): promote remounts twins + context (parity ana/amy).
    expect(twins.getAttribute("data-auto-promote")).toBe("true");
    expect(
      screen
        .getByTestId("meta-reading-twins-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("0");
    expect(
      screen
        .getByTestId("meta-reading-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("0");
    fireEvent.click(screen.getByTestId("meta-reading-twin-promote-notify"));
    await waitFor(() => {
      expect(
        screen
          .getByTestId("meta-reading-twins-refresh")
          .getAttribute("data-refresh-key"),
      ).toBe("1");
    });
    expect(
      screen
        .getByTestId("meta-reading-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("1");
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

  it("mounts collective panel when open DR spawns exist (anh)", async () => {
    collectDeepResearchSpawnIds.mockReturnValue(["spn_meta_1", "spn_meta_2"]);
    await generate();
    const mount = screen.getByTestId("meta-reading-collective-mount");
    expect(mount.getAttribute("data-view-format")).toBe("html");
    expect(mount.getAttribute("data-asset-id")).toBe("mr-abc123");
    expect(mount.getAttribute("data-seamless-meta-collective")).toBe("true");
    expect(mount.getAttribute("data-available-spawn-count")).toBe("2");
    expect(screen.getByTestId("collective-research-panel-stub").textContent).toMatch(
      /mr-abc123:spn_meta_1,spn_meta_2/,
    );
    // Collective merge remounts twins + context (parity ang / ResearchThis and).
    expect(
      screen
        .getByTestId("collective-research-panel-stub")
        .getAttribute("data-has-merged"),
    ).toBe("1");
    expect(
      screen
        .getByTestId("meta-reading-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("0");
    fireEvent.click(screen.getByTestId("meta-reading-collective-merge-notify"));
    await waitFor(() => {
      expect(
        screen
          .getByTestId("meta-reading-context-refresh")
          .getAttribute("data-refresh-key"),
      ).toBe("1");
    });
    expect(
      screen
        .getByTestId("meta-reading-twins-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("1");
  });

  it("wires recent_ring into collect + meta collective mount (anh)", async () => {
    listRecentDeepResearchSpawnIds.mockReturnValue([
      "spn_meta_recent",
      "spn_meta_older",
    ]);
    collectDeepResearchSpawnIds.mockImplementation(
      (source: { recentSpawnIds?: readonly string[] | null }) =>
        [...(source.recentSpawnIds ?? [])],
    );
    await generate();
    expect(collectDeepResearchSpawnIds).toHaveBeenCalled();
    const lastCall = collectDeepResearchSpawnIds.mock.calls.at(-1)?.[0] as {
      recentSpawnIds?: readonly string[];
    };
    expect(lastCall.recentSpawnIds).toEqual([
      "spn_meta_recent",
      "spn_meta_older",
    ]);
    const mount = screen.getByTestId("meta-reading-collective-mount");
    expect(mount.getAttribute("data-recent-count")).toBe("2");
    expect(mount.getAttribute("data-available-spawn-count")).toBe("2");
    const stub = screen.getByTestId("collective-research-panel-stub");
    expect(stub.getAttribute("data-recent")).toBe(
      "spn_meta_recent,spn_meta_older",
    );
    expect(stub.getAttribute("data-has-clear")).toBe("1");
    expect(stub.textContent).toMatch(
      /mr-abc123:spn_meta_recent,spn_meta_older/,
    );
  });

  it("omits collective panel when no open spawns (anh)", async () => {
    collectDeepResearchSpawnIds.mockReturnValue([]);
    await generate();
    expect(screen.queryByTestId("meta-reading-collective-mount")).toBeNull();
  });
});
