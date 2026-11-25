/**
 * investigationCenter.seen.test.tsx — the /inv/:id pane and the shared
 * seen map (workspace/seen.ts) that the SPR-10 agent monitor derives "done"
 * from (herdr R17: "done" persists until the pane is focused; reading it
 * does not clear it). Navigating to /inv/X is an explicit act and marks
 * seen. A status change or a window focus re-marks only while the
 * operator is watching: the document focused and visible, and the pane
 * with the focus the centre, not the companion (ffx-kpa-spr-10 critic
 * MAJOR, ResearchWorkstation/index.tsx:146-152).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, renderHook } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { forwardRef, type ReactNode } from "react";

const inv = vi.hoisted(() => ({ status: "in_progress" as string, completedAt: null as string | null }));
vi.mock("../../hooks/useInvestigation", () => ({
  useInvestigation: (id: string) => ({ id, status: inv.status, question: "q", events: [], terminalPayload: null, costTotal: 0, completedAt: inv.completedAt, streamStatus: "open", reconnects: 0, sourcePolicy: [] }),
}));
vi.mock("../../workspace/PanelHost", () => ({ PanelHost: ({ children }: { children: ReactNode }) => <>{children}</> }));
vi.mock("../../shell/GlassSurface", () => ({ default: forwardRef<HTMLDivElement, { children: ReactNode }>((p, r) => <div ref={r}>{p.children}</div>) }));
vi.mock("../../components/CapacitySoftWarnBanner", () => ({ default: () => null }));
for (const m of ["HighlightToolbar", "DistillView", "MasterMdViewer", "NotesPanel", "PasteIngest", "StartResearch", "SuggestedResearch", "DiligenceRail", "ThinkingStream"]) void m;
vi.mock("./HighlightToolbar", () => ({ default: () => null }));
vi.mock("./DistillView", () => ({ default: () => null }));
vi.mock("./MasterMdViewer", () => ({ default: () => null }));
vi.mock("./NotesPanel", () => ({ default: () => null }));
vi.mock("./PasteIngest", () => ({ default: () => null }));
vi.mock("./StartResearch", () => ({ default: () => null }));
vi.mock("./SuggestedResearch", () => ({ default: () => null }));
vi.mock("./DiligenceRail", () => ({ default: () => null }));
vi.mock("./ThinkingStream", () => ({ default: () => null }));

import ResearchWorkstation from "./index";
import { composePreBackendTree } from "../../workspace/contracts/adapters/preBackend";
import * as treeStore from "../../workspace/contracts/treeStore";
import { fixtureInputs, summary, tab } from "../../workspace/contracts/fixtures.test.helpers";
import { useCompanion } from "../../workspace/companionStore";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import { lastSeenAt } from "../../workspace/seen";
import { useAgentAttention, useAgentStatusStore } from "../../workspace/agents/agentStatusStore";
import { DEBOUNCE } from "../../workspace/agents/debounce";

const clock = { now: () => Date.now(), setTimeout: (fn: () => void, ms: number) => window.setTimeout(fn, ms), clearTimeout: (h: unknown) => window.clearTimeout(h as number) };
const T0 = 1_800_000_000_000;

function publish() {
  const tree = composePreBackendTree(fixtureInputs({
    investigations: [summary("X", { status: "in_progress", completed_at: null })],
    companionTabs: [tab("research-thread", { investigationId: "X", title: "X" })],
  }));
  act(() => treeStore.publishTree(tree, new Date(Date.now()).toISOString()));
}
let completedIso = "";
function observe(status: "in_progress" | "completed") {
  act(() => useAgentStatusStore.getState().observe([summary("X", { status, completed_at: status === "in_progress" ? null : completedIso })], new Set(["X"]), Date.now()));
  act(() => { vi.advanceTimersByTime(DEBOUNCE.confirmations * DEBOUNCE.intervalMs); });
}

const route = () => (
  <MemoryRouter initialEntries={["/inv/X"]}><Routes><Route path="/inv/:investigationId" element={<ResearchWorkstation />} /></Routes></MemoryRouter>
);

let hasFocus: ReturnType<typeof vi.spyOn>;
let visibility = "visible";
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(T0);
  inv.status = "in_progress"; inv.completedAt = null;
  visibility = "visible";
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => visibility });
  window.localStorage.removeItem("antiek:last_seen:v1");
  useCompanion.getState().reset();
  useWorkspace.getState().reset();
  useWorkspace.getState().setLayoutPreset("omarchy-inset");
  useAgentStatusStore.getState().reset();
  useAgentStatusStore.getState().start(clock);
  hasFocus = vi.spyOn(document, "hasFocus").mockReturnValue(false);
  publish();
});
afterEach(() => {
  cleanup();
  hasFocus.mockRestore();
  useAgentStatusStore.getState().stop();
  treeStore.markTreeUnfed();
  useCompanion.getState().reset();
  useWorkspace.getState().reset();
  vi.useRealTimers();
});

/** Mount /inv/X (navigation marks seen), let the grace and a minute pass,
 *  then finish X in the WS-fed hook and in the list poll. Returns the
 *  attention hook and the mount's seen stamp. */
function mountThenFinish() {
  const hook = renderHook(() => useAgentAttention("X"));
  const view = render(route());
  observe("in_progress");
  act(() => { vi.advanceTimersByTime(DEBOUNCE.startupGraceMs + 60_000); });
  const seenAtMount = lastSeenAt("X");
  expect(seenAtMount).not.toBeNull();
  completedIso = new Date(Date.now()).toISOString();
  act(() => { vi.advanceTimersByTime(5); });
  inv.status = "completed"; inv.completedAt = completedIso;
  view.rerender(route());
  observe("completed");
  return { hook, seenAtMount: seenAtMount! };
}

describe("/inv/:id and the seen map (herdr R17)", () => {
  it("navigating to /inv/X marks it seen (an explicit act), focus or not", () => {
    render(route());
    expect(lastSeenAt("X")).not.toBeNull();
  });

  it("the window unfocused and the document hidden: X completing on screen does NOT re-mark, so the monitor shows 'done'", () => {
    visibility = "hidden";
    const { hook, seenAtMount } = mountThenFinish();
    expect(lastSeenAt("X")).toBe(seenAtMount);
    expect(hook.result.current.state).toBe("done");
  });

  it("the window unfocused, the document visible: the completion still does not re-mark (nobody focused anything)", () => {
    const { hook, seenAtMount } = mountThenFinish();
    expect(lastSeenAt("X")).toBe(seenAtMount);
    expect(hook.result.current.state).toBe("done");
  });

  it("a window 'focus' event that leaves document.hasFocus() false is not a pane focus: 'done' persists", () => {
    const { hook, seenAtMount } = mountThenFinish();
    act(() => { vi.advanceTimersByTime(10); window.dispatchEvent(new Event("focus")); });
    expect(lastSeenAt("X")).toBe(seenAtMount);
    expect(hook.result.current.state).toBe("done");
  });

  it("focused and visible but the companion (right pane) holds the focus: the centre completing is not seen; 'done' persists", () => {
    hasFocus.mockReturnValue(true);
    useWorkspace.getState().setFocusedPane("right");
    const { hook, seenAtMount } = mountThenFinish();
    expect(lastSeenAt("X")).toBe(seenAtMount);
    expect(hook.result.current.state).toBe("done");
    act(() => { vi.advanceTimersByTime(10); window.dispatchEvent(new Event("focus")); });
    expect(hook.result.current.state).toBe("done");
  });

  it("control: focused, visible, the centre pane with the focus: X completing while watched is seen completing, so it reads 'idle'", () => {
    hasFocus.mockReturnValue(true);
    const { hook, seenAtMount } = mountThenFinish();
    expect(lastSeenAt("X")! > seenAtMount).toBe(true);
    expect(hook.result.current.state).toBe("idle");
  });

  it("control: regaining window focus with the centre pane focused and the document visible marks seen: 'done' → 'idle'", () => {
    const { hook } = mountThenFinish();
    expect(hook.result.current.state).toBe("done");
    hasFocus.mockReturnValue(true);
    act(() => { vi.advanceTimersByTime(10); window.dispatchEvent(new Event("focus")); });
    expect(hook.result.current.state).toBe("idle");
  });
});
