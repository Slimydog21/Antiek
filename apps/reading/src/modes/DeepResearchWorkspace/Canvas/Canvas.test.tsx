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

import type { DistilledNode } from "../../../lib/api";
import type { Event } from "../../../generated/types";

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

import Canvas from "./Canvas";

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
