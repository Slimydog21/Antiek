import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LiveCouncilPanel } from "./LiveCouncilPanel";

const preflight = vi.fn();
const approve = vi.fn();
const run = vi.fn();
const fetchResult = vi.fn();
const converge = vi.fn();
const fetchStatus = vi.fn();

vi.mock("../../api/engagement", () => ({
  preflightCollectiveCouncil: (...args: unknown[]) => preflight(...args),
  approveCollectiveCouncil: (...args: unknown[]) => approve(...args),
  runCollectiveCouncil: (...args: unknown[]) => run(...args),
  fetchCollectiveCouncilResult: (...args: unknown[]) => fetchResult(...args),
  convergeCollectiveCouncil: (...args: unknown[]) => converge(...args),
  fetchCollectiveCouncilStatus: (...args: unknown[]) => fetchStatus(...args),
}));

const frozenPlan = {
  plan_id: "cplan-1",
  collective_id: "col-1",
  shared_prompt: "What survives scrutiny?",
  members: [
    {
      spawn_id: "spn-1",
      investigation_id: "inv-1",
      parent_asset_id: "paper-1",
      role: "evidence-critic-1",
      model_id: "model/member",
      projected_max_cents: 100,
      evidence_sha256: "a".repeat(64),
      source_ref_ids: ["ref-1"],
      twin_note_ids: [],
    },
  ],
  synthesizer_model_id: "model/synth",
  synthesizer_projected_max_cents: 100,
  approved_ceiling_cents: 200,
  input_sha256: "b".repeat(64),
  state: "preflight" as const,
  approval_receipt_id: null,
};

describe("LiveCouncilPanel", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    preflight.mockResolvedValue(frozenPlan);
    approve.mockResolvedValue({
      ...frozenPlan,
      state: "approved",
      approval_receipt_id: "approval-1",
    });
    run.mockResolvedValue({ result_id: "result-1" });
    fetchResult.mockResolvedValue({
      result_id: "result-1",
      plan_id: "cplan-1",
      state: "complete",
      member_receipts: [
        {
          role: "evidence-critic-1",
          model_id: "model/member",
          projected_max_cents: 100,
          actual_cents: 61,
          state: "complete",
        },
      ],
      synthesizer_receipt: null,
      spent_cents: 61,
      held_cents: 0,
      html: "<article><h1>Reviewed synthesis</h1><script>window.pwned=true</script></article>",
      result_sha256: "c".repeat(64),
    });
    converge.mockResolvedValue({ action_id: "action-1", state: "complete" });
    fetchStatus.mockResolvedValue({
      view_format: "html",
      product_panel: "collective_council_status",
      substrate_available: true,
      executor_installed: true,
      ledger_installed: true,
      live_ready: true,
      offline_convergence_available: true,
      operator_gated: true,
      notes: [],
    });
  });

  it("requires configuration, immutable review, and approval before run", async () => {
    render(
      <LiveCouncilPanel
        selectedSpawnIds={["spn-1"]}
        collectiveId="col-1"
        parentAssetId="paper-1"
      />,
    );

    await screen.findByText(/Live paid execution ready/i);

    const freeze = screen.getByRole("button", { name: /Freeze council for review/i });
    expect((freeze as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("council-exact-ceiling").textContent).toContain("200¢");

    fireEvent.change(screen.getByTestId("council-shared-prompt"), {
      target: { value: "What survives scrutiny?" },
    });
    fireEvent.change(screen.getByTestId("council-member-model-0"), {
      target: { value: "model/member" },
    });
    fireEvent.change(screen.getByTestId("council-synth-model"), {
      target: { value: "model/synth" },
    });
    expect((freeze as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(freeze);

    await screen.findByTestId("council-review");
    expect(preflight).toHaveBeenCalledWith(
      expect.objectContaining({ approved_ceiling_cents: 200 }),
    );
    const approveButton = screen.getByRole("button", { name: /Approve exact ceiling/i });
    expect((approveButton as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(approveButton);

    const runButton = await screen.findByTestId("council-run");
    fireEvent.click(runButton);
    await screen.findByText(/spent 61¢/i);
    expect(run).toHaveBeenCalledWith("cplan-1", 1);
    expect(screen.getByTestId("council-html-result").textContent).toContain(
      "Reviewed synthesis",
    );
    expect(screen.getByTestId("council-html-result").querySelector("script")).toBeNull();

    fireEvent.click(
      screen.getByRole("button", { name: /Keep as offline cohesive unit/i }),
    );
    await waitFor(() => expect(converge).toHaveBeenCalledTimes(1));
    expect(converge).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: "offline_collective",
        expected_result_sha256: "c".repeat(64),
      }),
    );
    await screen.findByTestId("council-convergence-complete");
  });

  it("keeps paid execution locked when server authority is unavailable", async () => {
    fetchStatus.mockResolvedValueOnce({
      view_format: "html",
      product_panel: "collective_council_status",
      substrate_available: true,
      executor_installed: false,
      ledger_installed: false,
      live_ready: false,
      offline_convergence_available: true,
      operator_gated: true,
      notes: [],
    });
    approve.mockResolvedValueOnce({
      ...frozenPlan,
      state: "approved",
      approval_receipt_id: "approval-1",
    });
    render(<LiveCouncilPanel selectedSpawnIds={["spn-1"]} collectiveId="col-1" />);
    await screen.findByText(/currently unavailable/i);
    expect(screen.getByRole("link", { name: /Open council settings/i }).getAttribute("href")).toBe(
      "/settings#collective-live-council-status",
    );
    fireEvent.change(screen.getByTestId("council-shared-prompt"), { target: { value: "Question" } });
    fireEvent.change(screen.getByTestId("council-member-model-0"), { target: { value: "member" } });
    fireEvent.change(screen.getByTestId("council-synth-model"), { target: { value: "synth" } });
    fireEvent.click(screen.getByRole("button", { name: /Freeze council/i }));
    await screen.findByTestId("council-review");
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: /Approve exact ceiling/i }));
    const runButton = await screen.findByTestId("council-run");
    expect((runButton as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(runButton);
    expect(run).not.toHaveBeenCalled();
  });

  it("fails closed when readiness cannot be verified", async () => {
    fetchStatus.mockRejectedValueOnce(new Error("offline"));
    render(<LiveCouncilPanel selectedSpawnIds={["spn-1"]} />);
    await screen.findByText(/could not be verified/i);
    expect(screen.getByTestId("live-council-panel").getAttribute("data-live-ready")).toBe("false");
  });

  it("fails closed on a malformed contradictory readiness payload", async () => {
    fetchStatus.mockResolvedValueOnce({
      view_format: "html",
      product_panel: "collective_council_status",
      substrate_available: true,
      executor_installed: false,
      ledger_installed: false,
      live_ready: true,
      offline_convergence_available: true,
      operator_gated: true,
      notes: [],
    });
    render(<LiveCouncilPanel selectedSpawnIds={["spn-1"]} />);
    await screen.findByText(/could not be verified/i);
    expect(screen.getByTestId("live-council-panel").getAttribute("data-live-ready")).toBe("false");
  });

  it("resets reviewed authority when membership changes", async () => {
    const { rerender } = render(
      <LiveCouncilPanel selectedSpawnIds={["spn-1"]} collectiveId="col-1" />,
    );
    fireEvent.change(screen.getByTestId("council-shared-prompt"), {
      target: { value: "What survives scrutiny?" },
    });
    fireEvent.change(screen.getByTestId("council-member-model-0"), {
      target: { value: "model/member" },
    });
    fireEvent.change(screen.getByTestId("council-synth-model"), {
      target: { value: "model/synth" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Freeze council for review/i }));
    await screen.findByTestId("council-review");

    rerender(<LiveCouncilPanel selectedSpawnIds={["spn-2"]} collectiveId="col-2" />);
    await waitFor(() => expect(screen.queryByTestId("council-review")).toBeNull());
    expect(
      (screen.getByRole("button", {
        name: /Freeze council for review/i,
      }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("discards a stale preflight response after membership changes", async () => {
    let resolvePreflight: (value: typeof frozenPlan) => void = () => undefined;
    preflight.mockReturnValueOnce(new Promise((resolve) => { resolvePreflight = resolve; }));
    const { rerender } = render(
      <LiveCouncilPanel selectedSpawnIds={["spn-1"]} collectiveId="col-1" />,
    );
    fireEvent.change(screen.getByTestId("council-shared-prompt"), { target: { value: "Question" } });
    fireEvent.change(screen.getByTestId("council-member-model-0"), { target: { value: "member" } });
    fireEvent.change(screen.getByTestId("council-synth-model"), { target: { value: "synth" } });
    fireEvent.click(screen.getByRole("button", { name: /Freeze council/i }));
    rerender(<LiveCouncilPanel selectedSpawnIds={["spn-2"]} collectiveId="col-2" />);
    resolvePreflight(frozenPlan);
    await waitFor(() => expect(preflight).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId("council-review")).toBeNull();
  });

  it("discards a stale preflight rejection after membership changes", async () => {
    let rejectPreflight: (reason: Error) => void = () => undefined;
    preflight.mockReturnValueOnce(new Promise((_resolve, reject) => { rejectPreflight = reject; }));
    const { rerender } = render(<LiveCouncilPanel selectedSpawnIds={["spn-1"]} />);
    fireEvent.change(screen.getByTestId("council-shared-prompt"), { target: { value: "Question" } });
    fireEvent.change(screen.getByTestId("council-member-model-0"), { target: { value: "member" } });
    fireEvent.change(screen.getByTestId("council-synth-model"), { target: { value: "synth" } });
    fireEvent.click(screen.getByRole("button", { name: /Freeze council/i }));
    rerender(<LiveCouncilPanel selectedSpawnIds={["spn-2"]} />);
    rejectPreflight(new Error("stale failure"));
    await waitFor(() => expect(preflight).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert")).toBeNull();
    expect((screen.getByRole("button", { name: /Freeze council/i }) as HTMLButtonElement).disabled).toBe(true);
  });
});
