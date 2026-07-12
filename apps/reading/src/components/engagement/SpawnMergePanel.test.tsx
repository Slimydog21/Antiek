import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SpawnMergePanel } from "./SpawnMergePanel";

const mergeSpawnOutputs = vi.fn<(...args: unknown[]) => unknown>();
const commitReviewedMergeDraft = vi.fn<(...args: unknown[]) => unknown>();
const seedTwinNotes = vi.fn<(...args: unknown[]) => unknown>();
const openWindow = vi.fn(() => "win:merge:draft_1");

vi.mock("../../api/engagement", () => ({
  commitReviewedMergeDraft: (...args: unknown[]) => commitReviewedMergeDraft(...(args as Parameters<typeof commitReviewedMergeDraft>)),
  mergeSpawnOutputs: (...args: unknown[]) => mergeSpawnOutputs(...(args as Parameters<typeof mergeSpawnOutputs>)),
  seedTwinNotes: (...args: unknown[]) => seedTwinNotes(...(args as Parameters<typeof seedTwinNotes>)),
}));

vi.mock("../windows/openWindow", () => ({
  openWindow: (...args: unknown[]) => openWindow(...(args as Parameters<typeof openWindow>)),
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

const budgetProjection = vi.hoisted(() => ({
  wouldExceedBudget: false as boolean,
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
          wouldExceedBudget: budgetProjection.wouldExceedBudget,
          pricingKnown: true,
          estimatedUsdHigh: budgetProjection.wouldExceedBudget ? 99 : 0.1,
          remainingUsd: budgetProjection.wouldExceedBudget ? 0.5 : 5,
          modelId: null,
        });
      }, [props.onProjectionChange, props.promptText]);
      return (
        <div
          data-testid="research-launch-budget-panel-stub"
          data-research-tier={props.researchTier || "deep"}
          data-would-exceed={String(budgetProjection.wouldExceedBudget)}
        >
          budget len={props.promptText.length}
        </div>
      );
    },
  };
});

describe("SpawnMergePanel residual ci", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    budgetProjection.wouldExceedBudget = false;
    mergeSpawnOutputs.mockReset();
    commitReviewedMergeDraft.mockReset();
    seedTwinNotes.mockReset();
    seedTwinNotes.mockResolvedValue({
      asset_id: "draft_book-1_abc",
      seeded: true,
      view_format: "html",
      notes: [],
      insight_count: 1,
      question_count: 1,
    });
    openWindow.mockClear();
  });

  it("commits the exact reviewed draft only after explicit operator approval", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "book-1",
      document_id: "draft_book-1_reviewed",
      draft_sha256: "a".repeat(64),
      canonical_committed: false,
      source_spawn_ids: ["spn_1"],
      sections_merged: 2,
      draft_leaves_parent: true,
      parent_document_id: "book-1",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: ["Parent unchanged until canonical commit"],
      html: "<p>Reviewed preview</p>",
    });
    commitReviewedMergeDraft.mockResolvedValue({
      deliverable_id: "dlv-merge-book-1-spn_1",
      draft_document_id: "draft_book-1_reviewed",
      old_revision: null,
      new_revision: "b".repeat(64),
      section_id: "sec-reviewed",
      node_ids: ["node-reviewed"],
      paragraph_count: 1,
      draft_sha256: "a".repeat(64),
      view_format: "html",
      html: "<article>Canonical reviewed research</article>",
    });

    render(
      <SpawnMergePanel
        spawnId="spn_1"
        parentAssetId="book-1"
        autoOpenDraft={false}
      />,
    );
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await waitFor(() => expect(screen.getByTestId("spawn-merge-canonical-review")).toBeTruthy());
    expect(commitReviewedMergeDraft).not.toHaveBeenCalled();
    expect(screen.getByTestId("spawn-merge-canonical-review").textContent).toContain(
      "a".repeat(64),
    );
    expect(
      (screen.getByTestId("spawn-merge-canonical-target") as HTMLInputElement).value,
    ).toBe("dlv-merge-book-1-spn_1");
    expect(
      (screen.getByTestId("spawn-merge-expected-revision") as HTMLInputElement).value,
    ).toBe("new");
    expect(
      (screen.getByTestId("spawn-merge-create-combined") as HTMLInputElement).checked,
    ).toBe(true);

    fireEvent.click(screen.getByTestId("spawn-merge-canonical-commit"));
    await waitFor(() => {
      expect(commitReviewedMergeDraft).toHaveBeenCalledWith({
        draft_document_id: "draft_book-1_reviewed",
        reviewed_draft_sha256: "a".repeat(64),
        target_deliverable_id: "dlv-merge-book-1-spn_1",
        expected_revision: "new",
        create_combined: true,
      });
    });
    const success = await screen.findByTestId("spawn-merge-canonical-success");
    expect(success.getAttribute("data-deliverable-id")).toBe(
      "dlv-merge-book-1-spn_1",
    );
    expect(success.getAttribute("data-revision")).toBe("b".repeat(64));
    fireEvent.click(screen.getByTestId("spawn-merge-open-canonical"));
    expect(openWindow).toHaveBeenCalledWith(
      "hosted_html_document",
      expect.objectContaining({
        document_id: "dlv-merge-book-1-spn_1",
        html: "<article>Canonical reviewed research</article>",
      }),
      expect.objectContaining({ id: "win:canonical-merge:dlv-merge-book-1-spn_1" }),
    );
    expect(
      screen.getByTestId("spawn-merge-open-canonical-write").getAttribute("href") || "",
    ).toMatch(/html_draft=dlv-merge-book-1-spn_1/);
    fireEvent.change(screen.getByTestId("spawn-merge-canonical-target"), {
      target: { value: "dlv-retry" },
    });
    expect(screen.queryByTestId("spawn-merge-canonical-success")).toBeNull();
    commitReviewedMergeDraft.mockRejectedValueOnce(
      new Error("engagement API 409: retry target is stale"),
    );
    fireEvent.click(screen.getByTestId("spawn-merge-canonical-commit"));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/409.*stale/i);
    });
    expect(screen.queryByTestId("spawn-merge-canonical-success")).toBeNull();
  });

  it("keeps update intent independent from a real expected revision", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "paper-update",
      document_id: "draft-update",
      draft_sha256: "d".repeat(64),
      source_spawn_ids: ["spn_update"],
      sections_merged: 1,
      draft_leaves_parent: true,
      parent_document_id: "paper-update",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: [],
      html: "<p>Update preview</p>",
    });
    commitReviewedMergeDraft.mockResolvedValue({
      deliverable_id: "dlv-existing",
      draft_document_id: "draft-update",
      old_revision: "e".repeat(64),
      new_revision: "f".repeat(64),
      section_id: "sec-update",
      node_ids: ["node-update"],
      paragraph_count: 1,
      draft_sha256: "d".repeat(64),
      view_format: "html",
      html: "<p>Updated canonical</p>",
    });
    render(
      <SpawnMergePanel
        spawnId="spn_update"
        parentAssetId="paper-update"
        autoOpenDraft={false}
      />,
    );
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await screen.findByTestId("spawn-merge-canonical-review");
    fireEvent.change(screen.getByTestId("spawn-merge-canonical-target"), {
      target: { value: "dlv-existing" },
    });
    fireEvent.change(screen.getByTestId("spawn-merge-expected-revision"), {
      target: { value: "e".repeat(64) },
    });
    fireEvent.click(screen.getByTestId("spawn-merge-create-combined"));
    fireEvent.click(screen.getByTestId("spawn-merge-canonical-commit"));
    await waitFor(() => {
      expect(commitReviewedMergeDraft).toHaveBeenCalledWith(
        expect.objectContaining({
          target_deliverable_id: "dlv-existing",
          expected_revision: "e".repeat(64),
          create_combined: false,
        }),
      );
    });
    expect(await screen.findByTestId("spawn-merge-canonical-success")).toBeTruthy();
  });

  it("rejects a canonical response that does not match the reviewed request", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "paper-mismatch",
      document_id: "draft-mismatch",
      draft_sha256: "1".repeat(64),
      source_spawn_ids: ["spn_mismatch"],
      sections_merged: 1,
      draft_leaves_parent: true,
      parent_document_id: "paper-mismatch",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: [],
      html: "<p>Reviewed mismatch fixture</p>",
    });
    commitReviewedMergeDraft.mockResolvedValue({
      deliverable_id: "dlv-wrong",
      draft_document_id: "draft-other",
      old_revision: null,
      new_revision: "2".repeat(64),
      section_id: "sec-wrong",
      node_ids: [],
      paragraph_count: 0,
      draft_sha256: "3".repeat(64),
      view_format: "html",
      html: "<p>Wrong response</p>",
    });
    render(
      <SpawnMergePanel
        spawnId="spn_mismatch"
        parentAssetId="paper-mismatch"
        autoOpenDraft={false}
      />,
    );
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await screen.findByTestId("spawn-merge-canonical-review");
    fireEvent.click(screen.getByTestId("spawn-merge-canonical-commit"));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/conflicts with reviewed/i);
    });
    expect(screen.queryByTestId("spawn-merge-canonical-success")).toBeNull();
  });

  it("discards an in-flight commit when the bound spawn or parent changes", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "paper-race",
      document_id: "draft-race",
      draft_sha256: "4".repeat(64),
      source_spawn_ids: ["spn_race"],
      sections_merged: 1,
      draft_leaves_parent: true,
      parent_document_id: "paper-race",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: [],
      html: "<p>Race preview</p>",
    });
    let resolveCommit: ((value: unknown) => void) | undefined;
    commitReviewedMergeDraft.mockImplementation(
      () => new Promise((resolve) => { resolveCommit = resolve; }),
    );
    const { rerender } = render(
      <SpawnMergePanel
        spawnId="spn_race"
        parentAssetId="paper-race"
        autoOpenDraft={false}
      />,
    );
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await screen.findByTestId("spawn-merge-canonical-review");
    fireEvent.click(screen.getByTestId("spawn-merge-canonical-commit"));
    await waitFor(() => expect(commitReviewedMergeDraft).toHaveBeenCalled());
    rerender(
      <SpawnMergePanel
        spawnId="spn_new"
        parentAssetId="paper-new"
        autoOpenDraft={false}
      />,
    );
    resolveCommit?.({
      deliverable_id: "dlv-merge-paper-race-spn_race",
      draft_document_id: "draft-race",
      old_revision: null,
      new_revision: "5".repeat(64),
      section_id: "sec-race",
      node_ids: ["node-race"],
      paragraph_count: 1,
      draft_sha256: "4".repeat(64),
      view_format: "html",
      html: "<p>Old canonical response</p>",
    });
    await waitFor(() => {
      expect(screen.queryByTestId("spawn-merge-canonical-success")).toBeNull();
      expect(screen.queryByTestId("spawn-merge-canonical-review")).toBeNull();
    });
  });

  it("discards an in-flight preview when its spawn binding changes", async () => {
    let resolvePreview: ((value: unknown) => void) | undefined;
    mergeSpawnOutputs.mockImplementation(
      () => new Promise((resolve) => { resolvePreview = resolve; }),
    );
    const onMerged = vi.fn();
    const { rerender } = render(
      <SpawnMergePanel
        spawnId="spn_preview_old"
        parentAssetId="paper-preview-old"
        onMerged={onMerged}
        autoOpenDraft
      />,
    );
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await waitFor(() => expect(mergeSpawnOutputs).toHaveBeenCalled());
    rerender(
      <SpawnMergePanel
        spawnId="spn_preview_new"
        parentAssetId="paper-preview-new"
        onMerged={onMerged}
        autoOpenDraft
      />,
    );
    resolvePreview?.({
      mode: "draft_combined",
      parent_asset_id: "paper-preview-old",
      document_id: "draft-preview-old",
      draft_sha256: "6".repeat(64),
      source_spawn_ids: ["spn_preview_old"],
      sections_merged: 1,
      draft_leaves_parent: true,
      parent_document_id: "paper-preview-old",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: [],
      html: "<p>Stale preview</p>",
    });
    await waitFor(() => {
      expect(screen.queryByTestId("spawn-merge-result")).toBeNull();
    });
    expect(onMerged).not.toHaveBeenCalled();
    expect(openWindow).not.toHaveBeenCalled();
  });

  it("rejects a create response that reports prior canonical state", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "paper-revision-mismatch",
      document_id: "draft-revision-mismatch",
      draft_sha256: "7".repeat(64),
      source_spawn_ids: ["spn_revision_mismatch"],
      sections_merged: 1,
      draft_leaves_parent: true,
      parent_document_id: "paper-revision-mismatch",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: [],
      html: "<p>Revision mismatch preview</p>",
    });
    commitReviewedMergeDraft.mockResolvedValue({
      deliverable_id: "dlv-merge-paper-revision-mismatch-spn_revision_mismatch",
      draft_document_id: "draft-revision-mismatch",
      old_revision: "8".repeat(64),
      new_revision: "9".repeat(64),
      section_id: "sec-revision-mismatch",
      node_ids: ["node-revision-mismatch"],
      paragraph_count: 1,
      draft_sha256: "7".repeat(64),
      view_format: "html",
      html: "<p>Unexpected update</p>",
    });
    render(
      <SpawnMergePanel
        spawnId="spn_revision_mismatch"
        parentAssetId="paper-revision-mismatch"
        autoOpenDraft={false}
      />,
    );
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await screen.findByTestId("spawn-merge-canonical-review");
    fireEvent.click(screen.getByTestId("spawn-merge-canonical-commit"));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/revision intent/i);
    });
    expect(screen.queryByTestId("spawn-merge-canonical-success")).toBeNull();
  });

  it("single-flights rapid canonical commit activation", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "paper-single-flight",
      document_id: "draft-single-flight",
      draft_sha256: "a".repeat(64),
      source_spawn_ids: ["spn_single_flight"],
      sections_merged: 1,
      draft_leaves_parent: true,
      parent_document_id: "paper-single-flight",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: [],
      html: "<p>Single flight preview</p>",
    });
    let resolveCommit: ((value: unknown) => void) | undefined;
    commitReviewedMergeDraft.mockImplementation(
      () => new Promise((resolve) => { resolveCommit = resolve; }),
    );
    render(
      <SpawnMergePanel
        spawnId="spn_single_flight"
        parentAssetId="paper-single-flight"
        autoOpenDraft={false}
      />,
    );
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    const commit = await screen.findByTestId("spawn-merge-canonical-commit");
    commit.click();
    commit.click();
    expect(commitReviewedMergeDraft).toHaveBeenCalledTimes(1);
    resolveCommit?.({
      deliverable_id: "dlv-merge-paper-single-flight-spn_single_flight",
      draft_document_id: "draft-single-flight",
      old_revision: null,
      new_revision: "b".repeat(64),
      section_id: "sec-single-flight",
      node_ids: ["node-single-flight"],
      paragraph_count: 1,
      draft_sha256: "a".repeat(64),
      view_format: "html",
      html: "<p>Single canonical result</p>",
    });
    expect(await screen.findByTestId("spawn-merge-canonical-success")).toBeTruthy();
  });

  it("keeps the reviewed preview available when canonical revision conflicts", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "paper-1",
      document_id: "draft-conflict",
      draft_sha256: "c".repeat(64),
      source_spawn_ids: ["spn_conflict"],
      sections_merged: 1,
      draft_leaves_parent: true,
      parent_document_id: "paper-1",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: [],
      html: "<p>Still reviewable</p>",
    });
    commitReviewedMergeDraft.mockRejectedValue(
      new Error("engagement API 409: canonical target revision is stale"),
    );
    render(
      <SpawnMergePanel
        spawnId="spn_conflict"
        parentAssetId="paper-1"
        autoOpenDraft={false}
      />,
    );
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await screen.findByTestId("spawn-merge-canonical-review");
    fireEvent.click(screen.getByTestId("spawn-merge-canonical-commit"));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/409.*stale/i);
    });
    expect(screen.getByTestId("spawn-merge-canonical-review")).toBeTruthy();
    expect(screen.getByTestId("spawn-merge-html").innerHTML).toMatch(/Still reviewable/);
    expect(screen.queryByTestId("spawn-merge-canonical-success")).toBeNull();
  });

  it("creates draft combined from single spawn", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "book-1",
      document_id: "draft_book-1_abc",
      source_spawn_ids: ["spn_1"],
      sections_merged: 2,
      draft_leaves_parent: true,
      parent_document_id: "book-1",
      research_tiers: ["wrestle"],
      recommended_research_tier: "wrestle",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: ["Draft-combined document"],
      html: "<p>Draft merge HTML · recommended_tier=wrestle</p>",
    });

    const onMerged = vi.fn();
    render(
      <SpawnMergePanel
        spawnId="spn_1"
        parentAssetId="book-1"
        onMerged={onMerged}
      />,
    );
    const panel = screen.getByTestId("spawn-merge-panel");
    expect(panel.getAttribute("data-auto-open-draft")).toBe("true");
    // Residual (agu): seamless highlight→DR→merge path honesty when spawn+parent bound.
    expect(panel.getAttribute("data-seamless-spawn-merge")).toBe("true");
    expect(panel.getAttribute("data-seamless-highlight-dr-merge")).toBe("true");
    expect(panel.getAttribute("data-spawn-id")).toBe("spn_1");
    expect(panel.getAttribute("data-parent-asset-id")).toBe("book-1");
    expect(panel.textContent).toMatch(/seamless highlight→DR→merge path/i);
    // Residual (aqy): path-choices pure helper chrome on single-spawn merge.
    const path = screen.getByTestId("spawn-merge-path-choices");
    expect(path.getAttribute("data-html-first")).toBe("true");
    expect(path.getAttribute("data-parent-bound")).toBe("true");
    expect(path.getAttribute("data-draft-merge-ready")).toBe("true");
    expect(path.getAttribute("data-into-parent-ready")).toBe("true");
    expect(path.getAttribute("data-written-analysis-ready")).toBe("false");
    expect(path.getAttribute("data-selected-count")).toBe("1");
    expect(path.textContent).toMatch(/draft merge/i);
    expect(path.textContent).toMatch(/ready/i);
    expect(
      screen.getByTestId("spawn-merge-draft").getAttribute("data-seamless-merge-draft"),
    ).toBe("true");
    expect(
      screen.getByTestId("spawn-merge-parent").getAttribute("data-seamless-merge-parent"),
    ).toBe("true");
    expect(
      screen.getByTestId("spawn-merge-actions").getAttribute("data-seamless-spawn-merge"),
    ).toBe("true");
    // Residual (ih): Settings deep-link for driver + budget.
    const settings = screen.getByTestId("spawn-merge-settings-link");
    const dual = screen.getByTestId("spawn-merge-dual-gate-checklist-link");
    // Residual (xn/aat): multi-spawn merge prep → L6 collective checklist section.
    expect(dual.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4.*#l6-collective/);
    expect(dual.textContent).toMatch(/L6 collective checklist/i);
    expect(settings.getAttribute("href")).toBe("/settings#decision-tree-panel");
    expect(settings.textContent).toMatch(/driver & budget/i);
    // Residual (aix): highlight→DR→merge → competitive DR honesty map.
    const scorecard = screen.getByTestId("spawn-merge-competitive-scorecard-link");
    expect(scorecard.getAttribute("href")).toBe(
      "/settings#settings-competitive-dr-scorecard",
    );
    expect(scorecard.textContent).toMatch(/competitive DR scorecard/i);
    expect(
      screen
        .getByTestId("spawn-merge-competitive-dr-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-competitive-deep-research-quality/);
    // Residual (akn): highlight→DR→merge budget-before-fire → Settings prompt-cost.
    expect(
      screen
        .getByTestId("spawn-merge-prompt-cost-projection-link")
        .getAttribute("href"),
    ).toBe("/settings#prompt-cost-projection");
    expect(
      screen.getByTestId("spawn-merge-prompt-cost-projection-link").textContent,
    ).toMatch(/prompt-cost projection/i);
    // Residual (lj): driver badge defaults deep pre-merge.
    expect(
      screen
        .getByTestId("spawn-merge-driver-badge-mount")
        .getAttribute("data-research-tier"),
    ).toBe("deep");
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await waitFor(() => {
      expect(mergeSpawnOutputs).toHaveBeenCalledWith({
        parent_asset_id: "book-1",
        spawn_ids: ["spn_1"],
        mode: "draft_combined",
        include_html: true,
      });
    });
    await waitFor(() => {
      expect(seedTwinNotes).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "draft_book-1_abc",
          force_offline: true,
          source_spawn_id: "spn_1",
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("spawn-merge-result").textContent).toMatch(
        /draft_combined|Twin notes seeded/,
      );
    });
    expect(
      (screen.getByTestId("spawn-merge-canonical-commit") as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(
      screen.getByTestId("spawn-merge-panel").getAttribute("data-view-format"),
    ).toBe("html");
    expect(screen.getByTestId("spawn-merge-html").innerHTML).toMatch(/Draft merge/);
    // Residual (ho): machine-readable merge outcome metrics.
    const metrics = screen.getByTestId("spawn-merge-metrics");
    expect(metrics.getAttribute("data-mode")).toBe("draft_combined");
    expect(metrics.getAttribute("data-document-id")).toBe("draft_book-1_abc");
    expect(metrics.getAttribute("data-spawn-id")).toBe("spn_1");
    expect(metrics.getAttribute("data-parent-asset-id")).toBe("book-1");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.getAttribute("data-auto-open-draft")).toBe("true");
    // Residual (kn): recommended research tier + member tiers chrome.
    expect(metrics.getAttribute("data-recommended-research-tier")).toBe(
      "wrestle",
    );
    expect(metrics.getAttribute("data-research-tiers")).toBe("wrestle");
    expect(
      screen.getByTestId("spawn-merge-result").getAttribute(
        "data-recommended-research-tier",
      ),
    ).toBe("wrestle");
    expect(screen.getByTestId("spawn-merge-research-tier").textContent).toMatch(
      /wrestle/i,
    );
    expect(screen.getByTestId("spawn-merge-research-tier").textContent).toMatch(
      /long-horizon/i,
    );
    // Residual (lj): post-merge badge adopts recommended_research_tier.
    expect(
      screen
        .getByTestId("spawn-merge-driver-badge-mount")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
    expect(
      screen
        .getByTestId("decision-tree-driver-badge-stub")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
    expect(metrics.textContent).toMatch(/Spawn merge/);
    // Residual (eh): parent notified after merge + twin seed.
    await waitFor(() => {
      expect(onMerged).toHaveBeenCalled();
    });
    expect(onMerged.mock.calls[0][0].document_id).toBe("draft_book-1_abc");
    expect(onMerged.mock.calls[0][0].view_format).toBe("html");
    // Residual (el): draft_combined auto-opens hosted HTML without extra click.
    await waitFor(() => {
      expect(openWindow).toHaveBeenCalledWith(
        "hosted_html_document",
        expect.objectContaining({
          document_id: "draft_book-1_abc",
          view_format: "html",
          html: "<p>Draft merge HTML · recommended_tier=wrestle</p>",
          source: "spawn_merge",
        }),
        expect.objectContaining({
          id: "win:merge:draft_book-1_abc",
          mode: "floating",
        }),
      );
    });
    expect(screen.getByTestId("spawn-merge-auto-open-window").textContent).toMatch(
      /win:merge:draft_1/,
    );
  });

  it("does not auto-open draft when autoOpenDraft is false", async () => {
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
      html: "<p>Manual open</p>",
    });
    render(
      <SpawnMergePanel
        spawnId="spn_1"
        parentAssetId="book-1"
        autoOpenDraft={false}
      />,
    );
    expect(
      screen.getByTestId("spawn-merge-panel").getAttribute("data-auto-open-draft"),
    ).toBe("false");
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await waitFor(() => {
      expect(screen.getByTestId("spawn-merge-open-window")).toBeTruthy();
    });
    expect(openWindow).not.toHaveBeenCalled();
    expect(screen.queryByTestId("spawn-merge-auto-open-window")).toBeNull();
  });

  it("links Open Write handoff for merged HTML document (fn)", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "book-1",
      document_id: "draft_for_write",
      source_spawn_ids: ["spn_1"],
      sections_merged: 1,
      draft_leaves_parent: true,
      parent_document_id: "book-1",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: ["Draft"],
      html: "<p>Write me</p>",
    });
    render(
      <SpawnMergePanel
        spawnId="spn_1"
        parentAssetId="book-1"
        autoOpenDraft={false}
      />,
    );
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await waitFor(() => {
      expect(screen.getByTestId("spawn-merge-open-write")).toBeTruthy();
    });
    const link = screen.getByTestId("spawn-merge-open-write");
    expect(link.getAttribute("href") || "").toMatch(/html_draft=draft_for_write/);
    expect(link.getAttribute("href") || "").toMatch(/twin_seed=antiek\.twin_write_seed\./);
    expect(link.getAttribute("data-has-twin-seed")).toBe("1");
    expect(link.getAttribute("data-view-format")).toBe("html");
    // Residual (acl): twin_seed body honesty (parity marketplace acf / MO ack).
    expect(link.getAttribute("data-write-seed-has-body")).toBe("true");
    // Residual (aem): draft_combined path honesty on Open Write (not only metrics).
    expect(link.getAttribute("data-mode")).toBe("draft_combined");
    expect(link.getAttribute("data-draft-leaves-parent")).toBe("true");
    expect(link.getAttribute("data-parent-asset-id")).toBe("book-1");
    expect(link.getAttribute("data-spawn-id")).toBe("spn_1");
    expect(link.getAttribute("data-document-id")).toBe("draft_for_write");
    expect(link.getAttribute("data-seamless-merge-write")).toBe("true");
    expect(link.getAttribute("title") || "").toMatch(/draft_combined/i);
  });

  it("stamps into_parent Open Write path honesty (aem)", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "into_parent",
      parent_asset_id: "book-1",
      document_id: "book-1",
      source_spawn_ids: ["spn_1"],
      sections_merged: 1,
      draft_leaves_parent: false,
      parent_document_id: "book-1",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: ["Merged into parent"],
      html: "<p>Parent merge Write</p>",
    });
    render(
      <SpawnMergePanel
        spawnId="spn_1"
        parentAssetId="book-1"
        autoOpenDraft={false}
      />,
    );
    fireEvent.click(screen.getByTestId("spawn-merge-parent"));
    await waitFor(() => {
      expect(screen.getByTestId("spawn-merge-open-write")).toBeTruthy();
    });
    const link = screen.getByTestId("spawn-merge-open-write");
    expect(link.getAttribute("data-mode")).toBe("into_parent");
    expect(link.getAttribute("data-draft-leaves-parent")).toBe("false");
    expect(link.getAttribute("data-parent-asset-id")).toBe("book-1");
    expect(link.getAttribute("data-spawn-id")).toBe("spn_1");
    expect(link.getAttribute("data-document-id")).toBe("book-1");
    expect(link.getAttribute("data-seamless-merge-write")).toBe("true");
    expect(link.getAttribute("data-write-seed-has-body")).toBe("true");
    expect(link.getAttribute("title") || "").toMatch(/into_parent/i);
  });

  it("opens merged HTML in full working-region window (ev)", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "book-1",
      document_id: "draft_full",
      source_spawn_ids: ["spn_1"],
      sections_merged: 1,
      draft_leaves_parent: true,
      parent_document_id: "book-1",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: ["Draft"],
      html: "<p>Full open</p>",
    });
    render(
      <SpawnMergePanel
        spawnId="spn_1"
        parentAssetId="book-1"
        autoOpenDraft={false}
      />,
    );
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await waitFor(() => {
      expect(screen.getByTestId("spawn-merge-open-full")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("spawn-merge-open-full"));
    expect(openWindow).toHaveBeenCalledWith(
      "hosted_html_document",
      expect.objectContaining({
        document_id: "draft_full",
        view_format: "html",
      }),
      expect.objectContaining({
        id: "win:merge:draft_full:full",
        mode: "full",
      }),
    );
  });

  it("merges into parent without auto-open; manual open still works", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "into_parent",
      parent_asset_id: "book-1",
      document_id: "book-1",
      source_spawn_ids: ["spn_1"],
      sections_merged: 1,
      draft_leaves_parent: false,
      parent_document_id: "book-1",
      view_format: "html",
      product_panel: "engagement_merge",
      source: "engagement_spine.merge_spawn_outputs",
      notes: ["Merged into parent"],
      html: "<p>Parent merge HTML</p>",
    });

    render(
      <SpawnMergePanel spawnId="spn_1" parentAssetId="book-1" />,
    );
    fireEvent.click(screen.getByTestId("spawn-merge-parent"));
    await waitFor(() => {
      expect(mergeSpawnOutputs).toHaveBeenCalledWith({
        parent_asset_id: "book-1",
        spawn_ids: ["spn_1"],
        mode: "into_parent",
        include_html: true,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("spawn-merge-open-window")).toBeTruthy();
    });
    // Residual (el): into_parent does not auto-open (parent may already be open).
    expect(openWindow).not.toHaveBeenCalled();
    expect(screen.queryByTestId("spawn-merge-auto-open-window")).toBeNull();
    fireEvent.click(screen.getByTestId("spawn-merge-open-window"));
    // Residual (aah): default window source is spawn_merge (not spawn_merge_panel).
    expect(openWindow).toHaveBeenCalledWith(
      "hosted_html_document",
      expect.objectContaining({
        document_id: "book-1",
        view_format: "html",
        source: "spawn_merge",
      }),
      expect.objectContaining({ mode: "floating" }),
    );
  });

  it("refuses non-html view_format", async () => {
    mergeSpawnOutputs.mockResolvedValue({
      mode: "draft_combined",
      parent_asset_id: "book-1",
      document_id: "x",
      source_spawn_ids: ["spn_1"],
      sections_merged: 0,
      draft_leaves_parent: true,
      parent_document_id: "book-1",
      view_format: "pdf",
      product_panel: "engagement_merge",
      source: "test",
      notes: [],
      html: "%PDF",
    });
    render(
      <SpawnMergePanel spawnId="spn_1" parentAssetId="book-1" />,
    );
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/html/i);
    });
  });

  it("passes spawn merge promptText to driver badge (qh)", () => {
    render(
      <SpawnMergePanel spawnId="spn_qh" parentAssetId="paper_qh" />,
    );
    const badge = screen.getByTestId("decision-tree-driver-badge-stub");
    expect(Number(badge.getAttribute("data-prompt-len") || 0)).toBeGreaterThan(5);
    expect(badge.getAttribute("data-prompt-len")).not.toBe("0");
  });

  it("soft-gates draft and parent merge on budget projection (anl)", async () => {
    budgetProjection.wouldExceedBudget = true;
    mergeSpawnOutputs.mockResolvedValue({
      document_id: "draft_over",
      mode: "draft_combined",
      draft_leaves_parent: true,
      view_format: "html",
      html: "<p>should not merge without force</p>",
      notes: [],
    });
    render(<SpawnMergePanel spawnId="spn_over" parentAssetId="book_over" />);
    await waitFor(() => {
      expect(screen.getByTestId("spawn-merge-budget-mount")).toBeTruthy();
    });
    expect(
      screen.getByTestId("spawn-merge-budget-mount").getAttribute("data-budget-soft-gate"),
    ).toBe("true");
    await waitFor(() => {
      expect(screen.getByTestId("spawn-merge-over-budget-warn")).toBeTruthy();
    });
    const draftBtn = screen.getByTestId("spawn-merge-draft") as HTMLButtonElement;
    const parentBtn = screen.getByTestId(
      "spawn-merge-parent",
    ) as HTMLButtonElement;
    expect(draftBtn.disabled).toBe(true);
    expect(parentBtn.disabled).toBe(true);
    expect(draftBtn.getAttribute("data-budget-soft-gate")).toBe("true");
    fireEvent.click(draftBtn);
    expect(mergeSpawnOutputs).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("spawn-merge-force-over-budget"));
    await waitFor(() => {
      expect(
        (screen.getByTestId("spawn-merge-draft") as HTMLButtonElement).disabled,
      ).toBe(false);
    });
    fireEvent.click(screen.getByTestId("spawn-merge-draft"));
    await waitFor(() => {
      expect(mergeSpawnOutputs).toHaveBeenCalled();
    });
  });

  it("gates draft/parent CTAs on pathChoices readiness (ary)", () => {
    // Missing parent → draft_merge_ready false
    const { unmount } = render(<SpawnMergePanel spawnId="spn_only" />);
    const draftNoParent = screen.getByTestId(
      "spawn-merge-draft",
    ) as HTMLButtonElement;
    const parentNoParent = screen.getByTestId(
      "spawn-merge-parent",
    ) as HTMLButtonElement;
    expect(draftNoParent.getAttribute("data-draft-merge-ready")).toBe("false");
    expect(parentNoParent.getAttribute("data-into-parent-ready")).toBe("false");
    expect(draftNoParent.disabled).toBe(true);
    expect(parentNoParent.disabled).toBe(true);
    expect(draftNoParent.getAttribute("title") || "").toMatch(/parent/i);
    expect(
      screen.getByTestId("spawn-merge-actions").getAttribute("data-draft-merge-ready"),
    ).toBe("false");
    unmount();

    // Missing spawn → not ready
    render(<SpawnMergePanel parentAssetId="book-orphan" />);
    const draftNoSpawn = screen.getByTestId(
      "spawn-merge-draft",
    ) as HTMLButtonElement;
    expect(draftNoSpawn.getAttribute("data-draft-merge-ready")).toBe("false");
    expect(draftNoSpawn.disabled).toBe(true);
    expect(draftNoSpawn.getAttribute("title") || "").toMatch(/spawn|select/i);

    // Both bound → ready (no budget warn)
    cleanup();
    render(<SpawnMergePanel spawnId="spn_ok" parentAssetId="book_ok" />);
    const draftOk = screen.getByTestId("spawn-merge-draft") as HTMLButtonElement;
    const parentOk = screen.getByTestId(
      "spawn-merge-parent",
    ) as HTMLButtonElement;
    expect(draftOk.getAttribute("data-draft-merge-ready")).toBe("true");
    expect(parentOk.getAttribute("data-into-parent-ready")).toBe("true");
    expect(draftOk.disabled).toBe(false);
    expect(parentOk.disabled).toBe(false);
    expect(draftOk.getAttribute("data-view-format")).toBe("html");
  });

});
