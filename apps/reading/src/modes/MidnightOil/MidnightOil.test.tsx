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
  DecisionTreeDriverBadge: () => (
    <div data-testid="decision-tree-driver-badge-stub">driver badge</div>
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
    expect(link.getAttribute("href")).toBe("/settings");
    expect(link.textContent).toMatch(/model driver & budget/i);
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
    fireEvent.change(screen.getByLabelText(/goals/i), {
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
    fireEvent.change(screen.getByLabelText(/goals/i), {
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
    fireEvent.change(screen.getByLabelText(/goals/i), {
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
    // Residual (fo): Write handoff for deposit document.
    const write = screen.getByTestId("moil-open-write");
    expect(write.getAttribute("href")).toBe(
      "/write?html_draft=draft_moil_asset_dep_abc",
    );
    expect(write.getAttribute("data-view-format")).toBe("html");
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
    fireEvent.change(screen.getByLabelText(/goals/i), {
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
    expect(
      screen.getByTestId("moil-run-result").getAttribute("data-offline"),
    ).toBe("true");
    expect(
      screen.getByTestId("moil-run-result").getAttribute("data-live-step"),
    ).toBe("false");
    // Residual (hw): machine-readable offline swarm run metrics.
    const metrics = screen.getByTestId("moil-run-metrics");
    expect(metrics.getAttribute("data-status")).toBe("complete");
    expect(metrics.getAttribute("data-offline")).toBe("true");
    expect(metrics.getAttribute("data-live-step")).toBe("false");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.textContent).toMatch(/Midnight Oil run/);
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
});
