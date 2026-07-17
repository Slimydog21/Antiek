import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { handoffPopoutToMain, openPopoutFor } from "./popout";
import { useWorkspace } from "./WorkspaceStore";

type MessageListener = (event: MessageEvent) => void;

class FakeBroadcastChannel {
  static instances: FakeBroadcastChannel[] = [];
  listeners = new Set<MessageListener>();
  posted: unknown[] = [];
  closed = false;

  constructor(readonly name: string) {
    FakeBroadcastChannel.instances.push(this);
  }
  addEventListener(_kind: string, listener: MessageListener) {
    this.listeners.add(listener);
  }
  removeEventListener(_kind: string, listener: MessageListener) {
    this.listeners.delete(listener);
  }
  postMessage(message: unknown) {
    this.posted.push(message);
  }
  emit(data: unknown) {
    for (const listener of [...this.listeners]) listener({ data } as MessageEvent);
  }
  close() {
    this.closed = true;
  }
}

describe("popout exact main-view handoff", () => {
  beforeEach(() => {
    FakeBroadcastChannel.instances = [];
    vi.stubGlobal("BroadcastChannel", FakeBroadcastChannel);
    useWorkspace.getState().reset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    useWorkspace.getState().reset();
    window.history.replaceState({}, "", "/");
  });

  it("main consumes only the addressed descriptor, navigates, and acknowledges", () => {
    const mine = useWorkspace.getState().open("ChaseThread", {}, { id: "panel:mine" });
    const other = useWorkspace.getState().open("ChaseThread", {}, { id: "panel:other" });
    vi.spyOn(window, "open").mockReturnValue({} as Window);
    openPopoutFor(mine);
    const channel = FakeBroadcastChannel.instances[0];

    channel.emit({ kind: "popout-consumed", panelId: mine, path: "/inv/inv-child" });

    expect(useWorkspace.getState().panels[mine]).toBeUndefined();
    expect(useWorkspace.getState().panels[other]).toBeDefined();
    expect(window.location.pathname).toBe("/inv/inv-child");
    expect(channel.posted).toContainEqual({ kind: "popout-consumed-ack", panelId: mine });
  });

  it("popout waits for the exact acknowledgement before closing", () => {
    Object.defineProperty(window, "opener", {
      configurable: true,
      value: { closed: false },
    });
    const close = vi.spyOn(window, "close").mockImplementation(() => undefined);

    handoffPopoutToMain("panel:mine", "/inv/inv-child");
    const channel = FakeBroadcastChannel.instances[0];
    expect(channel.posted).toEqual([
      { kind: "popout-consumed", panelId: "panel:mine", path: "/inv/inv-child" },
    ]);
    expect(close).not.toHaveBeenCalled();

    channel.emit({ kind: "popout-consumed-ack", panelId: "panel:other" });
    expect(close).not.toHaveBeenCalled();
    channel.emit({ kind: "popout-consumed-ack", panelId: "panel:mine" });
    expect(close).toHaveBeenCalledTimes(1);
  });
});
