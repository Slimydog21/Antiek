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
});

describe("UnifiedSearch — M5 honest no-key escalate", () => {
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