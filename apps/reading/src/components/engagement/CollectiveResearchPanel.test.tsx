import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearCollectiveUnitMembership,
  storeCollectiveUnitMembership,
} from "../../workspace/collectiveUnitMembership";
import {
  buildCollectiveUnitPromptHtml,
  CollectiveResearchPanel,
} from "./CollectiveResearchPanel";

const fetchCollectiveResearch = vi.fn();
const mergeSpawnOutputs = vi.fn();
const seedTwinNotes = vi.fn();
const openWindow = vi.fn(() => "win:analysis:draft_1");
const launchFloatingDeepResearch = vi.fn();

vi.mock("../../api/engagement", () => ({
  fetchCollectiveResearch: (...args: unknown[]) => fetchCollectiveResearch(...args),
  mergeSpawnOutputs: (...args: unknown[]) => mergeSpawnOutputs(...args),
  seedTwinNotes: (...args: unknown[]) => seedTwinNotes(...args),
}));

vi.mock("../windows/openWindow", () => ({
  openWindow: (...args: unknown[]) => openWindow(...args),
}));

vi.mock("../../modes/Reading/launchFloatingDeepResearch", () => ({
  launchFloatingDeepResearch: (...args: unknown[]) =>
    launchFloatingDeepResearch(...args),
}));

const fetchDepthTiers = vi.hoisted(() =>
  vi.fn(async () => ({
    active_depth_tier: null as string | null,
    active_preset: null,
    presets: [],
    projection_hints: null,
    view_format: "html" as const,
    settings_panel: "depth_tier_presets",
    source: "test",
    notes: [] as string[],
  })),
);

vi.mock("../../api/settings", () => ({
  fetchDepthTiers: (...args: unknown[]) => fetchDepthTiers(...args),
}));

vi.mock("./DecisionTreeDriverBadge", () => ({
  DecisionTreeDriverBadge: (props: {
    researchTier?: string | null;
    promptText?: string | null;
  }) => (
    <div
      data-testid="decision-tree-driver-badge-stub"
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
      data-prompt-len={String((props.promptText || "").length)}
    >
      driver badge
    </div>
  ),
}));

vi.mock("./ResearchLaunchBudgetPanel", () => {
  const React = require("react") as typeof import("react");
  return {
    ResearchLaunchBudgetPanel: (props: {
      promptText: string;
      researchTier?: string;
      allowTierPick?: boolean;
      onProjectionChange?: (p: {
        wouldExceedBudget: boolean | null;
        pricingKnown: boolean;
        estimatedUsdHigh: number | null;
        remainingUsd: number | null;
        modelId: string | null;
      }) => void;
    }) => {
      React.useEffect(() => {
        props.onProjectionChange?.({
          wouldExceedBudget: false,
          pricingKnown: true,
          estimatedUsdHigh: 0.1,
          remainingUsd: 5,
          modelId: null,
        });
      }, [props.onProjectionChange]);
      return (
        <div
          data-testid="research-launch-budget-panel-stub"
          data-research-tier={props.researchTier || "deep"}
          data-allow-tier-pick={props.allowTierPick ? "true" : "false"}
        >
          budget len={props.promptText.length}
        </div>
      );
    },
  };
});

describe("CollectiveResearchPanel", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    clearCollectiveUnitMembership();
    fetchDepthTiers.mockReset().mockResolvedValue({
      active_depth_tier: null,
      active_preset: null,
      presets: [],
      projection_hints: null,
      view_format: "html",
      settings_panel: "depth_tier_presets",
      source: "test",
      notes: [],
    });
    fetchCollectiveResearch.mockReset();
    mergeSpawnOutputs.mockReset();
    seedTwinNotes.mockReset();
    seedTwinNotes.mockResolvedValue({
      asset_id: "draft_analysis_1",
      seeded: true,
      view_format: "html",
      notes: [],
      insight_count: 1,
      question_count: 1,
    });
    openWindow.mockClear();
    launchFloatingDeepResearch.mockReset();
  });

  it("auto-selects preferredSpawnId when available (cn)", () => {
    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_1", "spn_2"]}
        preferredSpawnId="spn_2"
      />,
    );
    const boxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    expect(boxes[0].checked).toBe(false);
    expect(boxes[1].checked).toBe(true);
  });

  it("stamps L6 live multi-agent deferred honesty + checklist deep-link (vx/wi)", () => {
    render(
      <CollectiveResearchPanel availableSpawnIds={["spn_1", "spn_2"]} />,
    );
    const panel = screen.getByTestId("collective-research-panel");
    expect(panel.getAttribute("data-l6-live-multiagent")).toBe("deferred");
    expect(panel.getAttribute("data-offline-merge-unit")).toBe("true");
    const honesty = screen.getByTestId("collective-l6-honesty");
    expect(honesty.getAttribute("data-l6-live-multiagent")).toBe("deferred");
    expect(honesty.getAttribute("data-offline-merge-unit")).toBe("true");
    expect(honesty.textContent).toMatch(/L6 live multi-agent council/i);
    expect(honesty.textContent).toMatch(/offline merge unit only/i);
    // Residual (wi): L6 checklist deep-link (parity Settings dual-gate wh).
    const l6 = screen.getByTestId("collective-l6-checklist-link");
    expect(l6.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4.*#l6-collective/);
    expect(l6.textContent).toMatch(/L6 checklist/i);
  });

  it("links to Settings for driver & budget (ig)", () => {
    render(
      <CollectiveResearchPanel availableSpawnIds={["spn_1", "spn_2"]} />,
    );
    const link = screen.getByTestId("collective-settings-link");
    expect(link.getAttribute("href")).toBe("/settings#decision-tree-panel");
    expect(link.textContent).toMatch(/driver & budget/i);
    // Residual (lg): DecisionTreeDriverBadge mount with researchTier default deep.
    expect(screen.getByTestId("collective-driver-badge-mount")).toBeTruthy();
    expect(
      screen
        .getByTestId("collective-driver-badge-mount")
        .getAttribute("data-research-tier"),
    ).toBe("deep");
    expect(
      screen
        .getByTestId("decision-tree-driver-badge-stub")
        .getAttribute("data-research-tier"),
    ).toBe("deep");
  });

  it("merges selected spawns into collective prompt", async () => {
    fetchCollectiveResearch.mockResolvedValue({
      collective_id: "col_abc",
      spawn_ids: ["spn_1", "spn_2"],
      asset_ids: ["a", "b"],
      investigation_ids: [],
      twin_units: [],
      source_references: [],
      view_format: "html",
      spawn_count: 2,
      twin_count: 0,
      ref_count: 0,
      prompt_block: "# Collective deep-research unit `col_abc`\n",
      // Residual (oj): bench usage from multi-spawn merge.
      usage_event: {
        source: "collective_merge",
        task_class: "synthesize",
        outcome: "worked",
      },
    });

    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_1", "spn_2", "spn_3"]}
        parentAssetId="asset_x"
      />,
    );

    const boxes = screen.getAllByRole("checkbox");
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);
    fireEvent.click(screen.getByTestId("collective-merge-prompt"));

    await waitFor(() => {
      expect(screen.getByTestId("collective-prompt-block").textContent).toContain(
        "col_abc",
      );
    });
    expect(fetchCollectiveResearch).toHaveBeenCalledWith({
      spawn_ids: ["spn_1", "spn_2"],
    });
    // Residual (hm): machine-readable multi-spawn collective metrics.
    const metrics = screen.getByTestId("collective-unit-metrics");
    expect(metrics.getAttribute("data-collective-id")).toBe("col_abc");
    expect(metrics.getAttribute("data-spawn-count")).toBe("2");
    expect(metrics.getAttribute("data-twin-count")).toBe("0");
    expect(metrics.getAttribute("data-ref-count")).toBe("0");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.textContent).toMatch(/Collective unit/);
    // Residual (oj): Antiek-bench usage on collective unit metrics.
    expect(metrics.getAttribute("data-usage-source")).toBe("collective_merge");
    expect(metrics.getAttribute("data-usage-task-class")).toBe("synthesize");
    expect(metrics.textContent).toMatch(/bench=collective_merge\/synthesize/);
    // Residual (tr): float|full cohesive unit prompt HTML (no invented server doc).
    fireEvent.click(screen.getByTestId("collective-unit-open-float"));
    expect(openWindow).toHaveBeenCalled();
    const floatCall = openWindow.mock.calls.at(-1) as [
      string,
      {
        source?: string;
        html?: string;
        view_format?: string;
        collective_id?: string;
        spawn_count?: number;
      },
      { mode?: string },
    ];
    expect(floatCall[0]).toBe("hosted_html_document");
    expect(floatCall[1].source).toBe("collective_unit_prompt");
    expect(floatCall[1].view_format).toBe("html");
    expect(floatCall[1].collective_id).toBe("col_abc");
    expect(floatCall[1].spawn_count).toBe(2);
    expect(floatCall[1].html).toMatch(/data-source="collective_unit_prompt"/);
    expect(floatCall[1].html).toMatch(/Cohesive prompt_block/);
    expect(floatCall[1].html).toMatch(/col_abc/);
    expect(floatCall[2].mode).toBe("floating");
    fireEvent.click(screen.getByTestId("collective-unit-open-full"));
    const fullCall = openWindow.mock.calls.at(-1) as [
      string,
      { source?: string },
      { mode?: string },
    ];
    expect(fullCall[1].source).toBe("collective_unit_prompt");
    expect(fullCall[2].mode).toBe("full");
    // Residual (aeh/afa): unit prompt → Open Write twin_seed + path honesty.
    const unitWrite = screen.getByTestId("collective-unit-open-write");
    expect(unitWrite.getAttribute("data-view-format")).toBe("html");
    expect(unitWrite.getAttribute("data-write-seed-has-body")).toBe("true");
    expect(unitWrite.getAttribute("data-has-twin-seed")).toBe("1");
    expect(unitWrite.getAttribute("data-collective-id")).toBe("col_abc");
    expect(unitWrite.getAttribute("data-l6-live-multiagent")).toBe("deferred");
    expect(unitWrite.getAttribute("href")).toMatch(
      /^\/write\?twin_seed=antiek\.twin_write_seed\./,
    );
    // Residual (afa): multi-select cohesive unit → Write path honesty.
    expect(unitWrite.getAttribute("data-seamless-unit-write")).toBe("true");
    expect(unitWrite.getAttribute("data-spawn-count")).toBe("2");
    expect(unitWrite.getAttribute("data-parent-asset-id")).toBe("asset_x");
    // Residual (jf): depth prefill none when Settings unset.
    await waitFor(() => {
      expect(
        screen
          .getByTestId("collective-continue-budget-mount")
          .getAttribute("data-depth-prefill"),
      ).toBe("none");
    });
  });

  it("builds collective unit prompt HTML pure helper (tr)", () => {
    const html = buildCollectiveUnitPromptHtml({
      collectiveId: "col_x",
      promptBlock: "Synthesize A + B",
      spawnCount: 2,
      twinCount: 4,
      refCount: 1,
      researchTier: "wrestle",
      spawnIds: ["spn_a", "spn_b"],
    });
    expect(html).toMatch(/data-source="collective_unit_prompt"/);
    expect(html).toMatch(/data-view-format="html"/);
    expect(html).toMatch(/collective=col_x/);
    expect(html).toMatch(/spawns=2/);
    expect(html).toMatch(/Synthesize A \+ B/);
    expect(html).toMatch(/spawn_ids=spn_a, spn_b/);
    expect(html).not.toMatch(/%pdf/i);
  });

  it("prefills collective continue depth from Settings wrestle (jf)", async () => {
    fetchDepthTiers.mockResolvedValue({
      active_depth_tier: "wrestle",
      active_preset: null,
      presets: [],
      projection_hints: null,
      view_format: "html",
      settings_panel: "depth_tier_presets",
      source: "test",
      notes: [],
    });
    fetchCollectiveResearch.mockResolvedValue({
      collective_id: "col_w",
      spawn_ids: ["spn_1", "spn_2"],
      asset_ids: ["a", "b"],
      investigation_ids: [],
      twin_units: [],
      source_references: [],
      view_format: "html",
      spawn_count: 2,
      twin_count: 0,
      ref_count: 0,
      prompt_block: "# Collective unit col_w\n",
      // Residual (ke): member tiers; recommended depth-max.
      research_tiers: ["deep", "wrestle"],
      recommended_research_tier: "wrestle",
    });
    render(
      <CollectiveResearchPanel availableSpawnIds={["spn_1", "spn_2"]} />,
    );
    const boxes = screen.getAllByRole("checkbox");
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);
    fireEvent.click(screen.getByTestId("collective-merge-prompt"));
    await waitFor(() => {
      const mount = screen.getByTestId("collective-continue-budget-mount");
      expect(mount.getAttribute("data-depth-prefill")).toBe("installed");
      expect(mount.getAttribute("data-research-tier")).toBe("wrestle");
    });
    expect(screen.getByTestId("collective-depth-prefill").textContent).toMatch(
      /installed.*wrestle/i,
    );
    // Residual (ke): metrics + recommended tier chrome.
    expect(
      screen
        .getByTestId("collective-unit-metrics")
        .getAttribute("data-recommended-research-tier"),
    ).toBe("wrestle");
    expect(screen.getByTestId("collective-recommended-tier").textContent).toBe(
      "wrestle",
    );
    expect(
      screen
        .getByTestId("research-launch-budget-panel-stub")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
  });

  it("continues collective prompt as floating deep research unit (dc)", async () => {
    fetchCollectiveResearch.mockResolvedValue({
      collective_id: "col_dc",
      spawn_ids: ["spn_1", "spn_2"],
      asset_ids: ["asset_parent"],
      investigation_ids: [],
      twin_units: [],
      source_references: [],
      view_format: "html",
      spawn_count: 2,
      twin_count: 1,
      ref_count: 0,
      prompt_block: "# Collective unit col_dc\nInsights and questions…",
    });
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "fsess_col",
      spawn_id: "spn_new",
      investigation_id: "inv_col",
      parent_asset_id: "book-1",
      window_id: "wdr_col_unit",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
      model_id: null,
    });

    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_1", "spn_2"]}
        parentAssetId="book-1"
      />,
    );
    const boxes = screen.getAllByRole("checkbox");
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);
    fireEvent.click(screen.getByTestId("collective-merge-prompt"));
    await waitFor(() => {
      expect(screen.getByTestId("collective-continue-as-unit")).toBeTruthy();
    });
    // Residual (adk): continue-as-unit is offline unit re-entry — L6 deferred.
    const contFloat = screen.getByTestId("collective-continue-as-unit");
    expect(contFloat.getAttribute("data-l6-live-multiagent")).toBe("deferred");
    expect(contFloat.getAttribute("data-window-mode")).toBe("floating");
    expect(contFloat.getAttribute("data-view-format")).toBe("html");
    // Residual (afh): unit re-entry → DR path honesty stamps.
    expect(contFloat.getAttribute("data-collective-id")).toBe("col_dc");
    expect(contFloat.getAttribute("data-parent-asset-id")).toBe("book-1");
    expect(contFloat.getAttribute("data-seamless-unit-continue")).toBe("true");
    expect(Number(contFloat.getAttribute("data-spawn-count") || "0")).toBeGreaterThanOrEqual(
      1,
    );
    const contFull = screen.getByTestId("collective-continue-as-unit-full");
    expect(contFull.getAttribute("data-l6-live-multiagent")).toBe("deferred");
    expect(contFull.getAttribute("data-window-mode")).toBe("full");
    expect(contFull.getAttribute("data-collective-id")).toBe("col_dc");
    expect(contFull.getAttribute("data-parent-asset-id")).toBe("book-1");
    expect(contFull.getAttribute("data-seamless-unit-continue")).toBe("true");
    expect(screen.getByTestId("collective-continue-budget-mount")).toBeTruthy();
    expect(screen.getByTestId("research-launch-budget-panel-stub")).toBeTruthy();
    fireEvent.click(screen.getByTestId("collective-continue-as-unit"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "book-1",
          view_mode: "floating",
        }),
      );
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      selection_text: string;
      goal_hint: string;
    };
    expect(call.selection_text).toMatch(/col_dc/);
    expect(call.goal_hint).toMatch(/col_dc/);
    await waitFor(() => {
      expect(screen.getByTestId("collective-continue-window-id").textContent).toMatch(
        /wdr_col_unit/,
      );
    });
    // Residual (afk): post-continue path audit stamps.
    const contWin = screen.getByTestId("collective-continue-window-id");
    expect(contWin.getAttribute("data-window-id")).toMatch(/wdr_col_unit/);
    expect(contWin.getAttribute("data-collective-id")).toBe("col_dc");
    expect(contWin.getAttribute("data-parent-asset-id")).toBe("book-1");
    expect(contWin.getAttribute("data-seamless-unit-continue")).toBe("true");
    expect(contWin.getAttribute("data-l6-live-multiagent")).toBe("deferred");
    expect(contWin.textContent).toMatch(/offline unit re-entry/i);

    // Residual (ey): full working-region continue.
    launchFloatingDeepResearch.mockClear();
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "fsess_col_full",
      spawn_id: "spn_full",
      investigation_id: "inv_col_full",
      parent_asset_id: "book-1",
      window_id: "wdr_col_full",
      view_format: "html",
      view_mode: "full",
      status: "reserved",
      model_id: null,
    });
    fireEvent.click(screen.getByTestId("collective-continue-as-unit-full"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "book-1",
          view_mode: "full",
        }),
      );
    });
  });

  it("merges selected spawns to draft document when parentAssetId set", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "book-1",
      document_id: "draft_book-1_deadbeef",
      source_spawn_ids: ["spn_1"],
      sections_merged: 2,
      draft_leaves_parent: true,
      parent_document_id: "book-1",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: ["Draft-combined document; parent asset unchanged until into_parent merge."],
      html: "<p>Merge mode: draft_combined</p>",
    });

    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_1", "spn_2"]}
        parentAssetId="book-1"
      />,
    );

    expect(screen.getByTestId("collective-parent-asset").textContent).toMatch(
      /book-1/,
    );
    expect(
      screen
        .getByTestId("collective-research-panel")
        .getAttribute("data-auto-open-draft"),
    ).toBe("true");
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.click(screen.getByTestId("collective-merge-draft"));

    await waitFor(() => {
      expect(screen.getByTestId("collective-doc-merge-result").textContent).toMatch(
        /draft_combined/,
      );
    });
    expect(mergeSpawnOutputs).toHaveBeenCalledWith({
      parent_asset_id: "book-1",
      spawn_ids: ["spn_1"],
      mode: "draft_combined",
      include_html: true,
    });
    expect(screen.getByTestId("collective-doc-merge-html").innerHTML).toMatch(
      /draft_combined/,
    );
    expect(
      screen.getByTestId("collective-research-panel").getAttribute("data-view-format"),
    ).toBe("html");
    // Residual (eo): twin notes seeded on draft merge document.
    await waitFor(() => {
      expect(seedTwinNotes).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "draft_book-1_deadbeef",
          force_offline: true,
          source_spawn_id: "spn_1",
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("collective-doc-merge-result").textContent).toMatch(
        /Twin notes seeded|Twin seed/,
      );
    });
    // Residual (em): draft_combined auto-opens hosted HTML without extra click.
    await waitFor(() => {
      expect(openWindow).toHaveBeenCalledWith(
        "hosted_html_document",
        expect.objectContaining({
          document_id: "draft_book-1_deadbeef",
          view_format: "html",
          source: "collective_doc_merge",
        }),
        expect.objectContaining({
          id: "win:collective-merge:draft_book-1_deadbeef",
          mode: "floating",
        }),
      );
    });
    expect(screen.getByTestId("collective-auto-open-window").textContent).toMatch(
      /win:analysis:draft_1/,
    );
  });

  it("notifies onDocMerged after draft merge with twin seed (ep)", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "book-1",
      document_id: "draft_ep",
      source_spawn_ids: ["spn_1"],
      sections_merged: 1,
      draft_leaves_parent: true,
      parent_document_id: "book-1",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: ["Draft"],
      html: "<p>ep</p>",
    });
    const onDocMerged = vi.fn();
    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_1"]}
        parentAssetId="book-1"
        onDocMerged={onDocMerged}
        autoOpenDraft={false}
      />,
    );
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.click(screen.getByTestId("collective-merge-draft"));
    await waitFor(() => {
      expect(onDocMerged).toHaveBeenCalled();
    });
    expect(onDocMerged.mock.calls[0][0].document_id).toBe("draft_ep");
    expect(onDocMerged.mock.calls[0][0].view_format).toBe("html");
    expect(seedTwinNotes).toHaveBeenCalled();
  });

  it("does not auto-open collective draft when autoOpenDraft is false", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "book-1",
      document_id: "draft_manual",
      source_spawn_ids: ["spn_1"],
      sections_merged: 1,
      draft_leaves_parent: true,
      parent_document_id: "book-1",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: ["Draft"],
      html: "<p>Manual</p>",
    });
    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_1"]}
        parentAssetId="book-1"
        autoOpenDraft={false}
      />,
    );
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.click(screen.getByTestId("collective-merge-draft"));
    await waitFor(() => {
      expect(screen.getByTestId("collective-open-analysis-window")).toBeTruthy();
    });
    expect(openWindow).not.toHaveBeenCalled();
    expect(screen.queryByTestId("collective-auto-open-window")).toBeNull();
  });

  it("disables document merge without parentAssetId", () => {
    render(
      <CollectiveResearchPanel availableSpawnIds={["spn_1"]} />,
    );
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    expect(
      (screen.getByTestId("collective-merge-draft") as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(
      (screen.getByTestId("collective-merge-parent") as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(
      (screen.getByTestId("collective-written-analysis") as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("creates written analysis draft from collective + draft merge (cf)", async () => {
    fetchCollectiveResearch.mockResolvedValue({
      collective_id: "col_analysis",
      spawn_ids: ["spn_1", "spn_2"],
      asset_ids: ["a", "b"],
      investigation_ids: [],
      twin_units: [],
      source_references: [],
      view_format: "html",
      spawn_count: 2,
      twin_count: 1,
      ref_count: 0,
      prompt_block: "# Collective deep-research unit `col_analysis`\n",
    });
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "book-1",
      document_id: "draft_analysis_1",
      source_spawn_ids: ["spn_1", "spn_2"],
      sections_merged: 3,
      draft_leaves_parent: true,
      parent_document_id: "book-1",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: ["Draft-combined document"],
      html: "<p>Written analysis draft HTML</p>",
    });

    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_1", "spn_2"]}
        parentAssetId="book-1"
      />,
    );
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.click(screen.getAllByRole("checkbox")[1]);
    fireEvent.click(screen.getByTestId("collective-written-analysis"));

    await waitFor(() => {
      expect(fetchCollectiveResearch).toHaveBeenCalledWith({
        spawn_ids: ["spn_1", "spn_2"],
      });
    });
    await waitFor(() => {
      expect(mergeSpawnOutputs).toHaveBeenCalledWith({
        parent_asset_id: "book-1",
        spawn_ids: ["spn_1", "spn_2"],
        mode: "draft_combined",
        include_html: true,
      });
    });
    await waitFor(() => {
      expect(seedTwinNotes).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "draft_analysis_1",
          force_offline: true,
        }),
      );
    });
    await waitFor(() => {
      expect(
        screen.getByTestId("collective-doc-merge-result").textContent,
      ).toMatch(/written analysis|draft_combined|Twin notes seeded/i);
    });
    expect(screen.getByTestId("collective-prompt-block").textContent).toMatch(
      /col_analysis/,
    );
    // Residual (em): written analysis draft auto-opens (manual button still present).
    await waitFor(() => {
      expect(openWindow).toHaveBeenCalledWith(
        "hosted_html_document",
        expect.objectContaining({
          document_id: "draft_analysis_1",
          view_format: "html",
          source: "collective_written_analysis",
        }),
        expect.objectContaining({
          id: "win:analysis:draft_analysis_1",
          mode: "floating",
        }),
      );
    });
    expect(screen.getByTestId("collective-auto-open-window")).toBeTruthy();
    expect(screen.getByTestId("collective-open-analysis-window")).toBeTruthy();
    // Residual (fn/qe/acm/afg): Write dual handoff preserves written analysis source.
    const write = screen.getByTestId("collective-open-write");
    expect(write.getAttribute("href") || "").toMatch(/html_draft=draft_analysis_1/);
    expect(write.getAttribute("href") || "").toMatch(/twin_seed=antiek\.twin_write_seed\./);
    expect(write.getAttribute("data-has-twin-seed")).toBe("1");
    expect(write.getAttribute("data-write-seed-has-body")).toBe("true");
    // Residual (afg): do not collapse analysis to collective_doc_merge Write seed.
    expect(write.getAttribute("data-write-seed-source")).toBe(
      "collective_written_analysis",
    );
    expect(write.getAttribute("data-analysis-write")).toBe("true");
    expect(write.textContent).toMatch(/Open Write \(written analysis\)/i);
    expect(write.getAttribute("title") || "").toMatch(/written analysis/i);
    // Session seed must also preserve analysis source (not collective_doc_merge).
    const twinKey = (write.getAttribute("href") || "").match(
      /twin_seed=(antiek\.twin_write_seed\.[^&]+)/,
    )?.[1];
    expect(twinKey).toBeTruthy();
    const raw = sessionStorage.getItem(twinKey!);
    expect(raw).toBeTruthy();
    const seed = JSON.parse(raw!) as { source?: string; title?: string };
    expect(seed.source).toBe("collective_written_analysis");
    expect(seed.title || "").toMatch(/Written analysis/i);
  });

  it("links dual-gate L1–L4 checklist for L6 collective prep (nl)", () => {
    render(
      <CollectiveResearchPanel availableSpawnIds={["spn_1"]} parentAssetId="p" />,
    );
    const dual = screen.getByTestId("collective-dual-gate-checklist-link");
    // Residual (xg/aat): L6 collective checklist section deep-link + label honesty.
    expect(dual.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4.*#l6-collective/);
    expect(dual.textContent).toMatch(/L6 collective checklist/i);
  });

  it("auto-selects newest recent_ring spawn when selection empty (ol)", async () => {
    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_open", "spn_newest", "spn_older"]}
        parentAssetId="parent"
        recentSpawnIds={["spn_newest", "spn_older"]}
        // no preferredSpawnId
      />,
    );
    await waitFor(() => {
      expect(
        screen
          .getByTestId("collective-selection-count")
          .getAttribute("data-selected-count"),
      ).toBe("1");
    });
    expect(
      (screen.getByTestId("collective-select-spn_newest") as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(
      (screen.getByTestId("collective-select-spn_open") as HTMLInputElement)
        .checked,
    ).toBe(false);
    // Clear selection — does not re-auto-select same newest.
    fireEvent.click(screen.getByTestId("collective-clear-selection"));
    expect(
      screen
        .getByTestId("collective-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("0");
    // Still empty after a tick (same newest).
    await waitFor(() => {
      expect(
        screen
          .getByTestId("collective-selection-count")
          .getAttribute("data-selected-count"),
      ).toBe("0");
    });
  });

  it("does not auto-select recent when preferredSpawnId is set (ol)", () => {
    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_pref", "spn_newest"]}
        preferredSpawnId="spn_pref"
        recentSpawnIds={["spn_newest"]}
      />,
    );
    expect(
      (screen.getByTestId("collective-select-spn_pref") as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(
      (screen.getByTestId("collective-select-spn_newest") as HTMLInputElement)
        .checked,
    ).toBe(false);
  });

  it("selects only recent_ring spawns in one click (og)", () => {
    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_open", "spn_chased", "spn_other"]}
        parentAssetId="parent"
        recentSpawnIds={["spn_chased", "spn_other"]}
      />,
    );
    expect(
      (screen.getByTestId("collective-select-recent") as HTMLButtonElement)
        .disabled,
    ).toBe(false);
    fireEvent.click(screen.getByTestId("collective-select-recent"));
    expect(
      screen
        .getByTestId("collective-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("2");
    expect(
      (screen.getByTestId("collective-select-spn_chased") as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(
      (screen.getByTestId("collective-select-spn_other") as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(
      (screen.getByTestId("collective-select-spn_open") as HTMLInputElement)
        .checked,
    ).toBe(false);
  });

  it("marks available spawns from recent_ring with origin badge (of)", async () => {
    const {
      pushRecentDeepResearchSpawnId,
      clearRecentDeepResearchSpawnIds,
    } = await import("../../workspace/recentDeepResearchSpawns");
    clearRecentDeepResearchSpawnIds();
    pushRecentDeepResearchSpawnId("spn_chased");
    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_open", "spn_chased"]}
        parentAssetId="parent"
        recentSpawnIds={["spn_chased"]}
      />,
    );
    const list = screen.getByTestId("collective-spawn-list");
    expect(list.getAttribute("data-recent-in-available")).toBe("1");
    expect(
      screen
        .getByTestId("collective-spawn-row-spn_chased")
        .getAttribute("data-origin-recent"),
    ).toBe("true");
    expect(
      screen
        .getByTestId("collective-spawn-row-spn_open")
        .getAttribute("data-origin-recent"),
    ).toBe("false");
    expect(screen.getByTestId("collective-origin-recent-spn_chased").textContent).toMatch(
      /recent/i,
    );
    expect(
      screen
        .getByTestId("collective-selection-count")
        .getAttribute("data-recent-in-available"),
    ).toBe("1");
    clearRecentDeepResearchSpawnIds();
  });

  it("clears recent closed-window spawns (oc)", async () => {
    const {
      pushRecentDeepResearchSpawnId,
      listRecentDeepResearchSpawnIds,
      clearRecentDeepResearchSpawnIds,
    } = await import("../../workspace/recentDeepResearchSpawns");
    clearRecentDeepResearchSpawnIds();
    pushRecentDeepResearchSpawnId("spn_recent");
    expect(listRecentDeepResearchSpawnIds()).toContain("spn_recent");
    const onRecentSpawnsCleared = vi.fn();
    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_a", "spn_recent"]}
        parentAssetId="parent"
        onRecentSpawnsCleared={onRecentSpawnsCleared}
      />,
    );
    const clearRecent = screen.getByTestId("collective-clear-recent-spawns");
    expect(clearRecent.getAttribute("disabled")).toBeNull();
    expect(
      screen
        .getByTestId("collective-select-controls")
        .getAttribute("data-recent-count"),
    ).toBe("1");
    fireEvent.click(clearRecent);
    expect(listRecentDeepResearchSpawnIds()).toEqual([]);
    expect(onRecentSpawnsCleared).toHaveBeenCalled();
    expect(
      screen
        .getByTestId("collective-select-controls")
        .getAttribute("data-recent-count"),
    ).toBe("0");
    clearRecentDeepResearchSpawnIds();
  });

  it("selects all / invert / clear multi-select helpers (nk)", () => {
    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_a", "spn_b", "spn_c"]}
        parentAssetId="parent"
      />,
    );
    expect(screen.getByTestId("collective-select-controls")).toBeTruthy();
    expect(
      screen
        .getByTestId("collective-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("0");
    fireEvent.click(screen.getByTestId("collective-select-all"));
    expect(
      screen
        .getByTestId("collective-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("3");
    // Invert all-selected → empty.
    fireEvent.click(screen.getByTestId("collective-invert-selection"));
    expect(
      screen
        .getByTestId("collective-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("0");
    // Select one, invert → other two.
    fireEvent.click(screen.getByTestId("collective-select-spn_a"));
    fireEvent.click(screen.getByTestId("collective-invert-selection"));
    expect(
      screen
        .getByTestId("collective-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("2");
    expect(
      (screen.getByTestId("collective-select-spn_a") as HTMLInputElement)
        .checked,
    ).toBe(false);
    expect(
      (screen.getByTestId("collective-select-spn_b") as HTMLInputElement)
        .checked,
    ).toBe(true);
    fireEvent.click(screen.getByTestId("collective-clear-selection"));
    expect(
      screen
        .getByTestId("collective-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("0");
  });

  it("stores unit membership on merge and restores last multi-select (py)", async () => {
    fetchCollectiveResearch.mockResolvedValue({
      collective_id: "col_mem",
      spawn_ids: ["spn_a", "spn_b"],
      asset_ids: ["asset_x"],
      investigation_ids: [],
      twin_units: [],
      source_references: [],
      view_format: "html",
      spawn_count: 2,
      twin_count: 0,
      ref_count: 0,
      prompt_block: "# unit col_mem",
    });

    const { unmount } = render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_a", "spn_b", "spn_c"]}
        parentAssetId="asset_x"
        autoSelectNewestRecent={false}
      />,
    );
    fireEvent.click(screen.getByTestId("collective-select-spn_a"));
    fireEvent.click(screen.getByTestId("collective-select-spn_b"));
    fireEvent.click(screen.getByTestId("collective-merge-prompt"));
    await waitFor(() => {
      expect(
        screen.getByTestId("collective-unit-membership-status"),
      ).toBeTruthy();
    });
    const stored = screen.getByTestId("collective-unit-membership-status");
    expect(stored.getAttribute("data-action")).toBe("stored");
    expect(stored.getAttribute("data-collective-id")).toBe("col_mem");
    expect(stored.getAttribute("data-spawn-count")).toBe("2");
    // Residual (adj): L6 live multi-agent deferred + HTML + depth on membership.
    expect(stored.getAttribute("data-l6-live-multiagent")).toBe("deferred");
    expect(stored.getAttribute("data-view-format")).toBe("html");
    expect(stored.textContent).toMatch(/L6 live multi-agent deferred/i);

    // Clear selection then restore last unit.
    fireEvent.click(screen.getByTestId("collective-clear-selection"));
    expect(
      screen
        .getByTestId("collective-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("0");
    fireEvent.click(screen.getByTestId("collective-restore-last-unit"));
    expect(
      screen
        .getByTestId("collective-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("2");
    expect(
      (screen.getByTestId("collective-select-spn_a") as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(
      (screen.getByTestId("collective-select-spn_b") as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(
      screen
        .getByTestId("collective-unit-membership-status")
        .getAttribute("data-action"),
    ).toBe("restored");
    expect(
      screen
        .getByTestId("collective-unit-membership-status")
        .getAttribute("data-restored-count"),
    ).toBe("2");

    // Re-mount: membership survives sessionStorage for re-open path.
    unmount();
    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_a", "spn_b", "spn_c"]}
        parentAssetId="asset_x"
        autoSelectNewestRecent={false}
      />,
    );
    fireEvent.click(screen.getByTestId("collective-restore-last-unit"));
    expect(
      screen
        .getByTestId("collective-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("2");
  });

  it("links dual Write handoff html_draft + twin_seed after draft merge (qe)", async () => {
    fetchCollectiveResearch.mockResolvedValue({
      collective_id: "col_qe",
      spawn_ids: ["spn_1", "spn_2"],
      asset_ids: ["asset_x"],
      investigation_ids: [],
      twin_units: [],
      source_references: [],
      view_format: "html",
      spawn_count: 2,
      twin_count: 0,
      ref_count: 0,
      prompt_block: "# unit",
    });
    mergeSpawnOutputs.mockResolvedValue({
      document_id: "draft_col_qe",
      mode: "draft_combined",
      parent_asset_id: "asset_x",
      source_spawn_ids: ["spn_1", "spn_2"],
      draft_leaves_parent: true,
      view_format: "html",
      html: "<article><p>Collective draft body</p></article>",
      notes: [],
    });
    seedTwinNotes.mockResolvedValue({ seeded: true, seed_skipped: null, view_format: "html" });
    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_1", "spn_2"]}
        parentAssetId="asset_x"
        autoSelectNewestRecent={false}
        autoOpenDraft={false}
      />,
    );
    fireEvent.click(screen.getByTestId("collective-select-spn_1"));
    fireEvent.click(screen.getByTestId("collective-select-spn_2"));
    fireEvent.click(screen.getByTestId("collective-merge-draft"));
    await waitFor(() => {
      expect(screen.getByTestId("collective-open-write")).toBeTruthy();
    });
    const write = screen.getByTestId("collective-open-write");
    const href = write.getAttribute("href") || "";
    expect(href).toMatch(/html_draft=draft_col_qe/);
    expect(href).toMatch(/twin_seed=antiek\.twin_write_seed\./);
    expect(write.getAttribute("data-has-twin-seed")).toBe("1");
    // Residual (acm): twin_seed body honesty (parity spawn merge acl).
    expect(write.getAttribute("data-write-seed-has-body")).toBe("true");
    // Residual (aeq): multi-spawn draft_combined path honesty (parity aem).
    expect(write.getAttribute("data-mode")).toBe("draft_combined");
    expect(write.getAttribute("data-draft-leaves-parent")).toBe("true");
    expect(write.getAttribute("data-parent-asset-id")).toBe("asset_x");
    expect(write.getAttribute("data-document-id")).toBe("draft_col_qe");
    expect(write.getAttribute("data-spawn-count")).toBe("2");
    expect(write.getAttribute("data-seamless-merge-write")).toBe("true");
    expect(write.getAttribute("title") || "").toMatch(/draft_combined/i);
  });


  it("passes unit prompt_block as driver badge promptText (qg)", async () => {
    fetchCollectiveResearch.mockResolvedValue({
      collective_id: "col_qg",
      spawn_ids: ["spn_1", "spn_2"],
      asset_ids: ["asset_x"],
      investigation_ids: [],
      twin_units: [],
      source_references: [],
      view_format: "html",
      spawn_count: 2,
      twin_count: 0,
      ref_count: 0,
      prompt_block: "# Collective unit col_qg\nLong prompt for budget projection.",
    });
    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_1", "spn_2"]}
        parentAssetId="asset_x"
        autoSelectNewestRecent={false}
      />,
    );
    fireEvent.click(screen.getByTestId("collective-select-spn_1"));
    fireEvent.click(screen.getByTestId("collective-select-spn_2"));
    // Before merge: selected spawn ids form promptText.
    expect(
      Number(
        screen
          .getByTestId("decision-tree-driver-badge-stub")
          .getAttribute("data-prompt-len") || 0,
      ),
    ).toBeGreaterThan(0);
    fireEvent.click(screen.getByTestId("collective-merge-prompt"));
    await waitFor(() => {
      expect(screen.getByTestId("collective-unit-result")).toBeTruthy();
    });
    expect(
      Number(
        screen
          .getByTestId("decision-tree-driver-badge-stub")
          .getAttribute("data-prompt-len") || 0,
      ),
    ).toBeGreaterThan(20);
  });


  it("auto-restores last unit membership multi-select on mount (ql)", () => {
    storeCollectiveUnitMembership({
      collective_id: "col_auto",
      spawn_ids: ["spn_a", "spn_b", "spn_gone"],
      parent_asset_id: "asset_x",
    });
    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_a", "spn_b", "spn_c"]}
        parentAssetId="asset_x"
        autoSelectNewestRecent={false}
      />,
    );
    expect(
      screen
        .getByTestId("collective-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("2");
    expect(
      screen
        .getByTestId("collective-unit-membership-status")
        .getAttribute("data-action"),
    ).toBe("restored");
    expect(
      screen
        .getByTestId("collective-unit-membership-status")
        .getAttribute("data-restored-count"),
    ).toBe("2");
  });

  it("selects open-window spawns only when openSpawnIds provided (ue)", () => {
    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_open_a", "spn_open_b", "spn_closed_recent"]}
        openSpawnIds={["spn_open_a", "spn_open_b"]}
        recentSpawnIds={["spn_closed_recent", "spn_open_a"]}
        autoSelectNewestRecent={false}
      />,
    );
    const controls = screen.getByTestId("collective-select-controls");
    expect(controls.getAttribute("data-has-open-spawn-ids")).toBe("true");
    expect(controls.getAttribute("data-open-in-available")).toBe("2");
    expect(screen.getByTestId("collective-select-open")).toBeTruthy();
    fireEvent.click(screen.getByTestId("collective-select-open"));
    expect(
      screen
        .getByTestId("collective-selection-count")
        .getAttribute("data-selected-count"),
    ).toBe("2");
    expect(
      (screen.getByTestId("collective-select-spn_open_a") as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(
      (screen.getByTestId("collective-select-spn_open_b") as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(
      (
        screen.getByTestId(
          "collective-select-spn_closed_recent",
        ) as HTMLInputElement
      ).checked,
    ).toBe(false);
  });

  it("hides select-open control when openSpawnIds omitted (ue)", () => {
    render(
      <CollectiveResearchPanel
        availableSpawnIds={["spn_1", "spn_2"]}
        autoSelectNewestRecent={false}
      />,
    );
    expect(screen.queryByTestId("collective-select-open")).toBeNull();
    expect(
      screen
        .getByTestId("collective-select-controls")
        .getAttribute("data-has-open-spawn-ids"),
    ).toBe("false");
  });

});
