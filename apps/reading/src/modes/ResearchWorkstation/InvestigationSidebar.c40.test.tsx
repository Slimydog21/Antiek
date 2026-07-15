import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import InvestigationSidebar from "./InvestigationSidebar";

const composeMock = vi.fn();
vi.mock("../../lib/api", async (load) => {
  const actual = await load<typeof import("../../lib/api")>();
  return { ...actual, composeResearchArtifacts: (...args: unknown[]) => composeMock(...args) };
});
vi.mock("../../hooks/useInvestigationList", () => ({
  useInvestigationList: () => ({
    loading: false, error: null, refetch: vi.fn(), investigations: [
      { investigation_id: "inv-a", question: "Alpha", status: "completed", artifact_composable: true, started_at: "2026-01-03", completed_at: "2026-01-03", cost_usd_total: 0, parent_investigation_id: null },
      { investigation_id: "inv-b", question: "Beta", status: "completed", artifact_composable: true, started_at: "2026-01-02", completed_at: "2026-01-02", cost_usd_total: 0, parent_investigation_id: null },
      { investigation_id: "inv-running", question: "Running", status: "in_progress", started_at: "2026-01-01", completed_at: null, cost_usd_total: 0, parent_investigation_id: null },
    ],
  }),
}));

describe("Cycle 40 investigation composition", () => {
  beforeEach(() => { composeMock.mockReset(); });
  afterEach(() => cleanup());

  it("selects completed rows in explicit order and opens success in a new tab", async () => {
    composeMock.mockResolvedValue({ url: "/research/artifacts/compositions/cmp-ok" });
    const replace = vi.fn();
    const preview = { close: vi.fn(), location: { replace }, opener: window };
    const open = vi.spyOn(window, "open").mockReturnValue(preview as unknown as Window);
    render(<MemoryRouter><InvestigationSidebar /></MemoryRouter>);
    fireEvent.click(screen.getByText("Select"));
    expect((screen.getByLabelText("Select inv-running") as HTMLInputElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("Select inv-b"));
    fireEvent.click(screen.getByLabelText("Select inv-a"));
    fireEvent.click(screen.getByText("Compose HTML"));
    await waitFor(() => expect(composeMock).toHaveBeenCalledWith(["inv-b", "inv-a"]));
    expect(open).toHaveBeenCalledWith("", "_blank");
    expect(replace).toHaveBeenCalledWith(
      new URL("/research/artifacts/compositions/cmp-ok", window.location.origin).toString(),
    );
    expect(preview.opener).toBeNull();
  });

  it("retains ordered selection and shows one actionable error", async () => {
    composeMock.mockRejectedValue(new Error("inv-b is not completed"));
    render(<MemoryRouter><InvestigationSidebar /></MemoryRouter>);
    fireEvent.click(screen.getByText("Select"));
    fireEvent.click(screen.getByLabelText("Select inv-a"));
    fireEvent.click(screen.getByLabelText("Select inv-b"));
    fireEvent.click(screen.getByText("Compose HTML"));
    expect((await screen.findByRole("alert")).textContent).toContain("inv-b is not completed");
    expect((screen.getByLabelText("Select inv-a") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("Select inv-b") as HTMLInputElement).checked).toBe(true);
  });

  it("freezes selection while the submitted order is pending", async () => {
    composeMock.mockReturnValue(new Promise(() => undefined));
    vi.spyOn(window, "open").mockReturnValue(
      { close: vi.fn(), location: { replace: vi.fn() }, opener: null } as unknown as Window,
    );
    render(<MemoryRouter><InvestigationSidebar /></MemoryRouter>);
    fireEvent.click(screen.getByText("Select"));
    fireEvent.click(screen.getByLabelText("Select inv-a"));
    fireEvent.click(screen.getByLabelText("Select inv-b"));
    fireEvent.click(screen.getByText("Compose HTML"));
    await waitFor(() => expect(composeMock).toHaveBeenCalledTimes(1));
    expect((screen.getByRole("button", { name: "Done" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText("Select inv-a") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("Select inv-b") as HTMLInputElement).disabled).toBe(true);
  });
});
