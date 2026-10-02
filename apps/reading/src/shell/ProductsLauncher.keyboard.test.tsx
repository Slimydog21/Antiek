import { useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import { ProductsLauncher } from "./ProductsLauncher";
import { MAX_WINDOWS, useWindows } from "../workspace/windowsStore";

beforeEach(() => useWindows.getState().reset());
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function Host() {
  const [open, setOpen] = useState(true);
  const location = useLocation();
  return <>
    <output aria-label="Current route">{location.pathname}{location.search}{location.hash}</output>
    <button onClick={() => setOpen(true)}>Reopen launcher</button>
    <ProductsLauncher open={open} onClose={() => setOpen(false)} />
  </>;
}
function mount() {
  return render(<MemoryRouter initialEntries={["/library?project=opaque%2Fid#passage"]}><Host /></MemoryRouter>);
}
function filter(query: string) {
  const input = screen.getByPlaceholderText("Filter…");
  fireEvent.change(input, { target: { value: query } });
  return input;
}
function route() { return screen.getByLabelText("Current route").textContent; }
const originalRoute = "/library?project=opaque%2Fid#passage";

describe("ProductsLauncher actual keyboard inventory", () => {
  it("starts on the visible Home action and Enter uses its pointer destination", () => {
    mount();
    fireEvent.keyDown(filter(""), { key: "Enter" });
    expect(route()).toBe("/home");
    expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();
  });

  it("places the first product header immediately after Home in keyboard order", () => {
    mount(); const input = filter("");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(useWindows.getState().windows["win:subaction:research"]?.payload).toEqual({ workflow: "research", __windowId: "win:subaction:research" });
    expect(route()).toBe(originalRoute);
  });

  it("matches product taglines and opens the real stable product window", () => {
    mount();
    fireEvent.keyDown(filter("gather their voices"), { key: "Enter" });
    expect(useWindows.getState().windows["win:subaction:speak"]?.kind).toBe("subaction");
    expect(route()).toBe(originalRoute);
  });

  it("uses product label search before its deep modes and can move back to Home", () => {
    mount(); const input = filter("Write");
    fireEvent.keyDown(input, { key: "ArrowUp" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(route()).toBe("/home");
  });

  it("selects a matching run label and keeps real taxonomy routing", () => {
    mount(); fireEvent.keyDown(filter("Billing & usage"), { key: "Enter" });
    expect(route()).toBe("/billing");
  });

  it("shows shared param-only inventory disabled instead of a fake destination", () => {
    mount(); const input = filter("Explain provenance");
    const row = screen.getByRole("button", { name: /Explain provenance/ });
    expect(row).toHaveProperty("disabled", true);
    fireEvent.click(row);
    fireEvent.keyDown(input, { key: "Enter" });
    expect(route()).toBe(originalRoute);
    expect(screen.getByRole("dialog", { name: "More" })).toBeTruthy();
  });

  it.each([{ ctrlKey: true }, { metaKey: true }, { altKey: true }, { shiftKey: true }, { isComposing: true }])(
    "preserves modified/composing Enter for %j", (modifiers) => {
      mount(); const input = filter("Billing");
      expect(fireEvent.keyDown(input, { key: "Enter", ...modifiers })).toBe(true);
      expect(route()).toBe(originalRoute);
      expect(screen.getByRole("dialog", { name: "More" })).toBeTruthy();
    },
  );

  it("refuses AltGraph-only and already consumed commands", () => {
    mount(); const input = filter("Billing");
    const altGraph = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    Object.defineProperty(altGraph, "getModifierState", { value: (key: string) => key === "AltGraph" });
    fireEvent(input, altGraph);
    const consumed = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    consumed.preventDefault(); fireEvent(input, consumed);
    expect(route()).toBe(originalRoute);
  });

  it("keeps text/Space and native row Enter outside the filter command handler", () => {
    mount(); const input = filter("Billing");
    expect(fireEvent.keyDown(input, { key: " " })).toBe(true);
    expect(fireEvent.keyDown(input, { key: "x" })).toBe(true);
    const button = screen.getByRole("button", { name: "Billing & usage" });
    button.focus();
    expect(fireEvent.keyDown(button, { key: "Enter" })).toBe(true);
    expect(route()).toBe(originalRoute);
    fireEvent.click(button); expect(route()).toBe("/billing");
  });

  it("has one visible active row and a useful selected-action description", () => {
    const { baseElement } = mount(); const input = filter("");
    act(() => { fireEvent.keyDown(input, { key: "ArrowDown" }); fireEvent.keyDown(input, { key: "ArrowDown", repeat: true }); });
    const rows = baseElement.querySelectorAll('[data-launcher-active="true"]');
    expect(rows.length).toBe(1);
    expect(rows[0].textContent).toContain("Research workstation");
    expect(input.getAttribute("aria-describedby")).toBeTruthy();
    const description = document.getElementById(input.getAttribute("aria-describedby") ?? "");
    expect(description?.textContent).toContain("Research workstation");
  });

  it("scrolls the actual selected row into view after arrows and filtering", () => {
    const previous = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollIntoView");
    const scroll = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: scroll });
    try {
      mount();
      const input = filter("");
      fireEvent.keyDown(input, { key: "ArrowDown" });
      expect(scroll.mock.contexts.at(-1)).toBe(screen.getByRole("button", { name: "Open Research workflow in a window" }));
      expect(scroll).toHaveBeenLastCalledWith({ block: "nearest" });
      filter("Billing & usage");
      expect(scroll.mock.contexts.at(-1)).toBe(screen.getByRole("button", { name: "Billing & usage" }));
    } finally {
      if (previous) Object.defineProperty(HTMLElement.prototype, "scrollIntoView", previous);
      else Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
    }
  });

  it("reuses the same product identity on repeated keyboard and pointer entry", () => {
    mount(); fireEvent.keyDown(filter("gather their voices"), { key: "Enter" });
    const id = "win:subaction:speak";
    expect(useWindows.getState().order).toEqual([id]);
    fireEvent.click(screen.getByRole("button", { name: "Reopen launcher" }));
    fireEvent.click(screen.getByRole("button", { name: "Open Speak workflow in a window" }));
    expect(useWindows.getState().order).toEqual([id]);
    expect(useWindows.getState().focusedId).toBe(id);
  });

  it("uses the actual index for an operable shared detail and workflow door fallback", () => {
    mount();
    fireEvent.keyDown(filter("Skill rule detail"), { key: "Enter" });
    expect(route()).toBe("/skill-rules");
    fireEvent.click(screen.getByRole("button", { name: "Reopen launcher" }));
    fireEvent.click(screen.getByRole("button", { name: "Reader" }));
    expect(route()).toBe("/library");
  });

  it("reuses a requested existing product even when eight windows are open", () => {
    const id = "win:subaction:write";
    useWindows.getState().open("subaction", { workflow: "write", __windowId: id }, { id });
    for (let i = 1; i < MAX_WINDOWS; i++) useWindows.getState().open("stats", {}, { id: `existing-${i}` });
    mount();
    fireEvent.keyDown(filter("Write"), { key: "Enter" });
    expect(useWindows.getState().focusedId).toBe(id);
    expect(useWindows.getState().order.length).toBe(MAX_WINDOWS);
    expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();
    expect(route()).toBe(originalRoute);
  });

  it.each([8, 14])("opens the requested product after %d existing windows without replacing them", (count) => {
    for (let i = 0; i < count; i++) useWindows.getState().open("stats", {}, { id: `existing-${i}` });
    const before = useWindows.getState();
    mount(); fireEvent.keyDown(filter("Write"), { key: "Enter" });
    const id = "win:subaction:write";
    const after = useWindows.getState();
    expect(after.windows[id]?.payload).toEqual({ workflow: "write", __windowId: id });
    expect(after.order).toEqual([...before.order, id]);
    expect(after.cycleOrder).toEqual([...before.cycleOrder, id]);
    expect(after.focusedId).toBe(id);
    for (const peer of before.order) expect(after.windows[peer]).toBe(before.windows[peer]);
    expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();
    expect(route()).toBe(originalRoute);
  });

  it.each([8, 14])("opens the requested inline reference after %d existing windows", (count) => {
    for (let i = 0; i < count; i++) useWindows.getState().open("stats", {}, { id: `existing-${i}` });
    const before = useWindows.getState();
    mount(); filter("Substrate stats");
    fireEvent.click(screen.getByRole("button", { name: "Open Substrate stats in a window" }));
    const id = "win:stats";
    const after = useWindows.getState();
    expect(after.windows[id]?.kind).toBe("stats");
    expect(after.order).toEqual([...before.order, id]);
    expect(after.cycleOrder).toEqual([...before.cycleOrder, id]);
    expect(after.focusedId).toBe(id);
    for (const peer of before.order) expect(after.windows[peer]).toBe(before.windows[peer]);
    expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();
    expect(route()).toBe(originalRoute);
  });

  it("still refuses a returned identity different from the requested product", () => {
    for (let i = 0; i < 8; i++) useWindows.getState().open("stats", {}, { id: `existing-${i}` });
    const before = useWindows.getState();
    const open = vi.spyOn(before, "open").mockReturnValue("existing-0");
    mount(); fireEvent.click(screen.getByRole("button", { name: "Open Write workflow in a window" }));
    expect(open).toHaveBeenCalledTimes(1);
    expect(useWindows.getState().order).toEqual(before.order);
    expect(useWindows.getState().windows["win:subaction:write"]).toBeUndefined();
    expect(screen.getByRole("dialog", { name: "More" })).toBeTruthy();
    expect(screen.getByRole("dialog", { name: "More" }).querySelector('[role="status"]')?.textContent).toMatch(/limit|Close a window/i);
    expect(route()).toBe(originalRoute);
  });
});
