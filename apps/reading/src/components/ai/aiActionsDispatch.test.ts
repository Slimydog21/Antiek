import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { dispatchAiAction, parseAssistantReply } from "./aiActions";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { EMPTY_SNAPSHOT } from "../../workspace/panel.types";
import { toast } from "../lemon/LemonToast";

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

beforeEach(() => {
  // Reset the workspace store to a known baseline before each test.
  useWorkspace.setState({ ...EMPTY_SNAPSHOT });
  // Keep LemonToast's auto-dismiss timer deterministic in this suite.
  vi.useFakeTimers();
});

afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
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
  });

  it("add_to_notebook writes to localStorage + bumps etag + dispatches the same-window event", () => {
    const nbId = "ai-test-nb-" + Math.random().toString(36).slice(2, 8);
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
    dispatchAiAction(actions[0]);

    const stored = window.localStorage.getItem("antiek.notebook." + nbId);
    expect(stored).toContain("antiek-note");
    expect(stored).toContain("hi from AI");

    const etag = window.localStorage.getItem(
      "antiek.notebook." + nbId + ".etag",
    );
    expect(parseInt(etag ?? "0", 10)).toBeGreaterThan(0);

    expect(events).toHaveLength(1);
    expect(events[0].notebookId).toBe(nbId);

    window.removeEventListener("antiek:notebook:appended", listener);
    window.localStorage.removeItem("antiek.notebook." + nbId);
    window.localStorage.removeItem("antiek.notebook." + nbId + ".etag");
  });

  it("toast dispatches the lemon toast queue before returning", () => {
    const warn = vi.spyOn(toast, "warn");
    const { actions } = parseAssistantReply(
      "x\n\n@@actions\n" +
        JSON.stringify([
          { kind: "toast", level: "warn", message: "smoke" },
        ]) +
        "\n@@end",
    );
    const r = dispatchAiAction(actions[0]);
    expect(r.label).toContain("smoke");
    expect(warn).toHaveBeenCalledOnce();
    expect(warn).toHaveBeenCalledWith("smoke");
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
