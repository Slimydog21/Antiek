/**
 * StartResearch.spr05.test.tsx — the SPR-05 home additions on top of the
 * shipped composer: VOICE + ATTACHMENT inputs (M1), the attachment-only
 * DERIVED prompt (M1 operator decision), and the LOG-AS-HOME consolidation
 * (M3 — composer ABOVE the MyResearch log, rows navigating to /inv/{id}).
 *
 * The base composer behaviour (Ask / tier / cascade toggle / felt-AI) is
 * pinned in StartResearch.test.tsx; this file pins ONLY the SPR-05 surface so
 * each file stays a focused unit. Auth, controller, picker and API are real;
 * HTTP responses, stream, recorder and embedded list/budget seams are
 * controlled. No fixture receipt proves a provider run or native recording.
 */
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { unstable_HistoryRouter as HistoryRouter, useLocation } from "react-router-dom";
import { initializeNavigationHistory, type NavigationHistory } from "../../workspace/navigationLifetime";
import { useWorkspaceHydration } from "../../workspace/useWorkspaceHydration";
import { AuthProvider, useAuth, type AuthContextValue } from "../../lib/auth";

import type { Event } from "../../generated/types";
import type { InvestigationSummary } from "../../lib/api";

const {
  startInvestigationMock,
  fetchUserModelsMock,
  ingestSourceMock,
  ingestVoiceNoteMock,
  transcribeAudioMock,
  navigateMock,
  recorderState,
  listState,
} = vi.hoisted(() => ({
  startInvestigationMock: vi.fn(),
  fetchUserModelsMock: vi.fn(),
  ingestSourceMock: vi.fn(),
  ingestVoiceNoteMock: vi.fn(),
  transcribeAudioMock: vi.fn(),
  navigateMock: vi.fn(),
  // Mutable recorder mock state — drives VoiceChaseButton's capture effect.
  recorderState: {
    current: {
      state: "idle" as "idle" | "recording" | "stopped" | "denied",
      blob: null as Blob | null,
      error: null as string | null,
      start: vi.fn(),
      stop: vi.fn(),
      reset: vi.fn(),
    },
  },
  listState: {
    current: {
      investigations: [] as InvestigationSummary[],
      loading: false,
      error: null as string | null,
      refetch: () => {},
    },
  },
}));

vi.mock("../../hooks/useEventStream", () => ({
  useEventStream: () => ({ events: [] as Event[], status: "closed", reconnects: 0 }),
}));

// VoiceChaseButton drives capture off useVoiceRecorder; control it per-test.
vi.mock("../../hooks/useVoiceRecorder", () => ({
  useVoiceRecorder: () => recorderState.current,
}));

// MyResearch (embedded log) seams — keep offline + deterministic.
vi.mock("../../hooks/useInvestigationList", () => ({
  useInvestigationList: () => listState.current,
}));
vi.mock("../../api/research", async (orig) => {
  const actual = await orig<typeof import("../../api/research")>();
  return {
    ...actual,
    getBudgetDefaults: () =>
      Promise.resolve({ per_research_cost_usd: 0.5, per_research_max_steps: 50, host_local_max_concurrency: 20 }),
    getSuggestions: () => Promise.resolve({ count: 0, suggestions: [] }),
  };
});
import StartResearch, { useResearchHomeBinding } from "./StartResearch";

// Actual auth, controller, scoped picker, QuickAsk and API. Recorder and list
// seams remain controlled; HTTP receipts below do not prove provider execution.
let auth: AuthContextValue;
let navigationHistory: NavigationHistory;
let homeBinding: ReturnType<typeof useResearchHomeBinding>;
function HydratedHome({ children }: { children: ReactNode }) {
  useWorkspaceHydration();
  homeBinding = useResearchHomeBinding();
  const location = useLocation();
  useEffect(() => { if (location.pathname !== "/") navigateMock(location.pathname); }, [location.pathname, location.key]);
  return <>{children}</>;
}
function TestRouter({ children }: { children: ReactNode }) {
  return <HistoryRouter history={navigationHistory}><HydratedHome>{children}</HydratedHome></HistoryRouter>;
}
const authRead = vi.fn();
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
function AuthProbe() { auth = useAuth(); return null; }
function installTransport() {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input), "http://fixture").pathname;
    if (path.endsWith("/auth/me")) return authRead();
    if (path.endsWith("/settings/models/user")) return json(await fetchUserModelsMock());
    if (path.endsWith("/settings/usage") || path.includes("/settings/balance/")) return json({ reason: "fixture_metrics_unavailable" }, 503);
    if (path.endsWith("/research/quick-ask/models")) return json({ count: 0, models: [] });
    if (path.endsWith("/research/quick-ask/recent")) return json({ operations: [] });
    if (path.endsWith("/sources/ingest")) return json(await ingestSourceMock(JSON.parse(String(init?.body))));
    if (path.endsWith("/voice-notes/ingest")) return json(await ingestVoiceNoteMock(JSON.parse(String(init?.body))));
    if (path.endsWith("/voice/transcribe")) return json(await transcribeAudioMock(init?.body));
    if (path.endsWith("/investigations") && init?.method === "POST") return json(await startInvestigationMock(JSON.parse(String(init.body))));
    throw new Error(`Unexpected controlled HTTP ${init?.method ?? "GET"} ${path}`);
  }));
}


const executableModel = {
  id: "user-paid", provider_kind: "anthropic", provider_catalog_id: "anthropic",
  model_id: "claude-paid", display_name: "Paid Claude", base_url: null,
  enabled: true, key_present: true, registered: true, route_eligible: true,
  pricing_status: "known", hard_ceiling_eligible: true,
  execution_status: "executable", rate_snapshot: "rates-2026-08",
};

// AMS2-SPR-03: the idle home wraps its content column in GlassSurface, which
// reads prefers-reduced-motion via window.matchMedia — absent in jsdom. Stub it
// (no reduced motion → glass path). Mirrors the AppShell + GlassSurface suites'
// stub; an environment dependency of the rendered primitive, not a weakening.
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

function inv(over: Partial<InvestigationSummary> & { investigation_id: string }): InvestigationSummary {
  return {
    question: "A past research",
    status: "completed",
    started_at: new Date().toISOString(),
    completed_at: null,
    cost_usd_total: 0,
    parent_investigation_id: null,
    ...over,
  };
}

beforeEach(() => {
  installMatchMedia(false);
  navigationHistory = initializeNavigationHistory(window);
  navigationHistory.replace("/");
  window.sessionStorage.clear();
  startInvestigationMock.mockReset();
  fetchUserModelsMock.mockReset();
  fetchUserModelsMock.mockResolvedValue({ models: [executableModel], count: 1, stale_registered: [], source: "test" });
  ingestSourceMock.mockReset();
  ingestVoiceNoteMock.mockReset();
  transcribeAudioMock.mockReset();
  navigateMock.mockReset();
  recorderState.current = {
    state: "idle",
    blob: null,
    error: null,
    start: vi.fn(),
    stop: vi.fn(),
    reset: vi.fn(),
  };
  listState.current = { investigations: [], loading: false, error: null, refetch: () => {} };
  authRead.mockReset();
  authRead.mockImplementation(() => Promise.resolve(json({ user_id: "spr05-owner", email: null, auth_method: "antiek_session_cookie" })));
  installTransport();
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function renderHome(embedded = false) {
  const view = render(
    <AuthProvider><AuthProbe /><TestRouter>
      <StartResearch embedded={embedded} />
    </TestRouter></AuthProvider>,
  );
  await waitFor(() => expect(auth.state.status).toBe("authenticated"));
  await waitFor(() => expect(homeBinding.readHome()).not.toBeNull());
  fireEvent.click(screen.getByRole("button", { name: "Deep research · multiple model calls" }));
  const picker = await screen.findByRole("button", { name: "Model for Ask investigation" });
  await waitFor(() => expect(picker.hasAttribute("disabled")).toBe(false));
  fireEvent.click(picker);
  fireEvent.click(screen.queryByRole("menuitem", { name: /claude-paid/ }) ?? await screen.findByRole("menuitem", { name: /Paid Claude/ }));
  return { ...view, rerender: (next: ReactNode) => view.rerender(<AuthProvider><AuthProbe />{next}</AuthProvider>) };
}

describe("StartResearch — voice fills the prompt (SPR-05 M1)", () => {
  it("a transcribed voice note becomes the prompt text and enables Ask", async () => {
    transcribeAudioMock.mockResolvedValue({
      transcript: "Trace how this idea evolved across the corpus.",
      language: "en",
      duration_seconds: 4,
    });
    const { rerender } = await renderHome();
    // Simulate a finished recording: VoiceChaseButton transcribes on the
    // state→stopped + blob transition.
    recorderState.current = {
      ...recorderState.current,
      state: "stopped",
      blob: new Blob(["x"], { type: "audio/webm" }),
    };
    rerender(
      <TestRouter>
        <StartResearch />
      </TestRouter>,
    );
    await waitFor(() => expect(transcribeAudioMock).toHaveBeenCalled());
    const input = (await screen.findByLabelText("Research question")) as HTMLTextAreaElement;
    await waitFor(() => expect(input.value).toMatch(/Trace how this idea evolved/i));
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("a transcription failure surfaces an honest error and leaves the prompt untouched (no hallucinated text)", async () => {
    const { ApiError } = await import("../../lib/api");
    transcribeAudioMock.mockRejectedValue(new ApiError("no key", 503, ""));
    const { rerender } = await renderHome();
    recorderState.current = {
      ...recorderState.current,
      state: "stopped",
      blob: new Blob(["x"], { type: "audio/webm" }),
    };
    rerender(
      <TestRouter>
        <StartResearch />
      </TestRouter>,
    );
    // VoiceChaseButton's honest no-key failure, never a fabricated transcript.
    expect(await screen.findByText(/Couldn’t turn that into a question/i)).toBeTruthy();
    // The composer is still there, and the prompt was NEVER filled with
    // hallucinated text — the failed transcription left it empty.
    const input = screen.getByLabelText("Research question") as HTMLTextAreaElement;
    expect(input.value).toBe("");
    // Ask stays disabled (nothing to ask).
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("StartResearch — attach a file/link (SPR-05 M1)", () => {
  it("pasting a link absorbs it via ingestSource (no investigation_id on the home) and reports it", async () => {
    ingestSourceMock.mockResolvedValue({
      status: "ingested",
      detected_kind: "url",
      document_id: "doc-1",
      document_loaded_event_id: "e1",
      chunks_written: 5,
      skipped_reason: null,
      error_message: null,
      title: "A Useful Paper",
      episodes_processed: 0,
      episodes_ingested: 0,
    });
    await renderHome();
    const link = screen.getByLabelText("Attach a link");
    fireEvent.change(link, { target: { value: "https://arxiv.org/abs/2401.00001" } });
    fireEvent.keyDown(link, { key: "Enter" });
    await waitFor(() =>
      expect(ingestSourceMock).toHaveBeenCalledWith(
        expect.objectContaining({ url: "https://arxiv.org/abs/2401.00001" }),
      ),
    );
    // Crucially: NO investigation_id is sent from the home (there's no run yet).
    // The backend bins an investigation_id-less ingest to the `__operator__`
    // corpus sentinel (interfaces/research/api/app.py), NOT the run launched
    // next — so the home copy says "Added to your corpus", never "cited when
    // this research runs" (a maintainer must not "fix" this by passing a wrong
    // id; binding the doc to the run is the documented SPR-05 follow-up).
    expect(ingestSourceMock.mock.calls[0][0]).not.toHaveProperty("investigation_id");
    expect(await screen.findByText(/Added “A Useful Paper” to your corpus/i)).toBeTruthy();
  });

  it("attachment-only with an empty prompt DERIVES an editable prompt, labelled as derived (operator decision)", async () => {
    ingestSourceMock.mockResolvedValue({
      status: "ingested",
      detected_kind: "url",
      document_id: "doc-2",
      document_loaded_event_id: "e2",
      chunks_written: 3,
      skipped_reason: null,
      error_message: null,
      title: "The Source",
      episodes_processed: 0,
      episodes_ingested: 0,
    });
    await renderHome();
    const input = screen.getByLabelText("Research question") as HTMLTextAreaElement;
    expect(input.value).toBe(""); // empty prompt to start
    const link = screen.getByLabelText("Attach a link");
    fireEvent.change(link, { target: { value: "https://example.com/x" } });
    fireEvent.keyDown(link, { key: "Enter" });
    // The empty prompt is filled with a sensible derived prompt, not blocked.
    await waitFor(() => expect(input.value).toMatch(/Understand and distill .*The Source/i));
    // …and it is honestly LABELLED as derived (not silently chosen).
    expect(screen.getByText(/Prompt suggested from your attachment/i)).toBeTruthy();
    // The derived prompt enables Ask (so attachment-only is genuinely runnable).
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("does NOT overwrite a prompt the operator already typed", async () => {
    ingestVoiceNoteMock.mockResolvedValue({ title: "note", document_id: "d", chunks_written: 1 });
    await renderHome();
    const input = screen.getByLabelText("Research question") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "My own question about the thesis" } });
    const link = screen.getByLabelText("Attach a link");
    fireEvent.change(link, { target: { value: "https://example.com/y" } });
    fireEvent.keyDown(link, { key: "Enter" });
    await waitFor(() => expect(ingestSourceMock).toHaveBeenCalled());
    // The operator's prompt is preserved; nothing derived over it.
    expect(input.value).toBe("My own question about the thesis");
    expect(screen.queryByText(/Prompt suggested from your attachment/i)).toBeNull();
  });

  it("surfaces an ingest failure honestly, not silently", async () => {
    ingestSourceMock.mockResolvedValue({
      status: "error",
      detected_kind: "url",
      document_id: null,
      document_loaded_event_id: null,
      chunks_written: 0,
      skipped_reason: null,
      error_message: "fetch blocked",
      title: null,
      episodes_processed: 0,
      episodes_ingested: 0,
    });
    await renderHome();
    const link = screen.getByLabelText("Attach a link");
    fireEvent.change(link, { target: { value: "https://blocked.example/z" } });
    fireEvent.keyDown(link, { key: "Enter" });
    expect(await screen.findByText(/Couldn’t absorb that/i)).toBeTruthy();
  });
});

describe("StartResearch — log-as-home consolidation (SPR-05 M3)", () => {
  it("embedded home shows the composer AND the research log together", async () => {
    listState.current.investigations = [
      inv({ investigation_id: "inv-past1", question: "A finished research" }),
    ];
    await renderHome(true);
    // The composer (start a research) is present…
    expect(screen.getByLabelText("Research question")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ask" })).toBeTruthy();
    // …AND the log below it (the embedded MyResearch heading + a past row).
    expect(await screen.findByText("Your research")).toBeTruthy();
    expect(screen.getByText("A finished research")).toBeTruthy();
  });

  it("a project row links to that project's workstation (/inv/{id})", async () => {
    listState.current.investigations = [
      inv({ investigation_id: "inv-go", question: "Click me" }),
    ];
    await renderHome(true);
    const row = (await screen.findByText("Click me")).closest("a") as HTMLAnchorElement;
    expect(row.getAttribute("href")).toBe("/inv/inv-go");
  });

  it("the embedded log does NOT render a second 'Start a research' launch bar (one entry only)", async () => {
    listState.current.investigations = [inv({ investigation_id: "inv-x" })];
    await renderHome(true);
    // The composer's Ask is the single entry; the MyResearch LaunchBar
    // ("Start a research" / "Launch several at once") is suppressed when embedded.
    expect(screen.queryByRole("button", { name: "Start a research" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Launch several at once" })).toBeNull();
  });

  it("standalone (non-embedded) home shows the composer but NOT the log (composer-only)", async () => {
    listState.current.investigations = [inv({ investigation_id: "inv-hidden", question: "Hidden in standalone" })];
    await renderHome(false);
    expect(screen.getByLabelText("Research question")).toBeTruthy();
    // No embedded log section in the bare composer.
    expect(screen.queryByText("Your research")).toBeNull();
    expect(screen.queryByText("Hidden in standalone")).toBeNull();
  });
});

// Held responses are controlled HTTP completion, not a live ingest/provider run.
describe("StartResearch — delayed source-derived draft admission", () => {
  it("preserves a newer typed question and refuses late ingest UI after its captured draft retired", async () => {
    let finish!: (value: unknown) => void;
    ingestSourceMock.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    await renderHome();
    const link = screen.getByLabelText("Attach a link");
    fireEvent.change(link, { target: { value: "https://example.com/held" } });
    fireEvent.keyDown(link, { key: "Enter" });
    await waitFor(() => expect(ingestSourceMock).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText("Research question"), { target: { value: "Newer deliberate question" } });
    await act(async () => { finish({ status: "ingested", title: "Retired attachment" }); });
    expect(screen.getByLabelText("Research question")).toHaveProperty("value", "Newer deliberate question");
    expect(screen.queryByText(/Added “Retired attachment”/)).toBeNull();
    expect(ingestSourceMock).toHaveBeenCalledTimes(1);
  });

  it("refuses a held transcription after actual owner verification retires its original scope", async () => {
    let finish!: (value: unknown) => void;
    transcribeAudioMock.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const { rerender } = await renderHome();
    recorderState.current = { ...recorderState.current, state: "stopped", blob: new Blob(["controlled-audio"], { type: "audio/webm" }) };
    rerender(<TestRouter><StartResearch /></TestRouter>);
    await waitFor(() => expect(transcribeAudioMock).toHaveBeenCalledTimes(1));
    await act(async () => { await auth.refresh(); });
    await act(async () => { finish({ transcript: "Old owner transcript", language: "en", duration_seconds: 1 }); });
    expect(screen.getByLabelText("Research question")).toHaveProperty("value", "");
    expect(transcribeAudioMock).toHaveBeenCalledTimes(1);
    expect(startInvestigationMock).not.toHaveBeenCalled();
  });
});
