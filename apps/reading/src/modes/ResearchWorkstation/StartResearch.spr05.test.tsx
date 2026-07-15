/**
 * StartResearch.spr05.test.tsx — the SPR-05 home additions on top of the
 * shipped composer: VOICE + ATTACHMENT inputs (M1), the attachment-only
 * DERIVED prompt (M1 operator decision), and the LOG-AS-HOME consolidation
 * (M3 — composer ABOVE the MyResearch log, rows navigating to /inv/{id}).
 *
 * The base composer behaviour (Ask / tier / cascade toggle / felt-AI) is
 * pinned in StartResearch.test.tsx; this file pins ONLY the SPR-05 surface so
 * each file stays a focused unit. The shipped seams are mocked at their
 * boundaries: the start path (startInvestigation), the event stream, the
 * voice recorder + transcriber (VoiceChaseButton's seams), the ingest calls
 * (PasteIngest's seams), and — for the embedded log — the substrate list +
 * budget contract + auth that MyResearch reads.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { Event } from "../../generated/types";
import type { InvestigationSummary } from "../../lib/api";

const {
  startInvestigationMock,
  ingestSourceMock,
  ingestVoiceNoteMock,
  transcribeAudioMock,
  navigateMock,
  recorderState,
  listState,
  authState,
} = vi.hoisted(() => ({
  startInvestigationMock: vi.fn(),
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
  authState: { current: { status: "authenticated" as const } },
}));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    startInvestigation: startInvestigationMock,
    ingestSource: ingestSourceMock,
    ingestVoiceNote: ingestVoiceNoteMock,
    transcribeAudio: transcribeAudioMock,
  };
});

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
vi.mock("../../lib/auth", async (orig) => {
  const actual = await orig<typeof import("../../lib/auth")>();
  return { ...actual, useAuth: () => ({ state: authState.current }) };
});

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

import StartResearch from "./StartResearch";

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
  startInvestigationMock.mockReset();
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
  authState.current = { status: "authenticated" };
});
afterEach(() => cleanup());

function renderHome(embedded = false) {
  return render(
    <MemoryRouter>
      <StartResearch embedded={embedded} />
    </MemoryRouter>,
  );
}

describe("StartResearch — voice fills the prompt (SPR-05 M1)", () => {
  it("a transcribed voice note becomes the prompt text and enables Ask", async () => {
    transcribeAudioMock.mockResolvedValue({
      transcript: "Trace how this idea evolved across the corpus.",
      language: "en",
      duration_seconds: 4,
    });
    const { rerender } = renderHome();
    // Simulate a finished recording: VoiceChaseButton transcribes on the
    // state→stopped + blob transition.
    recorderState.current = {
      ...recorderState.current,
      state: "stopped",
      blob: new Blob(["x"], { type: "audio/webm" }),
    };
    rerender(
      <MemoryRouter>
        <StartResearch />
      </MemoryRouter>,
    );
    await waitFor(() => expect(transcribeAudioMock).toHaveBeenCalled());
    const input = (await screen.findByLabelText("Research question")) as HTMLTextAreaElement;
    await waitFor(() => expect(input.value).toMatch(/Trace how this idea evolved/i));
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("a transcription failure surfaces an honest error and leaves the prompt untouched (no hallucinated text)", async () => {
    const { ApiError } = await import("../../lib/api");
    transcribeAudioMock.mockRejectedValue(new ApiError("no key", 503, ""));
    const { rerender } = renderHome();
    recorderState.current = {
      ...recorderState.current,
      state: "stopped",
      blob: new Blob(["x"], { type: "audio/webm" }),
    };
    rerender(
      <MemoryRouter>
        <StartResearch />
      </MemoryRouter>,
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
    renderHome();
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
    renderHome();
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
    renderHome();
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
    renderHome();
    const link = screen.getByLabelText("Attach a link");
    fireEvent.change(link, { target: { value: "https://blocked.example/z" } });
    fireEvent.keyDown(link, { key: "Enter" });
    expect(await screen.findByText(/Couldn’t absorb that/i)).toBeTruthy();
    expect(screen.queryByText(/fetch blocked/i)).toBeNull();
  });
});

describe("StartResearch — log-as-home consolidation (SPR-05 M3)", () => {
  it("embedded home shows the composer AND the research log together", async () => {
    listState.current.investigations = [
      inv({ investigation_id: "inv-past1", question: "A finished research" }),
    ];
    renderHome(true);
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
    renderHome(true);
    const row = (await screen.findByText("Click me")).closest("a") as HTMLAnchorElement;
    expect(row.getAttribute("href")).toBe("/inv/inv-go");
  });

  it("the embedded log does NOT render a second 'Start a research' launch bar (one entry only)", () => {
    listState.current.investigations = [inv({ investigation_id: "inv-x" })];
    renderHome(true);
    // The composer's Ask is the single entry; the MyResearch LaunchBar
    // ("Start a research" / "Launch several at once") is suppressed when embedded.
    expect(screen.queryByRole("button", { name: "Start a research" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Launch several at once" })).toBeNull();
  });

  it("standalone (non-embedded) home shows the composer but NOT the log (composer-only)", () => {
    listState.current.investigations = [inv({ investigation_id: "inv-hidden", question: "Hidden in standalone" })];
    renderHome(false);
    expect(screen.getByLabelText("Research question")).toBeTruthy();
    // No embedded log section in the bare composer.
    expect(screen.queryByText("Your research")).toBeNull();
    expect(screen.queryByText("Hidden in standalone")).toBeNull();
  });
});
