/**
 * shortcuts.agents.test.tsx — SPR-10 M4: the two agent keys through the real
 * dispatcher (installShortcuts + keymapTestKit). prefix+shift+o lands on the
 * visible status toast's agent and marks it seen; ctrl+alt+g / prefix+shift+g
 * toggle the goto picker through SHORTCUT_EVENTS; the prefix never arms
 * inside the picker's modal, so the chord is what closes it.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";

import { LemonModal } from "../../components/lemon/LemonModal";
import { prefixState } from "../../components/hotkeys/prefixState";
import { useCompanion } from "../companionStore";
import { pinPlatform, press, unpinPlatform } from "../keymapTestKit";
import { lastSeenAt } from "../seen";
import { SHORTCUT_EVENTS, installShortcuts } from "../shortcuts";
import { useWorkspace } from "../WorkspaceStore";
import { useAgentStatusStore, realClock } from "./agentStatusStore";
import { _seedForGuard, peek, resetStatusToasts } from "./statusToasts";

let uninstall: (() => void) | null = null;
const comp = () => useCompanion.getState();
const ws = () => useWorkspace.getState();

function key(spec: string, target: EventTarget = window, extra: KeyboardEventInit = {}): KeyboardEvent {
  let e = new KeyboardEvent("keydown");
  act(() => { e = press(target, spec, "mac", extra); });
  return e;
}

async function settle() {
  await act(async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); });
}

beforeEach(() => {
  pinPlatform("mac");
  window.localStorage.removeItem("antiek:last_seen:v1");
  ws().reset();
  ws().setLayoutPreset("omarchy-inset");
  comp().reset();
  resetStatusToasts();
  useAgentStatusStore.getState().reset();
  useAgentStatusStore.getState().start(realClock);
  uninstall = installShortcuts(vi.fn() as never);
});

afterEach(() => {
  uninstall?.();
  uninstall = null;
  cleanup();
  prefixState.disarm();
  resetStatusToasts();
  useAgentStatusStore.getState().stop();
  comp().reset();
  ws().reset();
  unpinPlatform();
  document.body.innerHTML = "";
});

describe("agents.gotoToast (prefix+shift+o / ctrl+alt+shift+o)", () => {
  it("with a visible toast whose target is open: activates that tab, focuses the right pane, marks it seen, promotes the next", async () => {
    act(() => { comp().openAgentTab({ kind: "research-thread", investigationId: "inv-a", title: "A" }); });
    act(() => { comp().openAgentTab({ kind: "research-thread", investigationId: "inv-b", title: "B" }); });
    expect(comp().activeTabId).toBe("agent:thread:inv-b");
    ws().setFocusedPane("left");
    act(() => {
      _seedForGuard({ runId: "inv-a", viewId: "agent:thread:inv-a", viewOpen: true, investigationId: "inv-a", title: "A", kind: "finished" });
      _seedForGuard({ runId: "inv-b", viewId: "agent:thread:inv-b", viewOpen: true, investigationId: "inv-b", title: "B", kind: "needs-you" });
    });
    expect(peek().visible?.runId).toBe("inv-a");
    expect(lastSeenAt("inv-a")).toBeNull();
    key("ctrl+b");
    expect(prefixState.isArmed()).toBe(true);
    const e = key("shift+o");
    expect(e.defaultPrevented).toBe(true);
    await settle();
    expect(comp().activeTabId).toBe("agent:thread:inv-a");
    expect(ws().focusedPane).toBe("right");
    expect(lastSeenAt("inv-a")).not.toBeNull();
    expect(peek().visible?.runId).toBe("inv-b");
  });

  it("with a target whose view is closed: opens a new research-thread tab with that investigationId", async () => {
    act(() => { _seedForGuard({ runId: "inv-z", viewId: "agent:thread:inv-z", viewOpen: false, investigationId: "inv-z", title: "Z", kind: "finished" }); });
    expect(comp().tabs).toHaveLength(0);
    const e = key("ctrl+alt+shift+o");
    expect(e.defaultPrevented).toBe(true);
    await settle();
    expect(comp().tabs.map((t) => [t.kind, t.investigationId])).toEqual([["research-thread", "inv-z"]]);
    expect(comp().activeTabId).toBe("agent:thread:inv-z");
    expect(lastSeenAt("inv-z")).not.toBeNull();
  });

  it("with nothing visible: the key is not ours (not prevented on the chord), activeTabId unchanged", async () => {
    act(() => { comp().openAgentTab({ kind: "research-thread", investigationId: "inv-a", title: "A" }); });
    const e = key("ctrl+alt+shift+o");
    expect(e.defaultPrevented).toBe(false);
    await settle();
    expect(comp().activeTabId).toBe("agent:thread:inv-a");
    expect(lastSeenAt("inv-a")).toBeNull();
  });
});

describe("agents.goto (prefix+shift+g / ctrl+alt+g)", () => {
  it("both keys dispatch AGENT_GOTO_TOGGLE; the prefix does not arm inside the picker's modal, the chord still fires there", () => {
    const seen = vi.fn();
    window.addEventListener(SHORTCUT_EVENTS.AGENT_GOTO_TOGGLE, seen);
    key("ctrl+b");
    key("shift+g");
    expect(seen).toHaveBeenCalledTimes(1);
    key("ctrl+alt+g");
    expect(seen).toHaveBeenCalledTimes(2);
    // A stand-in for the open picker: a modal owned by agents.goto.
    render(
      <LemonModal open onClose={() => {}} title="Agents">
        <div data-keymap-owner="agents.goto"><button type="button">row</button></div>
      </LemonModal>,
    );
    const dialog = document.querySelector('[aria-modal="true"]')!;
    const inner = dialog.querySelector("button")!;
    inner.focus();
    key("ctrl+b", inner);
    expect(prefixState.isArmed()).toBe(false);
    key("shift+g", inner);
    expect(seen).toHaveBeenCalledTimes(2);
    // The real Mac keydown composes "©" for option+g (keymapTestKit's
    // model, and what the guard's browser leg dispatches). A modal that is
    // not a text field cannot type it, so the chord twin must still fire.
    const e = key("ctrl+alt+g", inner);
    expect(e.defaultPrevented).toBe(true);
    expect(seen).toHaveBeenCalledTimes(3);
    // Another action's chord stays the dialog's.
    const other = key("ctrl+alt+c", inner);
    expect(other.defaultPrevented).toBe(false);
    window.removeEventListener(SHORTCUT_EVENTS.AGENT_GOTO_TOGGLE, seen);
  });

  it("the agent keys add no window keydown listener (the dispatcher's two owners are the only ones)", () => {
    const spy = vi.spyOn(window, "addEventListener");
    key("ctrl+alt+g");
    key("ctrl+alt+shift+o");
    expect(spy.mock.calls.filter((c) => c[0] === "keydown")).toHaveLength(0);
    spy.mockRestore();
  });
});
