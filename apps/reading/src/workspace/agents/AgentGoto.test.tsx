/**
 * AgentGoto.test.tsx — SPR-10 M5: the goto picker through the real
 * dispatcher. ctrl+alt+g opens it and closes it again; every key in herdr
 * B6 does its one thing; Esc in the search returns to the list without
 * closing; Enter lands on the row through focusAgent and closes.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { prefixState } from "../../components/hotkeys/prefixState";
import { composePreBackendTree } from "../contracts/adapters/preBackend";
import { markTreeUnfed, publishTree } from "../contracts/treeStore";
import { fixtureInputs, summary, tab } from "../contracts/fixtures.test.helpers";
import { useCompanion } from "../companionStore";
import { pinPlatform, press, unpinPlatform } from "../keymapTestKit";
import { installShortcuts } from "../shortcuts";
import { useWorkspace } from "../WorkspaceStore";
import { AgentGoto } from "./AgentGoto";
import { useAgentStatusStore, realClock } from "./agentStatusStore";

let uninstall: (() => void) | null = null;
const MEMBER = [{ member_kind: "investigation" as const, member_id: "D", added_at: "2026-09-18T10:00:00Z" }];

function publish() {
  act(() => publishTree(composePreBackendTree(fixtureInputs({
    investigations: [
      summary("A", { status: "in_progress", completed_at: null, question: "Alpha run", started_at: "2026-10-01T00:00:00Z" }),
      summary("B", { status: "completed", question: "Beta run", started_at: "2026-10-03T00:00:00Z", completed_at: "2026-10-03T01:00:00Z" }),
      summary("C", { status: "stopped", question: "Gamma run", started_at: "2026-10-02T00:00:00Z" }),
      summary("D", { status: "in_progress", completed_at: null, question: "Delta run", started_at: "2026-10-04T00:00:00Z" }),
    ],
    companionTabs: [tab("dialogue")],
    membersByProject: new Map([["p1", MEMBER]]),
  })), new Date().toISOString()));
}

const dialog = () => document.querySelector<HTMLElement>('[data-keymap-owner="agents.goto"]');
const list = () => screen.getByRole("listbox", { name: "Agents" });
const search = () => screen.getByRole("searchbox", { name: "Search agents" }) as HTMLInputElement;
const selected = () => dialog()!.querySelector<HTMLElement>('[role="option"][aria-selected="true"]')?.textContent ?? null;
const rowTitles = () => [...dialog()!.querySelectorAll<HTMLElement>('[role="option"] [data-row-title]')].map((e) => e.textContent);

async function chord(spec: string, target: EventTarget = window, extra: KeyboardEventInit = {}) {
  await act(async () => { press(target, spec, "mac", extra); });
}

async function open() {
  await chord("ctrl+alt+g");
  await waitFor(() => expect(dialog()).toBeTruthy());
  await waitFor(() => expect(rowTitles().length).toBeGreaterThan(0));
  act(() => list().focus());
}

beforeEach(() => {
  pinPlatform("mac");
  window.localStorage.removeItem("antiek:last_seen:v1");
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("omarchy-inset");
  useCompanion.getState().reset();
  act(() => { useCompanion.getState().openAgentTab({ kind: "dialogue" }); });
  useAgentStatusStore.getState().reset();
  useAgentStatusStore.getState().start(realClock);
  publish();
  uninstall = installShortcuts(vi.fn() as never);
});

afterEach(() => {
  uninstall?.();
  uninstall = null;
  cleanup();
  prefixState.disarm();
  useAgentStatusStore.getState().stop();
  markTreeUnfed();
  useCompanion.getState().reset();
  useWorkspace.getState().reset();
  unpinPlatform();
  document.body.innerHTML = "";
});

describe("open and close", () => {
  it("ctrl+alt+g opens the picker (root data-keymap-owner=agents.goto); ctrl+alt+g from inside closes it; prefix+shift+g never arms inside", async () => {
    render(<AgentGoto />);
    expect(dialog()).toBeNull();
    await open();
    expect(dialog()!.closest('[aria-modal="true"]')).toBeTruthy();
    // The prefix does not arm from inside the modal.
    await chord("ctrl+b", list());
    expect(prefixState.isArmed()).toBe(false);
    await chord("ctrl+alt+g", list(), { key: "g" });
    await waitFor(() => expect(dialog()).toBeNull());
  });

  it("groups by project with Everywhere last; rows carry a visible-word StatusDot and focus/open by viewOpen", async () => {
    render(<AgentGoto />);
    await open();
    const headings = [...dialog()!.querySelectorAll("h3")].map((h) => h.textContent);
    expect(headings).toEqual(["Default project", "Varda diligence", "Everywhere"]);
    expect(rowTitles()).toEqual(["Beta run", "Alpha run", "Gamma run", "Delta run", "dialogue"]);
    const first = dialog()!.querySelector('[role="option"]')!;
    expect(first.querySelector('[role="img"]')?.getAttribute("aria-label")).toBe("done");
    expect(first.textContent).toContain("open");
    const last = [...dialog()!.querySelectorAll('[role="option"]')].at(-1)!;
    expect(last.textContent).toContain("focus");
  });
});

describe("keys (herdr B6)", () => {
  it("j/k move inside a group and clamp; Left/Right move between groups without wrap", async () => {
    render(<AgentGoto />);
    await open();
    expect(selected()).toContain("Beta run");
    fireEvent.keyDown(list(), { key: "j" });
    expect(selected()).toContain("Alpha run");
    fireEvent.keyDown(list(), { key: "ArrowDown" });
    fireEvent.keyDown(list(), { key: "j" });
    expect(selected()).toContain("Gamma run");
    fireEvent.keyDown(list(), { key: "k" });
    expect(selected()).toContain("Alpha run");
    fireEvent.keyDown(list(), { key: "ArrowLeft" });
    expect(selected()).toContain("Alpha run");
    fireEvent.keyDown(list(), { key: "ArrowRight" });
    expect(selected()).toContain("Delta run");
    fireEvent.keyDown(list(), { key: "ArrowRight" });
    expect(selected()).toContain("dialogue");
    fireEvent.keyDown(list(), { key: "ArrowRight" });
    expect(selected()).toContain("dialogue");
    fireEvent.keyDown(list(), { key: "ArrowLeft" });
    fireEvent.keyDown(list(), { key: "ArrowLeft" });
    expect(selected()).toContain("Beta run");
  });

  it("b/w/i/d leave exactly that state; a restores; the chips name the active filter", async () => {
    render(<AgentGoto />);
    await open();
    act(() => useAgentStatusStore.getState().setNeedsInput("A", true));
    fireEvent.keyDown(list(), { key: "b" });
    expect(rowTitles()).toEqual(["Alpha run"]);
    fireEvent.keyDown(list(), { key: "w" });
    expect(rowTitles()).toEqual(["Delta run"]);
    fireEvent.keyDown(list(), { key: "i" });
    expect(rowTitles()).toEqual(["Gamma run"]);
    fireEvent.keyDown(list(), { key: "d" });
    expect(rowTitles()).toEqual(["Beta run"]);
    expect(dialog()!.querySelector('[data-filter-active="done"]')).toBeTruthy();
    fireEvent.keyDown(list(), { key: "a" });
    expect(rowTitles()).toEqual(["Alpha run", "Beta run", "Gamma run", "Delta run", "dialogue"]);
  });

  it("/ focuses the search where a typed b filters by TEXT; Esc in the search preventDefaults and returns focus to the list, modal stays open", async () => {
    render(<AgentGoto />);
    await open();
    fireEvent.keyDown(list(), { key: "/" });
    expect(document.activeElement).toBe(search());
    fireEvent.change(search(), { target: { value: "b" } });
    expect(rowTitles()).toEqual(["Beta run"]);
    const esc = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    act(() => { search().dispatchEvent(esc); });
    expect(esc.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(list());
    expect(dialog()).toBeTruthy();
    // ArrowDown leaves the search for the list.
    act(() => search().focus());
    fireEvent.keyDown(search(), { key: "ArrowDown" });
    expect(document.activeElement).toBe(list());
  });

  it("Enter opens a closed row's research thread through focusAgent and closes the picker", async () => {
    render(<AgentGoto />);
    await open();
    fireEvent.keyDown(list(), { key: "j" });
    expect(selected()).toContain("Alpha run");
    fireEvent.keyDown(list(), { key: "Enter" });
    await waitFor(() => expect(dialog()).toBeNull());
    await waitFor(() => expect(useCompanion.getState().activeTabId).toBe("agent:thread:A"));
    expect(useCompanion.getState().tabs.map((t) => t.investigationId ?? t.kind)).toEqual(["dialogue", "A"]);
    expect(useWorkspace.getState().focusedPane).toBe("right");
  });

  it("the picker registers no window/document keydown listener", async () => {
    const spy = vi.spyOn(window, "addEventListener");
    const dspy = vi.spyOn(document, "addEventListener");
    render(<AgentGoto />);
    await open();
    const keydowns = [...spy.mock.calls, ...dspy.mock.calls].filter((c) => c[0] === "keydown");
    // LemonModal's own Escape owner is the only global keydown added by opening.
    expect(keydowns.length).toBeLessThanOrEqual(1);
    spy.mockRestore(); dspy.mockRestore();
  });
});
