import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/** Hoisted so the mock survives vitest's cross-file lib/api partial mocks. */
const { postTypedEventMock } = vi.hoisted(() => ({
  postTypedEventMock: vi.fn(),
}));

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return { ...actual, postTypedEvent: postTypedEventMock };
});

import { dispatchAiAction, type AiActionContext } from "./aiActions";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { EMPTY_SNAPSHOT } from "../../workspace/panel.types";

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

beforeEach(async () => {
  useWorkspace.setState({ ...EMPTY_SNAPSHOT });
  postTypedEventMock.mockReset();
  postTypedEventMock.mockResolvedValue({
    event_id: "evt-fixture",
    action_type: "ai.action.applied",
  });
  // Drain straggler async from the prior test file's lib/api mocks.
  await drainAsyncBridge();
});

afterEach(async () => {
  await drainAsyncBridge();
  postTypedEventMock.mockReset();
});

/** Drain the bridge chain: descriptor → sha256Hex (Web Crypto) → postTypedEvent. */
async function drainAsyncBridge(): Promise<void> {
  await new Promise((r) => setTimeout(r, 0));
  for (let i = 0; i < 8; i++) await Promise.resolve();
}

async function expectEventCalls(times: number): Promise<void> {
  await vi.waitFor(
    () => expect(postTypedEventMock).toHaveBeenCalledTimes(times),
    { timeout: 3000, interval: 20 },
  );
}

async function expectNoEvents(): Promise<void> {
  await drainAsyncBridge();
  await new Promise((r) => setTimeout(r, 30));
  expect(postTypedEventMock).not.toHaveBeenCalled();
}

describe("AISidecar event-log bridge", () => {
  it("dispatchAiAction WITHOUT context does NOT emit events", async () => {
    dispatchAiAction({
      kind: "open_panel",
      panel_kind: "FakeNotebook",
      id: "no-ctx-test",
    });
    await expectNoEvents();
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
    await expectEventCalls(1);
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
    await expectEventCalls(1);
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
    await expectEventCalls(1);
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
    await expectNoEvents();
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
    await expectEventCalls(1);

    expect(record.undo).toBeTypeOf("function");
    record.undo!();
    await expectEventCalls(2);
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
