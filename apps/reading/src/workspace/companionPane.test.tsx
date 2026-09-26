/**
 * companionPane.test.tsx — cockpit chrome PR 2 (C4) acceptance.
 *
 *   The companion right pane with AI agents as tabs: stable per-agent ids
 *   (re-activation focuses, never duplicates), close as a view act, tab
 *   order = activation order, ⋯ overflow that never bounds cycling, status
 *   glyphs from the shared researchState vocabulary (terminal states
 *   honest, never a spinner forever), the prefix n/p + ctrl+alt ]/[ rows
 *   cycling tabs only when the pane is visible, and the C4→C5 seam event
 *   (openDocumentInLeftPane) reaching the bridge handler — one component,
 *   two mounts (the inset right pane; the docked "Companion" panel).
 *
 * The dispatcher runs with REAL handlers; the substrate is mocked at
 * apiFetch (investigation list + the one-shot thought-partner wire).
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

import type { InvestigationSummary } from "../lib/api";

const SUMMARIES: InvestigationSummary[] = [
  { investigation_id: "inv-live", question: "Is the gate safe?", status: "in_progress", started_at: "2026-09-20T10:00:00Z", completed_at: null, cost_usd_total: 0.42, parent_investigation_id: null },
  { investigation_id: "inv-done", question: "What breaks on retry?", status: "completed", started_at: "2026-09-19T10:00:00Z", completed_at: "2026-09-19T11:00:00Z", cost_usd_total: 1.2, parent_investigation_id: null, spawned_by_daemon: true },
  { investigation_id: "inv-fail", question: "Why did the embedder 503?", status: "failed", started_at: "2026-09-18T10:00:00Z", completed_at: "2026-09-18T10:30:00Z", cost_usd_total: 0.9, parent_investigation_id: null },
  { investigation_id: "inv-stop", question: "Halted mid-chase", status: "stopped", started_at: "2026-09-17T10:00:00Z", completed_at: "2026-09-17T10:20:00Z", cost_usd_total: 0.3, parent_investigation_id: null },
];

/** The thought-partner wire's next status (503 simulates no provider). */
let tpStatus = 200;

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/thought-partner")) {
      return Promise.resolve({
        ok: tpStatus === 200,
        status: tpStatus,
        json: async () => ({ text: "a considered reply", shape: "CHALLENGE" }),
        text: async () => "provider isn't configured",
      });
    }
    if (url.includes("/investigations")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ count: SUMMARIES.length, investigations: SUMMARIES }),
      });
    }
    return Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" });
  }),
  // listInvestigations is mocked directly: the original closes over the
  // module's REAL apiFetch, so overriding apiFetch alone would not intercept it.
  listInvestigations: vi.fn(async () => ({ count: SUMMARIES.length, investigations: SUMMARIES })),
  postTypedEvent: vi.fn(() => Promise.resolve({ event_id: "e" })),
}));

import { prefixState } from "../components/hotkeys/prefixState";
import CompanionPane from "./CompanionPane";
import { PanelLayout } from "./PanelLayout";
import { COMPANION_PANEL_ID, useCompanion } from "./companionStore";
import { useWorkspace } from "./WorkspaceStore";
import { useWindows } from "./windowsStore";
import { installShortcuts } from "./shortcuts";
import { openDocumentInLeftPane, setOpenDocumentHandler } from "./crossPane";
import { pinPlatform, press, unpinPlatform } from "./keymapTestKit";

const { tierRef } = vi.hoisted(() => ({ tierRef: { current: "xl" as string } }));
vi.mock("./useViewportTier", () => ({
  useViewportTier: () => tierRef.current,
}));

let uninstall: (() => void) | null = null;
const ws = () => useWorkspace.getState();
const comp = () => useCompanion.getState();

function key(target: EventTarget, spec: string): KeyboardEvent {
  let e = new KeyboardEvent("keydown");
  act(() => {
    e = press(target, spec, "mac");
  });
  return e;
}

beforeEach(() => {
  pinPlatform("mac");
  tierRef.current = "xl";
  tpStatus = 200;
  ws().reset();
  ws().setLayoutPreset("docked");
  comp().reset();
  uninstall = installShortcuts(vi.fn() as never);
});

afterEach(() => {
  uninstall?.();
  uninstall = null;
  cleanup();
  prefixState.disarm();
  ws().reset();
  ws().setLayoutPreset("docked");
  comp().reset();
  useWindows.getState().reset();
  setOpenDocumentHandler(null);
  unpinPlatform();
  document.body.innerHTML = "";
  window.localStorage.removeItem("antiek.workspace.layout-preset");
});

function mountPane() {
  return render(
    <MemoryRouter>
      <CompanionPane />
    </MemoryRouter>,
  );
}

function mountInsetLayout() {
  ws().setLayoutPreset("omarchy-inset");
  return render(
    <MemoryRouter>
      <PanelLayout mainSlot={<p>route content</p>} />
    </MemoryRouter>,
  );
}

function openThreadTab(investigationId: string, documentId?: string) {
  let id = "";
  act(() => {
    id = comp().openAgentTab({
      kind: "research-thread",
      investigationId,
      title: SUMMARIES.find((s) => s.investigation_id === investigationId)?.question ?? undefined,
      documentId,
    });
  });
  return id;
}

// ─── store semantics ─────────────────────────────────────────────────────

describe("agent tab semantics (companionStore)", () => {
  it("stable per-agent ids: re-activating an agent focuses its tab, never duplicates", () => {
    const a = openThreadTab("inv-live");
    openThreadTab("inv-done");
    const again = openThreadTab("inv-live");
    expect(again).toBe(a);
    expect(comp().tabs.filter((t) => t.id === a)).toHaveLength(1);
    expect(comp().activeTabId).toBe(a);
  });

  it("the dialogue agent is a single instance (one-shot: one is the honest model)", () => {
    act(() => {
      comp().openAgentTab({ kind: "dialogue" });
      comp().openAgentTab({ kind: "dialogue" });
    });
    expect(comp().tabs.filter((t) => t.kind === "dialogue")).toHaveLength(1);
  });

  it("close removes the tab only — a view act; activation falls to the neighbour", () => {
    const a = openThreadTab("inv-live");
    const b = openThreadTab("inv-done");
    expect(comp().activeTabId).toBe(b);
    act(() => {
      comp().closeAgentTab(b);
    });
    expect(comp().tabs.map((t) => t.id)).toEqual([a]);
    expect(comp().activeTabId).toBe(a);
  });

  it("cycling wraps across ALL tabs — overflow is never a hopping boundary", () => {
    for (const id of ["inv-live", "inv-done", "inv-fail", "inv-stop"]) openThreadTab(id);
    for (let i = 0; i < 3; i++) {
      act(() => {
        comp().openAgentTab({ kind: "research-thread", investigationId: `inv-x${i}`, title: `x${i}` });
      });
    }
    // 7 tabs: past the strip's visible five. Cycling from the last wraps to first.
    expect(comp().tabs).toHaveLength(7);
    const first = comp().tabs[0].id;
    act(() => {
      comp().activateAgentTab(comp().tabs[6].id);
    });
    act(() => {
      comp().cycleAgentTab(1);
    });
    expect(comp().activeTabId).toBe(first);
    act(() => {
      comp().cycleAgentTab(-1);
    });
    expect(comp().activeTabId).toBe(comp().tabs[6].id);
  });
});

// ─── mounts ──────────────────────────────────────────────────────────────

describe("one component, two mounts", () => {
  it("the inset preset's right pane IS the companion", () => {
    const { container } = mountInsetLayout();
    const right = container.querySelector<HTMLElement>('[data-pane="right"]')!;
    expect(right.querySelector("[data-companion-pane]")).toBeTruthy();
    expect(right.querySelector("[data-companion-empty]")).toBeTruthy();
  });

  it("in the docked preset, spawning an agent surfaces the Companion right-dock panel", () => {
    expect(ws().panels[COMPANION_PANEL_ID]).toBeUndefined();
    openThreadTab("inv-live");
    const panel = ws().panels[COMPANION_PANEL_ID];
    expect(panel).toBeTruthy();
    expect(ws().dockRightIds).toContain(COMPANION_PANEL_ID);
  });
});

// ─── the strip: tabs, glyphs, close, overflow ────────────────────────────

describe("the tab strip", () => {
  it("renders agent tabs with titles and status glyphs from the shared vocabulary", async () => {
    openThreadTab("inv-live");
    openThreadTab("inv-done");
    openThreadTab("inv-fail");
    mountPane();
    // The summary-driven surface proves the list has loaded (the tab titles
    // are synchronous from the store and would race the fetch).
    await screen.findByText("needs attention");
    expect(screen.getByText("Is the gate safe?")).toBeTruthy();
    // Working: the ambient pulse, reduced-motion honored by the class itself.
    const liveTab = document.querySelector('[data-agent-tab="agent:thread:inv-live"]')!;
    expect(liveTab.querySelector(".animate-pulse")).toBeTruthy();
    expect(liveTab.querySelector(".animate-pulse")!.className).toContain("motion-reduce:animate-none");
    // Done: the success dot, no pulse. Failed: "needs attention", no pulse —
    // terminal states are honest, never a spinner forever.
    const doneTab = document.querySelector('[data-agent-tab="agent:thread:inv-done"]')!;
    expect(doneTab.querySelector(".bg-\\[var\\(--state-done\\)\\]")).toBeTruthy();
    expect(doneTab.querySelector(".animate-pulse")).toBeNull();
    const failTab = document.querySelector('[data-agent-tab="agent:thread:inv-fail"]')!;
    expect(failTab.querySelector(".bg-\\[var\\(--state-blocked\\)\\]")).toBeTruthy();
    expect(failTab.querySelector(".animate-pulse")).toBeNull();
    expect(failTab.querySelector('[aria-label="needs attention"]')).toBeTruthy();
  });

  it("the active surface is the shared thread card; close removes the tab", async () => {
    openThreadTab("inv-done");
    mountPane();
    await screen.findByText("What breaks on retry?");
    expect(await screen.findByText("done")).toBeTruthy();
    expect(screen.getByText(/found by the loop/)).toBeTruthy();
    expect(screen.getByText(/\$1\.20/)).toBeTruthy();
    expect(screen.getByText("Open research →").closest("a")!.getAttribute("href")).toBe("/inv/inv-done");
    fireEvent.click(screen.getByLabelText(/Close What breaks on retry\?/));
    expect(comp().tabs).toHaveLength(0);
    expect(document.querySelector("[data-companion-empty]")).toBeTruthy();
  });

  it("past five tabs the rest collapse into a ⋯ menu; the menu activates them", async () => {
    for (const id of ["inv-live", "inv-done", "inv-fail", "inv-stop"]) openThreadTab(id);
    for (let i = 0; i < 3; i++) {
      act(() => {
        comp().openAgentTab({ kind: "research-thread", investigationId: `inv-x${i}`, title: `extra ${i}` });
      });
    }
    mountPane();
    // The strip renders from the store synchronously — no summary wait needed.
    expect(document.querySelectorAll("[data-agent-tab]")).toHaveLength(5);
    const overflow = document.querySelector("[data-companion-overflow]")!;
    expect(overflow).toBeTruthy();
    fireEvent.click(screen.getByLabelText("2 more agents"));
    fireEvent.click(screen.getByText("extra 1"));
    expect(comp().activeTabId).toBe("agent:thread:inv-x1");
  });

  it("+ new agent offers a one-shot dialogue and the open investigations", async () => {
    mountPane();
    await screen.findByText(/No agents yet/);
    fireEvent.click(screen.getByLabelText("New agent"));
    fireEvent.click(screen.getByText("Is the gate safe?"));
    expect(comp().tabs.map((t) => t.id)).toContain("agent:thread:inv-live");
    fireEvent.click(screen.getByLabelText("New agent"));
    fireEvent.click(screen.getByText("One-shot dialogue"));
    expect(comp().tabs.map((t) => t.kind)).toContain("dialogue");
  });
});

// ─── the key rows ────────────────────────────────────────────────────────

describe("the companion tab keys (prefix n/p + chord twins)", () => {
  it("prefix n/p cycle the companion's tabs (wrap) when the pane is visible", async () => {
    openThreadTab("inv-live");
    openThreadTab("inv-done");
    mountInsetLayout();
    await screen.findAllByText("What breaks on retry?");
    key(document.body, "ctrl+b");
    key(document.body, "n");
    expect(comp().activeTabId).toBe("agent:thread:inv-live");
    key(document.body, "ctrl+b");
    key(document.body, "n");
    expect(comp().activeTabId).toBe("agent:thread:inv-done");
    key(document.body, "ctrl+b");
    key(document.body, "p");
    expect(comp().activeTabId).toBe("agent:thread:inv-live");
  });

  it("the chord twins ctrl+alt+] / ctrl+alt+[ cycle too", () => {
    openThreadTab("inv-live");
    openThreadTab("inv-done");
    mountInsetLayout();
    key(document.body, "ctrl+alt+]");
    expect(comp().activeTabId).toBe("agent:thread:inv-live");
    key(document.body, "ctrl+alt+[");
    expect(comp().activeTabId).toBe("agent:thread:inv-done");
  });

  it("in the docked preset WITHOUT the companion panel the keys are an honest no-op", () => {
    // Seed tabs directly so only visibility (not tab absence) is tested.
    act(() => {
      comp().openAgentTab({ kind: "research-thread", investigationId: "inv-live" });
      ws().close(COMPANION_PANEL_ID);
    });
    const before = comp().activeTabId;
    key(document.body, "ctrl+b");
    key(document.body, "n");
    expect(comp().activeTabId).toBe(before);
  });

  it("none of the tab keys arms or fires from a text field", () => {
    openThreadTab("inv-live");
    openThreadTab("inv-done");
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    for (const k of ["n", "p"]) {
      key(input, "ctrl+b");
      expect(prefixState.isArmed(), `prefix must not arm in text (for ${k})`).toBe(false);
      const e = key(input, k);
      expect(e.defaultPrevented, `'${k}' must reach the field as a character`).toBe(false);
    }
    expect(comp().activeTabId).toBe("agent:thread:inv-done");
  });
});

// ─── the cross-pane seam (C4→C5) ─────────────────────────────────────────

describe("openDocumentInLeftPane — the seam PR 3 re-handles", () => {
  it("the bridge opens/focuses the reader window with the stable per-document id", async () => {
    openThreadTab("inv-live", "doc-9");
    mountPane();
    const btn = await screen.findByText("Open source document →");
    fireEvent.click(btn);
    const win = useWindows.getState().windows["win:reader:doc-9"];
    expect(win).toBeTruthy();
    expect(useWindows.getState().focusedId).toBe("win:reader:doc-9");
  });

  it("the contract is the event shape: a swapped handler receives it verbatim", () => {
    const seen: unknown[] = [];
    setOpenDocumentHandler((req) => seen.push(req));
    openDocumentInLeftPane("doc-9", { from: "companion", investigationId: "inv-live", agentTabId: "agent:thread:inv-live" });
    expect(seen).toEqual([
      { documentId: "doc-9", origin: { from: "companion", investigationId: "inv-live", agentTabId: "agent:thread:inv-live" } },
    ]);
    // The bridge was replaced, so no reader window opened.
    expect(useWindows.getState().windows["win:reader:doc-9"]).toBeUndefined();
  });

  it("an empty document identity is an honest no-op", () => {
    openDocumentInLeftPane("", { from: "companion" });
    expect(useWindows.getState().order).toHaveLength(0);
  });
});

// ─── the dialogue agent (one-shot, never a chat) ─────────────────────────

describe("the dialogue surface", () => {
  it("a question gets a labelled one-shot reply through the shared wire", async () => {
    act(() => {
      comp().openAgentTab({ kind: "dialogue" });
    });
    mountPane();
    fireEvent.change(screen.getByLabelText("Ask the thought partner"), { target: { value: "Stress-test this plan" } });
    fireEvent.click(screen.getByText("Ask"));
    await screen.findByText("a considered reply");
    expect(document.querySelector("blockquote")!.textContent).toContain("Stress-test this plan");
    expect(screen.getByText("AI reply")).toBeTruthy();
    expect(screen.getByTestId("dialogue-shape").textContent).toBe("CHALLENGE");
    expect(screen.getByText(/One-shot reply \(not a chat\)/)).toBeTruthy();
  });

  it("a 503 (no provider) surfaces the honest failure state, never a fabricated reply", async () => {
    tpStatus = 503;
    act(() => {
      comp().openAgentTab({ kind: "dialogue" });
    });
    mountPane();
    fireEvent.change(screen.getByLabelText("Ask the thought partner"), { target: { value: "Anything" } });
    fireEvent.click(screen.getByText("Ask"));
    await screen.findByText(/Couldn’t get a reply/);
    expect(screen.queryByText("a considered reply")).toBeNull();
  });
});
