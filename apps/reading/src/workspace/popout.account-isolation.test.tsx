import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setWorkspaceOwner } from "../lib/accountWorkspaceOwner";
import { workspaceOwnerSession } from "../lib/accountWorkspaceOwner";
import { applyOver, readScope } from "./persistence";
import { EMPTY_SNAPSHOT } from "./panel.types";
import { enablePersistence, setPersistScope, useWorkspace } from "./WorkspaceStore";
import { openPopoutFor, receivePopoutPanel } from "./popout";

// The cross-window transport and OS window are simulated. Production descriptors,
// owner transitions, channel selection and retirement run unchanged.
class UnitChannel extends EventTarget {
  static channels = new Set<UnitChannel>();
  closed = false;
  constructor(readonly name: string) { super(); UnitChannel.channels.add(this); }
  postMessage(data: unknown) {
    for (const peer of UnitChannel.channels) {
      if (peer !== this && !peer.closed && peer.name === this.name) {
        queueMicrotask(() => { if (!peer.closed) peer.dispatchEvent(new MessageEvent("message", { data })); });
      }
    }
  }
  close() { this.closed = true; UnitChannel.channels.delete(this); }
}
const closeWindow = vi.fn();
beforeEach(() => {
  setWorkspaceOwner(null);
  window.localStorage.clear();
  UnitChannel.channels.clear();
  closeWindow.mockReset();
  vi.stubGlobal("BroadcastChannel", UnitChannel);
  vi.spyOn(window, "close").mockImplementation(closeWindow);
  vi.spyOn(window, "open").mockReturnValue(window);
  setWorkspaceOwner("account-a");
  enablePersistence();
  setPersistScope({ kind: "global" });
});
afterEach(() => {
  setWorkspaceOwner(null);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  for (const channel of UnitChannel.channels) channel.close();
});
function openA() {
  useWorkspace.getState().open("NotebookEditor", { initialContent: "A private body" }, { id: "shared" });
  openPopoutFor("shared");
}

describe("popout account handoff", () => {
  it("a refused OS close cannot prevent retiring A's identity", () => {
    closeWindow.mockImplementationOnce(() => { throw new Error("OS close refused"); });
    openA();
    expect(() => setWorkspaceOwner("account-b")).not.toThrow();
    expect(workspaceOwnerSession().subject).toBe("account-b");
    expect(UnitChannel.channels.size).toBe(0);
  });
  it("hands off the real descriptor within the same trusted subject", async () => {
    openA();
    const panel = await receivePopoutPanel("shared");
    expect(panel?.props.initialContent).toBe("A private body");
  }, 15000);

  it("retires the old publisher and saves A's panel for its return instead of handing it to B", async () => {
    openA();
    const aChannels = [...UnitChannel.channels];
    setWorkspaceOwner("account-b");
    expect(closeWindow).toHaveBeenCalledOnce();
    expect(aChannels.every((channel) => channel.closed)).toBe(true);
    const pending = receivePopoutPanel("shared");
    const bChannel = [...UnitChannel.channels][0];
    expect(bChannel.name).toBe("antiek-workspace.account-b");
    setWorkspaceOwner(null);
    expect(await pending).toBeNull();
    setWorkspaceOwner("account-a");
    const saved = readScope({ kind: "global" });
    if (saved === null) throw new Error("A's saved panel is missing");
    const hydrated = applyOver(EMPTY_SNAPSHOT, saved);
    const restored = hydrated.panels.shared;
    expect(restored?.props.initialContent).toBe("A private body");
    expect(restored?.mode).toBe("floating");
    expect(hydrated.floatingIds).toContain("shared");
  }, 15000);

  it("unknown identity cannot open a transport or receive a private descriptor", async () => {
    setWorkspaceOwner(null);
    expect(await receivePopoutPanel("shared")).toBeNull();
    expect(UnitChannel.channels.size).toBe(0);
  });
});
