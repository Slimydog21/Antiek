import type { ComponentProps } from "react";
import type { CanvasProps } from "./Canvas/Canvas";
import type BlockDetail from "./BlockDetail";
import { LemonModal } from "../../components/lemon/LemonModal";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const captured = vi.hoisted(() => {
  const canvases: CanvasProps[] = [];
  const details: ComponentProps<typeof BlockDetail>[] = [];
  return { canvases, details };
});
// These wrappers retain callback props and render the actual children without substitution.
vi.mock("./Canvas/Canvas", async (original) => {
  const actual = await original<typeof import("./Canvas/Canvas")>();
  return { ...actual, default: (props: CanvasProps) => { captured.canvases.push(props); return <actual.default {...props} />; } };
});
vi.mock("./BlockDetail", async (original) => {
  const actual = await original<typeof import("./BlockDetail")>();
  return { ...actual, default: (props: ComponentProps<typeof BlockDetail>) => { captured.details.push(props); return <actual.default {...props} />; } };
});

const boundary = vi.hoisted(() => ({
  session: {
    current: {
      researches: [
        { investigation_id: "A", sub_question: "Research A", state: "done" },
        { investigation_id: "B", sub_question: "Research B", state: "running" },
      ],
      cost: null,
      live: true,
      allTerminal: false,
      loading: false,
      error: null as string | null,
    },
  },
  getDistillation: vi.fn(),
  getTrajectory: vi.fn(),
  postTypedEvent: vi.fn(),
  openWindow: vi.fn(),
}));

// External session/API/telemetry and unrelated lazy presentation are controlled.
// Monitor is the candidate host; Canvas, BlockCard and BlockDetail remain the actual accepted modules.
vi.mock("./useResearchSession", () => ({
  useResearchSession: () => boundary.session.current,
}));
vi.mock("./useMascotResearchReactions", () => ({
  useMascotResearchReactions: () => undefined,
}));
vi.mock("../../lib/api", async (original) => ({
  ...(await original<typeof import("../../lib/api")>()),
  getDistillation: boundary.getDistillation,
  getTrajectory: boundary.getTrajectory,
  postTypedEvent: boundary.postTypedEvent,
}));
vi.mock("../../lib/analytics", () => ({ track: vi.fn() }));
vi.mock("../../arcade/waitArcadeFlag", () => ({ mascotResearchWaitArcadeEnabled: false }));
vi.mock("../../workspace/usePrefersReducedMotion", () => ({ usePrefersReducedMotion: () => false }));

vi.mock("../../components/windows/openWindow", async (original) => ({
  ...(await original<typeof import("../../components/windows/openWindow")>()), openWindow: boundary.openWindow,
}));

import { Monitor } from "./index";

const proto = window.HTMLElement.prototype as unknown as Record<string, unknown>;
const pointer = {
  set: proto.setPointerCapture,
  release: proto.releasePointerCapture,
  has: proto.hasPointerCapture,
};

// Explicit controlled graph fixture; not a book, provider response or native result.
function node(id: string) {
  return {
    node_id: `${id}-node`, kind: "insight", text: `${id} detail text`, confidence: "high",
    source_document_id: `${id}-document`, refinement_count: 0, escalated: false,
    reserved_child_investigation_id: null,
  };
}

function mount() {
  return render(<MemoryRouter><Monitor sessionId="controlled-session" sessionGeneration={1} busy={false} /></MemoryRouter>);
}

function measureCanvas() {
  const port = screen.getByTestId("block-canvas");
  Object.defineProperty(port, "clientWidth", { configurable: true, value: 800 });
  Object.defineProperty(port, "clientHeight", { configurable: true, value: 600 });
  return port;
}

beforeEach(() => {
  captured.canvases.length = 0; captured.details.length = 0; boundary.openWindow.mockClear();
  boundary.session.current = {
    researches: [
      { investigation_id: "A", sub_question: "Research A", state: "done" },
      { investigation_id: "B", sub_question: "Research B", state: "running" },
    ], cost: null, live: true, allTerminal: false, loading: false, error: null,
  };
  boundary.getDistillation.mockImplementation((id: string) => Promise.resolve({ investigation_id: id, insights: [node(id)], questions: [] }));
  boundary.getTrajectory.mockImplementation((id: string) => Promise.resolve({ investigation_id: id, events: [] }));
  boundary.postTypedEvent.mockResolvedValue({ event_id: "controlled-unit-ack" });
  proto.setPointerCapture = vi.fn();
  proto.releasePointerCapture = vi.fn();
  proto.hasPointerCapture = vi.fn(() => false);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  boundary.getDistillation.mockReset();
  boundary.getTrajectory.mockReset();
  boundary.postTypedEvent.mockReset();
  proto.setPointerCapture = pointer.set;
  proto.releasePointerCapture = pointer.release;
  proto.hasPointerCapture = pointer.has;
});

describe("actual Monitor/Canvas/BlockDetail join (UNIT baseline)", () => {
  it("keeps same Canvas mounted but bars a focused underlying title while detail covers it", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "view as canvas" }));
    await screen.findByText("A detail text");
    const port = measureCanvas();
    const title = screen.getByRole("group", { name: "Move insight block" });
    title.focus();
    fireEvent.click(screen.getByRole("button", { name: "Open block detail" }));
    expect(screen.getByRole("button", { name: "Close block detail" })).toBeTruthy();
    expect(screen.getByTestId("block-canvas")).toBe(port);
    fireEvent.keyDown(title, { key: "ArrowRight" });
    const hazards = {
      canvasInert: port.hasAttribute("inert"),
      focusLeftUnderlyingTitle: document.activeElement !== title,
      newPositionWrites: boundary.postTypedEvent.mock.calls.length,
    };
    fireEvent.click(screen.getByRole("button", { name: "Close block detail" }));
    expect(screen.getByTestId("block-canvas")).toBe(port);
    expect(boundary.getDistillation).toHaveBeenCalledTimes(1);
    expect(hazards).toEqual({ canvasInert: true, focusLeftUnderlyingTitle: true, newPositionWrites: 0 });
  });

  it("does not pair A's detail with B after back and a different completed research is selected", async () => {
    const view = mount();
    fireEvent.click(screen.getByRole("button", { name: "view as canvas" }));
    await screen.findByText("A detail text");
    measureCanvas();
    fireEvent.click(screen.getByRole("button", { name: "Open block detail" }));
    expect(screen.getAllByText("A detail text").length).toBeGreaterThan(1);
    boundary.session.current = {
      ...boundary.session.current,
      researches: [
        { investigation_id: "B", sub_question: "Research B", state: "done" },
        { investigation_id: "A", sub_question: "Research A", state: "running" },
      ],
    };
    fireEvent.click(screen.getByRole("button", { name: /back to monitor/ }));
    view.rerender(<MemoryRouter><Monitor sessionId="controlled-session" sessionGeneration={1} busy={false} /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "view as canvas" }));
    await screen.findByText("B detail text");
    expect(screen.queryByRole("button", { name: "Close block detail" })).toBeNull();
    expect(screen.queryByText("A detail text")).toBeNull();
  });
});


function latestCanvas() {
  const value = captured.canvases.at(-1);
  if (!value) throw new Error("Actual Canvas has not rendered");
  return value;
}
function latestDetail() {
  const value = captured.details.at(-1);
  if (!value) throw new Error("Actual BlockDetail has not rendered");
  return value;
}
async function enterCanvas() {
  const view = mount();
  fireEvent.click(screen.getByRole("button", { name: "view as canvas" }));
  await screen.findByText("A detail text");
  return view;
}
function openFromTitle() {
  const title = screen.getByRole("group", { name: "Move insight block" });
  title.focus();
  fireEvent.click(screen.getByRole("button", { name: "Open block detail" }));
  return title;
}
async function selectCompleted(view: ReturnType<typeof mount>, id: string) {
  boundary.session.current = { ...boundary.session.current, researches: [
    { investigation_id: id, sub_question: `Research ${id}`, state: "done" },
  ] };
  fireEvent.click(screen.getByRole("button", { name: /back to monitor/ }));
  view.rerender(<MemoryRouter><Monitor sessionId="controlled-session" sessionGeneration={1} busy={false} /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "view as canvas" }));
  await screen.findByText(`${id} detail text`);
}

describe("detail resource lifetime and connected focus (controlled UNIT)", () => {
  it("keeps movement, scroll, load and DOM identity and restores the connected opener after closing", async () => {
    await enterCanvas(); const port = measureCanvas();
    const title = screen.getByRole("group", { name: "Move insight block" });
    const block = title.closest("[data-draggable-block]");
    if (!(block instanceof HTMLElement)) throw new Error("Missing actual block");
    title.focus(); fireEvent.keyDown(title, { key: "ArrowRight" });
    const left = block.style.left; port.scrollTop = 87; port.scrollLeft = 13;
    fireEvent.click(screen.getByRole("button", { name: "Open block detail" }));
    const close = screen.getByRole("button", { name: "Close block detail" });
    expect(document.activeElement).toBe(close); expect(port.hasAttribute("inert")).toBe(true);
    fireEvent.click(close);
    expect(document.activeElement).toBe(title); expect(port.hasAttribute("inert")).toBe(false);
    expect(screen.getByTestId("block-canvas")).toBe(port); expect(title.closest("[data-draggable-block]")).toBe(block);
    expect(block.style.left).toBe(left); expect(port.scrollTop).toBe(87); expect(port.scrollLeft).toBe(13);
    expect(boundary.getDistillation).toHaveBeenCalledTimes(1); expect(boundary.getTrajectory).toHaveBeenCalledTimes(1);
    expect(boundary.postTypedEvent).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(title, { key: "ArrowDown" }); expect(boundary.postTypedEvent).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "read source" }));
    expect(boundary.openWindow).toHaveBeenCalledWith("reader", { documentId: "A-document", origin: { from: "evidence", id: "A" } }, expect.any(Object));
  });

  it("refuses underlying movement, detail and source commands while its matching detail is active", async () => {
    await enterCanvas(); measureCanvas(); const before = latestCanvas(); const title = openFromTitle();
    const close = screen.getByRole("button", { name: "Close block detail" });
    const detail = latestDetail(); const block = title.closest("[data-draggable-block]");
    if (!(block instanceof HTMLElement)) throw new Error("Missing actual block");
    title.focus(); fireEvent.keyDown(title, { key: "ArrowRight" });
    fireEvent.pointerDown(block, { pointerId: 1, clientX: 0, clientY: 0 });
    fireEvent.pointerMove(block, { pointerId: 1, clientX: 50, clientY: 50 }); fireEvent.pointerUp(block, { pointerId: 1 });
    fireEvent.click(screen.getByRole("button", { name: "Open block detail" }));
    fireEvent.click(screen.getByRole("button", { name: "read source" }));
    act(() => {
      before.onOpenDetail?.(node("retained-call"));
      before.onCiteSource?.(node("A"), { left: 1, right: 2, top: 1, bottom: 2, width: 1, height: 1 });
    });
    expect(screen.getByRole("button", { name: "Close block detail" })).toBe(close);
    expect(latestDetail().node).toBe(detail.node);
    expect(boundary.postTypedEvent).not.toHaveBeenCalled(); expect(boundary.openWindow).not.toHaveBeenCalled();
  });

  it("retires retained A open, source and close callbacks across B and a fresh A selection", async () => {
    const view = await enterCanvas(); const oldCanvas = latestCanvas(); openFromTitle(); const oldClose = latestDetail().onClose;
    await selectCompleted(view, "B"); openFromTitle(); const bClose = screen.getByRole("button", { name: "Close block detail" });
    act(() => { oldCanvas.onOpenDetail?.(node("A")); oldClose?.(); });
    expect(screen.getByRole("button", { name: "Close block detail" })).toBe(bClose);
    expect(latestDetail().investigationId).toBe("B"); expect(latestDetail().node.node_id).toBe("B-node");
    await selectCompleted(view, "A");
    act(() => {
      oldCanvas.onOpenDetail?.(node("A")); oldClose?.();
      oldCanvas.onCiteSource?.(node("A"), { left: 1, right: 2, top: 1, bottom: 2, width: 1, height: 1 });
    });
    expect(screen.queryByRole("button", { name: "Close block detail" })).toBeNull();
    expect(boundary.openWindow).not.toHaveBeenCalled();
    openFromTitle(); expect(latestDetail().investigationId).toBe("A");
  });

  it("does not let an old same-resource close dismiss a newer detail or steal its focus", async () => {
    await enterCanvas(); openFromTitle(); const firstClose = latestDetail().onClose;
    fireEvent.click(screen.getByRole("button", { name: "Close block detail" }));
    openFromTitle(); const currentClose = screen.getByRole("button", { name: "Close block detail" });
    act(() => { firstClose?.(); });
    expect(screen.getByRole("button", { name: "Close block detail" })).toBe(currentClose);
    expect(document.activeElement).toBe(currentClose);
  });

  it("retires a current callback immediately when back is requested before React disposes Canvas", async () => {
    await enterCanvas(); const old = latestCanvas();
    act(() => { fireEvent.click(screen.getByRole("button", { name: /back to monitor/ })); old.onOpenDetail?.(node("A")); });
    expect(screen.queryByRole("button", { name: "Close block detail" })).toBeNull();
    expect(screen.getByRole("button", { name: "view as canvas" })).toBeTruthy();
  });

  it.each(["disconnected", "disabled", "inert"])("does not restore a %s opener", async (condition) => {
    await enterCanvas(); measureCanvas();
    const opener = screen.getByRole("button", { name: "Open block detail" }); opener.focus(); fireEvent.click(opener);
    if (condition === "disconnected") opener.remove(); else opener.setAttribute(condition, "");
    fireEvent.click(screen.getByRole("button", { name: "Close block detail" }));
    expect(document.activeElement).not.toBe(opener);
  });

  it("preserves a separate real modal's focus on detail open and close", async () => {
    await enterCanvas(); const callback = latestCanvas().onOpenDetail;
    render(<LemonModal open title="Priority modal" onClose={() => {}}><input aria-label="Priority input" /></LemonModal>);
    const input = screen.getByRole("textbox", { name: "Priority input" }); input.focus();
    act(() => { callback?.(node("A")); });
    expect(document.activeElement).toBe(input);
    act(() => { latestDetail().onClose?.(); });
    expect(document.activeElement).toBe(input);
  });

  it("does not restore over a surviving outside control or resurrect after unmount", async () => {
    const view = await enterCanvas(); const oldCanvas = latestCanvas(); openFromTitle(); const close = latestDetail().onClose;
    const outside = document.createElement("button"); outside.textContent = "Controlled outside focus"; document.body.appendChild(outside);
    try {
      outside.focus(); act(() => { close?.(); }); expect(document.activeElement).toBe(outside);
      view.unmount(); act(() => { oldCanvas.onOpenDetail?.(node("A")); close?.(); });
      expect(screen.queryByRole("button", { name: "Close block detail" })).toBeNull(); expect(document.activeElement).toBe(outside);
    } finally { outside.remove(); }
  });
});


it("leaves a real detail FloatMenu's focus alone across a monitor rerender", async () => {
  const view = await enterCanvas(); openFromTitle();
  const text = screen.getAllByText("A detail text").find((element) => element.tagName === "DIV" && element.classList.contains("font-serif"));
  if (!text?.firstChild) throw new Error("Missing actual detail selection scope");
  const range = document.createRange(); range.selectNodeContents(text);
  range.getBoundingClientRect = () => new DOMRect(100, 200, 80, 18);
  const selection = window.getSelection();
  if (!selection) throw new Error("Missing controlled DOM selection");
  selection.removeAllRanges(); selection.addRange(range);
  act(() => { document.dispatchEvent(new Event("selectionchange")); });
  const note = await screen.findByRole("menuitem", { name: "Note" }); note.focus();
  view.rerender(<MemoryRouter><Monitor sessionId="controlled-session" sessionGeneration={2} busy={false} /></MemoryRouter>);
  expect(document.activeElement).toBe(note); expect(screen.getByRole("menu", { name: "Highlight actions" })).toBeTruthy();
  expect(boundary.postTypedEvent).not.toHaveBeenCalled();
  act(() => { latestDetail().onClose?.(); });
  expect(document.activeElement).not.toBe(screen.getByRole("group", { name: "Move insight block" }));
  selection.removeAllRanges();
});


it("does not steal focus acquired outside between opening and the committed detail", async () => {
  await enterCanvas(); const title = screen.getByRole("group", { name: "Move insight block" }); title.focus();
  const outside = document.createElement("button"); outside.textContent = "Controlled focus competitor"; document.body.appendChild(outside);
  try {
    act(() => { latestCanvas().onOpenDetail?.(node("A")); outside.focus(); });
    expect(screen.getByRole("button", { name: "Close block detail" })).toBeTruthy();
    expect(document.activeElement).toBe(outside);
  } finally { outside.remove(); }
});
