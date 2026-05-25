/**
 * StartResearch.test.tsx — the Research-home start flow (UI four-product
 * simplify, milestones 1 + 2).
 *
 * Pins the behaviour the operator complaint was about ("I can't even
 * start a research"): a fresh `/` MUST present a real, working composer
 * — autofocused input, a visible Ask button (disabled under 3 chars,
 * enabled past it), example pills that populate the input — and
 * submitting MUST call the real `startInvestigation` and then surface a
 * genuine working state driven by the REAL event stream (here mocked at
 * the hook boundary so jsdom needs no WebSocket), not a silent `…`.
 *
 * The POST and the stream are mocked at their module boundaries so this
 * is a true unit of the start surface; we assert it calls the sanctioned
 * `startInvestigation` (never reimplements it) and renders the live
 * event count + cost from the streamed events.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { Event } from "../../generated/types";

const { startInvestigationMock, navigateMock, eventStreamState } = vi.hoisted(
  () => ({
    startInvestigationMock: vi.fn(),
    navigateMock: vi.fn(),
    eventStreamState: {
      current: {
        events: [] as Event[],
        status: "closed" as "connecting" | "open" | "closed" | "error",
        reconnects: 0,
      },
    },
  }),
);

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, startInvestigation: startInvestigationMock };
});

// Mock the stream at the hook boundary — useStartInvestigation reads it.
// We control its returned state per-test so we exercise the REAL phase
// logic without opening a socket in jsdom.
vi.mock("../../hooks/useEventStream", () => ({
  useEventStream: (id: string | null) =>
    id ? eventStreamState.current : { events: [], status: "closed", reconnects: 0 },
}));

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

import StartResearch from "./StartResearch";

function renderStart() {
  return render(
    <MemoryRouter>
      <StartResearch />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  startInvestigationMock.mockReset();
  navigateMock.mockReset();
  eventStreamState.current = { events: [], status: "closed", reconnects: 0 };
});
afterEach(() => cleanup());

describe("StartResearch — the start-a-research entry (M1)", () => {
  it("renders a real composer: input + Ask button + example pills", () => {
    renderStart();
    expect(screen.getByLabelText("Research question")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ask" })).toBeTruthy();
    // Three clickable example pills.
    expect(screen.getByText(/strongest case against this thesis/i)).toBeTruthy();
    expect(screen.getByText(/how this idea evolved/i)).toBeTruthy();
    expect(screen.getByText(/Where do these authors disagree/i)).toBeTruthy();
  });

  it("Ask is disabled under 3 chars and enabled past it", () => {
    renderStart();
    const ask = screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement;
    expect(ask.disabled).toBe(true); // empty
    const input = screen.getByLabelText("Research question");
    fireEvent.change(input, { target: { value: "ab" } });
    expect(ask.disabled).toBe(true); // 2 chars
    fireEvent.change(input, { target: { value: "abc" } });
    expect(ask.disabled).toBe(false); // 3 chars
  });

  it("clicking an example pill populates the input", () => {
    renderStart();
    const input = screen.getByLabelText("Research question") as HTMLTextAreaElement;
    fireEvent.click(screen.getByText(/strongest case against this thesis/i));
    expect(input.value).toMatch(/strongest case against this thesis/i);
    // ...and the Ask button is now enabled.
    expect(
      (screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("submitting calls the sanctioned startInvestigation (not a reimplemented POST)", async () => {
    startInvestigationMock.mockResolvedValue({ investigation_id: "inv-42" });
    renderStart();
    const input = screen.getByLabelText("Research question");
    fireEvent.change(input, { target: { value: "What is the strongest counter-thesis?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() =>
      expect(startInvestigationMock).toHaveBeenCalledWith(
        expect.objectContaining({ question: "What is the strongest counter-thesis?" }),
      ),
    );
  });

  it("rejects a too-short question without POSTing", async () => {
    renderStart();
    const input = screen.getByLabelText("Research question");
    // Bypass the button's disabled state via the ⌘+Enter submit path.
    fireEvent.change(input, { target: { value: "ab" } });
    fireEvent.keyDown(input, { key: "Enter", metaKey: true });
    // (LemonTextarea only fires onSubmit for non-empty; "ab" is non-empty
    //  but the hook validates >= 3 and refuses to POST.)
    await waitFor(() =>
      expect(screen.getByText(/at least 3 characters/i)).toBeTruthy(),
    );
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });
});

describe("StartResearch — the AI is felt during start (M2)", () => {
  it("shows a genuine connecting state from the REAL stream once the id returns", async () => {
    startInvestigationMock.mockResolvedValue({ investigation_id: "inv-7" });
    eventStreamState.current = { events: [], status: "connecting", reconnects: 0 };
    renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "Trace this idea across the corpus" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    // Working surface, not a silent `…`.
    await waitFor(() => expect(screen.getByText(/Starting your research/i)).toBeTruthy());
    expect(screen.getByText(/connecting to the live trajectory/i)).toBeTruthy();
  });

  it("surfaces the live event count + accumulated cost from streamed dispatch.call events", async () => {
    startInvestigationMock.mockResolvedValue({ investigation_id: "inv-9" });
    // An open stream carrying two real events, one of which is a costed
    // dispatch.call — the cost line must reflect it, never a fake.
    eventStreamState.current = {
      status: "open",
      reconnects: 0,
      events: [
        {
          event_id: "e1",
          investigation_id: "inv-9",
          action_type: "phase.enter",
          payload: {} as never,
          param_version: "v1",
          emitted_at: "2026-05-25T00:00:00Z",
        },
        {
          event_id: "e2",
          investigation_id: "inv-9",
          action_type: "dispatch.call",
          payload: { cost_usd: 0.0123 } as never,
          param_version: "v1",
          emitted_at: "2026-05-25T00:00:01Z",
        },
      ] as Event[],
    };
    renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "Where do the authors disagree?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(screen.getByText(/Working on it/i)).toBeTruthy());
    expect(screen.getByText(/2 events so far/i)).toBeTruthy();
    expect(screen.getByText(/\$0\.0123/)).toBeTruthy();
    // With events present, it routes to the full investigation surface.
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith("/inv/inv-9"),
    );
  });
});

describe("StartResearch — a failed run is surfaced honestly, never a dead route (M3)", () => {
  it("shows an honest error and does NOT navigate when the stream carries investigation.failed", async () => {
    startInvestigationMock.mockResolvedValue({ investigation_id: "inv-fail" });
    // The substrate emits a terminal investigation.failed (Loop 1 aborted —
    // exactly what happens in prod when the model provider isn't configured).
    // The id was returned, but navigating to /inv/:id would strand the
    // operator on a dead surface, so the start surface must catch it.
    eventStreamState.current = {
      status: "open",
      reconnects: 0,
      events: [
        {
          event_id: "f1",
          investigation_id: "inv-fail",
          action_type: "investigation.failed",
          payload: {
            action_type: "investigation.failed",
            phase: 1,
            reason: "no model provider configured",
          } as never,
          param_version: "v1",
          emitted_at: "2026-05-25T00:00:00Z",
        },
      ] as Event[],
    };
    renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "What changed my mind about the thesis?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    // Honest failure copy on the START surface, not the working spinner.
    await waitFor(() =>
      expect(screen.getByText(/research didn’t complete/i)).toBeTruthy(),
    );
    expect(screen.queryByText(/Working on it/i)).toBeNull();
    expect(screen.queryByText(/Starting your research/i)).toBeNull();
    // The diagnostic reason is shown (framed, not raw-as-prose).
    expect(screen.getByText(/no model provider configured/i)).toBeTruthy();
    // It MUST NOT have navigated to the dead /inv/:id route.
    expect(navigateMock).not.toHaveBeenCalled();
    // A Try-again action is offered.
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  it("keeps the typed question recoverable after a failure (not cleared)", async () => {
    startInvestigationMock.mockResolvedValue({ investigation_id: "inv-fail2" });
    eventStreamState.current = {
      status: "open",
      reconnects: 0,
      events: [
        {
          event_id: "f1",
          investigation_id: "inv-fail2",
          action_type: "investigation.failed",
          payload: {
            action_type: "investigation.failed",
            phase: 1,
            reason: "provider keys missing",
          } as never,
          param_version: "v1",
          emitted_at: "2026-05-25T00:00:00Z",
        },
      ] as Event[],
    };
    renderStart();
    const question = "Trace how this idea evolved across the sources.";
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: question },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() =>
      expect(screen.getByText(/research didn’t complete/i)).toBeTruthy(),
    );
    // The composer is back and the question survived the failed run.
    const input = screen.getByLabelText("Research question") as HTMLTextAreaElement;
    expect(input.value).toBe(question);
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
