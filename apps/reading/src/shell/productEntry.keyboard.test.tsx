import { useEffect } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";

import { NavRail } from "./NavRail";
import { WindowsLayer } from "../components/windows/WindowsLayer";
import { WorkspaceWindow } from "../components/windows/WorkspaceWindow";
import { useWindows } from "../workspace/windowsStore";
import { installShortcuts } from "../workspace/shortcuts";
import { setFeatureFlag } from "../lib/featureFlags";
import { currentPlatform } from "../components/hotkeys/keymap";
import { emitProductActivate } from "../components/hotkeys/bindings";

// Only external research-list retrieval is replaced. The router, menu,
// dispatcher, lazy window renderer, focus effects and window store are real.
vi.mock("../hooks/useInvestigationList", () => ({
  useInvestigationList: () => ({ investigations: [] }),
}));

function Journey({ orientation = "bottom" }: { orientation?: "bottom" | "left" }) {
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => installShortcuts(navigate), [navigate]);
  return <>
    <output data-testid="journey-url">{location.pathname + location.search + location.hash}</output>
    <input aria-label="Underlying draft" defaultValue="Keep this draft" />
    <NavRail orientation={orientation} />
    <WindowsLayer />
  </>;
}

const originalUrl = "/write/deliverable-id?m=writing#section";
beforeEach(() => {
  useWindows.getState().reset();
  localStorage.clear();
  // These journeys exercise the packet's launcher build (the More → type →
  // Enter path with the improved default selection), which rides pane.flow.
  setFeatureFlag("pane.flow", true);
  vi.stubGlobal("innerWidth", 1440);
  vi.stubGlobal("innerHeight", 900);
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function mount(orientation: "bottom" | "left" = "bottom") {
  return render(<MemoryRouter initialEntries={[originalUrl]}><Journey orientation={orientation} /></MemoryRouter>);
}
function more() { return screen.getByRole("button", { name: "More" }); }
function moreKey(target: Element) {
  return fireEvent.keyDown(target, {
    key: "i", code: "KeyI",
    metaKey: currentPlatform() === "mac", ctrlKey: currentPlatform() !== "mac",
  });
}
function filter() {
  const input = within(screen.getByRole("dialog", { name: "More" })).getByPlaceholderText("Filter…");
  if (!(input instanceof HTMLInputElement)) throw new Error("Missing real launcher filter");
  return input;
}
function sameScene() {
  expect(screen.getByTestId("journey-url").textContent).toBe(originalUrl);
  expect(screen.getByRole("textbox", { name: "Underlying draft" })).toHaveProperty("value", "Keep this draft");
}
async function readWindow() {
  const dialog = await screen.findByRole("dialog", { name: "Read" });
  await within(dialog).findByRole("button", { name: "Back to mothership" });
  return dialog;
}

describe("global mothership to product window keyboard journey", () => {
  it("Back closes only its actual product window and preserves the full scene", async () => {
    mount();
    const opener = more(); opener.focus();
    act(() => { useWindows.getState().open("subaction", { workflow: "read", __windowId: "win:subaction:read" }, { id: "win:subaction:read", title: "Read" }); });
    const dialog = await readWindow();
    fireEvent.click(within(dialog).getByRole("button", { name: "Back to mothership" }));
    expect(useWindows.getState().windows["win:subaction:read"]).toBeUndefined();
    await waitFor(() => expect(document.activeElement).toBe(opener));
    sameScene();
  });

  it.each(["bottom", "left"] as const)("the real More binding enters Read and returns to the %s rail", async (orientation) => {
    mount(orientation);
    const opener = more(); opener.focus();
    expect(moreKey(opener)).toBe(false);
    expect(screen.getAllByRole("dialog", { name: "More" })).toHaveLength(1);
    const input = filter(); expect(document.activeElement).toBe(input);
    fireEvent.change(input, { target: { value: "Read" } });
    fireEvent.keyDown(input, { key: "Enter" });
    const dialog = await readWindow();
    expect(useWindows.getState().order).toEqual(["win:subaction:read"]);
    await waitFor(() => expect(document.activeElement).toBe(dialog));
    sameScene();
    const bar = dialog.querySelector("[data-window-titlebar]");
    if (!(bar instanceof HTMLElement)) throw new Error("Missing real titlebar");
    const beforeX = useWindows.getState().windows["win:subaction:read"].rect.x;
    bar.focus(); fireEvent.keyDown(bar, { key: "ArrowRight" });
    expect(useWindows.getState().windows["win:subaction:read"].rect.x).toBe(beforeX + 24);
    const back = within(dialog).getByRole("button", { name: "Back to mothership" });
    back.focus();
    expect(fireEvent.keyDown(back, { key: "Enter" })).toBe(true);
    // jsdom does not perform native Enter activation; click is explicit.
    fireEvent.click(back);
    await waitFor(() => expect(document.activeElement).toBe(opener));
    sameScene();
  });

  it("the compact rail opens one launcher and another product event leaves it closed", () => {
    vi.stubGlobal("innerWidth", 390); mount();
    act(() => emitProductActivate({ productId: "read", source: "hotkey" }));
    expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();
    const opener = more(); opener.focus(); moreKey(opener);
    expect(screen.getAllByRole("dialog", { name: "More" })).toHaveLength(1);
    sameScene();
  });

  it("More works from the collapsed mobile rail without expanding it", () => {
    vi.stubGlobal("innerWidth", 390); mount("left");
    fireEvent.click(screen.getByRole("button", { name: "Close navigation" }));
    const opener = screen.getByRole("button", { name: "Open navigation" }); opener.focus();
    expect(moreKey(opener)).toBe(false);
    expect(screen.getAllByRole("dialog", { name: "More" })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "More" })).toBeNull();
    fireEvent.keyDown(filter(), { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();
    expect(document.activeElement).toBe(opener);
    expect(screen.getByRole("button", { name: "Open navigation" })).toBe(opener);
    sameScene();
  });

  it("click and repeated product activation reuse the same stable window", async () => {
    mount(); const opener = more(); opener.focus(); fireEvent.click(opener);
    fireEvent.click(screen.getByRole("button", { name: "Open Read workflow in a window" }));
    await readWindow();
    const first = useWindows.getState().windows["win:subaction:read"];
    opener.focus(); moreKey(opener);
    fireEvent.click(screen.getByRole("button", { name: "Open Read workflow in a window" }));
    expect(useWindows.getState().order).toEqual(["win:subaction:read"]);
    expect(useWindows.getState().windows["win:subaction:read"].rect).toEqual(first.rect);
    expect(useWindows.getState().focusedId).toBe("win:subaction:read");
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("dialog", { name: "Read" })));
    sameScene();
  });

  it("Escape closes the launcher alone and restores its actual opener", async () => {
    mount(); const opener = more(); opener.focus();
    act(() => { useWindows.getState().open("subaction", { workflow: "read", __windowId: "win:subaction:read" }, { id: "win:subaction:read", title: "Read" }); });
    await readWindow(); opener.focus(); moreKey(opener);
    fireEvent.keyDown(filter(), { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();
    expect(useWindows.getState().windows["win:subaction:read"]).toBeDefined();
    expect(document.activeElement).toBe(opener);
    sameScene();
  });

  it("the existing dispatcher leaves More unavailable while editing a draft", () => {
    mount(); const input = screen.getByRole("textbox", { name: "Underlying draft" }); input.focus();
    expect(moreKey(input)).toBe(true);
    expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();
    sameScene();
  });

  it.each([8, 14])("entry after %d windows preserves hosts and Back restores the retained topmost pane", async (count) => {
    mount();
    act(() => {
      for (let index = 0; index < count; index++) {
        const id = `cap:${index}`;
        useWindows.getState().open("subaction", { workflow: "read", __windowId: id }, { id, title: id });
      }
    });
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("dialog", { name: `cap:${count - 1}` })));
    const before = useWindows.getState();
    const hosts = before.order.map((id) => ({ id, element: screen.getByRole("dialog", { name: id }) }));
    const opener = more(); opener.focus(); moreKey(opener);
    const input = filter(); fireEvent.change(input, { target: { value: "Read" } });
    fireEvent.keyDown(input, { key: "Enter" });
    const dialog = await readWindow();
    const id = "win:subaction:read";
    expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();
    expect(useWindows.getState().order).toEqual([...before.order, id]);
    expect(useWindows.getState().cycleOrder).toEqual([...before.cycleOrder, id]);
    expect(useWindows.getState().focusedId).toBe(id);
    await waitFor(() => expect(document.activeElement).toBe(dialog));
    for (const host of hosts) {
      expect(screen.getByRole("dialog", { name: host.id })).toBe(host.element);
      expect(useWindows.getState().windows[host.id]).toBe(before.windows[host.id]);
    }
    sameScene();
    fireEvent.click(within(dialog).getByRole("button", { name: "Back to mothership" }));
    expect(useWindows.getState().windows[id]).toBeUndefined();
    expect(useWindows.getState().cycleOrder).toEqual(before.cycleOrder);
    for (const host of hosts) expect(screen.getByRole("dialog", { name: host.id })).toBe(host.element);
    expect(useWindows.getState().focusedId).toBe(before.focusedId);
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("dialog", { name: `cap:${count - 1}` })));
    sameScene();
  });

  it("raising an already-focused window preserves its native draft focus and value", async () => {
    const id = useWindows.getState().open("subaction", {}, { id: "draft-window", title: "Draft window" });
    render(<WorkspaceWindow id={id}><input aria-label="Product draft" defaultValue="Keep product draft" /></WorkspaceWindow>);
    const dialog = screen.getByRole("dialog", { name: "Draft window" });
    await waitFor(() => expect(document.activeElement).toBe(dialog));
    const input = screen.getByRole("textbox", { name: "Product draft" });
    input.focus();
    act(() => { useWindows.getState().focus(id); });
    expect(document.activeElement).toBe(input);
    expect(input).toHaveProperty("value", "Keep product draft");
  });
});
