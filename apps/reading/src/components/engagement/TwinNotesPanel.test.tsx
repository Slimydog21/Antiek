import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  buildTwinChasePayload,
  buildTwinDraftHtml,
  mergeTwinChaseNotes,
  TwinNotesPanel,
} from "./TwinNotesPanel";

const fetchTwinNotes = vi.fn();
const recordTwinNote = vi.fn();
const promoteTwinsToContext = vi.fn();
const seedTwinNotes = vi.fn();
const launchFloatingDeepResearch = vi.fn();
const openWindow = vi.fn(() => "win:twin-draft:test");
const storeTwinWriteSeed = vi.fn(() => "antiek.twin_write_seed.testkey");
const buildTwinWriteHref = vi.fn(
  (key: string) => `/write?twin_seed=${encodeURIComponent(key)}`,
);
const buildTwinPromoteWriteHref = vi.fn(
  () => "/write?twin_seed=antiek.twin_write_seed.promote",
);

vi.mock("../../api/engagement", () => ({
  fetchTwinNotes: (...args: unknown[]) => fetchTwinNotes(...args),
  recordTwinNote: (...args: unknown[]) => recordTwinNote(...args),
  promoteTwinsToContext: (...args: unknown[]) => promoteTwinsToContext(...args),
  seedTwinNotes: (...args: unknown[]) => seedTwinNotes(...args),
}));

vi.mock("../../modes/Reading/launchFloatingDeepResearch", () => ({
  launchFloatingDeepResearch: (...args: unknown[]) =>
    launchFloatingDeepResearch(...args),
}));

vi.mock("../windows/openWindow", () => ({
  openWindow: (...args: unknown[]) => openWindow(...args),
}));

vi.mock("../../workspace/twinWriteSeed", async (importOriginal) => {
  const actual = await importOriginal<
    typeof import("../../workspace/twinWriteSeed")
  >();
  return {
    ...actual,
    storeTwinWriteSeed: (...args: unknown[]) => storeTwinWriteSeed(...args),
    buildTwinWriteHref: (...args: unknown[]) =>
      buildTwinWriteHref(...(args as [string])),
    buildTwinPromoteWriteHref: (...args: unknown[]) =>
      buildTwinPromoteWriteHref(...args),
  };
});

vi.mock("./DecisionTreeDriverBadge", () => ({
  DecisionTreeDriverBadge: (props: {
    researchTier?: string;
    promptText?: string;
  }) => (
    <div
      data-testid="mock-decision-tree-driver-badge"
      data-research-tier={props.researchTier ?? ""}
      data-prompt-len={String((props.promptText || "").length)}
    >
      mock driver badge
    </div>
  ),
}));

// Residual (na): budget panel — controllable soft-gate via onProjectionChange.
let mockWouldExceed: boolean | null = false;
vi.mock("./ResearchLaunchBudgetPanel", () => ({
  ResearchLaunchBudgetPanel: (props: {
    promptText: string;
    researchTier: string;
    onProjectionChange?: (p: {
      wouldExceedBudget: boolean | null;
      pricingKnown: boolean;
      estimatedUsdHigh: number | null;
      remainingUsd: number | null;
      modelId: string | null;
    }) => void;
    onResearchTierChange?: (t: string) => void;
    allowTierPick?: boolean;
  }) => {
    // Fire projection once so parents receive soft-gate state.
    if (props.onProjectionChange) {
      queueMicrotask(() => {
        props.onProjectionChange?.({
          wouldExceedBudget: mockWouldExceed,
          pricingKnown: mockWouldExceed !== null,
          estimatedUsdHigh: mockWouldExceed ? 9.99 : 0.05,
          remainingUsd: mockWouldExceed ? 0.01 : 10,
          modelId: "model-a",
        });
      });
    }
    return (
      <div
        data-testid="mock-research-launch-budget"
        data-prompt-len={String((props.promptText || "").length)}
        data-research-tier={props.researchTier}
      >
        mock budget · tier={props.researchTier}
        {props.allowTierPick ? (
          <button
            type="button"
            data-testid="mock-budget-pick-wrestle"
            onClick={() => props.onResearchTierChange?.("wrestle")}
          >
            pick wrestle
          </button>
        ) : null}
      </div>
    );
  },
}));

describe("buildTwinDraftHtml (pn)", () => {
  it("builds HTML draft with questions first and escaped text", () => {
    const draft = buildTwinDraftHtml(
      [
        { note_id: "i1", kind: "insight", text: "A <b>bold</b> insight" },
        { note_id: "q1", kind: "question", text: "Why?" },
      ],
      "paper-42",
    );
    expect(draft.note_ids).toEqual(["q1", "i1"]);
    expect(draft.title).toMatch(/paper-42/);
    expect(draft.html).toMatch(/data-twin-draft="true"/);
    expect(draft.html).toMatch(/data-view-format="html"/);
    expect(draft.html).toMatch(/data-note-id="q1"/);
    expect(draft.html).toMatch(/&lt;b&gt;/);
    expect(draft.html).not.toMatch(/<b>bold<\/b>/);
  });
});

describe("mergeTwinChaseNotes (pw)", () => {
  it("dedupes by note_id and orders questions before insights", () => {
    const merged = mergeTwinChaseNotes([
      [
        { note_id: "i1", kind: "insight", text: "From A" },
        { note_id: "q1", kind: "question", text: "Q from A" },
      ],
      [
        { note_id: "q1", kind: "question", text: "duplicate ignored" },
        { note_id: "q2", kind: "question", text: "Q from B" },
        { note_id: "  ", kind: "insight", text: "skip empty id" },
        { note_id: "i2", kind: "insight", text: "  " },
      ],
    ]);
    expect(merged.map((n) => n.note_id)).toEqual(["q1", "q2", "i1"]);
    expect(merged.find((n) => n.note_id === "q1")?.text).toBe("Q from A");
    const draft = buildTwinDraftHtml(merged, "cross-asset");
    expect(draft.note_ids).toEqual(["q1", "q2", "i1"]);
    expect(draft.html).toMatch(/data-note-count="3"/);
  });
});

describe("buildTwinChasePayload (mz/ni)", () => {
  it("orders questions before insights and builds goal_hint", () => {
    const payload = buildTwinChasePayload(
      [
        { note_id: "i1", kind: "insight", text: "Insight first" },
        { note_id: "q1", kind: "question", text: "Question second" },
      ],
      "paper-42",
    );
    expect(payload.note_ids).toEqual(["q1", "i1"]);
    expect(payload.selection_text).toMatch(/\[question\] Question second/);
    expect(payload.selection_text).toMatch(/\[insight\] Insight first/);
    expect(payload.goal_hint).toMatch(/Twin chase on paper-42/);
    expect(payload.goal_hint).toMatch(/questions=1/);
    expect(payload.goal_hint).toMatch(/insights=1/);
    // Residual (ni): note_ids provenance in goal_hint.
    expect(payload.goal_hint).toMatch(/note_ids=q1,i1/);
  });

  it("truncates long note_ids preview in goal_hint (ni)", () => {
    const notes = Array.from({ length: 6 }, (_, i) => ({
      note_id: `n${i}`,
      kind: i % 2 === 0 ? "question" : "insight",
      text: `T${i}`,
    }));
    const payload = buildTwinChasePayload(notes, "asset");
    expect(payload.note_ids).toHaveLength(6);
    expect(payload.goal_hint).toMatch(/note_ids=/);
    expect(payload.goal_hint).toMatch(/\+2/);
  });

  it("appends research_domains when domainSubjects provided (aoc)", () => {
    const payload = buildTwinChasePayload(
      [{ note_id: "q1", kind: "question", text: "Why heat?" }],
      "pd-fourier",
      ["Heat", "signal_processing", "heat", "  ", ""],
    );
    expect(payload.goal_hint).toMatch(/Twin chase on pd-fourier/);
    expect(payload.goal_hint).toMatch(
      /research_domains=heat,signal_processing/,
    );
    // Dedupe + lower-case; empty trimmed out; order first-seen.
    expect(payload.goal_hint).not.toMatch(/Heat/);
    expect(payload.goal_hint.match(/heat/g)?.length).toBe(1);
  });

  it("omits research_domains when domainSubjects absent or empty (aoc)", () => {
    const bare = buildTwinChasePayload(
      [{ note_id: "q1", kind: "question", text: "Q" }],
      "paper",
    );
    expect(bare.goal_hint).not.toMatch(/research_domains=/);
    const empty = buildTwinChasePayload(
      [{ note_id: "q1", kind: "question", text: "Q" }],
      "paper",
      [],
    );
    expect(empty.goal_hint).not.toMatch(/research_domains=/);
    const nullish = buildTwinChasePayload(
      [{ note_id: "q1", kind: "question", text: "Q" }],
      "paper",
      null,
    );
    expect(nullish.goal_hint).not.toMatch(/research_domains=/);
  });
});

describe("TwinNotesPanel", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    fetchTwinNotes.mockReset();
    recordTwinNote.mockReset();
    promoteTwinsToContext.mockReset();
    openWindow.mockClear();
    openWindow.mockReturnValue("win:twin-draft:test");
    storeTwinWriteSeed.mockClear();
    storeTwinWriteSeed.mockReturnValue("antiek.twin_write_seed.testkey");
    buildTwinWriteHref.mockClear();
    buildTwinWriteHref.mockImplementation(
      (key: string) => `/write?twin_seed=${encodeURIComponent(key)}`,
    );
    buildTwinPromoteWriteHref.mockClear();
    buildTwinPromoteWriteHref.mockImplementation(
      () => "/write?twin_seed=antiek.twin_write_seed.promote",
    );
    seedTwinNotes.mockReset();
    launchFloatingDeepResearch.mockReset();
    mockWouldExceed = false;
  });

  it("links to Settings twin seed readiness (ib)", () => {
    render(<TwinNotesPanel assetId="paper" />);
    const link = screen.getByTestId("twin-notes-settings-link");
    expect(link.getAttribute("href")).toBe("/settings#twin-seed-live-status");
    expect(link.textContent).toMatch(/twin seed readiness/i);
    // Residual (nc): driver badge always mounted on note-taker.
    expect(screen.getByTestId("twin-notes-driver-badge-mount")).toBeTruthy();
    expect(screen.getByTestId("mock-decision-tree-driver-badge")).toBeTruthy();
  });

  it("links dual-gate L1–L4 checklist for L3 twin live seed prep (mt)", () => {
    render(<TwinNotesPanel assetId="paper" />);
    const dual = screen.getByTestId("twin-notes-dual-gate-checklist-link");
    // Residual (xa): L3 twin checklist section deep-link.
    expect(dual.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4.*#l3-twin/);
    expect(dual.textContent).toMatch(/L3 twin checklist/i);
    // Residual (aio): FUTURE-AGENT twin matrix + competitive scorecard deep-links.
    expect(
      screen
        .getByTestId("twin-notes-future-agent-matrix-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-twin-note-taker-completeness-matrix/);
    expect(
      screen
        .getByTestId("twin-notes-competitive-scorecard-link")
        .getAttribute("href"),
    ).toBe("/settings#settings-competitive-dr-scorecard");
    // Residual (aky): competitive FUTURE + prompt-cost on recursive note-taker.
    expect(
      screen
        .getByTestId("twin-notes-competitive-dr-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-competitive-deep-research-quality/);
    expect(
      screen.getByTestId("twin-notes-competitive-dr-future-agent-link")
        .textContent,
    ).toMatch(/competitive DR quality/i);
    expect(
      screen
        .getByTestId("twin-notes-prompt-cost-projection-link")
        .getAttribute("href"),
    ).toBe("/settings#prompt-cost-projection");
    expect(
      screen.getByTestId("twin-notes-prompt-cost-projection-link").textContent,
    ).toMatch(/prompt-cost projection/i);
  });

  it("stamps domain-search coverage when domainSubjects provided (alt)", () => {
    render(
      <TwinNotesPanel
        assetId="pd-fourier"
        domainSubjects={["heat", "signal_processing"]}
      />,
    );
    const panel = screen.getByTestId("twin-notes-panel");
    expect(panel.getAttribute("data-domain-search-has-default")).toBe("true");
    expect(panel.getAttribute("data-domain-search-covered")).toMatch(/heat/);
    expect(panel.getAttribute("data-domain-subjects")).toMatch(/heat/);
    // Residual (aoo): chase buttons stamp domain-aware titles/metrics.
    const chase = screen.getByTestId("twin-chase-selected");
    expect(chase.getAttribute("data-domain-aware-chase")).toBe("true");
    expect(chase.getAttribute("data-research-domains")).toBe(
      "heat,signal_processing",
    );
    expect(chase.getAttribute("title") || "").toMatch(
      /research_domains=heat,signal_processing/,
    );
    expect(
      screen.getByTestId("twin-chase-selected-full").getAttribute(
        "data-domain-aware-chase",
      ),
    ).toBe("true");
    const strip = screen.getByTestId("twin-notes-domain-search-coverage");
    expect(strip.getAttribute("data-has-default")).toBe("true");
    expect(strip.textContent).toMatch(/default active/i);
    expect(strip.textContent).toMatch(/heat/i);
  });

  it("surfaces researchTier chrome when provided (kr)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 1,
      insight_count: 1,
      question_count: 0,
      notes: [
        {
          note_id: "twin_w",
          asset_id: "paper",
          kind: "insight",
          text: "Wrestle twin",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    render(
      <TwinNotesPanel assetId="paper" autoLoad researchTier="wrestle" />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("twin-notes-summary")).toBeTruthy();
    });
    expect(
      screen.getByTestId("twin-notes-panel").getAttribute("data-research-tier"),
    ).toBe("wrestle");
    expect(
      screen.getByTestId("twin-notes-metrics").getAttribute("data-research-tier"),
    ).toBe("wrestle");
    expect(screen.getByTestId("twin-notes-research-tier").textContent).toMatch(
      /wrestle/i,
    );
    expect(screen.getByTestId("twin-notes-research-tier").textContent).toMatch(
      /long-horizon/i,
    );
  });

  it("falls back to API research_tier when prop absent (lb)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 0,
      insight_count: 0,
      question_count: 0,
      notes: [],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>empty</p>",
    });
    seedTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 2,
      insight_count: 1,
      question_count: 1,
      notes: [
        {
          note_id: "twin_s",
          asset_id: "paper",
          kind: "insight",
          text: "Seeded",
        },
      ],
      research_tier: "deep",
      source_spawn_id: "spn_seed",
      seeded: true,
      live_seed: false,
      seed_source: "engagement_spine.twin.seed_twins_for_asset",
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins · tier=deep</p>",
    });
    render(
      <TwinNotesPanel
        assetId="paper"
        spawnId="spn_seed"
        autoLoad
        autoSeedIfEmpty
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("twin-notes-research-tier").textContent).toMatch(
        /deep/i,
      );
    });
    expect(
      screen.getByTestId("twin-notes-panel").getAttribute("data-research-tier"),
    ).toBe("deep");
  });

  it("auto-loads twins on mount when autoLoad (cq)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 2,
      insight_count: 1,
      question_count: 1,
      notes: [
        {
          note_id: "twin_1",
          asset_id: "paper",
          kind: "insight",
          text: "Seeded insight",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    render(<TwinNotesPanel assetId="paper" autoLoad />);
    await waitFor(() => {
      expect(fetchTwinNotes).toHaveBeenCalledWith("paper", {
        includeHtml: true,
        spawnId: null,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("twin-notes-summary").textContent).toMatch(
        /insights=1/,
      );
    });
    // Residual (fk): machine-readable twin metrics.
    const metrics = screen.getByTestId("twin-notes-metrics");
    expect(metrics.getAttribute("data-insight-count")).toBe("1");
    expect(metrics.getAttribute("data-question-count")).toBe("1");
    expect(metrics.getAttribute("data-note-count")).toBe("2");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    // Residual (arq): substrate ready when both insight + question legs present.
    expect(metrics.getAttribute("data-substrate-ready")).toBe("true");
    expect(metrics.getAttribute("data-has-insights")).toBe("true");
    expect(metrics.getAttribute("data-has-questions")).toBe("true");
    const substrate = screen.getByTestId("twin-substrate-readiness");
    expect(substrate.getAttribute("data-substrate-ready")).toBe("true");
    expect(substrate.getAttribute("data-html-first")).toBe("true");
    expect(substrate.textContent).toMatch(/substrate ready/i);
    expect(
      screen.getByTestId("twin-notes-panel").getAttribute("data-substrate-ready"),
    ).toBe("true");
    expect(seedTwinNotes).not.toHaveBeenCalled();
  });

  it("offline seeds when empty and autoSeedIfEmpty (dd)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 0,
      insight_count: 0,
      question_count: 0,
      notes: [],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "",
    });
    seedTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 2,
      insight_count: 1,
      question_count: 1,
      notes: [
        {
          note_id: "twin_seed_1",
          asset_id: "paper",
          kind: "insight",
          text: "Offline seed insight",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>seeded</p>",
      seeded: true,
      force_offline: true,
      live_seed: false,
      seed_source: "engagement_spine.twin.seed_twins_for_asset",
    });

    render(
      <TwinNotesPanel
        assetId="paper"
        autoLoad
        autoSeedIfEmpty
        seedTitle="Attention paper"
        seedBodyText="Transformers are all you need."
      />,
    );

    await waitFor(() => {
      expect(seedTwinNotes).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "paper",
          force_offline: true,
          title: "Attention paper",
        }),
      );
    });
    await waitFor(() => {
      const status = screen.getByTestId("twin-seed-status");
      // Residual (hh): offline-honest copy + machine-readable attrs.
      expect(status.textContent).toMatch(/offline-honest identity stubs/);
      expect(status.getAttribute("data-offline-honest")).toBe("true");
      expect(status.getAttribute("data-live-seed")).toBe("false");
      expect(status.getAttribute("data-seeded")).toBe("true");
      expect(status.getAttribute("data-force-offline")).toBe("true");
      expect(status.getAttribute("data-seed-source")).toBe(
        "engagement_spine.twin.seed_twins_for_asset",
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("twin-notes-summary").textContent).toMatch(
        /notes=2/,
      );
    });
  });

  it("surfaces live seed honesty when API reports live_seed (hh)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 0,
      insight_count: 0,
      question_count: 0,
      notes: [],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "",
    });
    seedTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 2,
      insight_count: 1,
      question_count: 1,
      notes: [
        {
          note_id: "twin_live_1",
          asset_id: "paper",
          kind: "insight",
          text: "Live note_taker insight",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>live</p>",
      seeded: true,
      live_seed: true,
      seed_source: "engagement_spine.twin.seed_twins_for_asset.live",
    });

    render(
      <TwinNotesPanel assetId="paper" autoLoad autoSeedIfEmpty />,
    );

    await waitFor(() => {
      const status = screen.getByTestId("twin-seed-status");
      expect(status.textContent).toMatch(/live note_taker injector landed/);
      expect(status.getAttribute("data-offline-honest")).toBe("false");
      expect(status.getAttribute("data-live-seed")).toBe("true");
      expect(status.getAttribute("data-seed-source")).toMatch(/\.live$/);
    });
  });

  it("auto-promotes twins to context after load when autoPromoteAfterLoad (ea)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 1,
      insight_count: 1,
      question_count: 0,
      notes: [
        {
          note_id: "twin_1",
          asset_id: "paper",
          kind: "insight",
          text: "Attention is routing.",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    promoteTwinsToContext.mockResolvedValue({
      asset_id: "paper",
      promoted_count: 1,
      context_unit_count: 1,
      promoted: [
        {
          twin_note_id: "twin_1",
          graph_node_id: "n1",
          kind: "insight",
          text: "Attention is routing.",
        },
      ],
      context_units: [],
      view_format: "html",
      product_panel: "twin_promote_context",
      source: "engagement_spine.twin_promote",
      notes: [],
      html: "<p>promoted</p>",
    });

    const onPromoted = vi.fn();
    render(
      <TwinNotesPanel
        assetId="paper"
        autoLoad
        autoPromoteAfterLoad
        onPromoted={onPromoted}
      />,
    );

    await waitFor(() => {
      expect(promoteTwinsToContext).toHaveBeenCalledWith(
        expect.objectContaining({ asset_id: "paper", include_html: true }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("twin-promote-status").textContent).toMatch(
        /auto-promoted 1/,
      );
    });
    // Residual (ec): parent notified so context can remount.
    await waitFor(() => {
      expect(onPromoted).toHaveBeenCalled();
    });
    expect(onPromoted.mock.calls[0][0].promoted_count).toBe(1);
  });

  it("records insight and shows twin HTML", async () => {
    recordTwinNote.mockResolvedValue({
      asset_id: "paper",
      note_count: 1,
      insight_count: 1,
      question_count: 0,
      notes: [
        {
          note_id: "twin_1",
          asset_id: "paper",
          kind: "insight",
          text: "Attention is routing.",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>Insight: Attention is routing.</p>",
    });

    render(<TwinNotesPanel assetId="paper" spawnId="spn_1" />);
    fireEvent.change(screen.getByTestId("twin-text"), {
      target: { value: "Attention is routing." },
    });
    fireEvent.click(screen.getByTestId("twin-record"));
    await waitFor(() => {
      expect(screen.getByTestId("twin-notes-summary").textContent).toMatch(
        /insights=1/,
      );
    });
    expect(recordTwinNote).toHaveBeenCalledWith({
      asset_id: "paper",
      kind: "insight",
      text: "Attention is routing.",
      source_spawn_id: "spn_1",
      include_html: true,
    });
    expect(screen.getByTestId("twin-notes-html").innerHTML).toMatch(
      /Attention is routing/,
    );
    expect(
      screen.getByTestId("twin-notes-panel").getAttribute("data-view-format"),
    ).toBe("html");
  });

  it("promotes twins into context units", async () => {
    promoteTwinsToContext.mockResolvedValue({
      asset_id: "paper",
      promoted_count: 1,
      context_unit_count: 1,
      promoted: [
        {
          twin_note_id: "twin_1",
          graph_node_id: "insight_abc",
          kind: "insight",
          text: "Attention is routing.",
        },
      ],
      context_units: [
        {
          unit_id: "insight_abc",
          twin_note_id: "twin_1",
          kind: "insight",
          text: "Attention is routing.",
        },
      ],
      // Residual (ajr/ajo): substrate depth-graph honesty fields.
      graph_node_ids: ["insight_abc"],
      unique_graph_node_count: 1,
      unique_unit_id_count: 1,
      content_addressed_alignment: true,
      view_format: "html",
      product_panel: "twin_promote_context",
      source: "engagement_spine.twin_promote",
      notes: ["Twins promoted into content-addressed context units"],
      html: "<p>[insight] Attention is routing.</p>",
    });

    render(<TwinNotesPanel assetId="paper" researchTier="deep" />);
    fireEvent.click(screen.getByTestId("twin-promote-context"));
    await waitFor(() => {
      expect(screen.getByTestId("twin-promote-result").textContent).toMatch(
        /promoted=1/,
      );
    });
    expect(promoteTwinsToContext).toHaveBeenCalledWith({
      asset_id: "paper",
      include_html: true,
      kinds: null,
      note_ids: null,
    });
    expect(screen.getByTestId("twin-promote-html").innerHTML).toMatch(
      /Attention is routing/,
    );
    // Residual (hi): machine-readable promote→context metrics.
    const metrics = screen.getByTestId("twin-promote-metrics");
    expect(metrics.getAttribute("data-promoted-count")).toBe("1");
    expect(metrics.getAttribute("data-context-unit-count")).toBe("1");
    expect(metrics.getAttribute("data-promote-kinds")).toBe("all");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.getAttribute("data-product-panel")).toBe(
      "twin_promote_context",
    );
    expect(metrics.getAttribute("data-source")).toBe(
      "engagement_spine.twin_promote",
    );
    expect(metrics.textContent).toMatch(/Twin promote → context/);
    // Residual (adl): research_tier on promote metrics (depth audit parity adi).
    expect(metrics.getAttribute("data-research-tier")).toBe("deep");
    expect(metrics.textContent).toMatch(/tier=deep/);
    // Residual (ajn): content-addressed depth-graph node honesty on promote metrics.
    expect(metrics.getAttribute("data-graph-node-id-count")).toBe("1");
    expect(metrics.getAttribute("data-unique-graph-node-count")).toBe("1");
    expect(metrics.getAttribute("data-graph-node-ids")).toBe("insight_abc");
    expect(metrics.getAttribute("data-unique-unit-id-count")).toBe("1");
    expect(metrics.getAttribute("data-content-addressed-alignment")).toBe(
      "true",
    );
    // Residual (ajr): prefer API depth-graph fields when substrate emits them.
    expect(metrics.getAttribute("data-depth-graph-source")).toBe("api");
    expect(metrics.textContent).toMatch(/graph_nodes=1/);
    expect(metrics.textContent).toMatch(/content-addressed unit≡node/);
    expect(
      screen
        .getByTestId("twin-promote-twin-matrix-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-twin-note-taker-completeness-matrix/);
    expect(
      screen
        .getByTestId("twin-promote-competitive-scorecard-link")
        .getAttribute("href"),
    ).toBe("/settings#settings-competitive-dr-scorecard");
    // Residual (rr/aew): Open Write twin_seed from promoted context units + path.
    expect(buildTwinPromoteWriteHref).toHaveBeenCalled();
    const write = screen.getByTestId("twin-promote-open-write");
    expect(write.getAttribute("href")).toMatch(/twin_seed=/);
    expect(write.getAttribute("data-has-twin-seed")).toBe("1");
    expect(write.getAttribute("data-promoted-count")).toBe("1");
    expect(write.textContent).toMatch(/Open Write \(promoted twins\)/i);
    // Residual (acq): context unit body → has-body true.
    expect(write.getAttribute("data-write-seed-has-body")).toBe("true");
    // Residual (aew): promote → Write recursive note-taker path honesty.
    expect(write.getAttribute("data-seamless-twin-write")).toBe("true");
    expect(write.getAttribute("data-asset-id")).toBeTruthy();
  });

  it("promotes visible list filter in one click (ms)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 2,
      insight_count: 1,
      question_count: 1,
      notes: [
        {
          note_id: "twin_i",
          asset_id: "paper",
          kind: "insight",
          text: "Insight A",
        },
        {
          note_id: "twin_q",
          asset_id: "paper",
          kind: "question",
          text: "Question B?",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    promoteTwinsToContext.mockResolvedValue({
      asset_id: "paper",
      promoted_count: 1,
      context_unit_count: 1,
      promoted: [
        {
          twin_note_id: "twin_i",
          graph_node_id: "insight_a",
          kind: "insight",
          text: "Insight A",
        },
      ],
      context_units: [
        {
          unit_id: "insight_a",
          twin_note_id: "twin_i",
          kind: "insight",
          text: "Insight A",
        },
      ],
      kinds: ["insight"],
      view_format: "html",
      product_panel: "twin_promote_context",
      source: "engagement_spine.twin_promote",
      notes: [],
      html: "<p>[insight] Insight A</p>",
    });
    render(<TwinNotesPanel assetId="paper" autoLoad />);
    await waitFor(() => {
      expect(screen.getByTestId("twin-list-filter")).toBeTruthy();
    });
    fireEvent.change(screen.getByTestId("twin-list-filter"), {
      target: { value: "insight" },
    });
    fireEvent.click(screen.getByTestId("twin-promote-visible"));
    await waitFor(() => {
      expect(promoteTwinsToContext).toHaveBeenCalledWith({
        asset_id: "paper",
        include_html: true,
        kinds: ["insight"],
        note_ids: null,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("twin-promote-status").textContent).toMatch(
        /insight/i,
      );
    });
    expect(
      (screen.getByTestId("twin-promote-kinds") as HTMLSelectElement).value,
    ).toBe("insight");
  });

  it("filters twin list by kind before promote (mr)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 2,
      insight_count: 1,
      question_count: 1,
      notes: [
        {
          note_id: "twin_i",
          asset_id: "paper",
          kind: "insight",
          text: "Insight A",
        },
        {
          note_id: "twin_q",
          asset_id: "paper",
          kind: "question",
          text: "Question B?",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    render(<TwinNotesPanel assetId="paper" autoLoad />);
    await waitFor(() => {
      expect(screen.getByTestId("twin-list-filter")).toBeTruthy();
    });
    expect(screen.getByTestId("twin-notes-list").textContent).toMatch(
      /Insight A/,
    );
    expect(screen.getByTestId("twin-notes-list").textContent).toMatch(
      /Question B/,
    );
    fireEvent.change(screen.getByTestId("twin-list-filter"), {
      target: { value: "insight" },
    });
    expect(screen.getByTestId("twin-notes-list").textContent).toMatch(
      /Insight A/,
    );
    expect(screen.getByTestId("twin-notes-list").textContent).not.toMatch(
      /Question B/,
    );
    expect(
      screen.getByTestId("twin-notes-metrics").getAttribute("data-list-filter"),
    ).toBe("insight");
    expect(
      screen
        .getByTestId("twin-notes-metrics")
        .getAttribute("data-visible-count"),
    ).toBe("1");
    fireEvent.change(screen.getByTestId("twin-list-filter"), {
      target: { value: "question" },
    });
    expect(screen.getByTestId("twin-notes-list").textContent).toMatch(
      /Question B/,
    );
    expect(screen.getByTestId("twin-notes-list").textContent).not.toMatch(
      /Insight A/,
    );
  });

  it("selectively promotes questions only (mq)", async () => {
    promoteTwinsToContext.mockResolvedValue({
      asset_id: "paper",
      promoted_count: 1,
      context_unit_count: 1,
      promoted: [
        {
          twin_note_id: "twin_q",
          graph_node_id: "question_abc",
          kind: "question",
          text: "What remains open?",
        },
      ],
      context_units: [
        {
          unit_id: "question_abc",
          twin_note_id: "twin_q",
          kind: "question",
          text: "What remains open?",
        },
      ],
      kinds: ["question"],
      view_format: "html",
      product_panel: "twin_promote_context",
      source: "engagement_spine.twin_promote",
      notes: [],
      html: "<p>[question] What remains open?</p>",
    });
    render(<TwinNotesPanel assetId="paper" />);
    expect(screen.getByTestId("twin-promote-kinds")).toBeTruthy();
    fireEvent.change(screen.getByTestId("twin-promote-kinds"), {
      target: { value: "question" },
    });
    fireEvent.click(screen.getByTestId("twin-promote-context"));
    await waitFor(() => {
      expect(promoteTwinsToContext).toHaveBeenCalledWith({
        asset_id: "paper",
        include_html: true,
        kinds: ["question"],
        note_ids: null,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("twin-promote-status").textContent).toMatch(
        /questions only|question/i,
      );
    });
    expect(
      screen
        .getByTestId("twin-promote-metrics")
        .getAttribute("data-promote-kinds"),
    ).toBe("question");
  });

  it("gates promote CTAs by hydrated substrate kind readiness (arx)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 0,
      insight_count: 0,
      question_count: 0,
      notes: [],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "",
    });
    render(<TwinNotesPanel assetId="paper" autoLoad />);
    await waitFor(() => {
      expect(
        screen.getByTestId("twin-promote-context").getAttribute("data-twins-hydrated"),
      ).toBe("true");
    });
    const promoteAll = screen.getByTestId(
      "twin-promote-context",
    ) as HTMLButtonElement;
    expect(promoteAll.getAttribute("data-promote-ready")).toBe("false");
    expect(promoteAll.getAttribute("data-substrate-empty")).toBe("true");
    expect(promoteAll.disabled).toBe(true);
    expect(promoteAll.getAttribute("title") || "").toMatch(/Empty twin substrate/i);
    const promoteVisible = screen.getByTestId(
      "twin-promote-visible",
    ) as HTMLButtonElement;
    expect(promoteVisible.getAttribute("data-promote-ready")).toBe("false");
    expect(promoteVisible.disabled).toBe(true);

    // Insights only → promote all ready; promote questions kind not ready.
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 1,
      insight_count: 1,
      question_count: 0,
      notes: [
        {
          note_id: "twin_i",
          asset_id: "paper",
          kind: "insight",
          text: "Insight only",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>i</p>",
    });
    fireEvent.click(screen.getByTestId("twin-refresh"));
    await waitFor(() => {
      expect(
        screen.getByTestId("twin-promote-context").getAttribute("data-promote-ready"),
      ).toBe("true");
    });
    expect(
      (screen.getByTestId("twin-promote-context") as HTMLButtonElement).disabled,
    ).toBe(false);
    expect(
      screen.getByTestId("twin-promote-context").getAttribute("data-has-insights"),
    ).toBe("true");
    expect(
      screen.getByTestId("twin-promote-context").getAttribute("data-has-questions"),
    ).toBe("false");
    fireEvent.change(screen.getByTestId("twin-promote-kinds"), {
      target: { value: "question" },
    });
    await waitFor(() => {
      expect(
        screen.getByTestId("twin-promote-context").getAttribute("data-promote-ready"),
      ).toBe("false");
    });
    expect(
      (screen.getByTestId("twin-promote-context") as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(
      screen.getByTestId("twin-promote-context").getAttribute("title") || "",
    ).toMatch(/No question twins/i);
  });

  it("multi-selects note_ids and promotes selected only (mx)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 2,
      insight_count: 2,
      question_count: 0,
      notes: [
        {
          note_id: "twin_a",
          asset_id: "paper",
          kind: "insight",
          text: "Select me",
        },
        {
          note_id: "twin_b",
          asset_id: "paper",
          kind: "insight",
          text: "Leave me",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    promoteTwinsToContext.mockResolvedValue({
      asset_id: "paper",
      promoted_count: 1,
      context_unit_count: 1,
      promoted: [
        {
          twin_note_id: "twin_a",
          graph_node_id: "insight_a",
          kind: "insight",
          text: "Select me",
        },
      ],
      context_units: [
        {
          unit_id: "insight_a",
          twin_note_id: "twin_a",
          kind: "insight",
          text: "Select me",
        },
      ],
      note_ids: ["twin_a"],
      view_format: "html",
      product_panel: "twin_promote_context",
      source: "engagement_spine.twin_promote",
      notes: [],
      html: "<p>[insight] Select me</p>",
    });
    render(<TwinNotesPanel assetId="paper" autoLoad />);
    await waitFor(() => {
      expect(screen.getByTestId("twin-select-twin_a")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("twin-select-twin_a"));
    expect(
      screen.getByTestId("twin-selection-count").getAttribute("data-selected-count"),
    ).toBe("1");
    fireEvent.click(screen.getByTestId("twin-promote-selected"));
    await waitFor(() => {
      expect(promoteTwinsToContext).toHaveBeenCalledWith({
        asset_id: "paper",
        include_html: true,
        kinds: null,
        note_ids: ["twin_a"],
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("twin-promote-status").textContent).toMatch(
        /selected=1/,
      );
    });
    // Residual (my): selection clears after successful multi-select promote.
    await waitFor(() => {
      expect(
        screen
          .getByTestId("twin-selection-count")
          .getAttribute("data-selected-count"),
      ).toBe("0");
    });
    const metrics = screen.getByTestId("twin-promote-metrics");
    expect(metrics.getAttribute("data-promoted-note-ids")).toBe("twin_a");
    expect(metrics.getAttribute("data-promoted-note-id-count")).toBe("1");
    expect(metrics.textContent).toMatch(/note_ids=1/);
  });

  it("clears multi-select and echoes note_ids metrics after promote (my)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 2,
      insight_count: 1,
      question_count: 1,
      notes: [
        {
          note_id: "twin_i",
          asset_id: "paper",
          kind: "insight",
          text: "Insight A",
        },
        {
          note_id: "twin_q",
          asset_id: "paper",
          kind: "question",
          text: "Question B",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    promoteTwinsToContext.mockResolvedValue({
      asset_id: "paper",
      promoted_count: 2,
      context_unit_count: 2,
      promoted: [
        {
          twin_note_id: "twin_i",
          graph_node_id: "insight_i",
          kind: "insight",
          text: "Insight A",
        },
        {
          twin_note_id: "twin_q",
          graph_node_id: "question_q",
          kind: "question",
          text: "Question B",
        },
      ],
      context_units: [
        {
          unit_id: "insight_i",
          twin_note_id: "twin_i",
          kind: "insight",
          text: "Insight A",
        },
        {
          unit_id: "question_q",
          twin_note_id: "twin_q",
          kind: "question",
          text: "Question B",
        },
      ],
      note_ids: ["twin_i", "twin_q"],
      view_format: "html",
      product_panel: "twin_promote_context",
      source: "engagement_spine.twin_promote",
      notes: [],
      html: "<p>promoted</p>",
    });
    render(<TwinNotesPanel assetId="paper" autoLoad />);
    await waitFor(() => {
      expect(screen.getByTestId("twin-select-all-visible")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("twin-select-all-visible"));
    expect(
      screen.getByTestId("twin-selection-count").getAttribute("data-selected-count"),
    ).toBe("2");
    fireEvent.click(screen.getByTestId("twin-promote-selected"));
    await waitFor(() => {
      expect(promoteTwinsToContext).toHaveBeenCalledWith({
        asset_id: "paper",
        include_html: true,
        kinds: null,
        note_ids: ["twin_i", "twin_q"],
      });
    });
    await waitFor(() => {
      expect(
        screen
          .getByTestId("twin-selection-count")
          .getAttribute("data-selected-count"),
      ).toBe("0");
    });
    const metrics = screen.getByTestId("twin-promote-metrics");
    expect(metrics.getAttribute("data-promoted-note-ids")).toBe(
      "twin_i,twin_q",
    );
    expect(metrics.getAttribute("data-promoted-note-id-count")).toBe("2");
    // Promote-selected should be disabled again after clear.
    expect(
      (screen.getByTestId("twin-promote-selected") as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("chases selected twin notes as floating deep research (mz)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 2,
      insight_count: 1,
      question_count: 1,
      notes: [
        {
          note_id: "twin_i",
          asset_id: "paper",
          kind: "insight",
          text: "Claim about X",
        },
        {
          note_id: "twin_q",
          asset_id: "paper",
          kind: "question",
          text: "What follows from X?",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "sess_chase",
      spawn_id: "spn_chase",
      investigation_id: "inv_chase",
      parent_asset_id: "paper",
      window_id: "win_chase",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
      model_id: "model-a",
      research_tier: "deep",
      // Residual (nw): Antiek-bench twin_chase usage passthrough.
      usage_event: {
        task_class: "synthesize",
        outcome: "worked",
        source: "twin_chase",
        prompt_hint: "Twin chase on paper",
      },
    });
    render(
      <TwinNotesPanel assetId="paper" autoLoad researchTier="deep" />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("twin-select-twin_q")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("twin-select-twin_q"));
    fireEvent.click(screen.getByTestId("twin-select-twin_i"));
    fireEvent.click(screen.getByTestId("twin-chase-selected"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "paper",
          view_mode: "floating",
          research_tier: "deep",
          selection_text: expect.stringMatching(/\[question\] What follows from X\?/),
          goal_hint: expect.stringMatching(/Twin chase on paper/),
        }),
      );
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      selection_text: string;
    };
    // Questions ordered before insights in selection_text.
    expect(call.selection_text.indexOf("[question]")).toBeLessThan(
      call.selection_text.indexOf("[insight]"),
    );
    await waitFor(() => {
      expect(screen.getByTestId("twin-chase-status").textContent).toMatch(
        /chased 2 twin note/,
      );
      expect(screen.getByTestId("twin-chase-status").textContent).toMatch(
        /spn_chase/,
      );
      expect(screen.getByTestId("twin-chase-status").textContent).toMatch(
        /model=model-a/,
      );
    });
    // Residual (nc): machine-readable chase metrics.
    const metrics = screen.getByTestId("twin-chase-metrics");
    expect(metrics.getAttribute("data-spawn-id")).toBe("spn_chase");
    expect(metrics.getAttribute("data-session-id")).toBe("sess_chase");
    expect(metrics.getAttribute("data-model-id")).toBe("model-a");
    expect(metrics.getAttribute("data-research-tier")).toBe("deep");
    expect(metrics.getAttribute("data-view-mode")).toBe("floating");
    expect(metrics.getAttribute("data-note-id-count")).toBe("2");
    expect(metrics.getAttribute("data-note-ids")).toMatch(/twin_q/);
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    // Residual (nw): Antiek-bench twin_chase usage metrics.
    expect(metrics.getAttribute("data-usage-source")).toBe("twin_chase");
    expect(metrics.getAttribute("data-usage-task-class")).toBe("synthesize");
    expect(metrics.textContent).toMatch(/bench=twin_chase\/synthesize/);
    // Residual (oe): collective recent-ring honesty after chase.
    expect(metrics.getAttribute("data-collective-recent")).toBe("true");
    expect(metrics.textContent).toMatch(/collective=recent_ring/);
    expect(screen.getByTestId("twin-chase-status").textContent).toMatch(
      /collective=recent_ring/,
    );
    // Selection cleared after successful chase (parity my).
    expect(
      screen
        .getByTestId("twin-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("0");
  });

  it("passes domain-aware research_domains into twin chase goal_hint (aoc)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "pd-fourier",
      notes: [
        {
          note_id: "twin_q",
          kind: "question",
          text: "How does heat conduction map?",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "sess_domain",
      spawn_id: "spn_domain",
      investigation_id: "inv_domain",
      parent_asset_id: "pd-fourier",
      window_id: "win_domain",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
      model_id: "model-b",
      research_tier: "standard",
      usage_event: {
        task_class: "synthesize",
        outcome: "worked",
        source: "twin_chase",
        prompt_hint: "Twin chase on pd-fourier",
      },
    });
    render(
      <TwinNotesPanel
        assetId="pd-fourier"
        autoLoad
        researchTier="standard"
        domainSubjects={["heat", "signal_processing"]}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("twin-select-twin_q")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("twin-select-twin_q"));
    fireEvent.click(screen.getByTestId("twin-chase-selected"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "pd-fourier",
          view_mode: "floating",
          goal_hint: expect.stringMatching(
            /research_domains=heat,signal_processing/,
          ),
        }),
      );
    });
    // Residual (aod): chase metrics audit stamp for domain-aware chase.
    await waitFor(() => {
      expect(
        screen.getByTestId("twin-chase-metrics").getAttribute(
          "data-research-domains",
        ),
      ).toBe("heat,signal_processing");
    });
    expect(screen.getByTestId("twin-chase-metrics").textContent).toMatch(
      /research_domains=heat,signal_processing/,
    );
  });

  it("chases selected twins in full window mode (mz)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 1,
      insight_count: 0,
      question_count: 1,
      notes: [
        {
          note_id: "twin_q",
          asset_id: "paper",
          kind: "question",
          text: "Open Q",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "sess_full",
      spawn_id: "spn_full",
      investigation_id: "inv_full",
      parent_asset_id: "paper",
      window_id: "win_full",
      view_format: "html",
      view_mode: "full",
      status: "reserved",
      model_id: null,
      research_tier: "wrestle",
    });
    render(
      <TwinNotesPanel assetId="paper" autoLoad researchTier="wrestle" />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("twin-select-twin_q")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("twin-select-twin_q"));
    fireEvent.click(screen.getByTestId("twin-chase-selected-full"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "paper",
          view_mode: "full",
          research_tier: "wrestle",
          selection_text: expect.stringMatching(/\[question\] Open Q/),
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("twin-chase-status").textContent).toMatch(
        /mode=full/,
      );
    });
  });

  it("opens twin HTML draft and Write handoff seed (pn/pp)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 2,
      insight_count: 1,
      question_count: 1,
      notes: [
        {
          note_id: "twin_q",
          asset_id: "paper",
          kind: "question",
          text: "Open Q",
        },
        {
          note_id: "twin_i",
          asset_id: "paper",
          kind: "insight",
          text: "Insight",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    render(
      <TwinNotesPanel assetId="paper" autoLoad researchTier="wrestle" />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("twin-select-twin_q")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("twin-select-twin_q"));
    fireEvent.click(screen.getByTestId("twin-select-twin_i"));
    // Residual (atk): multi-select draft HTML CTAs stamp html-first · L3 deferred.
    const draftFloat = screen.getByTestId("twin-draft-selected-html");
    expect(draftFloat.getAttribute("data-html-first")).toBe("true");
    expect(draftFloat.getAttribute("data-view-format")).toBe("html");
    expect(draftFloat.getAttribute("data-multi-select-draft")).toBe("true");
    expect(draftFloat.getAttribute("data-draft-ready")).toBe("true");
    expect(draftFloat.getAttribute("data-selected-count")).toBe("2");
    expect(draftFloat.getAttribute("data-l3-live-seed")).toBe("deferred");
    expect(draftFloat.getAttribute("data-source")).toBe("twin_draft_selected");
    expect(draftFloat.getAttribute("title") || "").toMatch(/never PDF/i);
    expect(
      screen.getByTestId("twin-draft-selected-html-full").getAttribute(
        "data-window-mode",
      ),
    ).toBe("full");
    fireEvent.click(draftFloat);
    await waitFor(() => {
      expect(openWindow).toHaveBeenCalledWith(
        "hosted_html_document",
        expect.objectContaining({
          view_format: "html",
          source: "twin_draft_selected",
          html: expect.stringMatching(/data-twin-draft="true"/),
        }),
        expect.objectContaining({ mode: "floating" }),
      );
    });
    expect(storeTwinWriteSeed).toHaveBeenCalledWith(
      expect.objectContaining({
        asset_id: "paper",
        plain_text: expect.stringMatching(/\[question\] Open Q/),
        note_ids: expect.arrayContaining(["twin_q", "twin_i"]),
        // Residual (adv): explicit has_body into twin write seed.
        has_body: true,
      }),
    );
    const metrics = screen.getByTestId("twin-draft-metrics");
    expect(metrics.getAttribute("data-note-count")).toBe("2");
    // Residual (pt): note_ids provenance on draft metrics.
    expect(metrics.getAttribute("data-note-ids")).toMatch(/twin_q/);
    expect(metrics.getAttribute("data-note-ids")).toMatch(/twin_i/);
    expect(metrics.textContent).toMatch(/note_ids=/);
    expect(metrics.getAttribute("data-has-write-href")).toBe("1");
    expect(metrics.getAttribute("data-write-seed-key")).toBe(
      "antiek.twin_write_seed.testkey",
    );
    // Residual (adi): research_tier on twin draft metrics (depth audit).
    expect(metrics.getAttribute("data-research-tier")).toBe("wrestle");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.textContent).toMatch(/tier=wrestle/);
    const write = screen.getByTestId("twin-draft-open-write");
    expect(write.getAttribute("href")).toBe(
      "/write?twin_seed=antiek.twin_write_seed.testkey",
    );
    expect(write.getAttribute("data-view-format")).toBe("html");
    // Residual (acq): selected note body → has-body true.
    expect(write.getAttribute("data-write-seed-has-body")).toBe("true");
    // Residual (aew): twin draft → Write recursive note-taker path honesty.
    expect(write.getAttribute("data-asset-id")).toBe("paper");
    expect(write.getAttribute("data-note-count")).toBe("2");
    expect(write.getAttribute("data-research-tier")).toBe("wrestle");
    expect(write.getAttribute("data-seamless-twin-write")).toBe("true");
  });

  it("opens twin HTML draft in full working-region window (ps)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 1,
      insight_count: 0,
      question_count: 1,
      notes: [
        {
          note_id: "twin_q",
          asset_id: "paper",
          kind: "question",
          text: "Open Q",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    openWindow.mockReturnValue("win:twin-draft:paper:twin_q:full");
    render(<TwinNotesPanel assetId="paper" autoLoad />);
    await waitFor(() => {
      expect(screen.getByTestId("twin-select-twin_q")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("twin-select-twin_q"));
    fireEvent.click(screen.getByTestId("twin-draft-selected-html-full"));
    await waitFor(() => {
      expect(openWindow).toHaveBeenCalledWith(
        "hosted_html_document",
        expect.objectContaining({
          view_format: "html",
          source: "twin_draft_selected",
        }),
        expect.objectContaining({
          mode: "full",
          id: expect.stringMatching(/:full$/),
        }),
      );
    });
    expect(
      screen.getByTestId("twin-draft-metrics").getAttribute("data-window-mode"),
    ).toBe("full");
    expect(screen.getByTestId("twin-chase-status").textContent).toMatch(
      /mode=full/,
    );
  });

  it("inverts multi-select over visible notes (ne)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 2,
      insight_count: 2,
      question_count: 0,
      notes: [
        {
          note_id: "twin_a",
          asset_id: "paper",
          kind: "insight",
          text: "A",
        },
        {
          note_id: "twin_b",
          asset_id: "paper",
          kind: "insight",
          text: "B",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    render(<TwinNotesPanel assetId="paper" autoLoad />);
    await waitFor(() => {
      expect(screen.getByTestId("twin-invert-selection")).toBeTruthy();
    });
    // Invert empty → select all visible.
    fireEvent.click(screen.getByTestId("twin-invert-selection"));
    expect(
      screen
        .getByTestId("twin-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("2");
    // Invert again → clear all visible.
    fireEvent.click(screen.getByTestId("twin-invert-selection"));
    expect(
      screen
        .getByTestId("twin-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("0");
    // Select one, invert → only the other remains.
    fireEvent.click(screen.getByTestId("twin-select-twin_a"));
    fireEvent.click(screen.getByTestId("twin-invert-selection"));
    expect(
      screen
        .getByTestId("twin-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("1");
    expect(
      (screen.getByTestId("twin-select-twin_b") as HTMLInputElement).checked,
    ).toBe(true);
    expect(
      (screen.getByTestId("twin-select-twin_a") as HTMLInputElement).checked,
    ).toBe(false);
  });

  it("selects all questions or insights in one click (nd)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 3,
      insight_count: 2,
      question_count: 1,
      notes: [
        {
          note_id: "twin_i1",
          asset_id: "paper",
          kind: "insight",
          text: "I1",
        },
        {
          note_id: "twin_i2",
          asset_id: "paper",
          kind: "insight",
          text: "I2",
        },
        {
          note_id: "twin_q1",
          asset_id: "paper",
          kind: "question",
          text: "Q1",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    render(<TwinNotesPanel assetId="paper" autoLoad />);
    await waitFor(() => {
      expect(screen.getByTestId("twin-select-questions")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("twin-select-questions"));
    expect(
      screen
        .getByTestId("twin-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("1");
    expect(
      screen.getByTestId("twin-select-twin_q1").getAttribute("data-selected") ||
        (screen.getByTestId("twin-select-twin_q1") as HTMLInputElement).checked,
    ).toBeTruthy();
    // Select insights accumulates with questions (union).
    fireEvent.click(screen.getByTestId("twin-select-insights"));
    expect(
      screen
        .getByTestId("twin-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("3");
    fireEvent.click(screen.getByTestId("twin-clear-selection"));
    expect(
      screen
        .getByTestId("twin-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("0");
    // Insights only.
    fireEvent.click(screen.getByTestId("twin-select-insights"));
    expect(
      screen
        .getByTestId("twin-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("2");
  });

  it("soft-gates chase when budget would exceed; force unlocks (na)", async () => {
    mockWouldExceed = true;
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 1,
      insight_count: 0,
      question_count: 1,
      notes: [
        {
          note_id: "twin_q",
          asset_id: "paper",
          kind: "question",
          text: "Expensive Q",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "sess_force",
      spawn_id: "spn_force",
      investigation_id: "inv_force",
      parent_asset_id: "paper",
      window_id: "win_force",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
      model_id: "model-a",
      research_tier: "deep",
    });
    render(<TwinNotesPanel assetId="paper" autoLoad researchTier="deep" />);
    await waitFor(() => {
      expect(screen.getByTestId("twin-select-twin_q")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("twin-select-twin_q"));
    await waitFor(() => {
      expect(screen.getByTestId("twin-chase-budget-mount")).toBeTruthy();
      expect(
        screen
          .getByTestId("twin-chase-budget-mount")
          .getAttribute("data-budget-warn"),
      ).toBe("true");
    });
    // Soft-gate: chase buttons disabled until force.
    expect(
      (screen.getByTestId("twin-chase-selected") as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(screen.getByTestId("twin-chase-force-budget")).toBeTruthy();
    fireEvent.click(screen.getByTestId("twin-chase-force-budget"));
    expect(
      (screen.getByTestId("twin-chase-selected") as HTMLButtonElement).disabled,
    ).toBe(false);
    fireEvent.click(screen.getByTestId("twin-chase-selected"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByTestId("twin-chase-status").textContent).toMatch(
        /force_budget/,
      );
    });
  });

  it("loads second asset twins and opens cross-asset merge draft (px)", async () => {
    fetchTwinNotes.mockImplementation(async (assetId: string) => {
      if (assetId === "paper-a") {
        return {
          asset_id: "paper-a",
          note_count: 1,
          insight_count: 0,
          question_count: 1,
          notes: [
            {
              note_id: "twin_a_q",
              asset_id: "paper-a",
              kind: "question",
              text: "Q from A",
            },
          ],
          view_format: "html",
          product_panel: "twin_notes",
          source: "engagement_spine.twin",
          messages: [],
          html: "<p>a</p>",
        };
      }
      if (assetId === "paper-b") {
        return {
          asset_id: "paper-b",
          note_count: 2,
          insight_count: 1,
          question_count: 1,
          notes: [
            {
              note_id: "twin_b_q",
              asset_id: "paper-b",
              kind: "question",
              text: "Q from B",
            },
            {
              note_id: "twin_b_i",
              asset_id: "paper-b",
              kind: "insight",
              text: "I from B",
            },
          ],
          view_format: "html",
          product_panel: "twin_notes",
          source: "engagement_spine.twin",
          messages: [],
          html: "<p>b</p>",
        };
      }
      throw new Error(`unexpected asset ${assetId}`);
    });
    openWindow.mockReturnValue("win:twin-draft:paper-a_paper-b:twin_a_q-twin_b_q");

    render(<TwinNotesPanel assetId="paper-a" autoLoad />);
    await waitFor(() => {
      expect(screen.getByTestId("twin-select-twin_a_q")).toBeTruthy();
    });

    // Merge controls present; merge draft disabled until load + both sides selected.
    expect(screen.getByTestId("twin-cross-asset-merge")).toBeTruthy();
    expect(
      (screen.getByTestId("twin-merge-draft-html") as HTMLButtonElement)
        .disabled,
    ).toBe(true);

    fireEvent.change(screen.getByTestId("twin-merge-asset-id"), {
      target: { value: "paper-b" },
    });
    fireEvent.click(screen.getByTestId("twin-merge-asset-load"));

    await waitFor(() => {
      expect(screen.getByTestId("twin-merge-load-status").textContent).toMatch(
        /paper-b/,
      );
    });
    expect(fetchTwinNotes).toHaveBeenCalledWith("paper-b", {
      includeHtml: true,
    });
    // Secondary notes auto-selected on load.
    expect(
      screen
        .getByTestId("twin-cross-asset-merge")
        .getAttribute("data-merge-selected-count"),
    ).toBe("2");
    expect(screen.getByTestId("twin-merge-select-twin_b_q")).toBeTruthy();

    // Primary still needs selection for cross-asset merge.
    expect(
      (screen.getByTestId("twin-merge-draft-html") as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    fireEvent.click(screen.getByTestId("twin-select-twin_a_q"));
    expect(
      (screen.getByTestId("twin-merge-draft-html") as HTMLButtonElement)
        .disabled,
    ).toBe(false);
    // Residual (atl): cross-asset merge draft CTAs HTML-first · L3 deferred.
    const mergeDraft = screen.getByTestId("twin-merge-draft-html");
    expect(mergeDraft.getAttribute("data-html-first")).toBe("true");
    expect(mergeDraft.getAttribute("data-cross-asset-merge")).toBe("true");
    expect(mergeDraft.getAttribute("data-draft-ready")).toBe("true");
    expect(mergeDraft.getAttribute("data-source")).toBe("twin_cross_asset_merge");
    expect(mergeDraft.getAttribute("data-l3-live-seed")).toBe("deferred");
    expect(mergeDraft.getAttribute("data-merge-bucket-count")).toBe("1");
    expect(mergeDraft.getAttribute("title") || "").toMatch(/never PDF/i);
    expect(
      screen.getByTestId("twin-merge-draft-html-full").getAttribute(
        "data-window-mode",
      ),
    ).toBe("full");

    fireEvent.click(mergeDraft);

    await waitFor(() => {
      expect(openWindow).toHaveBeenCalled();
    });
    const openArgs = openWindow.mock.calls.at(-1);
    expect(openArgs?.[0]).toBe("hosted_html_document");
    expect(openArgs?.[1]).toEqual(
      expect.objectContaining({
        view_format: "html",
        source: "twin_cross_asset_merge",
        html: expect.stringMatching(/data-merge-assets="paper-a\|paper-b"/),
      }),
    );
    expect(openArgs?.[1].html).toMatch(/Q from A/);
    expect(openArgs?.[1].html).toMatch(/Q from B/);
    // Deduped merge includes B insight too (all secondary selected).
    expect(openArgs?.[1].html).toMatch(/I from B/);
    expect(storeTwinWriteSeed).toHaveBeenCalledWith(
      expect.objectContaining({
        asset_id: "paper-a+paper-b",
        note_ids: expect.arrayContaining(["twin_a_q", "twin_b_q", "twin_b_i"]),
        has_body: true,
      }),
    );

    const metrics = screen.getByTestId("twin-draft-metrics");
    expect(metrics.getAttribute("data-source")).toBe("twin_cross_asset_merge");
    expect(metrics.getAttribute("data-merge-assets")).toBe("paper-a|paper-b");
    expect(metrics.getAttribute("data-note-count")).toBe("3");
    expect(screen.getByTestId("twin-draft-open-write")).toBeTruthy();
    expect(screen.getByTestId("twin-chase-status").textContent).toMatch(
      /cross-asset/i,
    );
  });

  it("rejects merge asset_id equal to current asset (px)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 0,
      insight_count: 0,
      question_count: 0,
      notes: [],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "",
    });
    render(<TwinNotesPanel assetId="paper" autoLoad />);
    await waitFor(() => {
      expect(screen.getByTestId("twin-merge-asset-id")).toBeTruthy();
    });
    fireEvent.change(screen.getByTestId("twin-merge-asset-id"), {
      target: { value: "paper" },
    });
    fireEvent.click(screen.getByTestId("twin-merge-asset-load"));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(
        /must differ from the current asset/i,
      );
    });
    // Should not have called fetch for the merge load (only autoLoad primary).
    expect(
      fetchTwinNotes.mock.calls.filter((c) => c[0] === "paper"),
    ).toHaveLength(1);
  });

  it("accumulates N>2 merge assets into one cross-asset draft (qb)", async () => {
    fetchTwinNotes.mockImplementation(async (assetId: string) => {
      if (assetId === "paper-a") {
        return {
          asset_id: "paper-a",
          note_count: 1,
          insight_count: 0,
          question_count: 1,
          notes: [
            {
              note_id: "twin_a_q",
              asset_id: "paper-a",
              kind: "question",
              text: "Q from A",
            },
          ],
          view_format: "html",
          product_panel: "twin_notes",
          source: "engagement_spine.twin",
          messages: [],
          html: "<p>a</p>",
        };
      }
      if (assetId === "paper-b") {
        return {
          asset_id: "paper-b",
          note_count: 1,
          insight_count: 0,
          question_count: 1,
          notes: [
            {
              note_id: "twin_b_q",
              asset_id: "paper-b",
              kind: "question",
              text: "Q from B",
            },
          ],
          view_format: "html",
          product_panel: "twin_notes",
          source: "engagement_spine.twin",
          messages: [],
          html: "<p>b</p>",
        };
      }
      if (assetId === "paper-c") {
        return {
          asset_id: "paper-c",
          note_count: 1,
          insight_count: 1,
          question_count: 0,
          notes: [
            {
              note_id: "twin_c_i",
              asset_id: "paper-c",
              kind: "insight",
              text: "I from C",
            },
          ],
          view_format: "html",
          product_panel: "twin_notes",
          source: "engagement_spine.twin",
          messages: [],
          html: "<p>c</p>",
        };
      }
      throw new Error(`unexpected ${assetId}`);
    });

    render(<TwinNotesPanel assetId="paper-a" autoLoad />);
    await waitFor(() => {
      expect(screen.getByTestId("twin-select-twin_a_q")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("twin-select-twin_a_q"));

    fireEvent.change(screen.getByTestId("twin-merge-asset-id"), {
      target: { value: "paper-b" },
    });
    fireEvent.click(screen.getByTestId("twin-merge-asset-load"));
    await waitFor(() => {
      expect(screen.getByTestId("twin-merge-bucket-paper-b")).toBeTruthy();
    });
    fireEvent.change(screen.getByTestId("twin-merge-asset-id"), {
      target: { value: "paper-c" },
    });
    fireEvent.click(screen.getByTestId("twin-merge-asset-load"));
    await waitFor(() => {
      expect(screen.getByTestId("twin-merge-bucket-paper-c")).toBeTruthy();
    });
    expect(
      screen
        .getByTestId("twin-cross-asset-merge")
        .getAttribute("data-merge-asset-count"),
    ).toBe("2");
    expect(screen.getByTestId("twin-merge-load-status").textContent).toMatch(
      /paper-c/,
    );
    expect(screen.getByTestId("twin-merge-bucket-paper-b")).toBeTruthy();
    expect(screen.getByTestId("twin-merge-bucket-paper-c")).toBeTruthy();

    fireEvent.click(screen.getByTestId("twin-merge-draft-html"));
    await waitFor(() => {
      expect(openWindow).toHaveBeenCalled();
    });
    const html = openWindow.mock.calls.at(-1)?.[1]?.html as string;
    expect(html).toMatch(/data-merge-assets="paper-a\|paper-b\|paper-c"/);
    expect(html).toMatch(/Q from A/);
    expect(html).toMatch(/Q from B/);
    expect(html).toMatch(/I from C/);
    expect(storeTwinWriteSeed).toHaveBeenCalledWith(
      expect.objectContaining({
        asset_id: "paper-a+paper-b+paper-c",
        has_body: true,
      }),
    );
  });

  it("passes chase selection as driver badge promptText (qi)", async () => {
    fetchTwinNotes.mockResolvedValue({
      asset_id: "paper",
      note_count: 1,
      insight_count: 0,
      question_count: 1,
      notes: [
        {
          note_id: "twin_q_qi",
          asset_id: "paper",
          kind: "question",
          text: "Does promptText project budget?",
        },
      ],
      view_format: "html",
      product_panel: "twin_notes",
      source: "engagement_spine.twin",
      messages: [],
      html: "<p>twins</p>",
    });
    render(<TwinNotesPanel assetId="paper" autoLoad researchTier="deep" />);
    await waitFor(() => {
      expect(screen.getByTestId("twin-select-twin_q_qi")).toBeTruthy();
    });
    expect(
      screen
        .getByTestId("mock-decision-tree-driver-badge")
        .getAttribute("data-prompt-len"),
    ).toBe("0");
    fireEvent.click(screen.getByTestId("twin-select-twin_q_qi"));
    expect(
      Number(
        screen
          .getByTestId("mock-decision-tree-driver-badge")
          .getAttribute("data-prompt-len") || 0,
      ),
    ).toBeGreaterThan(10);
  });

});
