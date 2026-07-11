import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import FinalizeGatePanel from "./FinalizeGatePanel";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("FinalizeGatePanel", () => {
  it("shows authorized when accept checked and gate returns ok", () => {
    const authorizeFn = vi.fn(() => ({
      authorized: true,
      draft_id: "d1",
      parent_asset_id: "p1",
      reason: "ok",
      notes: ["authorized: provisional draft accepted by operator"],
    }));
    render(
      <FinalizeGatePanel
        authorizeFn={authorizeFn}
        initialDraftId="d1"
        initialParentId="p1"
        initialTwinIds="t1"
      />,
    );
    fireEvent.click(screen.getByTestId("finalize-gate-accept"));
    fireEvent.click(screen.getByTestId("finalize-gate-check"));
    expect(authorizeFn).toHaveBeenCalledWith({
      draft_id: "d1",
      parent_asset_id: "p1",
      provisional: true,
      operator_accepted: true,
      twin_ids: ["t1"],
    });
    const el = screen.getByTestId("finalize-gate-authorized");
    expect(el.getAttribute("data-authorized")).toBe("true");
    expect(el.textContent).toMatch(/AUTHORIZED/i);
    expect(el.textContent).toMatch(/not performed here/i);
  });

  it("shows denied when operator has not accepted", () => {
    const authorizeFn = vi.fn(() => ({
      authorized: false,
      draft_id: "d1",
      parent_asset_id: "p1",
      reason: "operator_accept_required",
      notes: ["explicit operator_accepted=true required before parent mutation"],
    }));
    render(
      <FinalizeGatePanel
        authorizeFn={authorizeFn}
        initialDraftId="d1"
        initialParentId="p1"
      />,
    );
    fireEvent.click(screen.getByTestId("finalize-gate-check"));
    expect(authorizeFn).toHaveBeenCalledWith(
      expect.objectContaining({ operator_accepted: false }),
    );
    const el = screen.getByTestId("finalize-gate-authorized");
    expect(el.getAttribute("data-authorized")).toBe("false");
    expect(el.textContent).toMatch(/DENIED/i);
    expect(screen.getByTestId("finalize-gate-reason").textContent).toMatch(
      /operator_accept_required/,
    );
  });

  it("surfaces authorizeFn throw as error without authorized result", () => {
    const authorizeFn = vi.fn(() => {
      throw new Error("draft_id must be non-empty");
    });
    render(<FinalizeGatePanel authorizeFn={authorizeFn} />);
    fireEvent.click(screen.getByTestId("finalize-gate-check"));
    expect(screen.getByTestId("finalize-gate-error").textContent).toMatch(
      /draft_id/,
    );
    expect(screen.queryByTestId("finalize-gate-result")).toBeNull();
  });
});
