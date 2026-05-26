/**
 * ThinkingStream.test.tsx — the glass-box surface (SPR-02 M2/M3/M4).
 *
 * Pins the contract the sprint's gates name:
 *   - the DEFAULT live view is narrated lines, not raw PhaseRow dumps (M2);
 *   - connecting / reconnecting states are visible, never a frozen feed (M2);
 *   - the raw event log is one explicit toggle away (M2 escape hatch);
 *   - reconnect idempotency: a re-delivered event narrates exactly once (M2 gate);
 *   - the no-key / failed case shows the honest failure surface, never a
 *     perpetual "thinking…" (M4);
 *   - the live cost is the real accumulated dollar figure (M3).
 *
 * The render pulls in Werner (PNG poses) + LemonCard via TrajectoryView; vite
 * resolves the asset imports to URL strings under jsdom, so no asset mock is
 * needed.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import type { Event } from "../../generated/types";
import type { InvestigationState } from "../../hooks/useInvestigation";
import ThinkingStream from "./ThinkingStream";

afterEach(() => cleanup());

function ev(
  id: string,
  actionType: string,
  payload: Record<string, unknown> = {},
  at = "2026-05-26T00:00:00Z",
): Event {
  return {
    event_id: id,
    investigation_id: "inv-test",
    action_type: actionType as Event["action_type"],
    payload: payload as unknown as Event["payload"],
    param_version: "v1",
    emitted_at: at,
  };
}

function state(overrides: Partial<InvestigationState>): InvestigationState {
  return {
    id: "inv-test",
    status: "in_progress",
    question: "What is the strongest counter-thesis?",
    events: [],
    terminalPayload: null,
    costTotal: 0,
    completedAt: null,
    streamStatus: "open",
    reconnects: 0,
    ...overrides,
  };
}

describe("ThinkingStream — narrated default (M2)", () => {
  it("renders plain-language lines, not raw action_type / phase dumps", () => {
    render(
      <ThinkingStream
        investigation={state({
          events: [
            ev("e1", "investigation.start_requested", { question: "Why?" }),
            ev("e2", "decompose.requested"),
            ev("e3", "decompose.delivered", { decomposition: [{}, {}] }),
            ev("e4", "evidence.retrieve.delivered", { supporting_claims: [{}, {}], evidentiary_gaps: [{}] }),
          ],
        })}
      />,
    );
    expect(screen.getByText(/Breaking your question into parts/i)).toBeTruthy();
    expect(screen.getByText(/Broke it into 2 angles/i)).toBeTruthy();
    expect(screen.getByText(/Found 2 supporting points/i)).toBeTruthy();
    // No raw substrate vocabulary in the default view.
    expect(screen.queryByText(/decompose\.delivered/)).toBeNull();
    expect(screen.queryByText(/action_type/)).toBeNull();
    expect(screen.queryByText(/phase 1/i)).toBeNull();
  });

  it("suppressed events (dispatch.call) produce no line", () => {
    render(
      <ThinkingStream
        investigation={state({
          events: [
            ev("e1", "decompose.requested"),
            ev("e2", "dispatch.call", { cost_usd: 0.01, target_role: "decomposer" }),
          ],
        })}
      />,
    );
    expect(screen.getByText(/Breaking your question into parts/i)).toBeTruthy();
    // The dispatch never becomes a line, and its role name never leaks.
    expect(screen.queryByText(/decomposer/)).toBeNull();
    expect(screen.queryByText(/dispatch/i)).toBeNull();
  });

  it("shows a connecting beat before the first event arrives", () => {
    render(<ThinkingStream investigation={state({ status: "in_progress", events: [], streamStatus: "connecting" })} />);
    expect(screen.getByText(/Connecting…/i)).toBeTruthy();
    expect(screen.getByText(/the first step will appear here/i)).toBeTruthy();
  });

  it("shows a reconnecting beat (not a frozen feed) when the socket drops mid-run", () => {
    render(
      <ThinkingStream
        investigation={state({
          status: "in_progress",
          streamStatus: "connecting",
          reconnects: 1,
          events: [ev("e1", "evidence.retrieve.requested", { sub_question: "X" })],
        })}
      />,
    );
    // The story so far is still shown…
    expect(screen.getByText(/Looking for evidence on: X/i)).toBeTruthy();
    // …with a reconnecting status beat, never a stuck spinner.
    expect(screen.getByText(/reconnecting…/i)).toBeTruthy();
  });
});

describe("ThinkingStream — the raw-activity escape hatch (M2)", () => {
  it("hides the raw event log by default and reveals it on toggle", () => {
    render(
      <ThinkingStream
        investigation={state({
          events: [ev("e1", "decompose.delivered", { decomposition: [{}] })],
        })}
      />,
    );
    // Default: narrated, no raw toggle engaged.
    expect(screen.getByText(/show raw activity/i)).toBeTruthy();
    expect(screen.queryByText(/Decomposed/)).toBeNull(); // TrajectoryView's PhaseRow label
    fireEvent.click(screen.getByText(/show raw activity/i));
    // Now the raw TrajectoryView is mounted (its PhaseRow renders "Decomposed").
    expect(screen.getByText(/Decomposed/)).toBeTruthy();
    expect(screen.getByText(/hide raw activity/i)).toBeTruthy();
  });
});

describe("ThinkingStream — reconnect idempotency (M2 gate)", () => {
  it("a re-delivered event (same event_id) narrates exactly once", () => {
    // Simulate the reconnect window: the same event appears twice in the list
    // (the seed fetch + the replayed live tail). useInvestigation dedupes by
    // event_id upstream; ThinkingStream dedupes locally too, so the story line
    // must appear once, never doubled.
    render(
      <ThinkingStream
        investigation={state({
          events: [
            ev("e1", "evidence.retrieve.delivered", { supporting_claims: [{}, {}, {}], evidentiary_gaps: [] }),
            ev("e1", "evidence.retrieve.delivered", { supporting_claims: [{}, {}, {}], evidentiary_gaps: [] }),
          ],
        })}
      />,
    );
    const matches = screen.getAllByText(/Found 3 supporting points/i);
    expect(matches).toHaveLength(1);
  });
});

describe("ThinkingStream — honest no-key / failed state (M4)", () => {
  it("a failed run with no reason shows the no-provider failure, never a spinner", () => {
    render(
      <ThinkingStream
        investigation={state({ status: "failed", terminalPayload: null, events: [] })}
        onRetry={() => {}}
      />,
    );
    expect(screen.getByText(/research didn’t complete/i)).toBeTruthy();
    expect(screen.getByText(/model provider isn’t configured/i)).toBeTruthy();
    expect(screen.queryByText(/thinking…/i)).toBeNull();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  it("a failed run WITH an engine reason frames the reason, not the no-provider guess", () => {
    render(
      <ThinkingStream
        investigation={state({
          status: "failed",
          terminalPayload: { reason: "retrieval timed out" },
          events: [],
        })}
        onRetry={() => {}}
      />,
    );
    expect(screen.getByText(/the engine reported a problem/i)).toBeTruthy();
    expect(screen.getByText(/retrieval timed out/i)).toBeTruthy();
    expect(screen.queryByText(/model provider isn’t configured/i)).toBeNull();
  });

  it("calls onRetry from the failure surface", () => {
    const onRetry = vi.fn();
    render(
      <ThinkingStream investigation={state({ status: "failed", events: [] })} onRetry={onRetry} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("ThinkingStream — live cost + steer (M3)", () => {
  it("shows the real accumulated cost in dollars, no token jargon", () => {
    render(
      <ThinkingStream
        investigation={state({ costTotal: 0.0731, events: [ev("e1", "decompose.requested")] })}
      />,
    );
    const cost = screen.getByLabelText("cost so far");
    expect(cost.textContent).toBe("$0.0731");
    // No token vocabulary anywhere in the header.
    expect(screen.queryByText(/token/i)).toBeNull();
  });

  it("renders a Stop control ONLY when a session-backed steer is wired", () => {
    const onStop = vi.fn();
    const { rerender } = render(
      <ThinkingStream investigation={state({ events: [ev("e1", "decompose.requested")] })} />,
    );
    // One-shot path: no steer prop → no Stop button (honest; nothing to stop).
    expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();

    // Session-backed path: steer wired → Stop visible + functional.
    rerender(
      <ThinkingStream
        investigation={state({ events: [ev("e1", "decompose.requested")] })}
        steer={{ onStop }}
      />,
    );
    const stop = screen.getByRole("button", { name: "Stop" });
    fireEvent.click(stop);
    expect(onStop).toHaveBeenCalledOnce();
  });

  it("a sealed (done) research drops the Stop control and the thinking beat", () => {
    render(
      <ThinkingStream
        investigation={state({ status: "completed", events: [ev("e1", "synthesize.delivered")] })}
        steer={{ onStop: () => {} }}
      />,
    );
    expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
    // The header status reads "done"; use the header span (avoid matching the
    // "the answer is below" footer copy).
    const header = within(screen.getByText("done"));
    expect(header).toBeTruthy();
  });
});
