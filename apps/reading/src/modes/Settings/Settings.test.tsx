import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Settings from "./index";

vi.mock("../../workspace/useViewportTier", () => ({
  useViewportTier: () => "desktop",
}));

const {
  installDecisionTreeSelection,
  clearDecisionTreeSelection,
  fetchDecisionTreeSelection,
  estimatePromptCost,
  fetchSettingsModels,
  fetchSettingsBudget,
  fetchAntiekBenchUsageSummary,
  fetchAntiekBenchSuiteProposal,
  approveAntiekBenchSuiteProposal,
  fetchDepthTiers,
  applyDepthTier,
  fetchAntiekBenchDogfoodFixtures,
  fetchAntiekBenchLeaderboard,
  runAntiekBenchOffline,
  fetchRegisteredModels,
  registerSettingsModel,
  fetchNotDiamondAdvisory,
  fetchHydrateLiveStatus,
  fetchTwinSeedLiveStatus,
  defaultUsageSummary,
} = vi.hoisted(() => {
  const models = {
    models: [
      {
        provider_id: "zai",
        ready: true,
        tier_bindings: ["flash", "pro"],
        primary_model: "glm-5.2",
        notes: null,
      },
    ],
    count: 1,
    providers_ready: true,
    source: "test",
  };
  const defaultUsageSummary = {
    event_count: 2,
    by_task_class: {
      wrestle: { worked: 1, failed: 0, total: 1 },
      book_qa: { worked: 0, failed: 1, total: 1 },
    },
    by_source: {
      investigation_start: 1,
      session_flywheel: 1,
      twin_chase: 3,
      floating_deep_research: 1,
      midnight_oil: 1,
      collective_merge: 1,
    },
    known_sources: [
      "investigation_start",
      "session_flywheel",
      "midnight_oil",
      "midnight_oil_deposit",
      "marketplace_host",
      "floating_deep_research",
      "twin_chase",
      "collective_merge",
      "collective_doc_merge",
      "spawn_merge",
      "hosted_html_document",
      "deep_research_session",
      "research_progress_complete",
      "research_progress_draft",
      "evidence_pack",
      "publication_hydrate",
      "session_flywheel_complete",
      "context_search",
      "research_context_pack",
      "twin_promote_context",
      "antiek_bench.offline_dogfood",
      "engagement",
    ],
    // Residual (ry): substrate Write-seed aggregates (SSOT).
    write_seed_by_source: {} as Record<string, number>,
    write_seed_source_count: 0,
    write_seed_event_count: 0,
    write_seed_known_count: 14,
    view_format: "html" as const,
    settings_panel: "antiek_bench_usage_weekly",
    source: "antiek_bench.usage_events",
    notes: [] as string[],
    html: "<p>Events recorded: 2 · By source: investigation_start=1 · Known feed sources: twin_chase</p>",
  };
  const budget = {
    daily_cap_usd: 5,
    spent_usd: 1,
    remaining_usd: 4,
    spent_status: "known" as const,
    cap_env: null,
    notes: ["test note"],
  };
  return {
    installDecisionTreeSelection: vi.fn(async () => ({
      model_id: "glm-5.2",
      provider_id: "zai",
      installed: true,
      notes: ["installed into process-local decision-tree registry"],
      source: "test",
    })),
    clearDecisionTreeSelection: vi.fn(async () => ({
      model_id: null,
      provider_id: null,
      installed: false,
      notes: ["decision-tree selection cleared"],
      source: "test",
    })),
    fetchDecisionTreeSelection: vi.fn(async () => ({
      model_id: null,
      provider_id: null,
      installed: false,
      notes: ["no decision-tree selection installed in this process"],
      source: "test",
    })),
    estimatePromptCost: vi.fn(async () => ({
      estimated_usd_low: null,
      estimated_usd_high: null,
      would_exceed_budget: null,
      pricing_known: false,
      notes: ["tier pricing is 0.0 placeholder"],
      assumed_input_tokens: 500,
      assumed_output_tokens: 500,
      tier: "pro",
      provider: "zai",
      model: "glm-5.2",
    })),
    fetchSettingsModels: vi.fn(async () => models),
    fetchSettingsBudget: vi.fn(async () => budget),
    fetchAntiekBenchUsageSummary: vi.fn(async () => defaultUsageSummary),
    defaultUsageSummary,
    fetchAntiekBenchSuiteProposal: vi.fn(async () => ({
      has_proposal: true,
      proposal_id: "prop_testdeadbeef01",
      status: "proposed",
      base_suite_version: "core-v1",
      proposed_suite_version: "core-v1+usage-abcd1234",
      active_suite_version: "core-v1",
      active_suite_unchanged: true,
      auto_promoted: false,
      rationale: "Ingested 2 usage events; added 1 items from failed outcomes",
      added_item_ids: ["usage-distill-abcd12-0"],
      event_count: 2,
      view_format: "html",
      settings_panel: "antiek_bench_suite_proposal",
      source: "antiek_bench.propose_from_recorded_usage",
      notes: ["Proposal status is proposed only"],
      html: "<p>Status: proposal only · proposed</p>",
    })),
    approveAntiekBenchSuiteProposal: vi.fn(async (opts: {
      proposal_id: string;
      approve: boolean;
    }) => ({
      ok: true,
      proposal_id: opts.proposal_id,
      status: opts.approve ? "approved" : "rejected",
      approved: opts.approve,
      promoted: opts.approve,
      active_suite_version: opts.approve
        ? "core-v1+usage-abcd1234"
        : "core-v1",
      active_suite_before: "core-v1",
      proposed_suite_version: "core-v1+usage-abcd1234",
      view_format: "html",
      settings_panel: "antiek_bench_suite_approve",
      source: "antiek_bench.approve_and_promote",
      notes: [
        opts.approve
          ? "Approved and promoted suite core-v1+usage-abcd1234"
          : "Rejected proposal",
      ],
      html: null,
    })),
    fetchDepthTiers: vi.fn(async () => ({
      active_depth_tier: null,
      active_preset: null,
      presets: [
        {
          depth_tier: "flash",
          label: "Flash",
          description: "fast",
          dispatch_tier: "flash",
          task_class: "distill",
          default_input_chars: 1500,
          default_expected_output_tokens: 400,
          competitor_posture: "Perplexity-class speed",
        },
        {
          depth_tier: "pro",
          label: "Pro",
          description: "balanced",
          dispatch_tier: "pro",
          task_class: "synthesize",
          default_input_chars: 4000,
          default_expected_output_tokens: 1200,
          competitor_posture: "balanced",
        },
        {
          depth_tier: "wrestle",
          label: "Wrestle",
          description: "deep",
          dispatch_tier: "pro",
          task_class: "wrestle",
          default_input_chars: 8000,
          default_expected_output_tokens: 4000,
          competitor_posture: "depth",
        },
      ],
      projection_hints: null,
      view_format: "html",
      settings_panel: "depth_tier_presets",
      source: "substrate.model_registration.depth_tiers",
      notes: [],
      html: "<p>Depth-tier presets</p>",
    })),
    applyDepthTier: vi.fn(async (opts: { depth_tier: string }) => ({
      active_depth_tier: opts.depth_tier,
      active_preset: {
        depth_tier: opts.depth_tier,
        label: opts.depth_tier,
        description: "",
        dispatch_tier: opts.depth_tier === "flash" ? "flash" : "pro",
        task_class:
          opts.depth_tier === "flash"
            ? "distill"
            : opts.depth_tier === "wrestle"
              ? "wrestle"
              : "synthesize",
        default_input_chars: 1500,
        default_expected_output_tokens:
          opts.depth_tier === "wrestle" ? 4000 : 400,
        competitor_posture: "test",
      },
      presets: [],
      projection_hints: {
        tier: opts.depth_tier === "flash" ? "flash" : "pro",
        input_chars: 1500,
        expected_output_tokens: opts.depth_tier === "wrestle" ? 4000 : 400,
        task_class:
          opts.depth_tier === "flash"
            ? "distill"
            : opts.depth_tier === "wrestle"
              ? "wrestle"
              : "synthesize",
      },
      view_format: "html",
      settings_panel: "depth_tier_presets",
      source: "substrate.model_registration.depth_tiers",
      notes: [`Active depth tier set to ${opts.depth_tier}`],
      html: `<p>Active: ${opts.depth_tier}</p>`,
    })),
    fetchAntiekBenchDogfoodFixtures: vi.fn(async () => ({
      suite_version: "suite-competitive-dogfood-v1",
      label: "antiek-bench-competitive-dogfood",
      item_count: 5,
      by_task_class: {
        distill: 1,
        synthesize: 1,
        wrestle: 2,
        book_qa: 1,
      },
      items: [
        {
          item_id: "dogfood-distill-attention",
          task_class: "distill",
          prompt: "Distill attention claim",
        },
      ],
      auto_promoted: false,
      view_format: "html",
      settings_panel: "antiek_bench_dogfood_fixtures",
      source: "antiek_bench.dogfood_fixtures",
      notes: ["Competitive dogfood fixtures are offline prompts only."],
      html: "<p>Suite suite-competitive-dogfood-v1 · items=5</p>",
    })),
    fetchAntiekBenchLeaderboard: vi.fn(async () => ({
      week_id: "2026-W28",
      models: [
        { model_id: "strong-model", mean_score: 0.95 },
        { model_id: "weak-model", mean_score: 0.2 },
      ],
      task_classes: ["distill", "synthesize"],
      run_count: 2,
      suite_versions: ["suite-v1"],
      recommended_model_id: "strong-model",
      recommended_mean_score: 0.95,
      view_format: "html",
      settings_panel: "antiek_bench_weekly",
      source: "antiek_bench.offline_runs",
      notes: [],
      html: "<p>Leaderboard week 2026-W28 · strong-model</p>",
    })),
    runAntiekBenchOffline: vi.fn(async () => ({
      week_id: "2026-W28",
      suite_version: "suite-competitive-dogfood-v1",
      suite_label: "antiek-bench-competitive-dogfood",
      run_count: 3,
      runs: [
        { run_id: "brun_1", model_id: "stub-strong", mean_score: 0.9 },
        { run_id: "brun_2", model_id: "stub-mid", mean_score: 0.5 },
        { run_id: "brun_3", model_id: "stub-weak", mean_score: 0.2 },
      ],
      models_run: ["stub-strong", "stub-mid", "stub-weak"],
      recommended_model_id: "stub-strong",
      recommended_mean_score: 0.9,
      leaderboard: {
        week_id: "2026-W28",
        models: [{ model_id: "stub-strong", mean_score: 0.9 }],
        task_classes: ["distill"],
        run_count: 3,
        suite_versions: ["suite-competitive-dogfood-v1"],
        recommended_model_id: "stub-strong",
        recommended_mean_score: 0.9,
        view_format: "html",
        settings_panel: "antiek_bench_weekly",
        source: "antiek_bench.offline_runs",
        notes: [],
        html: "<p>Leaderboard after offline run</p>",
      },
      view_format: "html",
      offline: true,
      auto_promoted: false,
      usage_events_recorded: 15,
      settings_panel: "antiek_bench_run_offline",
      source: "antiek_bench.product_path.run_offline_dogfood",
      notes: ["Offline dogfood suite run — keyword stub providers only."],
      html: "<p>Antiek-bench offline dogfood week 2026-W28</p>",
    })),
    fetchRegisteredModels: vi.fn(async () => ({
      models: [],
      count: 0,
      active_model_id: null,
      view_format: "html",
      settings_panel: "add_model",
      source: "substrate.model_registration.install",
      notes: ["No process-local model registry yet"],
    })),
    registerSettingsModel: vi.fn(async (opts: {
      model_id: string;
      provider_id: string;
      select?: boolean;
    }) => ({
      models: [
        {
          model_id: opts.model_id,
          provider_id: opts.provider_id,
          display_name: opts.model_id,
          enabled: true,
          selected: Boolean(opts.select),
        },
      ],
      count: 1,
      active_model_id: opts.select ? opts.model_id : null,
      view_format: "html",
      settings_panel: "add_model",
      source: "substrate.model_registration.install",
      notes: [`Registered model ${opts.model_id}`],
      model_id: opts.model_id,
      provider_id: opts.provider_id,
      selected: Boolean(opts.select),
      registered_count: 1,
    })),
    fetchNotDiamondAdvisory: vi.fn(async () => ({
      advisory_allowed: true,
      advisory_verdict: "GO",
      authority_allowed: false,
      authority_rejected: true,
      authority_verdict: "REJECT",
      dispatch_owner: "hermes_primary_plus_decision_tree",
      notdiamond_is_dispatch_authority: false,
      kill_switch_env: "ANTIEK_NOTDIAMOND",
      kill_switch_enabled: false,
      default_off: true,
      suggested_model_id: "stub-strong",
      suggested_provider_id: "offline-stub",
      suggestion_source: "notdiamond_advisory.offline_fallback",
      installable: true,
      view_format: "html",
      settings_panel: "notdiamond_advisory",
      source: "docs/htmlspec/notdiamond-verdict/VERDICT.md",
      verdict_date: "2026-07-09",
      notes: ["Authority REJECT under §16"],
      html: "<p>Authority REJECT — not the dispatch authority · Suggested model (advisory): stub-strong</p>",
    })),
    // Residual (hq): offline-honest hydrate status default.
    fetchHydrateLiveStatus: vi.fn(async () => ({
      view_format: "html",
      product_panel: "hydrate_live_status",
      source: "engagement_spine.hydrate_live_wiring",
      offline_honest: true,
      any_live_injector: false,
      arxiv: {
        env_flag: "ANTIEK_HYDRATE_LIVE_ARXIV",
        env_enabled: false,
        injector_installed: false,
      },
      substack: {
        env_flag: "ANTIEK_HYDRATE_LIVE_SUBSTACK",
        env_enabled: false,
        injector_installed: false,
      },
      generic_fetch_publication_installed: false,
      notes: [
        "Hydrate default: offline-honest identity — no live body injectors installed.",
      ],
      html: "<p>offline_honest=true</p>",
    })),
    // Residual (hs): offline-honest twin seed status default.
    fetchTwinSeedLiveStatus: vi.fn(async () => ({
      view_format: "html",
      product_panel: "twin_seed_live_status",
      source: "engagement_spine.twin_seed_live_wiring",
      offline_honest: true,
      live_env: false,
      use_dispatch: false,
      injector_installed: false,
      live_env_flag: "ANTIEK_TWIN_SEED_LIVE",
      use_dispatch_env_flag: "ANTIEK_TWIN_SEED_USE_DISPATCH",
      notes: [
        "Twin seed default: offline-honest identity stubs (UI panels force_offline=true).",
      ],
      html: "<p>offline_honest=true</p>",
    })),
  };
});

vi.mock("../../api/settings", () => ({
  fetchSettingsModels,
  fetchSettingsBudget,
  estimatePromptCost,
  fetchDecisionTreeSelection,
  installDecisionTreeSelection,
  clearDecisionTreeSelection,
  fetchAntiekBenchUsageSummary,
  fetchAntiekBenchSuiteProposal,
  approveAntiekBenchSuiteProposal,
  fetchDepthTiers,
  applyDepthTier,
  fetchAntiekBenchDogfoodFixtures,
  fetchAntiekBenchLeaderboard,
  runAntiekBenchOffline,
  fetchRegisteredModels,
  registerSettingsModel,
  fetchNotDiamondAdvisory,
}));

vi.mock("../../api/engagement", () => ({
  fetchHydrateLiveStatus,
  fetchTwinSeedLiveStatus,
}));

describe("Settings SPR-01 + decision-tree install", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    installDecisionTreeSelection.mockClear();
    clearDecisionTreeSelection.mockClear();
    fetchDecisionTreeSelection.mockClear();
    estimatePromptCost.mockClear();
    fetchSettingsModels.mockClear();
    fetchSettingsBudget.mockClear();
    fetchAntiekBenchUsageSummary.mockClear();
    // Residual (rt): restore default primary twin_chase after write-seed override tests.
    fetchAntiekBenchUsageSummary.mockResolvedValue(defaultUsageSummary);
    fetchAntiekBenchSuiteProposal.mockClear();
    approveAntiekBenchSuiteProposal.mockClear();
    fetchDepthTiers.mockClear();
    applyDepthTier.mockClear();
    fetchAntiekBenchDogfoodFixtures.mockClear();
    fetchAntiekBenchLeaderboard.mockClear();
    runAntiekBenchOffline.mockClear();
    fetchRegisteredModels.mockClear();
    registerSettingsModel.mockClear();
    fetchNotDiamondAdvisory.mockClear();
    fetchHydrateLiveStatus.mockClear();
    fetchTwinSeedLiveStatus.mockClear();
    // Default: no installed decision-tree driver (residual rl delta baseline).
    fetchDecisionTreeSelection.mockResolvedValue({
      model_id: null,
      provider_id: null,
      installed: false,
      notes: ["no decision-tree selection installed in this process"],
      source: "test",
    });
  });

  it("surfaces offline-honest twin seed live status (hs)", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(fetchTwinSeedLiveStatus).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByTestId("twin-seed-live-status-panel")).toBeTruthy();
    });
    const panel = screen.getByTestId("twin-seed-live-status-panel");
    expect(panel.getAttribute("data-offline-honest")).toBe("true");
    expect(panel.getAttribute("data-injector-installed")).toBe("false");
    const metrics = screen.getByTestId("twin-seed-live-status-metrics");
    expect(metrics.getAttribute("data-offline-honest")).toBe("true");
    expect(metrics.textContent).toMatch(/offline-honest identity stubs/);
  });

  it("surfaces offline-honest hydrate live status (hq)", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(fetchHydrateLiveStatus).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByTestId("hydrate-live-status-panel")).toBeTruthy();
    });
    const panel = screen.getByTestId("hydrate-live-status-panel");
    expect(panel.getAttribute("data-offline-honest")).toBe("true");
    expect(panel.getAttribute("data-any-live-injector")).toBe("false");
    const metrics = screen.getByTestId("hydrate-live-status-metrics");
    expect(metrics.getAttribute("data-offline-honest")).toBe("true");
    expect(metrics.getAttribute("data-arxiv-injector")).toBe("false");
    expect(metrics.getAttribute("data-substack-injector")).toBe("false");
    expect(metrics.textContent).toMatch(/offline-honest identity/);
  });

  it("renders registered providers and budget bar", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getAllByText(/zai/).length).toBeGreaterThan(0);
    });
    expect(screen.getByText(/ready/i)).toBeTruthy();
    // Residual (sa): cap/spent appear on Budget card and decision-tree bar.
    expect(screen.getAllByText("$5.00").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("$1.0000").length).toBeGreaterThanOrEqual(1);
  });

  it("projects cost and shows honest unknown pricing", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => expect(screen.getAllByText(/zai/).length).toBeGreaterThan(0));
    const buttons = screen.getAllByRole("button");
    const project = buttons.find((b) => /project cost/i.test(b.textContent ?? ""));
    expect(project).toBeTruthy();
    await user.click(project!);
    await waitFor(() => {
      expect(
        screen.getByText(/tier pricing is 0\.0 placeholder/i),
      ).toBeTruthy();
    });
    // Projection still #440 path (mocked api/settings estimatePromptCost)
    expect(estimatePromptCost).toHaveBeenCalled();
  });

  it("installs decision-tree driver via Settings panel", async () => {
    const user = userEvent.setup();
    const { container } = render(<Settings />);
    await waitFor(() => expect(screen.getAllByText(/zai/).length).toBeGreaterThan(0));
    const installBtn = container.querySelector(
      '[data-testid="decision-tree-install"]',
    ) as HTMLButtonElement | null;
    expect(installBtn).toBeTruthy();
    const modelInput = container.querySelector(
      '[data-testid="decision-tree-model"]',
    ) as HTMLInputElement;
    expect(modelInput).toBeTruthy();
    await user.clear(modelInput);
    await user.type(modelInput, "glm-5.2");
    await user.click(installBtn!);
    await waitFor(() => {
      expect(installDecisionTreeSelection).toHaveBeenCalled();
    });
    const call = installDecisionTreeSelection.mock.calls.at(-1)?.[0] as {
      model_id: string;
    };
    expect(call.model_id).toBe("glm-5.2");
    await waitFor(() => {
      const status = container.querySelector('[data-testid="decision-tree-status"]');
      expect(status?.textContent).toMatch(/zai\s*\/\s*glm-5\.2/i);
    });
  });

  it("scrolls to Settings hash anchors on mount (sp)", async () => {
    const scrollIntoView = vi.fn();
    const el = document.createElement("div");
    el.id = "decision-tree-panel";
    el.scrollIntoView = scrollIntoView;
    document.body.appendChild(el);
    window.location.hash = "#decision-tree-panel";
    render(<Settings />);
    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalled();
    });
    window.location.hash = "";
    el.remove();
  });

  it("embeds budget usage bar on decision-tree panel (sa)", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-budget-bar")).toBeTruthy();
    });
    const bar = screen.getByTestId("decision-tree-budget-bar");
    expect(bar.getAttribute("data-has-cap")).toBe("true");
    expect(bar.getAttribute("data-spent-status")).toBe("known");
    // Default mock: spent $1 / cap $5 → 20%
    expect(bar.getAttribute("data-spend-pct")).toBe("20");
    expect(bar.textContent).toMatch(/Budget vs driver/i);
    expect(bar.textContent).toMatch(/soft gate/i);
    expect(screen.getByTestId("decision-tree-budget-progress")).toBeTruthy();
    const projectLink = screen.getByTestId("decision-tree-budget-project-link");
    expect(projectLink.getAttribute("href")).toBe("#prompt-cost-projection");
    expect(screen.getByTestId("prompt-cost-projection-panel")).toBeTruthy();
  });

  it("projects sample cost from decision-tree mini panel (sb)", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-project-cost")).toBeTruthy();
    });
    await user.click(screen.getByTestId("decision-tree-project-cost"));
    await waitFor(() => {
      expect(estimatePromptCost).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-mini-estimate")).toBeTruthy();
    });
    const mini = screen.getByTestId("decision-tree-mini-estimate");
    // Default estimate mock: pricing_known false → would_exceed unknown
    expect(mini.getAttribute("data-pricing-known")).toBe("false");
    expect(mini.getAttribute("data-would-exceed")).toBe("unknown");
    expect(mini.textContent).toMatch(/Sample projection/i);
    expect(mini.textContent).toMatch(/never invents \$0/i);
  });

  it("loads Antiek-bench weekly usage summary in Settings", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("antiek-bench-usage-panel")).toBeTruthy();
    });
    expect(fetchAntiekBenchUsageSummary).toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.getByTestId("antiek-bench-usage-summary").textContent).toMatch(
        /Events/,
      );
    });
    expect(screen.getByTestId("antiek-bench-usage-panel").getAttribute("data-view-format")).toBe(
      "html",
    );
    // wrestle appears in usage summary and depth-tier chrome
    expect(screen.getAllByText(/wrestle/i).length).toBeGreaterThan(0);
    expect(screen.getByTestId("antiek-bench-usage-html").innerHTML).toContain("2");
    // Residual (hb): by_source list in Settings UI.
    expect(screen.getByTestId("antiek-bench-usage-sources").textContent).toMatch(
      /investigation_start/,
    );
    expect(screen.getByTestId("antiek-bench-usage-sources").textContent).toMatch(
      /session_flywheel/,
    );
    // Residual (rw): default mock by_source has no Write seed sources.
    const usageSources = screen.getByTestId("antiek-bench-usage-sources");
    expect(usageSources.getAttribute("data-write-seed-source-count")).toBe("0");
    for (const row of screen.getAllByTestId("antiek-bench-usage-source-row")) {
      expect(row.getAttribute("data-write-seed-feed")).toBe("false");
    }
    // Residual (rz): weekly Write-seed metrics from substrate SSOT.
    const metrics = screen.getByTestId("antiek-bench-usage-write-seed-metrics");
    expect(metrics.getAttribute("data-write-seed-event-count")).toBe("0");
    expect(metrics.getAttribute("data-write-seed-source-count")).toBe("0");
    expect(metrics.getAttribute("data-write-seed-known-count")).toBe("14");
    expect(metrics.textContent).toMatch(/Write seed this week/i);
    expect(metrics.textContent).toMatch(/not auto-promoted/i);
  });

  it("loads NotDiamond advisory posture — authority rejected", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("notdiamond-advisory-panel")).toBeTruthy();
    });
    expect(fetchNotDiamondAdvisory).toHaveBeenCalled();
    await waitFor(() => {
      expect(
        screen.getByTestId("notdiamond-advisory-summary").textContent,
      ).toMatch(/REJECT/i);
    });
    expect(
      screen.getByTestId("notdiamond-advisory-panel").getAttribute("data-view-format"),
    ).toBe("html");
    // Residual (he): authority / kill-switch attributes for honest posture.
    expect(
      screen
        .getByTestId("notdiamond-advisory-panel")
        .getAttribute("data-authority-rejected"),
    ).toBe("true");
    expect(
      screen
        .getByTestId("notdiamond-advisory-panel")
        .getAttribute("data-is-dispatch-authority"),
    ).toBe("false");
    expect(
      screen.getByTestId("notdiamond-advisory-panel").getAttribute("data-kill-switch"),
    ).toBe("off");
    expect(screen.getByTestId("notdiamond-refresh-advisory")).toBeTruthy();
    expect(screen.getByTestId("notdiamond-week-id")).toBeTruthy();
    expect(screen.getByTestId("notdiamond-advisory-summary").textContent).toMatch(
      /false/i,
    );
    expect(screen.getByTestId("notdiamond-advisory-html").innerHTML).toMatch(
      /authority|REJECT/i,
    );
    // Residual (rl): advisory vs installed driver delta (no driver by default).
    expect(
      screen.getByTestId("notdiamond-advisory-panel").getAttribute("data-advisory-only"),
    ).toBe("true");
    const delta = screen.getByTestId("notdiamond-driver-delta");
    expect(delta.getAttribute("data-advisory-only")).toBe("true");
    expect(delta.getAttribute("data-delta-status")).toBe("no_installed");
    expect(delta.getAttribute("data-suggested")).toBe("stub-strong");
    expect(delta.getAttribute("data-installed")).toBe("");
    expect(screen.getByTestId("notdiamond-driver-delta-label").textContent).toMatch(
      /No driver installed/i,
    );
    expect(screen.getByTestId("notdiamond-suggested-driver").textContent).toMatch(
      /stub-strong/,
    );
  });

  it("shows NotDiamond driver delta when installed differs from advisory (rl)", async () => {
    fetchDecisionTreeSelection.mockResolvedValue({
      model_id: "glm-5.2",
      provider_id: "zai",
      installed: true,
      notes: [],
      source: "test",
    });
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("notdiamond-driver-delta")).toBeTruthy();
    });
    const delta = screen.getByTestId("notdiamond-driver-delta");
    expect(delta.getAttribute("data-delta-status")).toBe("differs");
    expect(delta.getAttribute("data-installed")).toBe("glm-5.2");
    expect(delta.getAttribute("data-suggested")).toBe("stub-strong");
    expect(delta.getAttribute("data-advisory-only")).toBe("true");
    expect(screen.getByTestId("notdiamond-driver-delta-label").textContent).toMatch(
      /not auto-applied/i,
    );
    expect(
      screen.getByTestId("notdiamond-advisory-panel").getAttribute("data-driver-delta"),
    ).toBe("differs");
  });

  it("refreshes NotDiamond weekly advisory for leaderboard week (he)", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("notdiamond-refresh-advisory")).toBeTruthy();
    });
    fetchNotDiamondAdvisory.mockClear();
    await user.click(screen.getByTestId("notdiamond-refresh-advisory"));
    await waitFor(() => {
      expect(fetchNotDiamondAdvisory).toHaveBeenCalled();
    });
    const call = fetchNotDiamondAdvisory.mock.calls.at(-1)?.[0] as {
      includeHtml?: boolean;
      weekId?: string;
    };
    expect(call.includeHtml).toBe(true);
    expect(typeof call.weekId === "string" || call.weekId === undefined).toBe(
      true,
    );
    await waitFor(() => {
      expect(
        screen.getByTestId("notdiamond-advisory-summary").textContent,
      ).toMatch(/REJECT|GO/i);
    });
  });

  it("installs NotDiamond advisory pick as decision-tree driver (never authority)", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("notdiamond-install-advisory")).toBeTruthy();
    });
    expect(screen.getByTestId("notdiamond-advisory-summary").textContent).toMatch(
      /stub-strong/,
    );
    await user.click(screen.getByTestId("notdiamond-install-advisory"));
    await waitFor(() => {
      expect(installDecisionTreeSelection).toHaveBeenCalled();
    });
    const call = installDecisionTreeSelection.mock.calls.at(-1)?.[0] as {
      model_id: string;
      provider_id?: string;
    };
    expect(call.model_id).toBe("stub-strong");
    expect(call.provider_id).toBeTruthy();
  });

  it("shows known feed sources including twin_chase and floating DR (nx)", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("antiek-bench-usage-known-sources")).toBeTruthy();
    });
    const legend = screen.getByTestId("antiek-bench-usage-known-sources");
    expect(legend.getAttribute("data-has-twin-chase")).toBe("true");
    expect(legend.getAttribute("data-has-floating-dr")).toBe("true");
    // Residual (os): midnight_oil + collective_merge machine-readable honesty.
    expect(legend.getAttribute("data-has-midnight-oil")).toBe("true");
    expect(legend.getAttribute("data-has-collective-merge")).toBe("true");
    // Residual (qy): DR write seed feed sources in known legend.
    expect(legend.getAttribute("data-has-deep-research-session")).toBe("true");
    expect(legend.getAttribute("data-has-research-progress-complete")).toBe(
      "true",
    );
    // Residual (ra): dual-handoff Write seed sources in known legend.
    expect(legend.getAttribute("data-has-midnight-oil-deposit")).toBe("true");
    expect(legend.getAttribute("data-has-hosted-html-document")).toBe("true");
    expect(legend.textContent).toMatch(/twin_chase/);
    expect(legend.textContent).toMatch(/floating_deep_research/);
    expect(legend.textContent).toMatch(/midnight_oil/);
    expect(legend.textContent).toMatch(/collective_merge/);
    expect(legend.textContent).toMatch(/deep_research_session/);
    expect(legend.textContent).toMatch(/research_progress_complete/);
    expect(legend.textContent).toMatch(/midnight_oil_deposit/);
    expect(legend.textContent).toMatch(/hosted_html_document/);
    // Residual (rk): full Write seed matrix in known legend.
    expect(legend.getAttribute("data-has-evidence-pack")).toBe("true");
    expect(legend.getAttribute("data-has-publication-hydrate")).toBe("true");
    expect(legend.getAttribute("data-has-session-flywheel-complete")).toBe(
      "true",
    );
    expect(legend.getAttribute("data-has-context-search")).toBe("true");
    expect(legend.getAttribute("data-has-research-context-pack")).toBe("true");
    // Residual (rq): mid-flight + terminal progress Write seeds in known legend.
    expect(legend.getAttribute("data-has-research-progress-draft")).toBe("true");
    expect(legend.getAttribute("data-has-research-progress-complete")).toBe(
      "true",
    );
    expect(legend.textContent).toMatch(/evidence_pack/);
    expect(legend.textContent).toMatch(/publication_hydrate/);
    expect(legend.textContent).toMatch(/session_flywheel_complete/);
    expect(legend.textContent).toMatch(/context_search/);
    expect(legend.textContent).toMatch(/research_context_pack/);
    expect(legend.textContent).toMatch(/research_progress_draft/);
    expect(legend.textContent).toMatch(/research_progress_complete/);
    // Residual (rs): twin promote Write seed in known legend.
    expect(legend.getAttribute("data-has-twin-promote-context")).toBe("true");
    expect(legend.textContent).toMatch(/twin_promote_context/);
    // Residual (ru/ry): aggregate Write seed known-count honesty (substrate SSOT).
    const writeSeedKnown = Number(
      legend.getAttribute("data-write-seed-known-count") || "0",
    );
    expect(writeSeedKnown).toBe(14);
    expect(screen.getByTestId("antiek-bench-write-seed-known-count").textContent).toMatch(
      /Write seed feeds/i,
    );
    expect(screen.getByTestId("antiek-bench-write-seed-known-count").textContent).toMatch(
      "14",
    );
    // Residual (nx): by_source list includes chase open sources when present.
    const sources = screen.getByTestId("antiek-bench-usage-sources");
    expect(sources.textContent).toMatch(/twin_chase/);
    expect(sources.textContent).toMatch(/floating_deep_research/);
    expect(sources.textContent).toMatch(/midnight_oil/);
    expect(sources.textContent).toMatch(/collective_merge/);
  });

  it("links dual-gate checklist + NotDiamond advisory-only on suite panel (nt)", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(
        screen.getByTestId("antiek-bench-suite-proposal-panel"),
      ).toBeTruthy();
    });
    const dual = screen.getByTestId("antiek-bench-dual-gate-checklist-link");
    expect(dual.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4/);
    const nd = screen.getByTestId("antiek-bench-notdiamond-advisory-only");
    expect(nd.getAttribute("data-notdiamond-authority")).toBe("advisory_only");
    expect(nd.textContent).toMatch(/advisory only/i);
    // Residual (ro): suite L7 banner deep-links to ND advisory panel.
    expect(nd.getAttribute("href")).toBe("#notdiamond-advisory");
    expect(nd.tagName.toLowerCase()).toBe("a");
  });

  it("shows suite proposal feed sources from usage by_source (hf/nz/os)", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(
        screen.getByTestId("antiek-bench-suite-proposal-feed-sources"),
      ).toBeTruthy();
    });
    // Usage mock includes investigation_start + session_flywheel (hb).
    const feed = screen.getByTestId("antiek-bench-suite-proposal-feed-sources");
    expect(feed.textContent).toMatch(/investigation_start/);
    expect(feed.textContent).toMatch(/session_flywheel/);
    // Residual (nz): twin_chase + floating_deep_research when recorded.
    expect(feed.textContent).toMatch(/twin_chase/);
    expect(feed.textContent).toMatch(/floating_deep_research/);
    expect(feed.getAttribute("data-has-twin-chase")).toBe("true");
    expect(feed.getAttribute("data-has-floating-dr")).toBe("true");
    // Residual (os): midnight_oil + collective_merge feed chrome.
    expect(feed.textContent).toMatch(/midnight_oil/);
    expect(feed.textContent).toMatch(/collective_merge/);
    expect(feed.getAttribute("data-has-midnight-oil")).toBe("true");
    expect(feed.getAttribute("data-has-collective-merge")).toBe("true");
    expect(
      screen.getByTestId("antiek-bench-suite-proposal-panel").getAttribute(
        "data-propose-not-promote",
      ),
    ).toBe("true");
    // Residual (rt): default primary twin_chase is not a Write seed feed.
    const primary = screen.getByTestId("antiek-bench-suite-proposal-primary-feed");
    expect(primary.getAttribute("data-primary-feed-source")).toBe("twin_chase");
    expect(primary.getAttribute("data-write-seed-feed")).toBe("false");
    expect(screen.queryByTestId("antiek-bench-primary-feed-write-seed")).toBeNull();
    // Residual (rv): ranked rows stamp write-seed honestly (default mock has none).
    expect(feed.getAttribute("data-write-seed-ranked-count")).toBe("0");
    const rankedRows = screen.getAllByTestId("antiek-bench-ranked-feed-row");
    expect(rankedRows.length).toBeGreaterThan(0);
    for (const row of rankedRows) {
      expect(row.getAttribute("data-write-seed-feed")).toBe("false");
      expect(row.textContent || "").not.toMatch(/\[write seed\]/);
    }
  });

  it("labels primary rewrite feed when it is a Write seed source (rt)", async () => {
    fetchAntiekBenchUsageSummary.mockResolvedValue({
      event_count: 5,
      by_task_class: {},
      by_source: {
        twin_promote_context: 9,
        twin_chase: 2,
      },
      known_sources: ["twin_promote_context", "twin_chase"],
      write_seed_by_source: { twin_promote_context: 9 },
      write_seed_source_count: 1,
      write_seed_event_count: 9,
      write_seed_known_count: 1,
      view_format: "html",
      settings_panel: "antiek_bench_usage_weekly",
      source: "antiek_bench.usage_events",
      notes: [],
      html: "<p>Write seed primary</p>",
    });
    render(<Settings />);
    await waitFor(() => {
      expect(
        screen.getByTestId("antiek-bench-suite-proposal-primary-feed"),
      ).toBeTruthy();
    });
    const primary = screen.getByTestId("antiek-bench-suite-proposal-primary-feed");
    expect(primary.getAttribute("data-primary-feed-source")).toBe(
      "twin_promote_context",
    );
    expect(primary.getAttribute("data-write-seed-feed")).toBe("true");
    expect(screen.getByTestId("antiek-bench-primary-feed-write-seed").textContent).toMatch(
      /Write seed feed/i,
    );
    // Residual (rv): ranked write-seed row stamped when primary is Write seed.
    const feed = screen.getByTestId("antiek-bench-suite-proposal-feed-sources");
    expect(feed.getAttribute("data-write-seed-ranked-count")).toBe("1");
    const promoteRow = screen
      .getAllByTestId("antiek-bench-ranked-feed-row")
      .find((el) => el.getAttribute("data-feed-source") === "twin_promote_context");
    expect(promoteRow).toBeTruthy();
    expect(promoteRow!.getAttribute("data-write-seed-feed")).toBe("true");
    expect(promoteRow!.textContent).toMatch(/\[write seed\]/);
    const chaseRow = screen
      .getAllByTestId("antiek-bench-ranked-feed-row")
      .find((el) => el.getAttribute("data-feed-source") === "twin_chase");
    expect(chaseRow?.getAttribute("data-write-seed-feed")).toBe("false");
    // Residual (rw): usage weekly by_source list also stamps write-seed rows.
    const usageSources = screen.getByTestId("antiek-bench-usage-sources");
    expect(usageSources.getAttribute("data-write-seed-source-count")).toBe("1");
    const usagePromote = screen
      .getAllByTestId("antiek-bench-usage-source-row")
      .find((el) => el.getAttribute("data-source") === "twin_promote_context");
    expect(usagePromote?.getAttribute("data-write-seed-feed")).toBe("true");
    expect(usagePromote?.textContent).toMatch(/\[write seed\]/);
    const usageChase = screen
      .getAllByTestId("antiek-bench-usage-source-row")
      .find((el) => el.getAttribute("data-source") === "twin_chase");
    expect(usageChase?.getAttribute("data-write-seed-feed")).toBe("false");
    // Residual (rz): SSOT metrics reflect write-seed override week.
    const metrics = screen.getByTestId("antiek-bench-usage-write-seed-metrics");
    expect(metrics.getAttribute("data-write-seed-event-count")).toBe("9");
    expect(metrics.getAttribute("data-write-seed-source-count")).toBe("1");
    expect(metrics.getAttribute("data-write-seed-known-count")).toBe("1");
  });

  it("surfaces suite rewrite rationale + feed source count (pe)", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(
        screen.getByTestId("antiek-bench-suite-proposal-rationale"),
      ).toBeTruthy();
    });
    const rationale = screen.getByTestId(
      "antiek-bench-suite-proposal-rationale",
    );
    expect(rationale.textContent).toMatch(/Rewrite rationale/i);
    expect(rationale.textContent).toMatch(/not auto-promoted/i);
    expect(rationale.textContent).toMatch(/Ingested 2 usage events/i);
    expect(rationale.getAttribute("data-propose-not-promote")).toBe("true");
    expect(rationale.getAttribute("data-proposed-task-count")).toBe("1");
    expect(Number(rationale.getAttribute("data-feed-source-count") || 0)).toBeGreaterThan(
      0,
    );
    const metrics = screen.getByTestId("antiek-bench-suite-proposal-metrics");
    expect(metrics.getAttribute("data-has-rationale")).toBe("true");
    expect(Number(metrics.getAttribute("data-feed-source-count") || 0)).toBeGreaterThan(
      0,
    );
    expect(metrics.textContent).toMatch(/feed_sources=/);
  });

  it("surfaces primary rewrite feed source from by_source max (qa)", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(
        screen.getByTestId("antiek-bench-suite-proposal-primary-feed"),
      ).toBeTruthy();
    });
    const primary = screen.getByTestId(
      "antiek-bench-suite-proposal-primary-feed",
    );
    expect(primary.getAttribute("data-primary-feed-source")).toBe("twin_chase");
    expect(primary.getAttribute("data-primary-feed-count")).toBe("3");
    expect(primary.getAttribute("data-propose-not-promote")).toBe("true");
    expect(primary.textContent).toMatch(/Primary rewrite feed/i);
    expect(primary.textContent).toMatch(/twin_chase/);
    const metrics = screen.getByTestId("antiek-bench-suite-proposal-metrics");
    expect(metrics.getAttribute("data-primary-feed-source")).toBe("twin_chase");
    expect(metrics.textContent).toMatch(/primary_feed=twin_chase=3/);
    const feed = screen.getByTestId("antiek-bench-suite-proposal-feed-sources");
    expect(feed.getAttribute("data-primary-feed-source")).toBe("twin_chase");
    // Ranked: twin_chase first.
    expect(feed.textContent).toMatch(/^Feed sources \(ranked\): twin_chase=3/);
    const rationale = screen.getByTestId(
      "antiek-bench-suite-proposal-rationale",
    );
    expect(rationale.getAttribute("data-primary-feed-source")).toBe(
      "twin_chase",
    );
    expect(rationale.textContent).toMatch(/primary feed twin_chase=3/);
  });

  it("groups proposed suite tasks by task class (hg)", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("antiek-bench-proposed-tasks")).toBeTruthy();
    });
    // Mock has added_item_ids: ["usage-distill-abcd12-0"]
    await waitFor(() => {
      expect(
        screen.getByTestId("antiek-bench-proposed-task-classes").textContent,
      ).toMatch(/distill/);
    });
    expect(
      screen
        .getByTestId("antiek-bench-proposed-task-classes")
        .getAttribute("data-class-count"),
    ).toBe("1");
  });

  it("loads Antiek-bench suite proposal — proposed not auto-promoted", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("antiek-bench-suite-proposal-panel")).toBeTruthy();
    });
    expect(fetchAntiekBenchSuiteProposal).toHaveBeenCalled();
    await waitFor(() => {
      expect(
        screen.getByTestId("antiek-bench-suite-proposal-summary").textContent,
      ).toMatch(/proposed/i);
    });
    const panel = screen.getByTestId("antiek-bench-suite-proposal-panel");
    expect(panel.getAttribute("data-view-format")).toBe("html");
    // Residual (fg): propose≠promote banner + proposed task list.
    expect(panel.getAttribute("data-propose-not-promote")).toBe("true");
    expect(panel.getAttribute("data-auto-promoted")).toBe("false");
    expect(screen.getByTestId("antiek-bench-propose-not-promote").textContent).toMatch(
      /propose ≠ auto-promote/i,
    );
    // Residual (ht): recursive rewrite metrics machine attrs.
    const metrics = screen.getByTestId("antiek-bench-suite-proposal-metrics");
    expect(metrics.getAttribute("data-has-proposal")).toBe("true");
    expect(metrics.getAttribute("data-status")).toBe("proposed");
    expect(metrics.getAttribute("data-proposal-id")).toBe("prop_testdeadbeef01");
    expect(metrics.getAttribute("data-event-count")).toBe("2");
    expect(metrics.getAttribute("data-proposed-task-count")).toBe("1");
    expect(metrics.getAttribute("data-auto-promoted")).toBe("false");
    expect(metrics.getAttribute("data-propose-not-promote")).toBe("true");
    expect(metrics.textContent).toMatch(/Recursive rewrite/);
    const tasks = screen.getByTestId("antiek-bench-proposed-tasks");
    expect(tasks.getAttribute("data-task-count")).toBe("1");
    expect(screen.getByTestId("antiek-bench-proposed-task-id").textContent).toMatch(
      /usage-distill/,
    );
    const summary = screen.getByTestId("antiek-bench-suite-proposal-summary");
    expect(summary.textContent).toMatch(/prop_testdeadbeef01/);
    expect(summary.textContent).toMatch(/Auto-promoted\s*false/i);
    expect(screen.getByTestId("antiek-bench-suite-proposal-html").innerHTML).toMatch(
      /proposal|proposed/i,
    );
  });

  it("approves suite proposal via explicit Settings gate", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("antiek-bench-suite-approve")).toBeTruthy();
    });
    const approveBtn = screen.getByTestId("antiek-bench-suite-approve");
    expect(approveBtn).toBeTruthy();
    await waitFor(() => {
      expect((approveBtn as HTMLButtonElement).disabled).toBe(false);
    });
    await user.click(approveBtn);
    await waitFor(() => {
      expect(approveAntiekBenchSuiteProposal).toHaveBeenCalled();
    });
    const call = approveAntiekBenchSuiteProposal.mock.calls.at(-1)?.[0] as {
      proposal_id: string;
      approve: boolean;
    };
    expect(call.proposal_id).toBe("prop_testdeadbeef01");
    expect(call.approve).toBe(true);
    await waitFor(() => {
      expect(
        screen.getByTestId("antiek-bench-suite-approve-result").textContent,
      ).toMatch(/approved|Promoted\s*true/i);
    });
  });

  it("applies depth-tier wrestle preset and shows projection hints", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("depth-tier-panel")).toBeTruthy();
    });
    expect(fetchDepthTiers).toHaveBeenCalled();
    await user.click(screen.getByTestId("depth-tier-wrestle"));
    await waitFor(() => {
      expect(applyDepthTier).toHaveBeenCalled();
    });
    const call = applyDepthTier.mock.calls.at(-1)?.[0] as {
      depth_tier: string;
    };
    expect(call.depth_tier).toBe("wrestle");
    await waitFor(() => {
      expect(screen.getByTestId("depth-tier-summary").textContent).toMatch(
        /wrestle/i,
      );
    });
    expect(
      screen.getByTestId("depth-tier-panel").getAttribute("data-view-format"),
    ).toBe("html");
    // Residual (be): applying depth tier auto-projects cost via #440 API
    await waitFor(() => {
      expect(estimatePromptCost).toHaveBeenCalled();
    });
    const est = estimatePromptCost.mock.calls.at(-1)?.[0] as {
      tier?: string;
      expected_output_tokens?: number;
      input_chars?: number;
    };
    expect(est.tier).toBe("pro"); // wrestle maps dispatch tier to pro
    expect(est.expected_output_tokens).toBe(4000);
    expect(est.input_chars).toBe(1500);
  });

  it("loads competitive dogfood fixtures — never auto-promoted", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("antiek-bench-dogfood-panel")).toBeTruthy();
    });
    expect(fetchAntiekBenchDogfoodFixtures).toHaveBeenCalled();
    await waitFor(() => {
      expect(
        screen.getByTestId("antiek-bench-dogfood-summary").textContent,
      ).toMatch(/suite-competitive-dogfood-v1/);
    });
    expect(
      screen
        .getByTestId("antiek-bench-dogfood-panel")
        .getAttribute("data-view-format"),
    ).toBe("html");
    expect(
      screen.getByTestId("antiek-bench-dogfood-summary").textContent,
    ).toMatch(/Auto-promoted\s*false/i);
    expect(screen.getByTestId("antiek-bench-dogfood-html").innerHTML).toMatch(
      /items=5|dogfood/i,
    );
  });

  it("loads Antiek-bench weekly leaderboard — advisory ranking", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("antiek-bench-leaderboard-panel")).toBeTruthy();
    });
    expect(fetchAntiekBenchLeaderboard).toHaveBeenCalled();
    await waitFor(() => {
      expect(
        screen.getByTestId("antiek-bench-leaderboard-summary").textContent,
      ).toMatch(/strong-model/);
    });
    expect(
      screen
        .getByTestId("antiek-bench-leaderboard-panel")
        .getAttribute("data-view-format"),
    ).toBe("html");
    expect(screen.getByTestId("antiek-bench-leaderboard-html").innerHTML).toMatch(
      /Leaderboard|strong-model/i,
    );
  });

  it("runs offline dogfood suite and shows result panel", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("antiek-bench-run-offline")).toBeTruthy();
    });
    await user.click(screen.getByTestId("antiek-bench-run-offline"));
    await waitFor(() => {
      expect(runAntiekBenchOffline).toHaveBeenCalled();
    });
    const call = runAntiekBenchOffline.mock.calls.at(-1)?.[0] as {
      weekId: string;
      includeHtml?: boolean;
    };
    expect(call.weekId).toBeTruthy();
    expect(call.includeHtml).toBe(true);
    await waitFor(() => {
      expect(screen.getByTestId("antiek-bench-run-offline-result").textContent).toMatch(
        /stub-strong/,
      );
    });
    expect(
      screen.getByTestId("antiek-bench-run-offline-result").textContent,
    ).toMatch(/3/);
    // Residual (dt): usage events + auto-promoted honesty + weekly agent note.
    expect(
      screen.getByTestId("antiek-bench-run-offline-result").textContent,
    ).toMatch(/Usage events recorded/);
    expect(
      screen.getByTestId("antiek-bench-run-offline-result").textContent,
    ).toMatch(/15/);
    expect(
      screen
        .getByTestId("antiek-bench-run-offline-result")
        .getAttribute("data-auto-promoted"),
    ).toBe("false");
    expect(screen.getByTestId("antiek-bench-weekly-agent-note").textContent).toMatch(
      /LaunchAgent/i,
    );
    expect(screen.getByTestId("antiek-bench-run-offline-html").innerHTML).toMatch(
      /offline dogfood|2026-W28/i,
    );
    // Residual (dv/dx/dy): suite proposal + usage + NotDiamond advisory refreshed.
    await waitFor(() => {
      expect(fetchAntiekBenchSuiteProposal.mock.calls.length).toBeGreaterThanOrEqual(
        2,
      );
    });
    await waitFor(() => {
      expect(fetchAntiekBenchUsageSummary.mock.calls.length).toBeGreaterThanOrEqual(
        2,
      );
    });
    await waitFor(() => {
      expect(fetchNotDiamondAdvisory.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
    // Never treat ND as dispatch authority after refresh.
    const ndCall = fetchNotDiamondAdvisory.mock.calls.at(-1)?.[0] as {
      weekId?: string;
    };
    expect(ndCall?.weekId).toBeTruthy();
  });

  it("installs recommended leaderboard model as decision-tree driver", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => {
      expect(
        screen.getByTestId("antiek-bench-leaderboard-install-recommended"),
      ).toBeTruthy();
    });
    await user.click(
      screen.getByTestId("antiek-bench-leaderboard-install-recommended"),
    );
    await waitFor(() => {
      expect(installDecisionTreeSelection).toHaveBeenCalled();
    });
    const call = installDecisionTreeSelection.mock.calls.at(-1)?.[0] as {
      model_id: string;
      provider_id?: string;
    };
    expect(call.model_id).toBe("strong-model");
    expect(call.provider_id).toBeTruthy();
  });

  it("registers an operator model via Add model panel", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("add-model-panel")).toBeTruthy();
    });
    expect(fetchRegisteredModels).toHaveBeenCalled();
    await user.type(screen.getByTestId("add-model-provider"), "zai");
    await user.type(screen.getByTestId("add-model-id"), "glm-5.2");
    await user.click(screen.getByTestId("add-model-submit"));
    await waitFor(() => {
      expect(registerSettingsModel).toHaveBeenCalled();
    });
    const call = registerSettingsModel.mock.calls.at(-1)?.[0] as {
      model_id: string;
      provider_id: string;
      select: boolean;
    };
    expect(call.model_id).toBe("glm-5.2");
    expect(call.provider_id).toBe("zai");
    await waitFor(() => {
      expect(screen.getByTestId("add-model-summary").textContent).toMatch(
        /glm-5\.2/,
      );
    });
    expect(
      screen.getByTestId("add-model-panel").getAttribute("data-view-format"),
    ).toBe("html");
  });
});
