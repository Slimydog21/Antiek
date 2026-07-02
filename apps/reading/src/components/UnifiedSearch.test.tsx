/**
 * UnifiedSearch.test.tsx — antiek-reader SPR-08 M1–M5.
 *
 * Enumerates the six search states (rigor #3) and pins the instant-results
 * latency budget. Escalate is mocked at the hook boundary (cassette-equivalent
 * — no live model calls).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { Event } from "../generated/types";
import type { CorpusSearchHit } from "../api/corpusSearch";
import type { StartInvestigationState } from "../hooks/useStartInvestigation";
import type { ProviderKeysState } from "../hooks/useProviderKeys";
import UnifiedSearch, { INSTANT_RESULTS_LATENCY_BUDGET_MS } from "./UnifiedSearch";

const {
  corpusSearchMock,
  openDocumentMock,
  navigateMock,
  submitMock,
  investigationStateRef,
  providerKeysRef,
} = vi.hoisted(() => ({
  corpusSearchMock: vi.fn(),
  openDocumentMock: vi.fn(),
  navigateMock: vi.fn(),
  submitMock: vi.fn(),
  investigationStateRef: {
    current: {
      startedId: null,
      phase: "idle",
      events: [],
      liveCost: 0,
      failed: false,
      failureReason: null,
      error: null,
      busy: false,
      submit: vi.fn(),
      reset: vi.fn(),
    } as StartInvestigationState,
  },
  providerKeysRef: {
    current: {
      status: "ready" as const,
      providers: ["deepseek"],
      refresh: vi.fn(),
    } as ProviderKeysState & { refresh: () => void },
  },
}));

vi.mock("../api/corpusSearch", async (orig) => {
  const actual = await orig<typeof import("../api/corpusSearch")>();
  return { ...actual, corpusSearch: corpusSearchMock };
});

vi.mock("../hooks/useProviderKeys", () => ({
  useProviderKeys: () => providerKeysRef.current,
}));

vi.mock("../hooks/useStartInvestigation", () => ({
  useStartInvestigation: () => investigationStateRef.current,
}));

vi.mock("../lib/openDocument", async (orig) => {
  const actual = await orig<typeof import("../lib/openDocument")>();
  return {
    ...actual,
    useOpenDocument: () => openDocumentMock,
  };
});

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("../modes/ResearchWorkstation/MyResearch", () => ({
  default: () => <div data-testid="my-research-log">log</div>,
}));

vi.mock("../modes/ResearchWorkstation/VoiceChaseButton", () => ({
  default: ({ onTranscript }: { onTranscript: (transcript: string) => void }) => (
    <button
      type="button"
      onClick={() => onTranscript("spoken research question")}
    >
      Say it instead
    </button>
  ),
}));

vi.mock("../modes/ResearchWorkstation/CascadeProposal", () => ({
  default: ({
    problem,
    onLaunched,
    onFallBackToAsk,
  }: {
    problem: string;
    onLaunched: (sessionId: string) => void;
    onFallBackToAsk: () => void;
  }) => (
    <section data-testid="mock-cascade-proposal">
      <p>Planning: {problem}</p>
      <button type="button" onClick={() => onLaunched("cascade-session-1")}>
        Launch cascade
      </button>
      <button type="button" onClick={onFallBackToAsk}>
        Ask one question instead
      </button>
    </section>
  ),
}));

const hit = (over: Partial<CorpusSearchHit> = {}): CorpusSearchHit => ({
  chunk_id: "c1",
  document_id: "doc-1",
  document_title: "Quantum Book",
  page_index: 4,
  page_resolved: true,
  snippet: "a passage about quantum mechanics",
  similarity: 0.9,
  ...over,
});

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

function renderSearch(variant: "library" | "research" = "library") {
  return render(
    <MemoryRouter>
      <UnifiedSearch variant={variant} themeContext={[]} />
    </MemoryRouter>,
  );
}

function resetInvestigationState(over: Partial<StartInvestigationState> = {}) {
  investigationStateRef.current = {
    startedId: null,
    phase: "idle",
    events: [],
    liveCost: 0,
    failed: false,
    failureReason: null,
    error: null,
    busy: false,
    submit: submitMock,
    reset: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  installMatchMedia(false);
  vi.useFakeTimers({ shouldAdvanceTime: true });
  corpusSearchMock.mockReset();
  openDocumentMock.mockReset();
  navigateMock.mockReset();
  submitMock.mockReset();
  providerKeysRef.current = {
    status: "ready",
    providers: ["deepseek"],
    refresh: vi.fn(),
  };
  resetInvestigationState();
});

afterEach(() => {
  vi.useRealTimers();
  cleanup();
});

describe("UnifiedSearch — M1 instant local hits (no key)", () => {
  it("empty query shows a sensible default, not a spinner that never resolves", () => {
    renderSearch();
    expect(screen.getByTestId("unified-search-empty")).toBeTruthy();
    expect(corpusSearchMock).not.toHaveBeenCalled();
  });

  it("typing returns live local vector results within the latency budget", async () => {
    corpusSearchMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(
            () => resolve({ query: "quantum", hits: [hit()], count: 1 }),
            50,
          );
        }),
    );
    renderSearch();
    fireEvent.change(screen.getByLabelText("Unified search"), {
      target: { value: "quantum" },
    });

    await vi.advanceTimersByTimeAsync(200);
    await screen.findByText("Quantum Book");

    const latencyEl = screen.getByTestId("unified-search-latency");
    const ms = Number(latencyEl.getAttribute("data-latency-ms"));
    expect(ms).toBeLessThanOrEqual(INSTANT_RESULTS_LATENCY_BUDGET_MS);
    expect(corpusSearchMock).toHaveBeenCalledWith("quantum");
  });

  it("zero local hits surfaces an honest empty state", async () => {
    corpusSearchMock.mockResolvedValue({ query: "xyz", hits: [], count: 0 });
    renderSearch();
    fireEvent.change(screen.getByLabelText("Unified search"), { target: { value: "xyz" } });
    await vi.advanceTimersByTimeAsync(200);
    await screen.findByText(/Nothing in your corpus matched/i);
  });

  it("selected file text searches locally and renders hits even with the input left empty", async () => {
    corpusSearchMock.mockResolvedValue({
      query: "file",
      hits: [hit({ document_title: "File-Matched Book" })],
      count: 1,
    });
    renderSearch("research");
    const input = screen.getByLabelText("Unified search") as HTMLInputElement;
    const file = new File(["margin notes about embodied cognition"], "notes.md", {
      type: "text/markdown",
    });

    fireEvent.change(screen.getByLabelText("Choose a file to search by"), {
      target: { files: [file] },
    });

    await waitFor(() =>
      expect(corpusSearchMock).toHaveBeenCalledWith(
        "margin notes about embodied cognition",
      ),
    );
    expect(input.value).toBe("");
    expect(await screen.findByText("File-Matched Book")).toBeTruthy();
    expect(screen.getByTestId("unified-search-signal").textContent).toMatch(
      /books like "notes\.md"/,
    );
  });

  it("dropped file text searches locally and renders hits", async () => {
    corpusSearchMock.mockResolvedValue({
      query: "file",
      hits: [hit({ document_title: "Dropped-File Book" })],
      count: 1,
    });
    renderSearch("library");
    const file = new File(["notes on probabilistic programming"], "drop.txt", {
      type: "text/plain",
    });

    fireEvent.drop(screen.getByTestId("unified-search"), {
      dataTransfer: { files: [file] },
    });

    await waitFor(() =>
      expect(corpusSearchMock).toHaveBeenCalledWith(
        "notes on probabilistic programming",
      ),
    );
    expect(await screen.findByText("Dropped-File Book")).toBeTruthy();
  });
});

describe("UnifiedSearch — M2 Enter escalates (cassette)", () => {
  it("Enter launches research with the same query text", async () => {
    corpusSearchMock.mockResolvedValue({ query: "x", hits: [], count: 0 });
    submitMock.mockResolvedValue("inv-42");
    renderSearch();
    const input = screen.getByLabelText("Unified search");
    fireEvent.change(input, { target: { value: "consciousness and qualia" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() =>
      expect(submitMock).toHaveBeenCalledWith({
        question: "consciousness and qualia",
        researchTier: "deep",
      }),
    );
  });

  it("Research this button escalates without re-entering the query", async () => {
    corpusSearchMock.mockResolvedValue({ query: "x", hits: [], count: 0 });
    submitMock.mockResolvedValue("inv-99");
    renderSearch();
    fireEvent.change(screen.getByLabelText("Unified search"), {
      target: { value: "epistemic humility" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Research this" }));
    await waitFor(() =>
      expect(submitMock).toHaveBeenCalledWith({
        question: "epistemic humility",
        researchTier: "deep",
      }),
    );
  });

  it("escalate stays on the same surface (inline live banner, optional deep link)", () => {
    resetInvestigationState({
      startedId: "inv-live",
      phase: "streaming",
      events: [{ action_type: "dispatch.call", payload: { cost_usd: 0.01 } } as Event],
      liveCost: 0.01,
    });
    renderSearch();
    expect(screen.getByTestId("unified-search-research-live")).toBeTruthy();
    expect(screen.getByText(/Researching/i)).toBeTruthy();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("does not render malformed inline live cost as NaN or Infinity", () => {
    resetInvestigationState({
      startedId: "inv-live",
      phase: "streaming",
      events: [{ action_type: "dispatch.call", payload: { cost_usd: Number.NaN } } as Event],
      liveCost: Number.NaN,
    });

    renderSearch();

    expect(screen.getByTestId("unified-search-research-live")).toBeTruthy();
    expect(document.body.textContent).toContain("$0.0000");
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-/);
  });
});

describe("UnifiedSearch — re-homed research affordances", () => {
  it("voice capture fills the same research query instead of opening another composer", () => {
    renderSearch("research");

    fireEvent.click(screen.getByRole("button", { name: "Say it instead" }));

    expect((screen.getByLabelText("Unified search") as HTMLInputElement).value).toBe(
      "spoken research question",
    );
    expect(screen.queryByLabelText("Research question")).toBeNull();
    expect(screen.queryByRole("button", { name: "Ask" })).toBeNull();
  });

  it("plans a cascade from the same query and lands on the deep-research monitor", () => {
    renderSearch("research");

    fireEvent.change(screen.getByLabelText("Unified search"), {
      target: { value: "map the disagreements across these sources" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Plan sub-questions" }));

    expect(screen.getByTestId("unified-search-cascade-planner")).toBeTruthy();
    expect(screen.getByText(/Planning: map the disagreements/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Launch cascade" }));

    expect(navigateMock).toHaveBeenCalledWith("/deep-research/cascade-session-1");
  });

  it("backs out of cascade planning to the one-shot research path without clearing the query", () => {
    renderSearch("research");

    fireEvent.change(screen.getByLabelText("Unified search"), {
      target: { value: "one focused question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Plan sub-questions" }));
    fireEvent.click(screen.getByRole("button", { name: "Ask one question instead" }));

    expect(screen.queryByTestId("unified-search-cascade-planner")).toBeNull();
    expect((screen.getByLabelText("Unified search") as HTMLInputElement).value).toBe(
      "one focused question",
    );
  });

  it("closes cascade planning when the unified query changes so a stale plan cannot launch", () => {
    renderSearch("research");
    const input = screen.getByLabelText("Unified search");

    fireEvent.change(input, {
      target: { value: "map the disagreements across these sources" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Plan sub-questions" }));
    expect(screen.getByText(/Planning: map the disagreements/i)).toBeTruthy();

    fireEvent.change(input, { target: { value: "new research question" } });

    expect(screen.queryByTestId("unified-search-cascade-planner")).toBeNull();
    expect(screen.queryByText(/Planning: map the disagreements/i)).toBeNull();
  });

  it("does not start one-shot research while the cascade planner is open", () => {
    submitMock.mockResolvedValue("inv-one-shot");
    renderSearch("research");
    const input = screen.getByLabelText("Unified search");

    fireEvent.change(input, {
      target: { value: "map the disagreements across these sources" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Plan sub-questions" }));

    expect(
      (screen.getByRole("button", { name: "Research this" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    fireEvent.keyDown(input, { key: "Enter" });

    expect(submitMock).not.toHaveBeenCalled();
  });

  it("keeps voice and cascade affordances off the library search variant", () => {
    renderSearch("library");

    expect(screen.queryByRole("button", { name: "Say it instead" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Plan sub-questions" })).toBeNull();
  });
});

describe("UnifiedSearch — M3 every result opens via openDocument", () => {
  it("clicking a local hit opens the Reader at chunk + page", async () => {
    corpusSearchMock.mockResolvedValue({ query: "q", hits: [hit()], count: 1 });
    renderSearch();
    fireEvent.change(screen.getByLabelText("Unified search"), { target: { value: "q" } });
    await vi.advanceTimersByTimeAsync(200);
    await screen.findByText("Quantum Book");
    fireEvent.click(screen.getByText("Quantum Book").closest("button")!);
    expect(openDocumentMock).toHaveBeenCalledWith("doc-1", {
      page: 4,
      chunkId: "c1",
    });
  });

  it.each([
    { page_index: 4.5, label: "fractional" },
    { page_index: 9007199254740992, label: "unsafe" },
  ])("does not pass a $label local hit page index to openDocument", async ({ page_index }) => {
    corpusSearchMock.mockResolvedValue({
      query: "q",
      hits: [hit({ page_index })],
      count: 1,
    });
    renderSearch();
    fireEvent.change(screen.getByLabelText("Unified search"), { target: { value: "q" } });
    await vi.advanceTimersByTimeAsync(200);
    await screen.findByText("Quantum Book");

    expect(screen.getByText(/open the book/i)).toBeTruthy();
    fireEvent.click(screen.getByText("Quantum Book").closest("button")!);
    expect(openDocumentMock).toHaveBeenCalledWith("doc-1", {
      chunkId: "c1",
    });
  });

  it("clicking a research source opens the same Reader door", async () => {
    resetInvestigationState({
      startedId: "inv-src",
      phase: "streaming",
      events: [
        {
          action_type: "dispatch.call",
          event_id: "e1",
          investigation_id: "inv-src",
          param_version: "1",
          emitted_at: "2026-01-01T00:00:00Z",
          payload: {
            document_id: "doc-web-1",
            document_title: "A Web Source",
            chunk_id: "chunk-9",
            snippet: "from the web",
          },
        } as unknown as Event,
      ],
    });
    renderSearch();
    await screen.findByText("A Web Source");
    fireEvent.click(screen.getByText("A Web Source").closest("button")!);
    expect(openDocumentMock).toHaveBeenCalledWith("doc-web-1", { chunkId: "chunk-9" });
  });

  it("drops malformed research source payloads instead of minting Reader links", async () => {
    resetInvestigationState({
      startedId: "inv-src",
      phase: "streaming",
      events: [
        {
          action_type: "dispatch.call",
          event_id: "bad-empty-doc",
          investigation_id: "inv-src",
          param_version: "1",
          emitted_at: "2026-01-01T00:00:00Z",
          payload: {
            document_id: "   ",
            document_title: "Should not render",
            chunk_id: "bad-chunk",
            snippet: "bad source",
          },
        } as unknown as Event,
        {
          action_type: "dispatch.call",
          event_id: "bad-array-payload",
          investigation_id: "inv-src",
          param_version: "1",
          emitted_at: "2026-01-01T00:00:01Z",
          payload: [] as unknown as Event["payload"],
        } as unknown as Event,
        {
          action_type: "dispatch.call",
          event_id: "valid-source",
          investigation_id: "inv-src",
          param_version: "1",
          emitted_at: "2026-01-01T00:00:02Z",
          payload: {
            source_document_id: " doc-web-valid ",
            title: "  Valid Web Source  ",
            chunk_id: "  ",
            snippet: 42,
          },
        } as unknown as Event,
      ],
    });
    renderSearch();

    await screen.findByText("Valid Web Source");
    expect(screen.queryByText("Should not render")).toBeNull();
    fireEvent.click(screen.getByText("Valid Web Source").closest("button")!);
    expect(openDocumentMock).toHaveBeenCalledWith("doc-web-valid", undefined);
  });

  it("clears stale research source hits when the live stream no longer contains sources", async () => {
    resetInvestigationState({
      startedId: "inv-src",
      phase: "streaming",
      events: [
        {
          action_type: "dispatch.call",
          event_id: "source",
          investigation_id: "inv-src",
          param_version: "1",
          emitted_at: "2026-01-01T00:00:00Z",
          payload: {
            document_id: "doc-web-stale",
            document_title: "Stale Web Source",
          },
        } as unknown as Event,
      ],
    });
    const { rerender } = renderSearch();
    await screen.findByText("Stale Web Source");

    resetInvestigationState({
      startedId: "inv-src",
      phase: "streaming",
      events: [],
    });
    rerender(
      <MemoryRouter>
        <UnifiedSearch variant="library" themeContext={[]} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.queryByText("Stale Web Source")).toBeNull());
  });
});

describe("UnifiedSearch — M5 honest no-key escalate", () => {
  it("while the provider probe is loading, local search works but escalation stays inert", async () => {
    providerKeysRef.current = { status: "loading", refresh: vi.fn() };
    corpusSearchMock.mockResolvedValue({
      query: "stoic",
      hits: [hit({ document_title: "Stoic Text" })],
      count: 1,
    });
    renderSearch();
    const input = screen.getByLabelText("Unified search");
    fireEvent.change(input, { target: { value: "stoic" } });
    expect((screen.getByRole("button", { name: "Research this" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.keyDown(input, { key: "Enter" });

    await vi.advanceTimersByTimeAsync(200);
    await screen.findByText("Stoic Text");
    await vi.runOnlyPendingTimersAsync();
    expect(submitMock).not.toHaveBeenCalled();
  });

  it("with no provider key, local search still works", async () => {
    providerKeysRef.current = { status: "absent", refresh: vi.fn() };
    corpusSearchMock.mockResolvedValue({
      query: "stoic",
      hits: [hit({ document_title: "Stoic Text" })],
      count: 1,
    });
    renderSearch();
    fireEvent.change(screen.getByLabelText("Unified search"), { target: { value: "stoic" } });
    await vi.advanceTimersByTimeAsync(200);
    await screen.findByText("Stoic Text");
    expect(submitMock).not.toHaveBeenCalled();
  });

  it("with no provider key, Enter shows needs-key state (not a silent no-op)", async () => {
    providerKeysRef.current = { status: "absent", refresh: vi.fn() };
    renderSearch();
    const input = screen.getByLabelText("Unified search");
    fireEvent.change(input, { target: { value: "agentic test query" } });
    await waitFor(() => expect(screen.getByTestId("unified-search-needs-key")).toBeTruthy());
    fireEvent.keyDown(input, { key: "Enter" });
    const panel = screen.getByTestId("unified-search-needs-key");
    expect(panel.textContent).toMatch(/activation SPR-03/i);
    expect(submitMock).not.toHaveBeenCalled();
  });
});

describe("UnifiedSearch — rigor #3 enumerated states", () => {
  it("slow local search does not block the input or hang silently", async () => {
    let resolveSlow!: (v: unknown) => void;
    corpusSearchMock.mockReturnValue(
      new Promise((resolve) => {
        resolveSlow = resolve;
      }),
    );
    renderSearch();
    const input = screen.getByLabelText("Unified search") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "slow" } });
    await vi.advanceTimersByTimeAsync(200);
    expect(screen.getByText(/Searching locally/i)).toBeTruthy();
    expect(input.disabled).toBe(false);

    resolveSlow({ query: "slow", hits: [hit()], count: 1 });
    await screen.findByText("Quantum Book");
  });

  it("query can surface both local hits and research sources together", async () => {
    corpusSearchMock.mockResolvedValue({ query: "both", hits: [hit()], count: 1 });
    resetInvestigationState({
      startedId: "inv-both",
      phase: "streaming",
      events: [
        {
          action_type: "dispatch.call",
          event_id: "e2",
          investigation_id: "inv-both",
          param_version: "1",
          emitted_at: "2026-01-01T00:00:00Z",
          payload: {
            document_id: "doc-web-2",
            document_title: "Web Hit",
            chunk_id: "c-web",
            snippet: "web snippet",
          },
        } as unknown as Event,
      ],
    });
    renderSearch();
    fireEvent.change(screen.getByLabelText("Unified search"), { target: { value: "both" } });
    await vi.advanceTimersByTimeAsync(200);
    await screen.findByText("Quantum Book");
    expect(screen.getByText("Web Hit")).toBeTruthy();
  });

  it("denied-document servability is enforced only via openDocument (no legacy renderer)", async () => {
    corpusSearchMock.mockResolvedValue({
      query: "gated",
      hits: [hit({ document_id: "doc-gated", document_title: "Gated Work" })],
      count: 1,
    });
    renderSearch();
    fireEvent.change(screen.getByLabelText("Unified search"), { target: { value: "gated" } });
    await vi.advanceTimersByTimeAsync(200);
    await screen.findByText("Gated Work");
    fireEvent.click(screen.getByText("Gated Work").closest("button")!);
    expect(openDocumentMock).toHaveBeenCalledWith("doc-gated", {
      page: 4,
      chunkId: "c1",
    });
    // §9.0 deny panel is BookReader's job — UnifiedSearch must not open PdfViewer/MasterMdViewer.
  });

  it("after investigation failure, input re-enables and local search works again", async () => {
    resetInvestigationState({
      startedId: "inv-fail",
      phase: "failed",
      failed: true,
      failureReason: "investigation.failed",
      events: [],
    });
    corpusSearchMock.mockResolvedValue({ query: "retry", hits: [hit()], count: 1 });
    renderSearch();
    const input = screen.getByLabelText("Unified search") as HTMLInputElement;
    expect(input.disabled).toBe(false);
    fireEvent.change(input, { target: { value: "retry" } });
    await vi.advanceTimersByTimeAsync(200);
    await screen.findByText("Quantum Book");
  });

  it("theme context folds into the local query when present", async () => {
    corpusSearchMock.mockResolvedValue({ query: "x", hits: [], count: 0 });
    render(
      <MemoryRouter>
        <UnifiedSearch variant="library" themeContext={["determinism", "agency"]} />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText("Unified search"), { target: { value: "free will" } });
    await vi.advanceTimersByTimeAsync(200);
    await waitFor(() => expect(corpusSearchMock).toHaveBeenCalled());
    const q = corpusSearchMock.mock.calls[0][0] as string;
    expect(q).toContain("free will");
    expect(q).toContain("determinism");
  });
});
