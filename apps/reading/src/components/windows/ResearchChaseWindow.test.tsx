import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

const { chaseMock } = vi.hoisted(() => ({
  chaseMock: vi.fn(() => <div data-testid="chase-thread" />),
}));
vi.mock("../../modes/ResearchWorkstation/ChaseThread", () => ({ default: chaseMock }));

import ResearchChaseWindow from "./ResearchChaseWindow";

afterEach(() => {
  cleanup();
  chaseMock.mockClear();
});

describe("ResearchChaseWindow payload boundary", () => {
  it("delegates exact validated context to ChaseThread", () => {
    render(<ResearchChaseWindow spawnContext="exact passage" parentInvestigationId="read-doc" />);
    expect(screen.getByTestId("chase-thread")).toBeTruthy();
    expect(chaseMock).toHaveBeenCalledWith(
      expect.objectContaining({ spawnContext: "exact passage", parentInvestigationId: "read-doc" }),
      {},
    );
  });

  it("fails closed before ChaseThread when required context is malformed", () => {
    render(<ResearchChaseWindow spawnContext="" parentInvestigationId={42} />);
    expect(screen.getByRole("alert").textContent).toMatch(/invalid source passage/);
    expect(chaseMock).not.toHaveBeenCalled();
  });

  it("fails closed on a whitespace reserved investigation id", () => {
    render(
      <ResearchChaseWindow
        spawnContext="exact passage"
        parentInvestigationId="read-doc"
        reservedChildId="   "
      />,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(chaseMock).not.toHaveBeenCalled();
  });
});
