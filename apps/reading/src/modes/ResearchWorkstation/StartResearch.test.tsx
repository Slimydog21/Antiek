/**
 * StartResearch.test.tsx — compatibility contract after SPR-08.
 *
 * StartResearch is no longer its own composer. It is a deprecated export that
 * keeps historical imports alive while rendering the single UnifiedSearch
 * research surface.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { ProviderKeysState } from "../../hooks/useProviderKeys";
import type { StartInvestigationState } from "../../hooks/useStartInvestigation";

const { investigationStateRef, providerKeysRef, openDocumentMock } = vi.hoisted(
  () => ({
    openDocumentMock: vi.fn(),
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
  }),
);

vi.mock("../../api/corpusSearch", async (orig) => {
  const actual = await orig<typeof import("../../api/corpusSearch")>();
  return { ...actual, corpusSearch: vi.fn() };
});

vi.mock("../../hooks/useProviderKeys", () => ({
  useProviderKeys: () => providerKeysRef.current,
}));

vi.mock("../../hooks/useStartInvestigation", () => ({
  useStartInvestigation: () => investigationStateRef.current,
}));

vi.mock("../../lib/openDocument", async (orig) => {
  const actual = await orig<typeof import("../../lib/openDocument")>();
  return { ...actual, useOpenDocument: () => openDocumentMock };
});

vi.mock("./MyResearch", () => ({
  default: ({ embedded }: { embedded?: boolean }) => (
    <div data-testid="my-research-log">
      {embedded ? "Embedded research log" : "Standalone research log"}
    </div>
  ),
}));

import StartResearch from "./StartResearch";

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
    submit: vi.fn(),
    reset: vi.fn(),
    ...over,
  };
}

function renderStart(embedded = false) {
  return render(
    <MemoryRouter>
      <StartResearch variant="research" embedded={embedded} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  installMatchMedia(false);
  openDocumentMock.mockReset();
  providerKeysRef.current = {
    status: "ready",
    providers: ["deepseek"],
    refresh: vi.fn(),
  };
  resetInvestigationState();
});

afterEach(() => cleanup());

describe("StartResearch — deprecated UnifiedSearch compatibility", () => {
  it("renders the current research UnifiedSearch home, not the retired composer", () => {
    const { container } = renderStart();

    expect(screen.getByRole("heading", { name: "Search & research" })).toBeTruthy();
    expect(screen.getByLabelText("Unified search")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Research this" })).toBeTruthy();
    expect(container.querySelector("[data-glass-surface]")).toBeTruthy();

    expect(screen.queryByLabelText("Research question")).toBeNull();
    expect(screen.queryByRole("button", { name: "Ask" })).toBeNull();
  });

  it("keeps example prompts on the research landing surface", () => {
    renderStart();

    expect(screen.getByText(/strongest case against this thesis/i)).toBeTruthy();
    expect(screen.getByText(/how this idea evolved/i)).toBeTruthy();
    expect(screen.getByText(/Where do these authors disagree/i)).toBeTruthy();
  });

  it("embedded mode composes the search box above the research log", () => {
    renderStart(true);

    expect(screen.getByTestId("unified-search")).toBeTruthy();
    expect(screen.getByTestId("my-research-log").textContent).toContain(
      "Embedded research log",
    );
  });
});
