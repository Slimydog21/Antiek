import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProviderKeysState } from "../../hooks/useProviderKeys";

const { providerKeysRef, refreshMock } = vi.hoisted(() => ({
  providerKeysRef: {
    current: {
      status: "ready",
      providers: ["deepseek", "anthropic"],
      refresh: vi.fn(),
    } as ProviderKeysState & { refresh: () => void },
  },
  refreshMock: vi.fn(),
}));

vi.mock("../../hooks/useProviderKeys", () => ({
  useProviderKeys: () => providerKeysRef.current,
}));

vi.mock("../../workspace/useViewportTier", () => ({
  useViewportTier: () => "desktop",
}));

import Settings from "./index";

describe("Settings", () => {
  beforeEach(() => {
    refreshMock.mockReset();
    providerKeysRef.current = {
      status: "ready",
      providers: ["deepseek", "anthropic"],
      refresh: refreshMock,
    };
    window.matchMedia = vi.fn((query: string) => ({
      matches: query.includes("prefers-color-scheme"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the live environment and registered provider readout", () => {
    render(<Settings />);

    expect(screen.getByText("Workspace environment")).toBeTruthy();
    expect(screen.getByText("Agentic activation")).toBeTruthy();
    expect(screen.getByText("deepseek")).toBeTruthy();
    expect(screen.getByText("anthropic")).toBeTruthy();
    expect(screen.queryByText(/Settings surface stub/i)).toBeNull();
    expect(screen.getByText("/coordination/cost-consent")).toBeTruthy();
  });

  it("links to trust and privacy controls with plain copy", () => {
    render(<Settings />);

    expect(screen.getByText("Published privacy, deletion, and training commitments")).toBeTruthy();
    expect(screen.getByText("Privacy budgets and deletion controls")).toBeTruthy();
    expect(screen.queryByText(/ε exposure/i)).toBeNull();
    expect(screen.queryByText(/DP budget/i)).toBeNull();
    expect(screen.queryByText(/Substrate-level/i)).toBeNull();
  });

  it("surfaces the no-provider state without pretending agentic work is available", () => {
    providerKeysRef.current = { status: "absent", refresh: refreshMock };

    render(<Settings />);

    expect(screen.getByText("not configured")).toBeTruthy();
    expect(
      screen.getByText(/No model providers are registered/i),
    ).toBeTruthy();
  });

  it("refreshes provider status through the shared health hook", () => {
    render(<Settings />);

    fireEvent.click(screen.getByRole("button", { name: /refresh provider status/i }));

    expect(refreshMock).toHaveBeenCalledTimes(1);
  });
});
