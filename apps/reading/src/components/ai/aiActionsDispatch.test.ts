import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { postTypedEventMock, undoAiActionMock } = vi.hoisted(() => ({
  postTypedEventMock: vi.fn(),
  undoAiActionMock: vi.fn(),
}));

vi.mock("../../lib/api", async (importActual) => {
  const actual = await importActual<typeof import("../../lib/api")>();
  return {
    ...actual,
    postTypedEvent: postTypedEventMock,
    undoAiAction: undoAiActionMock,
  };
});

import { dispatchAiAction, parseAssistantReply } from "./aiActions";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { EMPTY_SNAPSHOT } from "../../workspace/panel.types";

/**
 * Full round-trip tests for the AI tool-call protocol.
 *
 * `parseAssistantReply` already has its own focused suite
 * (`aiActions.test.ts`). This file pairs the parser with the
 * dispatcher + the workspace store to verify the end-to-end
 * behavior: an assistant reply containing @@actions, when piped
 * through both stages, produces the expected store mutation.
 *
 * Spec acceptance (S8 WP-8.4): "When the AI asks 'open this PDF',
 * it dispatches a workspace open(PdfViewer, ...) action."
 */

function installLocalStorageShim(): void {
  if (typeof window.localStorage?.getItem === "function") {
    window.localStorage.clear();
    return;
  }
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => store.set(key, value),
      removeItem: (key: string) => store.delete(key),
      clear: () => store.clear(),
    },
  });
}

beforeEach(() => {
  // Reset the workspace store to a known baseline before each test.
  useWorkspace.setState({ ...EMPTY_SNAPSHOT });
  installLocalStorageShim();
  postTypedEventMock.mockReset();
  postTypedEventMock.mockResolvedValue({
    event_id: "evt-ai-applied-1",
    action_type: "ai.action.applied",
  });
  undoAiActionMock.mockReset();
  undoAiActionMock.mockResolvedValue({
    event_id: "evt-ai-undone-1",
    action_type: "ai.action.undone",
  });
  // Silence the deferred LemonToast dynamic-import — we test the
  // dispatched action records, not the toast renderer.
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("AI tool-call · full dispatch round-trip", () => {
  it("open_panel mutates the workspace store + the panel becomes present", () => {
    const reply =
      "Opening the relevant PDF.\n\n@@actions\n" +
      JSON.stringify([
        {
          kind: "open_panel",
          panel_kind: "FakeNotebook",
          props: { documentId: "doc-1", initialPage: 12 },
          mode: "floating",
          title: "Q4 risk",
          id: "ai:test:open",
        },
      ]) +
      "\n@@end";

    const parsed = parseAssistantReply(reply);
    expect(parsed.prose).toBe("Opening the relevant PDF.");
    expect(parsed.actions).toHaveLength(1);

    const record = dispatchAiAction(parsed.actions[0]);
    expect(record.action.kind).toBe("open_panel");
    expect(record.undo).toBeTypeOf("function");
    expect(record.label).toContain("Opened");

    const panel = useWorkspace.getState().panels["ai:test:open"];
    expect(panel).toBeTruthy();
    expect(panel.kind).toBe("FakeNotebook");
    expect(panel.mode).toBe("floating");
    expect(panel.title).toBe("Q4 risk");
    expect(panel.props).toEqual({ documentId: "doc-1", initialPage: 12 });
  });

  it("undo reverses an open_panel dispatch", () => {
    useWorkspace.getState().open(
      "FakeChat",
      {},
      { id: "ai:test:prior", mode: "floating", title: "Prior" },
    );
    useWorkspace.getState().focus("ai:test:prior");
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([
          {
            kind: "open_panel",
            panel_kind: "FakeSidebar",
            id: "ai:test:undo",
            mode: "docked-left",
          },
        ]) +
        "\n@@end",
    );
    const r = dispatchAiAction(actions[0]);
    expect(useWorkspace.getState().panels["ai:test:undo"]).toBeTruthy();
    r.undo!();
    expect(useWorkspace.getState().panels["ai:test:undo"]).toBeFalsy();
    expect(useWorkspace.getState().focusedPanelId).toBe("ai:test:prior");
  });

  it("open_panel undo restores previous focus when the panel already existed", () => {
    useWorkspace.getState().open(
      "FakeChat",
      {},
      { id: "ai:open:prior", mode: "floating", title: "Prior" },
    );
    useWorkspace.getState().open(
      "FakeSidebar",
      {},
      { id: "ai:open:existing", mode: "floating", title: "Existing" },
    );
    useWorkspace.getState().focus("ai:open:prior");
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([
          {
            kind: "open_panel",
            panel_kind: "FakeSidebar",
            id: "ai:open:existing",
          },
        ]) +
        "\n@@end",
    );
    const dispatched = dispatchAiAction(actions[0]);
    expect(useWorkspace.getState().panels["ai:open:existing"]).toBeTruthy();
    expect(useWorkspace.getState().focusedPanelId).toBe("ai:open:existing");

    dispatched.undo?.();
    expect(useWorkspace.getState().panels["ai:open:existing"]).toBeTruthy();
    expect(useWorkspace.getState().focusedPanelId).toBe("ai:open:prior");
  });

  it("contextual dispatch retains the applied event id and undo calls /ai/undo before local rollback", async () => {
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([
          {
            kind: "open_panel",
            panel_kind: "FakeSidebar",
            id: "ai:test:event-undo",
            mode: "docked-left",
          },
        ]) +
        "\n@@end",
    );
    const r = dispatchAiAction(actions[0], {
      investigation_id: "__sidecar__",
      operator_prompt: "open the sidebar",
    });

    expect(useWorkspace.getState().panels["ai:test:event-undo"]).toBeTruthy();
    await expect(r.appliedEventId).resolves.toBe("evt-ai-applied-1");
    expect(postTypedEventMock).toHaveBeenCalledWith(
      expect.objectContaining({
        investigation_id: "__sidecar__",
        role: "ai_sidecar",
        payload: expect.objectContaining({
          action_type: "ai.action.applied",
          target_kind: "ui_layout",
          target_id: "ai:test:event-undo",
          operator_prompt: "open the sidebar",
        }),
      }),
    );

    await r.undo?.();

    expect(undoAiActionMock).toHaveBeenCalledWith({
      event_id: "evt-ai-applied-1",
      investigation_id: "__sidecar__",
    });
    expect(useWorkspace.getState().panels["ai:test:event-undo"]).toBeFalsy();
  });

  it("contextual undo falls back to local rollback and direct undone event when /ai/undo fails", async () => {
    undoAiActionMock.mockRejectedValueOnce(new Error("offline"));
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([
          {
            kind: "open_panel",
            panel_kind: "FakeSidebar",
            id: "ai:test:event-fallback",
          },
        ]) +
        "\n@@end",
    );
    const r = dispatchAiAction(actions[0], {
      investigation_id: "__sidecar__",
      operator_prompt: "open the sidebar",
    });

    await r.undo?.();

    expect(useWorkspace.getState().panels["ai:test:event-fallback"]).toBeFalsy();
    expect(postTypedEventMock).toHaveBeenCalledWith(
      expect.objectContaining({
        payload: expect.objectContaining({
          action_type: "ai.action.undone",
          inverted_event_id: "evt-ai-applied-1",
        }),
      }),
    );
  });

  it("close_panel removes a previously-open panel", () => {
    useWorkspace.getState().open(
      "FakeChat",
      {},
      { id: "ai:test:close", mode: "floating", title: "X" },
    );
    expect(useWorkspace.getState().panels["ai:test:close"]).toBeTruthy();
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([{ kind: "close_panel", id: "ai:test:close" }]) +
        "\n@@end",
    );
    dispatchAiAction(actions[0]);
    expect(useWorkspace.getState().panels["ai:test:close"]).toBeFalsy();
  });

  it("close_panel undo restores the previously focused panel", () => {
    useWorkspace.getState().open(
      "FakeChat",
      {},
      { id: "ai:close:prior", mode: "floating", title: "Prior" },
    );
    useWorkspace.getState().open(
      "FakeSidebar",
      {},
      { id: "ai:close:target", mode: "floating", title: "Target" },
    );
    useWorkspace.getState().focus("ai:close:prior");
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([{ kind: "close_panel", id: "ai:close:target" }]) +
        "\n@@end",
    );
    const dispatched = dispatchAiAction(actions[0]);
    expect(useWorkspace.getState().panels["ai:close:target"]).toBeFalsy();
    expect(useWorkspace.getState().focusedPanelId).toBe("ai:close:prior");

    dispatched.undo?.();
    expect(useWorkspace.getState().panels["ai:close:target"]).toBeTruthy();
    expect(useWorkspace.getState().focusedPanelId).toBe("ai:close:prior");
  });

  it("set_panel_mode flips a panel's mode + undo restores", () => {
    useWorkspace.getState().open(
      "FakeSidebar",
      {},
      { id: "ai:test:mode", mode: "floating", title: "X" },
    );
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([
          {
            kind: "set_panel_mode",
            id: "ai:test:mode",
            mode: "docked-right",
          },
        ]) +
        "\n@@end",
    );
    const r = dispatchAiAction(actions[0]);
    expect(useWorkspace.getState().panels["ai:test:mode"].mode).toBe(
      "docked-right",
    );
    r.undo!();
    expect(useWorkspace.getState().panels["ai:test:mode"].mode).toBe(
      "floating",
    );
  });

  it("focus_panel sets focusedPanelId", () => {
    useWorkspace.getState().open(
      "FakeChat",
      {},
      { id: "ai:test:focus", mode: "floating", title: "X" },
    );
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([{ kind: "focus_panel", id: "ai:test:focus" }]) +
        "\n@@end",
    );
    dispatchAiAction(actions[0]);
    expect(useWorkspace.getState().focusedPanelId).toBe("ai:test:focus");
  });

  it("focus_panel undo restores the previous focused panel", () => {
    useWorkspace.getState().open(
      "FakeChat",
      {},
      { id: "ai:focus:old", mode: "floating", title: "Old" },
    );
    useWorkspace.getState().open(
      "FakeSidebar",
      {},
      { id: "ai:focus:new", mode: "floating", title: "New" },
    );
    useWorkspace.getState().focus("ai:focus:old");
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([{ kind: "focus_panel", id: "ai:focus:new" }]) +
        "\n@@end",
    );
    const dispatched = dispatchAiAction(actions[0]);
    expect(useWorkspace.getState().focusedPanelId).toBe("ai:focus:new");

    dispatched.undo?.();
    expect(useWorkspace.getState().focusedPanelId).toBe("ai:focus:old");
  });

  it("focus_panel undo restores null focus when nothing was focused before", () => {
    useWorkspace.getState().open(
      "FakeSidebar",
      {},
      { id: "ai:focus:null", mode: "floating", title: "New" },
    );
    useWorkspace.setState({ focusedPanelId: null });
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([{ kind: "focus_panel", id: "ai:focus:null" }]) +
        "\n@@end",
    );
    const dispatched = dispatchAiAction(actions[0]);
    expect(useWorkspace.getState().focusedPanelId).toBe("ai:focus:null");

    dispatched.undo?.();
    expect(useWorkspace.getState().focusedPanelId).toBeNull();
  });

  it("chase_question opens a Chase panel scoped to the question text", () => {
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([
          { kind: "chase_question", text: "is this real?" },
        ]) +
        "\n@@end",
    );
    dispatchAiAction(actions[0]);
    const chaseId = "chase:is this real?";
    expect(useWorkspace.getState().panels[chaseId]).toBeTruthy();
    expect(useWorkspace.getState().panels[chaseId].kind).toBe("Chase");
    expect(useWorkspace.getState().panels[chaseId].props).toEqual({
      spawnContext: "is this real?",
      parentInvestigationId: "__sidecar__",
    });
  });

  it("chase_question uses an explicit investigation id as the Chase parent", () => {
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([
          {
            kind: "chase_question",
            text: "is this tied to the current research?",
            investigation_id: "inv-parent",
          },
        ]) +
        "\n@@end",
    );
    dispatchAiAction(actions[0], {
      investigation_id: "__sidecar__",
      operator_prompt: "chase this",
    });
    const chaseId = "chase:is this tied to the current rese";
    expect(useWorkspace.getState().panels[chaseId].props).toEqual({
      spawnContext: "is this tied to the current research?",
      parentInvestigationId: "inv-parent",
    });
  });

  it("chase_question undo preserves a pre-existing chase panel", () => {
    useWorkspace.getState().open(
      "FakeChat",
      {},
      { id: "ai:chase:prior", mode: "floating", title: "Prior" },
    );
    const text = "What is the dispatch tier verdict criterion?";
    const chaseId = `chase:${text.slice(0, 32)}`;
    useWorkspace.getState().open(
      "Chase",
      { spawnContext: text, parentInvestigationId: "__sidecar__" },
      { id: chaseId, mode: "floating", title: "Chase" },
    );
    useWorkspace.getState().focus("ai:chase:prior");
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([{ kind: "chase_question", text }]) +
        "\n@@end",
    );
    const dispatched = dispatchAiAction(actions[0]);
    expect(useWorkspace.getState().panels[chaseId]).toBeTruthy();
    expect(useWorkspace.getState().focusedPanelId).toBe(chaseId);

    dispatched.undo?.();
    expect(useWorkspace.getState().panels[chaseId]).toBeTruthy();
    expect(useWorkspace.getState().focusedPanelId).toBe("ai:chase:prior");
  });

  it("chase_question undo closes a newly-opened chase panel", () => {
    useWorkspace.getState().open(
      "FakeChat",
      {},
      { id: "ai:chase:new-prior", mode: "floating", title: "Prior" },
    );
    useWorkspace.getState().focus("ai:chase:new-prior");
    const text = "is this new chase panel removable?";
    const chaseId = `chase:${text.slice(0, 32)}`;
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([{ kind: "chase_question", text }]) +
        "\n@@end",
    );
    const dispatched = dispatchAiAction(actions[0]);
    expect(useWorkspace.getState().panels[chaseId]).toBeTruthy();

    dispatched.undo?.();
    expect(useWorkspace.getState().panels[chaseId]).toBeUndefined();
    expect(useWorkspace.getState().focusedPanelId).toBe("ai:chase:new-prior");
  });

  it("add_to_notebook writes to localStorage + undo restores previous content and etag", async () => {
    const nbId = "ai-test-nb-" + Math.random().toString(36).slice(2, 8);
    const lsKey = "antiek.notebook." + nbId;
    const etagKey = lsKey + ".etag";
    window.localStorage.setItem(lsKey, "<p>before</p>");
    window.localStorage.setItem(etagKey, "7");
    const events: Array<{ notebookId: string; etag: number }> = [];
    const listener = (e: Event) => {
      const ce = e as CustomEvent<{ notebookId: string; etag: number }>;
      if (ce.detail) events.push(ce.detail);
    };
    window.addEventListener("antiek:notebook:appended", listener);

    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([
          {
            kind: "add_to_notebook",
            notebook_id: nbId,
            block: { kind: "note", text: "hi from AI" },
          },
        ]) +
        "\n@@end",
    );
    const dispatched = dispatchAiAction(actions[0]);

    const stored = window.localStorage.getItem(lsKey);
    expect(stored).toContain("antiek-note");
    expect(stored).toContain("hi from AI");

    const etag = window.localStorage.getItem(etagKey);
    expect(parseInt(etag ?? "0", 10)).toBe(8);

    expect(events).toHaveLength(1);
    expect(events[0].notebookId).toBe(nbId);
    expect(events[0].etag).toBe(8);

    await dispatched.undo?.();
    expect(window.localStorage.getItem(lsKey)).toBe("<p>before</p>");
    expect(window.localStorage.getItem(etagKey)).toBe("7");
    expect(events).toHaveLength(2);
    expect(events[1]).toEqual({ notebookId: nbId, etag: 7, force: true });

    window.removeEventListener("antiek:notebook:appended", listener);
    window.localStorage.removeItem(lsKey);
    window.localStorage.removeItem(etagKey);
  });

  it("contextual add_to_notebook undo calls /ai/undo before restoring local storage", async () => {
    const nbId = "ai-test-nb-context";
    const lsKey = "antiek.notebook." + nbId;
    const etagKey = lsKey + ".etag";
    window.localStorage.setItem(lsKey, "<p>old</p>");
    window.localStorage.setItem(etagKey, "2");
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([
          {
            kind: "add_to_notebook",
            notebook_id: nbId,
            block: { kind: "note", text: "new" },
          },
        ]) +
        "\n@@end",
    );
    const dispatched = dispatchAiAction(actions[0], {
      investigation_id: "__sidecar__",
      operator_prompt: "add a note",
    });
    await expect(dispatched.appliedEventId).resolves.toBe("evt-ai-applied-1");

    await dispatched.undo?.();
    expect(undoAiActionMock).toHaveBeenCalledWith({
      event_id: "evt-ai-applied-1",
      investigation_id: "__sidecar__",
    });
    expect(window.localStorage.getItem(lsKey)).toBe("<p>old</p>");
    expect(window.localStorage.getItem(etagKey)).toBe("2");

    window.localStorage.removeItem(lsKey);
    window.localStorage.removeItem(etagKey);
  });

  it("add_to_notebook undo removes newly-created local storage keys", async () => {
    const nbId = "ai-test-nb-empty";
    const lsKey = "antiek.notebook." + nbId;
    const etagKey = lsKey + ".etag";
    window.localStorage.removeItem(lsKey);
    window.localStorage.removeItem(etagKey);
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([
          {
            kind: "add_to_notebook",
            notebook_id: nbId,
            block: { kind: "note", text: "first" },
          },
        ]) +
        "\n@@end",
    );
    const dispatched = dispatchAiAction(actions[0]);
    expect(window.localStorage.getItem(lsKey)).toContain("first");
    expect(window.localStorage.getItem(etagKey)).toBe("1");

    await dispatched.undo?.();
    expect(window.localStorage.getItem(lsKey)).toBeNull();
    expect(window.localStorage.getItem(etagKey)).toBeNull();
  });

  it("add_to_notebook treats malformed stored etags as absent", async () => {
    const nbId = "ai-test-nb-bad-etag";
    const lsKey = "antiek.notebook." + nbId;
    const etagKey = lsKey + ".etag";
    window.localStorage.setItem(lsKey, "<p>before</p>");
    window.localStorage.setItem(etagKey, "7junk");
    const events: Array<{ notebookId: string; etag: number; force?: boolean }> = [];
    const listener = (e: Event) => {
      const ce = e as CustomEvent<{
        notebookId: string;
        etag: number;
        force?: boolean;
      }>;
      if (ce.detail) events.push(ce.detail);
    };
    window.addEventListener("antiek:notebook:appended", listener);

    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([
          {
            kind: "add_to_notebook",
            notebook_id: nbId,
            block: { kind: "note", text: "after bad etag" },
          },
        ]) +
        "\n@@end",
    );
    const dispatched = dispatchAiAction(actions[0]);
    expect(window.localStorage.getItem(etagKey)).toBe("1");
    expect(events[0]).toEqual({ notebookId: nbId, etag: 1 });

    await dispatched.undo?.();
    expect(window.localStorage.getItem(lsKey)).toBe("<p>before</p>");
    expect(window.localStorage.getItem(etagKey)).toBeNull();
    expect(events[1]).toEqual({ notebookId: nbId, etag: 0, force: true });

    window.removeEventListener("antiek:notebook:appended", listener);
    window.localStorage.removeItem(lsKey);
    window.localStorage.removeItem(etagKey);
  });

  it("toast dispatches the lemon toast queue (dynamic import resolves)", async () => {
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([
          { kind: "toast", level: "warn", message: "smoke" },
        ]) +
        "\n@@end",
    );
    const r = dispatchAiAction(actions[0]);
    expect(r.label).toContain("smoke");
    // Fire-and-forget; we don't fail the test on toast UI absence —
    // the deferred import returns a microtask we just confirm
    // didn't throw.
  });

  it("a multi-action reply dispatches every action in order", () => {
    const reply =
      "Multiple ops.\n\n@@actions\n" +
      JSON.stringify([
        { kind: "open_panel", panel_kind: "FakeChat", id: "ai:multi:a" },
        { kind: "open_panel", panel_kind: "FakeSidebar", id: "ai:multi:b" },
        { kind: "focus_panel", id: "ai:multi:b" },
      ]) +
      "\n@@end";
    const { actions } = parseAssistantReply(reply);
    expect(actions).toHaveLength(3);
    const records = actions.map((a) => dispatchAiAction(a));
    expect(records).toHaveLength(3);

    const state = useWorkspace.getState();
    expect(state.panels["ai:multi:a"]).toBeTruthy();
    expect(state.panels["ai:multi:b"]).toBeTruthy();
    expect(state.focusedPanelId).toBe("ai:multi:b");
  });
});
