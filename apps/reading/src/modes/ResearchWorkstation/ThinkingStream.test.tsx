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
 * Field-journal additions:
 *   - semantic region (section[aria-label]) + ordered list;
 *   - zero-padded rendered-order indices (aria-hidden);
 *   - visible tone labels with shape + colour differentiation;
 *   - raw toggle uses aria-expanded + aria-controls on a stable panel id;
 *   - busy Stop disables the button;
 *   - closing folio is a <hr> + mono text;
 *   - max-72ch prose + CSS guard;
 *   - long-text wrapping.
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
    expect(screen.getByText((_, element) =>
      element?.tagName === "P" &&
      element.textContent?.includes("model provider isn’t configured") === true,
    )).toBeTruthy();
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
    expect(screen.queryByText((_, element) =>
      element?.textContent?.includes("model provider isn’t configured") === true,
    )).toBeNull();
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

// ── Field-journal additions ──────────────────────────────────────────────

describe("ThinkingStream — semantic region + list + indices (field journal)", () => {
  it("wraps the narrated stream in a section with an accessible label and an ordered list", () => {
    render(
      <ThinkingStream
        investigation={state({
          events: [
            ev("e1", "decompose.requested"),
            ev("e2", "evidence.retrieve.requested", { sub_question: "X" }),
          ],
        })}
      />,
    );
    const section = screen.getByRole("region", { name: /research field journal/i });
    expect(section).toBeTruthy();
    expect(section.tagName.toLowerCase()).toBe("section");
    const list = screen.getByRole("list");
    expect(list.tagName.toLowerCase()).toBe("ol");
    // Two items in the list.
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
  });

  it("renders zero-padded rendered-order indices that are aria-hidden", () => {
    render(
      <ThinkingStream
        investigation={state({
          events: [
            ev("e1", "decompose.requested"),
            ev("e2", "evidence.retrieve.requested", { sub_question: "X" }),
            ev("e3", "evidence.retrieve.delivered", { supporting_claims: [{}], evidentiary_gaps: [] }),
          ],
        })}
      />,
    );
    const indices = screen.getAllByText(/^(0[1-9]|1[0-9])$/);
    expect(indices).toHaveLength(3);
    expect(indices[0].textContent).toBe("01");
    expect(indices[1].textContent).toBe("02");
    expect(indices[2].textContent).toBe("03");
    for (const idx of indices) {
      expect(idx.getAttribute("aria-hidden")).toBe("true");
    }
  });

  it("produces no line when there are zero events", () => {
    render(
      <ThinkingStream
        investigation={state({ events: [], streamStatus: "open" })}
      />,
    );
    // No section/ol when lines are empty (connecting beat shown instead).
    expect(screen.getByRole("region", { name: /research field journal/i })).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
  });
});

describe("ThinkingStream — tone labels (visible shape + colour)", () => {
  it("shows visible tone labels for each narrated line", () => {
    render(
      <ThinkingStream
        investigation={state({
          events: [
            ev("e1", "decompose.requested"),                                           // step
            ev("e2", "decompose.delivered", { decomposition: [{}, {}] }),              // finding
            ev("e3", "decomposer.paraphrase.flagged"),                                 // caution
            ev("e4", "investigation.start_requested", { question: "Why?" }),           // milestone
          ],
        })}
      />,
    );
    expect(screen.getAllByText("step")).toHaveLength(1);
    expect(screen.getByText("finding")).toBeTruthy();
    expect(screen.getByText("caution")).toBeTruthy();
    expect(screen.getByText("milestone")).toBeTruthy();
  });

  it("every item has a tone-label span with the tone modifier class", () => {
    render(
      <ThinkingStream
        investigation={state({
          events: [
            ev("e1", "decompose.requested"),
            ev("e2", "evidence.retrieve.delivered", { supporting_claims: [{}], evidentiary_gaps: [] }),
          ],
        })}
      />,
    );
    const items = screen.getAllByRole("listitem");
    for (const item of items) {
      const label = item.querySelector("[class*='tone-label--']");
      expect(label).toBeTruthy();
    }
  });

  it("finding and caution expose different non-colour geometry hooks", () => {
    render(
      <ThinkingStream investigation={state({ events: [
        ev("finding", "decompose.delivered", { decomposition: [{}] }),
        ev("caution", "decomposer.paraphrase.flagged"),
      ] })} />,
    );
    const finding = screen.getByText("finding");
    const caution = screen.getByText("caution");
    expect(finding.classList.contains("thinking-field-journal__tone-label--finding")).toBe(true);
    expect(caution.classList.contains("thinking-field-journal__tone-label--caution")).toBe(true);
    expect(finding.className).not.toBe(caution.className);
  });
});

describe("ThinkingStream — raw disclosure (aria-expanded + stable controls id)", () => {
  it("toggle button has aria-expanded and aria-controls pointing to a stable panel id", () => {
    render(
      <ThinkingStream
        investigation={state({
          events: [ev("e1", "decompose.requested")],
        })}
      />,
    );
    const toggle = screen.getByText(/show raw activity/i);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    const panelId = toggle.getAttribute("aria-controls");
    expect(panelId?.startsWith("thinking-stream-raw-panel-")).toBe(true);

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");

    // The raw panel element has the stable id.
    const panel = document.getElementById(panelId ?? "");
    expect(panel).toBeTruthy();
  });

  it("the raw panel id is stable across show/hide cycles", () => {
    render(
      <ThinkingStream
        investigation={state({
          events: [ev("e1", "decompose.requested")],
        })}
      />,
    );
    fireEvent.click(screen.getByText(/show raw activity/i));
    const hideToggle = screen.getByText(/hide raw activity/i);
    const controlledId = hideToggle.getAttribute("aria-controls") ?? "";
    const firstPanelId = document.getElementById(controlledId)?.id;

    fireEvent.click(hideToggle);
    fireEvent.click(screen.getByText(/show raw activity/i));
    const secondPanelId = document.getElementById(controlledId)?.id;

    expect(firstPanelId).toBe(controlledId);
    expect(secondPanelId).toBe(controlledId);
  });

  it("gives concurrent streams unique disclosure relationships", () => {
    render(
      <>
        <ThinkingStream investigation={state({ id: "inv-a", events: [ev("a", "decompose.requested")] })} />
        <ThinkingStream investigation={state({ id: "inv-b", events: [ev("b", "decompose.requested")] })} />
      </>,
    );
    const toggles = screen.getAllByRole("button", { name: /show raw activity/i });
    const ids = toggles.map((toggle) => toggle.getAttribute("aria-controls"));
    expect(new Set(ids).size).toBe(2);
    for (const id of ids) expect(document.getElementById(id ?? "")).toBeTruthy();
  });
});

describe("ThinkingStream — honest not-found state", () => {
  it("does not invent a provider failure or stopped verdict", () => {
    render(<ThinkingStream investigation={state({ status: "not_found" })} onRetry={() => {}} />);
    expect(screen.getByText("not found")).toBeTruthy();
    expect(screen.getByText(/no research exists for this link/i)).toBeTruthy();
    expect(screen.queryByText(/provider/i)).toBeNull();
    expect(screen.queryByText("stopped")).toBeNull();
    expect(screen.getByRole("button", { name: "Reload" })).toBeTruthy();
  });
});

describe("ThinkingStream — busy Stop (disabled while steer command is in flight)", () => {
  it("Stop button is disabled when steer.busy is true", () => {
    render(
      <ThinkingStream
        investigation={state({ events: [ev("e1", "decompose.requested")] })}
        steer={{ onStop: () => {}, busy: true }}
      />,
    );
    const stop = screen.getByRole("button", { name: "Stop" });
    expect((stop as HTMLButtonElement).disabled).toBe(true);
  });

  it("Stop button is enabled when steer.busy is false or absent", () => {
    render(
      <ThinkingStream
        investigation={state({ events: [ev("e1", "decompose.requested")] })}
        steer={{ onStop: () => {} }}
      />,
    );
    const stop = screen.getByRole("button", { name: "Stop" });
    expect((stop as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("ThinkingStream — closing folio on sealed stream", () => {
  it("renders a closing folio with hr and mono text when research completes", () => {
    render(
      <ThinkingStream
        investigation={state({
          status: "completed",
          events: [ev("e1", "investigation.completed")],
        })}
      />,
    );
    expect(screen.getByText(/the answer is below/i)).toBeTruthy();
    // The folio is a note region with an <hr>.
    const folio = screen.getByRole("note", { name: /research complete/i });
    expect(folio).toBeTruthy();
    expect(folio.querySelector("hr")).toBeTruthy();
  });

  it("does not show the closing folio on an in-progress stream", () => {
    render(
      <ThinkingStream
        investigation={state({
          events: [ev("e1", "decompose.requested")],
        })}
      />,
    );
    expect(screen.queryByText(/the answer is below/i)).toBeNull();
  });
});

describe("ThinkingStream — long-text wrapping (max-72ch prose)", () => {
  it("renders long prose lines without truncation", () => {
    const longQuestion =
      "What is the single strongest counter-thesis to the claim that " +
      "renewable energy grid integration costs will exceed fossil fuel " +
      "externalities within the next decade, given current battery technology " +
      "trajectories and regulatory frameworks across major economies?";
    render(
      <ThinkingStream
        investigation={state({
          events: [ev("e1", "investigation.start_requested", { question: longQuestion })],
        })}
      />,
    );
    const prose = screen.getByText(new RegExp(longQuestion.slice(0, 40)));
    expect(prose.textContent).toBe(`Starting on your question: ${longQuestion}`);
    // The prose element carries the max-width constraint class.
    expect(prose.classList.contains("thinking-field-journal__prose")).toBe(true);
  });
});

describe("ThinkingStream — CSS guard (thinking-field-journal.css loaded)", () => {
  it("the field-journal section class is present on the narrated region", () => {
    render(
      <ThinkingStream
        investigation={state({
          events: [ev("e1", "decompose.requested")],
        })}
      />,
    );
    const section = document.querySelector(".thinking-field-journal__section");
    expect(section).toBeTruthy();
    expect(section?.classList.contains("thinking-field-journal__section")).toBe(true);
  });

  it("items carry the field-journal item class", () => {
    render(
      <ThinkingStream
        investigation={state({
          events: [ev("e1", "decompose.requested")],
        })}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items[0].classList.contains("thinking-field-journal__item")).toBe(true);
  });
});
