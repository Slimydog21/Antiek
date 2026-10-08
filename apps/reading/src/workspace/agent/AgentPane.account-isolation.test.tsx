/** Local synthetic transports exercise the real pane/stores and authentic local
 * workspace-owner producer. They are not account/server/provider proof. */
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { awaitWorkspaceOwnerSession, beforeWorkspaceOwnerChange, resumeWorkspaceOwner, setWorkspaceOwner, suspendWorkspaceOwner, workspaceOwnerSession, subscribeWorkspaceOwnerAdmission } from "../../lib/accountWorkspaceOwner";
import { useCompanion } from "../companionStore";
import { createTurnRunner } from "./turnLifecycle";
import { AgentPane } from "./AgentPane";
import { useAgentThreads } from "./agentThreadStore";
import { useAgentPaneStore } from "./agentPaneStore";
import type { AgentTransport, AgentTransportReply, AgentTransportRequest } from "./agentTransport";
import type { AgentPaneTab } from "./agentTypes";

const tab: AgentPaneTab = { id: "agent:pane:x:1", title: "local agent", agentId: "x:1", scope: "cross-project" };
function open(t = tab) {
  useCompanion.getState().openAgentTab({ kind: "dialogue", agentId: t.agentId, title: t.title, scope: t.scope, ...(t.projectId ? { projectId: t.projectId } : {}) });
}
function deferredTransport() {
  const requests: AgentTransportRequest[] = [];
  const pending: { resolve: (r: AgentTransportReply) => void; reject: (e: Error) => void }[] = [];
  const transport: AgentTransport = { kind: "whole", send: vi.fn((r) => {
    requests.push(r);
    return new Promise<AgentTransportReply>((resolve, reject) => pending.push({ resolve, reject }));
  }) };
  return { transport, requests, pending };
}
function host(transport: AgentTransport, t = tab) {
  return render(<MemoryRouter><div data-pane="left" tabIndex={-1} /><AgentPane tab={t} transport={transport} /></MemoryRouter>);
}
function send(text: string) {
  const input = document.querySelector<HTMLTextAreaElement>("[data-agent-pane] textarea")!;
  fireEvent.change(input, { target: { value: text } });
  fireEvent.keyDown(input, { key: "Enter" });
}
async function settle(ms = 0) { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); }
async function owner(subject: string | null) { await act(async () => { setWorkspaceOwner(subject); await awaitWorkspaceOwnerSession(workspaceOwnerSession()); }); }
beforeEach(async () => {
  vi.useFakeTimers();
  Object.defineProperty(window, "matchMedia", { configurable: true, value: (query: string) => ({ matches: true, media: query, addEventListener() {}, removeEventListener() {} }) });
  setWorkspaceOwner(null); setWorkspaceOwner("unit-A");
  await awaitWorkspaceOwnerSession(workspaceOwnerSession());
  useCompanion.getState().reset(); useAgentThreads.getState().reset(); useAgentPaneStore.getState().reset();
  window.sessionStorage.clear(); open();
});
afterEach(() => { cleanup(); setWorkspaceOwner(null); vi.useRealTimers(); vi.restoreAllMocks(); });

describe("authentic account and actual resource isolation", () => {
  it.each([tab, { ...tab, id: "agent:pane:p:same", agentId: "p:same", scope: "project" as const, projectId: "same" }])("A completed history never renders or ships under B reusing $id", async (t) => {
    open(t); const d = deferredTransport(); const a = host(d.transport, t);
    send("A private question"); await settle();
    d.pending[0].resolve({ text: "A private answer", shape: "SYNTHESIS" }); await settle();
    expect(document.body.textContent).toContain("A private answer"); a.unmount();
    await owner("unit-B"); useCompanion.getState().reset(); open(t); host(d.transport, t);
    expect(document.body.textContent).not.toContain("A private answer");
    send("B question"); await settle(); expect(d.requests[1].history).toEqual([]);
  });
  it("A-B-A retires the original token even before old mounted cleanup", async () => {
    const d = deferredTransport(); host(d.transport); send("old"); await settle();
    await owner("unit-B"); await owner("unit-A");
    d.pending[0].resolve({ text: "retired answer", shape: "SYNTHESIS" }); await settle();
    expect(document.body.textContent).not.toContain("retired answer");
    expect(Object.values(useAgentThreads.getState().threads).flat()).toHaveLength(0);
  });
  it("null never dispatches", async () => {
    await owner(null); const d = deferredTransport(); host(d.transport);
    const input = document.querySelector<HTMLTextAreaElement>("textarea");
    if (input) { fireEvent.change(input, { target: { value: "refused" } }); fireEvent.keyDown(input, { key: "Enter" }); }
    await settle(); expect(d.requests).toHaveLength(0);
  });
  it("failed retirement cannot dispatch or retain a private thread", async () => {
    const d = deferredTransport(); host(d.transport); send("old"); await settle();
    const off = beforeWorkspaceOwnerChange(() => { throw new Error("local retirement control"); });
    act(() => { expect(() => setWorkspaceOwner("unit-B")).toThrow("local retirement control"); }); off();
    d.pending[0].resolve({ text: "failed admission answer", shape: "SYNTHESIS" }); await settle();
    expect(document.body.textContent).not.toContain("failed admission answer");
    expect(Object.values(useAgentThreads.getState().threads).flat()).toHaveLength(0);
  });
  it("same A suspension holds a new dispatch until confirmation and preserves the draft", async () => {
    const d = deferredTransport(); host(d.transport); act(() => suspendWorkspaceOwner());
    send("held question"); await settle(); expect(d.requests).toHaveLength(0);
    expect(document.querySelector<HTMLTextAreaElement>("textarea")!.value).toBe("held question");
    act(() => { resumeWorkspaceOwner(); }); await settle();
    expect(d.requests).toHaveLength(1); expect(d.requests[0].prompt).toBe("held question");
  });
  it.each(["success", "failure"])("same-A delayed %s is held through suspension then adopted once", async (kind) => {
    const d = deferredTransport(); host(d.transport); send("q"); await settle();
    act(() => suspendWorkspaceOwner());
    if (kind === "success") d.pending[0].resolve({ text: "confirmed answer", shape: "SYNTHESIS" });
    else d.pending[0].reject(new Error("local synthetic failure"));
    await settle(); expect(useAgentThreads.getState().threads[tab.id][0].status).toBe("pending");
    act(() => { resumeWorkspaceOwner(); }); await settle();
    expect(useAgentThreads.getState().threads[tab.id][0].status).toBe(kind === "success" ? "done" : "failed");
    expect(d.requests).toHaveLength(1);
  });
  it("eight-second failure remains exact; suspended Retry sends once after confirmation and drops the old reply", async () => {
    const d = deferredTransport(); host(d.transport); send("exact original"); await settle(8000);
    expect(document.body.textContent).toContain("Your agent couldn't answer");
    act(() => suspendWorkspaceOwner()); fireEvent.click(document.querySelector<HTMLButtonElement>("[data-lifecycle-notice] button")!);
    await settle(); expect(d.requests).toHaveLength(1);
    act(() => { resumeWorkspaceOwner(); }); await settle();
    expect(d.requests).toHaveLength(2); expect(d.requests[1].prompt).toBe("exact original"); expect(d.requests[0].signal.aborted).toBe(true);
    d.pending[0].resolve({ text: "old retry reply", shape: "SYNTHESIS" }); d.pending[1].resolve({ text: "new reply", shape: "SYNTHESIS" }); await settle();
    expect(document.body.textContent).toContain("new reply"); expect(document.body.textContent).not.toContain("old retry reply");
  });
  it("same paid request late-heals after confirmation without an extra dispatch", async () => {
    const d = deferredTransport(); host(d.transport); send("paid local seam"); await settle(8000);
    act(() => suspendWorkspaceOwner()); d.pending[0].resolve({ text: "late healing", shape: "SYNTHESIS" }); await settle();
    expect(document.body.textContent).not.toContain("late healing");
    act(() => { resumeWorkspaceOwner(); }); await settle();
    expect(document.body.textContent).toContain("late healing"); expect(d.requests).toHaveLength(1);
  });
  it("unmount refuses a late reply even when the synthetic transport ignores abort", async () => {
    const d = deferredTransport(); const h = host(d.transport); send("q"); await settle(); h.unmount();
    d.pending[0].resolve({ text: "after unmount", shape: "SYNTHESIS" }); await settle();
    expect(useAgentThreads.getState().threads[tab.id][0].answer).toBeNull();
  });
  it("retiring admission refuses a captured mounted callback before its React cleanup", async () => {
    const d = deferredTransport(); host(d.transport); send("current"); await settle();
    const oldInput = document.querySelector<HTMLTextAreaElement>("textarea")!;
    const off = beforeWorkspaceOwnerChange(() => {
      fireEvent.change(oldInput, { target: { value: "retiring dispatch" } });
      fireEvent.keyDown(oldInput, { key: "Enter" });
    });
    await owner("unit-B"); off(); await settle(); expect(d.requests).toHaveLength(1);
  });
  it("a later failed ready observer refuses suspended dispatch without a paid call", async () => {
    const d = deferredTransport(); host(d.transport); act(() => suspendWorkspaceOwner()); send("queued");
    const off = subscribeWorkspaceOwnerAdmission((a) => { if (a.state === "ready") throw new Error("local confirmation refusal"); });
    act(() => { expect(() => resumeWorkspaceOwner()).toThrow("local confirmation refusal"); }); off();
    await settle(); expect(d.requests).toHaveLength(0);
  });
  it("real simulated chunks hold partial/final state while A is suspended", async () => {
    Object.defineProperty(window, "matchMedia", { configurable: true, value: (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {} }) });
    const d = deferredTransport(); host(d.transport); send("stream"); await settle();
    const text = "A locally scripted whole answer rendered in many progressive chunks. ".repeat(10).trim();
    d.pending[0].resolve({ text, shape: "SYNTHESIS" }); await settle(32);
    const partial = useAgentThreads.getState().threads[tab.id][0].answer;
    expect(partial).not.toBeNull(); expect(partial).not.toBe(text);
    act(() => suspendWorkspaceOwner()); await settle(2000);
    expect(useAgentThreads.getState().threads[tab.id][0].answer).toBe(partial);
    act(() => { resumeWorkspaceOwner(); }); await settle();
    expect(useAgentThreads.getState().threads[tab.id][0].status).toBe("done");
    expect(useAgentThreads.getState().threads[tab.id][0]).toMatchObject({ status: "done", answer: text }); expect(d.requests).toHaveLength(1);
  });
  it("replacement by a newer actual same-ID descriptor refuses old reply before effect cleanup", async () => {
    const d = deferredTransport(); host(d.transport); send("old"); await settle();
    await act(async () => {
      useCompanion.getState().closeAgentTab(tab.id); open();
      d.pending[0].resolve({ text: "old incarnation answer", shape: "SYNTHESIS" });
      await Promise.resolve();
    });
    await settle(); expect(document.body.textContent).not.toContain("old incarnation answer");
  });
  it("a local current token cannot be replaced by subject-only equality in direct thread adoption", async () => {
    const a = workspaceOwnerSession(); const id = useAgentThreads.getState().startTurn(tab.id, "private", {}, a);
    await owner("unit-B"); await owner("unit-A");
    useAgentThreads.getState().completeTurn(tab.id, id, { answer: "retired", shape: "SYNTHESIS", actions: [] }, a);
    expect(useAgentThreads.getState().threads).toEqual({});
  });
  it("the original no-reply timer still starts at dispatch after held owner confirmation", async () => {
    const d = deferredTransport(); const states: string[] = [];
    const runner = createTurnRunner({ owner: workspaceOwnerSession(), transport: d.transport, request: () => ({ prompt: "held", history: [], system_context: "" }), onState: (s) => states.push(s.phase) });
    suspendWorkspaceOwner(); runner.send(); await vi.advanceTimersByTimeAsync(20000); expect(d.requests).toHaveLength(0); expect(states).toEqual([]);
    resumeWorkspaceOwner(); await vi.advanceTimersByTimeAsync(0); expect(d.requests).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(7999); expect(states).toEqual(["sent"]);
    await vi.advanceTimersByTimeAsync(1); expect(states).toEqual(["sent", "failed"]); runner.dispose();
  });

});
