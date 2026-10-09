import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { flushSync } from "react-dom";

import KeySheet from "./KeySheet";
import {
  awaitWorkspaceOwnerSession,
  beforeWorkspaceOwnerChange,
  resumeWorkspaceOwner,
  setWorkspaceOwner,
  suspendWorkspaceOwner,
  subscribeWorkspaceOwnerAdmission,
  workspaceOwnerSession,
} from "../../lib/accountWorkspaceOwner";
import { writeCustomHotkeys } from "../../workspace/persistence";

beforeAll(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true, configurable: true,
      value: (query: string) => ({ matches: false, media: query, onchange: null,
        addEventListener: () => {}, removeEventListener: () => {},
        addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false }),
    });
  }
});

function seed(owner: string, label: string) {
  setWorkspaceOwner(owner);
  writeCustomHotkeys({
    schemaVersion: 1,
    bindings: [{ id: "pinned", spec: "alt+j", route: "/inv/private", entityId: "private",
      entityKind: "investigation", label }],
  });
}

function open() {
  return render(<KeySheet onClose={() => {}} platform="mac" />);
}

function expectPublicHelp() {
  expect(screen.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeTruthy();
  expect(document.querySelector('[data-keymap-action="projecttree.toggle"]')).toBeTruthy();
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
  setWorkspaceOwner(null);
});

describe("custom hotkey admission (synthetic local UNIT owners)", () => {
  it("retires outgoing private labels if owner cleanup fails, preserving public help", async () => {
    seed("keys-A", "A private research");
    await act(async () => { open(); });
    const release = beforeWorkspaceOwnerChange(() => { throw new Error("UNIT cleanup failure"); });
    try {
      act(() => { expect(() => setWorkspaceOwner("keys-B")).toThrow("UNIT cleanup failure"); });
      expect(screen.queryByText("A private research")).toBeNull();
      expect(screen.getByRole("status").textContent).toContain("Custom hotkeys are unavailable");
      expectPublicHelp();
    } finally { release(); }
  });

  it("never reads private storage when first opened under failed admission", async () => {
    seed("keys-A", "A private research");
    const release = beforeWorkspaceOwnerChange(() => { throw new Error("UNIT cleanup failure"); });
    try {
      expect(() => setWorkspaceOwner("keys-B")).toThrow("UNIT cleanup failure");
      const read = vi.spyOn(Storage.prototype, "getItem");
      await act(async () => { open(); });
      expect(read.mock.calls.filter(([key]) => key.startsWith("antiek.workspace.custom-hotkeys.owner."))).toHaveLength(0);
      expect(screen.queryByText("A private research")).toBeNull();
      expect(screen.getByRole("status").textContent).toContain("Custom hotkeys are unavailable");
      expectPublicHelp();
    } finally { release(); }
  });

  it("adopts only B labels on replacement while an independently mounted sheet remains open", async () => {
    seed("keys-B", "B private research");
    seed("keys-A", "A private research");
    await act(async () => { open(); });
    await act(async () => { setWorkspaceOwner("keys-B"); });
    expect(screen.queryByText("A private research")).toBeNull();
    expect(screen.getByText("B private research")).toBeTruthy();
    expectPublicHelp();
  });

  it("does not reuse an earlier A snapshot after A-B-A incarnation replacement", async () => {
    seed("keys-A", "A original research");
    await act(async () => { open(); });
    await act(async () => { seed("keys-B", "B private research"); });
    await act(async () => { seed("keys-A", "A current research"); });
    expect(screen.queryByText("A original research")).toBeNull();
    expect(screen.queryByText("B private research")).toBeNull();
    expect(screen.getByText("A current research")).toBeTruthy();
  });

  it("removes private labels on null ownership without removing public help", async () => {
    seed("keys-A", "A private research");
    await act(async () => { open(); });
    act(() => setWorkspaceOwner(null));
    expect(screen.queryByText("A private research")).toBeNull();
    expectPublicHelp();
  });

  it("preserves a loaded same-token snapshot across suspension and resume without rereading", async () => {
    seed("keys-A", "A private research");
    await act(async () => { open(); });
    const owner = workspaceOwnerSession();
    const read = vi.spyOn(Storage.prototype, "getItem");
    act(() => suspendWorkspaceOwner());
    expect(screen.getByText("A private research")).toBeTruthy();
    await act(async () => { expect(resumeWorkspaceOwner(owner)).toBe(true); });
    expect(screen.getByText("A private research")).toBeTruthy();
    expect(read.mock.calls.filter(([key]) => key.startsWith("antiek.workspace.custom-hotkeys.owner."))).toHaveLength(0);
  });

  it("waits for ready admission before an initially suspended sheet reads private storage", async () => {
    seed("keys-A", "A private research");
    suspendWorkspaceOwner();
    const owner = workspaceOwnerSession();
    const read = vi.spyOn(Storage.prototype, "getItem");
    await act(async () => { open(); });
    expect(read.mock.calls.filter(([key]) => key.startsWith("antiek.workspace.custom-hotkeys.owner."))).toHaveLength(0);
    expect(screen.queryByText("A private research")).toBeNull();
    expectPublicHelp();
    await act(async () => { expect(resumeWorkspaceOwner(owner)).toBe(true); });
    expect(screen.getByText("A private research")).toBeTruthy();
    expect(read.mock.calls.filter(([key]) => key.startsWith("antiek.workspace.custom-hotkeys.owner."))).toHaveLength(1);
  });

  it("does not read any account partition for an unknown owner", async () => {
    setWorkspaceOwner(null);
    const read = vi.spyOn(Storage.prototype, "getItem");
    await act(async () => { open(); });
    expect(read.mock.calls.filter(([key]) => key.startsWith("antiek.workspace.custom-hotkeys.owner."))).toHaveLength(0);
    expectPublicHelp();
  });

  it("refuses A data returned by a storage read that synchronously replaces A with B", async () => {
    seed("keys-B", "B private research");
    seed("keys-A", "A private research");
    const original = Storage.prototype.getItem;
    let replaced = false;
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) {
      const value = original.call(this, key);
      if (!replaced && key.endsWith(".owner.keys-A")) {
        replaced = true;
        setWorkspaceOwner("keys-B");
      }
      return value;
    });
    await act(async () => { open(); });
    expect(replaced).toBe(true);
    expect(screen.queryByText("A private research")).toBeNull();
    expect(screen.getByText("B private research")).toBeTruthy();
  });
});


describe("settled KeySheet confirmation (synthetic local UNIT owners)", () => {
  it("refuses private reads when a later ready observer fails admission", async () => {
    seed("keys-confirm", "Unconfirmed private research");
    const owner = workspaceOwnerSession();
    suspendWorkspaceOwner();
    const read = vi.spyOn(Storage.prototype, "getItem");
    const stopOpen = subscribeWorkspaceOwnerAdmission(({ state }) => {
      if (state === "ready") flushSync(() => { open(); });
    });
    const stopFailure = subscribeWorkspaceOwnerAdmission(({ state }) => {
      if (state === "ready") throw new Error("UNIT later ready observer failure");
    });
    try {
      act(() => {
        expect(() => resumeWorkspaceOwner(owner)).toThrow("UNIT later ready observer failure");
      });
      await act(async () => { await awaitWorkspaceOwnerSession(owner); });
      expect(read.mock.calls.filter(([key]) => key.startsWith("antiek.workspace.custom-hotkeys.owner."))).toHaveLength(0);
      expect(screen.queryByText("Unconfirmed private research")).toBeNull();
      expectPublicHelp();
    } finally { stopFailure(); stopOpen(); }
  });
});


describe("KeySheet pending view lifetime (synthetic local UNIT owners)", () => {
  it("withholds the initial private snapshot until settled confirmation", async () => {
    seed("keys-initial", "Confirmed private research");
    const owner = workspaceOwnerSession();
    const read = vi.spyOn(Storage.prototype, "getItem");
    open();
    expect(read.mock.calls.filter(([key]) => key.startsWith("antiek.workspace.custom-hotkeys.owner."))).toHaveLength(0);
    expect(screen.queryByText("Confirmed private research")).toBeNull();
    await act(async () => { await awaitWorkspaceOwnerSession(owner); });
    expect(screen.getByText("Confirmed private research")).toBeTruthy();
    expect(read.mock.calls.filter(([key]) => key.startsWith("antiek.workspace.custom-hotkeys.owner."))).toHaveLength(1);
  });

  it("retires an unmounted view before its pending same-token confirmation", async () => {
    seed("keys-dispose", "Disposed private research");
    const owner = workspaceOwnerSession();
    suspendWorkspaceOwner();
    const read = vi.spyOn(Storage.prototype, "getItem");
    const view = open();
    view.unmount();
    await act(async () => { expect(resumeWorkspaceOwner(owner)).toBe(true); });
    expect(read.mock.calls.filter(([key]) => key.startsWith("antiek.workspace.custom-hotkeys.owner."))).toHaveLength(0);
    expect(screen.queryByText("Disposed private research")).toBeNull();
  });

  it("does not adopt a pending A view after B replaces its session", async () => {
    seed("keys-pending-B", "B confirmed research");
    seed("keys-pending-A", "A pending research");
    suspendWorkspaceOwner();
    const read = vi.spyOn(Storage.prototype, "getItem");
    open();
    await act(async () => { setWorkspaceOwner("keys-pending-B"); });
    expect(read.mock.calls.filter(([key]) => key.endsWith(".owner.keys-pending-A"))).toHaveLength(0);
    expect(screen.queryByText("A pending research")).toBeNull();
    expect(screen.getByText("B confirmed research")).toBeTruthy();
    expectPublicHelp();
  });
});
