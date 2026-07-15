/**
 * SuggestedResearch.test.tsx — the §7 compounding flywheel, surfaced (SPR-09).
 *
 * Pins the load-bearing behaviour the sprint page names:
 *   - M1: the daemon's scored gaps render as PLAIN-LANGUAGE threads (no
 *     "evidentiary_gap" / "chase score" / "policy_id" / raw key in the copy),
 *     grounded in a "found across N researches" line.
 *   - Surfacing adds no spend: mounting fetches (read-only) but launches
 *     NOTHING — no startInvestigation call fires on render.
 *   - Launch = explicit click, existing capped path: "Chase this" calls
 *     startInvestigation (the lane, no parent) or the onChase gesture (beside
 *     the answer, reusing the ChaseThread launch) — only on the click.
 *   - Distinction: a suggestion renders as a "could chase" proposal card,
 *     never a running-research row.
 *   - Dedupe: a chased suggestion drops from the offered list (no re-offer).
 *   - Honest no-key / no-daemon: an empty list shows the shared no-result
 *     sentence; a fetch error shows AIActionFailure — never a fabricated
 *     thread.
 *
 * The API client + navigate are mocked at their module boundaries, so this is
 * a true unit (no network).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import type { Suggestion } from "../../api/research";

const { suggestState, startMock, navigateMock, ApiErrorShim } = vi.hoisted(() => {
  // A tiny ApiError-shaped error so the catch branch's `instanceof ApiError`
  // path is exercised. Its prototype is re-pointed at the real ApiError inside
  // the lib/api mock factory below, so `instanceof ApiError` holds.
  class ApiErrorShim extends Error {
    status = 503;
    body: string;
    constructor(body: string) {
      super(body);
      this.body = body;
    }
  }
  return {
    suggestState: {
      current: { suggestions: [] as Suggestion[] },
      error: null as string | null,
    },
    startMock: vi.fn(),
    navigateMock: vi.fn(),
    ApiErrorShim,
  };
});

vi.mock("../../api/research", async (orig) => {
  const actual = await orig<typeof import("../../api/research")>();
  return {
    ...actual,
    getSuggestions: () =>
      suggestState.error
        ? Promise.reject(new ApiErrorShim(suggestState.error))
        : Promise.resolve({
            count: suggestState.current.suggestions.length,
            suggestions: suggestState.current.suggestions,
          }),
  };
});

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  // Make the shim pass `instanceof ApiError`.
  Object.setPrototypeOf(ApiErrorShim.prototype, actual.ApiError.prototype);
  return {
    ...actual,
    startInvestigation: startMock,
  };
});

vi.mock("../../hooks/useInvestigationTree", () => ({
  recordSpawnRelationship: vi.fn(),
}));

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

import SuggestedResearch, { type SuggestedChase } from "./SuggestedResearch";

function sug(over: Partial<Suggestion> & { key: string; question: string }): Suggestion {
  return {
    suggested_retrieval: null,
    seen_in_research_count: 1,
    source_investigation_id: null,
    ...over,
  };
}

function renderLane(props: Partial<React.ComponentProps<typeof SuggestedResearch>> = {}) {
  return render(
    <MemoryRouter>
      <SuggestedResearch {...props} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  suggestState.current = { suggestions: [] };
  suggestState.error = null;
  startMock.mockReset();
  startMock.mockResolvedValue({ investigation_id: "inv-new99", status: "started", start_event_id: "e1" });
  navigateMock.mockReset();
});
afterEach(() => cleanup());

describe("SuggestedResearch — plain-language threads (M1)", () => {
  it("renders the gap as a plain thread, no daemon vocabulary", async () => {
    suggestState.current.suggestions = [
      sug({
        key: "k1",
        question: "What is the dispatch verdict threshold?",
        seen_in_research_count: 3,
        suggested_retrieval: "check §14.4",
      }),
    ];
    const { container } = renderLane();
    expect(await screen.findByText("What is the dispatch verdict threshold?")).toBeTruthy();
    expect(screen.getByText(/found across 3 of your researches/i)).toBeTruthy();
    expect(screen.getByText(/worth looking at: check §14.4/i)).toBeTruthy();
    // No daemon vocabulary, no opaque key in the rendered copy.
    const text = container.textContent ?? "";
    expect(text.toLowerCase()).not.toContain("evidentiary");
    expect(text.toLowerCase()).not.toContain("chase score");
    expect(text.toLowerCase()).not.toContain("policy_id");
    expect(text).not.toContain("k1");
  });

  it("renders each suggestion as a 'could chase' proposal, not a running row", async () => {
    suggestState.current.suggestions = [sug({ key: "k1", question: "A thread" })];
    renderLane();
    await screen.findByText("A thread");
    // Distinct proposal styling + the "could chase" framing (not a status).
    expect(screen.getByTestId("suggestion-card")).toBeTruthy();
    expect(screen.getByText("could chase")).toBeTruthy();
    expect(screen.queryByText("working")).toBeNull();
  });

  it("gives offered threads stable visual locators without changing their status", async () => {
    suggestState.current.suggestions = [
      sug({ key: "k1", question: "First open thread" }),
      sug({ key: "k2", question: "Second open thread" }),
    ];
    renderLane();
    await screen.findByText("First open thread");
    expect(screen.getByText("thread 01")).toBeTruthy();
    expect(screen.getByText("thread 02")).toBeTruthy();
    expect(startMock).not.toHaveBeenCalled();
  });
});

describe("SuggestedResearch — surfacing adds no spend / explicit click (M3)", () => {
  it("launches NOTHING on render (no startInvestigation on mount)", async () => {
    suggestState.current.suggestions = [sug({ key: "k1", question: "A thread" })];
    renderLane();
    await screen.findByText("A thread");
    expect(startMock).not.toHaveBeenCalled();
  });

  it("launches through startInvestigation only on an explicit click (lane, no parent)", async () => {
    suggestState.current.suggestions = [
      sug({ key: "k1", question: "Chase me", source_investigation_id: "inv-src1" }),
    ];
    const user = userEvent.setup();
    renderLane();
    await screen.findByText("Chase me");
    expect(startMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Chase this" }));
    await waitFor(() => expect(startMock).toHaveBeenCalledTimes(1));
    expect(startMock.mock.calls[0][0]).toMatchObject({
      question: "Chase me",
      parent_investigation_id: "inv-src1",
    });
    // The launched research opens.
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/inv/inv-new99"));
  });

  it("hands off to the chase gesture (no direct launch) when a parent is in context", async () => {
    suggestState.current.suggestions = [sug({ key: "k1", question: "Beside me" })];
    const onChase = vi.fn<(chase: SuggestedChase) => void>();
    const user = userEvent.setup();
    renderLane({ variant: "beside", onChase });
    await screen.findByText("Beside me");
    await user.click(screen.getByRole("button", { name: "Chase this" }));
    // The existing chase gesture is used; no standalone launch fires here.
    expect(onChase).toHaveBeenCalledWith({ text: "Beside me", key: "k1" });
    expect(startMock).not.toHaveBeenCalled();
  });

  it("disables the chase control when the user can't launch", async () => {
    suggestState.current.suggestions = [sug({ key: "k1", question: "Locked thread" })];
    renderLane({ canLaunch: false });
    await screen.findByText("Locked thread");
    const btn = screen.getByRole("button", { name: "Chase this" }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });
});

describe("SuggestedResearch — dedupe (M2)", () => {
  it("drops a suggestion from the offered list once it is chased", async () => {
    suggestState.current.suggestions = [
      sug({ key: "k1", question: "First thread" }),
      sug({ key: "k2", question: "Second thread" }),
    ];
    const user = userEvent.setup();
    renderLane();
    await screen.findByText("First thread");
    const firstChaseBtn = screen.getAllByRole("button", { name: "Chase this" })[0];
    await user.click(firstChaseBtn);
    // After chasing the first, it is no longer offered (dedupe); the second
    // remains.
    await waitFor(() => expect(screen.queryByText("First thread")).toBeNull());
    expect(screen.getByText("Second thread")).toBeTruthy();
  });
});

describe("SuggestedResearch — honest no-key / no-daemon (M4)", () => {
  it("shows the honest no-result state when there are no gaps", async () => {
    suggestState.current.suggestions = [];
    renderLane();
    // The shared no-provider sentence (AIActionFailure no-reason branch).
    expect(await screen.findByText(/the engine returned no result/i)).toBeTruthy();
    expect(screen.getByText(/model provider isn/i)).toBeTruthy();
    // Never a fabricated thread.
    expect(screen.queryByTestId("suggestion-card")).toBeNull();
  });

  it("shows the honest failure surface (engine reason) when the fetch errors", async () => {
    suggestState.error = "daemon offline";
    renderLane();
    expect(await screen.findByText(/the engine reported a problem/i)).toBeTruthy();
    expect(screen.getByText(/daemon offline/i)).toBeTruthy();
  });
});
