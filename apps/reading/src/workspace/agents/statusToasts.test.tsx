/**
 * statusToasts.test.tsx — SPR-10 M4: herdr R18 over LemonToast. Queue of 8
 * (oldest dropped at 9), one entry per run, warn 8 s / info 5 s, never err,
 * never for the active tab, promotion through onDismiss, and the Undo
 * toasts outside the cap.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";

import { LemonToastViewport, toast } from "../../components/lemon/LemonToast";
import { MASCOT_EXPERIENCE_EVENT } from "../../mascot";
import { composePreBackendTree } from "../contracts/adapters/preBackend";
import { markTreeUnfed, publishTree } from "../contracts/treeStore";
import { fixtureInputs, summary, tab } from "../contracts/fixtures.test.helpers";
import { useCompanion } from "../companionStore";
import { useWorkspace } from "../WorkspaceStore";
import { useAgentStatusStore } from "./agentStatusStore";
import { DEBOUNCE } from "./debounce";
import {
  FINISHED_TTL_MS,
  NEEDS_YOU_TTL_MS,
  STATUS_TOAST_QUEUE_MAX,
  enqueue,
  focusVisibleStatusToast,
  installStatusToasts,
  peek,
  resetStatusToasts,
  type StatusToast,
} from "./statusToasts";

let now = 50_000;
const clock = {
  now: () => now,
  setTimeout: (fn: () => void, ms: number) => window.setTimeout(fn, ms),
  clearTimeout: (h: unknown) => window.clearTimeout(h as number),
};
const IDS = Array.from({ length: 10 }, (_, i) => `X${i + 1}`);

function spec(runId: string, kind: StatusToast["kind"] = "needs-you"): StatusToast {
  return { runId, viewId: `agent:thread:${runId}`, viewOpen: false, investigationId: runId, title: `Title ${runId}`, kind };
}

function publish(tabs: string[] = []) {
  act(() => publishTree(composePreBackendTree(fixtureInputs({
    investigations: IDS.map((id) => summary(id, { status: "in_progress", completed_at: null, question: `Title ${id}` })),
    companionTabs: tabs.map((id) => tab("research-thread", { investigationId: id, title: `Title ${id}` })),
  })), new Date(now).toISOString()));
}

function observe(status: "in_progress" | "completed", ids: string[] = IDS) {
  act(() => {
    useAgentStatusStore.getState().observe(
      ids.map((id) => summary(id, { status, completed_at: status === "completed" ? new Date(now).toISOString() : null, question: `Title ${id}` })),
      new Set(ids),
      now,
    );
  });
  act(() => {
    now += DEBOUNCE.confirmations * DEBOUNCE.intervalMs;
    vi.advanceTimersByTime(DEBOUNCE.confirmations * DEBOUNCE.intervalMs);
  });
}

let uninstall: (() => void) | null = null;
let failures = 0;
const onFail = () => { failures += 1; };

beforeEach(() => {
  vi.useFakeTimers();
  now = 50_000;
  failures = 0;
  window.addEventListener(MASCOT_EXPERIENCE_EVENT, onFail);
  window.localStorage.removeItem("antiek:last_seen:v1");
  useCompanion.getState().reset();
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("omarchy-inset");
  resetStatusToasts();
  useAgentStatusStore.getState().reset();
  useAgentStatusStore.getState().start(clock);
  uninstall = installStatusToasts();
});

afterEach(() => {
  cleanup();
  window.removeEventListener(MASCOT_EXPERIENCE_EVENT, onFail);
  uninstall?.();
  uninstall = null;
  resetStatusToasts();
  useAgentStatusStore.getState().stop();
  markTreeUnfed();
  useCompanion.getState().reset();
  vi.useRealTimers();
});

describe("the queue", () => {
  it("one visible + 9 queued → queued.length === 8 and the first-queued run is the one missing", () => {
    for (const id of IDS) enqueue(spec(id));
    expect(STATUS_TOAST_QUEUE_MAX).toBe(8);
    expect(peek().visible?.runId).toBe("X1");
    expect(peek().queued).toHaveLength(8);
    expect(peek().queued.map((q) => q.runId)).toEqual(IDS.slice(2));
  });

  it("the same run twice → replaced in place, never two entries", () => {
    enqueue(spec("X1"));
    enqueue(spec("X2", "finished"));
    enqueue(spec("X3"));
    enqueue(spec("X2", "needs-you"));
    expect(peek().queued.map((q) => [q.runId, q.kind])).toEqual([["X2", "needs-you"], ["X3", "needs-you"]]);
  });

  it("needs-you → toast.warn ttl 8000 with an Open action; finished → toast.info ttl 5000; toast.err never (no shell failure)", () => {
    const warn = vi.spyOn(toast, "warn");
    const info = vi.spyOn(toast, "info");
    const err = vi.spyOn(toast, "err");
    enqueue(spec("X1", "needs-you"));
    expect(warn).toHaveBeenCalledWith("Title X1 needs you", expect.objectContaining({ ttl: NEEDS_YOU_TTL_MS, action: expect.objectContaining({ label: "Open" }), onDismiss: expect.any(Function) }));
    expect(NEEDS_YOU_TTL_MS).toBe(8000);
    act(() => toast.dismiss(peek().visible!.toastId!));
    enqueue(spec("X2", "finished"));
    expect(info).toHaveBeenCalledWith("Title X2 finished", expect.objectContaining({ ttl: FINISHED_TTL_MS, onDismiss: expect.any(Function) }));
    expect(FINISHED_TTL_MS).toBe(5000);
    expect(err).not.toHaveBeenCalled();
    expect(failures).toBe(0);
    warn.mockRestore(); info.mockRestore(); err.mockRestore();
  });

  it("onDismiss of the visible toast promotes the next and emits it (✕, action, ttl and the key all go through dismiss)", () => {
    const info = vi.spyOn(toast, "info");
    enqueue(spec("X1", "finished"));
    enqueue(spec("X2", "finished"));
    enqueue(spec("X3", "finished"));
    expect(info).toHaveBeenCalledTimes(1);
    expect(peek().visible?.runId).toBe("X1");
    act(() => toast.dismiss(peek().visible!.toastId!));
    expect(info).toHaveBeenCalledTimes(2);
    expect(peek().visible?.runId).toBe("X2");
    expect(peek().queued.map((q) => q.runId)).toEqual(["X3"]);
    // The ttl timer is the same road.
    act(() => { vi.advanceTimersByTime(FINISHED_TTL_MS); });
    expect(peek().visible?.runId).toBe("X3");
    act(() => { vi.advanceTimersByTime(FINISHED_TTL_MS); });
    expect(peek().visible).toBeNull();
    info.mockRestore();
  });

  it("a toast.undo created before and after the flood is still in LemonToast's rendered viewport", () => {
    render(<LemonToastViewport />);
    act(() => { toast.undo("Closed before", () => {}); });
    for (const id of IDS) act(() => enqueue(spec(id)));
    act(() => { toast.undo("Closed after", () => {}); });
    expect(screen.getByText("Closed before")).toBeTruthy();
    expect(screen.getByText("Closed after")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Undo" })).toHaveLength(2);
    // The visible status toast is in the viewport beside them, and only one.
    expect(screen.getAllByText(/needs you$/)).toHaveLength(1);
  });

  it("focusVisibleStatusToast() with nothing visible returns false", () => {
    expect(peek().visible).toBeNull();
    expect(focusVisibleStatusToast()).toBe(false);
  });
});

describe("transitions from the store", () => {
  it("active tab + companion visible → no toast; companion hidden with the same active tab → toast", () => {
    act(() => { useCompanion.getState().openAgentTab({ kind: "research-thread", investigationId: "X1", title: "Title X1" }); });
    publish(["X1"]);
    expect(useCompanion.getState().activeTabId).toBe("agent:thread:X1");
    observe("in_progress", ["X1"]);
    now += DEBOUNCE.startupGraceMs;
    observe("completed", ["X1"]);
    expect(peek().visible).toBeNull();
    // Same active tab, companion hidden (docked, no panel).
    useWorkspace.getState().reset();
    useWorkspace.getState().setLayoutPreset("docked");
    observe("in_progress", ["X1"]);
    observe("completed", ["X1"]);
    expect(peek().visible?.kind).toBe("finished");
    expect(peek().visible?.runId).toBe("X1");
    expect(peek().visible?.viewOpen).toBe(true);
  });

  it("needs-you is suppressed for the active tab too: setNeedsInput on the active, visible tab shows nothing; the same on a background tab shows 'needs you'", () => {
    act(() => { useCompanion.getState().openAgentTab({ kind: "research-thread", investigationId: "X2", title: "Title X2" }); });
    act(() => { useCompanion.getState().openAgentTab({ kind: "research-thread", investigationId: "X1", title: "Title X1" }); });
    publish(["X2", "X1"]);
    expect(useCompanion.getState().activeTabId).toBe("agent:thread:X1");
    observe("in_progress", ["X1", "X2"]);
    now += DEBOUNCE.startupGraceMs;
    act(() => useAgentStatusStore.getState().setNeedsInput("X1", true));
    expect(peek().visible, "needs-you toast fired for the tab the user is looking at").toBeNull();
    expect(peek().queued).toEqual([]);
    act(() => useAgentStatusStore.getState().setNeedsInput("X2", true));
    expect(peek().visible?.runId).toBe("X2");
    expect(peek().visible?.kind).toBe("needs-you");
  });

  it("needs-you fires on working→blocked after the grace, and the visible toast's key focuses and promotes", async () => {
    publish();
    observe("in_progress", ["X1", "X2"]);
    now += DEBOUNCE.startupGraceMs;
    act(() => useAgentStatusStore.getState().setNeedsInput("X1", true));
    act(() => useAgentStatusStore.getState().setNeedsInput("X2", true));
    expect(peek().visible?.runId).toBe("X1");
    expect(peek().queued.map((q) => q.runId)).toEqual(["X2"]);
    let ok = false;
    act(() => { ok = focusVisibleStatusToast(); });
    expect(ok).toBe(true);
    expect(peek().visible?.runId).toBe("X2");
    await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
    expect(useCompanion.getState().activeTabId).toBe("agent:thread:X1");
  });
});
