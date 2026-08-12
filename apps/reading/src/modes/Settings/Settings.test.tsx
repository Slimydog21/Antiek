import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  approveFallbackReceipt,
  fetchFallbackReceiptHistory,
  fetchModelDecision,
  type ModelDecisionResponse,
} from "../../api/settings";
import { fetchComposerProjection } from "../../api/composerProjection";
import { fetchSettingsUsage } from "../../api/settingsUsage";
import { fetchUserModels } from "../../api/settingsModels";
import Settings from "./index";

vi.mock("../../workspace/useViewportTier", () => ({
  useViewportTier: () => "desktop",
}));

const models = {
  models: [
    {
      provider_id: "zai",
      registered: true,
      ready: true,
      tier_bindings: ["flash", "pro"],
      primary_model: "glm-5.2",
      notes: null,
    },
    {
      provider_id: "user-custom",
      registered: true,
      ready: false,
      tier_bindings: [],
      primary_model: null,
      notes: "registered, but not bound to an active dispatch tier",
    },
  ],
  count: 2,
  providers_ready: true,
  source: "test",
};

const budget = {
  daily_cap_usd: 5,
  spent_usd: 1,
  remaining_usd: 4,
  spent_status: "known" as const,
  cap_env: null,
  reserved_estimated_usd: 1,
  spend_basis: "reserved_estimate" as const,
  enforcement_cap_usd: 5,
  enforcement_cap_env: null,
  caps_aligned: true,
  over_budget: false,
  over_budget_usd: 0,
  notes: ["test note"],
};

const usageSnapshot = {
  keys: [
    {
      api_key_id: "user-custom",
      used_cents: 120,
      limit_cents: 1000,
      remaining_cents: 880,
      held_cents: 40,
      available_cents: 840,
    },
  ],
  count: 1,
};

const userModelInventory = {
  models: [
    {
      id: "user-custom",
      provider_kind: "openai_compat" as const,
      provider_catalog_id: "deepseek",
      model_id: "deepseek-chat",
      display_name: "User key",
      base_url: "https://api.deepseek.com",
      enabled: true,
      key_present: true,
      registered: true,
      route_eligible: true,
      pricing_status: "known" as const,
      hard_ceiling_eligible: false,
      execution_status: "blocked_idempotency_unproven" as const,
      rate_snapshot: "deepseek-v4",
    },
  ],
  count: 1,
  stale_registered: [],
  source: "test",
};

vi.mock("../../api/settings", () => ({
  fetchSettingsModels: vi.fn(async () => models),
  fetchSettingsBudget: vi.fn(async () => budget),
  fetchFallbackReceiptHistory: vi.fn(async () => ({
    authority: "read_only_fallback_receipt_history",
    next_cursor: null,
    items: [],
  })),
  approveFallbackReceipt: vi.fn(),
  fetchModelDecision: vi.fn(async () => ({
    authority: "advisory",
    task: "deep_research",
    recommended_tier: "pro",
    benchmark_status: "measured",
    benchmark_generated_at: "2026-07-13T00:00:00Z",
    notes: ["server-owned evidence"],
    candidates: [
      {
        rank: 1,
        tier: "pro",
        provider: "zai",
        model: "glm-5.2",
        ready: true,
        eligible: true,
        quality_score: 0.91,
        quality_basis: "measured",
        benchmark_samples: 40,
        estimated_usd_low: 0.01,
        estimated_usd_high: 0.02,
        would_exceed_budget: false,
      },
    ],
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
}));

vi.mock("../../api/settingsUsage", () => ({
  fetchSettingsUsage: vi.fn(async () => ({ keys: [], count: 0 })),
  fetchSettingsBalance: vi.fn(async () => ({
    api_key_id: "user-custom",
    catalog_id: "deepseek",
    kind: "balance_native",
    balance_usd: 42.5,
    granted_usd: 100,
    spend_usd: 57.5,
    budget_usd: null,
    utilization: null,
    window_label: null,
    resets_at: null,
    note: null,
    held_cents: 40,
    available_cents: 840,
  })),
  setSettingsUsageLimit: vi.fn(),
}));

vi.mock("../../api/settingsModels", () => ({
  fetchUserModels: vi.fn(async () => ({
    models: [],
    count: 0,
    stale_registered: [],
    source: "test",
  })),
  fetchSettingsModelCatalog: vi.fn(async () => ({ providers: [], count: 0 })),
  addUserModel: vi.fn(),
  removeUserModel: vi.fn(),
}));

const composerProjection = {
  task: "deep_research" as const,
  recommended_tier: "pro",
  ranked_candidates: [
    {
      rank: 1,
      tier: "pro",
      provider: "zai",
      model: "glm-5.2",
      quality_score: 0.91,
      quality_basis: "measured" as const,
      eligible: true,
      pricing_status: "unknown" as const,
      estimated_usd_low: null,
      estimated_usd_high: null,
    },
  ],
  budget: { daily_cap_usd: 5, spent_usd: 1 },
  remaining_usd: 4,
  chosen_provider: null,
  chosen_model: null,
  chosen_projection: null,
  would_exceed_budget: null,
  pricing_status: "unknown" as const,
  authority: "advisory_explanatory",
  notes: ["curated default"],
  fallback_plan: {
    authority: "advisory_fallback_plan" as const,
    tier: "pro",
    status: "blocked" as const,
    maximum_chain_exposure_cents: null,
    would_exceed_budget: null,
    routes: [
      {
        fallback_index: 0,
        provider: "zai",
        model: "glm-5.2",
        registered: true,
        projection: {
          maximum_cost_usd: "0",
          reservation_cents: 0,
          disposition: "ineligible" as const,
          ineligibility: "unknown_pricing",
          rate_snapshot: "unverified-v1",
        },
        hard_ceiling_eligible: false,
        execution_status: "blocked_selection_authority",
      },
      {
        fallback_index: 1,
        provider: "deepseek",
        model: "deepseek-v4-pro",
        registered: true,
        projection: {
          maximum_cost_usd: "0",
          reservation_cents: 0,
          disposition: "ineligible" as const,
          ineligibility: "unknown_pricing",
          rate_snapshot: "unverified-v1",
        },
        hard_ceiling_eligible: false,
        execution_status: "blocked_selection_authority",
      },
    ],
  },
};

vi.mock("../../api/composerProjection", () => ({
  fetchComposerProjection: vi.fn(async () => composerProjection),
}));

describe("Settings SPR-01", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchSettingsUsage).mockResolvedValue(usageSnapshot);
    vi.mocked(fetchUserModels).mockResolvedValue(userModelInventory);
  });

  afterEach(cleanup);

  it("renders registered providers and budget bar", async () => {
    render(<Settings />);
    await waitFor(() => {
      expect(screen.getByText("zai")).toBeTruthy();
    });
    expect(screen.getByText(/ready/i)).toBeTruthy();
    expect(screen.getAllByText("registered").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$5.00")).toHaveLength(2);
    expect(screen.getByText("$1.0000")).toBeTruthy();
    expect(screen.getByText("Reserved estimate today")).toBeTruthy();
    expect(screen.getByText("Usage & balances (BYOT)")).toBeTruthy();
    expect(screen.queryByText("Spent today")).toBeNull();
  });

  it("projects cost and shows honest unknown pricing", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await waitFor(() => expect(screen.getByText("zai")).toBeTruthy());
    const buttons = screen.getAllByRole("button");
    const project = buttons.find((b) =>
      /project cost/i.test(b.textContent ?? ""),
    );
    expect(project).toBeTruthy();
    await user.click(project!);
    await waitFor(() => {
      expect(
        screen.getByText(/tier pricing is 0\.0 placeholder/i),
      ).toBeTruthy();
    });
  });

  it("compares server-owned model candidates in the decision tree tab", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.click(screen.getByRole("button", { name: "Compare models" }));
    expect(await screen.findByText(/Recommended tier:/)).toBeTruthy();
    expect(screen.getByText("pro", { selector: "strong" })).toBeTruthy();
    expect(screen.getByText("glm-5.2")).toBeTruthy();
    expect(screen.getByText("Measured evidence")).toBeTruthy();
    expect(screen.getByText("n=40")).toBeTruthy();
    expect(screen.getByTestId("fallback-route-0").textContent).toContain(
      "zai/glm-5.2",
    );
    expect(screen.getByTestId("fallback-route-1").textContent).toContain(
      "deepseek/deepseek-v4-pro",
    );
    expect(screen.getByTestId("fallback-plan-exposure").textContent).toBe(
      "execution blocked",
    );
    expect(fetchComposerProjection).toHaveBeenCalledWith({
      task: "deep_research",
      bounded_usage: [
        { unit: "input_token", maximum: 500 },
        { unit: "output_token", maximum: 500 },
      ],
      seam_id: "user.prompt.generate",
      operation: "generate",
    });
  });

  it("shows selected-provider usage chip when the chosen provider key is available", async () => {
    vi.mocked(fetchComposerProjection).mockResolvedValueOnce({
      ...composerProjection,
      ranked_candidates: [
        {
          rank: 1,
          tier: "pro",
          provider: "user-custom",
          model: "deepseek-chat",
          quality_score: 0.88,
          quality_basis: "measured",
          eligible: true,
          pricing_status: "known",
          estimated_usd_low: 0.01,
          estimated_usd_high: 0.02,
        },
      ],
      chosen_provider: "user-custom",
      chosen_model: "deepseek-chat",
      pricing_status: "known",
    });
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.click(screen.getByRole("button", { name: "Compare models" }));
    expect((await screen.findByTestId("selected-provider-balance")).textContent).toContain(
      "key remaining $8.80",
    );
  });

  it("renders durable fallback receipts independently from model comparison", async () => {
    vi.mocked(fetchFallbackReceiptHistory).mockResolvedValueOnce({
      authority: "read_only_fallback_receipt_history",
      next_cursor: null,
      items: [{
        chain_id: "chain-1",
        manifest_sha256: "a".repeat(64),
        outcome: "settled",
        created_at: "2026-07-16T10:00:00Z",
        currency: "USD",
        ceiling_cents: 20,
        maximum_chain_exposure_cents: 20,
        approval_eligible: false,
        approval_id: `fallback-approval:${"d".repeat(64)}`,
        approved_at: "2026-07-16T09:59:00Z",
        routes: [{
          fallback_index: 0,
          provider: "zai",
          model: "glm-5.2",
          seam_id: "user.prompt.generate",
          operation: "generate",
          projected_max_cents: 20,
          state: "settled",
          actual_cents: 12,
          resolved_at: "2026-07-16T10:01:00Z",
          settlement_evidence_sha256: "b".repeat(64),
          settlement_intent_sha256: "c".repeat(64),
        }],
      }],
    });
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    expect(await screen.findByText("Recent fallback executions")).toBeTruthy();
    expect(await screen.findByText("glm-5.2")).toBeTruthy();
    expect(screen.getByText(/actual \$0\.12/)).toBeTruthy();
    expect(screen.getByText("Receipt bbbbbbbbbb")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /execute|retry|run/i })).toBeNull();
  });

  it("reviews and approves one exact unattempted fallback chain", async () => {
    const chain = {
      chain_id: "chain-ready", manifest_sha256: "a".repeat(64), outcome: "unattempted" as const,
      created_at: "2026-07-16T10:00:00Z", currency: "USD" as const, ceiling_cents: 200,
      maximum_chain_exposure_cents: 75, approval_eligible: true, approval_id: null, approved_at: null,
      routes: [{ fallback_index: 0, provider: "zai", model: "glm-5.2", seam_id: "user.prompt.generate", operation: "generate", projected_max_cents: 75, state: "unattempted" as const, actual_cents: null, resolved_at: null, settlement_evidence_sha256: null, settlement_intent_sha256: null }],
    };
    vi.mocked(fetchFallbackReceiptHistory).mockResolvedValueOnce({ authority: "read_only_fallback_receipt_history", next_cursor: null, items: [chain] });
    vi.mocked(approveFallbackReceipt).mockResolvedValueOnce({ authority: "durable_fallback_spend_approval", approval_id: `fallback-approval:${"e".repeat(64)}`, chain_id: chain.chain_id, manifest_sha256: chain.manifest_sha256, currency: "USD", ceiling_cents: 200, maximum_chain_exposure_cents: 75, approved_at: "2026-07-16T10:01:00Z" });
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.click(await screen.findByRole("button", { name: "Review approval" }));
    expect(document.activeElement).toBe(screen.getByRole("region", { name: "Fallback approval review" }));
    expect(screen.getByText(chain.chain_id)).toBeTruthy();
    expect(screen.getByText(chain.manifest_sha256)).toBeTruthy();
    expect(screen.getByText(/Hard ceiling \$2\.00/)).toBeTruthy();
    expect(screen.getByText(/maximum sequential exposure \$0\.75/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Approve exact terms" }));
    await waitFor(() => expect(approveFallbackReceipt).toHaveBeenCalledWith(chain));
    const approved = await screen.findByText(/Approved/);
    expect(document.activeElement).toBe(approved);
    expect(screen.queryByRole("button", { name: "Review approval" })).toBeNull();
    expect(screen.queryByRole("button", { name: /execute|dispatch|retry|run/i })).toBeNull();
  });

  it("deduplicates pending approval and retains exact terms after failure", async () => {
    const chain = {
      chain_id: "chain-fail", manifest_sha256: "f".repeat(64), outcome: "unattempted" as const,
      created_at: "2026-07-16T10:00:00Z", currency: "USD" as const, ceiling_cents: 100,
      maximum_chain_exposure_cents: 40, approval_eligible: true, approval_id: null, approved_at: null,
      routes: [{ fallback_index: 0, provider: "zai", model: "glm-5.2", seam_id: "user.prompt.generate", operation: "generate", projected_max_cents: 40, state: "unattempted" as const, actual_cents: null, resolved_at: null, settlement_evidence_sha256: null, settlement_intent_sha256: null }],
    };
    vi.mocked(fetchFallbackReceiptHistory).mockResolvedValueOnce({ authority: "read_only_fallback_receipt_history", next_cursor: null, items: [chain] });
    let rejectApproval!: (reason: Error) => void;
    vi.mocked(approveFallbackReceipt).mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectApproval = reject; }));
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.click(await screen.findByRole("button", { name: "Review approval" }));
    await user.click(screen.getByRole("button", { name: "Approve exact terms" }));
    expect(screen.getByRole("button", { name: "Approving..." }).hasAttribute("disabled")).toBe(true);
    expect(approveFallbackReceipt).toHaveBeenCalledTimes(1);
    rejectApproval(new Error("approval terms changed"));
    expect((await screen.findByRole("alert")).textContent).toContain("approval terms changed");
    expect(screen.getByText(/Hard ceiling \$1\.00/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Approve exact terms" })).toBeTruthy();
  });

  it("preserves decision controls when receipt history is unavailable", async () => {
    vi.mocked(fetchFallbackReceiptHistory).mockRejectedValueOnce(new Error("down"));
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    expect(await screen.findByText("Execution receipts are unavailable.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Compare models" })).toBeTruthy();
  });

  it("preserves model comparison when the supplemental fallback preview fails", async () => {
    vi.mocked(fetchComposerProjection).mockRejectedValueOnce(
      new Error("preview down"),
    );
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.click(screen.getByRole("button", { name: "Compare models" }));
    expect(await screen.findByText(/Recommended tier:/)).toBeTruthy();
    expect(screen.getByText("glm-5.2")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain(
      "Fallback projection is unavailable",
    );
    expect(screen.queryByTestId("fallback-plan")).toBeNull();
  });

  it("clears prior authority when a comparison refresh fails", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.click(screen.getByRole("button", { name: "Compare models" }));
    expect(await screen.findByTestId("fallback-plan")).toBeTruthy();

    vi.mocked(fetchModelDecision).mockRejectedValueOnce(new Error("refresh failed"));
    await user.click(screen.getByRole("button", { name: "Compare models" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "refresh failed",
    );
    expect(screen.queryByTestId("fallback-plan")).toBeNull();
    expect(screen.queryByText(/Recommended tier:/)).toBeNull();
  });

  it("clears prior authority when a model selection fails", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.click(screen.getByRole("button", { name: "Compare models" }));
    expect(await screen.findByTestId("fallback-plan")).toBeTruthy();

    vi.mocked(fetchComposerProjection).mockRejectedValueOnce(
      new Error("selection failed"),
    );
    await user.selectOptions(screen.getByLabelText("model choice"), "0");
    expect((await screen.findByRole("alert")).textContent).toContain(
      "selection failed",
    );
    expect(screen.queryByTestId("fallback-plan")).toBeNull();
  });

  it("does not submit an invalid zero-usage comparison", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.clear(screen.getByLabelText("Input characters"));
    expect(
      (screen.getByRole("button", { name: "Compare models" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(fetchModelDecision).not.toHaveBeenCalled();
    expect(fetchComposerProjection).not.toHaveBeenCalled();
  });

  it("links tabs to panels and supports arrow-key navigation", async () => {
    const user = userEvent.setup();
    render(<Settings />);
    const overview = screen.getByRole("tab", { name: "Overview" });
    const decision = screen.getByRole("tab", { name: "Decision tree" });
    expect(overview.getAttribute("aria-controls")).toBe(
      "settings-overview-panel",
    );
    overview.focus();
    await user.keyboard("{ArrowRight}");
    expect(decision.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(decision);
    const panel = screen.getByRole("tabpanel");
    expect(panel.getAttribute("aria-labelledby")).toBe("settings-decision-tab");
  });

  it("does not render an in-flight result after the task changes", async () => {
    let resolveDecision: ((value: ModelDecisionResponse) => void) | undefined;
    vi.mocked(fetchModelDecision).mockImplementationOnce(
      () =>
        new Promise<ModelDecisionResponse>((resolve) => {
          resolveDecision = resolve;
        }),
    );
    const user = userEvent.setup();
    render(<Settings />);
    await user.click(screen.getByRole("tab", { name: "Decision tree" }));
    await user.click(screen.getByRole("button", { name: "Compare models" }));
    await user.selectOptions(screen.getByLabelText("Task"), "writing");
    resolveDecision?.({
      authority: "advisory",
      task: "deep_research",
      recommended_tier: "pro",
      benchmark_status: "unavailable",
      benchmark_generated_at: null,
      notes: [],
      candidates: [],
    });
    await waitFor(() =>
      expect(screen.queryByText(/Recommended tier:/)).toBeNull(),
    );
  });
});
