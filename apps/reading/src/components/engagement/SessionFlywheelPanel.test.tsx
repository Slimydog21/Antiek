import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionFlywheelPanel } from "./SessionFlywheelPanel";

const completeSessionFlywheel = vi.fn();
const openWindow = vi.fn(() => "win:flywheel:test");

vi.mock("../windows/openWindow", () => ({
  openWindow: (...args: unknown[]) => openWindow(...args),
}));

vi.mock("../../api/engagement", () => ({
  completeSessionFlywheel: (...args: unknown[]) =>
    completeSessionFlywheel(...args),
}));

vi.mock("./DecisionTreeDriverBadge", () => ({
  DecisionTreeDriverBadge: (props: {
    researchTier?: string | null;
  }) => (
    <div
      data-testid="decision-tree-driver-badge-stub"
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
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
        >
          budget len={props.promptText.length}
        </div>
      );
    },
  };
});

describe("SessionFlywheelPanel residual cl/ee", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    budgetProjection.wouldExceedBudget = false;
    completeSessionFlywheel.mockReset();
    openWindow.mockClear();
  });

  it("completes flywheel with twins and shows context pack", async () => {
    completeSessionFlywheel.mockResolvedValue({
      session_id: "fsess_1",
      spawn_id: "spn_1",
      status: "complete",
      context: {
        asset_id: "book-1",
        twin_units: [{ unit_id: "t1" }, { unit_id: "t2" }],
        source_references: [],
        twin_count: 2,
        ref_count: 0,
        research_tier: "wrestle",
      },
      view_format: "html",
      prompt_block: "# Research context pack\n",
      research_tier: "wrestle",
      usage_event: {
        task_class: "wrestle",
        outcome: "worked",
        source: "session_flywheel",
      },
    });

    const onCompleted = vi.fn();
    render(
      <SessionFlywheelPanel
        sessionId="fsess_1"
        defaultOutputText="Attention is content-addressable memory."
        onCompleted={onCompleted}
        researchTier="deep"
      />,
    );
    // Residual (lt): pre-complete badge uses prop (deep).
    expect(
      screen
        .getByTestId("session-flywheel-driver-badge-mount")
        .getAttribute("data-research-tier"),
    ).toBe("deep");
    fireEvent.click(screen.getByTestId("session-flywheel-complete"));
    await waitFor(() => {
      expect(completeSessionFlywheel).toHaveBeenCalledWith({
        session_id: "fsess_1",
        output_text: "Attention is content-addressable memory.",
        record_twins: true,
        include_twin_promote: true,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId("session-flywheel-result").textContent).toMatch(
        /complete/,
      );
    });
    expect(screen.getByTestId("session-flywheel-prompt-block").textContent).toMatch(
      /Research context/,
    );
    expect(
      screen.getByTestId("session-flywheel-panel").getAttribute("data-view-format"),
    ).toBe("html");
    // Residual (ee): parent notified so research context can remount.
    await waitFor(() => {
      expect(onCompleted).toHaveBeenCalled();
    });
    expect(onCompleted.mock.calls[0][0].view_format).toBe("html");
    expect(onCompleted.mock.calls[0][0].status).toBe("complete");
    // Residual (hj): machine-readable session flywheel metrics.
    const metrics = screen.getByTestId("session-flywheel-metrics");
    expect(metrics.getAttribute("data-status")).toBe("complete");
    expect(metrics.getAttribute("data-session-id")).toBe("fsess_1");
    expect(metrics.getAttribute("data-spawn-id")).toBe("spn_1");
    expect(metrics.getAttribute("data-twin-count")).toBe("2");
    expect(metrics.getAttribute("data-ref-count")).toBe("0");
    expect(metrics.getAttribute("data-record-twins")).toBe("true");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.textContent).toMatch(/Session flywheel/);
    // Residual (jt): research_tier + Antiek-bench task_class audit.
    expect(metrics.getAttribute("data-research-tier")).toBe("wrestle");
    expect(metrics.getAttribute("data-usage-task-class")).toBe("wrestle");
    expect(metrics.getAttribute("data-usage-outcome")).toBe("worked");
    expect(screen.getByTestId("session-flywheel-research-tier").textContent).toBe(
      "wrestle",
    );
    expect(
      screen.getByTestId("session-flywheel-usage-task-class").textContent,
    ).toMatch(/wrestle/);
    // Residual (kq): pack context.research_tier chrome.
    expect(metrics.getAttribute("data-context-research-tier")).toBe("wrestle");
    expect(
      screen
        .getByTestId("session-flywheel-result")
        .getAttribute("data-context-research-tier"),
    ).toBe("wrestle");
    expect(
      screen.getByTestId("session-flywheel-context-research-tier").textContent,
    ).toMatch(/wrestle/);
    // Residual (sn): float|full session complete HTML.
    fireEvent.click(screen.getByTestId("session-flywheel-open-float"));
    const floatCall = openWindow.mock.calls.at(-1) as [
      string,
      { source?: string; html?: string; view_format?: string },
      { mode?: string },
    ];
    expect(floatCall[0]).toBe("hosted_html_document");
    expect(floatCall[1].source).toBe("session_flywheel_complete");
    expect(floatCall[1].view_format).toBe("html");
    expect(floatCall[1].html).toMatch(/Session flywheel complete/);
    expect(floatCall[1].html).toMatch(/Attention is content-addressable/);
    expect(floatCall[2].mode).toBe("floating");
    fireEvent.click(screen.getByTestId("session-flywheel-open-full"));
    expect(
      (openWindow.mock.calls.at(-1) as [{}, {}, { mode?: string }])[2].mode,
    ).toBe("full");
    // Residual (re/aex): Open Write twin_seed after flywheel complete + path.
    const write = screen.getByTestId("session-flywheel-open-write");
    const href = write.getAttribute("href") || "";
    expect(href).toMatch(/^\/write\?twin_seed=antiek\.twin_write_seed\./);
    expect(href).not.toMatch(/html_draft=/);
    expect(write.getAttribute("data-has-twin-seed")).toBe("1");
    expect(write.getAttribute("data-status")).toBe("complete");
    // Residual (acs): output/prompt_block body → has-body true.
    expect(write.getAttribute("data-write-seed-has-body")).toBe("true");
    // Residual (aex): session flywheel → Write path honesty.
    expect(write.getAttribute("data-seamless-flywheel-write")).toBe("true");
    expect(
      write.getAttribute("data-session-id") ||
        write.getAttribute("data-spawn-id"),
    ).toBeTruthy();
    // Residual (lt): post-complete badge adopts session/pack effective tier.
    expect(
      screen
        .getByTestId("session-flywheel-driver-badge-mount")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
    expect(
      screen
        .getByTestId("decision-tree-driver-badge-stub")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
  });

  it("falls back to context.research_tier when session tier absent (kq)", async () => {
    completeSessionFlywheel.mockResolvedValue({
      session_id: "fsess_2",
      spawn_id: "spn_2",
      status: "complete",
      context: {
        asset_id: "book-2",
        twin_units: [],
        source_references: [],
        twin_count: 0,
        ref_count: 0,
        research_tier: "deep",
      },
      view_format: "html",
      prompt_block: "# pack\n",
      research_tier: null,
      usage_event: null,
    });
    render(
      <SessionFlywheelPanel
        sessionId="fsess_2"
        defaultOutputText="Fallback pack tier path."
      />,
    );
    fireEvent.click(screen.getByTestId("session-flywheel-complete"));
    await waitFor(() => {
      expect(screen.getByTestId("session-flywheel-research-tier").textContent).toBe(
        "deep",
      );
    });
    expect(
      screen.getByTestId("session-flywheel-metrics").getAttribute("data-research-tier"),
    ).toBe("deep");
    expect(
      screen
        .getByTestId("session-flywheel-metrics")
        .getAttribute("data-context-research-tier"),
    ).toBe("deep");
  });

  it("disables complete when output too short", () => {
    render(<SessionFlywheelPanel sessionId="fsess_1" defaultOutputText="ab" />);
    expect(
      (screen.getByTestId("session-flywheel-complete") as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("links to Settings for driver & budget (ii)", () => {
    render(<SessionFlywheelPanel sessionId="fsess_1" />);
    const link = screen.getByTestId("session-flywheel-settings-link");
    expect(link.getAttribute("href")).toBe("/settings#decision-tree-panel");
    expect(link.textContent).toMatch(/driver & budget/i);
  });

  it("links dual-gate L1–L4 checklist (np)", () => {
    render(<SessionFlywheelPanel sessionId="fsess_1" />);
    const dual = screen.getByTestId("session-flywheel-dual-gate-checklist-link");
    // Residual (yc): session land → bench feed prep → L1 hydrate checklist section.
    expect(dual.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4.*#l1-arxiv/);
    expect(dual.textContent).toMatch(/L1 arxiv checklist/i);
    // Residual (aas): L2 Substack checklist (parity aal–aaq).
    const dualL2 = screen.getByTestId("session-flywheel-dual-gate-l2-link");
    expect(dualL2.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4.*#l2-substack/);
    expect(dualL2.textContent).toMatch(/L2 Substack checklist/i);
  });

  it("links competitive DR scorecard and FUTURE brief (ajd)", () => {
    render(<SessionFlywheelPanel sessionId="fsess_1" />);
    expect(
      screen
        .getByTestId("session-flywheel-competitive-scorecard-link")
        .getAttribute("href"),
    ).toBe("/settings#settings-competitive-dr-scorecard");
    expect(
      screen
        .getByTestId("session-flywheel-competitive-dr-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-competitive-deep-research-quality/);
    // Residual (apy): hop/stage pipeline honesty on session land.
    const pipeHint = screen.getByTestId(
      "session-flywheel-competitive-pipeline-hint",
    );
    expect(pipeHint.getAttribute("data-hop-pipeline")).toBe("api");
    expect(pipeHint.getAttribute("data-stage-pipeline")).toBe("ape");
    expect(pipeHint.textContent).toMatch(/insights.*questions.*sources/i);
  });

  it("links Settings prompt-cost projection for budget-before-fire (ako)", () => {
    render(<SessionFlywheelPanel sessionId="fsess_1" />);
    const link = screen.getByTestId(
      "session-flywheel-prompt-cost-projection-link",
    );
    expect(link.getAttribute("href")).toBe("/settings#prompt-cost-projection");
    expect(link.textContent).toMatch(/prompt-cost projection/i);
  });

  it("soft-gates complete flywheel on budget projection (ant)", async () => {
    budgetProjection.wouldExceedBudget = true;
    completeSessionFlywheel.mockResolvedValue({
      session_id: "fsess_over",
      spawn_id: "spn_over",
      status: "complete",
      view_format: "html",
      context: { twin_count: 0, ref_count: 0 },
    });
    render(
      <SessionFlywheelPanel
        sessionId="fsess_over"
        defaultOutputText="Substantial session synthesis for budget gate."
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("session-flywheel-budget-mount")).toBeTruthy();
    });
    expect(
      screen
        .getByTestId("session-flywheel-budget-mount")
        .getAttribute("data-budget-soft-gate"),
    ).toBe("true");
    await waitFor(() => {
      expect(screen.getByTestId("session-flywheel-over-budget-warn")).toBeTruthy();
    });
    const btn = screen.getByTestId(
      "session-flywheel-complete",
    ) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.getAttribute("data-budget-soft-gate")).toBe("true");
    fireEvent.click(btn);
    expect(completeSessionFlywheel).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("session-flywheel-force-over-budget"));
    await waitFor(() => {
      expect(
        (screen.getByTestId("session-flywheel-complete") as HTMLButtonElement)
          .disabled,
      ).toBe(false);
    });
    fireEvent.click(screen.getByTestId("session-flywheel-complete"));
    await waitFor(() => {
      expect(completeSessionFlywheel).toHaveBeenCalled();
    });
  });
});
