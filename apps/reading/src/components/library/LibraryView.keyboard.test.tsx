import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, createEvent, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { UseLibraryResult } from "./useLibrary";

const state = vi.hoisted(() => ({
  reload: vi.fn(),
  loading: false,
}));

vi.mock("./useLibrary", () => ({
  useLibrary: (): UseLibraryResult => ({
    works: [],
    total: 0,
    page: 1,
    pageSize: 24,
    loading: state.loading,
    error: state.loading ? null : "GET /library: HTTP 503",
    routeAbsent: false,
    reload: state.reload,
  }),
}));

import LibraryView from "./LibraryView";

function mount() {
  return render(<MemoryRouter><LibraryView /></MemoryRouter>);
}

beforeEach(() => {
  state.reload.mockClear();
  state.loading = false;
});
afterEach(cleanup);

describe("Library browse keyboard and failure states", () => {
  it("has one tab stop for the selected filter", () => {
    mount();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((tab) => ({ name: tab.textContent, tabIndex: tab.tabIndex }))).toEqual([
      { name: "Shelf", tabIndex: 0 },
      { name: "Preview", tabIndex: -1 },
      { name: "All", tabIndex: -1 },
    ]);
  });

  it("moves focus and activates the next filter with Right", () => {
    mount();
    const shelf = screen.getByRole("tab", { name: "Shelf" });
    shelf.focus();
    fireEvent.keyDown(shelf, { key: "ArrowRight" });
    const preview = screen.getByRole("tab", { name: "Preview" });
    expect(document.activeElement).toBe(preview);
    expect(preview.getAttribute("aria-selected")).toBe("true");
  });

  it("wraps Left from Shelf to All and Right back to Shelf", () => {
    mount();
    const shelf = screen.getByRole("tab", { name: "Shelf" });
    shelf.focus();
    fireEvent.keyDown(shelf, { key: "ArrowLeft" });
    const all = screen.getByRole("tab", { name: "All" });
    expect(document.activeElement).toBe(all);
    expect(all.getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(all, { key: "ArrowRight" });
    expect(document.activeElement).toBe(shelf);
    expect(shelf.getAttribute("aria-selected")).toBe("true");
  });

  it("uses Home and End for the first and last filters", () => {
    mount();
    const shelf = screen.getByRole("tab", { name: "Shelf" });
    shelf.focus();
    fireEvent.keyDown(shelf, { key: "End" });
    const all = screen.getByRole("tab", { name: "All" });
    expect(document.activeElement).toBe(all);
    fireEvent.keyDown(all, { key: "Home" });
    expect(document.activeElement).toBe(shelf);
  });

  it("updates the roving tab stop after a pointer selection", () => {
    mount();
    fireEvent.click(screen.getByRole("tab", { name: "All" }));
    expect(screen.getByRole("tab", { name: "All" }).tabIndex).toBe(0);
    expect(screen.getByRole("tab", { name: "Shelf" }).tabIndex).toBe(-1);
  });

  it("leaves modified, composing and already handled keys alone", () => {
    mount();
    const shelf = screen.getByRole("tab", { name: "Shelf" });
    shelf.focus();
    for (const modifiers of [{ ctrlKey: true }, { metaKey: true }, { altKey: true }, { shiftKey: true }, { isComposing: true }]) {
      fireEvent.keyDown(shelf, { key: "ArrowRight", ...modifiers });
      expect(document.activeElement).toBe(shelf);
      expect(shelf.getAttribute("aria-selected")).toBe("true");
    }
    const handled = createEvent.keyDown(shelf, { key: "ArrowRight" });
    handled.preventDefault();
    fireEvent(shelf, handled);
    expect(document.activeElement).toBe(shelf);
  });

  it("links the selected tab to its actual panel with unique view IDs", () => {
    const view = render(<MemoryRouter><LibraryView /><LibraryView /></MemoryRouter>);
    const panels = screen.getAllByRole("tabpanel");
    expect(panels).toHaveLength(2);
    expect(panels[0].id).not.toBe(panels[1].id);
    for (const panel of panels) {
      const tab = view.container.querySelector(`[id="${panel.getAttribute("aria-labelledby")}"]`);
      expect(tab?.getAttribute("aria-controls")).toBe(panel.id);
      expect(tab?.getAttribute("aria-selected")).toBe("true");
    }
  });

  it("offers a real retry callback without presenting failure as zero works", () => {
    mount();
    expect(screen.queryByText(/0 readable in full/)).toBeNull();
    expect(screen.queryByText(/Nothing is readable in full/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(state.reload).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alert").textContent).toContain("GET /library: HTTP 503");
  });

  it("announces loading without inventing empty catalog data", () => {
    state.loading = true;
    mount();
    expect(screen.getByRole("status").textContent).toContain("Opening the library");
    expect(screen.queryByText(/0 readable in full/)).toBeNull();
    expect(screen.queryByText(/Nothing is readable in full/)).toBeNull();
  });

  it("keeps Retry focus in the mounted result panel through loading and failure", () => {
    const view = mount();
    const retry = screen.getByRole("button", { name: "Retry" });
    const panel = screen.getByRole("tabpanel");
    retry.focus();
    fireEvent.click(retry);
    expect(document.activeElement).toBe(panel);
    expect(state.reload).toHaveBeenCalledTimes(1);

    state.loading = true;
    view.rerender(<MemoryRouter><LibraryView /></MemoryRouter>);
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(document.activeElement).toBe(panel);

    state.loading = false;
    view.rerender(<MemoryRouter><LibraryView /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(document.activeElement).toBe(panel);
  });

});
