import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MidnightOil from "./index";

const {
  createMidnightOilJob,
  approveMidnightOilCeiling,
  depositMidnightOilJob,
  runMidnightOilJob,
  getMidnightOilJob,
  fetchDecisionTreeSelection,
} = vi.hoisted(() => ({
  createMidnightOilJob: vi.fn(),
  approveMidnightOilCeiling: vi.fn(),
  depositMidnightOilJob: vi.fn(),
  runMidnightOilJob: vi.fn(),
  getMidnightOilJob: vi.fn(),
  fetchDecisionTreeSelection: vi.fn(),
}));

vi.mock("../../api/midnightOil", () => ({
  createMidnightOilJob,
  approveMidnightOilCeiling,
  depositMidnightOilJob,
  runMidnightOilJob,
  getMidnightOilJob,
}));

vi.mock("../../api/settings", () => ({
  fetchDecisionTreeSelection: (...args: unknown[]) =>
    fetchDecisionTreeSelection(...args),
}));

vi.mock("../../components/engagement/ResearchLaunchBudgetPanel", () => {
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
          goals={props.promptText.length}
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

const openWindow = vi.fn(() => "win:moil-deposit:draft_moil_asset_dep_abc");
vi.mock("../../components/windows/openWindow", () => ({
  openWindow: (...args: unknown[]) => openWindow(...args),
}));

describe("MidnightOil mode", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    createMidnightOilJob.mockReset();
    approveMidnightOilCeiling.mockReset();
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

  it("mounts budget projection panel before create (cs)", () => {
    render(<MidnightOil />);
    expect(screen.getByTestId("moil-budget-mount")).toBeTruthy();
    expect(screen.getByTestId("research-launch-budget-panel-stub")).toBeTruthy();
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

  it("creates job then approves at recommended ceiling", async () => {
    createMidnightOilJob.mockResolvedValue({
      job_id: "moil_test",
      goals: ["Map residual risks"],
      duration_minutes: 60,
      status: "awaiting_approval",
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
    expect(screen.getByTestId("moil-progress-summary").textContent).toMatch(
      /complete/,
    );
    expect(screen.getByTestId("deposit-html").innerHTML).toMatch(/Deposited HTML/);
    expect(
      screen.getByTestId("midnight-oil-mode").getAttribute("data-view-format"),
    ).toBe("html");

    // Residual (db): open deposit HTML in hosted window for reading flywheel.
    fireEvent.click(screen.getByTestId("moil-open-deposit-window"));
    expect(openWindow).toHaveBeenCalledWith(
      "hosted_html_document",
      expect.objectContaining({
        document_id: "draft_moil_asset_dep_abc",
        view_format: "html",
        source: "midnight_oil_deposit",
      }),
      expect.objectContaining({
        id: "win:moil-deposit:draft_moil_asset_dep_abc",
      }),
    );
    await waitFor(() => {
      expect(screen.getByTestId("moil-deposit-window-id").textContent).toMatch(
        /win:moil-deposit/,
      );
    });
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
    expect(screen.getByTestId("moil-run-notes").textContent).toMatch(
      /Offline worker|LIVE_STEP/i,
    );
    expect(screen.getByTestId("moil-deposit-result").textContent).toMatch(
      /twins=2/,
    );
  });
});
