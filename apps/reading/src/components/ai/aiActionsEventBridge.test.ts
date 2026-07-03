import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock postTypedEvent BEFORE importing aiActions so the named-import
// binding in aiActions.ts picks up the mock. vi.mock factories are
// hoisted to the top of the module by vitest.
vi.mock("../../lib/api", () => ({
  postTypedEvent: vi.fn(),
}));

import { dispatchAiAction, type AiActionContext } from "./aiActions";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { EMPTY_SNAPSHOT } from "../../workspace/panel.types";
import { postTypedEvent } from "../../lib/api";

const postTypedEventMock = postTypedEvent as ReturnType<typeof vi.fn>;

/**
 * Event-log bridging tests for the AISidecar dispatcher.
 *
 * Master-spec §5.5 + §13.8 + PostHog Wedge 4 require that every
 * AI-driven UI action emits a typed ``ai.action.applied`` event so
 * trajectory replay (Wedge 5) can re-render the trajectory at any
 * point in time. Undo emits ``ai.action.undone`` linking back to the
 * applied event via ``inverted_event_id``.
 *
 * These tests verify the bridge:
 *   - dispatchAiAction WITHOUT context does NOT emit events
 *     (preserves legacy / test callers + the toast transient case).
 *   - dispatchAiAction WITH context emits AIActionApplied per
 *     stateful action kind (panel ops, notebook write, chase).
 *   - The wrapped undo callable emits AIActionUndone when invoked.
 *   - Toasts (transient) do NOT emit events even when context given.
 */

const CONTEXT: AiActionContext = {
  operator_prompt: "open the Q4 risk PDF and add a note",
  investigation_id: "inv-test-bridge",
};

beforeEach(() => {
  useWorkspace.setState({ ...EMPTY_SNAPSHOT });
  postTypedEventMock.mockReset();
  postTypedEventMock.mockResolvedValue({
    event_id: "evt-fixture",
    action_type: "ai.action.applied",
  });
});

afterEach(() => {
  postTypedEventMock.mockReset();
});

/** Helper: flush pending fire-and-forget Promises before asserting.
 * The bridge chain is: descriptor → sha256Hex (Web Crypto, real async)
 * → postTypedEvent (network mock). A macrotask yield + several
 * microtask rounds drains the whole chain reliably. */
async function flushMicrotasks(): Promise<void> {
  // Macrotask yield — lets the Web Crypto promise resolve.
  await new Promise((r) => setTimeout(r, 0));
  // Several microtask rounds for any chained .then() after the digest.
  for (let i = 0; i < 5; i++) {
    await Promise.resolve();
  }
}

describe("AISidecar event-log bridge", () => {
  it("dispatchAiAction WITHOUT context does NOT emit events", async () => {
    dispatchAiAction({
      kind: "open_panel",
      panel_kind: "FakeNotebook",
      id: "no-ctx-test",
    });
    await flushMicrotasks();
    expect(postTypedEventMock).not.toHaveBeenCalled();
  });

  it("open_panel WITH context emits AIActionApplied with target_kind=ui_layout", async () => {
    dispatchAiAction(
      {
        kind: "open_panel",
        panel_kind: "FakeNotebook",
        props: { docId: "abc" },
        id: "ctx:open",
        title: "Q4",
      },
      CONTEXT,
    );
    // vi.waitFor (not a fixed-round flush): the emit chain includes a real
    // Web Crypto sha256 digest whose resolution can slip past a fixed
    // macrotask+microtask budget on a slower/CI runner — the flake the
    // AGH SPR-04 vitest gate caught (green locally, 0-calls under CI). waitFor
    // retries until the mock is actually called, deterministic on any host.
    await vi.waitFor(() => expect(postTypedEventMock).toHaveBeenCalledTimes(1));
    const call = postTypedEventMock.mock.calls[0][0];
    expect(call.investigation_id).toBe("inv-test-bridge");
    expect(call.role).toBe("ai_sidecar");
    expect(call.payload.action_type).toBe("ai.action.applied");
    const p = call.payload as { target_kind: string; target_id: string; operator_prompt: string; next_state: Record<string, unknown> };
    expect(p.target_kind).toBe("ui_layout");
    expect(p.target_id).toBe("ctx:open");
    expect(p.operator_prompt).toBe(CONTEXT.operator_prompt);
    expect(p.next_state.open).toBe(true);
    expect(p.next_state.kind).toBe("FakeNotebook");
  });

  it("add_to_notebook WITH context emits target_kind=notebook with etag delta", async () => {
    dispatchAiAction(
      {
        kind: "add_to_notebook",
        notebook_id: "scratch",
        block: { kind: "note", text: "Worth chasing." },
      },
      CONTEXT,
    );
    // vi.waitFor (not a fixed-round flush): the emit chain includes a real
    // Web Crypto sha256 digest whose resolution can slip past a fixed
    // macrotask+microtask budget on a slower/CI runner — the flake the
    // AGH SPR-04 vitest gate caught (green locally, 0-calls under CI). waitFor
    // retries until the mock is actually called, deterministic on any host.
    await vi.waitFor(() => expect(postTypedEventMock).toHaveBeenCalledTimes(1));
    const p = postTypedEventMock.mock.calls[0][0].payload as { target_kind: string; target_id: string; prev_state: Record<string, unknown>; next_state: Record<string, unknown> };
    expect(p.target_kind).toBe("notebook");
    expect(p.target_id).toBe("scratch");
    expect(typeof p.prev_state.etag).toBe("number");
    expect(p.next_state.etag).toBe((p.prev_state.etag as number) + 1);
    expect(p.next_state.block_kind).toBe("note");
  });

  it("chase_question WITH context emits target_kind=investigation_chase", async () => {
    dispatchAiAction(
      {
        kind: "chase_question",
        text: "What is the dispatch tier verdict criterion?",
        investigation_id: "inv-parent",
      },
      CONTEXT,
    );
    // vi.waitFor (not a fixed-round flush): the emit chain includes a real
    // Web Crypto sha256 digest whose resolution can slip past a fixed
    // macrotask+microtask budget on a slower/CI runner — the flake the
    // AGH SPR-04 vitest gate caught (green locally, 0-calls under CI). waitFor
    // retries until the mock is actually called, deterministic on any host.
    await vi.waitFor(() => expect(postTypedEventMock).toHaveBeenCalledTimes(1));
    const p = postTypedEventMock.mock.calls[0][0].payload as { target_kind: string; next_state: Record<string, unknown> };
    expect(p.target_kind).toBe("investigation_chase");
    expect(p.next_state.open).toBe(true);
    expect(p.next_state.question).toBe(
      "What is the dispatch tier verdict criterion?",
    );
    expect(p.next_state.investigation_id).toBe("inv-parent");
  });

  it("toast WITH context does NOT emit events (transient action)", async () => {
    dispatchAiAction(
      { kind: "toast", level: "info", message: "Done" },
      CONTEXT,
    );
    await flushMicrotasks();
    expect(postTypedEventMock).not.toHaveBeenCalled();
  });

  it("undo wrapper fires AIActionUndone when the underlying undo runs", async () => {
    // Pre-open a panel so set_panel_mode has a real prev mode.
    useWorkspace.getState().open(
      "FakeSidebar",
      {},
      { id: "ai:mode:real", mode: "floating", title: "Test" },
    );
    postTypedEventMock.mockResolvedValueOnce({
      event_id: "evt-applied-002",
      action_type: "ai.action.applied",
    });
    postTypedEventMock.mockResolvedValueOnce({
      event_id: "evt-undone-002",
      action_type: "ai.action.undone",
    });

    const record = dispatchAiAction(
      {
        kind: "set_panel_mode",
        id: "ai:mode:real",
        mode: "docked-right",
      },
      CONTEXT,
    );
    // vi.waitFor (not a fixed-round flush): the emit chain includes a real
    // Web Crypto sha256 digest whose resolution can slip past a fixed
    // macrotask+microtask budget on a slower/CI runner — the flake the
    // AGH SPR-04 vitest gate caught (green locally, 0-calls under CI). waitFor
    // retries until the mock is actually called, deterministic on any host.
    await vi.waitFor(() => expect(postTypedEventMock).toHaveBeenCalledTimes(1));

    expect(record.undo).toBeTypeOf("function");
    record.undo!();
    await vi.waitFor(() => expect(postTypedEventMock).toHaveBeenCalledTimes(2));
    const undonePayload = postTypedEventMock.mock.calls[1][0].payload as {
      action_type: string;
      inverted_event_id: string;
      target_kind: string;
      target_id: string;
      reason?: string;
    };
    expect(undonePayload.action_type).toBe("ai.action.undone");
    expect(undonePayload.inverted_event_id).toBe("evt-applied-002");
    expect(undonePayload.target_kind).toBe("ui_layout");
    expect(undonePayload.target_id).toBe("ai:mode:real");
    expect(undonePayload.reason).toBe("operator_undo");
  });

  it("network failure in event POST is silently swallowed (best-effort observability)", async () => {
    postTypedEventMock.mockRejectedValueOnce(new Error("network down"));
    expect(() =>
      dispatchAiAction(
        {
          kind: "open_panel",
          panel_kind: "FakeNotebook",
          id: "ai:net:fail",
        },
        CONTEXT,
      ),
    ).not.toThrow();
    // The action still mutated the workspace despite the network error.
    expect(useWorkspace.getState().panels["ai:net:fail"]).toBeTruthy();
  });
});
