/**
 * Canvas.test.tsx — DRW block-canvas M2 acceptance + the rigor #3 edge cases.
 *
 * Load-bearing claims (each ASSERTED, not eyeballed):
 *  - blocks render from the REAL graph result (getDistillation), one card per
 *    insight + one per question, positioned absolutely (M1+M2);
 *  - a node with NO saved position gets deterministic auto-layout, NOT a
 *    (0,0) pile-up (rigor #3);
 *  - dragging a block updates its position live AND emits ONE block.positioned
 *    typed event through postTypedEvent — NOT a side store (M2);
 *  - the persisted event ROUND-TRIPS: feeding the emitted event back as a
 *    trajectory event and reloading re-derives the SAME coordinates (M2 — the
 *    single-source-of-truth criterion);
 *  - an aggressive off-screen drag CLAMPS so the block stays reachable
 *    (rigor #3);
 *  - an EMPTY graph renders an honest empty state, not a blank void (rigor #3);
 *  - a SINGLE node renders with no edges (rigor #3).
 *
 * No browser-local side store is touched — the grep gate confirms it; this
 * suite confirms the only write is the typed-event POST.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { useLayoutEffect, type ComponentProps } from "react";
import type { BlockCardProps } from "./BlockCard";
import type { DistilledNode } from "../../../lib/api";
import type { Event } from "../../../generated/types";

const captured = vi.hoisted(() => {
  const cards: BlockCardProps[] = [];
  const retries: Array<() => void> = [];
  return { cards, retries };
});
// Delegating instrumentation records supplied callbacks while rendering the actual components.
vi.mock("./BlockCard", async () => {
  const actual = await vi.importActual<typeof import("./BlockCard")>("./BlockCard");
  return { ...actual, default: (props: BlockCardProps) => { captured.cards.push(props); return <actual.default {...props} />; } };
});
vi.mock("../../../shared/AIActionFailure", async () => {
  const actual = await vi.importActual<typeof import("../../../shared/AIActionFailure")>("../../../shared/AIActionFailure");
  return { ...actual, default: (props: ComponentProps<typeof actual.default>) => {
    captured.retries.push(props.onRetry); return <actual.default {...props} />;
  } };
});

const { getDistillationMock, getTrajectoryMock, postTypedEventMock } = vi.hoisted(() => ({
  getDistillationMock: vi.fn(),
  getTrajectoryMock: vi.fn(),
  postTypedEventMock: vi.fn(),
}));

vi.mock("../../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../../lib/api")>();
  return {
    ...actual,
    getDistillation: getDistillationMock,
    getTrajectory: getTrajectoryMock,
    postTypedEvent: postTypedEventMock,
  };
});

import userEvent from "@testing-library/user-event";
import { LemonModal } from "../../../components/lemon/LemonModal";
import Canvas from "./Canvas";
import { PanelLayoutPanel } from "../../../workspace/PanelLayoutPanel";
import { disablePersistence, useWorkspace } from "../../../workspace/WorkspaceStore";

// Controlled registry mounting; the panel frame, store and Canvas remain actual components.
vi.mock("../../../workspace/PanelRegistry", () => ({ PanelRegistry: { Notes: () => <Canvas investigationId="panel-resource" /> } }));

const proto = window.HTMLElement.prototype as unknown as Record<string, unknown>;
const ORIG = {
  setPointerCapture: proto.setPointerCapture,
  releasePointerCapture: proto.releasePointerCapture,
  hasPointerCapture: proto.hasPointerCapture,
};

function insight(node_id: string, text: string, extra: Partial<DistilledNode> = {}): DistilledNode {
  return {
    node_id, kind: "insight", text, confidence: "high",
    source_document_id: "doc-1", refinement_count: 0, escalated: false,
    reserved_child_investigation_id: null, ...extra,
  };
}
function question(node_id: string, text: string, extra: Partial<DistilledNode> = {}): DistilledNode {
  return {
    node_id, kind: "question", text, confidence: null,
    source_document_id: null, refinement_count: 0, escalated: false,
    reserved_child_investigation_id: null, ...extra,
  };
}

/** Build a block.positioned trajectory Event (the read-back shape). */
function positionEvent(node_id: string, x: number, y: number): Event {
  return {
    event_id: `ev-${node_id}-${x}-${y}`,
    investigation_id: "inv-1",
    action_type: "block.positioned" as Event["action_type"],
    payload: { action_type: "block.positioned", node_id, x, y, region_id: null, region_label: null },
    param_version: "test",
    emitted_at: new Date().toISOString(),
  };
}

beforeEach(() => {
  captured.cards.length = 0; captured.retries.length = 0;
  proto.setPointerCapture = vi.fn();
  proto.releasePointerCapture = vi.fn();
  proto.hasPointerCapture = vi.fn(() => false);
  Object.defineProperty(window, "innerWidth", { value: 1200, configurable: true });
  Object.defineProperty(window, "innerHeight", { value: 800, configurable: true });
  postTypedEventMock.mockResolvedValue({ event_id: "ev-new", action_type: "block.positioned" });
});

afterEach(() => {
  cleanup();
  getDistillationMock.mockReset();
  getTrajectoryMock.mockReset();
  postTypedEventMock.mockReset();
  proto.setPointerCapture = ORIG.setPointerCapture;
  proto.releasePointerCapture = ORIG.releasePointerCapture;
  proto.hasPointerCapture = ORIG.hasPointerCapture;
});

function blockEl(nodeId: string): HTMLElement {
  const el = document.querySelector(`[data-draggable-block="${nodeId}"]`);
  if (!el) throw new Error(`no block for ${nodeId}`);
  if (el.parentElement?.parentElement && !Object.hasOwn(el.parentElement.parentElement, "clientWidth")) measureScrollport(el);
  return el as HTMLElement;
}

describe("Canvas — renders real graph nodes + auto-layout (M1/M2, rigor #3)", () => {
  it("renders one block per insight + question, auto-laid-out (no (0,0) pile-up)", async () => {
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [insight("i1", "GPUs gate scale."), insight("i2", "Latency is the moat.")],
      questions: [question("q1", "What is the moat?")],
    });
    getTrajectoryMock.mockResolvedValue({ investigation_id: "inv-1", count: 0, events: [] });

    render(<Canvas investigationId="inv-1" />);
    await waitFor(() => expect(screen.getByText("GPUs gate scale.")).toBeTruthy());

    const i1 = blockEl("i1");
    const i2 = blockEl("i2");
    // Auto-layout: distinct positions, neither at (0,0).
    expect(i1.style.left).not.toBe("0px");
    expect(i2.style.left === i1.style.left && i2.style.top === i1.style.top).toBe(false);
  });
});

describe("Canvas — drag persists via typed event, round-trips (M2)", () => {
  it("dragging emits ONE block.positioned event and moves the block live", async () => {
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [insight("i1", "GPUs gate scale.")],
      questions: [],
    });
    getTrajectoryMock.mockResolvedValue({ investigation_id: "inv-1", count: 0, events: [] });

    render(<Canvas investigationId="inv-1" />);
    await waitFor(() => expect(screen.getByText("GPUs gate scale.")).toBeTruthy());

    const el = blockEl("i1");
    const startLeft = parseFloat(el.style.left);
    fireEvent.pointerDown(el, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 260, clientY: 220 });
    fireEvent.pointerUp(el, { pointerId: 1, clientX: 260, clientY: 220 });

    // Live move: the block shifted +160 / +120 from its start.
    expect(parseFloat(el.style.left)).toBeCloseTo(startLeft + 160, 0);

    // Exactly one typed event emitted, with the dragged coordinates — and it
    // is a block.positioned event (the single-writer funnel), not a side store.
    expect(postTypedEventMock).toHaveBeenCalledTimes(1);
    const env = postTypedEventMock.mock.calls[0][0];
    expect(env.investigation_id).toBe("inv-1");
    expect(env.payload.action_type).toBe("block.positioned");
    expect(env.payload.node_id).toBe("i1");
    expect(env.payload.x).toBeCloseTo(startLeft + 160, 0);
  });

  it("round-trips: the emitted event reloaded from /trajectory re-derives the same coords", async () => {
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [insight("i1", "GPUs gate scale.")],
      questions: [],
    });
    getTrajectoryMock.mockResolvedValue({ investigation_id: "inv-1", count: 0, events: [] });

    const { unmount } = render(<Canvas investigationId="inv-1" />);
    await waitFor(() => expect(screen.getByText("GPUs gate scale.")).toBeTruthy());

    const el = blockEl("i1");
    fireEvent.pointerDown(el, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 250, clientY: 250 });
    fireEvent.pointerUp(el, { pointerId: 1, clientX: 250, clientY: 250 });

    const env = postTypedEventMock.mock.calls[0][0];
    const savedX = env.payload.x as number;
    const savedY = env.payload.y as number;
    unmount();

    // Reload: the trajectory now carries the persisted event (the single
    // source of truth — no local state survives the unmount).
    getTrajectoryMock.mockResolvedValue({
      investigation_id: "inv-1",
      count: 1,
      events: [positionEvent("i1", savedX, savedY)],
    });
    render(<Canvas investigationId="inv-1" />);
    await waitFor(() => expect(screen.getByText("GPUs gate scale.")).toBeTruthy());

    const reloaded = blockEl("i1");
    expect(parseFloat(reloaded.style.left)).toBeCloseTo(savedX, 0);
    expect(parseFloat(reloaded.style.top)).toBeCloseTo(savedY, 0);
  });

  it("an aggressive off-screen drag CLAMPS so the block stays reachable (rigor #3)", async () => {
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [insight("i1", "GPUs gate scale.")],
      questions: [],
    });
    getTrajectoryMock.mockResolvedValue({ investigation_id: "inv-1", count: 0, events: [] });

    render(<Canvas investigationId="inv-1" />);
    await waitFor(() => expect(screen.getByText("GPUs gate scale.")).toBeTruthy());

    const el = blockEl("i1");
    fireEvent.pointerDown(el, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 100000, clientY: 100000 });
    fireEvent.pointerUp(el, { pointerId: 1, clientX: 100000, clientY: 100000 });

    // clampBlockToViewport keeps >= 80px reachable: x <= innerWidth - 80.
    expect(parseFloat(el.style.left)).toBeLessThanOrEqual(1200 - 80);
    expect(parseFloat(el.style.top)).toBeLessThanOrEqual(800 - 80);
  });
});

describe("Canvas — empty + single-node edge cases (rigor #3)", () => {
  it("empty graph renders an honest empty state, not a blank void", async () => {
    getDistillationMock.mockResolvedValue({ investigation_id: "inv-1", insights: [], questions: [] });
    getTrajectoryMock.mockResolvedValue({ investigation_id: "inv-1", count: 0, events: [] });

    render(<Canvas investigationId="inv-1" />);
    await waitFor(() => expect(screen.getByTestId("canvas-empty")).toBeTruthy());
    expect(screen.getByText("Nothing to lay out yet.")).toBeTruthy();
  });

  it("a single node renders with no edge layer", async () => {
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [insight("i1", "Only one.")],
      questions: [],
    });
    getTrajectoryMock.mockResolvedValue({ investigation_id: "inv-1", count: 0, events: [] });

    render(<Canvas investigationId="inv-1" />);
    await waitFor(() => expect(screen.getByText("Only one.")).toBeTruthy());
    expect(screen.queryByTestId("lineage-edges")).toBeNull();
  });
});

describe("Canvas — a plain click (no movement) does NOT persist", () => {
  it("a pointer down/up without movement emits no event", async () => {
    getDistillationMock.mockResolvedValue({
      investigation_id: "inv-1",
      insights: [insight("i1", "GPUs gate scale.")],
      questions: [],
    });
    getTrajectoryMock.mockResolvedValue({ investigation_id: "inv-1", count: 0, events: [] });

    render(<Canvas investigationId="inv-1" />);
    await waitFor(() => expect(screen.getByText("GPUs gate scale.")).toBeTruthy());

    const el = blockEl("i1");
    act(() => {
      fireEvent.pointerDown(el, { pointerId: 1, clientX: 100, clientY: 100 });
      fireEvent.pointerUp(el, { pointerId: 1, clientX: 100, clientY: 100 });
    });
    expect(postTypedEventMock).not.toHaveBeenCalled();
  });
});


function measureScrollport(block: Element, width = 1200, height = 800, left = 0, top = 0) {
  const port = block.parentElement?.parentElement;
  if (!(port instanceof HTMLElement)) throw new Error("Missing actual connected canvas scrollport");
  Object.defineProperties(port, { clientWidth: { value: width, configurable: true }, clientHeight: { value: height, configurable: true } });
  port.scrollLeft = left; port.scrollTop = top;
  return port;
}
function titleEl(nodeId = "i1") {
  const kind = blockEl(nodeId).querySelector("[data-block-card] > div");
  if (!(kind instanceof HTMLElement)) throw new Error("Missing actual kind header");
  return kind;
}
function deferred<T>() {
  let resolve: (value: T) => void = () => { throw new Error("uninitialized"); };
  let reject: (reason: unknown) => void = () => { throw new Error("uninitialized"); };
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
async function single(events: Event[] = []) {
  getDistillationMock.mockResolvedValue({ investigation_id: "inv-1", insights: [insight("i1", "Current block")], questions: [] });
  getTrajectoryMock.mockResolvedValue({ investigation_id: "inv-1", count: events.length, events });
  const view = render(<Canvas investigationId="inv-1" />);
  await screen.findByText("Current block"); return view;
}
describe("Canvas keyboard and resource counterfactuals", () => {
  it("makes the actual kind title keyboard reachable", async () => {
    await single(); const title = titleEl(); act(() => { title.focus(); });
    expect(document.activeElement).toBe(title); expect(title.tabIndex).toBe(0);
  });
  it("moves twice from live coordinates and dispatches both writes before held completions", async () => {
    await single(); postTypedEventMock.mockReturnValue(new Promise(() => {}));
    const el = blockEl("i1"), title = titleEl(), x = parseFloat(el.style.left);
    act(() => { title.focus(); fireEvent.keyDown(title, { key: "ArrowRight" }); fireEvent.keyDown(title, { key: "ArrowRight", repeat: true }); });
    expect(parseFloat(el.style.left)).toBe(x + 48);
    expect(postTypedEventMock.mock.calls.map(([env]) => env.payload.x)).toEqual([x + 24, x + 48]);
  });
  it("uses actual small scrolled bounds for pointer movement", async () => {
    await single(); const el = blockEl("i1"); measureScrollport(el, 300, 200, 100, 60);
    fireEvent.pointerDown(el, { pointerId: 1, clientX: 0, clientY: 0 });
    fireEvent.pointerMove(el, { pointerId: 1, clientX: 9999, clientY: 9999 });
    fireEvent.pointerUp(el, { pointerId: 1, clientX: 9999, clientY: 9999 });
    expect(el.style.left).toBe("320px"); expect(el.style.top).toBe("180px");
  });
  it("preserves replayed region metadata when pointer movement emits", async () => {
    const event = positionEvent("i1", 100, 100); event.payload = { action_type: "block.positioned", node_id: "i1", x: 100, y: 100, region_id: "region-a", region_label: "Recorded region" };
    await single([event]); const el = blockEl("i1");
    fireEvent.pointerDown(el, { pointerId: 1, clientX: 0, clientY: 0 }); fireEvent.pointerMove(el, { pointerId: 1, clientX: 30, clientY: 20 }); fireEvent.pointerUp(el, { pointerId: 1 });
    expect(postTypedEventMock.mock.calls[0][0].payload).toMatchObject({ region_id: "region-a", region_label: "Recorded region" });
  });
  it("ignores a late old-resource result after the current resource has loaded", async () => {
    const a = deferred<{ investigation_id: string; insights: DistilledNode[]; questions: DistilledNode[] }>();
    getDistillationMock.mockImplementation((id: string) => id === "A" ? a.promise : Promise.resolve({ investigation_id: "B", insights: [insight("same", "Current B")], questions: [] }));
    getTrajectoryMock.mockResolvedValue({ events: [] });
    const view = render(<Canvas investigationId="A" />); view.rerender(<Canvas investigationId="B" />); await screen.findByText("Current B");
    await act(async () => { a.resolve({ investigation_id: "A", insights: [insight("same", "Old A")], questions: [] }); });
    expect(screen.queryByText("Old A")).toBeNull(); expect(screen.getByText("Current B")).toBeTruthy();
  });
});


describe("Canvas input admission and immediate movement", () => {
  it("reaches the real title with simulated Tab and leaves a clamped zero step unconsumed without POST", async () => {
    await single([positionEvent("i1", 220, 120)]); const title = titleEl(), el = blockEl("i1");
    measureScrollport(el, 300, 200); await userEvent.setup().tab(); expect(document.activeElement).toBe(title);
    expect(fireEvent.keyDown(title, { key: "ArrowRight" })).toBe(true); expect(postTypedEventMock).not.toHaveBeenCalled();
    expect(el.style.left).toBe("220px");
  });
  it("uses fresh positive scrollport offsets for keys and refuses zero-size bounds", async () => {
    await single(); const title = titleEl(), el = blockEl("i1"); title.focus();
    const port = measureScrollport(el, 300, 200, 100, 60);
    fireEvent.keyDown(title, { key: "ArrowUp" }); expect(el.style.top).toBe("60px");
    port.scrollTop = 90; fireEvent.keyDown(title, { key: "ArrowUp" }); expect(el.style.top).toBe("90px");
    const count = postTypedEventMock.mock.calls.length; measureScrollport(el, 0, 200);
    expect(fireEvent.keyDown(title, { key: "ArrowRight" })).toBe(true); expect(postTypedEventMock).toHaveBeenCalledTimes(count);
  });
  it.each([{ ctrlKey: true }, { metaKey: true }, { altKey: true }, { shiftKey: true }, { isComposing: true }])("refuses key ownership %j", async (options) => {
    await single(); const title = titleEl(); title.focus();
    expect(fireEvent.keyDown(title, { key: "ArrowRight", ...options })).toBe(true); expect(postTypedEventMock).not.toHaveBeenCalled();
  });
  it("refuses consumed, AltGraph, sibling/body and detached title origins", async () => {
    const view = await single(); const title = titleEl(); title.focus();
    for (const prevented of [true, false]) {
      const event = new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, cancelable: true });
      if (prevented) event.preventDefault(); else Object.defineProperty(event, "getModifierState", { value: (key: string) => key === "AltGraph" });
      fireEvent(title, event);
    }
    fireEvent.keyDown(document.body, { key: "ArrowRight" });
    const outside = document.createElement("button"); document.body.appendChild(outside); outside.focus(); fireEvent.keyDown(title, { key: "ArrowRight" }); outside.remove();
    view.unmount(); fireEvent.keyDown(title, { key: "ArrowRight" }); expect(postTypedEventMock).not.toHaveBeenCalled();
  });
  it.each(["hidden", "aria-hidden", "inert"])("refuses %s block ancestry", async (attribute) => {
    await single(); const title = titleEl(), el = blockEl("i1"); title.focus(); el.setAttribute(attribute, attribute === "aria-hidden" ? "true" : "");
    expect(fireEvent.keyDown(title, { key: "ArrowRight" })).toBe(true); expect(postTypedEventMock).not.toHaveBeenCalled();
  });
  it("keeps real detail/source actions and diligence draft/node identity during movement and callback rerender", async () => {
    getDistillationMock.mockResolvedValue({ insights: [insight("i1", "Current block")], questions: [] }); getTrajectoryMock.mockResolvedValue({ events: [] });
    const first = vi.fn(), latest = vi.fn(), cite = vi.fn();
    const view = render(<Canvas investigationId="A" onOpenDetail={first} onCiteSource={cite} />); await screen.findByText("Current block");
    const el = blockEl("i1"), title = titleEl(), detail = screen.getByRole("button", { name: "Open block detail" });
    detail.focus(); fireEvent.keyDown(detail, { key: "ArrowRight" }); expect(postTypedEventMock).not.toHaveBeenCalled(); fireEvent.click(detail); expect(first).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "read source" })); expect(cite).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /flag for diligence/i }));
    const draft = screen.getByRole("textbox"); fireEvent.change(draft, { target: { value: "Keep this diligence draft" } });
    title.focus(); fireEvent.keyDown(title, { key: "ArrowRight" }); expect(postTypedEventMock).not.toHaveBeenCalled();
    view.rerender(<Canvas investigationId="A" onOpenDetail={latest} onCiteSource={cite} />);
    expect(blockEl("i1")).toBe(el); expect(screen.getByRole("textbox")).toBe(draft); expect(draft).toHaveProperty("value", "Keep this diligence draft");
    fireEvent.click(detail); expect(latest).toHaveBeenCalledTimes(1); expect(first).toHaveBeenCalledTimes(1); expect(getDistillationMock).toHaveBeenCalledTimes(1);
  });
  it("scopes nonmodal composers to their own block but respects a real top modal", async () => {
    getDistillationMock.mockResolvedValue({ insights: [insight("i1", "First"), insight("i2", "Second")], questions: [] }); getTrajectoryMock.mockResolvedValue({ events: [] });
    render(<Canvas investigationId="A" />); await screen.findByText("Second");
    fireEvent.click(blockEl("i1").querySelector('button')!);
    const own = titleEl("i1"), other = titleEl("i2"); own.focus(); fireEvent.keyDown(own, { key: "ArrowRight" }); expect(postTypedEventMock).not.toHaveBeenCalled();
    other.focus(); fireEvent.keyDown(other, { key: "ArrowRight" }); expect(postTypedEventMock).toHaveBeenCalledTimes(1);
    render(<LemonModal open title="Global modal" onClose={() => {}}><input /></LemonModal>); other.focus(); fireEvent.keyDown(other, { key: "ArrowRight" }); expect(postTypedEventMock).toHaveBeenCalledTimes(1);
  });
  it("disable/resume keeps committed position and drafts, discards pointer preview and cannot redeem old pointerup", async () => {
    const view = await single(); const el = blockEl("i1"), title = titleEl(); title.focus(); fireEvent.keyDown(title, { key: "ArrowRight" });
    const committed = el.style.left;
    fireEvent.pointerDown(el, { pointerId: 4, clientX: 0, clientY: 0 }); fireEvent.pointerMove(el, { pointerId: 4, clientX: 100, clientY: 0 }); expect(el.style.left).not.toBe(committed);
    view.rerender(<Canvas investigationId="inv-1" interactionEnabled={false} />);
    expect(el.style.left).toBe(committed); expect(el.closest("[inert]")).not.toBeNull(); expect(proto.releasePointerCapture).toHaveBeenCalledWith(4);
    title.focus(); fireEvent.keyDown(title, { key: "ArrowRight" });
    view.rerender(<Canvas investigationId="inv-1" interactionEnabled />);
    fireEvent.pointerUp(el, { pointerId: 4 }); fireEvent.pointerCancel(el, { pointerId: 4 }); expect(postTypedEventMock).toHaveBeenCalledTimes(1);
    expect(blockEl("i1")).toBe(el); expect(getDistillationMock).toHaveBeenCalledTimes(1);
    fireEvent.pointerDown(el, { pointerId: 5, clientX: 0, clientY: 0 }); fireEvent.pointerMove(el, { pointerId: 5, clientX: 24, clientY: 0 }); fireEvent.pointerUp(el, { pointerId: 5 });
    expect(postTypedEventMock).toHaveBeenCalledTimes(2); expect(el.style.left).toBe(`${parseFloat(committed) + 24}px`);
  });
  it("retains explicit admitted pointercancel persistence and same-batch pointer coordinates", async () => {
    await single(); const el = blockEl("i1"), x = parseFloat(el.style.left);
    act(() => { fireEvent.pointerDown(el, { pointerId: 1, clientX: 0, clientY: 0 }); fireEvent.pointerMove(el, { pointerId: 1, clientX: 45, clientY: 30 }); fireEvent.pointerCancel(el, { pointerId: 1 }); });
    expect(postTypedEventMock).toHaveBeenCalledTimes(1); expect(postTypedEventMock.mock.calls[0][0].payload.x).toBe(x + 45);
  });
  it("POST completions never cause later dispatch/state changes and a successful ack without replay still falls back", async () => {
    const view = await single(); const a = deferred<unknown>(), b = deferred<unknown>(); postTypedEventMock.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise);
    const title = titleEl(), el = blockEl("i1"), start = el.style.left; title.focus(); fireEvent.keyDown(title, { key: "ArrowRight" }); fireEvent.keyDown(title, { key: "ArrowRight" });
    const final = el.style.left; expect(postTypedEventMock).toHaveBeenCalledTimes(2);
    await act(async () => { b.resolve({ event_id: "later-invocation-first-response" }); a.resolve({ event_id: "first-invocation-last-response" }); });
    expect(el.style.left).toBe(final); expect(postTypedEventMock).toHaveBeenCalledTimes(2);
    view.unmount(); render(<Canvas investigationId="inv-1" />); await screen.findByText("Current block");
    expect(blockEl("i1").style.left).toBe(start); expect(postTypedEventMock).toHaveBeenCalledTimes(2);
  });
});

describe("resource and attempt lifetime", () => {
  it("A/B/A creates a fresh resource even with shared node IDs, and ignores late old error", async () => {
    const firstA = deferred<unknown>(), b = deferred<unknown>(); let aReads = 0;
    getDistillationMock.mockImplementation((id: string) => id === "B" ? b.promise : ++aReads === 1 ? firstA.promise : Promise.resolve({ insights: [insight("same", "Fresh A")], questions: [] }));
    getTrajectoryMock.mockResolvedValue({ events: [] });
    const view = render(<Canvas investigationId="A" />); view.rerender(<Canvas investigationId="B" />); view.rerender(<Canvas investigationId="A" />); await screen.findByText("Fresh A");
    await act(async () => { firstA.reject(new Error("old A")); b.resolve({ insights: [insight("same", "Old B")], questions: [] }); });
    expect(screen.getByText("Fresh A")).toBeTruthy(); expect(screen.queryByText("Old B")).toBeNull(); expect(screen.queryByText("Couldn’t load the canvas")).toBeNull();
  });
  it("resource change removes old shared-node positions and invalidates an unfinished gesture", async () => {
    getDistillationMock.mockImplementation((id: string) => Promise.resolve({ insights: [insight("same", id)], questions: [] })); getTrajectoryMock.mockResolvedValue({ events: [] });
    const view = render(<Canvas investigationId="A" />); await screen.findByText("A"); const old = blockEl("same");
    fireEvent.pointerDown(old, { pointerId: 1, clientX: 0, clientY: 0 }); fireEvent.pointerMove(old, { pointerId: 1, clientX: 100, clientY: 100 });
    view.rerender(<Canvas investigationId="B" />); expect(screen.queryByText("A")).toBeNull(); await screen.findByText("B");
    expect(blockEl("same")).not.toBe(old); expect(blockEl("same").style.left).toBe("40px"); fireEvent.pointerUp(old, { pointerId: 1 }); expect(postTypedEventMock).not.toHaveBeenCalled();
  });
  it("current error retry works and unmounted deferred results cannot create effects", async () => {
    getDistillationMock.mockRejectedValueOnce(new Error("unavailable")).mockResolvedValueOnce({ insights: [insight("i1", "Recovered")], questions: [] }); getTrajectoryMock.mockResolvedValue({ events: [] });
    const view = render(<Canvas investigationId="A" />); fireEvent.click(await screen.findByRole("button", { name: "Try again" })); await screen.findByText("Recovered");
    expect(getDistillationMock).toHaveBeenCalledTimes(2); view.unmount();
    const held = deferred<unknown>(); getDistillationMock.mockReturnValue(held.promise); const last = render(<Canvas investigationId="B" />); last.unmount();
    await act(async () => { held.resolve({ insights: [insight("i1", "Late")], questions: [] }); }); expect(screen.queryByText("Late")).toBeNull(); expect(postTypedEventMock).not.toHaveBeenCalled();
  });
});


function capturedCard() {
  const props = captured.cards.at(-1); if (!props) throw new Error("No actual BlockCard props recorded"); return props;
}
function capturedRetry() {
  const retry = captured.retries.at(-1); if (!retry) throw new Error("No actual retry recorded"); return retry;
}
describe("retained actual-component callback entries", () => {
  it("old error retry cannot issue reads after a current same-ID attempt starts or accepts", async () => {
    const held = deferred<unknown>(); getDistillationMock.mockRejectedValueOnce(new Error("first failure")).mockReturnValueOnce(held.promise); getTrajectoryMock.mockResolvedValue({ events: [] });
    render(<Canvas investigationId="A" />); await screen.findByRole("button", { name: "Try again" }); const retry = capturedRetry();
    act(() => { retry(); retry(); }); expect(getDistillationMock).toHaveBeenCalledTimes(2);
    await act(async () => { held.resolve({ insights: [insight("i1", "Recovered")], questions: [] }); }); await screen.findByText("Recovered");
    act(() => { retry(); }); expect(getDistillationMock).toHaveBeenCalledTimes(2); expect(getTrajectoryMock).toHaveBeenCalledTimes(2);
  });
  it("old retry stays retired after resource ABA and after unmount", async () => {
    getDistillationMock.mockRejectedValueOnce(new Error("old A")).mockResolvedValue({ insights: [insight("i1", "Fresh")], questions: [] }); getTrajectoryMock.mockResolvedValue({ events: [] });
    const view = render(<Canvas investigationId="A" />); await screen.findByRole("button", { name: "Try again" }); const old = capturedRetry();
    view.rerender(<Canvas investigationId="B" />); await screen.findByText("Fresh"); view.rerender(<Canvas investigationId="A" />); await screen.findByText("Fresh");
    act(() => { old(); }); expect(getDistillationMock).toHaveBeenCalledTimes(3); view.unmount(); act(() => { old(); }); expect(getDistillationMock).toHaveBeenCalledTimes(3);
  });
  it("old loaded detail/source callbacks refuse ABA, while current same-attempt callbacks use latest host functions", async () => {
    getDistillationMock.mockResolvedValue({ insights: [insight("same", "Block")], questions: [] }); getTrajectoryMock.mockResolvedValue({ events: [] });
    const first = vi.fn(), current = vi.fn(), cite = vi.fn(); const anchor = { left: 1, top: 2, right: 3, bottom: 4, width: 2, height: 2 };
    const view = render(<Canvas investigationId="A" onOpenDetail={first} onCiteSource={cite} />); await screen.findByText("Block");
    const oldA = capturedCard(), node = blockEl("same");
    view.rerender(<Canvas investigationId="A" onOpenDetail={current} onCiteSource={cite} />);
    act(() => { oldA.onOpenDetail?.(oldA.node); }); expect(current).toHaveBeenCalledTimes(1); expect(first).not.toHaveBeenCalled(); expect(blockEl("same")).toBe(node);
    view.rerender(<Canvas investigationId="B" onOpenDetail={current} onCiteSource={cite} />); await screen.findByText("Block");
    view.rerender(<Canvas investigationId="A" onOpenDetail={current} onCiteSource={cite} />); await screen.findByText("Block");
    act(() => { oldA.onOpenDetail?.(oldA.node); oldA.onCiteSource?.(oldA.node, anchor); }); expect(current).toHaveBeenCalledTimes(1); expect(cite).not.toHaveBeenCalled();
    const fresh = capturedCard(); view.unmount(); act(() => { fresh.onOpenDetail?.(fresh.node); fresh.onCiteSource?.(fresh.node, anchor); }); expect(current).toHaveBeenCalledTimes(1); expect(cite).not.toHaveBeenCalled();
  });
  it("interaction disable gates retained detail/source/retry without invalidating accepted reads", async () => {
    const held = deferred<unknown>(); getDistillationMock.mockReturnValue(held.promise); getTrajectoryMock.mockResolvedValue({ events: [] }); const detail = vi.fn(), cite = vi.fn();
    const view = render(<Canvas investigationId="A" onOpenDetail={detail} onCiteSource={cite} />);
    view.rerender(<Canvas investigationId="A" interactionEnabled={false} onOpenDetail={detail} onCiteSource={cite} />);
    await act(async () => { held.resolve({ insights: [insight("i1", "Accepted while disabled")], questions: [] }); }); await screen.findByText("Accepted while disabled");
    const props = capturedCard(), node = blockEl("i1"), anchor = { left: 0, top: 0, right: 1, bottom: 1, width: 1, height: 1 };
    act(() => { props.onOpenDetail?.(props.node); props.onCiteSource?.(props.node, anchor); }); expect(detail).not.toHaveBeenCalled(); expect(cite).not.toHaveBeenCalled();
    view.rerender(<Canvas investigationId="A" onOpenDetail={detail} onCiteSource={cite} />); expect(blockEl("i1")).toBe(node); expect(getDistillationMock).toHaveBeenCalledTimes(1);
    act(() => { capturedCard().onOpenDetail?.(props.node); }); expect(detail).toHaveBeenCalledTimes(1);
    view.unmount(); getDistillationMock.mockRejectedValueOnce(new Error("error"));
    const errorView = render(<Canvas investigationId="B" />); await screen.findByRole("button", { name: "Try again" }); const retry = capturedRetry(); const count = getDistillationMock.mock.calls.length;
    errorView.rerender(<Canvas investigationId="B" interactionEnabled={false} />); act(() => { retry(); }); expect(getDistillationMock).toHaveBeenCalledTimes(count);
  });
  it("invokes each effective POST synchronously and completions after unmount add no effects", async () => {
    const view = await single(); const a = deferred<unknown>(), b = deferred<unknown>(); postTypedEventMock.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise); const title = titleEl(); title.focus();
    act(() => { fireEvent.keyDown(title, { key: "ArrowRight" }); expect(postTypedEventMock).toHaveBeenCalledTimes(1); fireEvent.keyDown(title, { key: "ArrowRight" }); expect(postTypedEventMock).toHaveBeenCalledTimes(2); });
    view.unmount(); await act(async () => { b.reject(new Error("unknown outcome")); a.resolve({ event_id: "accepted" }); }); expect(postTypedEventMock).toHaveBeenCalledTimes(2);
  });
});


describe("commit boundaries", () => {
  it("hides the old resource during the new committed layout before passive load starts", async () => {
    const held = deferred<unknown>(); getDistillationMock.mockImplementation((id: string) => id === "A" ? Promise.resolve({ insights: [insight("same", "Old committed A")], questions: [] }) : held.promise); getTrajectoryMock.mockResolvedValue({ events: [] });
    const observations: boolean[] = [];
    function Host({ id }: { id: string }) {
      useLayoutEffect(() => { if (id === "B") observations.push(Boolean(screen.queryByText("Old committed A"))); }, [id]);
      return <Canvas investigationId={id} />;
    }
    const view = render(<Host id="A" />); await screen.findByText("Old committed A"); view.rerender(<Host id="B" />);
    expect(observations).toEqual([false]);
  });
  it("rechecks the current measured scrollport at pointer-up before immediate dispatch", async () => {
    await single(); const el = blockEl("i1");
    fireEvent.pointerDown(el, { pointerId: 1, clientX: 0, clientY: 0 }); fireEvent.pointerMove(el, { pointerId: 1, clientX: 500, clientY: 400 });
    measureScrollport(el, 300, 200, 100, 60); fireEvent.pointerUp(el, { pointerId: 1 });
    expect(postTypedEventMock.mock.calls[0][0].payload).toMatchObject({ x: 320, y: 180 }); expect(el.style.left).toBe("320px"); expect(el.style.top).toBe("180px");
  });
});


it("leaves an active pointer gesture to pointer-end before admitting a fresh title arrow", async () => {
  await single(); const title = titleEl(), el = blockEl("i1"); title.focus();
  fireEvent.pointerDown(el, { pointerId: 1, clientX: 0, clientY: 0 }); fireEvent.pointerMove(el, { pointerId: 1, clientX: 30, clientY: 20 }); const preview = el.style.left;
  expect(fireEvent.keyDown(title, { key: "ArrowRight" })).toBe(true); expect(el.style.left).toBe(preview); expect(postTypedEventMock).not.toHaveBeenCalled();
  fireEvent.pointerUp(el, { pointerId: 1 }); expect(postTypedEventMock).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(title, { key: "ArrowRight" }); expect(postTypedEventMock).toHaveBeenCalledTimes(2); expect(el.style.left).toBe(`${parseFloat(preview) + 24}px`);
});

it("retains the actual diligence draft through disabled and enabled commits without reloading", async () => {
  const view = await single(); const block = blockEl("i1");
  fireEvent.click(screen.getByRole("button", { name: /flag for diligence/i }));
  const draft = screen.getByRole("textbox");
  fireEvent.change(draft, { target: { value: "Retained across suspension" } });
  view.rerender(<Canvas investigationId="inv-1" interactionEnabled={false} />);
  expect(draft.closest("[inert]")).not.toBeNull();
  expect(screen.getByRole("textbox")).toBe(draft);
  view.rerender(<Canvas investigationId="inv-1" interactionEnabled />);
  expect(blockEl("i1")).toBe(block); expect(screen.getByRole("textbox")).toBe(draft);
  expect(draft).toHaveProperty("value", "Retained across suspension");
  expect(getDistillationMock).toHaveBeenCalledTimes(1); expect(postTypedEventMock).not.toHaveBeenCalled();
});

it("restores committed preview without dispatch when measured bounds disappear before pointer-end", async () => {
  await single(); const block = blockEl("i1"), initial = block.style.left;
  fireEvent.pointerDown(block, { pointerId: 8, clientX: 0, clientY: 0 });
  fireEvent.pointerMove(block, { pointerId: 8, clientX: 100, clientY: 0 });
  expect(block.style.left).not.toBe(initial); measureScrollport(block, 0, 0);
  fireEvent.pointerUp(block, { pointerId: 8 });
  expect(block.style.left).toBe(initial); expect(postTypedEventMock).not.toHaveBeenCalled();
  expect(proto.releasePointerCapture).toHaveBeenCalledWith(8);
});


it("admits a block inside its actual focused persistent panel without moving the panel", async () => {
  disablePersistence(); useWorkspace.getState().reset();
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
  getDistillationMock.mockResolvedValue({ insights: [insight("i1", "Panel block")], questions: [] });
  getTrajectoryMock.mockResolvedValue({ events: [] });
  useWorkspace.getState().open("Notes", {}, { id: "canvas-host", title: "Canvas host", mode: "floating" });
  const view = render(<PanelLayoutPanel id="canvas-host" />);
  try {
    await screen.findByText("Panel block");
    const title = titleEl(), region = screen.getByRole("region", { name: "Canvas host" });
    const before = useWorkspace.getState().panels["canvas-host"];
    expect(region.hasAttribute("data-esc-overlay")).toBe(true);
    title.focus(); fireEvent.keyDown(title, { key: "ArrowRight" });
    expect(postTypedEventMock).toHaveBeenCalledTimes(1);
    expect(useWorkspace.getState().panels["canvas-host"]).toBe(before);
  } finally {
    view.unmount(); useWorkspace.getState().reset(); vi.unstubAllGlobals();
  }
});
