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
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { Event } from "../../generated/types";

const { startInvestigationMock, fetchUserModelsMock, navigateMock, eventStreamState } = vi.hoisted(
  () => ({
    startInvestigationMock: vi.fn(),
    fetchUserModelsMock: vi.fn(),
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

vi.mock("../../api/settingsModels", () => ({
  fetchUserModels: fetchUserModelsMock,
}));

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

vi.mock("./QuickAsk", () => ({
  default: ({ onPaidRequestInFlight }: { onPaidRequestInFlight?: (pending: boolean) => void }) => (
    <div>
      <span>Quick Ask one-request form</span>
      <input aria-label="Quick Ask operation marker" defaultValue="original-operation" />
      <button type="button" onClick={() => onPaidRequestInFlight?.(true)}>Begin paid send</button>
      <button type="button" onClick={() => onPaidRequestInFlight?.(false)}>Complete paid send</button>
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

async function renderStart() {
  const view = render(
    <MemoryRouter>
      <StartResearch />
    </MemoryRouter>,
  );
  const deep = screen.getByRole("button", { name: "Deep research · multiple model calls" });
  if (deep.getAttribute("aria-pressed") !== "true") {
    fireEvent.click(deep);
    await choosePaidModel();
  }
  return view;
}

beforeEach(() => {
  installMatchMedia(false);
  startInvestigationMock.mockReset();
  fetchUserModelsMock.mockReset();
  fetchUserModelsMock.mockResolvedValue({ models: [executableModel], count: 1, stale_registered: [], source: "test" });
  window.sessionStorage.clear();
  navigateMock.mockReset();
  eventStreamState.current = { events: [], status: "closed", reconnects: 0 };
});

const executableModel = {
  id: "user-paid", provider_kind: "anthropic", provider_catalog_id: "anthropic",
  model_id: "claude-paid", display_name: "Paid Claude", base_url: null,
  enabled: true, key_present: true, registered: true, route_eligible: true,
  pricing_status: "known", hard_ceiling_eligible: true,
  execution_status: "executable", rate_snapshot: "rates-2026-08",
};

async function choosePaidModel() {
  fireEvent.click((await screen.findByRole("combobox", { name: "Model for Ask investigation" })).querySelector("button")!);
  fireEvent.click(await screen.findByRole("option", { name: /Paid Claude/ }));
}
afterEach(() => cleanup());

describe("StartResearch — the start-a-research entry (M1)", () => {
  it("opens the personal Ask on its one-request mode", async () => {
    render(<MemoryRouter><StartResearch /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Quick Ask · one model request" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("Quick Ask one-request form")).toBeTruthy();
  });

  it("keeps a Settings-returned deep launch on its original mode", async () => {
    window.sessionStorage.setItem("antiek.research.pending-owner-launch.session.v1", JSON.stringify({
      question: "Resume this investigation",
      operationId: "operation-1",
      modelChoice: { authority: "user_model", provider_id: "saved-1", model_id: "model-1" },
    }));
    render(<MemoryRouter><StartResearch /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Deep research · multiple model calls" }).getAttribute("aria-pressed")).toBe("true");
    expect((screen.getByLabelText("Research question") as HTMLTextAreaElement).value).toBe("Resume this investigation");
  });

  it("retains the Quick Ask operation across mode switches and locks them during a paid send", async () => {
    render(<MemoryRouter><StartResearch /></MemoryRouter>);
    const marker = screen.getByLabelText("Quick Ask operation marker");
    const quick = screen.getByRole("button", { name: "Quick Ask · one model request" });
    const deep = screen.getByRole("button", { name: "Deep research · multiple model calls" });
    fireEvent.click(screen.getByRole("button", { name: "Begin paid send" }));
    expect((deep as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(deep);
    expect(quick.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Complete paid send" }));
    fireEvent.click(deep);
    expect(deep.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(quick);
    expect(screen.getByLabelText("Quick Ask operation marker")).toBe(marker);
  });

  it("wraps the idle `/` home column in a LANDING-GLASS surface (SPR-03 M2 occlusion contract)", async () => {
    // Audit §3 item 1: the idle `/` home is the landing-glass counterpart of the
    // dense /inv/:id IDE. Its content column rides on GlassSurface variant="glass"
    // so the bare heading clears AA over the scrim while the scene shows through
    // the margins. A refactor swapping it to an opaque body / solid would re-
    // occlude the mountain on `/`; this enforces the variant per-route (rigor #5).
    const { container } = await renderStart();
    const surface = container.querySelector("[data-glass-surface]");
    expect(surface, "the idle home column must render through GlassSurface").toBeTruthy();
    expect(surface!.getAttribute("data-glass-variant")).toBe("glass");
  });

  it("renders a real composer: input + Ask button + example pills", async () => {
    await renderStart();
    expect(screen.getByLabelText("Research question")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ask" })).toBeTruthy();
    // Three clickable example pills.
    expect(screen.getByText(/strongest case against this thesis/i)).toBeTruthy();
    expect(screen.getByText(/how this idea evolved/i)).toBeTruthy();
    expect(screen.getByText(/Where do these authors disagree/i)).toBeTruthy();
  });

  it("Ask is disabled under 3 chars and enabled past it", async () => {
    await renderStart();
    const ask = screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement;
    expect(ask.disabled).toBe(true); // empty
    const input = screen.getByLabelText("Research question");
    fireEvent.change(input, { target: { value: "ab" } });
    expect(ask.disabled).toBe(true); // 2 chars
    fireEvent.change(input, { target: { value: "abc" } });
    expect(ask.disabled).toBe(false); // 3 chars
  });

  it("clicking an example pill populates the input", async () => {
    await renderStart();
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
    await renderStart();
    const input = screen.getByLabelText("Research question");
    fireEvent.change(input, { target: { value: "What is the strongest counter-thesis?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() =>
      expect(startInvestigationMock).toHaveBeenCalledWith(
        expect.objectContaining({ question: "What is the strongest counter-thesis?" }),
      ),
    );
  });

  it("submits the default source policy as metadata-only source-pack intent", async () => {
    startInvestigationMock.mockResolvedValue({ investigation_id: "inv-source-default" });
    await renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "Trace this claim across high-quality sources." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() =>
      expect(startInvestigationMock).toHaveBeenCalledWith(
        expect.objectContaining({
          source_policy: ["operator_corpus", "web"],
        }),
      ),
    );
  });

  it("lets the operator add arXiv and Substack to the submitted source policy", async () => {
    startInvestigationMock.mockResolvedValue({ investigation_id: "inv-source-expanded" });
    await renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "Which technical claims have the strongest paper trail?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "arXiv" }));
    fireEvent.click(screen.getByRole("button", { name: "Substack" }));
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() =>
      expect(startInvestigationMock).toHaveBeenCalledWith(
        expect.objectContaining({
          source_policy: ["operator_corpus", "web", "arxiv", "substack"],
        }),
      ),
    );
  });

  it("selecting Fast changes the submitted tier (SPR-01 M3)", async () => {
    startInvestigationMock.mockResolvedValue({ investigation_id: "inv-fast" });
    await renderStart();
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

  it("a failed submit says what failed and what is safe, hides the raw HTTP error, and retries (C2)", async () => {
    // Before: "Submit failed: POST /investigations failed: HTTP 500" in 12px
    // mono red under the composer.
    startInvestigationMock.mockRejectedValueOnce(new Error("POST /investigations failed: HTTP 500"));
    await renderStart();
    const input = screen.getByLabelText("Research question") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "What drives the thesis?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/Couldn.t start the research/);
    expect(alert.textContent).toMatch(/question is still here/i);
    expect(document.body.textContent).not.toMatch(/HTTP 500|POST \/investigations|Submit failed/);
    expect(input.value).toBe("What drives the thesis?");
    startInvestigationMock.mockResolvedValueOnce({ investigation_id: "inv-retry" });
    fireEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(2));
  });

  it("sets an error sentence in the interface face, never mono (T5)", async () => {
    await renderStart();
    const input = screen.getByLabelText("Research question");
    fireEvent.change(input, { target: { value: "ab" } });
    fireEvent.keyDown(input, { key: "Enter", metaKey: true });
    const sentence = await screen.findByText(/at least 3 characters/i);
    expect(sentence.closest(".font-mono")).toBeNull();
  });

  it("rejects a too-short question without POSTing", async () => {
    await renderStart();
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

describe("StartResearch — cascade action safety", () => {
  it("keeps cascade disabled even for a complete question", async () => {
    await renderStart();
    const ask = screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement;
    const cascade = screen.getByRole("button", {
      name: /Break into sub-questions/i,
    }) as HTMLButtonElement;
    expect(ask).toBeTruthy();
    expect(cascade.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "How will the energy transition reshape geopolitics?" },
    });
    expect(cascade.disabled).toBe(true);
  });

  it("does not mount the proposal or issue a paid request", async () => {
    await renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "How will the energy transition reshape geopolitics?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Break into sub-questions/i }));
    expect(screen.queryByTestId("cascade-proposal")).toBeNull();
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });
});

describe("StartResearch — owner model authority", () => {
  it("requires an executable owner before Deep Ask can submit by button or keyboard", async () => {
    fetchUserModelsMock.mockResolvedValue({ models: [], count: 0, stale_registered: [], source: "server" });
    render(<MemoryRouter><StartResearch /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "Deep research · multiple model calls" }));
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "No route has been selected." } });
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.keyDown(screen.getByLabelText("Research question"), { key: "Enter", metaKey: true });
    expect(startInvestigationMock).not.toHaveBeenCalled();
    expect(window.sessionStorage.length).toBe(0);
  });

  it("shows only fully executable inventory rows and submits one exact paired choice", async () => {
    fetchUserModelsMock.mockResolvedValue({
      models: [executableModel, { ...executableModel, id: "blocked", display_name: "Blocked", execution_status: "blocked_unknown_pricing" }],
      count: 2, stale_registered: [], source: "server",
    });
    startInvestigationMock.mockResolvedValue({ investigation_id: "inv-owner" });
    await renderStart();
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalled());
    expect(screen.queryByText(/Blocked/)).toBeNull();
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Trace the owner model contract." } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalled());
    const request = startInvestigationMock.mock.calls[0][0];
    expect(request.model_choice).toEqual({ authority: "user_model", provider_id: "user-paid", model_id: "claude-paid" });
    expect(request.operation_id).toMatch(/^research-/);
    expect(Object.keys(request).filter((key) => key === "model_choice" || key === "operation_id")).toHaveLength(2);
  });

  it("persists the same pending operation and choice across a reload", async () => {
    fetchUserModelsMock.mockResolvedValue({ models: [executableModel], count: 1, stale_registered: [], source: "server" });
    startInvestigationMock.mockImplementation(() => new Promise(() => {}));
    const first = await renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Resume this exact launch." } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(1));
    const firstRequest = startInvestigationMock.mock.calls[0][0];
    first.unmount();
    await renderStart();
    await waitFor(() => expect((screen.getByLabelText("Research question") as HTMLTextAreaElement).value).toBe("Resume this exact launch."));
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(2));
    expect(startInvestigationMock.mock.calls[1][0].operation_id).toBe(firstRequest.operation_id);
    expect(startInvestigationMock.mock.calls[1][0].model_choice).toEqual(firstRequest.model_choice);
  });

  it("clears a stale selected route after refresh and blocks button and keyboard submission", async () => {
    fetchUserModelsMock
      .mockResolvedValueOnce({ models: [executableModel], count: 1, stale_registered: [], source: "server" })
      .mockResolvedValueOnce({ models: [], count: 0, stale_registered: [], source: "server" });
    await renderStart();
    fireEvent.click(screen.getByRole("button", { name: "Retry inventory" }));
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalledTimes(2));
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Use the established route now." } });
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    fireEvent.keyDown(screen.getByLabelText("Research question"), { key: "Enter", metaKey: true });
    expect(startInvestigationMock).not.toHaveBeenCalled();
    expect(window.sessionStorage.length).toBe(0);
  });

  it("blocks paid submission while inventory refresh is pending, then restores the selected route", async () => {
    const inventory = { models: [executableModel], count: 1, stale_registered: [], source: "server" };
    let resolveRefresh!: (value: typeof inventory) => void;
    const refresh = new Promise<typeof inventory>((resolve) => { resolveRefresh = resolve; });
    fetchUserModelsMock
      .mockResolvedValueOnce(inventory)
      .mockReturnValueOnce(refresh);
    startInvestigationMock.mockResolvedValue({ investigation_id: "inv-after-refresh" });

    await renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Wait for the refreshed owner route." } });
    fireEvent.click(screen.getByRole("button", { name: "Retry inventory" }));
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalledTimes(2));

    const ask = screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement;
    expect(ask.disabled).toBe(true);
    fireEvent.click(ask);
    fireEvent.keyDown(screen.getByLabelText("Research question"), { key: "Enter", metaKey: true });
    expect(startInvestigationMock).not.toHaveBeenCalled();
    expect(window.sessionStorage.length).toBe(0);

    resolveRefresh(inventory);
    await waitFor(() => expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(1));
    expect(startInvestigationMock.mock.calls[0][0].model_choice).toEqual({
      authority: "user_model", provider_id: "user-paid", model_id: "claude-paid",
    });
  });

  it("surfaces inventory failure and blocks Ask and keyboard submission without an owner", async () => {
    fetchUserModelsMock.mockRejectedValue(new Error("secret upstream detail"));
    render(<MemoryRouter><StartResearch /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "Deep research · multiple model calls" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Can’t load executable models");
    expect(screen.queryByText(/research-[0-9a-f-]+/i)).toBeNull();
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Continue without an owner route." } });
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.keyDown(screen.getByLabelText("Research question"), { key: "Enter", metaKey: true });
    expect(startInvestigationMock).not.toHaveBeenCalled();
    expect(window.sessionStorage.length).toBe(0);
  });

  it("disables cascade because it cannot bind the planned requests to an owner route", async () => {
    fetchUserModelsMock.mockResolvedValue({ models: [executableModel], count: 1, stale_registered: [], source: "server" });
    await renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Break this broad question down." } });
    const cascade = screen.getByRole("button", { name: /Break into sub-questions/ }) as HTMLButtonElement;
    expect(cascade.disabled).toBe(true);
    fireEvent.click(cascade);
    expect(screen.queryByTestId("cascade-proposal")).toBeNull();
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });
});

describe("StartResearch — the AI is felt during start (M2)", () => {
  it("shows a genuine connecting state from the REAL stream once the id returns", async () => {
    startInvestigationMock.mockResolvedValue({ investigation_id: "inv-7" });
    eventStreamState.current = { events: [], status: "connecting", reconnects: 0 };
    await renderStart();
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
    await renderStart();
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
    await renderStart();
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
    await renderStart();
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

    const first = startInvestigationMock.mock.calls[0][0];
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(2));
    const retried = startInvestigationMock.mock.calls[1][0];
    expect(retried.question).toBe(first.question);
    expect(retried.model_choice).toEqual(first.model_choice);
    expect(retried.operation_id).not.toBe(first.operation_id);
  });
});
