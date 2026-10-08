/** Synthetic UNIT owners/anchors and an observable opener exercise the real
 * mounted pane, reply buttons and lease. No account/provider/live proof. */
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { awaitWorkspaceOwnerSession, beforeWorkspaceOwnerChange, resumeWorkspaceOwner, setWorkspaceOwner, suspendWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import type { DocumentAnchor } from "../contracts/anchor";
import type { OpenDocumentFromAgentResult } from "../contracts/openers";
import { useCompanion } from "../companionStore";
import { AgentPane } from "./AgentPane";
import { AGENT_REPLY_AGENT_KIND, AgentReplyActions, type AgentReplyActionsProps } from "./AgentReplyActions";
import { captureAgentPaneLease, isCurrentAgentPaneLease, useAgentPaneStore } from "./agentPaneStore";
import { useAgentThreads } from "./agentThreadStore";
import type { AgentTransport } from "./agentTransport";
import type { AgentPaneTab } from "./agentTypes";
import { isConfirmedAgentOwner } from "./turnLifecycle";

const { opener } = vi.hoisted(() => ({ opener: vi.fn<() => OpenDocumentFromAgentResult>() }));
vi.mock("../contracts/openers", async (load) => ({
  ...await load<typeof import("../contracts/openers")>(),
  openDocumentFromAgent: opener,
}));

const tab: AgentPaneTab = { id: "agent:pane:x:passage", agentId: "x:passage", title: "UNIT passage agent", scope: "cross-project" };
const anchor: DocumentAnchor = {
  space: "book", documentId: "unit-book", kind: "text",
  version: { kind: "unversioned", reason: "metadata_only_anchor" },
  range: { kind: "text", nodeId: "unit-node", start: 0, end: 4, unit: "utf16", basis: "chunk" },
  quoteHint: { quote: "UNIT passage", prefix: "", suffix: "" },
};
const writerAnchor: DocumentAnchor = {
  space: "deliverable", deliverableId: "unit-deliverable", kind: "block",
  version: { kind: "unversioned", reason: "writer_prose_block_unpersisted" },
  range: { kind: "block", sectionId: "unit-section", outlineBlockId: null, paragraphIndex: null },
  quoteHint: null,
};
const send = vi.fn<AgentTransport["send"]>();
const transport: AgentTransport = { kind: "whole", send };

function open() {
  useCompanion.getState().openAgentTab({ kind: "dialogue", agentId: tab.agentId, title: tab.title, scope: tab.scope });
}
function complete(passage = anchor) {
  const owner = workspaceOwnerSession();
  const id = useAgentThreads.getState().startTurn(tab.id, "UNIT question", {}, owner);
  expect(id).not.toBeNull();
  useAgentThreads.getState().completeTurn(tab.id, id, { answer: "UNIT retained answer", shape: "SYNTHESIS", actions: [{ kind: "open_document", anchor: passage }] }, owner);
}
function host(passage = anchor) {
  complete(passage);
  return render(<MemoryRouter><AgentPane tab={tab} transport={transport} /></MemoryRouter>);
}
function button() {
  const node = document.querySelector<HTMLButtonElement>("[data-reply-action='open_document']");
  expect(node).not.toBeNull();
  return node!;
}
function refusal() { return document.querySelector("[data-reply-action-refusal]")?.textContent ?? null; }
async function owner(subject: string | null) {
  await act(async () => { setWorkspaceOwner(subject); await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
}
function child(passage = anchor, mutate?: (props: AgentReplyActionsProps) => void) {
  const capturedOwner = workspaceOwnerSession();
  const lease = captureAgentPaneLease(tab.id);
  expect(lease).not.toBeNull();
  const props: AgentReplyActionsProps = {
    tab, interview: false, actions: [{ kind: "open_document", anchor: passage }],
    isCurrent: () => isConfirmedAgentOwner(capturedOwner) && lease !== null && isCurrentAgentPaneLease(lease),
  };
  mutate?.(props);
  return render(<AgentReplyActions {...props} />);
}

beforeEach(async () => {
  Object.defineProperty(window, "matchMedia", { configurable: true, value: (media: string) => ({ media, matches: true, addEventListener() {}, removeEventListener() {} }) });
  setWorkspaceOwner(null); setWorkspaceOwner("unit-passage-A");
  await awaitWorkspaceOwnerSession(workspaceOwnerSession());
  useCompanion.getState().reset(); useAgentThreads.getState().reset(); useAgentPaneStore.getState().reset();
  window.sessionStorage.clear(); open();
  opener.mockReset(); opener.mockReturnValue({ ok: true }); send.mockReset();
});
afterEach(() => { cleanup(); setWorkspaceOwner(null); vi.restoreAllMocks(); });

describe("mounted passage originating admission", () => {
  it.each([1, 0])("current mounted button activation detail=%s calls once with exact frozen arguments", (detail) => {
    host(); const b = button();
    expect(b.tagName).toBe("BUTTON"); expect(b.type).toBe("button"); expect(b.disabled).toBe(false);
    expect(opener).not.toHaveBeenCalled(); b.focus(); fireEvent.click(b, { detail });
    expect(opener).toHaveBeenCalledTimes(1);
    expect(opener).toHaveBeenCalledWith({ documentId: "unit-book", anchor, agent: { id: tab.id, viewId: tab.id, kind: AGENT_REPLY_AGENT_KIND } });
    expect(send).not.toHaveBeenCalled();
  });
  it("same-owner suspension refuses without losing content or replay; explicit confirmed action works", async () => {
    host(); const b = button(); act(() => suspendWorkspaceOwner()); fireEvent.click(b);
    expect(opener).not.toHaveBeenCalled(); expect(document.body.textContent).toContain("UNIT retained answer");
    act(() => { resumeWorkspaceOwner(); }); await act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
    expect(opener).not.toHaveBeenCalled(); expect(button()).toBe(b);
    fireEvent.click(b); expect(opener).toHaveBeenCalledTimes(1);
  });
  it.each(["B", "B-A"])("old mounted callback refuses %s before React cleanup", (replacement) => {
    host(); const b = button();
    act(() => { setWorkspaceOwner("unit-passage-B"); if (replacement === "B-A") setWorkspaceOwner("unit-passage-A"); fireEvent.click(b); });
    expect(opener).not.toHaveBeenCalled();
  });
  it("new same-ID incarnation refuses the old mounted callback before React cleanup", () => {
    host(); const b = button(); const lease = captureAgentPaneLease(tab.id);
    act(() => { useCompanion.getState().closeAgentTab(tab.id); open(); fireEvent.click(b); });
    expect(captureAgentPaneLease(tab.id)).not.toBe(lease); expect(opener).not.toHaveBeenCalled();
  });
  it("descriptor/focus clones keep the actual lease and permit the current action", () => {
    host(); const lease = captureAgentPaneLease(tab.id);
    act(() => useCompanion.setState((s) => ({ tabs: s.tabs.map((t) => ({ ...t, title: "UNIT clone" })), activeTabId: tab.id })));
    expect(captureAgentPaneLease(tab.id)).toBe(lease); fireEvent.click(button()); expect(opener).toHaveBeenCalledTimes(1);
  });
  it("retiring owner refuses the old button inside the actual retirement boundary", async () => {
    host(); const b = button(); const off = beforeWorkspaceOwnerChange(() => fireEvent.click(b));
    try { await owner("unit-passage-B"); } finally { off(); }
    expect(opener).not.toHaveBeenCalled();
  });
  it("failed retirement refuses the old mounted callback and retires the content", () => {
    host(); const b = button(); const off = beforeWorkspaceOwnerChange(() => { throw new Error("UNIT retirement failure"); });
    try { act(() => { expect(() => setWorkspaceOwner("unit-passage-B")).toThrow("UNIT retirement failure"); fireEvent.click(b); }); } finally { off(); }
    expect(opener).not.toHaveBeenCalled(); expect(document.body.textContent).not.toContain("UNIT retained answer");
  });
  it("null owner refuses an old callback before cleanup", () => {
    host(); const b = button(); act(() => { setWorkspaceOwner(null); fireEvent.click(b); }); expect(opener).not.toHaveBeenCalled();
  });
  it("unmounted button cannot open", () => {
    const h = host(); const b = button(); h.unmount(); fireEvent.click(b); expect(opener).not.toHaveBeenCalled();
  });
  it("suspended deliverable action cannot publish even the local refusal", () => {
    host(writerAnchor); act(() => suspendWorkspaceOwner()); fireEvent.click(button());
    expect(opener).not.toHaveBeenCalled(); expect(refusal()).toBeNull();
  });
  it("current ordinary opener refusal remains visible", () => {
    opener.mockReturnValue({ ok: false, reason: "document_mismatch" }); host(); fireEvent.click(button());
    expect(opener).toHaveBeenCalledTimes(1); expect(refusal()).toBe("That passage is in another document");
  });
  it("suspension synchronously published inside the opener refuses its returned error", () => {
    opener.mockImplementation(() => { suspendWorkspaceOwner(); return { ok: false, reason: "document_mismatch" }; });
    host(); fireEvent.click(button()); expect(opener).toHaveBeenCalledTimes(1); expect(refusal()).toBeNull();
    expect(document.body.textContent).toContain("UNIT retained answer");
  });
  it.each(["owner", "incarnation"])("synchronous %s retirement inside the opener never publishes into its replacement", (kind) => {
    host();
    opener.mockImplementation(() => {
      if (kind === "owner") setWorkspaceOwner("unit-passage-B");
      else { useCompanion.getState().closeAgentTab(tab.id); open(); }
      return { ok: false, reason: "document_mismatch" };
    });
    fireEvent.click(button()); expect(opener).toHaveBeenCalledTimes(1); expect(refusal()).toBeNull();
  });
});

describe("reply button required predicate boundary", () => {
  it.each(["missing", "false", "undefined", "truthy", "throw"] as const)("runtime %s admission refuses the opener and local refusal", (kind) => {
    const mutate = (props: AgentReplyActionsProps) => {
      if (kind === "missing") Reflect.deleteProperty(props, "isCurrent");
      else Object.defineProperty(props, "isCurrent", { value: kind === "throw" ? () => { throw new Error("UNIT admission failure"); } : () => ({ false: false, undefined: undefined, truthy: 1 })[kind] });
    };
    child(anchor, mutate); fireEvent.click(button()); expect(opener).not.toHaveBeenCalled(); expect(refusal()).toBeNull();
    cleanup(); child(writerAnchor, mutate); fireEvent.click(button()); expect(opener).not.toHaveBeenCalled(); expect(refusal()).toBeNull();
  });
  it.each(["missing", "false", "undefined", "truthy", "throw"] as const)("runtime %s admission after opener return refuses old state", (kind) => {
    let post = false;
    child(anchor, (props) => Object.defineProperty(props, "isCurrent", { value: () => {
      if (!post) return true;
      if (kind === "throw") throw new Error("UNIT late admission failure");
      return ({ missing: undefined, false: false, undefined: undefined, truthy: 1 })[kind];
    } }));
    opener.mockImplementation(() => { post = true; return { ok: false, reason: "document_mismatch" }; });
    fireEvent.click(button()); expect(opener).toHaveBeenCalledTimes(1); expect(refusal()).toBeNull();
  });
  it("an inadmissible returned success cannot clear a prior current refusal", () => {
    let admitted = true;
    child(anchor, (props) => { props.isCurrent = () => admitted; });
    opener.mockReturnValue({ ok: false, reason: "document_mismatch" }); fireEvent.click(button());
    expect(refusal()).toBe("That passage is in another document");
    opener.mockImplementation(() => { admitted = false; return { ok: true }; }); fireEvent.click(button());
    expect(opener).toHaveBeenCalledTimes(2); expect(refusal()).toBe("That passage is in another document");
  });
  it("a current returned success clears a prior ordinary refusal", () => {
    child(); opener.mockReturnValue({ ok: false, reason: "document_mismatch" }); fireEvent.click(button());
    expect(refusal()).toBe("That passage is in another document");
    opener.mockReturnValue({ ok: true }); fireEvent.click(button()); expect(opener).toHaveBeenCalledTimes(2); expect(refusal()).toBeNull();
  });
});
