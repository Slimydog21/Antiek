/** PaneResizer.test.tsx — SPR-07 M5 / invariant 28 (patterns 4/6): a keyboard-operable separator; drag-past-threshold closes only an agent tab. */
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const closeAgentPane = vi.fn();
vi.mock("./agentPaneStore", async (orig) => ({
  ...(await orig<typeof import("./agentPaneStore")>()),
  closeAgentPane: (...a: unknown[]) => closeAgentPane(...a),
}));

import { useCompanion } from "../companionStore";
import { PaneResizer } from "./PaneResizer";
import { PANE_MIN, STEP, usePaneWidthStore } from "./paneWidthStore";

function Host({ max = 600, onPreview = () => {} }: { max?: number; onPreview?: (w: number | null) => void }) {
  const preferred = usePaneWidthStore((s) => s.preferred);
  return <PaneResizer width={preferred ?? 320} max={max} onPreview={onPreview} />;
}

beforeEach(() => { usePaneWidthStore.getState().reset(); useCompanion.getState().reset(); closeAgentPane.mockReset(); window.localStorage.clear(); });
afterEach(cleanup);

const sep = () => document.querySelector<HTMLElement>('[role="separator"]')!;

describe("PaneResizer keyboard", () => {
  it("is a vertical separator controlling the right pane; ArrowLeft grows by 32 and is consumed; Home/End go to min/max", () => {
    render(<Host max={600} />);
    const s = sep();
    expect(s.getAttribute("aria-orientation")).toBe("vertical");
    expect(s.getAttribute("aria-controls")).toBe("cockpit-right-pane");
    expect(s.getAttribute("aria-label")).toBe("Resize the agents pane");
    expect(s.tabIndex).toBe(0);
    expect(s.getAttribute("aria-valuenow")).toBe("320");
    expect(s.getAttribute("aria-valuemin")).toBe(String(PANE_MIN));
    expect(s.getAttribute("aria-valuemax")).toBe("600");
    expect(fireEvent.keyDown(s, { key: "ArrowLeft" })).toBe(false);
    expect(sep().getAttribute("aria-valuenow")).toBe(String(320 + STEP));
    fireEvent.keyDown(sep(), { key: "ArrowRight" });
    fireEvent.keyDown(sep(), { key: "ArrowRight" });
    expect(sep().getAttribute("aria-valuenow")).toBe(String(320 - STEP));
    fireEvent.keyDown(sep(), { key: "Home" });
    expect(sep().getAttribute("aria-valuenow")).toBe(String(PANE_MIN));
    fireEvent.keyDown(sep(), { key: "End" });
    expect(sep().getAttribute("aria-valuenow")).toBe("600");
    expect(usePaneWidthStore.getState().preferred).toBe(600);
  });

  it("never exceeds max from the keyboard", () => {
    usePaneWidthStore.getState().setPreferred(590);
    render(<Host max={600} />);
    fireEvent.keyDown(sep(), { key: "ArrowLeft" });
    expect(sep().getAttribute("aria-valuenow")).toBe("600");
  });
});

describe("PaneResizer pointer drag", () => {
  function drag(dx: number, release: "up" | "escape" | "cancel") {
    const s = sep();
    fireEvent.pointerDown(s, { clientX: 500, pointerId: 1, button: 0 });
    fireEvent.pointerMove(s, { clientX: 500 + dx, pointerId: 1 });
    if (release === "up") fireEvent.pointerUp(s, { clientX: 500 + dx, pointerId: 1 });
    else if (release === "escape") fireEvent.keyDown(s, { key: "Escape" });
    else fireEvent.pointerCancel(s, { pointerId: 1 });
  }

  it("previews below the threshold at PANE_MIN; release closes the ACTIVE AGENT tab and restores the pre-drag width", () => {
    const onPreview = vi.fn();
    usePaneWidthStore.getState().setPreferred(320);
    useCompanion.setState({ tabs: [{ id: "agent:pane:p:1", kind: "agent" as never, title: "a", seq: 1, scope: "project" }], activeTabId: "agent:pane:p:1" });
    render(<Host max={600} onPreview={onPreview} />);
    drag(100, "up"); // moving right shrinks the right pane: 320 - 100 = 220 < 244
    expect(onPreview).toHaveBeenCalledWith(PANE_MIN);
    expect(onPreview).toHaveBeenLastCalledWith(null);
    expect(closeAgentPane).toHaveBeenCalledWith("agent:pane:p:1", "a");
    expect(usePaneWidthStore.getState().preferred).toBe(320);
  });

  it("release below the threshold with a non-agent active tab snaps to PANE_MIN and closes nothing", () => {
    useCompanion.getState().openAgentTab({ kind: "dialogue" });
    render(<Host max={600} />);
    drag(100, "up");
    expect(closeAgentPane).not.toHaveBeenCalled();
    expect(usePaneWidthStore.getState().preferred).toBe(PANE_MIN);
  });

  it("a release above the threshold commits the dragged width", () => {
    render(<Host max={600} />);
    drag(-40, "up");
    expect(usePaneWidthStore.getState().preferred).toBe(360);
  });

  it("Escape and pointercancel mid-drag restore and close nothing", () => {
    const onPreview = vi.fn();
    useCompanion.setState({ tabs: [{ id: "agent:pane:p:1", kind: "agent" as never, title: "a", seq: 1, scope: "project" }], activeTabId: "agent:pane:p:1" });
    render(<Host max={600} onPreview={onPreview} />);
    drag(100, "escape");
    expect(closeAgentPane).not.toHaveBeenCalled();
    expect(onPreview).toHaveBeenLastCalledWith(null);
    expect(usePaneWidthStore.getState().preferred).toBeNull();
    act(() => { drag(100, "cancel"); });
    expect(closeAgentPane).not.toHaveBeenCalled();
    expect(usePaneWidthStore.getState().preferred).toBeNull();
  });
});
