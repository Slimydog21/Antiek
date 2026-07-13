import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MidnightOil from "./index";

const V1_POLICY = {
  policy_version: 1 as const,
  required_coverage: "insights_and_output_paragraphs" as const,
  exploratory_questions: "operational_only" as const,
  external_receipts: "local_canonical_chunk_required" as const,
  unsupported_output: "retain_operational_only" as const,
  legacy_rows: "legacy_unverified" as const,
};

const {
  createMidnightOilJob,
  approveMidnightOilCeiling,
  depositMidnightOilJob,
  runMidnightOilJob,
  getMidnightOilJob,
  retryMidnightOilGraphAdmission,
  fetchMidnightOilLiveStepStatus,
  fetchDecisionTreeSelection,
  seedTwinNotes,
  hydratePublicationRefsMock,
  parsePublicationRefsMock,
  collectDeepResearchSpawnIdsMock,
  listRecentDeepResearchSpawnIdsMock,
  pushRecentDeepResearchSpawnIdMock,
} = vi.hoisted(() => ({
  createMidnightOilJob: vi.fn<(...args: unknown[]) => unknown>(),
  approveMidnightOilCeiling: vi.fn<(...args: unknown[]) => unknown>(),
  depositMidnightOilJob: vi.fn<(...args: unknown[]) => unknown>(),
  runMidnightOilJob: vi.fn<(...args: unknown[]) => unknown>(),
  getMidnightOilJob: vi.fn<(...args: unknown[]) => unknown>(),
  retryMidnightOilGraphAdmission: vi.fn<(...args: unknown[]) => unknown>(),
  fetchMidnightOilLiveStepStatus: vi.fn(async () => ({
    view_format: "html",
    product_panel: "midnight_oil_live_step_status",
    source: "substrate.midnight_oil.product_path",
    offline_honest: true,
    live_env: false,
    injector_installed: false,
    live_env_flag: "ANTIEK_MIDNIGHT_OIL_LIVE_STEP",
    notes: [
      "Midnight Oil default: offline stub steps — no live multi-provider swarm.",
    ],
    html: "<p>offline_honest=true</p>",
  })),
  fetchDecisionTreeSelection: vi.fn<(...args: unknown[]) => unknown>(),
  seedTwinNotes: vi.fn<(...args: unknown[]) => unknown>(),
  hydratePublicationRefsMock: vi.fn(async (refs: string[]) => ({
    ok: refs.map((reference) => ({
      asset_id: `pub_${reference}`,
      ref: { handle: reference },
      title: reference,
      body_text: "",
      fetched: false,
      offline_honest: true,
      view_format: "html" as const,
      notes: [],
      product_panel: "test",
      source: "test",
    })),
    failed: [] as Array<{ reference: string; error: string }>,
    view_format: "html" as const,
  })),
  parsePublicationRefsMock: vi.fn((raw: string) =>
    (raw || "")
      .split(/\r?\n+/)
      .map((l) => l.trim())
      .filter(Boolean),
  ),
  collectDeepResearchSpawnIdsMock: vi.fn(
    (source: {
      extraSpawnIds?: readonly string[] | null;
      recentSpawnIds?: readonly string[] | null;
    }) => {
      const seen = new Set<string>();
      const out: string[] = [];
      for (const x of [
        ...(source.extraSpawnIds ?? []),
        ...(source.recentSpawnIds ?? []),
      ]) {
        const id = String(x || "").trim();
        if (!id || seen.has(id)) continue;
        seen.add(id);
        out.push(id);
      }
      return out;
    },
  ),
  listRecentDeepResearchSpawnIdsMock: vi.fn(() => [] as string[]),
  pushRecentDeepResearchSpawnIdMock: vi.fn((id: string) => {
    const sid = String(id || "").trim();
    if (!sid) return listRecentDeepResearchSpawnIdsMock();
    const prev = listRecentDeepResearchSpawnIdsMock().filter(
      (x: string) => x !== sid,
    );
    const next = [sid, ...prev];
    listRecentDeepResearchSpawnIdsMock.mockReturnValue(next);
    return next;
  }),
}));

vi.mock("../../api/midnightOil", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/midnightOil")>();
  return {
    ...actual,
    MidnightOilConsentExpiredError: class MidnightOilConsentExpiredError extends Error {},
    createMidnightOilJob,
    approveMidnightOilCeiling,
    depositMidnightOilJob,
    runMidnightOilJob,
    getMidnightOilJob,
    retryMidnightOilGraphAdmission,
    fetchMidnightOilLiveStepStatus,
  };
});

vi.mock("../../api/engagement", () => ({
  seedTwinNotes: (...args: unknown[]) => seedTwinNotes(...(args as Parameters<typeof seedTwinNotes>)),
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
  estimatePromptCost: vi.fn(async () => ({
    estimated_usd_low: null,
    estimated_usd_high: null,
    would_exceed_budget: null,
    pricing_known: false,
    notes: [],
    assumed_input_tokens: 500,
    assumed_output_tokens: 500,
    tier: null,
    provider: null,
    model: null,
  })),
  fetchDecisionTreeSelection: (...args: unknown[]) =>
    fetchDecisionTreeSelection(...(args as Parameters<typeof fetchDecisionTreeSelection>)),
  fetchDepthTiers: (...args: unknown[]) => fetchDepthTiers(...(args as Parameters<typeof fetchDepthTiers>)),
}));

vi.mock("../../components/engagement/ResearchLaunchBudgetPanel", () => {
  const React = require("react") as typeof import("react");
  return {
    ResearchLaunchBudgetPanel: (props: {
      promptText: string;
      researchTier?: string;
      allowTierPick?: boolean;
      onResearchTierChange?: (t: "fast" | "deep" | "wrestle") => void;
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
          data-allow-tier-pick={props.allowTierPick ? "true" : "false"}
          data-research-tier={props.researchTier || "deep"}
          data-prompt-len={String(props.promptText?.length ?? 0)}
        >
          goals={props.promptText.length}
          {props.allowTierPick ? (
            <button
              type="button"
              data-testid="research-launch-tier-wrestle"
              onClick={() => props.onResearchTierChange?.("wrestle")}
            >
              wrestle
            </button>
          ) : null}
        </div>
      );
    },
  };
});

vi.mock("../../components/engagement/DecisionTreeDriverBadge", () => ({
  DecisionTreeDriverBadge: (props: {
    researchTier?: string | null;
  }) => (
    <div
      data-testid="decision-tree-driver-badge-stub"
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
    >
      driver badge{props.researchTier ? `:tier=${props.researchTier}` : ""}
    </div>
  ),
}));

vi.mock("../../components/engagement/ResearchProgressPanel", () => ({
  ResearchProgressPanel: (props: {
    spawnId: string;
    autoLoad?: boolean;
    autoSeedIfEmpty?: boolean;
    researchTier?: string | null;
    pollIntervalMs?: number;
  }) => (
    <div
      data-testid="research-progress-panel-stub"
      data-research-tier={props.researchTier ?? ""}
      data-poll-ms={String(props.pollIntervalMs ?? 0)}
    >
      spawn={props.spawnId}:auto={String(Boolean(props.autoLoad))}:seed=
      {String(Boolean(props.autoSeedIfEmpty))}:tier=
      {props.researchTier ?? ""}:poll={String(props.pollIntervalMs ?? 0)}
    </div>
  ),
}));

vi.mock("../../components/engagement/CollectiveResearchPanel", () => ({
  CollectiveResearchPanel: (props: {
    availableSpawnIds: string[];
    parentAssetId?: string | null;
    recentSpawnIds?: readonly string[] | null;
    openSpawnIds?: readonly string[] | null;
    preferredSpawnId?: string | null;
    onRecentSpawnsCleared?: () => void;
    onDocMerged?: (r: { document_id: string }) => void;
  }) => (
    <div
      data-testid="collective-research-panel-stub"
      data-parent={props.parentAssetId ?? ""}
      data-spawns={props.availableSpawnIds.join(",")}
      data-recent={
        props.recentSpawnIds != null ? props.recentSpawnIds.join(",") : ""
      }
      data-open={
        props.openSpawnIds != null ? props.openSpawnIds.join(",") : ""
      }
      data-has-open-spawn-ids={props.openSpawnIds != null ? "1" : "0"}
      data-preferred={props.preferredSpawnId ?? ""}
      data-has-clear={props.onRecentSpawnsCleared ? "1" : "0"}
      data-has-merged={props.onDocMerged ? "1" : "0"}
    >
      parent={props.parentAssetId ?? ""}:spawns=
      {props.availableSpawnIds.join(",")}
    </div>
  ),
}));

vi.mock("../../components/engagement/TwinNotesPanel", () => ({
  TwinNotesPanel: (props: {
    assetId: string;
    spawnId?: string | null;
    researchTier?: string | null;
    autoLoad?: boolean;
    autoSeedIfEmpty?: boolean;
    autoPromoteAfterLoad?: boolean;
    onPromoted?: () => void;
  }) => (
    <div
      data-testid="twin-notes-panel-stub"
      data-asset-id={props.assetId}
      data-spawn-id={props.spawnId ?? ""}
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
      data-auto-load={props.autoLoad ? "1" : "0"}
      data-auto-seed={props.autoSeedIfEmpty ? "1" : "0"}
      data-auto-promote={props.autoPromoteAfterLoad ? "1" : "0"}
      data-has-promoted={props.onPromoted ? "1" : "0"}
    >
      twins={props.assetId}
      {props.researchTier ? `:tier=${props.researchTier}` : ""}
    </div>
  ),
}));

vi.mock("../../components/engagement/ResearchContextPanel", () => ({
  ResearchContextPanel: (props: {
    assetId: string;
    spawnId?: string | null;
    autoLoad?: boolean;
    researchTier?: string | null;
  }) => (
    <div
      data-testid="research-context-panel-stub"
      data-asset-id={props.assetId}
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
      data-spawn-id={props.spawnId ?? ""}
      data-auto-load={props.autoLoad ? "1" : "0"}
    >
      context={props.assetId}
    </div>
  ),
}));

vi.mock("../../workspace/windowsStore", () => ({
  useWindows: (sel: (s: { windows: Record<string, unknown> }) => unknown) =>
    sel({ windows: {} }),
}));

vi.mock("../ResearchWorkstation/publicationRefs", () => ({
  parsePublicationRefs: (...args: unknown[]) =>
    parsePublicationRefsMock(...(args as [string])),
  hydratePublicationRefs: (...args: unknown[]) =>
    hydratePublicationRefsMock(...(args as [string[]])),
}));

vi.mock("../../workspace/collectDeepResearchSpawnIds", () => ({
  collectDeepResearchSpawnIds: (...args: unknown[]) =>
    collectDeepResearchSpawnIdsMock(...(args as Parameters<typeof collectDeepResearchSpawnIdsMock>)),
}));

vi.mock("../../workspace/recentDeepResearchSpawns", () => ({
  listRecentDeepResearchSpawnIds: (...args: unknown[]) =>
    listRecentDeepResearchSpawnIdsMock(...(args as Parameters<typeof listRecentDeepResearchSpawnIdsMock>)),
  pushRecentDeepResearchSpawnId: (...args: unknown[]) =>
    pushRecentDeepResearchSpawnIdMock(...(args as [string])),
}));

const openWindow = vi.fn(() => "win:moil-deposit:draft_moil_asset_dep_abc");
vi.mock("../../components/windows/openWindow", () => ({
  openWindow: (...args: unknown[]) => openWindow(...(args as Parameters<typeof openWindow>)),
}));

describe("MidnightOil mode", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    createMidnightOilJob.mockReset();
    approveMidnightOilCeiling.mockReset();
    fetchMidnightOilLiveStepStatus.mockClear();
    seedTwinNotes.mockReset().mockResolvedValue({
      asset_id: "draft_moil_asset_dep_abc",
      seeded: true,
      view_format: "html",
      notes: [],
      insight_count: 1,
      question_count: 1,
    });
    depositMidnightOilJob.mockReset();
    runMidnightOilJob.mockReset();
    getMidnightOilJob.mockReset();
    retryMidnightOilGraphAdmission.mockReset();
    openWindow.mockClear();
    collectDeepResearchSpawnIdsMock.mockClear();
    listRecentDeepResearchSpawnIdsMock.mockReset().mockReturnValue([]);
    pushRecentDeepResearchSpawnIdMock.mockClear();
    hydratePublicationRefsMock.mockClear();
    parsePublicationRefsMock.mockClear();
    parsePublicationRefsMock.mockImplementation((raw: string) =>
      (raw || "")
        .split(/\r?\n+/)
        .map((l) => l.trim())
        .filter(Boolean),
    );
    hydratePublicationRefsMock.mockImplementation(async (refs: string[]) => ({
      ok: refs.map((reference) => ({
        asset_id: `pub_${reference}`,
        ref: { handle: reference },
        title: reference,
        body_text: "",
        fetched: false,
        offline_honest: true,
        view_format: "html" as const,
        notes: [],
        product_panel: "test",
        source: "test",
      })),
      failed: [] as Array<{ reference: string; error: string }>,
      view_format: "html" as const,
    }));
    // Keep ring-update behavior after clear.
    pushRecentDeepResearchSpawnIdMock.mockImplementation((id: string) => {
      const sid = String(id || "").trim();
      if (!sid) return listRecentDeepResearchSpawnIdsMock();
      const prev = listRecentDeepResearchSpawnIdsMock().filter(
        (x: string) => x !== sid,
      );
      const next = [sid, ...prev];
      listRecentDeepResearchSpawnIdsMock.mockReturnValue(next);
      return next;
    });
    fetchDecisionTreeSelection.mockReset();
    fetchDecisionTreeSelection.mockResolvedValue({
      installed: false,
      model_id: null,
      provider_id: null,
    });
  });

  it("surfaces offline-honest live-step status (hy)", async () => {
    render(<MidnightOil />);
    await waitFor(() => {
      expect(fetchMidnightOilLiveStepStatus).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByTestId("moil-live-step-status")).toBeTruthy();
    });
    const panel = screen.getByTestId("moil-live-step-status");
    expect(panel.getAttribute("data-offline-honest")).toBe("true");
    expect(panel.getAttribute("data-live-env")).toBe("false");
    expect(panel.getAttribute("data-injector-installed")).toBe("false");
    expect(panel.textContent).toMatch(/offline-honest stub steps/);
  });

  it("links to Settings for driver & budget (ic)", () => {
    render(<MidnightOil />);
    const link = screen.getByTestId("moil-settings-link");
    expect(link.getAttribute("href")).toBe("/settings#decision-tree-panel");
    expect(link.textContent).toMatch(/model driver & budget/i);
  });

  it("links competitive DR scorecard and FUTURE brief (aiu)", () => {
    render(<MidnightOil />);
    // Residual (arp): offline product surface catalog honesty (parity arm/arn/aro).
    const links = screen.getByTestId("moil-competitive-links");
    expect(links.getAttribute("data-html-first")).toBe("true");
    expect(links.getAttribute("data-live-injectors-deferred")).toBe("true");
    expect(links.getAttribute("data-notdiamond-is-router")).toBe("false");
    expect(
      Number(links.getAttribute("data-offline-surface-count") || 0),
    ).toBeGreaterThanOrEqual(10);
    const scorecard = screen.getByTestId("moil-competitive-scorecard-link");
    expect(scorecard.getAttribute("href")).toBe(
      "/settings#settings-competitive-dr-scorecard",
    );
    expect(scorecard.getAttribute("data-notdiamond-is-router")).toBe("false");
    expect(scorecard.textContent).toMatch(/competitive DR scorecard/i);
    const future = screen.getByTestId("moil-competitive-dr-future-agent-link");
    expect(future.getAttribute("href") || "").toBe(
      "/settings#settings-competitive-dr-scorecard",
    );
    expect(future.textContent).toMatch(/competitive quality status/i);
  });

  it("links Settings prompt-cost projection for budget-before-fire (akk)", () => {
    render(<MidnightOil />);
    const link = screen.getByTestId("moil-prompt-cost-projection-link");
    expect(link.getAttribute("href")).toBe("/settings#prompt-cost-projection");
    expect(link.textContent).toMatch(/prompt-cost projection/i);
  });

  it("links dual-gate L4 MO checklist section for live-step prep (ml/wx)", () => {
    render(<MidnightOil />);
    const dual = screen.getByTestId("moil-dual-gate-checklist-link");
    // Residual (wx): deep-link L4 MO section (not checklist root only).
    expect(dual.getAttribute("href")).toBe("/settings#moil-live-step-status");
    expect(dual.textContent).toMatch(/L4 MO checklist/i);
  });

  it("links Settings L4 MO live-step readiness (uh)", async () => {
    render(<MidnightOil />);
    await waitFor(() => {
      expect(screen.getByTestId("moil-live-step-status")).toBeTruthy();
    });
    const panel = screen.getByTestId("moil-live-step-status");
    expect(panel.getAttribute("data-l4-prep")).toBe("true");
    expect(panel.getAttribute("data-never-enables-live")).toBe("true");
    const l4 = screen.getByTestId("moil-settings-l4-live-step-link");
    expect(l4.getAttribute("href")).toBe("/settings#moil-live-step-status");
    expect(l4.textContent).toMatch(/L4 MO live-step/i);
  });

  it("shows multi-goal swarm plan chrome and appends templates (aof)", () => {
    render(<MidnightOil />);
    const plan = screen.getByTestId("moil-goals-plan");
    expect(plan.getAttribute("data-goal-count")).toBe("0");
    expect(Number(plan.getAttribute("data-template-count"))).toBeGreaterThanOrEqual(
      3,
    );
    // Residual (ara): north-star templates + plan readiness pure helper chrome.
    expect(Number(plan.getAttribute("data-template-count") || 0)).toBeGreaterThanOrEqual(
      8,
    );
    expect(screen.getByTestId("moil-goal-template-knowledge_dense_refs")).toBeTruthy();
    expect(screen.getByTestId("moil-goal-template-multi_agent_analysis")).toBeTruthy();
    expect(screen.getByTestId("moil-goal-template-budget_wrestle")).toBeTruthy();
    expect(screen.getByTestId("moil-goal-template-reading_merge")).toBeTruthy();
    const readiness = screen.getByTestId("moil-plan-readiness");
    expect(readiness.getAttribute("data-plan-ready")).toBe("false");
    expect(readiness.getAttribute("data-html-first")).toBe("true");
    expect(readiness.textContent).toMatch(/Plan readiness/i);
    // Residual (ard): create disabled until plan ready (goals+duration).
    expect(
      (screen.getByTestId("moil-create-recommend-ceiling") as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(
      screen
        .getByTestId("moil-create-recommend-ceiling")
        .getAttribute("data-plan-ready"),
    ).toBe("false");
    expect(screen.getByTestId("moil-goal-templates")).toBeTruthy();
    fireEvent.click(screen.getByTestId("moil-goal-template-map_landscape"));
    expect(screen.getByTestId("moil-goals-plan").getAttribute("data-goal-count")).toBe(
      "1",
    );
    // Default duration 60m → plan ready once ≥1 goal.
    expect(
      screen.getByTestId("moil-plan-readiness").getAttribute("data-plan-ready"),
    ).toBe("true");
    // Residual (ard): create button gated by plan readiness pure helper.
    const createBtn = screen.getByTestId("moil-create-recommend-ceiling");
    expect(createBtn.getAttribute("data-plan-ready")).toBe("true");
    expect((createBtn as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByTestId("moil-goals-plan-list")).toBeTruthy();
    expect(screen.getByTestId("moil-goals-plan-item-0").textContent).toMatch(
      /competitive landscape/i,
    );
    // Second click does not invent a duplicate.
    fireEvent.click(screen.getByTestId("moil-goal-template-map_landscape"));
    expect(screen.getByTestId("moil-goals-plan").getAttribute("data-goal-count")).toBe(
      "1",
    );
    fireEvent.click(screen.getByTestId("moil-goal-template-evidence_chain"));
    expect(screen.getByTestId("moil-goals-plan").getAttribute("data-goal-count")).toBe(
      "2",
    );
    const input = screen.getByTestId("moil-goals-input") as HTMLTextAreaElement;
    expect(input.value.split("\n").filter(Boolean)).toHaveLength(2);
  });

  it("lists full swarm goals on job receipt after create (aog)", async () => {
    createMidnightOilJob.mockResolvedValueOnce({
      job_id: "moil_goals_plan",
      goals: [
        "Map competitive landscape",
        "Build evidence chain",
        "Ground publication: arxiv:1706.03762",
      ],
      duration_minutes: 60,
      model_id: "default",
      research_tier: "deep",
      fanout_depth: 3,
      status: "awaiting_approval",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      recommended_price_ceiling_usd: 3.6,
      view_format: "html",
      runnable: false,
      notes: "created",
    });
    render(<MidnightOil />);
    fireEvent.change(screen.getByLabelText(/^Goals \(one per line\)$/i), {
      target: {
        value: "Map competitive landscape\nBuild evidence chain",
      },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /create job \+ recommend ceiling/i }),
    );
    await waitFor(() => expect(screen.getByTestId("moil-job")).toBeTruthy());
    const jobPlan = screen.getByTestId("moil-job-goals-plan");
    expect(jobPlan.getAttribute("data-goal-count")).toBe("3");
    expect(jobPlan.getAttribute("data-research-goal-count")).toBe("2");
    expect(jobPlan.getAttribute("data-grounded-pub-goal-count")).toBe("1");
    expect(screen.getByTestId("moil-job-goals-plan-item-0").textContent).toMatch(
      /Map competitive landscape/,
    );
    expect(
      screen
        .getByTestId("moil-job-goals-plan-item-2")
        .getAttribute("data-grounded-pub"),
    ).toBe("true");
  });

  it("soft-hints when goal count exceeds fan-out depth (aoh)", () => {
    render(<MidnightOil />);
    const hint0 = screen.getByTestId("moil-goals-fanout-hint");
    expect(hint0.getAttribute("data-exceeds-fanout")).toBe("false");
    expect(hint0.getAttribute("data-fanout-depth")).toBe("3");
    fireEvent.change(screen.getByTestId("moil-goals-input"), {
      target: {
        value: "G1\nG2\nG3\nG4",
      },
    });
    const hint = screen.getByTestId("moil-goals-fanout-hint");
    expect(hint.getAttribute("data-goal-count")).toBe("4");
    expect(hint.getAttribute("data-exceeds-fanout")).toBe("true");
    expect(hint.textContent).toMatch(/raise fan-out/i);
    // Residual (aop): operator click matches fan-out to goal count.
    const matchBtn = screen.getByTestId("moil-match-fanout-to-goals");
    expect(matchBtn.getAttribute("data-match-target")).toBe("4");
    fireEvent.click(matchBtn);
    expect(
      (screen.getByTestId("moil-fanout-depth") as HTMLInputElement).value,
    ).toBe("4");
    expect(
      screen.getByTestId("moil-goals-fanout-hint").getAttribute(
        "data-exceeds-fanout",
      ),
    ).toBe("false");
    expect(
      screen.getByTestId("moil-goals-fanout-hint").textContent,
    ).toMatch(/coverage ok/i);
    expect(screen.queryByTestId("moil-match-fanout-to-goals")).toBeNull();
  });

  it("previews recommended ceiling before create (adx)", () => {
    render(<MidnightOil />);
    const preview = screen.getByTestId("moil-ceiling-preview");
    expect(preview.getAttribute("data-preview-only")).toBe("true");
    // Residual (ady): offline rate table for default model.
    expect(preview.getAttribute("data-pricing-source")).toBe(
      "offline-table:default",
    );
    expect(preview.getAttribute("data-model-id")).toBe("default");
    // Default form: 60m · fanout 3 · deep · default rates → $3.60 (substrate parity).
    expect(preview.getAttribute("data-recommended-usd")).toBe("3.6");
    expect(preview.getAttribute("data-duration-minutes")).toBe("60");
    expect(preview.getAttribute("data-fanout-depth")).toBe("3");
    expect(preview.getAttribute("data-research-tier")).toBe("deep");
    expect(screen.getByTestId("moil-ceiling-preview-usd").textContent).toMatch(
      /\$3\.60/,
    );
    expect(preview.textContent).toMatch(/create job remains authoritative/i);
  });

  it("previews model-aware ceiling rates for gpt-5.5 (ady)", async () => {
    render(<MidnightOil />);
    const modelInput = screen.getByDisplayValue("default") as HTMLInputElement;
    fireEvent.change(modelInput, { target: { value: "gpt-5.5" } });
    await waitFor(() => {
      const preview = screen.getByTestId("moil-ceiling-preview");
      expect(preview.getAttribute("data-model-id")).toBe("gpt-5.5");
      expect(preview.getAttribute("data-pricing-source")).toBe(
        "offline-table:gpt-5.5",
      );
      // 60m · fanout 3 · deep · combined 20 → $18.00
      expect(preview.getAttribute("data-recommended-usd")).toBe("18");
    });
  });

  it("stamps preview-matches-server when create ceiling equals form preview (aeg)", async () => {
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_preview_match",
      goals: ["Match preview"],
      duration_minutes: 60,
      status: "awaiting_approval",
      acceptance_policy_version: 1,
      acceptance_policy: {
        policy_version: 1,
        required_coverage: "insights_and_output_paragraphs",
        exploratory_questions: "operational_only",
        external_receipts: "local_canonical_chunk_required",
        unsupported_output: "retain_operational_only",
        legacy_rows: "legacy_unverified",
      },
      research_brief_hash: "a".repeat(64),
      approved_research_brief_hash: null,
      research_brief_state: "proposed",
      research_result_state: "none",
      deposit_state: "pending",
      graph_projection_state: "pending",
      research_tier: "deep",
      fanout_depth: 3,
      recommended_price_ceiling_usd: 3.6,
      view_format: "html",
      runnable: false,
      html: "<p>Match</p>",
    });
    render(<MidnightOil />);
    fireEvent.change(screen.getByLabelText(/^Goals \(one per line\)$/i), {
      target: { value: "Match preview" },
    });
    // Default fanout 3 · deep · default rates → preview $3.60
    fireEvent.click(
      screen.getByRole("button", { name: /create job \+ recommend ceiling/i }),
    );
    await waitFor(() => {
      expect(screen.getByTestId("moil-ceiling-metrics")).toBeTruthy();
    });
    const metrics = screen.getByTestId("moil-ceiling-metrics");
    expect(metrics.getAttribute("data-recommended-usd")).toBe("3.6");
    expect(metrics.getAttribute("data-preview-usd")).toBe("3.6");
    expect(metrics.getAttribute("data-preview-matches-server")).toBe("true");
    expect(metrics.textContent).toMatch(/preview=server/);
  });

  it("mounts budget projection panel before create (cs)", () => {
    render(<MidnightOil />);
    expect(screen.getByTestId("moil-budget-mount")).toBeTruthy();
    expect(screen.getByTestId("research-launch-budget-panel-stub")).toBeTruthy();
    // Residual (gn): depth-tier picker on Midnight Oil create path.
    expect(
      screen
        .getByTestId("research-launch-budget-panel-stub")
        .getAttribute("data-allow-tier-pick"),
    ).toBe("true");
    expect(
      screen.getByTestId("moil-budget-mount").getAttribute("data-view-format"),
    ).toBe("html");
  });

  it("prefills model_id from decision-tree driver when installed (cz)", async () => {
    fetchDecisionTreeSelection.mockResolvedValue({
      installed: true,
      model_id: "claude-opus-4-8",
      provider_id: "anthropic",
    });
    render(<MidnightOil />);
    await waitFor(() => {
      expect(fetchDecisionTreeSelection).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(
        (screen.getByTestId("moil-model-id") as HTMLInputElement).value,
      ).toBe("claude-opus-4-8");
    });
    const prefill = screen.getByTestId("moil-driver-prefill");
    expect(prefill.getAttribute("data-prefill")).toBe("installed");
    expect(prefill.getAttribute("data-view-format")).toBe("html");
    expect(screen.getByTestId("decision-tree-driver-badge-stub")).toBeTruthy();
    // Residual (kv): Midnight Oil wires researchTier into driver badge (ku).
    expect(
      screen
        .getByTestId("decision-tree-driver-badge-stub")
        .getAttribute("data-research-tier"),
    ).toBe("deep");
  });

  it("keeps default model when no driver installed (cz)", async () => {
    render(<MidnightOil />);
    await waitFor(() => {
      expect(
        screen.getByTestId("moil-driver-prefill").getAttribute("data-prefill"),
      ).toBe("none");
    });
    expect(
      (screen.getByTestId("moil-model-id") as HTMLInputElement).value,
    ).toBe("default");
  });

  it("creates job with wrestle research_tier from budget picker (gs)", async () => {
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_wrestle",
      goals: ["Long-horizon synthesis"],
      duration_minutes: 90,
      status: "awaiting_approval",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      research_tier: "wrestle",
      recommended_price_ceiling_usd: 5.0,
      view_format: "html",
      runnable: false,
      html: "<p>Wrestle job</p>",
    });
    render(<MidnightOil />);
    fireEvent.change(screen.getByLabelText(/^Goals \(one per line\)$/i), {
      target: { value: "Long-horizon synthesis" },
    });
    fireEvent.click(screen.getByTestId("research-launch-tier-wrestle"));
    fireEvent.click(
      screen.getByRole("button", { name: /create job \+ recommend ceiling/i }),
    );
    await waitFor(() => {
      expect(createMidnightOilJob).toHaveBeenCalledWith(
        expect.objectContaining({
          goals: ["Long-horizon synthesis"],
          research_tier: "wrestle",
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("moil-research-tier").textContent).toMatch(
        /wrestle/i,
      );
    });
    expect(
      screen.getByTestId("moil-research-tier").getAttribute("data-research-tier"),
    ).toBe("wrestle");
    // Residual (jl): tier factor transparency on recommended ceiling.
    const tierFactor = screen.getByTestId("moil-ceiling-tier-factor");
    expect(tierFactor.getAttribute("data-research-tier")).toBe("wrestle");
    expect(tierFactor.getAttribute("data-tier-multiplier")).toBe("2");
    expect(tierFactor.textContent).toMatch(/2\.0× \(wrestle\)/);
    expect(
      screen.getByTestId("moil-ceiling-formula-note").textContent,
    ).toMatch(/tier multiplier/);
  });

  it("creates job then approves at recommended ceiling", async () => {
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_test",
      goals: ["Map residual risks"],
      duration_minutes: 60,
      status: "awaiting_approval",
      acceptance_policy_version: 1,
      acceptance_policy: {
        policy_version: 1,
        required_coverage: "insights_and_output_paragraphs",
        exploratory_questions: "operational_only",
        external_receipts: "local_canonical_chunk_required",
        unsupported_output: "retain_operational_only",
        legacy_rows: "legacy_unverified",
      },
      research_brief_hash: "a".repeat(64),
      approved_research_brief_hash: null,
      research_brief_state: "proposed",
      research_result_state: "none",
      deposit_state: "pending",
      graph_projection_state: "pending",
      research_tier: "deep",
      recommended_price_ceiling_usd: 3.6,
      view_format: "html",
      runnable: false,
      html: "<p>Midnight Oil job receipt</p>",
    });
    approveMidnightOilCeiling.mockResolvedValue({
      job_id: "moil_test",
      goals: ["Map residual risks"],
      duration_minutes: 60,
      status: "approved",
      acceptance_policy_version: 1,
      acceptance_policy: {
        policy_version: 1,
        required_coverage: "insights_and_output_paragraphs",
        exploratory_questions: "operational_only",
        external_receipts: "local_canonical_chunk_required",
        unsupported_output: "retain_operational_only",
        legacy_rows: "legacy_unverified",
      },
      research_brief_hash: "a".repeat(64),
      approved_research_brief_hash: "a".repeat(64),
      research_brief_state: "approved",
      research_result_state: "none",
      deposit_state: "pending",
      graph_projection_state: "pending",
      research_tier: "deep",
      recommended_price_ceiling_usd: 3.6,
      approved_ceiling_usd: 3.6,
      view_format: "html",
      runnable: true,
      html: "<p>Approved</p>",
    });

    render(<MidnightOil />);
    fireEvent.change(screen.getByLabelText(/^Goals \(one per line\)$/i), {
      target: { value: "Map residual risks" },
    });
    // Residual (adc): fan-out control defaults to 3 and is passed on create.
    const fanout = screen.getByTestId("moil-fanout-depth");
    expect(fanout.getAttribute("data-default-fanout")).toBe("3");
    fireEvent.change(fanout, { target: { value: "5" } });
    fireEvent.click(
      screen.getByRole("button", { name: /create job \+ recommend ceiling/i }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("recommended-ceiling").textContent).toContain(
        "3.60",
      );
    });
    const proposedBrief = screen.getByTestId("moil-research-acceptance-brief");
    expect(proposedBrief.getAttribute("data-policy-version")).toBe("1");
    expect(proposedBrief.getAttribute("data-brief-state")).toBe("proposed");
    expect(proposedBrief.getAttribute("data-read-only")).toBe("false");
    expect(proposedBrief.textContent).toMatch(/review this rule before approving/i);
    expect(
      screen.getByTestId("moil-graph-admission-status").getAttribute("data-admission-state"),
    ).toBe("not_started");
    expect(createMidnightOilJob).toHaveBeenCalledWith(
      expect.objectContaining({
        fanout_depth: 5,
        duration_minutes: expect.any(Number),
      }),
    );
    // Residual (hn/add): recommended ceiling metrics + formula transparency.
    const metrics = screen.getByTestId("moil-ceiling-metrics");
    expect(metrics.getAttribute("data-job-id")).toBe("moil_test");
    expect(metrics.getAttribute("data-status")).toBe("awaiting_approval");
    expect(metrics.getAttribute("data-duration-minutes")).toBe("60");
    expect(metrics.getAttribute("data-goal-count")).toBe("1");
    expect(metrics.getAttribute("data-recommended-usd")).toBe("3.6");
    expect(metrics.getAttribute("data-research-tier")).toBe("deep");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    // Residual (add): form fanout=5 when job omits fanout_depth (mock has none).
    expect(metrics.getAttribute("data-fanout-depth")).toBe("5");
    expect(metrics.getAttribute("data-fanout-source")).toBe("form");
    expect(metrics.textContent).toMatch(/Ceiling audit/);
    expect(metrics.textContent).toMatch(/fanout=5/);
    // Residual (aeg): form preview vs server recommended (fanout 5 → preview $6 ≠ mock $3.6).
    expect(metrics.getAttribute("data-preview-usd")).toBe("6");
    expect(metrics.getAttribute("data-preview-matches-server")).toBe("false");
    expect(metrics.textContent).toMatch(/preview≠server/);
    const formula = screen.getByTestId("moil-ceiling-formula-note");
    expect(formula.textContent).toMatch(/1\.25 safety/);
    // Residual (ada/add): machine-readable ceiling formula constants + form fanout.
    expect(formula.getAttribute("data-tokens-per-minute")).toBe("4000");
    expect(formula.getAttribute("data-safety-factor")).toBe("1.25");
    expect(formula.getAttribute("data-fanout-depth")).toBe("5");
    expect(formula.getAttribute("data-fanout-source")).toBe("form");
    expect(formula.getAttribute("data-tier-multiplier")).toBe("1");
    expect(formula.getAttribute("data-research-tier")).toBe("deep");
    expect(formula.getAttribute("data-view-format")).toBe("html");
    expect(formula.textContent).toMatch(/tokens\/min \(4000\)/);
    expect(formula.textContent).toMatch(/fanout \(\s*5\s*\)/);
    expect(
      screen
        .getByTestId("recommended-ceiling")
        .getAttribute("data-recommended-usd"),
    ).toBe("3.6");
    // Residual (md): ceiling vs remaining budget fit (mock remaining=$5, ceiling=$3.6).
    const budgetFit = screen.getByTestId("moil-ceiling-budget-fit");
    expect(budgetFit.getAttribute("data-fit")).toBe("fits");
    expect(budgetFit.getAttribute("data-recommended-usd")).toBe("3.6");
    expect(budgetFit.getAttribute("data-remaining-usd")).toBe("5");
    expect(
      screen.getByTestId("moil-ceiling-budget-fit-label").textContent,
    ).toMatch(/fits remaining/i);
    // Residual (um): after-approve remaining projection (5 − 3.6 = 1.4).
    const after = screen.getByTestId("moil-ceiling-remaining-after");
    expect(after.getAttribute("data-remaining-after-usd")).toBe("1.4");
    expect(after.getAttribute("data-recommended-usd")).toBe("3.6");
    expect(after.getAttribute("data-remaining-usd")).toBe("5");
    expect(
      screen.getByTestId("moil-ceiling-remaining-after-label").textContent,
    ).toMatch(/remaining≈\$1\.40/);
    // Residual (un): custom ceiling remaining-after (input prefilled to recommended).
    const customAfter = screen.getByTestId("moil-custom-ceiling-remaining-after");
    expect(customAfter.getAttribute("data-custom-usd")).toBe("3.6");
    expect(customAfter.getAttribute("data-remaining-after-usd")).toBe("1.4");
    expect(customAfter.getAttribute("data-fit")).toBe("fits");
    fireEvent.change(screen.getByTestId("moil-custom-ceiling-input"), {
      target: { value: "2" },
    });
    expect(
      screen
        .getByTestId("moil-custom-ceiling-remaining-after")
        .getAttribute("data-remaining-after-usd"),
    ).toBe("3");
    expect(
      screen.getByTestId("moil-custom-ceiling-remaining-after-label").textContent,
    ).toMatch(/remaining≈\$3\.00/);

    fireEvent.click(
      screen.getByRole("button", { name: /approve at recommended/i }),
    );
    await waitFor(() => {
      expect(screen.getByTestId("approved-ceiling").textContent).toContain(
        "3.60",
      );
    });
    const approvedBrief = screen.getByTestId("moil-research-acceptance-brief");
    expect(approvedBrief.getAttribute("data-brief-state")).toBe("approved");
    expect(approvedBrief.getAttribute("data-read-only")).toBe("true");
    expect(approvedBrief.getAttribute("data-approved-hash")).toBe("a".repeat(64));
    expect(approveMidnightOilCeiling).toHaveBeenCalledWith({
      job_id: "moil_test",
      use_recommended: true,
    });
  });

  it("preserves refused operational HTML across status recovery", async () => {
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_refused",
      goals: ["Audit unsupported claims"],
      duration_minutes: 60,
      status: "queued",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      research_brief_hash: "b".repeat(64),
      approved_research_brief_hash: "b".repeat(64),
      research_brief_state: "approved",
      research_result_state: "none",
      deposit_state: "pending",
      graph_projection_state: "pending",
      recommended_price_ceiling_usd: 3.6,
      view_format: "html",
      runnable: false,
    });
    getMidnightOilJob.mockResolvedValue({
      job_id: "moil_refused",
      goals: ["Audit unsupported claims"],
      duration_minutes: 60,
      status: "complete",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      research_brief_hash: "b".repeat(64),
      approved_research_brief_hash: "b".repeat(64),
      research_brief_state: "approved",
      research_result_state: "returned",
      deposit_state: "complete",
      deposit_document_id: "doc-refused-html",
      graph_projection_state: "refused",
      graph_projection_reason: "claim_coverage_missing",
      recommended_price_ceiling_usd: 3.6,
      view_format: "html",
      runnable: false,
    });

    render(<MidnightOil />);
    fireEvent.change(screen.getByLabelText(/^Goals \(one per line\)$/i), {
      target: { value: "Audit unsupported claims" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /create job \+ recommend ceiling/i }),
    );

    await screen.findByTestId("moil-refresh-status");
    fireEvent.click(screen.getByTestId("moil-refresh-status"));
    const admission = await screen.findByTestId("moil-graph-admission-status");
    await waitFor(() => {
      expect(admission.getAttribute("data-admission-state")).toBe("refused");
    });
    expect(getMidnightOilJob).toHaveBeenCalledWith("moil_refused");
    expect(admission.getAttribute("data-admission-reason")).toBe(
      "claim_coverage_missing",
    );
    expect(admission.getAttribute("data-verified")).toBe("false");
    expect(admission.textContent).toMatch(/operational HTML retained/i);
    expect(admission.textContent).not.toMatch(/admitted to the knowledge graph/i);

    fireEvent.click(screen.getByTestId("moil-reopen-operational-html"));
    expect(openWindow).toHaveBeenCalledWith(
      "hosted_html_document",
      expect.objectContaining({ document_id: "doc-refused-html" }),
      expect.objectContaining({ mode: "floating" }),
    );
    expect(screen.queryByTestId("moil-retry-graph-admission")).toBeNull();
  });

  it("retries transient graph admission once without rerunning research", async () => {
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_retry",
      goals: ["Recover graph admission"],
      duration_minutes: 60,
      status: "complete",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      research_brief_hash: "c".repeat(64),
      approved_research_brief_hash: "c".repeat(64),
      research_brief_state: "approved",
      research_result_state: "returned",
      deposit_state: "complete",
      deposit_document_id: "doc-retry-html",
      graph_projection_state: "pending",
      graph_projection_reason: "graph_lock_unavailable",
      recommended_price_ceiling_usd: 3.6,
      view_format: "html",
      runnable: false,
    });
    let resolveRetry: (value: unknown) => void = () => undefined;
    retryMidnightOilGraphAdmission.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRetry = resolve;
        }),
    );

    render(<MidnightOil />);
    fireEvent.change(screen.getByLabelText(/^Goals \(one per line\)$/i), {
      target: { value: "Recover graph admission" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /create job \+ recommend ceiling/i }),
    );
    const retry = await screen.findByTestId("moil-retry-graph-admission");
    expect(retry.textContent).toMatch(/no research rerun/i);
    fireEvent.click(retry);
    fireEvent.click(retry);
    expect(retryMidnightOilGraphAdmission).toHaveBeenCalledTimes(1);
    expect(retryMidnightOilGraphAdmission).toHaveBeenCalledWith("moil_retry");
    expect((retry as HTMLButtonElement).disabled).toBe(true);

    resolveRetry({
      job_id: "moil_retry",
      goals: ["Recover graph admission"],
      duration_minutes: 60,
      status: "complete",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      research_brief_hash: "c".repeat(64),
      approved_research_brief_hash: "c".repeat(64),
      research_brief_state: "approved",
      research_result_state: "returned",
      deposit_state: "complete",
      deposit_document_id: "doc-retry-html",
      graph_projection_state: "complete",
      graph_projection_reason: null,
      graph_node_ids: ["node-recovered"],
      graph_deliverable_id: "dlv-recovered",
      recommended_price_ceiling_usd: 3.6,
      view_format: "html",
      runnable: false,
    });
    await waitFor(() => {
      expect(
        screen
          .getByTestId("moil-graph-admission-status")
          .getAttribute("data-admission-state"),
      ).toBe("admitted");
    });
    expect(screen.queryByTestId("moil-retry-graph-admission")).toBeNull();
    expect(screen.getByTestId("moil-graph-projection-nav")).toBeTruthy();
    expect(runMidnightOilJob).not.toHaveBeenCalled();
  });

  it("hides graph navigation for a contradictory complete response", async () => {
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_unknown_complete",
      goals: ["Inspect contradictory admission"],
      duration_minutes: 60,
      status: "complete",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      research_brief_state: "approved",
      research_result_state: "returned",
      deposit_state: "complete",
      graph_projection_state: "complete",
      graph_projection_reason: "claim_coverage_missing",
      graph_node_ids: ["node-must-not-open"],
      recommended_price_ceiling_usd: 3.6,
      view_format: "html",
      runnable: false,
    });

    render(<MidnightOil />);
    fireEvent.change(screen.getByLabelText(/^Goals \(one per line\)$/i), {
      target: { value: "Inspect contradictory admission" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /create job \+ recommend ceiling/i }),
    );

    const admission = await screen.findByTestId("moil-graph-admission-status");
    expect(admission.getAttribute("data-admission-state")).toBe("unknown");
    expect(admission.getAttribute("data-verified")).toBe("false");
    expect(screen.queryByTestId("moil-graph-projection-nav")).toBeNull();
  });

  it("soft-gates approve when ceiling may exceed remaining budget (me)", async () => {
    // Override budget mock remaining to $1 so ceiling $3.6 may_exceed.
    // Re-render path: use existing mock remaining=5 for create, then we need
    // a separate mock — patch via creating high ceiling + low remaining is
    // hard mid-mock; instead create with huge recommended and reuse remaining=5.
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_over",
      goals: ["Huge wrestle"],
      duration_minutes: 600,
      status: "awaiting_approval",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      research_tier: "wrestle",
      recommended_price_ceiling_usd: 50,
      view_format: "html",
      runnable: false,
      html: "<p>over</p>",
    });
    approveMidnightOilCeiling.mockResolvedValue({
      job_id: "moil_over",
      goals: ["Huge wrestle"],
      duration_minutes: 600,
      status: "approved",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      research_tier: "wrestle",
      recommended_price_ceiling_usd: 50,
      approved_ceiling_usd: 50,
      view_format: "html",
      runnable: true,
      html: "<p>ok</p>",
    });
    render(<MidnightOil />);
    fireEvent.change(screen.getByLabelText(/^Goals \(one per line\)$/i), {
      target: { value: "Huge wrestle" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /create job \+ recommend ceiling/i }),
    );
    await waitFor(() => {
      expect(screen.getByTestId("moil-ceiling-budget-fit").getAttribute("data-fit")).toBe(
        "may_exceed",
      );
    });
    // Residual (arz): soft-gate is CTA disabled (not only handler error).
    const approveRec = screen.getByTestId(
      "moil-approve-recommended",
    ) as HTMLButtonElement;
    expect(approveRec.getAttribute("data-may-exceed")).toBe("true");
    expect(approveRec.getAttribute("data-approve-ready")).toBe("false");
    expect(approveRec.getAttribute("data-budget-soft-gate")).toBe("true");
    expect(approveRec.disabled).toBe(true);
    expect(approveRec.getAttribute("title") || "").toMatch(
      /may exceed remaining daily budget/i,
    );
    fireEvent.click(approveRec);
    expect(approveMidnightOilCeiling).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("moil-force-ceiling-over-budget").querySelector("input")!);
    await waitFor(() => {
      expect(
        (screen.getByTestId("moil-approve-recommended") as HTMLButtonElement)
          .disabled,
      ).toBe(false);
    });
    expect(
      screen.getByTestId("moil-approve-recommended").getAttribute("data-approve-ready"),
    ).toBe("true");
    fireEvent.click(screen.getByTestId("moil-approve-recommended"));
    await waitFor(() => {
      expect(approveMidnightOilCeiling).toHaveBeenCalledWith({
        job_id: "moil_over",
        use_recommended: true,
      });
    });
  });

  it("ceiling formula prefers job fanout_depth over form (add)", async () => {
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_fanout_job",
      goals: ["Job fanout wins"],
      duration_minutes: 30,
      status: "awaiting_approval",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      research_tier: "deep",
      fanout_depth: 7,
      recommended_price_ceiling_usd: 2.5,
      view_format: "html",
      runnable: false,
      html: "<p>job fanout</p>",
    });
    render(<MidnightOil />);
    fireEvent.change(screen.getByLabelText(/^Goals \(one per line\)$/i), {
      target: { value: "Job fanout wins" },
    });
    fireEvent.change(screen.getByTestId("moil-fanout-depth"), {
      target: { value: "2" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /create job \+ recommend ceiling/i }),
    );
    await waitFor(() => {
      expect(
        screen.getByTestId("moil-ceiling-metrics").getAttribute("data-fanout-source"),
      ).toBe("job");
    });
    expect(
      screen.getByTestId("moil-ceiling-metrics").getAttribute("data-fanout-depth"),
    ).toBe("7");
    expect(screen.getByTestId("moil-ceiling-metrics").textContent).toMatch(
      /fanout=7/,
    );
    expect(
      screen.getByTestId("moil-ceiling-formula-note").getAttribute("data-fanout-source"),
    ).toBe("job");
    expect(
      screen.getByTestId("moil-ceiling-formula-note").getAttribute("data-fanout-depth"),
    ).toBe("7");
  });

  it("deposits results and shows progress after approve", async () => {
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_dep",
      goals: ["Wrestle with twin notes"],
      duration_minutes: 30,
      status: "awaiting_approval",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      recommended_price_ceiling_usd: 2.0,
      view_format: "html",
      runnable: false,
      html: "<p>Receipt</p>",
    });
    approveMidnightOilCeiling.mockResolvedValue({
      job_id: "moil_dep",
      goals: ["Wrestle with twin notes"],
      duration_minutes: 30,
      status: "approved",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      recommended_price_ceiling_usd: 2.0,
      approved_ceiling_usd: 2.0,
      view_format: "html",
      runnable: true,
      html: "<p>Approved</p>",
    });
    runMidnightOilJob.mockResolvedValue({
      job_id: "moil_dep",
      status: "queued",
      spent_usd: 0,
      approved_ceiling_usd: 2.0,
      spawn_ids: ["spn_1"],
      goals_total: 1,
      steps_cap: 1,
      elapsed_ms: 1,
      view_format: "html",
      runnable: false,
      offline: true,
      live_step: false,
      queued: true,
      operation_id: "operation-dep",
      queue_state: "queued",
      deposit: null,
    });
    getMidnightOilJob.mockResolvedValue({
      job_id: "moil_dep",
      goals: ["Wrestle with twin notes"],
      duration_minutes: 30,
      status: "complete",
      operation_state: "complete",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      research_brief_state: "approved",
      research_brief_hash: "c".repeat(64),
      approved_research_brief_hash: "c".repeat(64),
      recommended_price_ceiling_usd: 2.0,
      approved_ceiling_usd: 2.0,
      graph_projection_state: "complete",
      graph_node_ids: ["node-1111111111111111"],
      graph_deliverable_id: "dlv-2222222222222222",
      view_format: "html",
      runnable: false,
    });
    depositMidnightOilJob.mockResolvedValue({
      job_id: "moil_dep",
      asset_id: "moil_asset_dep",
      document_id: "draft_moil_asset_dep_abc",
      twin_count: 2,
      spawn_ids: ["spn_1"],
      draft_combined: true,
      usage_recorded: true,
      progress_seeded: true,
      progress: {
        spawn_id: "spn_1",
        event_count: 5,
        latest_stage: "complete",
        is_terminal: true,
        view_format: "html",
        html: "<p>Deep research progress · complete</p>",
        events: [],
      },
      job_status: "complete",
      view_format: "html",
      html: "<p>Deposited HTML research asset</p>",
      notes: ["Deposit lands HTML research asset + twin notes."],
    });

    render(<MidnightOil />);
    fireEvent.change(screen.getByLabelText(/^Goals \(one per line\)$/i), {
      target: { value: "Wrestle with twin notes" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /create job \+ recommend ceiling/i }),
    );
    await waitFor(() => expect(screen.getByTestId("moil-job")).toBeTruthy());
    fireEvent.click(
      screen.getByRole("button", { name: /approve at recommended/i }),
    );
    await waitFor(() => expect(screen.getByTestId("moil-run-offline")).toBeTruthy());
    expect(screen.queryByTestId("moil-deposit")).toBeNull();
    expect(screen.getByTestId("moil-deposit-pending").textContent).toMatch(/terminal state/i);
    fireEvent.click(screen.getByTestId("moil-auto-deposit"));
    fireEvent.click(screen.getByTestId("moil-run-offline"));
    await waitFor(() => expect(screen.getByText("Worker queued")).toBeTruthy());
    expect(screen.queryByTestId("moil-deposit")).toBeNull();
    fireEvent.click(screen.getByTestId("moil-refresh-status"));
    await waitFor(() => expect(screen.getByTestId("moil-deposit")).toBeTruthy());
    expect(screen.queryByText("Worker queued")).toBeNull();
    expect(
      screen.getByTestId("moil-open-graph-node-0").getAttribute("href"),
    ).toBe("/knowledge-graph?node_id=node-1111111111111111");
    expect(
      screen
        .getByTestId("moil-graph-projection-nav")
        .getAttribute("data-deliverable-id"),
    ).toBe("dlv-2222222222222222");
    openWindow.mockClear();
    expect(screen.getByTestId("moil-auto-open-deposit")).toBeTruthy();
    fireEvent.click(screen.getByTestId("moil-deposit"));
    await waitFor(() => {
      expect(depositMidnightOilJob).toHaveBeenCalledWith({
        job_id: "moil_dep",
        draft_combined: true,
        record_progress: true,
        mark_complete: true,
        include_progress_html: true,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("moil-deposit-result").textContent).toMatch(
        /twins=2/,
      );
    });
    // Residual (gk/ahu): client offline twin reseed after deposit + MO port honesty.
    await waitFor(() => {
      expect(seedTwinNotes).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "draft_moil_asset_dep_abc",
          force_offline: true,
          body_text: expect.stringMatching(/Midnight Oil deposit HTML/i),
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("moil-twin-reseed-status").textContent).toMatch(
        /Twin notes reseeded/,
      );
    });
    // Residual (oo): TwinNotesPanel on deposit HTML asset (promote/chase).
    expect(screen.getByTestId("moil-deposit-twins-mount")).toBeTruthy();
    expect(
      screen.getByTestId("moil-deposit-twins-mount").getAttribute("data-asset-id"),
    ).toBe("draft_moil_asset_dep_abc");
    expect(
      screen
        .getByTestId("moil-deposit-twins-mount")
        .getAttribute("data-research-tier"),
    ).toBe("deep");
    expect(
      screen.getByTestId("moil-deposit-twins-refresh").getAttribute("data-refresh-key"),
    ).toBe("0");
    const twinsStub = screen.getByTestId("twin-notes-panel-stub");
    expect(twinsStub.getAttribute("data-asset-id")).toBe(
      "draft_moil_asset_dep_abc",
    );
    expect(twinsStub.getAttribute("data-spawn-id")).toBe("spn_1");
    expect(twinsStub.getAttribute("data-auto-load")).toBe("1");
    expect(twinsStub.getAttribute("data-auto-seed")).toBe("1");
    expect(twinsStub.getAttribute("data-auto-promote")).toBe("1");
    expect(twinsStub.getAttribute("data-has-promoted")).toBe("1");
    // Residual (op): ResearchContextPanel over deposit twin substrate.
    expect(screen.getByTestId("moil-deposit-context-mount")).toBeTruthy();
    expect(
      screen
        .getByTestId("moil-deposit-context-mount")
        .getAttribute("data-asset-id"),
    ).toBe("draft_moil_asset_dep_abc");
    expect(
      screen
        .getByTestId("moil-deposit-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("0");
    const ctxStub = screen.getByTestId("research-context-panel-stub");
    expect(ctxStub.getAttribute("data-asset-id")).toBe(
      "draft_moil_asset_dep_abc",
    );
    expect(ctxStub.getAttribute("data-spawn-id")).toBe("spn_1");
    expect(ctxStub.getAttribute("data-auto-load")).toBe("1");
    // Residual (amp): deposit ResearchContext inherits job research_tier.
    expect(
      screen
        .getByTestId("moil-deposit-context-mount")
        .getAttribute("data-research-tier"),
    ).toBe("deep");
    expect(
      screen
        .getByTestId("moil-deposit-context-mount")
        .getAttribute("data-seamless-moil-context"),
    ).toBe("true");
    expect(ctxStub.getAttribute("data-research-tier")).toBe("deep");
    // Residual (gl/js): progress panel for deposit spawn_ids + tier poll.
    expect(screen.getByTestId("moil-deposit-progress-mount")).toBeTruthy();
    expect(
      screen
        .getByTestId("moil-deposit-progress-mount")
        .getAttribute("data-spawn-count"),
    ).toBe("1");
    expect(
      screen
        .getByTestId("moil-deposit-progress-mount")
        .getAttribute("data-research-tier"),
    ).toBe("deep");
    expect(screen.getByTestId("moil-progress-spawn-spn_1").textContent).toMatch(
      /spawn=spn_1:auto=true/,
    );
    expect(
      screen.getByTestId("moil-progress-spawn-spn_1").getAttribute("data-poll-ms"),
    ).toBe("4000");
    expect(
      screen
        .getByTestId("research-progress-panel-stub")
        .getAttribute("data-research-tier"),
    ).toBe("deep");
    // Residual (on): collective multi-select on deposit + recent_ring push.
    await waitFor(() => {
      expect(pushRecentDeepResearchSpawnIdMock).toHaveBeenCalledWith("spn_1");
    });
    await waitFor(() => {
      expect(screen.getByTestId("moil-deposit-collective-mount")).toBeTruthy();
    });
    const collectiveMount = screen.getByTestId("moil-deposit-collective-mount");
    expect(collectiveMount.getAttribute("data-view-format")).toBe("html");
    expect(collectiveMount.getAttribute("data-asset-id")).toBe(
      "draft_moil_asset_dep_abc",
    );
    expect(collectiveMount.getAttribute("data-available-spawn-count")).toBe(
      "1",
    );
    expect(collectiveMount.getAttribute("data-deposit-spawn-count")).toBe("1");
    const collectiveStub = screen.getByTestId("collective-research-panel-stub");
    expect(collectiveStub.getAttribute("data-parent")).toBe(
      "draft_moil_asset_dep_abc",
    );
    expect(collectiveStub.getAttribute("data-spawns")).toBe("spn_1");
    expect(collectiveStub.getAttribute("data-preferred")).toBe("spn_1");
    expect(collectiveStub.getAttribute("data-has-clear")).toBe("1");
    expect(collectiveStub.getAttribute("data-has-merged")).toBe("1");
    // Residual (uf): openSpawnIds wired for Select open only (parity ue).
    expect(collectiveStub.getAttribute("data-has-open-spawn-ids")).toBe("1");
    expect(screen.getByTestId("moil-progress-summary").textContent).toMatch(
      /complete/,
    );
    expect(screen.getByTestId("deposit-html").innerHTML).toMatch(/Deposited HTML/);
    expect(
      screen.getByTestId("midnight-oil-mode").getAttribute("data-view-format"),
    ).toBe("html");
    // Residual (aor): multi-goal swarm intro + HTML-first mode stamps.
    const moilMode = screen.getByTestId("midnight-oil-mode");
    expect(moilMode.getAttribute("data-html-first")).toBe("true");
    expect(moilMode.getAttribute("data-multi-goal-swarm")).toBe("true");
    // Residual (aqn): soft budget · budget-before-fire · L4 deferred · never auto-route.
    expect(moilMode.getAttribute("data-soft-budget")).toBe("true");
    expect(moilMode.getAttribute("data-budget-before-fire")).toBe("true");
    expect(moilMode.getAttribute("data-l4-live-step")).toBe("deferred");
    expect(moilMode.getAttribute("data-never-auto-route")).toBe("true");
    expect(
      Number(moilMode.getAttribute("data-goal-templates")),
    ).toBeGreaterThanOrEqual(3);
    expect(screen.getByTestId("moil-mode-intro").textContent).toMatch(
      /multi-goal|templates|fan-out/i,
    );
    expect(screen.getByTestId("moil-mode-intro").textContent).toMatch(
      /budget|ceiling|L4/i,
    );
    const honesty = screen.getByTestId("moil-honesty-nav");
    expect(honesty.getAttribute("data-soft-budget")).toBe("true");
    expect(honesty.getAttribute("data-never-auto-route")).toBe("true");
    expect(
      screen.getByTestId("moil-prompt-cost-honesty-link").getAttribute("href"),
    ).toBe("/settings#prompt-cost-projection");
    expect(
      screen
        .getByTestId("moil-decision-tree-honesty-link")
        .getAttribute("href"),
    ).toBe("/settings#decision-tree-panel");
    expect(
      screen.getByTestId("moil-notdiamond-honesty-link").getAttribute("href"),
    ).toBe("/settings#notdiamond-advisory");
    expect(screen.getByTestId("moil-soft-budget-hint").textContent).toMatch(
      /soft budget/i,
    );

    // Residual (ex): auto-open floating hosted HTML after deposit.
    await waitFor(() => {
      expect(openWindow).toHaveBeenCalledWith(
        "hosted_html_document",
        expect.objectContaining({
          document_id: "draft_moil_asset_dep_abc",
          view_format: "html",
          source: "midnight_oil_deposit",
        }),
        expect.objectContaining({
          id: "win:moil-deposit:draft_moil_asset_dep_abc",
          mode: "floating",
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("moil-deposit-window-id").textContent).toMatch(
        /win:moil-deposit/,
      );
    });
    // Residual (ew/ata): full working-region open + HTML-first deposit open stamps.
    const openActions = screen.getByTestId("moil-deposit-open-actions");
    expect(openActions.getAttribute("data-deposit-html-ready")).toBe("true");
    expect(openActions.getAttribute("data-html-first")).toBe("true");
    expect(openActions.getAttribute("data-l4-live-step")).toBe("deferred");
    const openFull = screen.getByTestId("moil-open-deposit-full");
    expect(openFull.getAttribute("data-deposit-html-ready")).toBe("true");
    expect(openFull.getAttribute("data-html-first")).toBe("true");
    expect(openFull.getAttribute("data-window-mode")).toBe("full");
    expect(openFull.getAttribute("data-document-id")).toBe(
      "draft_moil_asset_dep_abc",
    );
    expect(openFull.getAttribute("title") || "").toMatch(/HTML reading window/i);
    expect((openFull as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(openFull);
    expect(openWindow).toHaveBeenCalledWith(
      "hosted_html_document",
      expect.objectContaining({
        document_id: "draft_moil_asset_dep_abc",
        view_format: "html",
      }),
      expect.objectContaining({
        id: "win:moil-deposit:draft_moil_asset_dep_abc:full",
        mode: "full",
      }),
    );
    // Residual (fo/pz/ack/aep/ata): Write dual handoff + seamless MO deposit path.
    const write = screen.getByTestId("moil-open-write");
    const href = write.getAttribute("href") || "";
    expect(href).toMatch(/html_draft=draft_moil_asset_dep_abc/);
    expect(href).toMatch(/twin_seed=antiek\.twin_write_seed\./);
    expect(write.getAttribute("data-view-format")).toBe("html");
    expect(write.getAttribute("data-html-first")).toBe("true");
    expect(write.getAttribute("data-deposit-html-ready")).toBe("true");
    expect(write.getAttribute("data-has-twin-seed")).toBe("1");
    expect(write.getAttribute("data-write-seed-has-body")).toBe("true");
    expect(write.getAttribute("data-document-id")).toBe(
      "draft_moil_asset_dep_abc",
    );
    expect(write.getAttribute("data-seamless-moil-write")).toBe("true");
    expect(write.getAttribute("data-seamless-host-write")).toBe("true");
    expect(write.getAttribute("data-job-id") || "").toBeTruthy();
  });

  it("runs offline worker after approve with auto-deposit", async () => {
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_run",
      goals: ["Goal A"],
      duration_minutes: 30,
      status: "awaiting_approval",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      recommended_price_ceiling_usd: 1.5,
      view_format: "html",
      runnable: false,
      html: "<p>Receipt</p>",
    });
    approveMidnightOilCeiling.mockResolvedValue({
      job_id: "moil_run",
      goals: ["Goal A"],
      duration_minutes: 30,
      status: "approved",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      recommended_price_ceiling_usd: 1.5,
      approved_ceiling_usd: 1.5,
      view_format: "html",
      runnable: true,
      html: "<p>Approved</p>",
    });
    runMidnightOilJob.mockResolvedValue({
      job_id: "moil_run",
      status: "complete",
      spent_usd: 0.05,
      approved_ceiling_usd: 1.5,
      spawn_ids: ["spn_moil_run_0"],
      goals_total: 1,
      steps_cap: 4,
      elapsed_ms: 0,
      view_format: "html",
      runnable: false,
      offline: true,
      live_step: false,
      notes_list: [
        "Offline worker simulation — no live multi-provider calls.",
        "Live env ANTIEK_MIDNIGHT_OIL_LIVE_STEP=off (default).",
      ],
      html: "<p>Offline run complete</p>",
      deposit: {
        job_id: "moil_run",
        asset_id: "moil_asset_run",
        document_id: "draft_x",
        twin_count: 2,
        spawn_ids: ["spn_moil_run_0"],
        draft_combined: true,
        usage_recorded: true,
        progress_seeded: true,
        progress: {
          latest_stage: "complete",
          event_count: 5,
          is_terminal: true,
          html: "<p>progress</p>",
        },
        job_status: "complete",
        view_format: "html",
        html: "<p>Deposited</p>",
      },
    });

    render(<MidnightOil />);
    fireEvent.change(screen.getByLabelText(/^Goals \(one per line\)$/i), {
      target: { value: "Goal A" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /create job \+ recommend ceiling/i }),
    );
    await waitFor(() => expect(screen.getByTestId("moil-job")).toBeTruthy());
    fireEvent.click(
      screen.getByRole("button", { name: /approve at recommended/i }),
    );
    await waitFor(() => {
      expect(screen.getByTestId("moil-run-offline")).toBeTruthy();
    });
    // Residual (ase): offline run CTA gated on runnable + approved/running.
    const runBtn = screen.getByTestId("moil-run-offline") as HTMLButtonElement;
    expect(runBtn.getAttribute("data-runnable")).toBe("true");
    expect(runBtn.getAttribute("data-run-ready")).toBe("true");
    expect(runBtn.getAttribute("data-l4-live-step")).toBe("deferred");
    expect(runBtn.getAttribute("data-offline-worker")).toBe("true");
    expect(runBtn.disabled).toBe(false);
    fireEvent.click(runBtn);
    await waitFor(() => {
      expect(runMidnightOilJob).toHaveBeenCalledWith({
        job_id: "moil_run",
        auto_deposit: true,
        spent_per_goal: 0.05,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("moil-run-result").textContent).toMatch(
        /complete/,
      );
    });
    // Residual (oq): offline run spawn_ids enter recent_ring for collective.
    await waitFor(() => {
      expect(pushRecentDeepResearchSpawnIdMock).toHaveBeenCalledWith(
        "spn_moil_run_0",
      );
    });
    expect(
      screen.getByTestId("moil-run-result").getAttribute("data-offline"),
    ).toBe("true");
    expect(
      screen.getByTestId("moil-run-result").getAttribute("data-live-step"),
    ).toBe("false");
    // Residual (hw/ot): machine-readable offline swarm run metrics + recent_ring.
    const metrics = screen.getByTestId("moil-run-metrics");
    expect(metrics.getAttribute("data-status")).toBe("complete");
    expect(metrics.getAttribute("data-offline")).toBe("true");
    expect(metrics.getAttribute("data-live-step")).toBe("false");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    await waitFor(() => {
      expect(metrics.getAttribute("data-recent-ring-has-run-spawns")).toBe(
        "true",
      );
    });
    expect(Number(metrics.getAttribute("data-recent-ring-count") || 0)).toBeGreaterThan(
      0,
    );
    expect(metrics.textContent).toMatch(/Midnight Oil run/);
    expect(metrics.textContent).toMatch(/recent_ring=/);
    expect(screen.getByTestId("moil-run-recent-ring-status").textContent).toMatch(
      /recent_ring/i,
    );
    expect(screen.getByTestId("moil-run-notes").textContent).toMatch(
      /Offline worker|LIVE_STEP/i,
    );
    expect(screen.getByTestId("moil-deposit-result").textContent).toMatch(
      /twins=2/,
    );
    // Residual (hx): machine-readable deposit land metrics.
    const depositMetrics = screen.getByTestId("moil-deposit-metrics");
    expect(depositMetrics.getAttribute("data-twin-count")).toBe("2");
    expect(depositMetrics.getAttribute("data-usage-recorded")).toBe("true");
    expect(depositMetrics.getAttribute("data-progress-seeded")).toBe("true");
    expect(depositMetrics.getAttribute("data-view-format")).toBe("html");
    expect(depositMetrics.textContent).toMatch(/Midnight Oil deposit/);
    // Residual (any): deposit land HTML-first honesty + competitive deep-links.
    const depositResult = screen.getByTestId("moil-deposit-result");
    expect(depositResult.getAttribute("data-html-first")).toBe("true");
    expect(depositResult.getAttribute("data-seamless-moil-deposit")).toBe(
      "true",
    );
    expect(depositResult.getAttribute("data-l4-live-step")).toBe("deferred");
    expect(depositMetrics.getAttribute("data-html-first")).toBe("true");
    expect(depositMetrics.getAttribute("data-seamless-moil-deposit")).toBe(
      "true",
    );
    expect(depositMetrics.getAttribute("data-deposit-html-present")).toBe(
      "true",
    );
    expect(depositMetrics.getAttribute("data-l4-live-step")).toBe("deferred");
    expect(depositMetrics.getAttribute("data-research-tier")).toMatch(
      /deep|fast|wrestle/,
    );
    expect(depositMetrics.textContent).toMatch(/HTML-first/i);
    expect(depositMetrics.textContent).toMatch(/L4 live deferred/i);
    const competitive = screen.getByTestId("moil-deposit-competitive-links");
    expect(competitive.getAttribute("data-l4-live-step")).toBe("deferred");
    expect(
      screen
        .getByTestId("moil-deposit-competitive-scorecard-link")
        .getAttribute("href"),
    ).toBe("/settings#settings-competitive-dr-scorecard");
    expect(
      screen
        .getByTestId("moil-deposit-competitive-dr-future-agent-link")
        .getAttribute("href") || "",
    ).toBe("/settings#settings-competitive-dr-scorecard");
    expect(
      screen
        .getByTestId("moil-deposit-dual-gate-l4-link")
        .getAttribute("href") || "",
    ).toBe("/settings#moil-live-step-status");
  });

  it("includes pub refs in budget projection promptText (pa)", () => {
    render(<MidnightOil />);
    fireEvent.change(screen.getByLabelText(/^Goals \(one per line\)$/i), {
      target: { value: "Goal alone" },
    });
    const before = Number(
      screen
        .getByTestId("research-launch-budget-panel-stub")
        .getAttribute("data-prompt-len") || 0,
    );
    fireEvent.change(screen.getByTestId("moil-pub-refs"), {
      target: { value: "arxiv:1706.03762" },
    });
    const mount = screen.getByTestId("moil-budget-mount");
    expect(mount.getAttribute("data-prompt-includes-pub-refs")).toBe("true");
    expect(Number(mount.getAttribute("data-pub-refs-chars") || 0)).toBeGreaterThan(
      0,
    );
    const after = Number(
      screen
        .getByTestId("research-launch-budget-panel-stub")
        .getAttribute("data-prompt-len") || 0,
    );
    expect(after).toBeGreaterThan(before);
    expect(after).toBeGreaterThan("Goal alone".length);
  });

  it("links dual-gate L1–L2 hydrate checklist beside pub refs (pb)", () => {
    render(<MidnightOil />);
    const link = screen.getByTestId("moil-pub-refs-dual-gate-link");
    // Residual (xy): L1 arxiv checklist section deep-link.
    expect(link.getAttribute("href")).toBe("/settings#hydrate-live-status");
    expect(link.textContent).toMatch(/L1 arxiv checklist/i);
    // Residual (aan): L2 Substack checklist (parity aal/aam).
    const l2 = screen.getByTestId("moil-pub-refs-dual-gate-l2-link");
    expect(l2.getAttribute("href")).toBe("/settings#hydrate-live-status");
    expect(l2.textContent).toMatch(/L2 Substack checklist/i);
    const offline = screen.getByTestId("moil-pub-refs-offline-default");
    expect(offline.getAttribute("data-offline-honest")).toBe("true");
    expect(offline.textContent).toMatch(/offline identity default/i);
  });

  it("inserts knowledge-dense pub quick-call presets into refs (anu)", () => {
    render(<MidnightOil />);
    const block = screen.getByTestId("moil-pub-refs-block");
    expect(block.getAttribute("data-seamless-pub-quick-call")).toBe("true");
    expect(block.getAttribute("data-offline-default")).toBe("true");
    expect(
      Number(block.getAttribute("data-knowledge-dense-presets") || 0),
    ).toBeGreaterThanOrEqual(4);
    const quick = screen.getByTestId("moil-publication-quick-call");
    expect(quick.getAttribute("data-seamless-pub-quick-call")).toBe("true");
    expect(quick.getAttribute("data-auto-hydrate")).toBe("false");
    expect(
      Number(quick.getAttribute("data-preset-count") || 0),
    ).toBeGreaterThanOrEqual(4);
    const attention = screen.getByTestId("moil-preset-attention-is-all-you-need");
    expect(attention.getAttribute("data-kind")).toBe("arxiv");
    expect(attention.getAttribute("data-reference")).toBe("arxiv:1706.03762");
    fireEvent.click(attention);
    expect(
      (screen.getByTestId("moil-pub-refs") as HTMLTextAreaElement).value,
    ).toBe("arxiv:1706.03762");
    // Idempotent: second click does not duplicate.
    fireEvent.click(attention);
    expect(
      (screen.getByTestId("moil-pub-refs") as HTMLTextAreaElement).value,
    ).toBe("arxiv:1706.03762");
    // Second preset appends on new line.
    fireEvent.click(screen.getByTestId("moil-preset-bert"));
    expect(
      (screen.getByTestId("moil-pub-refs") as HTMLTextAreaElement).value,
    ).toBe("arxiv:1706.03762\narxiv:1810.04805");
    // Budget foresight sees pub-ref impact after quick-call insert.
    expect(
      screen
        .getByTestId("moil-budget-mount")
        .getAttribute("data-prompt-includes-pub-refs"),
    ).toBe("true");
  });

  it("links Settings hydrate readiness beside pub refs (uw)", () => {
    render(<MidnightOil />);
    const settings = screen.getByTestId("moil-pub-refs-hydrate-settings-link");
    expect(settings.getAttribute("href")).toBe("/settings#hydrate-live-status");
    expect(settings.textContent).toMatch(/hydrate readiness/i);
  });

  it("hydrates pub refs and appends grounded goals on create (oy)", async () => {
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_pubs",
      goals: [
        "Wrestle with attention",
        "Ground publication: arxiv:1706.03762",
      ],
      duration_minutes: 30,
      status: "awaiting_approval",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      recommended_price_ceiling_usd: 2.0,
      view_format: "html",
      runnable: false,
      html: "<p>Receipt</p>",
    });
    render(<MidnightOil />);
    fireEvent.change(screen.getByLabelText(/^Goals \(one per line\)$/i), {
      target: { value: "Wrestle with attention" },
    });
    fireEvent.change(screen.getByTestId("moil-pub-refs"), {
      target: { value: "arxiv:1706.03762" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /create job \+ recommend ceiling/i }),
    );
    await waitFor(() => {
      expect(hydratePublicationRefsMock).toHaveBeenCalledWith([
        "arxiv:1706.03762",
      ]);
    });
    await waitFor(() => {
      expect(createMidnightOilJob).toHaveBeenCalledWith(
        expect.objectContaining({
          goals: expect.arrayContaining([
            "Wrestle with attention",
            "Ground publication: arxiv:1706.03762",
          ]),
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("moil-pub-refs-status").textContent).toMatch(
        /Hydrated 1/,
      );
    });
    expect(screen.getByTestId("moil-pub-refs-status").textContent).toMatch(
      /HTML-first/,
    );
    // Residual (pc): job receipt grounded pub goals chrome.
    await waitFor(() => {
      expect(screen.getByTestId("moil-job")).toBeTruthy();
    });
    expect(
      screen
        .getByTestId("moil-ceiling-metrics")
        .getAttribute("data-grounded-pub-goal-count"),
    ).toBe("1");
    expect(screen.getByTestId("moil-grounded-pub-goals").getAttribute("data-count")).toBe(
      "1",
    );
    expect(screen.getByTestId("moil-grounded-pub-goals").textContent).toMatch(
      /Ground publication: arxiv:1706.03762/,
    );
  });

  it("pushes offline run spawn_ids to recent_ring without auto-deposit (oq)", async () => {
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_run_no_dep",
      goals: ["Goal alone"],
      duration_minutes: 30,
      status: "awaiting_approval",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      recommended_price_ceiling_usd: 1.0,
      view_format: "html",
      runnable: false,
      html: "<p>Receipt</p>",
    });
    approveMidnightOilCeiling.mockResolvedValue({
      job_id: "moil_run_no_dep",
      goals: ["Goal alone"],
      duration_minutes: 30,
      status: "approved",
      acceptance_policy_version: 1,
      acceptance_policy: V1_POLICY,
      recommended_price_ceiling_usd: 1.0,
      approved_ceiling_usd: 1.0,
      view_format: "html",
      runnable: true,
      html: "<p>Approved</p>",
    });
    runMidnightOilJob.mockResolvedValue({
      job_id: "moil_run_no_dep",
      status: "complete",
      spent_usd: 0.05,
      approved_ceiling_usd: 1.0,
      spawn_ids: ["spn_run_only"],
      goals_total: 1,
      steps_cap: 4,
      elapsed_ms: 0,
      view_format: "html",
      runnable: false,
      offline: true,
      live_step: false,
      notes_list: ["Offline without auto-deposit."],
      html: "<p>Offline run only</p>",
      deposit: null,
    });

    render(<MidnightOil />);
    fireEvent.change(screen.getByLabelText(/^Goals \(one per line\)$/i), {
      target: { value: "Goal alone" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /create job \+ recommend ceiling/i }),
    );
    await waitFor(() => expect(screen.getByTestId("moil-job")).toBeTruthy());
    fireEvent.click(
      screen.getByRole("button", { name: /approve at recommended/i }),
    );
    await waitFor(() => {
      expect(screen.getByTestId("moil-run-offline")).toBeTruthy();
    });
    // Turn off auto-deposit before run (testid is the checkbox input).
    const autoDep = screen.getByTestId("moil-auto-deposit") as HTMLInputElement;
    expect(autoDep.checked).toBe(true);
    fireEvent.click(autoDep);
    expect(autoDep.checked).toBe(false);
    fireEvent.click(screen.getByTestId("moil-run-offline"));
    await waitFor(() => {
      expect(runMidnightOilJob).toHaveBeenCalledWith({
        job_id: "moil_run_no_dep",
        auto_deposit: false,
        spent_per_goal: 0.05,
      });
    });
    await waitFor(() => {
      expect(pushRecentDeepResearchSpawnIdMock).toHaveBeenCalledWith(
        "spn_run_only",
      );
    });
    expect(screen.queryByTestId("moil-deposit-result")).toBeNull();
  });

  it("applies competitive recommended duration by tier (ng)", async () => {
    render(<MidnightOil />);
    await waitFor(() => {
      expect(screen.getByTestId("moil-duration-recommend")).toBeTruthy();
    });
    // Default deep → recommend 10m.
    expect(
      screen
        .getByTestId("moil-duration-recommend")
        .getAttribute("data-recommended-minutes"),
    ).toBe("10");
    expect(
      screen
        .getByTestId("moil-duration-recommend")
        .getAttribute("data-band-minutes"),
    ).toBe("3–10");
    // Residual (aue): competitiveDurationBand pure helper stamps on MO duration.
    const rec = screen.getByTestId("moil-duration-recommend");
    expect(rec.getAttribute("data-competitive-duration-band")).toBe("true");
    expect(rec.getAttribute("data-band-label")).toMatch(/deep synthesize/i);
    expect(Number(rec.getAttribute("data-poll-ms") || 0)).toBeGreaterThan(0);
    // Default duration is 60; apply recommended.
    expect(
      (screen.getByTestId("moil-duration-minutes") as HTMLInputElement).value,
    ).toBe("60");
    fireEvent.click(screen.getByTestId("moil-apply-recommended-duration"));
    expect(
      (screen.getByTestId("moil-duration-minutes") as HTMLInputElement).value,
    ).toBe("10");
    expect(
      screen
        .getByTestId("moil-duration-recommend")
        .getAttribute("data-matches-recommended"),
    ).toBe("true");
    // Wrestle chip → 30m.
    fireEvent.click(screen.getByTestId("moil-duration-chip-wrestle"));
    expect(
      (screen.getByTestId("moil-duration-minutes") as HTMLInputElement).value,
    ).toBe("30");
    // Fast chip → 3m.
    fireEvent.click(screen.getByTestId("moil-duration-chip-fast"));
    expect(
      (screen.getByTestId("moil-duration-minutes") as HTMLInputElement).value,
    ).toBe("3");
  });

  it("soft-applies recommended duration on Settings depth prefill (nr)", async () => {
    fetchDepthTiers.mockResolvedValueOnce({
      active_depth_tier: "wrestle",
      active_preset: null,
      presets: [],
      projection_hints: null,
      view_format: "html",
      settings_panel: "depth_tier_presets",
      source: "test",
      notes: [],
    });
    render(<MidnightOil />);
    // Factory default 60 → wrestle recommended 30 after prefill.
    await waitFor(() => {
      expect(
        (screen.getByTestId("moil-duration-minutes") as HTMLInputElement).value,
      ).toBe("30");
    });
    expect(
      screen
        .getByTestId("moil-duration-recommend")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
    expect(
      screen
        .getByTestId("moil-duration-recommend")
        .getAttribute("data-matches-recommended"),
    ).toBe("true");
  });

  it("soft-syncs duration when research tier changes at recommended (nh)", async () => {
    render(<MidnightOil />);
    await waitFor(() => {
      expect(screen.getByTestId("moil-duration-minutes")).toBeTruthy();
      expect(screen.getByTestId("research-launch-tier-wrestle")).toBeTruthy();
    });
    // Start at recommended deep (10m).
    fireEvent.click(screen.getByTestId("moil-apply-recommended-duration"));
    expect(
      (screen.getByTestId("moil-duration-minutes") as HTMLInputElement).value,
    ).toBe("10");
    // Tier → wrestle while duration matches deep recommended → soft-sync to 30.
    fireEvent.click(screen.getByTestId("research-launch-tier-wrestle"));
    await waitFor(() => {
      expect(
        (screen.getByTestId("moil-duration-minutes") as HTMLInputElement).value,
      ).toBe("30");
    });
    // Custom override: set 45, then tier change should NOT overwrite.
    fireEvent.change(screen.getByTestId("moil-duration-minutes"), {
      target: { value: "45" },
    });
    expect(
      (screen.getByTestId("moil-duration-minutes") as HTMLInputElement).value,
    ).toBe("45");
    // Stub only has wrestle button; re-click wrestle (same tier) — still 45.
    fireEvent.click(screen.getByTestId("research-launch-tier-wrestle"));
    expect(
      (screen.getByTestId("moil-duration-minutes") as HTMLInputElement).value,
    ).toBe("45");
  });
});
