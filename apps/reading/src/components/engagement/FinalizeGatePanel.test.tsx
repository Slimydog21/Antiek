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
      authorized: true,
      draft_id: "d1",
      parent_asset_id: "p1",
      reason: "ok",
      notes: ["should not be trusted without accept"],
    }));
    render(
      <FinalizeGatePanel
        authorizeFn={authorizeFn}
        initialDraftId="d1"
        initialParentId="p1"
      />,
    );
    fireEvent.click(screen.getByTestId("finalize-gate-check"));
    expect(authorizeFn).not.toHaveBeenCalled();
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
    render(
      <FinalizeGatePanel
        authorizeFn={authorizeFn}
        initialDraftId="d"
        initialParentId="p"
      />,
    );
    fireEvent.click(screen.getByTestId("finalize-gate-accept"));
    fireEvent.click(screen.getByTestId("finalize-gate-check"));
    expect(screen.getByTestId("finalize-gate-error").textContent).toMatch(
      /draft_id/,
    );
    expect(screen.queryByTestId("finalize-gate-result")).toBeNull();
  });

  it("never shows AUTHORIZED when accept unchecked even if authorizeFn always authorizes", () => {
    const authorizeFn = vi.fn(() => ({
      authorized: true,
      draft_id: "d1",
      parent_asset_id: "p1",
      reason: "ok",
      notes: ["should not surface"],
    }));
    render(
      <FinalizeGatePanel
        authorizeFn={authorizeFn}
        initialDraftId="d1"
        initialParentId="p1"
      />,
    );
    fireEvent.click(screen.getByTestId("finalize-gate-check"));
    expect(authorizeFn).not.toHaveBeenCalled();
    const el = screen.getByTestId("finalize-gate-authorized");
    expect(el.getAttribute("data-authorized")).toBe("false");
    expect(el.textContent).toMatch(/DENIED/i);
  });

  it("clears authorized result when accept is unchecked", () => {
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
      />,
    );
    fireEvent.click(screen.getByTestId("finalize-gate-accept"));
    fireEvent.click(screen.getByTestId("finalize-gate-check"));
    expect(
      screen.getByTestId("finalize-gate-authorized").getAttribute("data-authorized"),
    ).toBe("true");
    fireEvent.click(screen.getByTestId("finalize-gate-accept"));
    expect(screen.queryByTestId("finalize-gate-result")).toBeNull();
  });
});
