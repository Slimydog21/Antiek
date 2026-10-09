/**
 * agentStatusStore.test.tsx — SPR-10 M2/M6: the raw-only sidecar store.
 * Membership and rollups derive from the context tree at read time; seen
 * state lives in workspace/seen.ts; done→idle happens only on focus; the
 * owner epoch resets everything; the store never writes the tree.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";

import { setWorkspaceOwner } from "../../lib/accountWorkspaceOwner";
import { composePreBackendTree } from "../contracts/adapters/preBackend";
import * as treeStore from "../contracts/treeStore";
import { fixtureInputs, summary, tab } from "../contracts/fixtures.test.helpers";
import { useCompanion } from "../companionStore";
import { useWorkspace } from "../WorkspaceStore";
import { lastSeenAt } from "../seen";
import { attentionOf } from "./agentStatus";
import { subscribeTransitions, useAgentAttention, useAgentStatusStore, useProjectAttention, useWorkspaceAttention } from "./agentStatusStore";
import { DEBOUNCE, inStartupGrace } from "./debounce";
import { installStatusToasts, peek, resetStatusToasts } from "./statusToasts";

const { publishTree } = treeStore;

let now = 100_000;
const clock = {
  now: () => now,
  setTimeout: (fn: () => void, ms: number) => window.setTimeout(fn, ms),
  clearTimeout: (h: unknown) => window.clearTimeout(h as number),
};

const MEMBER = [{ member_kind: "investigation" as const, member_id: "X", added_at: "2026-09-18T10:00:00Z" }];

function publishFixture(opts: { tabOnX?: boolean } = {}) {
  const tree = composePreBackendTree(fixtureInputs({
    investigations: [
      summary("X", { status: "in_progress", completed_at: null, question: "X question" }),
      summary("Q", { status: "stopped", question: "Q question" }),
    ],
    companionTabs: [
      ...(opts.tabOnX ? [tab("research-thread", { investigationId: "X", title: "X tab" })] : []),
      tab("dialogue"),
    ],
    membersByProject: new Map([["p1", MEMBER]]),
  }));
  act(() => publishTree(tree, new Date(now).toISOString()));
  return tree;
}

/** One poll observation, then the debounce window (3 × 100 ms) run through
 *  the fake clock so a working→finished step actually commits. */
function observe(status: "in_progress" | "completed" | "failed" | "stopped", id = "X") {
  act(() => {
    useAgentStatusStore.getState().observe(
      [summary(id, { status, completed_at: status === "in_progress" ? null : new Date(now).toISOString(), started_at: "2026-10-07T00:00:00Z", question: `${id} question` })],
      new Set([id]),
      now,
    );
  });
  act(() => {
    now += DEBOUNCE.confirmations * DEBOUNCE.intervalMs;
    vi.advanceTimersByTime(DEBOUNCE.confirmations * DEBOUNCE.intervalMs);
  });
}

let uninstallToasts: (() => void) | null = null;

beforeEach(() => {
  vi.useFakeTimers();
  now = 100_000;
  window.localStorage.removeItem("antiek:last_seen:v1");
  useCompanion.getState().reset();
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("omarchy-inset");
  resetStatusToasts();
  useAgentStatusStore.getState().reset();
  useAgentStatusStore.getState().start(clock);
  uninstallToasts = installStatusToasts();
});

afterEach(() => {
  cleanup();
  uninstallToasts?.();
  uninstallToasts = null;
  useAgentStatusStore.getState().stop();
  treeStore.markTreeUnfed();
  useCompanion.getState().reset();
  vi.useRealTimers();
});

describe("M6 integration: a blocked sub-agent lights its project's slot", () => {
  it("setNeedsInput(X) → project p1 blocked, workspace blocked, unrelated Q null or lower", () => {
    publishFixture({ tabOnX: true });
    const p1 = renderHook(() => useProjectAttention("p1"));
    const ws = renderHook(() => useWorkspaceAttention());
    const p2 = renderHook(() => useProjectAttention("p2"));
    expect(p1.result.current).toBe("working");
    act(() => useAgentStatusStore.getState().setNeedsInput("X", true));
    expect(p1.result.current).toBe("blocked");
    expect(ws.result.current).toBe("blocked");
    expect(p2.result.current).toBeNull();
    act(() => useAgentStatusStore.getState().setNeedsInput("X", false));
    expect(p1.result.current).toBe("working");
  });
});

describe("done → idle only via markFocused", () => {
  it("ten recomputes and ten observations leave it done; markFocused makes it idle", () => {
    publishFixture({ tabOnX: true });
    observe("in_progress");
    now += DEBOUNCE.startupGraceMs + 1;
    observe("completed");
    const hook = renderHook(() => useAgentAttention("X"));
    expect(hook.result.current.state).toBe("done");
    for (let i = 0; i < 10; i++) {
      now += 1000;
      observe("completed");
      hook.rerender();
      expect(hook.result.current.state).toBe("done");
    }
    expect(lastSeenAt("X")).toBeNull();
    act(() => useAgentStatusStore.getState().markFocused("X"));
    expect(lastSeenAt("X")).not.toBeNull();
    expect(hook.result.current.state).toBe("idle");
  });
});

describe("the companion subscription marks seen on activation with focus and a visible companion", () => {
  it("activateAgentTab with document.hasFocus() true and companionVisible() true marks seen; with either false it does not; no window focus listener", () => {
    const addSpy = vi.spyOn(window, "addEventListener");
    useAgentStatusStore.getState().stop();
    useAgentStatusStore.getState().start(clock);
    expect(addSpy.mock.calls.filter((c) => c[0] === "focus")).toHaveLength(0);
    addSpy.mockRestore();

    publishFixture();
    const hasFocus = vi.spyOn(document, "hasFocus");
    // companion hidden (docked, no panel) + focus → not marked
    useWorkspace.getState().setLayoutPreset("docked");
    hasFocus.mockReturnValue(true);
    act(() => { useCompanion.getState().openAgentTab({ kind: "research-thread", investigationId: "X", title: "X" }); });
    // openAgentTab in docked surfaces the panel; activate again to exercise the subscription with the panel open
    act(() => { useCompanion.getState().openAgentTab({ kind: "dialogue" }); });
    useWorkspace.getState().reset();
    useWorkspace.getState().setLayoutPreset("docked");
    act(() => { useCompanion.getState().activateAgentTab("agent:thread:X"); });
    expect(lastSeenAt("X")).toBeNull();
    // visible companion but window unfocused → not marked
    useWorkspace.getState().setLayoutPreset("omarchy-inset");
    hasFocus.mockReturnValue(false);
    act(() => { useCompanion.getState().activateAgentTab("agent:dialogue"); });
    act(() => { useCompanion.getState().activateAgentTab("agent:thread:X"); });
    expect(lastSeenAt("X")).toBeNull();
    // both true → marked
    hasFocus.mockReturnValue(true);
    act(() => { useCompanion.getState().activateAgentTab("agent:dialogue"); });
    act(() => { useCompanion.getState().activateAgentTab("agent:thread:X"); });
    expect(lastSeenAt("X")).not.toBeNull();
    hasFocus.mockRestore();
  });
});

describe("the 3 s startup grace (recorded interpretation: from the store's start, toasts only)", () => {
  it("a completion committed at +2999 from start emits a transition with no toast; the same at +3000 toasts 'finished'", () => {
    publishFixture();
    const events: { prev?: string; next: string; transition: unknown }[] = [];
    const un = subscribeTransitions((t) => events.push({ prev: t.prev, next: t.next, transition: t.transition }));
    observe("in_progress");
    now = 100_000 + 2999 - DEBOUNCE.confirmations * DEBOUNCE.intervalMs;
    observe("completed"); // commits at startedAt + 2999
    expect(useAgentStatusStore.getState().raw.get("X")?.status).toBe("completed");
    const inGrace = events.filter((e) => e.prev === "working" && e.next === "done");
    expect(inGrace).toHaveLength(1);
    expect(inGrace[0].transition).toBeNull();
    expect(peek().visible).toBeNull();

    act(() => useAgentStatusStore.getState().reset()); // startedAt = now
    publishFixture();
    events.length = 0;
    const started = now;
    observe("in_progress");
    now = started + 3000 - DEBOUNCE.confirmations * DEBOUNCE.intervalMs;
    observe("completed"); // commits at startedAt + 3000
    const after = events.filter((e) => e.prev === "working" && e.next === "done");
    expect(after).toHaveLength(1);
    expect(after[0].transition).toEqual({ kind: "finished" });
    expect(peek().visible?.kind).toBe("finished");
    un();
  });

  it("the grace does not delay the debounce: working→completed commits at +300 inside it, so the badge is right before the toast is allowed", () => {
    publishFixture();
    observe("in_progress");
    observe("completed");
    expect(inStartupGrace(100_000, now)).toBe(true);
    expect(useAgentStatusStore.getState().raw.get("X")?.status).toBe("completed");
  });
});

describe("owner epoch", () => {
  it("after setWorkspaceOwner(other): raw empty, queue empty, inStartupGrace true, no toast for 3 s under the new epoch", () => {
    publishFixture({ tabOnX: true });
    observe("in_progress");
    now += DEBOUNCE.startupGraceMs + 1;
    const before = useAgentStatusStore.getState().epoch;
    act(() => useAgentStatusStore.getState().setNeedsInput("X", true));
    expect(peek().queued.length + (peek().visible ? 1 : 0)).toBeGreaterThan(0);
    act(() => setWorkspaceOwner("someone-else"));
    const s = useAgentStatusStore.getState();
    expect(s.epoch).toBe(before + 1);
    expect(s.raw.size).toBe(0);
    expect(peek().visible).toBeNull();
    expect(peek().queued).toEqual([]);
    expect(inStartupGrace(s.startedAt!, now)).toBe(true);
    // Under the new epoch, within 3 s, a working→done transition toasts nothing.
    observe("in_progress");
    now += 1000;
    observe("completed");
    expect(peek().visible).toBeNull();
    expect(peek().queued).toEqual([]);
  });
});

describe("the store never writes the tree; dialogue is always unknown/no-run", () => {
  it("publishTree is never called by the store; a dialogue entry reads unknown/no-run and never toasts", () => {
    publishFixture();
    const spy = vi.spyOn(treeStore, "publishTree");
    const seen: unknown[] = [];
    const off = subscribeTransitions((t) => seen.push(t));
    observe("in_progress");
    now += DEBOUNCE.startupGraceMs + 1;
    observe("completed");
    act(() => useAgentStatusStore.getState().setNeedsInput("X", true));
    act(() => useAgentStatusStore.getState().markFocused("X"));
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
    off();
    const d = renderHook(() => useAgentAttention("agent:dialogue"));
    expect(d.result.current).toEqual({ state: "unknown", reason: "no-run" });
    expect(seen.every((t) => (t as { runId: string }).runId !== "agent:dialogue")).toBe(true);
    // Tree state is the fallback when no raw exists: Q is stopped in the tree.
    const q = renderHook(() => useAgentAttention("Q"));
    expect(q.result.current).toEqual({ state: "idle", reason: "stopped" });
    expect(attentionOf(useAgentStatusStore.getState().raw.get("Q"), null).state).toBe("unknown");
  });
});
