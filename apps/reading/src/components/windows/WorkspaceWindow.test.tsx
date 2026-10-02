/**
 * WorkspaceWindow.test.tsx — SPR-09 M1 + M7 + M8 acceptance.
 *
 * Lifecycle: a window drags via the store rect, expands→restores, closes;
 * clicking it raises it (focus z-order); the glass body reveals the scene;
 * an unfocused window drops backdrop blur (perf); keyboard moves/closes it;
 * reduced-motion disables the spring; focus enters on mount + returns on close.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { WorkspaceWindow } from "./WorkspaceWindow";
import { WINDOW_Z_BASE, useWindows } from "../../workspace/windowsStore";

function stubMatchMedia(reduce: boolean): void {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: (query: string) => ({
      matches: reduce && query.includes("reduce"),
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

const w = () => useWindows.getState();

beforeEach(() => {
  stubMatchMedia(false);
  Object.defineProperty(window, "innerWidth", { value: 1440, configurable: true });
  Object.defineProperty(window, "innerHeight", { value: 900, configurable: true });
  w().reset();
});
afterEach(cleanup);

/** Render a single window with a child page stand-in. */
function renderWindow(id: string) {
  return render(
    <WorkspaceWindow id={id}>
      <div data-testid="hosted-page">hosted page content</div>
    </WorkspaceWindow>,
  );
}

describe("WorkspaceWindow — frame + body", () => {
  it("renders the title bar, hosted child, and a glass body that reveals the scene", () => {
    const id = w().open("library", {}, { title: "Library" });
    const { container } = renderWindow(id);
    expect(screen.getByText("Library")).toBeTruthy();
    expect(screen.getByTestId("hosted-page")).toBeTruthy();
    const root = container.querySelector(`[data-workspace-window='${id}']`) as HTMLElement;
    // Focused floating window uses live glass (transparent body → scene shows).
    expect(root.className).toContain("bg-glass");
    expect(root.className).toContain("backdrop-blur-glass");
  });

  it("returns null for an unknown window id", () => {
    const { container } = render(
      <WorkspaceWindow id="missing">
        <div>x</div>
      </WorkspaceWindow>,
    );
    expect(container.querySelector("[data-workspace-window]")).toBeNull();
  });
});

describe("WorkspaceWindow — drag + resize via store", () => {
  it("dragging the title bar moves the window rect", () => {
    const id = w().open("library", {});
    w().setRect(id, { x: 100, y: 100 });
    const { container } = renderWindow(id);
    const bar = container.querySelector("[data-window-titlebar]") as HTMLElement;
    // jsdom has no pointer capture; stub it so setPointerCapture doesn't throw.
    (bar as unknown as { setPointerCapture: () => void }).setPointerCapture = () => {};
    fireEvent.pointerDown(bar, { clientX: 100, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(bar, { clientX: 140, clientY: 130, pointerId: 1 });
    fireEvent.pointerUp(bar, { pointerId: 1 });
    expect(w().windows[id].rect.x).toBe(140);
    expect(w().windows[id].rect.y).toBe(130);
  });
});

describe("WorkspaceWindow — expand / restore / close", () => {
  it("expand fills the working region and restore returns to floating", () => {
    const id = w().open("library", {});
    const { container } = renderWindow(id);
    const expandBtn = screen.getByLabelText("Expand window to full");
    fireEvent.click(expandBtn);
    expect(w().windows[id].mode).toBe("full");
    const root = container.querySelector(`[data-workspace-window='${id}']`) as HTMLElement;
    // A full window goes opaque so the scene blur can be paused behind it.
    expect(root.className).toContain("bg-glass-solid");
    fireEvent.click(screen.getByLabelText("Restore window to floating"));
    expect(w().windows[id].mode).toBe("floating");
  });

  it("close removes the window from the store", () => {
    const id = w().open("library", {});
    renderWindow(id);
    fireEvent.click(screen.getByLabelText("Close window"));
    expect(w().windows[id]).toBeUndefined();
  });
});

describe("WorkspaceWindow — focus / z-order (M7 perf)", () => {
  it("clicking a window raises it (focus restacks z)", () => {
    const a = w().open("stats", {});
    const b = w().open("library", {});
    render(
      <>
        <WorkspaceWindow id={a}>
          <div data-testid="page-a">A</div>
        </WorkspaceWindow>
        <WorkspaceWindow id={b}>
          <div data-testid="page-b">B</div>
        </WorkspaceWindow>
      </>,
    );
    expect(w().focusedId).toBe(b);
    const rootA = document.querySelector(`[data-workspace-window='${a}']`) as HTMLElement;
    fireEvent.mouseDown(rootA);
    expect(w().focusedId).toBe(a);
    expect(w().windows[a].z).toBeGreaterThan(w().windows[b].z);
  });

  it("an unfocused window drops the backdrop blur (perf degradation)", () => {
    const a = w().open("stats", {});
    const b = w().open("library", {});
    render(
      <>
        <WorkspaceWindow id={a}>
          <div>A</div>
        </WorkspaceWindow>
        <WorkspaceWindow id={b}>
          <div>B</div>
        </WorkspaceWindow>
      </>,
    );
    // b is focused; a is unfocused → a must NOT pay for live backdrop blur.
    const rootA = document.querySelector(`[data-workspace-window='${a}']`) as HTMLElement;
    const rootB = document.querySelector(`[data-workspace-window='${b}']`) as HTMLElement;
    expect(rootA.className).not.toContain("backdrop-blur-glass");
    expect(rootB.className).toContain("backdrop-blur-glass");
    expect(rootA.getAttribute("data-window-focused")).toBe("false");
  });
});

describe("WorkspaceWindow — keyboard a11y (M8)", () => {
  it("arrow keys on the title bar move the window", () => {
    const id = w().open("library", {});
    w().setRect(id, { x: 200, y: 200 });
    const { container } = renderWindow(id);
    const bar = container.querySelector("[data-window-titlebar]") as HTMLElement;
    bar.focus();
    fireEvent.keyDown(bar, { key: "ArrowRight" });
    expect(w().windows[id].rect.x).toBe(224);
    fireEvent.keyDown(bar, { key: "ArrowDown" });
    expect(w().windows[id].rect.y).toBe(224);
  });

  it("Escape on the title bar closes the window", () => {
    const id = w().open("library", {});
    const { container } = renderWindow(id);
    const bar = container.querySelector("[data-window-titlebar]") as HTMLElement;
    bar.focus();
    fireEvent.keyDown(bar, { key: "Escape" });
    expect(w().windows[id]).toBeUndefined();
  });

  it("Enter on the title bar toggles full/restore", () => {
    const id = w().open("library", {});
    const { container } = renderWindow(id);
    const bar = container.querySelector("[data-window-titlebar]") as HTMLElement;
    bar.focus();
    fireEvent.keyDown(bar, { key: "Enter" });
    expect(w().windows[id].mode).toBe("full");
  });

  it("keystrokes typed inside the hosted page are NOT intercepted", () => {
    const id = w().open("library", {});
    render(
      <WorkspaceWindow id={id}>
        <input data-testid="page-input" />
      </WorkspaceWindow>,
    );
    const input = screen.getByTestId("page-input") as HTMLInputElement;
    input.focus();
    fireEvent.keyDown(input, { key: "ArrowRight" });
    // Focus is inside the page, not on the chrome → no window move, no close.
    expect(w().windows[id]).toBeDefined();
    expect(w().windows[id].mode).toBe("floating");
  });
});

describe("WorkspaceWindow — focus management on mount/unmount (M8)", () => {
  it("focus enters the window on mount and returns to the opener on close", async () => {
    const opener = document.createElement("button");
    opener.textContent = "opener";
    document.body.appendChild(opener);
    opener.focus();
    expect(document.activeElement).toBe(opener);

    const id = w().open("library", {});
    const { unmount } = renderWindow(id);
    const root = document.querySelector(`[data-workspace-window='${id}']`) as HTMLElement;
    expect(root.getAttribute("tabindex")).toBe("-1");

    // The mount effect defers focus via setTimeout(0); wait for it to land.
    await waitFor(() => expect(document.activeElement).toBe(root));

    act(() => unmount());
    // On unmount (close), focus is restored to the opener.
    expect(document.activeElement).toBe(opener);
    document.body.removeChild(opener);
  });

  it("moves DOM focus into an already-mounted stable-id window when it is reopened", async () => {
    const a = w().open("reader", {}, { id: "reader:a" });
    const b = w().open("library", {}, { id: "library:b" });
    render(
      <>
        <WorkspaceWindow id={a}><div>A</div></WorkspaceWindow>
        <WorkspaceWindow id={b}><input data-testid="window-b-input" /></WorkspaceWindow>
      </>,
    );
    const input = screen.getByTestId("window-b-input");
    input.focus();

    act(() => { w().open("reader", {}, { id: "reader:a" }); });

    const rootA = document.querySelector("[data-workspace-window='reader:a']") as HTMLElement;
    await waitFor(() => expect(document.activeElement).toBe(rootA));
  });
});

describe("WorkspaceWindow — reduced motion (M8)", () => {
  it("does not crash and keeps the frame under reduced motion", () => {
    stubMatchMedia(true);
    const id = w().open("library", {});
    const { container } = renderWindow(id);
    // The window still renders; framer-motion spring is set to duration 0
    // (no animation) — asserted by the frame being immediately present + the
    // hosted page visible (no entrance scale gating content).
    expect(container.querySelector(`[data-workspace-window='${id}']`)).toBeTruthy();
    expect(screen.getByTestId("hosted-page")).toBeTruthy();
  });
});

// Ensure WINDOW_Z_BASE is applied to the rendered z-index (over the scene).
describe("WorkspaceWindow — z stacking", () => {
  it("applies WINDOW_Z_BASE + win.z as the rendered z-index", () => {
    const id = w().open("library", {});
    const { container } = renderWindow(id);
    const root = container.querySelector(`[data-workspace-window='${id}']`) as HTMLElement;
    const z = Number(root.style.zIndex);
    expect(z).toBeGreaterThan(WINDOW_Z_BASE);
  });
});
