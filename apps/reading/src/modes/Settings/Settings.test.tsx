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
  fetchRegisteredModels,
  registerSettingsModel,
  fetchNotDiamondAdvisory,
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
    fetchAntiekBenchUsageSummary: vi.fn(async () => ({
      event_count: 2,
      by_task_class: {
        wrestle: { worked: 1, failed: 0, total: 1 },
        book_qa: { worked: 0, failed: 1, total: 1 },
      },
      view_format: "html",
      settings_panel: "antiek_bench_usage_weekly",
      source: "antiek_bench.usage_events",
      notes: [],
      html: "<p>Events recorded: 2</p>",
    })),
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
      view_format: "html",
      settings_panel: "notdiamond_advisory",
      source: "docs/htmlspec/notdiamond-verdict/VERDICT.md",
      verdict_date: "2026-07-09",
      notes: ["Authority REJECT under §16"],
      html: "<p>Authority REJECT — not the dispatch authority</p>",
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
  fetchRegisteredModels,
  registerSettingsModel,
  fetchNotDiamondAdvisory,
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
    fetchAntiekBenchSuiteProposal.mockClear();
    approveAntiekBenchSuiteProposal.mockClear();
    fetchDepthTiers.mockClear();
    applyDepthTier.mockClear();
    fetchAntiekBenchDogfoodFixtures.mockClear();
    fetchAntiekBenchLeaderboard.mockClear();
    fetchRegisteredModels.mockClear();
    registerSettingsModel.mockClear();
    fetchNotDiamondAdvisory.mockClear();
  });

  it("renders registered providers and budget bar", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getAllByText(/zai/).length).toBeGreaterThan(0);
    });
    expect(screen.getByText(/ready/i)).toBeTruthy();
    expect(screen.getByText("$5.00")).toBeTruthy();
    expect(screen.getByText("$1.0000")).toBeTruthy();
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
    expect(screen.getByTestId("notdiamond-advisory-summary").textContent).toMatch(
      /false/i,
    );
    expect(screen.getByTestId("notdiamond-advisory-html").innerHTML).toMatch(
      /authority|REJECT/i,
    );
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
    expect(
      screen
        .getByTestId("antiek-bench-suite-proposal-panel")
        .getAttribute("data-view-format"),
    ).toBe("html");
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
