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

const { startInvestigationMock, navigateMock, eventStreamState, routePreviewState } = vi.hoisted(
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
    routePreviewState: { current: {} as Record<string, unknown> },
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

// Existing start-flow cases exercise the promised preview-outage fallback.
// The route instrument's ready/race behavior has focused tests of its own.
vi.mock("../../hooks/useResearchRoutePreview", () => ({
  useResearchRoutePreview: () => routePreviewState.current,
}));

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

// Mock the cascade child at its boundary: this file is a unit of the toggle,
// not of the proposal (CascadeProposal has its own test). The stub renders a
// marker + a launch button so we can prove the toggle mounts it on the same
// surface and that a launch navigates to the session monitor.
vi.mock("./CascadeProposal", () => ({
  default: ({ problem, onLaunched }: { problem: string; onLaunched: (id: string) => void }) => (
    <div data-testid="cascade-proposal">
      <span>cascade for: {problem}</span>
      <button type="button" onClick={() => onLaunched("session-xyz")}>
        launch-stub
      </button>
    </div>
  ),
}));

import StartResearch from "./StartResearch";

// AMS2-SPR-03: the idle home now wraps its content column in GlassSurface
// (landing-glass, M2 for `/`), and GlassSurface reads `prefers-reduced-motion`
// via window.matchMedia — which jsdom lacks. Stub it (no reduced motion) so the
// surface renders its glass path; mirrors the AppShell + GlassSurface suites'
// stub. This is an environment dependency of the newly-rendered primitive, not
// a weakening of any assertion below.
function installMatchMedia(reducedMotion = false) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: query.includes("prefers-reduced-motion") ? reducedMotion : false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

function renderStart() {
  return render(
    <MemoryRouter>
      <StartResearch />
    </MemoryRouter>,
  );
}

function installReadyBudget(budget: Record<string, unknown>) {
  routePreviewState.current = {
    status: "ready",
    error: null,
    retry: vi.fn(),
    preview: {
      policy_version: "research-route.v1",
      prompt_fingerprint: "prompt-proof",
      candidates: [{
        choice_id: "rr_fast",
        tier: "fast",
        configuration_fingerprint: "cfg-fast",
        display_name: "Fast lens",
        model_policy_label: "GLM-5.2 · thinking off",
        rationale: "Exploratory work",
        ready: true,
        readiness_label: "Ready",
      }],
      budget,
    },
  };
}

beforeEach(() => {
  installMatchMedia(false);
  startInvestigationMock.mockReset();
  navigateMock.mockReset();
  eventStreamState.current = { events: [], status: "closed", reconnects: 0 };
  routePreviewState.current = {
    status: "error",
    preview: null,
    error: "preview unavailable",
    retry: vi.fn(),
  };
});
afterEach(() => cleanup());

describe("StartResearch — the start-a-research entry (M1)", () => {
  it("wraps the idle `/` home column in a LANDING-GLASS surface (SPR-03 M2 occlusion contract)", () => {
    // Audit §3 item 1: the idle `/` home is the landing-glass counterpart of the
    // dense /inv/:id IDE. Its content column rides on GlassSurface variant="glass"
    // so the bare heading clears AA over the scrim while the scene shows through
    // the margins. A refactor swapping it to an opaque body / solid would re-
    // occlude the mountain on `/`; this enforces the variant per-route (rigor #5).
    const { container } = renderStart();
    const surface = container.querySelector("[data-glass-surface]");
    expect(surface, "the idle home column must render through GlassSurface").toBeTruthy();
    expect(surface!.getAttribute("data-glass-variant")).toBe("glass");
  });

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

  it("defaults the research tier to deep and submits it (SPR-01 M3)", async () => {
    startInvestigationMock.mockResolvedValue({ investigation_id: "inv-tier" });
    renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "Does the moat compound with more dispatches?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() =>
      expect(startInvestigationMock).toHaveBeenCalledWith(
        expect.objectContaining({ research_tier: "deep" }),
      ),
    );
  });

  it("selecting Fast changes the submitted tier (SPR-01 M3)", async () => {
    startInvestigationMock.mockResolvedValue({ investigation_id: "inv-fast" });
    renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "A quick exploratory scan of this topic." },
    });
    // The curated closed-set control — pick "Fast".
    fireEvent.click(screen.getByRole("radio", { name: "Fast" }));
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() =>
      expect(startInvestigationMock).toHaveBeenCalledWith(
        expect.objectContaining({ research_tier: "fast" }),
      ),
    );
  });

  it("explains depth accessibly without provider names or static prices", () => {
    renderStart();
    expect(screen.getByRole("radiogroup", { name: "Research depth" })).toBeTruthy();
    expect(screen.getByText(/more reasoning for upstream investigation work/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "Fast" }));
    expect(screen.getByText(/lighter upstream investigation work/i)).toBeTruthy();
    expect(screen.getByText(/final synthesis stays on its dedicated reasoning route/i)).toBeTruthy();
    expect(screen.getByText(/cost depends on the sources and work required/i)).toBeTruthy();
    expect(screen.queryByText(/\$0\.08|\$0\.16|MiMo|DeepSeek/i)).toBeNull();
  });

  it("renders and submits only the server-issued ready route proof", async () => {
    routePreviewState.current = {
      status: "ready",
      error: null,
      retry: vi.fn(),
      preview: {
        policy_version: "research-route.v1",
        prompt_fingerprint: "prompt-proof",
        candidates: [
          {
            choice_id: "rr_fast",
            tier: "fast",
            configuration_fingerprint: "cfg-fast",
            display_name: "Fast lens",
            model_policy_label: "GLM-5.2 · thinking off",
            rationale: "Exploratory work",
            ready: true,
            readiness_label: "Ready",
          },
          {
            choice_id: "rr_deep",
            tier: "deep",
            configuration_fingerprint: "cfg-deep",
            display_name: "Deep lens",
            model_policy_label: "GLM-5.2 · thinking on",
            rationale: "Reasoning-heavy work",
            ready: true,
            readiness_label: "Ready",
          },
        ],
        budget: {
          authority: "advisory",
          daily_cap_usd: 5,
          spent_usd: null,
          spent_status: "unknown",
          cap_source: "ANTIEK_OPERATOR_BUDGET_USD",
          notes: [],
          projection_status: "unavailable",
          projection_note: "Trajectory cost is unavailable until measured telemetry supports an estimator.",
        },
      },
    };
    startInvestigationMock.mockResolvedValue({ investigation_id: "inv-route" });
    renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "Compare these sources and resolve their disagreement." },
    });
    expect(screen.getByRole("radiogroup", { name: "Research route" })).toBeTruthy();
    expect(screen.getByText(/spend unknown · \$5\.00 operator ceiling · projection unavailable/i)).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("radio", { name: /Deep lens/i }), { key: "ArrowLeft" });
    expect(screen.getByRole("radio", { name: /Fast lens/i }).getAttribute("aria-checked")).toBe("true");
    fireEvent.keyDown(screen.getByRole("radio", { name: /Fast lens/i }), { key: "End" });
    expect(screen.getByRole("radio", { name: /Deep lens/i }).getAttribute("aria-checked")).toBe("true");
    fireEvent.keyDown(screen.getByRole("radio", { name: /Deep lens/i }), { key: "Home" });
    expect(screen.getByRole("radio", { name: /Fast lens/i }).getAttribute("aria-checked")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledWith(
      expect.objectContaining({
        research_tier: undefined,
        route_choice_id: "rr_fast",
        route_prompt_fingerprint: "prompt-proof",
        route_policy_version: "research-route.v1",
        route_configuration_fingerprint: "cfg-fast",
      }),
    ));
  });

  it.each([
    ["configured and known", 8, 2, "known", "ANTIEK_OPERATOR_BUDGET_USD", true, /\$2\.00 spent · \$8\.00 operator ceiling/i],
    ["configured and unknown", 8, null, "unknown", "ANTIEK_OPERATOR_BUDGET_USD", false, /spend unknown · \$8\.00 operator ceiling/i],
    ["unconfigured and known", null, 2, "known", null, false, /\$2\.00 daemon-tracked · no operator ceiling/i],
    ["unconfigured and unknown", null, null, "unknown", null, false, /spend unknown · no operator ceiling/i],
  ])("renders truthful budget authority when %s", (_, cap, spent, spentStatus, capSource, hasMeter, copy) => {
    installReadyBudget({
      authority: "advisory",
      daily_cap_usd: cap,
      spent_usd: spent,
      spent_status: spentStatus,
      cap_source: capSource,
      notes: [],
      projection_status: "unavailable",
      projection_note: "Trajectory cost is unavailable.",
    });
    renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "Compare these sources." },
    });

    expect(screen.getByText(copy)).toBeTruthy();
    expect(screen.queryByTestId("research-budget-meter") !== null).toBe(hasMeter);
  });

  it("offers the explicit recovery-chain fallback when preferred drivers are unavailable", async () => {
    routePreviewState.current = {
      status: "ready",
      error: null,
      retry: vi.fn(),
      preview: {
        policy_version: "research-route.v1",
        prompt_fingerprint: "prompt-proof",
        candidates: [{
          choice_id: "rr_deep",
          tier: "deep",
          configuration_fingerprint: "cfg-deep",
          display_name: "Deep lens",
          model_policy_label: "GLM-5.2 · thinking on",
          rationale: "Reasoning-heavy work",
          ready: false,
          readiness_label: "Provider unavailable",
        }],
        budget: {
          authority: "advisory",
          daily_cap_usd: null,
          spent_usd: null,
          spent_status: "unknown",
          cap_source: null,
          notes: ["No operator cap is configured; the daemon default is reference-only."],
          projection_status: "unavailable",
          projection_note: "Trajectory cost is unavailable until measured telemetry supports an estimator.",
        },
      },
    };
    startInvestigationMock.mockResolvedValue({ investigation_id: "inv-recovery" });
    renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "Research this through the configured recovery chain." },
    });
    expect(screen.getByText(/preferred drivers are unavailable/i)).toBeTruthy();
    expect(screen.getByRole("radiogroup", { name: "Research depth" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledWith(
      expect.objectContaining({ research_tier: "deep", route_choice_id: undefined }),
    ));
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

describe("StartResearch — cascade mode beside the one-shot Ask (SPR-01 M1)", () => {
  it("shows two clearly-labelled actions; cascade is disabled under 3 chars", () => {
    renderStart();
    const ask = screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement;
    const cascade = screen.getByRole("button", {
      name: /Break into sub-questions/i,
    }) as HTMLButtonElement;
    expect(ask).toBeTruthy();
    expect(cascade.disabled).toBe(true); // empty composer
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "How will the energy transition reshape geopolitics?" },
    });
    expect(cascade.disabled).toBe(false);
  });

  it("choosing cascade renders the proposal in place — no navigation away, no POST of a one-shot", () => {
    renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "How will the energy transition reshape geopolitics?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Break into sub-questions/i }));
    // The proposal mounted on the SAME surface.
    expect(screen.getByTestId("cascade-proposal")).toBeTruthy();
    expect(screen.getByText(/cascade for: How will the energy transition/i)).toBeTruthy();
    // It did NOT start a one-shot investigation.
    expect(startInvestigationMock).not.toHaveBeenCalled();
    // The one-shot composer is gone (we're in cascade mode).
    expect(screen.queryByRole("button", { name: "Ask" })).toBeNull();
  });

  it("a launched cascade navigates to the session monitor", () => {
    renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "Where do the authors disagree across the corpus?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Break into sub-questions/i }));
    fireEvent.click(screen.getByRole("button", { name: "launch-stub" }));
    expect(navigateMock).toHaveBeenCalledWith("/deep-research/session-xyz");
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
    // The question is restored by a useEffect that runs AFTER the failure
    // render (onSubmit clears it only on a successful POST), so wait for that
    // restoration instead of reading the input synchronously. The field is
    // briefly "" between the onSubmit clear and the failure-effect restore.
    await waitFor(() => {
      const input = screen.getByLabelText("Research question") as HTMLTextAreaElement;
      expect(input.value).toBe(question);
    });
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
