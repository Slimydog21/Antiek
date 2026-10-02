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
 * Auth, controller, picker, QuickAsk, launch hook and API execute normally.
 * HTTP responses and the event-stream hook are controlled. This proves only
 * the local component/protocol behavior, not native or provider execution.
 */
import { useEffect, useLayoutEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { unstable_HistoryRouter as HistoryRouter, useLocation } from "react-router-dom";
import { AuthProvider, useAuth, type AuthContextValue } from "../../lib/auth";
import { createRootResearchLaunchArchive } from "./rootResearchLaunch";

import * as delight from "../../shared/delight";
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

// Mock the stream at the hook boundary — useStartInvestigation reads it.
// We control its returned state per-test so we exercise the REAL phase
// logic without opening a socket in jsdom.
vi.mock("../../hooks/useEventStream", () => ({
  useEventStream: (id: string | null) =>
    id ? eventStreamState.current : { events: [], status: "closed", reconnects: 0 },
}));

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

import StartResearch, { useResearchHomeBinding } from "./StartResearch";
import { initializeNavigationHistory, readNavigationEpoch, type NavigationHistory } from "../../workspace/navigationLifetime";
import { useWorkspaceHydration } from "../../workspace/useWorkspaceHydration";
import { encodeWsParam, project } from "../../workspace/persistence";
import { EMPTY_SNAPSHOT } from "../../workspace/panel.types";
import { getHydrationGeneration } from "../../workspace/WorkspaceStore";

// Actual AuthProvider/controller/picker/QuickAsk/hook/API. Only HTTP, stream and
// browser primitives are controlled; these receipts are local protocol fixtures.
const archiveSlot = vi.hoisted(() => ({ current: null as ReturnType<typeof createRootResearchLaunchArchive> | null }));
vi.mock("./rootResearchLaunch", async (original) => {
  const actual = await original<typeof import("./rootResearchLaunch")>();
  return { ...actual, get rootResearchLaunchArchive() {
    if (!archiveSlot.current) throw new Error("archive fixture is not mounted");
    return archiveSlot.current;
  } };
});
let auth: AuthContextValue;
let navigationHistory: NavigationHistory;
let homeBinding: ReturnType<typeof useResearchHomeBinding>;
const authRead = vi.fn();
const quickSend = vi.fn();
const owner = { user_id: "deep-owner", email: null, auth_method: "antiek_session_cookie" };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const ownerReceipt = (id: string, operationId: unknown) => ({
  investigation_id: id, start_event_id: `event-${id}`, status: "started",
  operation_id: operationId, owner_model_status: "queued",
});
function AuthProbe() { auth = useAuth(); return null; }
function LocationProbe() {
  const location = useLocation();
  useEffect(() => { if (location.pathname !== "/") navigateMock(location.pathname); }, [location.key, location.pathname]);
  return null;
}
function RouteHydration({ afterHydration }: { afterHydration?: () => void }) {
  useWorkspaceHydration();
  useLayoutEffect(() => { afterHydration?.(); }, [afterHydration]);
  return null;
}
function HydratedHome({ children, hydrate, afterHydration }: {
  children: ReactNode; hydrate: boolean; afterHydration?: () => void;
}) {
  homeBinding = useResearchHomeBinding();
  return <>{hydrate && <RouteHydration afterHydration={afterHydration} />}{children}</>;
}
function TestRouter({ children, hydrate = true, afterHydration }: {
  children: ReactNode; hydrate?: boolean; afterHydration?: () => void;
}) {
  return <HistoryRouter history={navigationHistory}><LocationProbe /><HydratedHome hydrate={hydrate} afterHydration={afterHydration}>{children}</HydratedHome></HistoryRouter>;
}
async function mount(children: ReactNode) {
  const view = render(<AuthProvider><AuthProbe />{children}</AuthProvider>);
  await waitFor(() => expect(auth.state.status).toBe("authenticated"));
  await waitFor(() => expect(homeBinding.readHome()).not.toBeNull());
  return { ...view, rerender: (next: ReactNode) => view.rerender(<AuthProvider><AuthProbe />{next}</AuthProvider>) };
}
function installTransport() {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input), "http://fixture").pathname;
    if (path.endsWith("/auth/me")) return authRead();
    if (path.endsWith("/settings/models/user")) return json(await fetchUserModelsMock());
    if (path.endsWith("/settings/usage") || path.includes("/settings/balance/")) return json({ reason: "fixture_metrics_unavailable" }, 503);
    if (path.endsWith("/research/quick-ask/models")) return json({ count: 1, models: [{
      provider_id: "user-paid", model_id: "claude-paid", display_name: "Paid Claude", price_snapshot: "controlled-price", price_source: "fixture",
    }] });
    if (path.endsWith("/research/quick-ask/recent")) return json({ operations: [] });
    if (path.endsWith("/research/quick-ask/quote")) return json({
      quote_digest: "a".repeat(64), estimate_usd: "0.01", reserved_cents: 1,
      provider_id: "user-paid", model_id: "claude-paid", max_output_tokens: 100,
      price_snapshot: "controlled-price", price_source: "fixture", warning: "Controlled estimate; charge may differ.",
    });
    if (path.endsWith("/research/quick-ask")) return quickSend();
    if (path.endsWith("/investigations") && init?.method === "POST") {
      const body: unknown = JSON.parse(String(init.body));
      const result: unknown = await startInvestigationMock(body);
      return result instanceof Response ? result : json(result);
    }
    throw new Error(`Unexpected controlled HTTP ${init?.method ?? "GET"} ${path}`);
  }));
}


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
  const view = await mount(
    <TestRouter>
      <StartResearch />
    </TestRouter>,
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
  navigationHistory = initializeNavigationHistory(window);
  navigationHistory.replace("/");
  startInvestigationMock.mockReset();
  startInvestigationMock.mockImplementation(async (body) => ownerReceipt("inv-default", body.operation_id));
  archiveSlot.current = createRootResearchLaunchArchive();
  authRead.mockReset();
  authRead.mockImplementation(() => Promise.resolve(json(owner)));
  quickSend.mockReset();
  quickSend.mockResolvedValue(json({ reason: "charge_unknown" }, 503));
  installTransport();
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
  const picker = await screen.findByRole("button", { name: "Model for Ask investigation" });
  await waitFor(() => expect(picker.hasAttribute("disabled")).toBe(false));
  fireEvent.click(picker);
  fireEvent.click(screen.queryByRole("menuitem", { name: /claude-paid/ }) ?? await screen.findByRole("menuitem", { name: /Paid Claude/ }));
}
afterEach(() => { cleanup(); archiveSlot.current = null; vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("StartResearch — the start-a-research entry (M1)", () => {
  it("opens the personal Ask on its one-request mode", async () => {
    await mount(<TestRouter><StartResearch /></TestRouter>);
    expect(screen.getByRole("button", { name: "Quick Ask · one model request" }).getAttribute("aria-pressed")).toBe("true");
    expect(await screen.findByRole("heading", { name: "Quick Ask" })).toBeTruthy();
  });

  it("retains a legacy pending launch as opaque uncertainty without restoring private text", async () => {
    const marker = JSON.stringify({ question: "Resume this investigation", operationId: "operation-1",
      modelChoice: { authority: "user_model", provider_id: "saved-1", model_id: "model-1" } });
    window.sessionStorage.setItem("antiek.research.pending-owner-launch.session.v1", marker);
    await mount(<TestRouter><StartResearch /></TestRouter>);
    expect(screen.getByRole("button", { name: "Quick Ask · one model request" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Deep research · multiple model calls" }));
    expect(screen.getByLabelText("Research question")).toHaveProperty("value", "");
    expect(screen.getByText(/previous research request may have been accepted or charged/i)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Resume this investigation|saved-1|operation-1/);
    expect(window.sessionStorage.getItem("antiek.research.pending-owner-launch.session.v1")).toBe(marker);
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });

  it("retains the actual Quick Ask node and quote across modes and locks modes while paid send is held", async () => {
    let finish!: (response: Response) => void;
    quickSend.mockReturnValue(new Promise<Response>((resolve) => { finish = resolve; }));
    await mount(<TestRouter><StartResearch /></TestRouter>);
    const input = await screen.findByLabelText("Quick Ask question");
    fireEvent.change(input, { target: { value: "Keep this actual Quick draft" } });
    fireEvent.click((await screen.findByRole("combobox", { name: "Quick Ask model" })).querySelector("button")!);
    fireEvent.click(await screen.findByRole("option", { name: /Paid Claude/ }));
    fireEvent.click(screen.getByRole("button", { name: "Review estimate" }));
    await screen.findByRole("button", { name: "Send one request" });
    const deep = screen.getByRole("button", { name: "Deep research · multiple model calls" });
    const quick = screen.getByRole("button", { name: "Quick Ask · one model request" });
    fireEvent.click(deep);
    fireEvent.click(quick);
    expect(screen.getByLabelText("Quick Ask question")).toBe(input);
    expect(input).toHaveProperty("value", "Keep this actual Quick draft");
    fireEvent.click(screen.getByRole("button", { name: "Send one request" }));
    expect(deep).toHaveProperty("disabled", true);
    fireEvent.click(deep);
    expect(quick.getAttribute("aria-pressed")).toBe("true");
    await act(async () => { finish(json({ reason: "charge_unknown" }, 503)); });
    await waitFor(() => expect(deep).toHaveProperty("disabled", false));
    expect(quickSend).toHaveBeenCalledTimes(1);
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
    startInvestigationMock.mockImplementation(async (body) => ownerReceipt("inv-42", body.operation_id));
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
    startInvestigationMock.mockImplementation(async (body) => ownerReceipt("inv-source-default", body.operation_id));
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
    startInvestigationMock.mockImplementation(async (body) => ownerReceipt("inv-source-expanded", body.operation_id));
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
    startInvestigationMock.mockImplementation(async (body) => ownerReceipt("inv-fast", body.operation_id));
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

  it("an unknown submit hides raw HTTP error and refuses generic paid retry (C2)", async () => {
    // Before: "Submit failed: POST /investigations failed: HTTP 500" in 12px
    // mono red under the composer.
    startInvestigationMock.mockRejectedValueOnce(new Error("POST /investigations failed: HTTP 500"));
    await renderStart();
    const input = screen.getByLabelText("Research question") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "What drives the thesis?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/could not confirm the start/i);
    expect(alert.textContent).toMatch(/may have been accepted or charged/i);
    expect(document.body.textContent).not.toMatch(/HTTP 500|POST \/investigations|Submit failed/);
    expect(input.value).toBe("What drives the thesis?");
    expect(within(alert).queryByRole("button", { name: "Try again" })).toBeNull();
    fireEvent.keyDown(input, { key: "Enter", metaKey: true });
    expect(startInvestigationMock).toHaveBeenCalledTimes(1);
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
    await mount(<TestRouter><StartResearch /></TestRouter>);
    fireEvent.click(screen.getByRole("button", { name: "Deep research · multiple model calls" }));
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "No route has been selected." } });
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.keyDown(screen.getByLabelText("Research question"), { key: "Enter", metaKey: true });
    expect(startInvestigationMock).not.toHaveBeenCalled();
    expect(window.sessionStorage.length).toBe(0);
  });

  it("shows ineligible inventory rows as disabled and submits one exact paired choice", async () => {
    fetchUserModelsMock.mockResolvedValue({
      models: [executableModel, { ...executableModel, id: "blocked", display_name: "Blocked", execution_status: "blocked_unknown_pricing" }],
      count: 2, stale_registered: [], source: "server",
    });
    startInvestigationMock.mockImplementation(async (body) => ownerReceipt("inv-owner", body.operation_id));
    await renderStart();
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Model for Ask investigation" }));
    const blocked = await screen.findByRole("menuitem", { name: /Blocked/ });
    expect(blocked).toHaveProperty("disabled", true);
    fireEvent.click(blocked);
    fireEvent.click(screen.getByRole("menuitem", { name: /Paid Claude/ }));
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Trace the owner model contract." } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalled());
    const request = startInvestigationMock.mock.calls[0][0];
    expect(request.model_choice).toEqual({ authority: "user_model", provider_id: "user-paid", model_id: "claude-paid" });
    expect(request.operation_id).toMatch(/^research-/);
    expect(Object.keys(request).filter((key) => key === "model_choice" || key === "operation_id")).toHaveLength(2);
  });

  it("retains operation-only uncertainty across remount without restoring or replaying a body", async () => {
    startInvestigationMock.mockRejectedValue(new Error("outcome unknown"));
    const first = await renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Private original launch" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText(/previous research request may have been accepted or charged/i);
    const operation = startInvestigationMock.mock.calls[0][0].operation_id;
    expect(JSON.stringify(window.sessionStorage)).not.toContain("Private original launch");
    first.unmount();
    await renderStart();
    expect(screen.getByLabelText("Research question")).toHaveProperty("value", "");
    expect(document.body.textContent).not.toContain(operation);
    fireEvent.keyDown(screen.getByLabelText("Research question"), { key: "Enter", metaKey: true });
    expect(startInvestigationMock).toHaveBeenCalledTimes(1);
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
    startInvestigationMock.mockImplementation(async (body) => ownerReceipt("inv-after-refresh", body.operation_id));

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
    await mount(<TestRouter><StartResearch /></TestRouter>);
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
    startInvestigationMock.mockImplementation(async (body) => ownerReceipt("inv-7", body.operation_id));
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
    startInvestigationMock.mockImplementation(async (body) => ownerReceipt("inv-9", body.operation_id));
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
    // The actual navigation boundary throws once so received progress remains
    // inspectable. A later explicit Open uses the same real router normally.
    const push = vi.spyOn(navigationHistory, "push").mockImplementation(() => { throw new Error("controlled route publication failure"); });
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "Where do the authors disagree?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(screen.getByText(/Working on it/i)).toBeTruthy());
    expect(screen.getByText(/2 events so far/i)).toBeTruthy();
    expect(screen.getByText(/\$0\.0123/)).toBeTruthy();
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringMatching(/Research started.*could not open/i));
    expect(push).toHaveBeenCalledTimes(1);
    expect(archiveSlot.current?.hasUnresolved()).toBe(false);
    push.mockRestore();
    fireEvent.click(screen.getByRole("button", { name: "Open received investigation" }));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/inv/inv-9"));
    expect(startInvestigationMock).toHaveBeenCalledTimes(1);
  });
});

describe("StartResearch — a failed run is surfaced honestly, never a dead route (M3)", () => {
  it("shows an honest error and does NOT navigate when the stream carries investigation.failed", async () => {
    startInvestigationMock.mockImplementation(async (body) => ownerReceipt("inv-fail", body.operation_id));
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
    // A terminal failed run never authorizes an automatic second paid launch.
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    expect(screen.getByRole("button", { name: "Start a separate paid research" })).toBeTruthy();
    expect(startInvestigationMock).toHaveBeenCalledTimes(1);
  });

  it("keeps the typed question recoverable after a failure (not cleared)", async () => {
    startInvestigationMock.mockImplementation(async (body) => ownerReceipt("inv-fail2", body.operation_id));
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
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Start a separate paid research" }));
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(2));
    const retried = startInvestigationMock.mock.calls[1][0];
    expect(retried.question).toBe(first.question);
    expect(retried.model_choice).toEqual(first.model_choice);
    expect(retried.operation_id).not.toBe(first.operation_id);
  });
});

// These controls use the actual observed history, owner scope and paid path.
// HTTP and stream responses are controlled; this is not native navigation proof.
describe("StartResearch — scoped paid host boundaries", () => {
  it("refuses a same-batch duplicate and conflicting mode switch before POST settles", async () => {
    let finish!: (value: unknown) => void;
    startInvestigationMock.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    await renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "One deliberate paid research" } });
    const ask = screen.getByRole("button", { name: "Ask" });
    const quick = screen.getByRole("button", { name: "Quick Ask · one model request" });
    act(() => { fireEvent.click(ask); fireEvent.click(ask); fireEvent.click(quick); });
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(1));
    expect(quick.getAttribute("aria-pressed")).toBe("false");
    const body = startInvestigationMock.mock.calls[0][0];
    await act(async () => { finish(ownerReceipt("inv-one", body.operation_id)); });
    expect(startInvestigationMock).toHaveBeenCalledTimes(1);
  });

  it("keeps the real Quick draft node mounted through deep receipt and live panel", async () => {
    await mount(<TestRouter><StartResearch /></TestRouter>);
    const quickDraft = await screen.findByLabelText("Quick Ask question");
    fireEvent.change(quickDraft, { target: { value: "Retained Quick question" } });
    fireEvent.click(screen.getByRole("button", { name: "Deep research · multiple model calls" }));
    await choosePaidModel();
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Separate deep question" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByText(/Starting your research|Working on it/)).toBeTruthy());
    expect(quickDraft.isConnected).toBe(true);
    expect(quickDraft).toHaveProperty("value", "Retained Quick question");
    expect(quickDraft.closest("[hidden]")).toBeTruthy();
  });

  it("archives a late valid receipt after same-owner refresh without restoring draft, stream or navigation", async () => {
    let finish!: (value: unknown) => void;
    startInvestigationMock.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    await renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Private retired draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(1));
    const body = startInvestigationMock.mock.calls[0][0];
    const oldScope = auth.modelExecution.readCurrent();
    await act(async () => { await auth.refresh(); });
    expect(auth.modelExecution.readCurrent()).not.toBe(oldScope);
    expect(screen.getByLabelText("Research question")).toHaveProperty("value", "");
    expect(archiveSlot.current?.hasUnresolved()).toBe(true);
    await act(async () => { finish(ownerReceipt("inv-retired", body.operation_id)); });
    await waitFor(() => expect(archiveSlot.current?.hasUnresolved()).toBe(false));
    expect(screen.queryByText(/Starting your research|Working on it/)).toBeNull();
    expect(navigateMock).not.toHaveBeenCalled();
    expect(startInvestigationMock).toHaveBeenCalledTimes(1);
    expect(window.sessionStorage.getItem("antiek.research.unresolved-owner-launch.session.v2")).toBeNull();
  });

  it("does not disclose or restore A's draft across A to B to A verification", async () => {
    await renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "A private body" } });
    authRead.mockImplementation(() => Promise.resolve(json({ ...owner, user_id: "other-owner" })));
    await act(async () => { await auth.refresh(); });
    expect(screen.getByLabelText("Research question")).toHaveProperty("value", "");
    authRead.mockImplementation(() => Promise.resolve(json(owner)));
    await act(async () => { await auth.refresh(); });
    expect(screen.getByLabelText("Research question")).toHaveProperty("value", "");
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });

  it("retains unknown continuity on a malformed current receipt and offers no generic retry", async () => {
    startInvestigationMock.mockResolvedValue({ investigation_id: "not-a-complete-receipt" });
    await renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Validate every owner receipt field" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText(/previous research request may have been accepted or charged/i);
    expect(archiveSlot.current?.hasUnresolved()).toBe(true);
    expect(window.sessionStorage.getItem("antiek.research.unresolved-owner-launch.session.v2")).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    expect(navigateMock).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByLabelText("Research question"), { key: "Enter", metaKey: true });
    expect(startInvestigationMock).toHaveBeenCalledTimes(1);
  });

  it("requires explicit separate paid intent after unknown outcome and preserves the prior hold", async () => {
    startInvestigationMock.mockRejectedValueOnce(new Error("unknown transport outcome"));
    await renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "First paid intent" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText(/previous research request may have been accepted or charged/i);
    const firstOperation = startInvestigationMock.mock.calls[0][0].operation_id;
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "A deliberate separate intent" } });
    fireEvent.keyDown(screen.getByLabelText("Research question"), { key: "Enter", metaKey: true });
    expect(startInvestigationMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Start a separate paid research" }));
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(2));
    const secondOperation = startInvestigationMock.mock.calls[1][0].operation_id;
    expect(secondOperation).not.toBe(firstOperation);
    await waitFor(() => expect(window.sessionStorage.getItem("antiek.research.unresolved-owner-launch.session.v2")).not.toContain(secondOperation));
    expect(window.sessionStorage.getItem("antiek.research.unresolved-owner-launch.session.v2")).toContain(firstOperation);
  });
});

describe("StartResearch — actual history lifetime", () => {
  it("keeps a normal same-home rerender admitted after actual hydration layout", async () => {
    const view = await renderStart();
    const home = homeBinding.readHome();
    expect(home).not.toBeNull();
    view.rerender(<TestRouter><StartResearch /></TestRouter>);
    expect(homeBinding.readHome()).toBe(home);
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Still the same observed home" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(1));
  });

  it("refuses the mounted old handler after PUSH and REPLACE before the React batch commits", async () => {
    await renderStart();
    const input = screen.getByLabelText("Research question");
    fireEvent.change(input, { target: { value: "Do not send from the retired route" } });
    const oldHome = homeBinding.readHome();
    const epoch = readNavigationEpoch();
    act(() => {
      navigationHistory.push("/other");
      navigationHistory.replace("/");
      expect(readNavigationEpoch()).not.toBe(epoch);
      expect(input.isConnected).toBe(true);
      fireEvent.keyDown(input, { key: "Enter", metaKey: true });
    });
    expect(oldHome && homeBinding.isHomeCurrent(oldHome)).toBe(false);
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });

  it("retires the original home on actual POP back to its original history entry", async () => {
    await renderStart();
    const home = homeBinding.readHome();
    const originalKey = navigationHistory.location.key;
    const epoch = readNavigationEpoch();
    await act(async () => {
      navigationHistory.push("/other");
      const popped = new Promise<void>((resolve) => window.addEventListener("popstate", () => resolve(), { once: true }));
      navigationHistory.go(-1);
      await popped;
    });
    expect(navigationHistory.location.key).toBe(originalKey);
    expect(navigationHistory.location.pathname).toBe("/");
    expect(readNavigationEpoch()).not.toBe(epoch);
    expect(home && homeBinding.isHomeCurrent(home)).toBe(false);
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });

  it("refuses a retained real grace callback after leaving and returning home", async () => {
    const timers = vi.spyOn(window, "setTimeout");
    await renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Retire the original grace delivery" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText(/Starting your research/i);
    const timer = timers.mock.calls.find((call) => call[1] === 1500)?.[0];
    if (typeof timer !== "function") throw new Error("actual grace callback was not scheduled");
    act(() => { navigationHistory.push("/other"); navigationHistory.replace("/"); });
    navigateMock.mockClear();
    act(() => { timer(); });
    expect(navigateMock).not.toHaveBeenCalled();
    expect(navigationHistory.location.pathname).toBe("/");
    expect(startInvestigationMock).toHaveBeenCalledTimes(1);
  });

  it("refuses an identical applied REPLACE even though the home URL is unchanged", async () => {
    await renderStart();
    const input = screen.getByLabelText("Research question");
    fireEvent.change(input, { target: { value: "A new replacement is a new lifetime" } });
    const home = homeBinding.readHome();
    act(() => {
      navigationHistory.replace("/");
      fireEvent.keyDown(input, { key: "Enter", metaKey: true });
    });
    expect(home && homeBinding.isHomeCurrent(home)).toBe(false);
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });
});


describe("StartResearch — received delivery failure", () => {
  it("retains the received operation when the actual celebration callback fails", async () => {
    const actualUseCelebrate = delight.useCelebrate;
    vi.spyOn(delight, "useCelebrate").mockImplementation(() => {
      const actual = actualUseCelebrate();
      return { ...actual, celebrate: () => { throw new Error("controlled celebration failure"); } };
    });
    await renderStart();
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "A received research survives UI failure" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringMatching(/Research started.*animation/i));
    expect(archiveSlot.current?.hasUnresolved()).toBe(false);
    expect(window.sessionStorage.getItem("antiek.research.unresolved-owner-launch.session.v2")).toBeNull();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open received investigation" }));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/inv/inv-default"));
    expect(startInvestigationMock).toHaveBeenCalledTimes(1);
  });
});


it("establishes its first home after real ws hydration and its no-publication replacement", async () => {
  navigationHistory.replace(`/?ws=${encodeURIComponent(encodeWsParam(project(EMPTY_SNAPSHOT)))}`);
  const before = getHydrationGeneration();
  await renderStart();
  expect(window.location.search).toBe("");
  expect(window.history.state).toEqual({});
  const home = homeBinding.readHome();
  if (!home) throw new Error("actual home was not established after hydration");
  expect(home.hydrationGeneration).toBeGreaterThan(before);
  expect(home.hydrationGeneration).toBe(getHydrationGeneration());
  fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Start after the real layout restoration" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(1));
});


it("retires pre-clear callbacks during actual delayed ws hydration, then admits a fresh home action", async () => {
  navigationHistory.replace(`/?ws=${encodeURIComponent(encodeWsParam(project(EMPTY_SNAPSHOT)))}`);
  const view = await mount(<TestRouter hydrate={false}><StartResearch /></TestRouter>);
  fireEvent.click(screen.getByRole("button", { name: "Deep research · multiple model calls" }));
  await choosePaidModel();
  const input = screen.getByLabelText("Research question");
  fireEvent.change(input, { target: { value: "The old pre-clear intent" } });
  const oldHome = homeBinding.readHome();
  let attemptedAfterRealHydration = false;
  view.rerender(<TestRouter afterHydration={() => {
    expect(window.location.search).toBe("");
    expect(input.isConnected).toBe(true);
    attemptedAfterRealHydration = true;
    fireEvent.keyDown(input, { key: "Enter", metaKey: true });
  }}><StartResearch /></TestRouter>);
  expect(attemptedAfterRealHydration).toBe(true);
  expect(startInvestigationMock).not.toHaveBeenCalled();
  expect(oldHome && homeBinding.isHomeCurrent(oldHome)).toBe(false);
  await waitFor(() => expect(homeBinding.readHome()).not.toBeNull());
  expect(screen.getByLabelText("Research question")).toBe(input);
  fireEvent.change(input, { target: { value: "A fresh deliberate post-clear intent" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(1));
  expect(startInvestigationMock.mock.calls[0][0].question).toBe("A fresh deliberate post-clear intent");
});

it("keeps explicit separate intent available after editing a known received failure", async () => {
  eventStreamState.current = { status: "open", reconnects: 0, events: [{
    event_id: "received-failure", investigation_id: "inv-default", action_type: "investigation.failed",
    payload: { action_type: "investigation.failed", phase: 1, reason: "Controlled received failure" },
    param_version: "v1", emitted_at: "2026-10-02T00:00:00Z",
  }] };
  await renderStart();
  fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Original received intent" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  await screen.findByText(/Controlled received failure/);
  expect(archiveSlot.current?.hasUnresolved()).toBe(false);
  const firstOperation = startInvestigationMock.mock.calls[0][0].operation_id;
  fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Edited new deliberate intent" } });
  expect(screen.getByRole("button", { name: "Ask" })).toHaveProperty("disabled", true);
  expect(screen.getByText("Start a separate paid research before sending another question.")).toBeTruthy();
  expect(screen.queryByText(/previous research request may have been accepted or charged/i)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Start a separate paid research" }));
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(2));
  expect(startInvestigationMock.mock.calls[1][0].question).toBe("Edited new deliberate intent");
  expect(startInvestigationMock.mock.calls[1][0].operation_id).not.toBe(firstOperation);
});


it("binds the actual scoped picker variant and complete required deep request", async () => {
  fetchUserModelsMock.mockResolvedValue({ models: [{ ...executableModel, model_ids: ["claude-paid", "claude-alt"] }], count: 1, stale_registered: [], source: "test" });
  await renderStart();
  fireEvent.click(screen.getByRole("button", { name: "Model for Ask investigation" }));
  expect(screen.queryByRole("menuitem", { name: /Default.*house/ })).toBeNull();
  fireEvent.click(await screen.findByRole("menuitem", { name: /claude-alt/ }));
  fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "  Choose the second saved variant  " } });
  fireEvent.click(screen.getByRole("radio", { name: "Fast" }));
  fireEvent.click(screen.getByRole("button", { name: "arXiv" }));
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  await waitFor(() => expect(startInvestigationMock).toHaveBeenCalledTimes(1));
  expect(startInvestigationMock.mock.calls[0][0]).toEqual({
    question: "Choose the second saved variant", research_tier: "fast",
    source_policy: ["operator_corpus", "web", "arxiv"],
    model_choice: { authority: "user_model", provider_id: "user-paid", model_id: "claude-alt" },
    operation_id: expect.stringMatching(/^research-/),
  });
});
