import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  accountStorageKey, awaitWorkspaceOwnerSession, beforeWorkspaceOwnerChange,
  isWorkspaceOwnerSession, resumeWorkspaceOwner, setWorkspaceOwner,
  subscribeWorkspaceOwnerAdmission, suspendWorkspaceOwner, workspaceOwnerAdmission,
  workspaceOwnerSession, type WorkspaceOwnerAdmission,
} from "./accountWorkspaceOwner";

const disposers: Array<() => void> = [];
function observe(listener: (admission: WorkspaceOwnerAdmission) => void) {
  const dispose = subscribeWorkspaceOwnerAdmission(listener);
  disposers.push(dispose);
  return dispose;
}
function retire(listener: () => void) {
  const dispose = beforeWorkspaceOwnerChange(listener);
  disposers.push(dispose);
  return dispose;
}
beforeEach(() => {
  localStorage.clear();
  setWorkspaceOwner("acct_observation_a");
});
afterEach(() => {
  for (const dispose of disposers.splice(0)) dispose();
  setWorkspaceOwner(null);
});

describe("synchronous captured-session admission", () => {
  it("closes admission before suspension delivery, deduplicates suspension and confirms the same token", async () => {
    const captured = workspaceOwnerSession();
    const events: Array<[WorkspaceOwnerAdmission["state"], boolean]> = [];
    observe((event) => {
      expect(event.session).toBe(captured);
      expect(Object.isFrozen(event)).toBe(true);
      expect(Object.keys(event).sort()).toEqual(["session", "state"]);
      events.push([event.state, isWorkspaceOwnerSession(captured)]);
    });
    suspendWorkspaceOwner();
    expect(events).toEqual([["suspended", false]]);
    const held = awaitWorkspaceOwnerSession(captured);
    suspendWorkspaceOwner();
    expect(events).toHaveLength(1);
    setWorkspaceOwner(captured.subject);
    expect(resumeWorkspaceOwner(captured)).toBe(true);
    expect(await held).toBe(true);
    expect(events).toEqual([["suspended", false], ["ready", true]]);
    expect(workspaceOwnerSession()).toBe(captured);
    expect(resumeWorkspaceOwner(captured)).toBe(false);
    expect(events).toHaveLength(2);
  });

  it("reports retiring before old-subject local flush, then publishes only the actual replacement", () => {
    const captured = workspaceOwnerSession();
    const order: string[] = [];
    observe((event) => {
      order.push(event.state);
      if (event.state === "retiring") {
        expect(event.session).toBe(captured);
        expect(isWorkspaceOwnerSession(captured)).toBe(false);
      } else {
        expect(event.session).toBe(workspaceOwnerSession());
        expect(event.session.subject).toBe("acct_observation_b");
      }
    });
    retire(() => {
      order.push("local-flush");
      expect(workspaceOwnerSession()).toBe(captured);
      expect(isWorkspaceOwnerSession(captured)).toBe(false);
      const key = accountStorageKey("draft", captured);
      if (key === null) throw new Error("A local partition is required");
      localStorage.setItem(key, "A unsaved local draft");
    });
    setWorkspaceOwner("acct_observation_b");
    expect(order).toEqual(["retiring", "local-flush", "ready"]);
    expect(localStorage.getItem("draft.owner.acct_observation_a")).toBe("A unsaved local draft");
    expect(localStorage.getItem("draft.owner.acct_observation_b")).toBeNull();
    expect(isWorkspaceOwnerSession(captured)).toBe(false);
  });

  it("delivers denied suspension and failure to later observers when the first one throws", async () => {
    const captured = workspaceOwnerSession();
    const primary = new Error("synthetic suspension observer failure");
    observe((event) => { if (event.state === "suspended") throw primary; });
    const events: Array<[WorkspaceOwnerAdmission["state"], boolean]> = [];
    observe((event) => { events.push([event.state, isWorkspaceOwnerSession(captured)]); });
    expect(() => suspendWorkspaceOwner()).toThrow(primary);
    expect(events).toEqual([["suspended", false], ["failed", false]]);
    expect(workspaceOwnerAdmission().state).toBe("failed");
    expect(workspaceOwnerSession()).toBe(captured);
    expect(await awaitWorkspaceOwnerSession(captured)).toBe(false);
    expect(resumeWorkspaceOwner(captured)).toBe(false);
    expect(events).toHaveLength(2);
  });

  it("retains observer, cleanup and failed-notification errors while still flushing the outgoing partition", () => {
    const captured = workspaceOwnerSession();
    const primary = new Error("synthetic retiring observer failure");
    const cleanupFailure = new TypeError("synthetic local flush failure");
    const secondary = new Error("synthetic failure observer failure");
    observe((event) => {
      if (event.state === "retiring") throw primary;
      if (event.state === "failed") throw secondary;
    });
    const later = vi.fn();
    observe(later);
    retire(() => {
      const key = accountStorageKey("draft", captured);
      if (key === null) throw new Error("A local partition is required");
      localStorage.setItem(key, "A final local edit");
      throw cleanupFailure;
    });
    try {
      setWorkspaceOwner("acct_observation_b");
      throw new Error("replacement unexpectedly succeeded");
    } catch (error) {
      expect(error).toBeInstanceOf(AggregateError);
      if (!(error instanceof AggregateError)) throw error;
      expect(error.errors).toEqual([primary, cleanupFailure, secondary]);
    }
    expect(later.mock.calls.map(([event]) => event.state)).toEqual(["retiring", "failed"]);
    expect(localStorage.getItem("draft.owner.acct_observation_a")).toBe("A final local edit");
    expect(workspaceOwnerSession()).toBe(captured);
    expect(isWorkspaceOwnerSession(captured)).toBe(false);
  });

  it.each(["suspend", "resume", "replace"] as const)("refuses reentrant %s without reopening the captured owner", (operation) => {
    const captured = workspaceOwnerSession();
    observe((event) => {
      if (event.state !== "retiring") return;
      if (operation === "suspend") suspendWorkspaceOwner();
      if (operation === "resume") resumeWorkspaceOwner(captured);
      if (operation === "replace") setWorkspaceOwner("acct_observation_c");
    });
    const denied: boolean[] = [];
    observe(() => { denied.push(isWorkspaceOwnerSession(captured)); });
    expect(() => setWorkspaceOwner("acct_observation_b")).toThrow("cannot change during admission notification");
    expect(denied).toEqual([false, false]);
    expect(workspaceOwnerSession()).toBe(captured);
    expect(workspaceOwnerAdmission().state).toBe("failed");
  });

  it("honors disposal before delivery and during an earlier observer", () => {
    const removed = vi.fn();
    let disposeLater = () => {};
    observe(() => { disposeLater(); });
    disposeLater = observe(removed);
    const alreadyDisposed = vi.fn();
    const dispose = observe(alreadyDisposed);
    dispose();
    suspendWorkspaceOwner();
    resumeWorkspaceOwner();
    expect(removed).not.toHaveBeenCalled();
    expect(alreadyDisposed).not.toHaveBeenCalled();
  });

  it("does not deliver an old event to the same callback's new registration", () => {
    const callback = vi.fn();
    let dispose = () => {};
    observe((event) => {
      if (event.state !== "suspended") return;
      dispose();
      dispose = observe(callback);
    });
    dispose = observe(callback);
    suspendWorkspaceOwner();
    expect(callback).not.toHaveBeenCalled();
    expect(resumeWorkspaceOwner(workspaceOwnerSession())).toBe(true);
    expect(callback.mock.calls.map(([event]) => event.state)).toEqual(["ready"]);
  });

  it("retires only one subscription when two consumers share a callback", () => {
    const callback = vi.fn();
    const first = observe(callback);
    observe(callback);
    suspendWorkspaceOwner();
    const suspended = callback.mock.calls.map(([event]) => event.state);
    first();
    expect(resumeWorkspaceOwner(workspaceOwnerSession())).toBe(true);
    expect(callback.mock.calls.map(([event]) => event.state)).toEqual(["suspended", "suspended", "ready"]);
    expect(suspended).toEqual(["suspended", "suspended"]);
  });

  it("refuses an A confirmation during B suspension and after A-to-B-to-A", () => {
    const oldA = workspaceOwnerSession();
    setWorkspaceOwner("acct_observation_b");
    const b = workspaceOwnerSession();
    suspendWorkspaceOwner();
    const observed = vi.fn();
    observe(observed);
    expect(resumeWorkspaceOwner(oldA)).toBe(false);
    expect(workspaceOwnerAdmission()).toEqual({ session: b, state: "suspended" });
    expect(observed).not.toHaveBeenCalled();
    setWorkspaceOwner("acct_observation_a");
    const freshA = workspaceOwnerSession();
    suspendWorkspaceOwner();
    observed.mockClear();
    expect(resumeWorkspaceOwner(oldA)).toBe(false);
    expect(observed).not.toHaveBeenCalled();
    expect(isWorkspaceOwnerSession(oldA)).toBe(false);
    expect(resumeWorkspaceOwner(freshA)).toBe(true);
    expect(observed).toHaveBeenCalledOnce();
  });

  it("failed same-subject recovery requires cleanup and produces a fresh token", async () => {
    const captured = workspaceOwnerSession();
    const primary = new Error("synthetic flush failure");
    const dispose = retire(() => { throw primary; });
    suspendWorkspaceOwner();
    const held = awaitWorkspaceOwnerSession(captured);
    expect(() => setWorkspaceOwner("acct_observation_b")).toThrow(primary);
    expect(await held).toBe(false);
    dispose();
    const events = vi.fn();
    observe(events);
    setWorkspaceOwner("acct_observation_a");
    expect(events.mock.calls.map(([event]) => event.state)).toEqual(["retiring", "ready"]);
    expect(workspaceOwnerSession()).not.toBe(captured);
    expect(isWorkspaceOwnerSession(captured)).toBe(false);
    expect(isWorkspaceOwnerSession(workspaceOwnerSession())).toBe(true);
  });

  it("cancellation refuses suspended work even when the same owner later confirms", async () => {
    const captured = workspaceOwnerSession();
    suspendWorkspaceOwner();
    const controller = new AbortController();
    const held = awaitWorkspaceOwnerSession(captured, controller.signal);
    controller.abort();
    expect(await held).toBe(false);
    expect(resumeWorkspaceOwner(captured)).toBe(true);
    expect(await held).toBe(false);
  });

  it("a throwing ready observer leaves failure visible and does not release held work", async () => {
    const captured = workspaceOwnerSession();
    suspendWorkspaceOwner();
    const held = awaitWorkspaceOwnerSession(captured);
    const primary = new Error("synthetic confirmation observer failure");
    observe((event) => { if (event.state === "ready") throw primary; });
    const events = vi.fn();
    observe(events);
    expect(() => resumeWorkspaceOwner(captured)).toThrow(primary);
    expect(await held).toBe(false);
    expect(events.mock.calls.map(([event]) => event.state)).toEqual(["ready", "failed"]);
    expect(isWorkspaceOwnerSession(captured)).toBe(false);
  });

  it("holds a waiter created by an early ready observer until all observers finish", async () => {
    const captured = workspaceOwnerSession();
    suspendWorkspaceOwner();
    let pending = Promise.resolve(true);
    observe((event) => {
      if (event.state === "ready") pending = awaitWorkspaceOwnerSession(captured);
    });
    const primary = new Error("synthetic later ready observer failure");
    observe((event) => { if (event.state === "ready") throw primary; });
    expect(() => resumeWorkspaceOwner(captured)).toThrow(primary);
    expect(await pending).toBe(false);
    expect(isWorkspaceOwnerSession(captured)).toBe(false);
  });

  it("releases a waiter created during successful same-token ready delivery", async () => {
    const captured = workspaceOwnerSession();
    suspendWorkspaceOwner();
    let pending = Promise.resolve(false);
    const order: string[] = [];
    observe((event) => {
      if (event.state !== "ready") return;
      pending = awaitWorkspaceOwnerSession(captured).then((ready) => {
        order.push("completion");
        return ready;
      });
      order.push("observer");
    });
    expect(resumeWorkspaceOwner(captured)).toBe(true);
    expect(order).toEqual(["observer"]);
    expect(await pending).toBe(true);
    expect(order).toEqual(["observer", "completion"]);
    expect(workspaceOwnerSession()).toBe(captured);
  });

  it("publishes null retirement without giving anonymous work owned authority", async () => {
    const captured = workspaceOwnerSession();
    const events = vi.fn();
    observe(events);
    setWorkspaceOwner(null);
    expect(events.mock.calls.map(([event]) => [event.state, event.session.subject])).toEqual([
      ["retiring", "acct_observation_a"], ["ready", null],
    ]);
    expect(isWorkspaceOwnerSession(captured)).toBe(false);
    expect(await awaitWorkspaceOwnerSession(workspaceOwnerSession())).toBe(false);
  });
});
