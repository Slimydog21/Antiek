import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MidnightOil from "./index";

const {
  createMidnightOilJob,
  approveMidnightOilCeiling,
  depositMidnightOilJob,
  runMidnightOilJob,
  getMidnightOilJob,
  fetchMidnightOilLiveStepStatus,
  fetchDecisionTreeSelection,
  seedTwinNotes,
  hydratePublicationRefsMock,
  parsePublicationRefsMock,
  collectDeepResearchSpawnIdsMock,
  listRecentDeepResearchSpawnIdsMock,
  pushRecentDeepResearchSpawnIdMock,
} = vi.hoisted(() => ({
  createMidnightOilJob: vi.fn(),
  approveMidnightOilCeiling: vi.fn(),
  depositMidnightOilJob: vi.fn(),
  runMidnightOilJob: vi.fn(),
  getMidnightOilJob: vi.fn(),
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
  fetchDecisionTreeSelection: vi.fn(),
  seedTwinNotes: vi.fn(),
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

vi.mock("../../api/midnightOil", () => ({
  createMidnightOilJob,
  approveMidnightOilCeiling,
  depositMidnightOilJob,
  runMidnightOilJob,
  getMidnightOilJob,
  fetchMidnightOilLiveStepStatus,
}));

vi.mock("../../api/engagement", () => ({
  seedTwinNotes: (...args: unknown[]) => seedTwinNotes(...args),
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
  fetchDecisionTreeSelection: (...args: unknown[]) =>
    fetchDecisionTreeSelection(...args),
  fetchDepthTiers: (...args: unknown[]) => fetchDepthTiers(...args),
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
  }) => (
    <div
      data-testid="research-context-panel-stub"
      data-asset-id={props.assetId}
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
    collectDeepResearchSpawnIdsMock(...args),
}));

vi.mock("../../workspace/recentDeepResearchSpawns", () => ({
  listRecentDeepResearchSpawnIds: (...args: unknown[]) =>
    listRecentDeepResearchSpawnIdsMock(...args),
  pushRecentDeepResearchSpawnId: (...args: unknown[]) =>
    pushRecentDeepResearchSpawnIdMock(...(args as [string])),
}));

const openWindow = vi.fn(() => "win:moil-deposit:draft_moil_asset_dep_abc");
vi.mock("../../components/windows/openWindow", () => ({
  openWindow: (...args: unknown[]) => openWindow(...args),
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

  it("links dual-gate L1–L4 checklist for live-step prep (ml)", () => {
    render(<MidnightOil />);
    const dual = screen.getByTestId("moil-dual-gate-checklist-link");
    expect(dual.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4/);
    expect(dual.textContent).toMatch(/dual-gate/i);
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
    fireEvent.click(
      screen.getByRole("button", { name: /create job \+ recommend ceiling/i }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("recommended-ceiling").textContent).toContain(
        "3.60",
      );
    });
    // Residual (hn): recommended ceiling metrics + formula transparency.
    const metrics = screen.getByTestId("moil-ceiling-metrics");
    expect(metrics.getAttribute("data-job-id")).toBe("moil_test");
    expect(metrics.getAttribute("data-status")).toBe("awaiting_approval");
    expect(metrics.getAttribute("data-duration-minutes")).toBe("60");
    expect(metrics.getAttribute("data-goal-count")).toBe("1");
    expect(metrics.getAttribute("data-recommended-usd")).toBe("3.6");
    expect(metrics.getAttribute("data-research-tier")).toBe("deep");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.textContent).toMatch(/Ceiling audit/);
    expect(
      screen.getByTestId("moil-ceiling-formula-note").textContent,
    ).toMatch(/1\.25 safety/);
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

    fireEvent.click(
      screen.getByRole("button", { name: /approve at recommended/i }),
    );
    await waitFor(() => {
      expect(screen.getByTestId("approved-ceiling").textContent).toContain(
        "3.60",
      );
    });
    expect(approveMidnightOilCeiling).toHaveBeenCalledWith({
      job_id: "moil_test",
      use_recommended: true,
    });
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
    fireEvent.click(screen.getByTestId("moil-approve-recommended"));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(
        /may exceed remaining daily budget/i,
      );
    });
    expect(approveMidnightOilCeiling).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("moil-force-ceiling-over-budget").querySelector("input")!);
    fireEvent.click(screen.getByTestId("moil-approve-recommended"));
    await waitFor(() => {
      expect(approveMidnightOilCeiling).toHaveBeenCalledWith({
        job_id: "moil_over",
        use_recommended: true,
      });
    });
  });

  it("deposits results and shows progress after approve", async () => {
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_dep",
      goals: ["Wrestle with twin notes"],
      duration_minutes: 30,
      status: "awaiting_approval",
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
      recommended_price_ceiling_usd: 2.0,
      approved_ceiling_usd: 2.0,
      view_format: "html",
      runnable: true,
      html: "<p>Approved</p>",
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
    await waitFor(() => {
      expect(screen.getByTestId("moil-deposit")).toBeTruthy();
    });
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
    // Residual (gk): client offline twin reseed after deposit.
    await waitFor(() => {
      expect(seedTwinNotes).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "draft_moil_asset_dep_abc",
          force_offline: true,
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
    // Residual (ew): full working-region open remains available.
    fireEvent.click(screen.getByTestId("moil-open-deposit-full"));
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
    // Residual (fo/pz): Write dual handoff html_draft + twin_seed for empty twin seed.
    const write = screen.getByTestId("moil-open-write");
    const href = write.getAttribute("href") || "";
    expect(href).toMatch(/html_draft=draft_moil_asset_dep_abc/);
    expect(href).toMatch(/twin_seed=antiek\.twin_write_seed\./);
    expect(write.getAttribute("data-view-format")).toBe("html");
    expect(write.getAttribute("data-has-twin-seed")).toBe("1");
  });

  it("runs offline worker after approve with auto-deposit", async () => {
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_run",
      goals: ["Goal A"],
      duration_minutes: 30,
      status: "awaiting_approval",
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
    fireEvent.click(screen.getByTestId("moil-run-offline"));
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
    expect(link.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4/);
    expect(link.textContent).toMatch(/L1–L2 hydrate/i);
    const offline = screen.getByTestId("moil-pub-refs-offline-default");
    expect(offline.getAttribute("data-offline-honest")).toBe("true");
    expect(offline.textContent).toMatch(/offline identity default/i);
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
