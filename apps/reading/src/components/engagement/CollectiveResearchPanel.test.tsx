import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CollectiveResearchPanel } from "./CollectiveResearchPanel";

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

vi.mock("./ResearchLaunchBudgetPanel", () => {
  const React = require("react") as typeof import("react");
  return {
    ResearchLaunchBudgetPanel: (props: {
      promptText: string;
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
        <div data-testid="research-launch-budget-panel-stub">
          budget len={props.promptText.length}
        </div>
      );
    },
  };
});

describe("CollectiveResearchPanel", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
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
    });

    render(
      <CollectiveResearchPanel availableSpawnIds={["spn_1", "spn_2", "spn_3"]} />,
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
  });
});
