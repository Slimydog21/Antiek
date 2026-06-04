/**
 * Dialogue.spr06.test.tsx — antiek-reader SPR-06 gates for the Dialogue action
 * (run: `npx vitest run Dialogue.spr06`).
 *
 * Asserts, against the api boundary mocked with a real ReadableStream (the SSE
 * cassette — NOT a live model; the backend's own test holds the real-dispatch
 * proof):
 *   - M1: the request carries the passage + the resolved Region (anchor), and a
 *     no-key error frame surfaces the honest AIActionFailure (not a fake reply);
 *   - M2: token frames render PROGRESSIVELY (the panel shows the partial while
 *     streaming), and a mid-stream interruption (body ends with no terminal
 *     frame) surfaces a RECOVERABLE state with a Retry — never a frozen UI;
 *   - M3/M4: a `thread` frame marks the conversation persisted (anchored);
 *     a selection with NO resolvable Region is labelled honestly as un-saved;
 *   - multi-turn: a completed turn is carried as history into the next request.
 *
 * INERT-without-keys: a green run here means "the streamed, anchored gesture is
 * real and lights up when keys land," NOT "the operator can talk to a passage."
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useRef } from "react";

// One shared apiFetch mock — each test sets its response (an SSE stream / error).
const apiFetchMock = vi.fn();

vi.mock("../../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../lib/api")>();
  return { ...actual, apiFetch: (input: unknown, init?: unknown) => apiFetchMock(input, init) };
});

// Voice mock (the panel mounts useVoiceCapture) — idle, never used here.
vi.mock("../../../hooks/useVoiceCapture", () => ({
  useVoiceCapture: () => ({
    phase: "idle",
    error: null,
    recorderState: "idle",
    result: null,
    start: vi.fn(async () => {}),
    stopAndCapture: vi.fn(async () => null),
    reset: () => {},
  }),
}));

import FloatMenu from "./FloatMenu";
import { regionOfSelection, streamDialogueOverSelection } from "./floatMenuActions";
import type { FloatMenuSelection } from "./useFloatMenuSelection";
import { useFloatMenuSelection } from "./useFloatMenuSelection";

// ── SSE stream helpers ──────────────────────────────────────────────────────

/** Build a Response whose body streams the given SSE frames (each a `data: …`
 * line + blank-line separator), optionally WITHOUT a terminal frame to simulate
 * a mid-stream interruption. */
function sseResponse(frames: object[], { terminate = true }: { terminate?: boolean } = {}): Response {
  const enc = new TextEncoder();
  const lines = frames.map((f) => `data: ${JSON.stringify(f)}\n\n`);
  // A non-terminated stream just ends after the partial frames (no done/error).
  void terminate;
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const l of lines) controller.enqueue(enc.encode(l));
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

// jsdom selection helper (same pattern as FloatMenu.test.tsx).
function selectTextIn(scope: HTMLElement, text: string, rect = { top: 200, left: 100, width: 80, height: 18 }) {
  if (!scope.firstChild) scope.appendChild(document.createTextNode(text));
  const node = scope.firstChild as Text;
  const range = document.createRange();
  range.setStart(node, 0);
  range.setEnd(node, node.textContent?.length ?? text.length);
  range.getBoundingClientRect = () =>
    ({ ...rect, right: rect.left + rect.width, bottom: rect.top + rect.height, x: rect.left, y: rect.top, toJSON() { return rect; } }) as DOMRect;
  vi.spyOn(window, "getSelection").mockReturnValue({
    rangeCount: 1, getRangeAt: () => range, toString: () => text, removeAllRanges: () => {},
  } as unknown as Selection);
  act(() => {
    document.dispatchEvent(new Event("selectionchange"));
  });
}

function Host({ provenance }: { provenance?: FloatMenuSelection["provenance"] }) {
  const scopeRef = useRef<HTMLDivElement>(null);
  const selection = useFloatMenuSelection({
    scopeRef,
    resolveProvenance: provenance ? () => provenance : undefined,
  });
  return (
    <div>
      <div ref={scopeRef} data-testid="scope">the selected passage text</div>
      <FloatMenu selection={selection} investigationId="inv-1" onDeepResearch={vi.fn()} />
    </div>
  );
}

const ANCHORED = { documentId: "doc-1", chunkId: "blk-1", servable: true, charStart: 0, charEnd: 12 };

beforeEach(() => apiFetchMock.mockReset());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ── regionOfSelection (M3 anchor resolution) ────────────────────────────────

describe("regionOfSelection resolves the SPR-01 Region (M3)", () => {
  it("builds a Region from documentId + chunkId + char range", () => {
    const sel: FloatMenuSelection = { text: "x", rect: { top: 0, left: 0, width: 1, height: 1 }, provenance: ANCHORED };
    expect(regionOfSelection(sel)).toEqual({ document_id: "doc-1", block_id: "blk-1", char_start: 0, char_end: 12 });
  });
  it("returns null when no chunk is resolved (free-prose selection — no anchor)", () => {
    const sel: FloatMenuSelection = { text: "x", rect: { top: 0, left: 0, width: 1, height: 1 }, provenance: {} };
    expect(regionOfSelection(sel)).toBeNull();
  });
});

// ── streamDialogueOverSelection (the SSE consumer) ──────────────────────────

describe("streamDialogueOverSelection consumes SSE frames (M2)", () => {
  const sel: FloatMenuSelection = { text: "discuss this passage", rect: { top: 0, left: 0, width: 1, height: 1 }, provenance: ANCHORED };

  it("delivers token frames progressively + a thread frame + done", async () => {
    apiFetchMock.mockResolvedValueOnce(
      sseResponse([
        { kind: "token", text: "alpha " },
        { kind: "token", text: "beta" },
        { kind: "thread", node_id: "question-abc" },
        { kind: "done" },
      ]),
    );
    const events: string[] = [];
    let assembled = "";
    let node: string | null = null;
    await streamDialogueOverSelection({ investigationId: "inv-1", selection: sel }, (ev) => {
      events.push(ev.kind);
      if (ev.kind === "token") assembled += ev.text;
      if (ev.kind === "thread") node = ev.node_id;
    });
    expect(assembled).toBe("alpha beta"); // loss-less concat of progressive chunks
    expect(node).toBe("question-abc");
    expect(events).toEqual(["token", "token", "thread", "done"]);
  });

  it("sends the passage + Region in the request body (anchored)", async () => {
    apiFetchMock.mockResolvedValueOnce(sseResponse([{ kind: "done" }]));
    await streamDialogueOverSelection({ investigationId: "inv-1", selection: sel }, () => {});
    const [, init] = apiFetchMock.mock.calls[0];
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.passage).toBe("discuss this passage");
    expect(body.region).toEqual({ document_id: "doc-1", block_id: "blk-1", char_start: 0, char_end: 12 });
  });

  it("a 503 channel surfaces a single recoverable error frame (no fake reply)", async () => {
    apiFetchMock.mockResolvedValueOnce(new Response("no key", { status: 503 }));
    const evs: { kind: string; status?: number }[] = [];
    await streamDialogueOverSelection({ investigationId: "inv-1", selection: sel }, (ev) => evs.push(ev));
    expect(evs).toEqual([{ kind: "error", status: 503, detail: "stream channel HTTP 503" }]);
  });
});

// ── DialoguePanel — progressive render, interruption recovery, persistence ──

describe("DialoguePanel streams, recovers, and persists honestly (M2 + M4)", () => {
  function openDialogue(provenance: FloatMenuSelection["provenance"]) {
    render(<Host provenance={provenance} />);
    selectTextIn(screen.getByTestId("scope"), "discuss this");
    fireEvent.click(screen.getByRole("menuitem", { name: "Dialogue" }));
  }

  it("renders the reply progressively + marks the thread persisted (anchored)", async () => {
    apiFetchMock.mockResolvedValueOnce(
      sseResponse([
        { kind: "token", text: "the model " },
        { kind: "token", text: "reply" },
        { kind: "thread", node_id: "question-xyz" },
        { kind: "done" },
      ]),
    );
    openDialogue(ANCHORED);
    await act(async () => {
      fireEvent.click(screen.getByText("Ask"));
    });
    // The completed turn shows the assembled model reply.
    await waitFor(() => expect(screen.getByText("the model reply")).toBeTruthy());
    // Honest persistence label (M4) — the thread anchored + survives reload.
    expect(screen.getByText(/survives reload/i)).toBeTruthy();
  });

  it("a mid-stream interruption (no terminal frame) surfaces a recoverable Retry, not a frozen UI", async () => {
    // Body ends after one token, WITHOUT a done/error frame → interrupted.
    apiFetchMock.mockResolvedValueOnce(sseResponse([{ kind: "token", text: "partial answer so far" }]));
    openDialogue(ANCHORED);
    await act(async () => {
      fireEvent.click(screen.getByText("Ask"));
    });
    await waitFor(() => expect(document.querySelector("[data-dialogue-interrupted]")).toBeTruthy());
    // The partial is kept (not silently dropped) + a Retry is offered.
    expect(screen.getByText(/partial answer so far/)).toBeTruthy();
    expect(screen.getByText("Retry")).toBeTruthy();
    expect(screen.getByText(/interrupted before it finished/i)).toBeTruthy();
  });

  it("a no-key error frame shows the honest AIActionFailure (not a fabricated reply)", async () => {
    apiFetchMock.mockResolvedValueOnce(sseResponse([{ kind: "error", status: 503, detail: "dispatch_unavailable" }]));
    openDialogue(ANCHORED);
    await act(async () => {
      fireEvent.click(screen.getByText("Ask"));
    });
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/provider isn|no result/i));
  });

  it("an un-anchored selection is labelled honestly as NOT saved", async () => {
    apiFetchMock.mockResolvedValueOnce(sseResponse([{ kind: "token", text: "reply" }, { kind: "done" }]));
    openDialogue({}); // no documentId/chunkId → no Region → no persistence
    await act(async () => {
      fireEvent.click(screen.getByText("Ask"));
    });
    await waitFor(() => expect(screen.getByText(/isn.t saved/i)).toBeTruthy());
  });

  it("carries a completed turn as history into the next request (multi-turn)", async () => {
    apiFetchMock
      .mockResolvedValueOnce(sseResponse([{ kind: "token", text: "first answer" }, { kind: "done" }]))
      .mockResolvedValueOnce(sseResponse([{ kind: "token", text: "second answer" }, { kind: "done" }]));
    openDialogue(ANCHORED);
    // First turn.
    const ta = screen.getByPlaceholderText("Ask about this passage…");
    fireEvent.change(ta, { target: { value: "first question" } });
    await act(async () => {
      fireEvent.click(screen.getByText("Ask"));
    });
    await waitFor(() => expect(screen.getByText("first answer")).toBeTruthy());
    // Second turn — the first (question, answer) is sent as history.
    fireEvent.change(screen.getByPlaceholderText("Ask about this passage…"), { target: { value: "second question" } });
    await act(async () => {
      fireEvent.click(screen.getByText("Ask again"));
    });
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(2));
    const secondBody = JSON.parse((apiFetchMock.mock.calls[1][1] as RequestInit).body as string);
    expect(secondBody.history).toEqual([{ question: "first question", answer: "first answer" }]);
  });
});
