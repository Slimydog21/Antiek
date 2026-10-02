import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { LemonModal } from "../components/lemon/LemonModal";
import { PanelHost } from "./PanelHost";
import { useWorkspaceHydration } from "./useWorkspaceHydration";
import { project, writeScope } from "./persistence";
import { panelFocusId } from "./panelFocusId";
import { installShortcuts } from "./shortcuts";
import { PanelLayoutPanel } from "./PanelLayoutPanel";
import { disablePersistence, getHydrationGeneration, markHydrated, useWorkspace } from "./WorkspaceStore";

vi.mock("./PanelRegistry", () => ({ PanelRegistry: { Notes: () => <input aria-label="Hosted draft" defaultValue="Kept draft" /> } }));
const state = () => useWorkspace.getState();
beforeEach(() => {
  disablePersistence(); state().reset();
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
  vi.stubGlobal("innerWidth", 1000); vi.stubGlobal("innerHeight", 800);
});
afterEach(() => { cleanup(); disablePersistence(); vi.restoreAllMocks(); vi.unstubAllGlobals(); localStorage.clear(); });
function title(id: string): HTMLElement {
  const span = within(screen.getByRole("region", { name: id })).getByText(id);
  if (!span.parentElement) throw new Error("No actual title strip");
  return span.parentElement;
}
function mount(ids = ["a"]) {
  for (const id of ids) state().open("Notes", {}, { id, title: id, mode: "floating" });
  return render(<>{ids.map((id) => <PanelLayoutPanel key={id} id={id} />)}</>);
}

let uninstall = () => {};
beforeEach(() => { uninstall = installShortcuts(vi.fn()); });
afterEach(() => { uninstall(); });
function cycle(key = "[") {
  const event = new KeyboardEvent("keydown", { key, metaKey: true, bubbles: true, cancelable: true });
  act(() => { (document.activeElement ?? document).dispatchEvent(event); });
  return event;
}
describe("actual panel traversal", () => {
  it("moves real DOM focus to the previous rendered title", () => {
    mount(["a", "b", "c"]); const event = cycle();
    expect(state().focusedPanelId).toBe("b"); expect(document.activeElement).toBe(title("b"));
    expect(event.defaultPrevented).toBe(true);
  });
  it("visits all floating members in reverse despite restacking", () => {
    mount(["a", "b", "c"]);
    cycle(); expect(state().focusedPanelId).toBe("b");
    cycle(); expect(state().focusedPanelId).toBe("a");
    cycle(); expect(state().focusedPanelId).toBe("c");
  });
});


describe("stable ring, actual admission and hydration", () => {
  it("cycles forward and repeated same-batch backward with one z bump per changed focus", () => {
    mount(["a", "b", "c"]); const z = state().zCounter;
    act(() => { cycle(); cycle(); });
    expect(state().focusedPanelId).toBe("a"); expect(document.activeElement).toBe(title("a")); expect(state().zCounter).toBe(z + 2);
    for (const id of ["b", "c", "a"]) { const before = state().zCounter; cycle("]"); expect(state().focusedPanelId).toBe(id); expect(document.activeElement).toBe(title(id)); expect(state().zCounter).toBe(before + 1); }
    expect(state().panelCycleOrder).toEqual(["a", "b", "c"]);
  });
  it("uses first/last when no cursor and can focus one real title without redundant z", () => {
    mount(["a", "b", "c"]); act(() => { useWorkspace.setState({ focusedPanelId: null }); });
    cycle("]"); expect(document.activeElement).toBe(title("a"));
    act(() => { useWorkspace.setState({ focusedPanelId: null }); }); cycle(); expect(document.activeElement).toBe(title("c"));
    act(() => { state().close("a"); state().close("b"); }); const before = state().zCounter;
    expect(cycle().defaultPrevented).toBe(true); expect(state().zCounter).toBe(before);
  });
  it("keeps membership stable across focus and dock changes; popout return appends", () => {
    mount(["a", "b", "c"]); act(() => { state().focus("a"); state().open("Notes", {}, { id: "b" }); state().setMode("b", "docked-left"); state().setMode("b", "floating"); });
    expect(state().panelCycleOrder).toEqual(["a", "b", "c"]);
    act(() => { state().setMode("b", "popout"); }); expect(state().panelCycleOrder).toEqual(["a", "c"]); expect(screen.queryByRole("region", { name: "b" })).toBeNull();
    act(() => { state().setMode("b", "floating"); }); expect(state().panelCycleOrder).toEqual(["a", "c", "b"]);
    act(() => { state().close("c"); }); expect(state().panelCycleOrder).toEqual(["a", "b"]);
    act(() => { state().reset(); }); expect(state().panelCycleOrder).toEqual([]); expect(cycle().defaultPrevented).toBe(false);
  });
  it.each(["hidden", "aria-hidden", "inert"])("skips destinations under %s", (attribute) => {
    mount(["a", "b", "c"]); screen.getByRole("region", { name: "b" }).setAttribute(attribute, attribute === "aria-hidden" ? "true" : "");
    cycle(); expect(state().focusedPanelId).toBe("a"); expect(document.activeElement).toBe(title("a"));
  });
  it("skips missing and mismatched owned-title markers without inventing DOM", () => {
    const view = mount(["a", "b", "c"]);
    view.rerender(<><PanelLayoutPanel id="a" /><PanelLayoutPanel id="c" /></>);
    cycle(); expect(state().focusedPanelId).toBe("a");
    title("c").setAttribute("data-panel-title", "foreign"); const before = state().zCounter;
    cycle(); expect(state().focusedPanelId).toBe("a"); expect(state().zCounter).toBe(before);
  });
  it("does not mutate focus or claim a key when no target renders or actual focus fails", () => {
    state().open("Notes", {}, { id: "missing", mode: "floating" }); const before = state();
    expect(cycle().defaultPrevented).toBe(false); expect(state()).toBe(before);
    act(() => { state().reset(); }); mount(); const strip = title("a");
    vi.spyOn(strip, "focus").mockImplementation(() => {}); const current = state();
    expect(cycle().defaultPrevented).toBe(false); expect(state()).toBe(current);
  });
  it("leaves focused transient controls and programmatically refocused current title with their dropdown", () => {
    mount(["a", "b", "c"]); const region = screen.getByRole("region", { name: "c" });
    fireEvent.click(within(region).getByRole("button", { name: "Panel actions" }));
    const item = within(region).getByRole("menuitem", { name: /Dock left/ }); act(() => { item.focus(); });
    const before = state(); expect(cycle().defaultPrevented).toBe(false); expect(state()).toBe(before);
    act(() => { title("c").focus(); }); expect(cycle().defaultPrevented).toBe(false); expect(state()).toBe(before);
    act(() => { title("b").focus(); }); expect(cycle().defaultPrevented).toBe(true); expect(state().focusedPanelId).toBe("a");
  });
  it("respects top modal, input text and hidden current panel ownership", () => {
    mount(["a", "b"]); const input = within(screen.getByRole("region", { name: "b" })).getByRole("textbox"); act(() => { input.focus(); });
    const before = state(); expect(cycle().defaultPrevented).toBe(false); expect(state()).toBe(before);
    render(<LemonModal open title="Modal" onClose={() => {}}><input /></LemonModal>); act(() => { title("b").focus(); });
    expect(cycle().defaultPrevented).toBe(false); expect(state()).toBe(before);
  });
  it("rebuilds only live visible own members at the actual hydration marker without persisting the ring", () => {
    mount(["a", "b", "c"]); act(() => { state().setMode("b", "popout"); }); const generation = getHydrationGeneration();
    act(() => { useWorkspace.setState({ dockLeftIds: ["c", "toString", "b"], floatingIds: ["a", "c"], dockBottomIds: ["missing"], dockRightIds: ["a"] }); markHydrated(); });
    expect(state().panelCycleOrder).toEqual(["c", "a"]); expect(getHydrationGeneration()).toBe(generation + 1);
    expect(project(state())).not.toHaveProperty("panelCycleOrder");
  });
  it("hydrates cold saved panels before passive starters, then carries only pinned panels to the next route", () => {
    localStorage.clear();
    state().open("Notes", {}, { id: "saved", title: "saved", mode: "docked-right" });
    writeScope({ kind: "route", route: "/one" }, project(state())); state().reset();
    function HydratedHost() {
      useWorkspaceHydration(); const navigate = useNavigate();
      const panels = useWorkspace((s) => s.panels);
      return <PanelHost starters={[{ kind: "Notes", mode: "docked-left", title: "starter", id: "starter" }]}>
        <button onClick={() => navigate("/two")}>Next route</button>
        {Object.keys(panels).map((id) => <PanelLayoutPanel key={id} id={id} />)}
      </PanelHost>;
    }
    render(<MemoryRouter initialEntries={["/one"]}><HydratedHost /></MemoryRouter>);
    expect(state().panelCycleOrder).toEqual(["saved", "starter"]);
    expect(document.getElementById(panelFocusId("saved"))).toBe(title("saved"));
    act(() => { state().pin("saved"); state().open("Notes", {}, { id: "discard", title: "discard" }); });
    fireEvent.click(screen.getByRole("button", { name: "Next route" }));
    expect(state().panelCycleOrder).toEqual(["saved"]);
    expect(state().panels.discard).toBeUndefined(); expect(title("saved").isConnected).toBe(true);
    expect(cycle("]").defaultPrevented).toBe(true); expect(document.activeElement).toBe(title("saved"));
  });
});


describe("hydration generation publication", () => {
  it("publishes the new generation with the introduced ring notification", () => {
    mount(["a", "b"]); const before = getHydrationGeneration();
    const observed: number[] = [];
    const unsubscribe = useWorkspace.subscribe((current, previous) => {
      if (current.panelCycleOrder !== previous.panelCycleOrder) observed.push(getHydrationGeneration());
    });
    try { act(() => { markHydrated(); }); } finally { unsubscribe(); }
    expect(observed).toEqual([before + 1]);
  });
  it("marks real route hydration before old PanelHost cleanup can close the restored same-ID panel", () => {
    localStorage.clear();
    state().open("Notes", {}, { id: "starter", title: "Restored starter", mode: "docked-right" });
    writeScope({ kind: "investigation", id: "two" }, project(state())); state().reset();
    function Starter() {
      const panels = useWorkspace((s) => s.panels);
      return <PanelHost starters={[{ kind: "Notes", id: "starter", title: "Initial starter", mode: "docked-left" }]}>
        {Object.keys(panels).map((id) => <PanelLayoutPanel key={id} id={id} />)}
      </PanelHost>;
    }
    function Shell() {
      useWorkspaceHydration(); const navigate = useNavigate();
      return <><button onClick={() => navigate("/inv/two")}>Restore next investigation</button>
        <Routes><Route path="/inv/:investigationId" element={<Starter />} /></Routes></>;
    }
    render(<MemoryRouter initialEntries={["/inv/one"]}><Shell /></MemoryRouter>);
    expect(state().panels.starter.title).toBe("Initial starter"); const before = getHydrationGeneration();
    const observed: number[] = [];
    const unsubscribe = useWorkspace.subscribe((current, previous) => {
      if (current.panelCycleOrder !== previous.panelCycleOrder) observed.push(getHydrationGeneration());
    });
    try { fireEvent.click(screen.getByRole("button", { name: "Restore next investigation" })); } finally { unsubscribe(); }
    expect(observed[0]).toBe(before + 1);
    expect(state().panels.starter.title).toBe("Restored starter");
    expect(state().panels.starter.mode).toBe("docked-right"); expect(state().panelCycleOrder).toEqual(["starter"]);
    expect(screen.getByRole("region", { name: "Restored starter" })).toBeTruthy();
  });
});
