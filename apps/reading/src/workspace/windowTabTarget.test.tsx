import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { WorkspaceWindow } from "../components/windows/WorkspaceWindow";
import { awaitWorkspaceOwnerSession, setWorkspaceOwner, workspaceOwnerSession } from "../lib/accountWorkspaceOwner";
import { COMPANION_PANEL_ID, useCompanion } from "./companionStore";
import { pinPlatform, press, unpinPlatform } from "./keymapTestKit";
import { prefixState } from "../components/hotkeys/prefixState";
import { installShortcuts } from "./shortcuts";
import { useTabTrees } from "./tabTreeStore";
import { disablePersistence, useWorkspace } from "./WorkspaceStore";
import { useWindows } from "./windowsStore";

// Real mounted frame, dispatcher, stores and canonical local UNIT admission.
// This fixture is not a credential, server/catalogue or signed browser proof.
const ws = () => useWorkspace.getState();
const tabs = () => useTabTrees.getState();
const comp = () => useCompanion.getState();
const windows = () => useWindows.getState();
let uninstall: (() => void) | undefined;
const commands = ["ctrl+alt+]", "ctrl+alt+[", "prefix:n", "prefix:p"] as const;
const targets = ["root", "titlebar", "body"] as const;

beforeEach(async () => {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: (query: string) => ({
      matches: query.includes("reduce"), media: query, onchange: null,
      addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
      dispatchEvent: () => false,
    }),
  });
  pinPlatform("mac");
  disablePersistence();
  setWorkspaceOwner(null);
  setWorkspaceOwner("unit-window-tab-owner");
  await awaitWorkspaceOwnerSession(workspaceOwnerSession());
  ws().reset();
  comp().reset();
  windows().reset();
  tabs().resetTabTrees();
  window.history.replaceState(null, "", "/read/unit-background-a");
  await tabs().ensureMothership("reading");
  for (const id of ["unit-doc-a", "unit-doc-b"]) {
    tabs().spawnTab("reading", null, { tab_id: id, kind: "reader", ref: id, mothership: "reading", activate: false });
  }
  tabs().activateTab("reading", "unit-doc-a");
  comp().openAgentTab({ kind: "research-thread", investigationId: "unit-agent-a" });
  comp().openAgentTab({ kind: "research-thread", investigationId: "unit-agent-b" });
  comp().activateAgentTab("agent:thread:unit-agent-a");
  uninstall = installShortcuts(vi.fn());
});

afterEach(async () => {
  try {
    uninstall?.();
    uninstall = undefined;
    cleanup();
    await vi.dynamicImportSettled();
    prefixState.disarm();
    windows().reset();
    ws().reset();
    comp().reset();
    tabs().resetTabTrees();
    window.history.replaceState(null, "", "/");
    unpinPlatform();
  } finally {
    setWorkspaceOwner(null);
  }
});

function run(target: EventTarget, command: typeof commands[number]) {
  let event: KeyboardEvent | undefined;
  act(() => {
    if (command.startsWith("prefix:")) {
      press(target, "ctrl+b", "mac");
      event = press(target, command.slice(7), "mac");
    } else {
      event = press(target, command, "mac");
    }
  });
  return event;
}

async function mountWindow(side: "left" | "right", preset: "omarchy-inset" | "docked" = "omarchy-inset") {
  ws().setLayoutPreset(preset);
  if (preset === "omarchy-inset") ws().setFocusedPane(side);
  else if (side === "right") {
    ws().open("Companion", {}, { mode: "docked-right", title: "Agents", id: COMPANION_PANEL_ID });
    ws().focus(COMPANION_PANEL_ID);
  }
  const id = windows().open("library", {}, { title: "Foreground Library" });
  render(<>
    <button data-testid="background">Background cockpit</button>
    <WorkspaceWindow id={id}>
      <button data-testid="window-body">Hosted action</button>
      <input aria-label="Hosted text" />
    </WorkspaceWindow>
  </>);
  const root = screen.getByRole("dialog", { name: "Foreground Library" });
  await waitFor(() => expect(document.activeElement).toBe(root));
  const titlebar = screen.getByLabelText("Foreground Library — window controls");
  return { id, root, titlebar, body: screen.getByTestId("window-body") };
}

function unchangedBackground() {
  expect(tabs().trees.reading?.active_tab_id).toBe("unit-doc-a");
  expect(comp().activeTabId).toBe("agent:thread:unit-agent-a");
}

describe.each(["left", "right"] as const)("foreground window over remembered %s cockpit focus", (side) => {
  it.each(commands)("%s preserves background tabs from real window chrome and body", async (command) => {
    const frame = await mountWindow(side);
    for (const name of targets) {
      const target = frame[name];
      act(() => target.focus());
      run(target, command);
      await vi.dynamicImportSettled();
      unchangedBackground();
      expect(windows().windows[frame.id]).toBeDefined();
    }
  });

  it.each(["ctrl+alt+]", "ctrl+alt+["] as const)("%s preserves background tabs with body event and actual window focus", async (command) => {
    await mountWindow(side);
    const event = run(document.body, command);
    await vi.dynamicImportSettled();
    unchangedBackground();
    expect(event?.defaultPrevented).toBe(false);
  });
});

it.each(commands)("docked remembered right panel cannot steal %s from a window", async (command) => {
  const frame = await mountWindow("right", "docked");
  run(frame.root, command);
  await vi.dynamicImportSettled();
  unchangedBackground();
});

it.each(["left", "right"] as const)("returning actual focus to %s cockpit restores its next/previous keys", async (side) => {
  await mountWindow(side);
  const background = screen.getByTestId("background");
  act(() => background.focus());
  run(background, "ctrl+alt+]");
  await waitFor(() => {
    if (side === "left") expect(tabs().trees.reading?.active_tab_id).toBe("unit-doc-b");
    else expect(comp().activeTabId).toBe("agent:thread:unit-agent-b");
  });
  run(background, "prefix:p");
  await waitFor(unchangedBackground);
});

it("closing the actual window leaves ordinary cockpit tab cycling available", async () => {
  const frame = await mountWindow("left");
  act(() => windows().close(frame.id));
  expect(screen.queryByRole("dialog", { name: "Foreground Library" })).toBeNull();
  const background = screen.getByTestId("background");
  act(() => background.focus());
  run(background, "prefix:n");
  expect(tabs().trees.reading?.active_tab_id).toBe("unit-doc-b");
});

it("hosted text typing retains local ownership and never cycles background tabs", async () => {
  await mountWindow("left");
  const input = screen.getByRole("textbox", { name: "Hosted text" });
  act(() => input.focus());
  const event = run(input, "prefix:n");
  expect(prefixState.isArmed()).toBe(false);
  expect(event?.defaultPrevented).toBe(false);
  unchangedBackground();
});

it.each(["ctrl+alt+]", "ctrl+alt+["] as const)("hosted handler moving focus cannot send the same %s event to background tabs", async (command) => {
  const frame = await mountWindow("left");
  const background = screen.getByTestId("background");
  frame.body.addEventListener("keydown", () => background.focus());
  act(() => frame.body.focus());
  run(frame.body, command);
  expect(document.activeElement).toBe(background);
  unchangedBackground();
});
