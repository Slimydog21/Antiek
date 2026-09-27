/**
 * InvestigationCenter.loadError.test.tsx — /inv/:id on a failed trajectory
 * fetch shows a retryable failure, not "No investigation with id X"
 * (audit wave4 C15). useInvestigation is stubbed at the hook boundary; the
 * workspace panel host is reduced to its children (the docked panels are not
 * under test).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const retry = vi.fn();
const stub: { status: string } = { status: "error" };

vi.mock("../../hooks/useInvestigation", () => ({
  useInvestigation: (id: string | null) => ({
    id: id ?? "",
    status: stub.status,
    question: null,
    events: [],
    terminalPayload: null,
    costTotal: 0,
    completedAt: null,
    streamStatus: "open",
    reconnects: 0,
    sourcePolicy: [],
    loadError: { code: "backend_unreachable", retryable: true },
    retry,
  }),
}));

vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

import ResearchWorkstation from ".";

afterEach(() => {
  cleanup();
  retry.mockReset();
  stub.status = "error";
});

function renderAt(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/inv/${id}`]}>
      <Routes>
        <Route path="/inv/:investigationId" element={<ResearchWorkstation />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("InvestigationCenter — trajectory outage", () => {
  it("renders a retryable failure and retries the fetch", () => {
    renderAt("inv-123");
    expect(screen.getByRole("alert").textContent).toContain("Couldn’t load this research");
    expect(screen.queryByText(/No investigation with id/)).toBeNull();
    // The failure replaces the live IDE: no empty notes rail implying a run
    // is underway when nothing about it could be loaded.
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.queryByText("Notes")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("CONTROL: not_found still reads as a definite not-found", () => {
    stub.status = "not_found";
    renderAt("inv-123");
    expect(screen.getByText(/No investigation with id/)).toBeTruthy();
  });
});
