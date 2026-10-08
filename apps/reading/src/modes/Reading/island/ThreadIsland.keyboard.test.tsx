/**
 * LANDING NOTE (pane-flow packet → main, SPR-01 M1, ledger L-f23f-island): the
 * three "flag for diligence" composer cases were DROPPED at landing — main's
 * composer (flagFromIsland) evolved past the packet's and is covered by main's
 * own flagFromIsland.test.tsx (passes at the landing head). The island hunks
 * themselves are REUSED because workspace/windowCycle.test.tsx needs them.
 */
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import ThreadIsland from "./ThreadIsland";
import type { IslandThreadState } from "./useIslandThread";
import { LemonModal } from "../../../components/lemon/LemonModal";
import { useWindows } from "../../../workspace/windowsStore";
import { WorkspaceWindow } from "../../../components/windows/WorkspaceWindow";

const network = vi.hoisted(() => ({ thread: vi.fn(), start: vi.fn(), steer: vi.fn(), reformat: vi.fn(), flag: vi.fn() }));
vi.mock("./useIslandThread", () => ({ useIslandThread: network.thread }));
vi.mock("../../../lib/api", async (load) => ({ ...await load<typeof import("../../../lib/api")>(), startInvestigation: network.start }));
vi.mock("../../../api/research", async (load) => ({ ...await load<typeof import("../../../api/research")>(), steerResearch: network.steer }));
vi.mock("../../../api/reformat", async (load) => ({ ...await load<typeof import("../../../api/reformat")>(), postReformat: network.reformat }));
vi.mock("../../../api/diligence", async (load) => ({ ...await load<typeof import("../../../api/diligence")>(), createFlag: network.flag }));

const thread: IslandThreadState = {
  status: "complete", costTotal: 0, question: "A real thread question", family: [], loading: false,
  outcomeLoading: false, sessionState: null, retry: null, refetchFamily: vi.fn(),
  outcome: {
    insights: [{ node_id: "insight", kind: "insight", text: "A finding", refinement_count: 0, escalated: false }],
    questions: [{ node_id: "question", kind: "question", text: "A follow-up question", refinement_count: 0, escalated: false }],
  },
};
function island(anchorId = "a", servable = true) {
  return <ThreadIsland anchorId={anchorId} documentId="doc" investigationId={`inv-${anchorId}`} servable={servable} passageQuote="Permitted passage" pageIndexHint={2} />;
}
function mount() { return render(<MemoryRouter>{island()}<button>Outside</button></MemoryRouter>); }
function expand(index = 0) {
  const glyph = screen.getAllByRole("button", { name: /Expand the island/ })[index];
  fireEvent.click(glyph);
  return glyph;
}
function card() { return screen.getByRole("dialog", { name: /Research thread island/ }); }
function dismiss() { return within(card()).getByRole("button", { name: "Dismiss the island" }); }
function pending() {
  let release: (value: unknown) => void = () => { throw new Error("not initialized"); };
  const promise = new Promise((resolve) => { release = resolve; });
  return { promise, release };
}
beforeEach(() => { vi.clearAllMocks(); network.thread.mockReturnValue(thread); useWindows.getState().reset(); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("actual anchored island keyboard ownership", () => {
  it("focuses Dismiss on expansion and returns to the glyph after plain Escape", () => {
    mount(); expand();
    const button = dismiss(); expect(document.activeElement).toBe(button);
    fireEvent.keyDown(button, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /Expand the island/ }));
    expect(useWindows.getState().order).toEqual([]);
  });
  it("returns to the newly rendered glyph after explicit Dismiss", () => {
    mount(); expand(); fireEvent.click(dismiss());
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /Expand the island/ }));
  });
  it("closes only the island owning actual focus among two expanded cards", () => {
    render(<MemoryRouter>{island("a")}{island("b")}</MemoryRouter>);
    expand(); expand();
    const cards = screen.getAllByRole("dialog");
    const last = within(cards[1]).getByRole("button", { name: "Dismiss the island" }); last.focus();
    fireEvent.keyDown(last, { key: "Escape" });
    expect(screen.getAllByRole("dialog")).toEqual([cards[0]]);
  });
  it.each([{ ctrlKey: true }, { metaKey: true }, { altKey: true }, { shiftKey: true }, { isComposing: true }])(
    "refuses modified or composing Escape %j", (modifiers) => {
      mount(); expand(); const button = dismiss(); button.focus();
      expect(fireEvent.keyDown(button, { key: "Escape", ...modifiers })).toBe(true);
      expect(card()).toBeTruthy();
    },
  );
  it("refuses consumed and AltGraph-only Escape", () => {
    mount(); expand(); const button = dismiss(); button.focus();
    const consumed = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    consumed.preventDefault(); fireEvent(button, consumed); expect(card()).toBeTruthy();
    const altGraph = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    Object.defineProperty(altGraph, "getModifierState", { value: (key: string) => key === "AltGraph" });
    fireEvent(button, altGraph); expect(card()).toBeTruthy();
  });
  it("does not close a hidden island or accept document-level Escape outside it", () => {
    const view = render(<MemoryRouter><section>{island()}</section><button>Outside</button></MemoryRouter>);
    expand(); const button = dismiss(); button.focus();
    view.rerender(<MemoryRouter><section hidden>{island()}</section><button>Outside</button></MemoryRouter>);
    fireEvent.keyDown(button, { key: "Escape" });
    expect(view.container.querySelector('[data-island-state="expanded"]')).not.toBeNull();
    view.rerender(<MemoryRouter><section>{island()}</section><button>Outside</button></MemoryRouter>);
    const outside = screen.getByRole("button", { name: "Outside" }); outside.focus();
    fireEvent.keyDown(document, { key: "Escape" }); expect(card()).toBeTruthy();
  });
  it("leaves Escape to the actual top modal", () => {
    const close = vi.fn(); const view = render(<MemoryRouter>{island()}</MemoryRouter>); expand();
    view.rerender(<MemoryRouter>{island()}<LemonModal open title="Confirmation" onClose={close}><input aria-label="Modal input" /></LemonModal></MemoryRouter>);
    const input = screen.getByRole("textbox", { name: "Modal input" }); input.focus(); fireEvent.keyDown(input, { key: "Escape" });
    expect(close).toHaveBeenCalledTimes(1); expect(card()).toBeTruthy();
  });
  // Universal popover rule (wave repair, design-lead call 2026-10-08): a
  // body-targeted Escape closes the top floating card — PR 3757's
  // ThreadIsland.escape.test.tsx control is the acceptance oracle.
  it("accepts a body-targeted Escape when the card is the top overlay", () => {
    mount(); expand();
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: /Research thread island/ })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /Expand the island/ }));
  });
  it("refuses a body-targeted Escape while another overlay is above the card", () => {
    mount(); expand();
    const above = document.createElement("div");
    above.setAttribute("data-esc-overlay", "");
    document.body.append(above);
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(card()).toBeTruthy();
    above.remove();
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: /Research thread island/ })).toBeNull();
  });
  it("click-away collapses without taking focus from the clicked control", () => {
    mount(); expand(); const outside = screen.getByRole("button", { name: "Outside" });
    fireEvent.mouseDown(outside); outside.focus(); fireEvent.click(outside);
    expect(screen.queryByRole("dialog")).toBeNull(); expect(document.activeElement).toBe(outside);
  });
  it("closes child then card inside a real WorkspaceWindow without closing or duplicating the frame", async () => {
    const id = useWindows.getState().open("reader", { documentId: "doc" }, { id: "reader-window", title: "Source frame" });
    render(<MemoryRouter><WorkspaceWindow id={id}>{island()}</WorkspaceWindow></MemoryRouter>);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    const frame = screen.getByRole("dialog", { name: "Source frame" });
    expect(document.activeElement).toBe(frame);
    expand(); const opener = within(card()).getByRole("button", { name: "Dig deeper" });
    fireEvent.click(opener);
    const input = screen.getByRole("textbox", { name: "What do you want to find out?" });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("textbox", { name: "What do you want to find out?" })).toBeNull();
    expect(card().isConnected).toBe(true);
    expect(document.activeElement).toBe(opener);
    expect(useWindows.getState().order).toEqual([id]);
    fireEvent.keyDown(opener, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: /Research thread island/ })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /Expand the island/ }));
    expect(screen.getByRole("dialog", { name: "Source frame" })).toBe(frame);
    expect(useWindows.getState().order).toEqual([id]);
  });
  it("unmount removes its listener and cannot restore a detached glyph", () => {
    const view = mount(); expand(); const old = dismiss();
    view.unmount(); const outside = document.createElement("button"); document.body.append(outside); outside.focus();
    fireEvent.keyDown(old, { key: "Escape" }); fireEvent.keyDown(document, { key: "Escape" });
    expect(document.activeElement).toBe(outside); outside.remove(); expect(useWindows.getState().order).toEqual([]);
  });
  it.each([
    ["Dig deeper", "What do you want to find out?"],
    ["Reformat this", "What should the reformat do?"],
    // "flag for diligence" row DROPPED at landing — see the header note (L-f23f-island).
  ])("one Escape closes the real %s composer and restores its opener", (label, inputLabel) => {
    mount(); expand(); const opener = within(card()).getAllByRole("button", { name: label })[0];
    fireEvent.click(opener); const input = screen.getByRole("textbox", { name: inputLabel });
    expect(document.activeElement).toBe(input);
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("textbox", { name: inputLabel })).toBeNull(); expect(card()).toBeTruthy();
    const restored = label === "flag for diligence"
      ? within(card()).getAllByRole("button", { name: label })[0] : opener;
    expect(document.activeElement).toBe(restored);
    expect(restored.isConnected).toBe(true);
    fireEvent.keyDown(restored, { key: "Escape" }); expect(screen.queryByRole("dialog")).toBeNull();
  });
  it.each([
    ["Dig deeper", "What do you want to find out?"],
    ["Reformat this", "What should the reformat do?"],
    // "flag for diligence" row DROPPED at landing — see the header note (L-f23f-island).
  ])("nested %s refuses consumed, modified and composing Escape", (label, inputLabel) => {
    mount(); expand();
    fireEvent.click(within(card()).getAllByRole("button", { name: label })[0]);
    const input = screen.getByRole("textbox", { name: inputLabel });
    for (const modifier of [{ ctrlKey: true }, { metaKey: true }, { altKey: true }, { shiftKey: true }, { isComposing: true }]) {
      expect(fireEvent.keyDown(input, { key: "Escape", ...modifier })).toBe(true);
      expect(input.isConnected).toBe(true);
    }
    const consumed = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    consumed.preventDefault(); fireEvent(input, consumed);
    expect(input.isConnected).toBe(true); expect(card()).toBeTruthy();
  });
  it("refuses Escape and focus restoration while its ancestor is aria-hidden", () => {
    const view = render(<MemoryRouter><section>{island()}</section><button>Outside</button></MemoryRouter>);
    expand(); const button = dismiss();
    view.rerender(<MemoryRouter><section aria-hidden="true">{island()}</section><button>Outside</button></MemoryRouter>);
    fireEvent.keyDown(button, { key: "Escape" });
    expect(view.container.querySelector('[data-island-state="expanded"]')).not.toBeNull();
    const outside = screen.getByRole("button", { name: "Outside" }); outside.focus();
    fireEvent.click(button);
    expect(document.activeElement).toBe(outside);
  });
  it("question-dig returns to that exact question's connected opener", () => {
    mount(); expand(); const opener = within(card()).getByRole("button", { name: "dig →" });
    fireEvent.click(opener); const input = screen.getByRole("textbox", { name: "What do you want to find out?" });
    fireEvent.keyDown(input, { key: "Escape" }); expect(document.activeElement).toBe(opener);
  });
  it("retains an admitted deepen operation until its existing acknowledgment", async () => {
    network.thread.mockReturnValue({ ...thread, sessionState: "running" });
    const held = pending(); network.steer.mockReturnValue(held.promise);
    mount(); expand(); fireEvent.click(within(card()).getByRole("button", { name: "Dig deeper" }));
    const input = screen.getByRole("textbox", { name: "What do you want to find out?" });
    fireEvent.click(within(card()).getByRole("button", { name: "More budget on this same thread" }));
    expect(network.steer).toHaveBeenCalledWith("inv-a", "inv-a", "deepen");
    expect(within(card()).getByRole("button", { name: "Cancel" })).toHaveProperty("disabled", true);
    expect(fireEvent.keyDown(input, { key: "Escape" })).toBe(false);
    expect(input.isConnected).toBe(true);
    await act(async () => { held.release({}); });
    expect(within(card()).getByRole("button", { name: "Budget added — the thread continues" })).toBeTruthy();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("textbox", { name: "What do you want to find out?" })).toBeNull();
    expect(card()).toBeTruthy();
  });
  // "flag" kind DROPPED at landing — see the header note (L-f23f-island).
  it.each(["dig", "reformat"])("busy %s consumes Escape and refuses Cancel without discarding the operation", async (kind) => {
    const held = pending();
    network.start.mockReturnValue(held.promise); network.reformat.mockReturnValue(held.promise); network.flag.mockReturnValue(held.promise);
    mount(); expand();
    const labels = kind === "dig" ? ["Dig deeper", "What do you want to find out?", "Follow this", "Cancel"] :
      kind === "reformat" ? ["Reformat this", "What should the reformat do?", "Reformat", "Cancel"] :
      ["flag for diligence", "A note for the diligence flag (optional)", "flag", "Cancel the flag"];
    fireEvent.click(within(card()).getAllByRole("button", { name: labels[0] })[0]);
    const input = screen.getByRole("textbox", { name: labels[1] }); fireEvent.change(input, { target: { value: "A precise request" } });
    fireEvent.click(within(card()).getByRole("button", { name: labels[2] }));
    await act(async () => { await Promise.resolve(); });
    const cancel = within(card()).getByRole("button", { name: labels[3] });
    expect(cancel).toHaveProperty("disabled", true);
    expect(fireEvent.keyDown(input, { key: "Escape" })).toBe(false);
    fireEvent.click(cancel); expect(card().contains(input)).toBe(true);
    if (kind === "flag") await act(async () => { held.release({}); });
    else if (kind === "dig") await act(async () => { held.release({ investigation_id: "child" }); });
    // Reformat remains held at its external boundary; no server or follow-on is issued.
    expect(useWindows.getState().order).toEqual([]);
  });
});
