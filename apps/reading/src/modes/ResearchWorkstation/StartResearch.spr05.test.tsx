/**
 * StartResearch.spr05.test.tsx — SPR-05 home consolidation after SPR-08.
 *
 * The old voice/link composer was deliberately retired. This file keeps the
 * SPR-05 consolidation executable by proving the compatibility export renders
 * the re-homed UnifiedSearch surface, its contextual voice/cascade affordances,
 * and the embedded research log, with no stale duplicate launch bar.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { StartInvestigationState } from "../../hooks/useStartInvestigation";
import type { ProviderKeysState } from "../../hooks/useProviderKeys";

const { investigationStateRef, providerKeysRef } = vi.hoisted(() => ({
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
  return { ...actual, useOpenDocument: () => vi.fn() };
});

vi.mock("./MyResearch", () => ({
  default: ({ embedded }: { embedded?: boolean }) => (
    <section data-testid="embedded-research-log">
      {embedded ? "Your research" : "Launch bar"}
    </section>
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

function renderHome(embedded = false) {
  return render(
    <MemoryRouter>
      <StartResearch variant="research" embedded={embedded} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  installMatchMedia(false);
  providerKeysRef.current = {
    status: "ready",
    providers: ["deepseek"],
    refresh: vi.fn(),
  };
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
  };
});

afterEach(() => cleanup());

describe("StartResearch — SPR-05 log-as-home consolidation", () => {
  it("embedded home shows the re-homed search composer and research log together", () => {
    renderHome(true);

    expect(screen.getByLabelText("Unified search")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Research this" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Say it instead/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Plan sub-questions" })).toBeTruthy();
    expect(screen.getByTestId("embedded-research-log").textContent).toContain(
      "Your research",
    );
  });

  it("embedded home has no retired link composer or duplicate launch bar", () => {
    renderHome(true);

    expect(screen.queryByLabelText("Research question")).toBeNull();
    expect(screen.queryByLabelText("Attach a link")).toBeNull();
    expect(screen.queryByRole("button", { name: "Ask" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Start a research" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Launch several at once" })).toBeNull();
  });

  it("standalone compatibility render stays composer-only", () => {
    renderHome(false);

    expect(screen.getByLabelText("Unified search")).toBeTruthy();
    expect(screen.queryByTestId("embedded-research-log")).toBeNull();
  });
});
