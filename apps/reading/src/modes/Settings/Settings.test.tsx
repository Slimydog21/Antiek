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
  fetchMidnightOilLiveStepStatus,
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
      "marketplace_catalog",
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
      "collective_unit_prompt",
      "twin_cross_asset_merge",
      "collective_written_analysis",
      "antiek_bench.offline_dogfood",
      "engagement",
    ],
    // Residual (ry): substrate Write-seed aggregates (SSOT).
    write_seed_by_source: {} as Record<string, number>,
    write_seed_source_count: 0,
    write_seed_event_count: 0,
    // Residual (aaj/anw): includes marketplace_catalog + meta_reading_deliverable (19 write-seed sources).
    write_seed_known_count: 19,
    // Residual (act/acu): body honesty aggregates for recursive rewrite.
    write_seed_with_body_count: 0,
    write_seed_title_only_count: 0,
    write_seed_body_unknown_count: 0,
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
      rationale:
        "Ingested 2 usage events; added 1 items from failed outcomes · title-only Write seeds (has_body=false): 1 (body honesty → suite rewrite)",
      added_item_ids: ["usage-distill-abcd12-0"],
      // Residual (acy/adp): full body honesty matrix on suite proposal.
      title_only_write_seed_count: 1,
      with_body_write_seed_count: 2,
      body_unknown_write_seed_count: 0,
      event_count: 2,
      view_format: "html",
      settings_panel: "antiek_bench_suite_proposal",
      source: "antiek_bench.propose_from_recorded_usage",
      notes: ["Proposal status is proposed only"],
      html: "<p>Status: proposal only · proposed · Body honesty matrix: with_body=2 · title_only=1 · unknown=0</p>",
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
      // Residual (st/su/…/adn/aeu/afo/ags/agw/ahd): competitive dogfood v23 postures.
      suite_version: "suite-competitive-dogfood-v35",
      label: "antiek-bench-competitive-dogfood",
      item_count: 53,
      by_task_class: {
        distill: 2,
        synthesize: 2,
        wrestle: 39,
        book_qa: 10,
      },
      // Residual (yb/adn/aeu/afo/ags/agw/ahd): full v23 item list (matches substrate; item_count-matches-listed).
      items: [
        { item_id: "dogfood-distill-attention", task_class: "distill", prompt: "Distill attention claim" },
        { item_id: "dogfood-synth-perplexity-vs-openai", task_class: "synthesize", prompt: "Perplexity vs OpenAI" },
        { item_id: "dogfood-wrestle-twin-notes", task_class: "wrestle", prompt: "twin notes wrestle" },
        { item_id: "dogfood-book-html-first", task_class: "book_qa", prompt: "HTML-first book QA" },
        { item_id: "dogfood-wrestle-citations", task_class: "wrestle", prompt: "citations wrestle" },
        { item_id: "dogfood-wrestle-write-seed", task_class: "wrestle", prompt: "twin_seed Write path" },
        { item_id: "dogfood-synth-float-evidence", task_class: "synthesize", prompt: "float evidence HTML" },
        { item_id: "dogfood-distill-budget-foresight", task_class: "distill", prompt: "budget projection" },
        { item_id: "dogfood-book-faraday-induction", task_class: "book_qa", prompt: "Faraday induction free PD HTML" },
        { item_id: "dogfood-wrestle-collective-unit-write-seed", task_class: "wrestle", prompt: "collective_unit_prompt twin_seed Write path" },
        { item_id: "dogfood-book-boole-laws-of-thought", task_class: "book_qa", prompt: "Boole laws of thought free PD HTML" },
        { item_id: "dogfood-book-heaviside-em", task_class: "book_qa", prompt: "Heaviside electromagnetic free PD HTML" },
        { item_id: "dogfood-wrestle-citation-trust-ungrounded", task_class: "wrestle", prompt: "citation trust ungrounded hydrate prep" },
        { item_id: "dogfood-wrestle-twin-cross-asset-merge-write-seed", task_class: "wrestle", prompt: "twin_cross_asset_merge Write twin_seed path" },
        { item_id: "dogfood-wrestle-collective-written-analysis-write-seed", task_class: "wrestle", prompt: "collective_written_analysis Write twin_seed path" },
        { item_id: "dogfood-wrestle-write-seed-has-body", task_class: "wrestle", prompt: "write-seed has-body title-only honesty rewrite" },
        { item_id: "dogfood-book-shannon-communication", task_class: "book_qa", prompt: "Shannon mathematical theory of communication free PD HTML" },
        { item_id: "dogfood-book-turing-computable-numbers", task_class: "book_qa", prompt: "Turing on computable numbers free PD HTML" },
        { item_id: "dogfood-book-lovelace-analytical-engine", task_class: "book_qa", prompt: "Lovelace Analytical Engine free PD HTML" },
        { item_id: "dogfood-book-godel-incompleteness", task_class: "book_qa", prompt: "Gödel incompleteness free PD HTML foundations" },
        { item_id: "dogfood-book-fourier-heat", task_class: "book_qa", prompt: "Fourier Analytical Theory of Heat free PD HTML" },
        { item_id: "dogfood-wrestle-seamless-write-path", task_class: "wrestle", prompt: "seamless Open Write path honesty merge host MO" },
        { item_id: "dogfood-wrestle-intelligent-search-context-write", task_class: "wrestle", prompt: "intelligent search evidence citation-trust Write" },
        { item_id: "dogfood-wrestle-written-analysis-open-write-source", task_class: "wrestle", prompt: "written analysis Open Write source not doc merge" },
        { item_id: "dogfood-wrestle-continue-as-unit-path", task_class: "wrestle", prompt: "continue-as-unit seamless unit path honesty" },
        { item_id: "dogfood-wrestle-select-open-path", task_class: "wrestle", prompt: "Select open multi-select assembly path honesty" },
        { item_id: "dogfood-wrestle-unit-restore-path", task_class: "wrestle", prompt: "restore last unit membership path honesty" },
        { item_id: "dogfood-wrestle-select-recent-path", task_class: "wrestle", prompt: "Select recent multi-select assembly path honesty" },
        { item_id: "dogfood-wrestle-research-workstation-spine", task_class: "wrestle", prompt: "ResearchWorkstation twins context collective spine" },
        { item_id: "dogfood-wrestle-highlight-deep-research-path", task_class: "wrestle", prompt: "highlight seamless deep research path honesty" },
        { item_id: "dogfood-wrestle-talk-to-book-twins", task_class: "wrestle", prompt: "TalkToBook twin note-taker path" },
        { item_id: "dogfood-wrestle-meta-reading-twins", task_class: "wrestle", prompt: "MetaReading twin note-taker path" },
        { item_id: "dogfood-wrestle-research-this-twins", task_class: "wrestle", prompt: "ResearchThis twin note-taker path" },
        { item_id: "dogfood-wrestle-spawn-merge-path", task_class: "wrestle", prompt: "seamless highlight→DR→spawn merge path" },
        { item_id: "dogfood-wrestle-collective-multi-spawn-merge", task_class: "wrestle", prompt: "seamless multi-spawn collective merge path" },
        { item_id: "dogfood-wrestle-pub-quick-call-matrix", task_class: "wrestle", prompt: "knowledge-dense pub quick-call matrix" },
        { item_id: "dogfood-wrestle-budget-foresight-pub-refs", task_class: "wrestle", prompt: "budget foresight with pub refs" },
        { item_id: "dogfood-wrestle-purchase-seamless-port", task_class: "wrestle", prompt: "purchase seamless port L5 deferred" },
        { item_id: "dogfood-wrestle-domain-aware-twin-search", task_class: "wrestle", prompt: "domain-aware twin intelligent search" },
        { item_id: "dogfood-wrestle-collective-unit-twin-seed", task_class: "wrestle", prompt: "collective unit twin seed" },
        { item_id: "dogfood-wrestle-moil-deposit-twin-honesty", task_class: "wrestle", prompt: "MO deposit twin honesty" },
        { item_id: "dogfood-wrestle-pub-ref-foresight-chrome", task_class: "wrestle", prompt: "pub-ref foresight chrome matrix" },
        { item_id: "dogfood-wrestle-citation-chain", task_class: "wrestle", prompt: "citation chain honesty" },
        { item_id: "dogfood-wrestle-citation-chain-hops", task_class: "wrestle", prompt: "multi-hop citation chain hops navigation" },
        { item_id: "dogfood-wrestle-domain-aware-stem-expanded", task_class: "wrestle", prompt: "domain-aware STEM expanded twin search" },
        { item_id: "dogfood-wrestle-evidence-write-multi-hop", task_class: "wrestle", prompt: "evidence Write multi-hop hop honesty" },
        { item_id: "dogfood-wrestle-twin-promote-depth-graph", task_class: "wrestle", prompt: "twin promote depth-graph unit node honesty" },
        { item_id: "dogfood-wrestle-twin-promote-write-depth-graph", task_class: "wrestle", prompt: "twin promote Write depth-graph honesty" },
        { item_id: "dogfood-wrestle-talk-to-book-collective", task_class: "wrestle", prompt: "talk collective" },
        { item_id: "dogfood-wrestle-meta-reading-collective", task_class: "wrestle", prompt: "meta collective" },
        { item_id: "dogfood-wrestle-marketplace-host-collective", task_class: "wrestle", prompt: "marketplace host collective" },
        { item_id: "dogfood-book-nicomachean-ethics", task_class: "book_qa", prompt: "Nicomachean Ethics free PD HTML" },
        { item_id: "dogfood-wrestle-competitive-dr-scorecard", task_class: "wrestle", prompt: "competitive DR scorecard" },
      ],
      auto_promoted: false,
      view_format: "html",
      settings_panel: "antiek_bench_dogfood_fixtures",
      source: "antiek_bench.dogfood_fixtures",
      notes: ["Competitive dogfood fixtures are offline prompts only."],
      html: "<p>Suite suite-competitive-dogfood-v35 · items=53 · dogfood-wrestle-twin-promote-write-depth-graph · dogfood-wrestle-competitive-dr-scorecard</p>",
    })),
    fetchAntiekBenchLeaderboard: vi.fn(async () => ({
      week_id: "2026-W28",
      models: [
        {
          model_id: "strong-model",
          mean_score: 0.95,
          // Residual (adr): per-task scores for weekly model quality honesty.
          by_task_class: { distill: 0.99, wrestle: 0.92, synthesize: 0.9 },
        },
        {
          model_id: "weak-model",
          mean_score: 0.2,
          by_task_class: { distill: 0.15, wrestle: 0.1, synthesize: 0.25 },
        },
        {
          model_id: "book-specialist",
          mean_score: 0.7,
          by_task_class: { book_qa: 0.98, distill: 0.5 },
        },
      ],
      task_classes: ["book_qa", "distill", "synthesize", "wrestle"],
      run_count: 3,
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
    // Residual (sz): offline-honest MO live-step status default.
    fetchMidnightOilLiveStepStatus: vi.fn(async () => ({
      view_format: "html",
      product_panel: "midnight_oil_live_step_status",
      source: "midnight_oil.live_step_wiring",
      offline_honest: true,
      live_env: false,
      injector_installed: false,
      live_env_flag: "ANTIEK_MIDNIGHT_OIL_LIVE_STEP",
      notes: [
        "Midnight Oil default: offline-honest stub steps (live dual-gate off).",
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

vi.mock("../../api/midnightOil", () => ({
  fetchMidnightOilLiveStepStatus,
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
    fetchMidnightOilLiveStepStatus.mockClear();
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
    // Residual (aec): offline default is not L3 live ready.
    expect(panel.getAttribute("data-l3-live-ready")).toBe("false");
    const metrics = screen.getByTestId("twin-seed-live-status-metrics");
    expect(metrics.getAttribute("data-offline-honest")).toBe("true");
    expect(metrics.getAttribute("data-l3-live-ready")).toBe("false");
    expect(metrics.getAttribute("data-l3-gates-live-env")).toBe("false");
    expect(metrics.getAttribute("data-l3-gates-use-dispatch")).toBe("false");
    expect(metrics.getAttribute("data-l3-gates-injector")).toBe("false");
    expect(metrics.textContent).toMatch(/offline-honest identity stubs/);
    // Residual (aec): in-panel L3 checklist deep-link + gate matrix.
    expect(screen.getByTestId("twin-seed-live-l3-prep")).toBeTruthy();
    expect(
      screen
        .getByTestId("twin-seed-live-l3-checklist-link")
        .getAttribute("href"),
    ).toMatch(/DUAL-GATE-L1-L4.*#l3-twin/);
    const gateMatrix = screen.getByTestId("twin-seed-live-l3-gate-matrix");
    expect(gateMatrix.getAttribute("data-l3-live-ready")).toBe("false");
    expect(gateMatrix.textContent).toMatch(/L3 gate matrix/i);
    expect(gateMatrix.textContent).toMatch(/live_ready=false/);
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
    // Residual (aee): offline default — neither L1 nor L2 live ready.
    expect(panel.getAttribute("data-l1-arxiv-live-ready")).toBe("false");
    expect(panel.getAttribute("data-l2-substack-live-ready")).toBe("false");
    const metrics = screen.getByTestId("hydrate-live-status-metrics");
    expect(metrics.getAttribute("data-offline-honest")).toBe("true");
    expect(metrics.getAttribute("data-arxiv-injector")).toBe("false");
    expect(metrics.getAttribute("data-substack-injector")).toBe("false");
    expect(metrics.getAttribute("data-l1-arxiv-live-ready")).toBe("false");
    expect(metrics.getAttribute("data-l2-substack-live-ready")).toBe("false");
    expect(metrics.textContent).toMatch(/offline-honest identity/);
    // Residual (aee): in-panel L1/L2 checklist + gate matrix.
    expect(screen.getByTestId("hydrate-live-l1-l2-prep")).toBeTruthy();
    expect(
      screen.getByTestId("hydrate-live-l1-checklist-link").getAttribute("href"),
    ).toMatch(/DUAL-GATE-L1-L4.*#l1-arxiv/);
    expect(
      screen.getByTestId("hydrate-live-l2-checklist-link").getAttribute("href"),
    ).toMatch(/DUAL-GATE-L1-L4.*#l2-substack/);
    const gateMatrix = screen.getByTestId("hydrate-live-l1-l2-gate-matrix");
    expect(gateMatrix.getAttribute("data-l1-arxiv-live-ready")).toBe("false");
    expect(gateMatrix.getAttribute("data-l2-substack-live-ready")).toBe(
      "false",
    );
    expect(gateMatrix.textContent).toMatch(/L1\/L2 gate matrix/i);
    expect(gateMatrix.textContent).toMatch(/arxiv_live=false/);
    expect(gateMatrix.textContent).toMatch(/substack_live=false/);
  });

  it("renders registered providers and budget bar", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getAllByText(/zai/).length).toBeGreaterThan(0);
    });
    // Residual (aec): /ready/i also matches twin L3 live_ready=false — use getAllByText.
    expect(screen.getAllByText(/ready/i).length).toBeGreaterThan(0);
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
    // Residual (wb): remaining-after empty when high band unknown (never invent).
    expect(mini.getAttribute("data-remaining-after-usd")).toBe("");
    // Residual (aej): goes-negative unknown when remaining-after cannot be computed.
    expect(mini.getAttribute("data-goes-negative")).toBe("unknown");
    expect(mini.textContent).toMatch(/Sample projection/i);
    expect(mini.textContent).toMatch(/never invents \$0/i);
  });

  it("stamps data-goes-negative on mini+full when high band burns past remaining (aej)", async () => {
    const user = userEvent.setup();
    estimatePromptCost.mockResolvedValueOnce({
      estimated_usd_low: 3,
      estimated_usd_high: 5,
      would_exceed_budget: true,
      pricing_known: true,
      notes: [],
      assumed_input_tokens: 500,
      assumed_output_tokens: 2500,
      tier: "pro",
      provider: "zai",
      model: "glm-5.2",
    });
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-project-cost")).toBeTruthy();
    });
    await user.click(screen.getByTestId("decision-tree-project-cost"));
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-mini-estimate")).toBeTruthy();
    });
    const mini = screen.getByTestId("decision-tree-mini-estimate");
    // remaining 4 − high 5 = −1
    expect(mini.getAttribute("data-remaining-after-usd")).toBe("-1");
    expect(mini.getAttribute("data-goes-negative")).toBe("true");
    expect(mini.getAttribute("data-would-exceed")).toBe("yes");
    expect(mini.textContent).toMatch(/over remaining \(soft foresight\)/i);
    await waitFor(() => {
      expect(screen.getByTestId("prompt-cost-remaining-after")).toBeTruthy();
    });
    const full = screen.getByTestId("prompt-cost-remaining-after");
    expect(full.getAttribute("data-remaining-after-usd")).toBe("-1");
    expect(full.getAttribute("data-goes-negative")).toBe("true");
    expect(full.textContent).toMatch(/over remaining \(soft foresight\)/i);
  });

  it("links competitive DR scorecard from prompt-cost projection panel (ake)", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("prompt-cost-projection-panel")).toBeTruthy();
    });
    const panel = screen.getByTestId("prompt-cost-projection-panel");
    expect(panel.getAttribute("data-soft-budget")).toBe("true");
    expect(panel.getAttribute("data-budget-before-fire")).toBe("true");
    expect(
      screen
        .getByTestId("prompt-cost-competitive-scorecard-link")
        .getAttribute("href"),
    ).toBe("#settings-competitive-dr-scorecard");
    expect(
      screen
        .getByTestId("prompt-cost-competitive-dr-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-competitive-deep-research-quality/);
    expect(
      screen.getByTestId("prompt-cost-decision-tree-link").getAttribute("href"),
    ).toBe("#decision-tree-panel");
  });

  it("surfaces remaining-after on mini + full projection when high known (wb)", async () => {
    const user = userEvent.setup();
    estimatePromptCost.mockResolvedValueOnce({
      estimated_usd_low: 0.08,
      estimated_usd_high: 0.12,
      would_exceed_budget: false,
      pricing_known: true,
      notes: [],
      assumed_input_tokens: 500,
      assumed_output_tokens: 500,
      tier: "pro",
      provider: "zai",
      model: "glm-5.2",
    });
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-project-cost")).toBeTruthy();
    });
    await user.click(screen.getByTestId("decision-tree-project-cost"));
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-mini-estimate")).toBeTruthy();
    });
    const mini = screen.getByTestId("decision-tree-mini-estimate");
    // remaining 4 − high 0.12 = 3.88
    expect(mini.getAttribute("data-remaining-after-usd")).toBe("3.88");
    expect(mini.getAttribute("data-would-exceed")).toBe("no");
    // Residual (aej): within remaining → goes-negative false.
    expect(mini.getAttribute("data-goes-negative")).toBe("false");
    expect(mini.textContent).toMatch(/remaining after≈\$3\.8800/);
    // Full projection panel shares estimate state after mini project.
    await waitFor(() => {
      expect(screen.getByTestId("prompt-cost-remaining-after")).toBeTruthy();
    });
    const full = screen.getByTestId("prompt-cost-remaining-after");
    expect(full.getAttribute("data-remaining-after-usd")).toBe("3.88");
    expect(full.getAttribute("data-goes-negative")).toBe("false");
    expect(full.textContent).toMatch(/Remaining after prompt/i);
    expect(full.textContent).toMatch(/\$3\.880000/);
    expect(
      screen
        .getByTestId("prompt-cost-estimate-result")
        .getAttribute("data-remaining-after-usd"),
    ).toBe("3.88");
  });

  it("deep-links decision-tree to weekly leaderboard (sq)", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-leaderboard-link")).toBeTruthy();
    });
    const link = screen.getByTestId("decision-tree-leaderboard-link");
    expect(link.getAttribute("href")).toBe("#antiek-bench-leaderboard");
    expect(screen.getByTestId("antiek-bench-leaderboard-panel").id).toBe(
      "antiek-bench-leaderboard",
    );
  });

  it("deep-links decision-tree to dogfood fixtures (sv)", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-dogfood-link")).toBeTruthy();
    });
    const link = screen.getByTestId("decision-tree-dogfood-link");
    expect(link.getAttribute("href")).toBe("#antiek-bench-dogfood");
    expect(screen.getByTestId("antiek-bench-dogfood-panel").id).toBe(
      "antiek-bench-dogfood",
    );
  });

  it("surfaces honest deferred map (not stale coming-later) (wc)", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("settings-deferred-honest")).toBeTruthy();
    });
    // Residual (aii): competitive DR quality scorecard — honest shipped vs deferred.
    const scorecard = screen.getByTestId("settings-competitive-dr-scorecard");
    expect(scorecard.getAttribute("data-view-format")).toBe("html");
    expect(scorecard.getAttribute("data-html-first")).toBe("true");
    expect(scorecard.getAttribute("data-propose-not-promote")).toBe("true");
    // Residual (apr): citation hop pipeline (api) + multi-stage pipeline (ape) honesty.
    const citationTrust = screen.getByTestId("competitive-dr-citation-trust");
    expect(citationTrust.getAttribute("data-status")).toBe("shipped");
    expect(citationTrust.textContent).toMatch(
      /citation hop pipeline completeness/i,
    );
    expect(citationTrust.textContent).toMatch(/insights.*questions.*sources/i);
    const stagePipe = screen.getByTestId("competitive-dr-stage-pipeline");
    expect(stagePipe.getAttribute("data-status")).toBe("shipped");
    expect(stagePipe.textContent).toMatch(
      /plan.*gather.*synthesize.*cite.*terminal/i,
    );
    expect(
      screen.getByTestId("competitive-dr-budget-before-fire").getAttribute("data-status"),
    ).toBe("shipped");
    // Residual (aok): multi-goal MO + domain-aware chase + ≥2 written analysis honesty.
    expect(
      screen
        .getByTestId("competitive-dr-multiagent-merge")
        .textContent,
    ).toMatch(/≥2|>=2/i);
    expect(
      screen
        .getByTestId("competitive-dr-midnight-oil-multigoal")
        .getAttribute("data-status"),
    ).toBe("shipped");
    expect(
      screen
        .getByTestId("competitive-dr-midnight-oil-multigoal")
        .textContent,
    ).toMatch(/multi-goal|templates|fan-out/i);
    expect(
      screen
        .getByTestId("competitive-dr-domain-aware-chase")
        .getAttribute("data-status"),
    ).toBe("shipped");
    expect(
      screen.getByTestId("competitive-dr-live-hydrate").getAttribute("data-status"),
    ).toBe("deferred");
    expect(
      screen.getByTestId("competitive-dr-nd-router").getAttribute("data-status"),
    ).toBe("never");
    // Residual (akf): L5 payment deferred row links FUTURE digital book port brief.
    expect(
      screen.getByTestId("competitive-dr-payment").getAttribute("data-status"),
    ).toBe("deferred");
    expect(
      screen
        .getByTestId("competitive-dr-payment-l5-future-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-l5-digital-book-seamless-port/);
    // Residual (aki): twin notes row FUTURE completeness matrix deep-link.
    expect(
      screen
        .getByTestId("competitive-dr-twin-notes-future-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-twin-note-taker-completeness-matrix/);
    // Residual (akh): deferred live rows deep-link dual-gate L1/L2/L4/L6 prep.
    expect(
      screen
        .getByTestId("competitive-dr-live-hydrate-l1-link")
        .getAttribute("href") || "",
    ).toMatch(/#l1-arxiv/);
    expect(
      screen
        .getByTestId("competitive-dr-live-hydrate-l2-link")
        .getAttribute("href") || "",
    ).toMatch(/#l2-substack/);
    expect(
      screen
        .getByTestId("competitive-dr-live-moil-l4-link")
        .getAttribute("href") || "",
    ).toMatch(/#l4-moil/);
    expect(
      screen
        .getByTestId("competitive-dr-live-council-l6-link")
        .getAttribute("href") || "",
    ).toMatch(/#l6-collective/);
    expect(
      screen
        .getByTestId("competitive-dr-live-council-l6-future-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-l6-live-multiagent-collective/);
    expect(
      screen
        .getByTestId("settings-competitive-dr-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-competitive-deep-research-quality/);
    const panel = screen.getByTestId("settings-deferred-honest");
    expect(panel.textContent).toMatch(/truly deferred|dual-gate/i);
    expect(screen.getByTestId("settings-deferred-shipped-spine").textContent).toMatch(
      /Shipped offline spine/i,
    );
    expect(screen.getByTestId("settings-deferred-shipped-spine").textContent).toMatch(
      /Midnight Oil/i,
    );
    // Stale backlog claims removed (Midnight Oil UI is offline-complete).
    expect(panel.textContent).not.toMatch(
      /Midnight oil: time \+ goals \+ price-ceiling approve UI/i,
    );
    expect(panel.textContent).not.toMatch(
      /Antiek-bench weekly model quality report \(UI polish\)/i,
    );
    expect(screen.getByTestId("settings-deferred-l5").getAttribute("data-deferred")).toBe(
      "l5-payment",
    );
    expect(screen.getByTestId("settings-deferred-l6").getAttribute("data-deferred")).toBe(
      "l6-collective",
    );
    expect(screen.getByTestId("settings-deferred-l7").getAttribute("data-deferred")).toBe(
      "l7-nd",
    );
    expect(screen.getByTestId("settings-deferred-l7").textContent).toMatch(
      /advisory only/i,
    );
    // Residual (wk): deferred map deep-links into dual-gate L5–L7 sections.
    expect(
      screen
        .getByTestId("settings-deferred-l5-checklist-link")
        .getAttribute("href"),
    ).toMatch(/#l5-payment/);
    expect(
      screen
        .getByTestId("settings-deferred-l6-checklist-link")
        .getAttribute("href"),
    ).toMatch(/#l6-collective/);
    expect(
      screen
        .getByTestId("settings-deferred-l7-checklist-link")
        .getAttribute("href"),
    ).toMatch(/#l7-notdiamond/);
    // Residual (ahz): FUTURE-AGENT L5/L6 executable briefs from deferred map.
    expect(
      screen
        .getByTestId("settings-deferred-l5-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-l5-digital-book-seamless-port/);
    expect(
      screen
        .getByTestId("settings-deferred-l6-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-l6-live-multiagent-collective/);
    // Residual (wo): Deferred L7 → in-app ND advisory panel (never-router).
    expect(
      screen
        .getByTestId("settings-deferred-l7-panel-link")
        .getAttribute("href"),
    ).toBe("#notdiamond-advisory");
    expect(
      screen.getByTestId("settings-deferred-l7-panel-link").textContent,
    ).toMatch(/ND advisory panel/i);
    // Residual (aia): twin completeness FUTURE-AGENT brief.
    expect(
      screen
        .getByTestId("settings-deferred-twin-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-twin-note-taker-completeness-matrix/);
  });

  it("surfaces dual-gate L1–L4 prep strip on decision-tree (sw)", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("settings-dual-gate-prep")).toBeTruthy();
    });
    const prep = screen.getByTestId("settings-dual-gate-prep");
    expect(prep.getAttribute("data-offline-default")).toBe("true");
    expect(prep.getAttribute("data-l7-notdiamond")).toBe("advisory_only");
    // Residual (vt): L5 payment rails deferred honesty.
    expect(prep.getAttribute("data-l5-payment-rails")).toBe("deferred");
    expect(
      screen.getByTestId("settings-dual-gate-l5-payment").getAttribute(
        "data-live-payment",
      ),
    ).toBe("false");
    expect(screen.getByTestId("settings-dual-gate-l5-payment").textContent).toMatch(
      /L5 payment deferred/i,
    );
    // Residual (vz): L6 live multi-agent deferred honesty (parity Collective vx).
    expect(prep.getAttribute("data-l6-live-multiagent")).toBe("deferred");
    expect(prep.getAttribute("data-offline-merge-unit")).toBe("true");
    expect(
      screen.getByTestId("settings-dual-gate-l6-collective").getAttribute(
        "data-l6-live-multiagent",
      ),
    ).toBe("deferred");
    expect(
      screen.getByTestId("settings-dual-gate-l6-collective").getAttribute(
        "data-offline-merge-unit",
      ),
    ).toBe("true");
    expect(
      screen.getByTestId("settings-dual-gate-l6-collective").textContent,
    ).toMatch(/L6 offline merge unit/i);
    expect(screen.getByTestId("settings-dual-gate-l1-l2-link").getAttribute("href")).toBe(
      "#hydrate-live-status",
    );
    // Residual (xh): L1 checklist section #l1-arxiv (parity reading hydrate).
    expect(
      screen
        .getByTestId("settings-dual-gate-l1-checklist-link")
        .getAttribute("href"),
    ).toMatch(/DUAL-GATE-L1-L4.*#l1-arxiv/);
    // Residual (xr): L2 checklist section #l2-substack.
    expect(
      screen
        .getByTestId("settings-dual-gate-l2-checklist-link")
        .getAttribute("href"),
    ).toMatch(/DUAL-GATE-L1-L4.*#l2-substack/);
    expect(screen.getByTestId("settings-dual-gate-l3-link").getAttribute("href")).toBe(
      "#twin-seed-live-status",
    );
    // Residual (xb): L3 checklist section #l3-twin (parity TwinNotes xa).
    expect(
      screen
        .getByTestId("settings-dual-gate-l3-checklist-link")
        .getAttribute("href"),
    ).toMatch(/DUAL-GATE-L1-L4.*#l3-twin/);
    expect(screen.getByTestId("settings-dual-gate-l4-link").getAttribute("href")).toBe(
      "#moil-live-step-status",
    );
    // Residual (wy): L4 checklist section #l4-moil (parity MO wx).
    expect(
      screen.getByTestId("settings-dual-gate-l4-checklist-link").getAttribute("href"),
    ).toMatch(/DUAL-GATE-L1-L4.*#l4-moil/);
    // Residual (wh): L5/L6/L7 checklist deep-links (complete operator map).
    expect(
      screen.getByTestId("settings-dual-gate-l5-payment").getAttribute("href"),
    ).toMatch(/DUAL-GATE-L1-L4.*#l5-payment/);
    expect(
      screen.getByTestId("settings-dual-gate-l6-collective").getAttribute("href"),
    ).toMatch(/DUAL-GATE-L1-L4.*#l6-collective/);
    expect(screen.getByTestId("settings-dual-gate-l7-link").getAttribute("href")).toBe(
      "#notdiamond-advisory",
    );
    expect(
      screen.getByTestId("settings-dual-gate-l7-checklist-link").getAttribute("href"),
    ).toMatch(/DUAL-GATE-L1-L4.*#l7-notdiamond/);
    // Residual (aip): competitive DR scorecard from decision-tree dual-gate prep.
    expect(
      screen
        .getByTestId("settings-dual-gate-competitive-scorecard-link")
        .getAttribute("href"),
    ).toBe("#settings-competitive-dr-scorecard");
  });

  it("surfaces offline-honest Midnight Oil live-step status (sz)", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(fetchMidnightOilLiveStepStatus).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByTestId("moil-live-step-status-panel")).toBeTruthy();
    });
    const panel = screen.getByTestId("moil-live-step-status-panel");
    expect(panel.id).toBe("moil-live-step-status");
    expect(panel.getAttribute("data-offline-honest")).toBe("true");
    expect(panel.getAttribute("data-injector-installed")).toBe("false");
    // Residual (aed): offline default is not L4 live ready.
    expect(panel.getAttribute("data-l4-live-ready")).toBe("false");
    const metrics = screen.getByTestId("moil-live-step-status-metrics");
    expect(metrics.getAttribute("data-offline-honest")).toBe("true");
    expect(metrics.getAttribute("data-live-env")).toBe("false");
    expect(metrics.getAttribute("data-l4-live-ready")).toBe("false");
    expect(metrics.getAttribute("data-l4-gates-live-env")).toBe("false");
    expect(metrics.getAttribute("data-l4-gates-injector")).toBe("false");
    expect(metrics.textContent).toMatch(/offline-honest stub steps/i);
    // Residual (aed): in-panel L4 checklist + gate matrix.
    expect(screen.getByTestId("moil-live-l4-prep")).toBeTruthy();
    expect(
      screen.getByTestId("moil-live-l4-checklist-link").getAttribute("href"),
    ).toMatch(/DUAL-GATE-L1-L4.*#l4-moil/);
    const gateMatrix = screen.getByTestId("moil-live-l4-gate-matrix");
    expect(gateMatrix.getAttribute("data-l4-live-ready")).toBe("false");
    expect(gateMatrix.textContent).toMatch(/L4 gate matrix/i);
    expect(gateMatrix.textContent).toMatch(/live_ready=false/);
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
    expect(metrics.getAttribute("data-write-seed-known-count")).toBe("19");
    expect(metrics.textContent).toMatch(/Write seed this week/i);
    expect(metrics.textContent).toMatch(/not auto-promoted/i);
    // Residual (sr): write-seed metrics deep-link suite proposal.
    const suiteLink = screen.getByTestId("antiek-bench-write-seed-suite-link");
    expect(suiteLink.getAttribute("href")).toBe("#antiek-bench-suite-proposal");
    expect(screen.getByTestId("antiek-bench-suite-proposal-panel").id).toBe(
      "antiek-bench-suite-proposal",
    );
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
    // Residual (aez): L7 gate matrix + prep (never-router posture).
    expect(screen.getByTestId("notdiamond-live-l7-prep").getAttribute("data-dual-gate")).toBe(
      "L7",
    );
    expect(
      screen.getByTestId("notdiamond-live-l7-checklist-link").getAttribute("href") || "",
    ).toMatch(/#l7-notdiamond/);
    // Residual (ahy): FUTURE-AGENT advisory-only brief deep-link.
    expect(
      screen
        .getByTestId("notdiamond-future-agent-advisory-spec-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-notdiamond-advisory-only/);
    const l7 = screen.getByTestId("notdiamond-live-l7-gate-matrix");
    expect(l7.getAttribute("data-l7-advisory-only")).toBe("true");
    expect(l7.getAttribute("data-l7-is-dispatch-authority")).toBe("false");
    expect(l7.getAttribute("data-l7-authority-rejected")).toBe("true");
    expect(l7.getAttribute("data-l7-advisory-allowed")).toBe("true");
    expect(l7.getAttribute("data-l7-never-router-posture")).toBe("true");
    expect(l7.textContent).toMatch(/L7 gate matrix/i);
    expect(
      screen
        .getByTestId("notdiamond-advisory-panel")
        .getAttribute("data-l7-never-router-posture"),
    ).toBe("true");
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
    // Residual (ade): ND advisory vs Antiek-bench weekly recommended (both advisory).
    await waitFor(() => {
      expect(screen.getByTestId("notdiamond-bench-delta")).toBeTruthy();
    });
    const benchDelta = screen.getByTestId("notdiamond-bench-delta");
    expect(benchDelta.getAttribute("data-advisory-only")).toBe("true");
    expect(benchDelta.getAttribute("data-is-dispatch-authority")).toBe("false");
    expect(benchDelta.getAttribute("data-delta-status")).toBe("diverge");
    expect(benchDelta.getAttribute("data-nd-suggested")).toBe("stub-strong");
    expect(benchDelta.getAttribute("data-bench-recommended")).toBe("strong-model");
    expect(screen.getByTestId("notdiamond-bench-recommended").textContent).toMatch(
      /strong-model/,
    );
    expect(screen.getByTestId("notdiamond-bench-nd-suggested").textContent).toMatch(
      /stub-strong/,
    );
    expect(screen.getByTestId("notdiamond-bench-delta-label").textContent).toMatch(
      /diverge/i,
    );
    expect(
      screen.getByTestId("notdiamond-bench-leaderboard-link").getAttribute("href"),
    ).toBe("#antiek-bench-leaderboard");
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
    // Residual (ajy): install control never grants ND dispatch authority.
    const installBtn = screen.getByTestId("notdiamond-install-advisory");
    expect(installBtn.getAttribute("data-never-dispatch-authority")).toBe(
      "true",
    );
    expect(installBtn.getAttribute("data-install-is-decision-tree-only")).toBe(
      "true",
    );
    expect(installBtn.getAttribute("data-notdiamond-authority")).toBe(
      "advisory_only",
    );
    expect(installBtn.getAttribute("data-is-dispatch-authority")).toBe(
      "false",
    );
    expect(
      screen
        .getByTestId("notdiamond-competitive-scorecard-link")
        .getAttribute("href"),
    ).toBe("#settings-competitive-dr-scorecard");
    await user.click(installBtn);
    await waitFor(() => {
      expect(installDecisionTreeSelection).toHaveBeenCalled();
    });
    const call = installDecisionTreeSelection.mock.calls.at(-1)?.[0] as {
      model_id: string;
      provider_id?: string;
    };
    expect(call.model_id).toBe("stub-strong");
    expect(call.provider_id).toBeTruthy();
    // Residual (aka): after ND install, decision-tree provenance stamps never-dispatch.
    await waitFor(() => {
      expect(
        screen.getByTestId("decision-tree-install-provenance"),
      ).toBeTruthy();
    });
    const prov = screen.getByTestId("decision-tree-install-provenance");
    expect(prov.getAttribute("data-install-source")).toBe("notdiamond");
    expect(prov.getAttribute("data-never-dispatch-authority")).toBe("true");
    expect(prov.getAttribute("data-install-is-decision-tree-only")).toBe(
      "true",
    );
    expect(prov.getAttribute("data-notdiamond-authority")).toBe(
      "advisory_only",
    );
    expect(prov.textContent).toMatch(/decision-tree only/i);
    expect(prov.textContent).toMatch(/never dispatch/i);
    const status = screen.getByTestId("decision-tree-status");
    expect(status.getAttribute("data-install-source")).toBe("notdiamond");
    expect(status.getAttribute("data-never-dispatch-authority")).toBe("true");
    expect(status.getAttribute("data-notdiamond-authority")).toBe(
      "advisory_only",
    );
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
    expect(writeSeedKnown).toBe(19);
    expect(screen.getByTestId("antiek-bench-write-seed-known-count").textContent).toMatch(
      /Write seed feeds/i,
    );
    expect(screen.getByTestId("antiek-bench-write-seed-known-count").textContent).toMatch(
      "19",
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
    // Residual (yj): Antiek-bench dual-gate → L7 ND never-router section.
    expect(dual.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4.*#l7-notdiamond/);
    expect(dual.textContent).toMatch(/L7 ND checklist/i);
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
      // Residual (acu): body honesty week.
      write_seed_with_body_count: 7,
      write_seed_title_only_count: 1,
      write_seed_body_unknown_count: 1,
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
    // Residual (acu): body honesty chrome for recursive rewrite quality.
    expect(metrics.getAttribute("data-write-seed-with-body-count")).toBe("7");
    expect(metrics.getAttribute("data-write-seed-title-only-count")).toBe("1");
    expect(metrics.getAttribute("data-write-seed-body-unknown-count")).toBe("1");
    expect(metrics.textContent).toMatch(/with_body=7/);
    expect(metrics.textContent).toMatch(/title_only=1/);
    expect(metrics.textContent).toMatch(/unknown=1/);
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
    // Residual (aoy): vision north-star feed coverage chrome.
    const vision = screen.getByTestId("antiek-bench-vision-feed-coverage");
    expect(vision.getAttribute("data-propose-not-promote")).toBe("true");
    expect(vision.getAttribute("data-view-format")).toBe("html");
    expect(Number(vision.getAttribute("data-total") || 0)).toBeGreaterThanOrEqual(
      6,
    );
    expect(vision.getAttribute("data-covered") || "").toMatch(/twin_chase/);
    expect(Number(vision.getAttribute("data-covered-count") || 0)).toBeGreaterThan(
      0,
    );
    expect(vision.textContent).toMatch(/Vision feed coverage/i);
    expect(vision.textContent).toMatch(/propose≠promote|propose=not promote|never invents/i);
    // Residual (apc): per-task training feed coverage under suite proposal.
    const train = screen.getByTestId("antiek-bench-task-training-coverage");
    expect(train.getAttribute("data-propose-not-promote")).toBe("true");
    const wrestleTrain = screen.getByTestId("antiek-bench-task-training-wrestle");
    expect(wrestleTrain.getAttribute("data-task-class")).toBe("wrestle");
    expect(Number(wrestleTrain.getAttribute("data-total") || 0)).toBe(3);
    expect(wrestleTrain.getAttribute("data-covered") || "").toMatch(/twin_chase/);
    expect(wrestleTrain.getAttribute("data-covered") || "").toMatch(
      /midnight_oil/,
    );
    expect(wrestleTrain.textContent).toMatch(/wrestle/i);
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
    // Residual (ht/acy): recursive rewrite metrics + title-only Write seed count.
    const metrics = screen.getByTestId("antiek-bench-suite-proposal-metrics");
    expect(metrics.getAttribute("data-has-proposal")).toBe("true");
    expect(metrics.getAttribute("data-status")).toBe("proposed");
    expect(metrics.getAttribute("data-proposal-id")).toBe("prop_testdeadbeef01");
    expect(metrics.getAttribute("data-event-count")).toBe("2");
    expect(metrics.getAttribute("data-proposed-task-count")).toBe("1");
    expect(metrics.getAttribute("data-auto-promoted")).toBe("false");
    expect(metrics.getAttribute("data-propose-not-promote")).toBe("true");
    expect(metrics.getAttribute("data-title-only-write-seed-count")).toBe("1");
    // Residual (adp): full body honesty matrix on suite proposal metrics.
    expect(metrics.getAttribute("data-with-body-write-seed-count")).toBe("2");
    expect(metrics.getAttribute("data-body-unknown-write-seed-count")).toBe(
      "0",
    );
    expect(metrics.textContent).toMatch(/Recursive rewrite/);
    expect(metrics.textContent).toMatch(/title_only_write_seeds=1/);
    expect(metrics.textContent).toMatch(/with_body=2/);
    expect(metrics.textContent).toMatch(/title_only=1/);
    expect(metrics.textContent).toMatch(/unknown=0/);
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
    // Residual (zf): panel-level propose≠promote honesty.
    const panel = screen.getByTestId("antiek-bench-dogfood-panel");
    expect(panel.getAttribute("data-view-format")).toBe("html");
    expect(panel.getAttribute("data-propose-not-promote")).toBe("true");
    expect(panel.getAttribute("data-auto-promoted")).toBe("false");
    expect(fetchAntiekBenchDogfoodFixtures).toHaveBeenCalled();
    await waitFor(() => {
      expect(
        screen.getByTestId("antiek-bench-dogfood-summary").textContent,
      ).toMatch(/suite-competitive-dogfood-v35/);
    });
    // Residual (zh/zm): panel suite version + label + item count after load.
    expect(panel.getAttribute("data-suite-version")).toBe(
      "suite-competitive-dogfood-v35",
    );
    expect(panel.getAttribute("data-label")).toBe(
      "antiek-bench-competitive-dogfood",
    );
    // Residual (zo/zq): panel source + settings_panel honesty after load.
    expect(panel.getAttribute("data-source")).toBe(
      "antiek_bench.dogfood_fixtures",
    );
    expect(panel.getAttribute("data-settings-panel")).toBe(
      "antiek_bench_dogfood_fixtures",
    );
    expect(panel.getAttribute("data-item-count")).toBe("53");
    // Residual (zs/zu): panel full task-class counts after load (parity summary).
    expect(panel.getAttribute("data-book-qa-count")).toBe("10");
    expect(panel.getAttribute("data-wrestle-count")).toBe("39");
    expect(panel.getAttribute("data-distill-count")).toBe("2");
    expect(panel.getAttribute("data-synthesize-count")).toBe("2");
    const summary = screen.getByTestId("antiek-bench-dogfood-summary");
    // Residual (su/…/adn/aeu/afo/ags/agw/ahd/anj): v34 spine posture machine attrs.
    expect(summary.getAttribute("data-suite-version")).toBe(
      "suite-competitive-dogfood-v35",
    );
    // Residual (yx): dogfood label honesty.
    expect(summary.getAttribute("data-label")).toBe(
      "antiek-bench-competitive-dogfood",
    );
    expect(summary.getAttribute("data-item-count")).toBe("53");
    expect(summary.getAttribute("data-auto-promoted")).toBe("false");
    // Residual (yt): HTML-first dogfood view_format honesty.
    expect(summary.getAttribute("data-view-format")).toBe("html");
    // Residual (yv): substrate source honesty.
    expect(summary.getAttribute("data-source")).toBe(
      "antiek_bench.dogfood_fixtures",
    );
    // Residual (yz): settings panel identity honesty.
    expect(summary.getAttribute("data-settings-panel")).toBe(
      "antiek_bench_dogfood_fixtures",
    );
    // Residual (yg/yh): full task-class counts on dogfood summary.
    expect(summary.getAttribute("data-book-qa-count")).toBe("10");
    expect(summary.getAttribute("data-wrestle-count")).toBe("39");
    expect(summary.getAttribute("data-distill-count")).toBe("2");
    expect(summary.getAttribute("data-synthesize-count")).toBe("2");
    expect(summary.getAttribute("data-has-write-seed-posture")).toBe("true");
    expect(summary.getAttribute("data-has-float-evidence-posture")).toBe(
      "true",
    );
    expect(summary.getAttribute("data-has-budget-foresight-posture")).toBe(
      "true",
    );
    expect(summary.getAttribute("data-has-faraday-book-qa-posture")).toBe(
      "true",
    );
    expect(
      summary.getAttribute("data-has-collective-unit-write-seed-posture"),
    ).toBe("true");
    expect(summary.getAttribute("data-has-boole-book-qa-posture")).toBe(
      "true",
    );
    expect(summary.getAttribute("data-has-heaviside-book-qa-posture")).toBe(
      "true",
    );
    expect(summary.getAttribute("data-has-shannon-book-qa-posture")).toBe(
      "true",
    );
    expect(summary.getAttribute("data-has-turing-book-qa-posture")).toBe(
      "true",
    );
    expect(summary.getAttribute("data-has-lovelace-book-qa-posture")).toBe(
      "true",
    );
    expect(summary.getAttribute("data-has-godel-book-qa-posture")).toBe(
      "true",
    );
    expect(
      summary.getAttribute("data-has-nicomachean-ethics-book-qa-posture"),
    ).toBe("true");
    expect(summary.getAttribute("data-has-fourier-book-qa-posture")).toBe(
      "true",
    );
    expect(
      summary.getAttribute("data-has-citation-trust-ungrounded-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute(
        "data-has-twin-cross-asset-merge-write-seed-posture",
      ),
    ).toBe("true");
    expect(
      summary.getAttribute(
        "data-has-collective-written-analysis-write-seed-posture",
      ),
    ).toBe("true");
    // Residual (ado/aeu/afo): v18 write-seed + multi-spawn path postures.
    expect(
      summary.getAttribute("data-has-write-seed-has-body-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-seamless-write-path-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-intelligent-search-context-write-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-written-analysis-open-write-source-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-continue-as-unit-path-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-select-open-path-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-unit-restore-path-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-select-recent-path-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-research-workstation-spine-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-highlight-deep-research-path-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-talk-to-book-twins-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-meta-reading-twins-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-research-this-twins-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-spawn-merge-path-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-collective-multi-spawn-merge-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-pub-quick-call-matrix-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-budget-foresight-pub-refs-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-purchase-seamless-port-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-domain-aware-twin-search-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-moil-deposit-twin-honesty-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-pub-ref-foresight-chrome-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-citation-chain-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-citation-chain-hops-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-domain-aware-stem-expanded-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-evidence-write-multi-hop-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-twin-promote-depth-graph-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-twin-promote-write-depth-graph-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-talk-to-book-collective-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-meta-reading-collective-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-marketplace-host-collective-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-competitive-dr-scorecard-posture"),
    ).toBe("true");
    expect(
      summary.getAttribute("data-has-collective-unit-twin-seed-posture"),
    ).toBe("true");
    expect(summary.getAttribute("data-propose-not-promote")).toBe("true");
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /Spine postures \(v35\)/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /multi-hop citation chain hops/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /domain-aware STEM expanded/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /evidence Write multi-hop/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /twin promote depth-graph/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /twin promote Write depth-graph/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /write-seed has-body/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /seamless Write path/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /intelligent search/i,
    );
    // Residual (aos): aoc–aor product postures in spine listing (propose≠promote).
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /domain-aware twin chase/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /MO multi-goal templates/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /multi-agent written analysis/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /Select open path/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /unit restore/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /write-seed/i,
    );
    // Residual (adw): has-body posture deep-links to suite rewrite + usage.
    const hasBodyLinks = screen.getByTestId(
      "antiek-bench-dogfood-has-body-links",
    );
    expect(hasBodyLinks.getAttribute("data-has-write-seed-has-body-posture")).toBe(
      "true",
    );
    expect(hasBodyLinks.getAttribute("data-propose-not-promote")).toBe("true");
    expect(
      screen
        .getByTestId("dogfood-has-body-suite-proposal-link")
        .getAttribute("href"),
    ).toBe("#antiek-bench-suite-proposal");
    expect(
      screen.getByTestId("dogfood-has-body-usage-link").getAttribute("href"),
    ).toBe("#antiek-bench-usage");
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /Faraday book_qa/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /collective unit write-seed/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /Boole book_qa/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /Shannon book_qa/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /Turing book_qa/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /Lovelace book_qa/i,
    );
    // Residual (we): full dogfood item list — no silent top-12 truncate.
    const itemsList = screen.getByTestId("antiek-bench-dogfood-items");
    expect(itemsList.getAttribute("data-truncated")).toBe("false");
    // Residual (yb/…/ais/anj): full v35 mock lists all 53 items — matches item_count.
    expect(itemsList.getAttribute("data-listed-count")).toBe("53");
    expect(itemsList.getAttribute("data-item-count")).toBe("53");
    expect(itemsList.getAttribute("data-item-count-matches-listed")).toBe(
      "true",
    );
    // Residual (zd): HTML-first list view_format honesty.
    expect(itemsList.getAttribute("data-view-format")).toBe("html");
    // Mock lists posture items including reading twins + Fourier (v21).
    expect(
      itemsList.querySelector('[data-item-id="dogfood-book-shannon-communication"]'),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-book-turing-computable-numbers"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-wrestle-seamless-write-path"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-wrestle-written-analysis-open-write-source"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-wrestle-continue-as-unit-path"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-wrestle-select-open-path"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-wrestle-unit-restore-path"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-wrestle-select-recent-path"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-wrestle-research-workstation-spine"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-wrestle-highlight-deep-research-path"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-wrestle-talk-to-book-twins"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-wrestle-meta-reading-twins"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-wrestle-research-this-twins"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-wrestle-spawn-merge-path"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-wrestle-collective-multi-spawn-merge"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-wrestle-pub-quick-call-matrix"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-wrestle-intelligent-search-context-write"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-wrestle-write-seed-has-body"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-book-lovelace-analytical-engine"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-book-godel-incompleteness"]',
      ),
    ).toBeTruthy();
    expect(
      itemsList.querySelector(
        '[data-item-id="dogfood-book-fourier-heat"]',
      ),
    ).toBeTruthy();
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /Heaviside book_qa/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /Fourier book_qa/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /ResearchThis twins/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /spawn merge path/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /multi-spawn collective merge/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /pub quick-call matrix/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /budget foresight/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /purchase seamless port/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /citation-trust ungrounded/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /twin cross-asset merge write-seed/i,
    );
    expect(screen.getByTestId("antiek-bench-dogfood-v2-postures").textContent).toMatch(
      /collective written analysis write-seed/i,
    );
    expect(
      screen
        .getByTestId("antiek-bench-dogfood-panel")
        .getAttribute("data-view-format"),
    ).toBe("html");
    expect(summary.textContent).toMatch(/Auto-promoted\s*false/i);
    expect(screen.getByTestId("antiek-bench-dogfood-html").innerHTML).toMatch(
      /items=9|dogfood|faraday/i,
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
    // Residual (adf): reciprocal ND vs bench delta on leaderboard panel.
    await waitFor(() => {
      expect(screen.getByTestId("leaderboard-nd-delta")).toBeTruthy();
    });
    const lbDelta = screen.getByTestId("leaderboard-nd-delta");
    expect(lbDelta.getAttribute("data-advisory-only")).toBe("true");
    expect(lbDelta.getAttribute("data-is-dispatch-authority")).toBe("false");
    expect(lbDelta.getAttribute("data-delta-status")).toBe("diverge");
    expect(lbDelta.getAttribute("data-bench-recommended")).toBe("strong-model");
    expect(lbDelta.getAttribute("data-nd-suggested")).toBe("stub-strong");
    expect(
      screen.getByTestId("leaderboard-nd-advisory-link").getAttribute("href"),
    ).toBe("#notdiamond-advisory");
    expect(screen.getByTestId("antiek-bench-leaderboard-html").innerHTML).toMatch(
      /Leaderboard|strong-model/i,
    );
    // Residual (adr): per-task best models + by_task_class on model rows.
    const byTask = screen.getByTestId("antiek-bench-leaderboard-by-task");
    expect(byTask.getAttribute("data-advisory-only")).toBe("true");
    expect(byTask.getAttribute("data-is-dispatch-authority")).toBe("false");
    expect(byTask.getAttribute("data-task-class-count")).toBe("4");
    const winners = screen.getByTestId("antiek-bench-leaderboard-task-winners");
    expect(
      winners.querySelector('[data-task-class="book_qa"]')?.getAttribute(
        "data-best-model-id",
      ),
    ).toBe("book-specialist");
    expect(
      winners.querySelector('[data-task-class="wrestle"]')?.getAttribute(
        "data-best-model-id",
      ),
    ).toBe("strong-model");
    expect(
      winners.querySelector('[data-task-class="distill"]')?.getAttribute(
        "data-best-model-id",
      ),
    ).toBe("strong-model");
    // Residual (apb): task winners stamp vision feeds that train each task_class.
    const wrestleRow = winners.querySelector('[data-task-class="wrestle"]');
    expect(wrestleRow?.getAttribute("data-vision-feeds") || "").toMatch(
      /twin_chase/,
    );
    expect(wrestleRow?.getAttribute("data-vision-feeds") || "").toMatch(
      /midnight_oil/,
    );
    expect(
      screen.getByTestId("antiek-bench-leaderboard-vision-feeds-wrestle")
        .textContent,
    ).toMatch(/trains from/i);
    expect(
      screen
        .getByTestId("antiek-bench-leaderboard-install-task-wrestle")
        .getAttribute("data-never-auto-route"),
    ).toBe("true");
    expect(
      screen
        .getByTestId("antiek-bench-leaderboard-install-task-wrestle")
        .getAttribute("data-vision-feeds") || "",
    ).toMatch(/twin_chase/);
    const models = screen.getByTestId("antiek-bench-leaderboard-models");
    const strong = models.querySelector('[data-model-id="strong-model"]');
    expect(strong?.getAttribute("data-by-task-class")).toMatch(/wrestle=0\.92/);
    expect(strong?.textContent).toMatch(/wrestle=0\.92/);
    expect(strong?.textContent).toMatch(/distill=0\.99/);
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

  it("installs best-by-task model as decision-tree driver (ads)", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => {
      expect(
        screen.getByTestId("antiek-bench-leaderboard-install-task-book_qa"),
      ).toBeTruthy();
    });
    const btn = screen.getByTestId(
      "antiek-bench-leaderboard-install-task-book_qa",
    );
    expect(btn.getAttribute("data-install-model-id")).toBe("book-specialist");
    expect(btn.getAttribute("data-install-task-class")).toBe("book_qa");
    expect(btn.getAttribute("data-advisory-only")).toBe("true");
    installDecisionTreeSelection.mockClear();
    await user.click(btn);
    await waitFor(() => {
      expect(installDecisionTreeSelection).toHaveBeenCalled();
    });
    const call = installDecisionTreeSelection.mock.calls.at(-1)?.[0] as {
      model_id: string;
      provider_id?: string;
    };
    expect(call.model_id).toBe("book-specialist");
    expect(call.provider_id).toBeTruthy();
    // Residual (adu): decision-tree status stamps install provenance.
    await waitFor(() => {
      const status = screen.getByTestId("decision-tree-status");
      expect(status.getAttribute("data-install-source")).toBe(
        "leaderboard_task",
      );
      expect(status.getAttribute("data-install-task-class")).toBe("book_qa");
    });
    const prov = screen.getByTestId("decision-tree-install-provenance");
    expect(prov.getAttribute("data-install-source")).toBe("leaderboard_task");
    expect(prov.getAttribute("data-install-task-class")).toBe("book_qa");
    expect(prov.textContent).toMatch(/best book_qa/i);
  });

  it("registers an operator model via Add model panel", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByTestId("add-model-panel")).toBeTruthy();
    });
    expect(fetchRegisteredModels).toHaveBeenCalled();
    // Residual (aqj): HTML-first + never-auto-route honesty on add-model path.
    const addPanel = screen.getByTestId("add-model-panel");
    expect(addPanel.getAttribute("data-view-format")).toBe("html");
    expect(addPanel.getAttribute("data-html-first")).toBe("true");
    expect(addPanel.getAttribute("data-never-auto-route")).toBe("true");
    expect(addPanel.getAttribute("data-notdiamond-authority")).toBe(
      "advisory_only",
    );
    const honesty = screen.getByTestId("add-model-honesty-nav");
    expect(honesty.getAttribute("data-never-auto-route")).toBe("true");
    expect(
      screen.getByTestId("add-model-decision-tree-link").getAttribute("href"),
    ).toBe("#decision-tree-panel");
    expect(
      screen
        .getByTestId("add-model-notdiamond-advisory-link")
        .getAttribute("href"),
    ).toBe("#notdiamond-advisory");
    expect(
      screen.getByTestId("add-model-antiek-bench-link").getAttribute("href"),
    ).toBe("#antiek-bench-leaderboard-panel");
    expect(
      screen.getByTestId("add-model-prompt-cost-link").getAttribute("href"),
    ).toBe("#prompt-cost-projection");
    expect(
      screen.getByTestId("add-model-never-router-hint").textContent,
    ).toMatch(/never auto-route/i);
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
  });
});
