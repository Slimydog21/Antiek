/** Real resizer/store/canonical admission with synthetic local UNIT subjects.
 * No account, provider, browser or signed-session acceptance. */
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { accountStorageKey, awaitWorkspaceOwnerSession, beforeWorkspaceOwnerChange, resumeWorkspaceOwner, setWorkspaceOwner, subscribeWorkspaceOwnerAdmission, suspendWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import { useCompanion } from "../companionStore";
import { PaneResizer } from "./PaneResizer";
import { CLOSE_LINGER_MS, captureAgentPaneLease, useAgentPaneStore } from "./agentPaneStore";
import { PANE_WIDTH_KEY, clearPaneWidth, readPaneWidth, usePaneWidth, usePaneWidthStore, writePaneWidth } from "./paneWidthStore";
import { StrictMode, useRef } from "react";

const A = "unit-resizer-A";
const B = "unit-resizer-B";
const tabId = "agent:pane:x:resizer";
function open() { useCompanion.getState().openAgentTab({ kind: "dialogue", agentId: "x:resizer", title: "UNIT resizer agent", scope: "cross-project" }); }
async function owner(subject: string | null) {
  await act(async () => { setWorkspaceOwner(subject); await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
}
async function resume() {
  await act(async () => { resumeWorkspaceOwner(); await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
}
function Host({ preview = () => {} }: { preview?: (width: number | null) => void }) {
  const preferred = usePaneWidthStore((s) => s.preferred);
  return <PaneResizer width={preferred ?? 320} max={600} onPreview={preview} />;
}
function HydratedHost() {
  const ref = useRef<HTMLDivElement>(null);
  const { width } = usePaneWidth({ leftDockWidth: 0, containerRef: ref, defaultWidth: 320 });
  return <div ref={ref} data-width={width} />;
}
function separator() { return document.querySelector<HTMLElement>('[role="separator"]')!; }
function down(node = separator(), pointerId = 1) { fireEvent.pointerDown(node, { clientX: 500, pointerId, button: 0 }); }
function up(node = separator(), clientX = 460, pointerId = 1) { fireEvent.pointerUp(node, { clientX, pointerId }); }
function finish() { act(() => { vi.advanceTimersByTime(CLOSE_LINGER_MS); }); }

beforeEach(async () => {
  vi.useFakeTimers();
  setWorkspaceOwner(null); setWorkspaceOwner(A); await awaitWorkspaceOwnerSession(workspaceOwnerSession());
  useCompanion.getState().reset(); useAgentPaneStore.getState().reset(); usePaneWidthStore.getState().reset();
  window.localStorage.clear(); window.sessionStorage.clear(); open();
});
afterEach(() => { try { cleanup(); setWorkspaceOwner(null); } finally { vi.useRealTimers(); vi.restoreAllMocks(); } });

describe("width memory follows the canonical owner token", () => {
  it("new owner hydrates its own persisted width, not the already hydrated owner A memory", async () => {
    writePaneWidth(416); render(<HydratedHost />);
    expect(usePaneWidthStore.getState().preferred).toBe(416);
    await owner(B);
    expect(usePaneWidthStore.getState().preferred).toBeNull();
    expect(document.querySelector('[data-width]')?.getAttribute("data-width")).toBe("320");
    act(() => usePaneWidthStore.getState().setPreferred(512));
    await owner(A);
    expect(usePaneWidthStore.getState().preferred).toBe(416);
    expect(readPaneWidth()).toBe(416);
    await owner(B);
    expect(usePaneWidthStore.getState().preferred).toBe(512);
  });
  it("logout retires the preference immediately and does not write a prior width", () => {
    usePaneWidthStore.getState().setPreferred(416); const key = accountStorageKey(PANE_WIDTH_KEY)!;
    act(() => setWorkspaceOwner(null));
    expect(usePaneWidthStore.getState().preferred).toBeNull();
    usePaneWidthStore.getState().setPreferred(512);
    expect(usePaneWidthStore.getState().preferred).toBeNull();
    expect(JSON.parse(window.localStorage.getItem(key)!).width).toBe(416);
  });
  it("same-subject A-B-A is a new token and rehydrates persisted A instead of carrying transient memory", async () => {
    writePaneWidth(416); usePaneWidthStore.getState().hydrate();
    usePaneWidthStore.setState({ preferred: 544 });
    const original = workspaceOwnerSession();
    await owner(B); await owner(A); usePaneWidthStore.getState().hydrate();
    expect(workspaceOwnerSession()).not.toBe(original);
    expect(usePaneWidthStore.getState().preferred).toBe(416);
  });
  it("same-token suspension preserves memory but refuses width writes, clears and hydration until confirmed", async () => {
    usePaneWidthStore.getState().setPreferred(416); const token = workspaceOwnerSession();
    act(() => suspendWorkspaceOwner());
    usePaneWidthStore.getState().setPreferred(512); writePaneWidth(544); clearPaneWidth(); usePaneWidthStore.getState().hydrate();
    expect(usePaneWidthStore.getState().preferred).toBe(416);
    await resume(); expect(workspaceOwnerSession()).toBe(token); expect(readPaneWidth()).toBe(416);
    usePaneWidthStore.getState().setPreferred(448); expect(readPaneWidth()).toBe(448);
  });
  it("failed retirement clears private in-memory preference and refuses subsequent storage work", () => {
    usePaneWidthStore.getState().setPreferred(416);
    const off = beforeWorkspaceOwnerChange(() => { throw new Error("UNIT retirement failure"); });
    try { act(() => { expect(() => setWorkspaceOwner(B)).toThrow("UNIT retirement failure"); }); } finally { off(); }
    expect(usePaneWidthStore.getState().preferred).toBeNull();
    usePaneWidthStore.getState().setPreferred(512); expect(usePaneWidthStore.getState().preferred).toBeNull();
  });
  it("storage publication changing the owner cannot adopt the old width into B memory", () => {
    const original = Storage.prototype.setItem;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key, value) {
      original.call(this, key, value); setWorkspaceOwner(B);
    });
    usePaneWidthStore.getState().setPreferred(416);
    expect(workspaceOwnerSession().subject).toBe(B); expect(usePaneWidthStore.getState().preferred).toBeNull();
  });
  it("a storage read replacing the owner cannot hydrate its returned A body", () => {
    writePaneWidth(416); const original = Storage.prototype.getItem;
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key) {
      const value = original.call(this, key); setWorkspaceOwner(B); return value;
    });
    usePaneWidthStore.getState().hydrate();
    expect(workspaceOwnerSession().subject).toBe(B); expect(usePaneWidthStore.getState().preferred).toBeNull();
    expect(usePaneWidthStore.getState().hydrated).toBe(false);
  });
});

describe("resizer originating owner and drag lifetime", () => {
  it.each(["B", "B-A", "null"])("old keyboard event refuses %s before React cleanup", (replacement) => {
    render(<Host />); const node = separator();
    act(() => { setWorkspaceOwner(replacement === "null" ? null : B); if (replacement === "B-A") setWorkspaceOwner(A); fireEvent.keyDown(node, { key: "End" }); });
    expect(usePaneWidthStore.getState().preferred).toBeNull();
    expect(window.localStorage.length).toBe(0);
  });
  it("suspended keyboard refuses; explicit same-token confirmed keyboard works without replay", async () => {
    render(<Host />); act(() => suspendWorkspaceOwner()); fireEvent.keyDown(separator(), { key: "End" });
    expect(usePaneWidthStore.getState().preferred).toBeNull();
    await resume(); expect(usePaneWidthStore.getState().preferred).toBeNull();
    fireEvent.keyDown(separator(), { key: "ArrowLeft" }); expect(usePaneWidthStore.getState().preferred).toBe(352);
  });
  it("ready notification alone cannot admit a keyboard or direct width write before confirmation", async () => {
    render(<Host />); act(() => suspendWorkspaceOwner());
    const off = subscribeWorkspaceOwnerAdmission(({ state }) => {
      if (state === "ready") { fireEvent.keyDown(separator(), { key: "End" }); usePaneWidthStore.getState().setPreferred(544); }
    });
    try { await resume(); } finally { off(); }
    expect(usePaneWidthStore.getState().preferred).toBeNull(); expect(window.localStorage.length).toBe(0);
    fireEvent.keyDown(separator(), { key: "End" }); expect(usePaneWidthStore.getState().preferred).toBe(600);
  });
  it("failed resume confirmation refuses the ready observer's writes and retires memory", () => {
    usePaneWidthStore.getState().setPreferred(416); render(<Host />); act(() => suspendWorkspaceOwner());
    const off = subscribeWorkspaceOwnerAdmission(({ state }) => {
      if (state === "ready") { fireEvent.keyDown(separator(), { key: "End" }); throw new Error("UNIT confirmation failure"); }
    });
    try { act(() => { expect(() => resumeWorkspaceOwner()).toThrow("UNIT confirmation failure"); }); } finally { off(); }
    expect(usePaneWidthStore.getState().preferred).toBeNull(); fireEvent.keyDown(separator(), { key: "End" });
    expect(usePaneWidthStore.getState().preferred).toBeNull();
  });
  it.each(["up", "escape", "cancel", "blur", "lost"])("retired drag %s cannot restore A width or close B pane", async (ending) => {
    const preview = vi.fn(); usePaneWidthStore.getState().setPreferred(416); render(<Host preview={preview} />); const node = separator(); down(node);
    await owner(B); open(); usePaneWidthStore.getState().setPreferred(512); preview.mockClear();
    if (ending === "up") up(node, 700);
    else if (ending === "escape") fireEvent.keyDown(node, { key: "Escape" });
    else if (ending === "cancel") fireEvent.pointerCancel(node, { pointerId: 1 });
    else if (ending === "blur") fireEvent.blur(node);
    else fireEvent.lostPointerCapture(node, { pointerId: 1 });
    finish(); expect(usePaneWidthStore.getState().preferred).toBe(512); expect(readPaneWidth()).toBe(512);
    expect(useCompanion.getState().tabs.some((t) => t.id === tabId)).toBe(true); expect(preview).not.toHaveBeenCalled();
  });
  it("retired drag cannot preview into B", async () => {
    const preview = vi.fn(); render(<Host preview={preview} />); down(); await owner(B); preview.mockClear();
    fireEvent.pointerMove(separator(), { clientX: 460, pointerId: 1 }); expect(preview).not.toHaveBeenCalled();
  });
  it("same-subject ABA drag cannot close a new admitted same-ID agent", async () => {
    render(<Host />); down(); await owner(B); await owner(A); open();
    up(separator(), 600); finish(); expect(useCompanion.getState().tabs.some((t) => t.id === tabId)).toBe(true);
  });
  it("same-owner suspension pauses callbacks and confirmed resume continues the actual drag", async () => {
    const preview = vi.fn(); render(<Host preview={preview} />); down(); act(() => suspendWorkspaceOwner());
    fireEvent.pointerMove(separator(), { clientX: 460, pointerId: 1 });
    expect(preview).not.toHaveBeenCalled(); expect(usePaneWidthStore.getState().preferred).toBeNull();
    await resume(); up(); expect(usePaneWidthStore.getState().preferred).toBe(360);
  });
  it.each(["owner", "suspend"])("end-preview synchronous %s publication refuses later commit and close", (change) => {
    const preview = vi.fn((width: number | null) => { if (width === null) { if (change === "owner") setWorkspaceOwner(B); else suspendWorkspaceOwner(); } });
    usePaneWidthStore.getState().setPreferred(416); render(<Host preview={preview} />); down(); up(separator(), 700); finish();
    expect(useAgentPaneStore.getState().closing[tabId]).toBeUndefined();
    expect(useCompanion.getState().tabs.some((t) => t.id === tabId)).toBe(true);
    if (change === "owner") expect(usePaneWidthStore.getState().preferred).toBeNull();
    else expect(usePaneWidthStore.getState().preferred).toBe(416);
  });
  it("width publication replacement refuses the following close into the new owner", () => {
    usePaneWidthStore.getState().setPreferred(416); render(<Host />); down();
    const off = usePaneWidthStore.subscribe(() => { off(); setWorkspaceOwner(B); open(); });
    try { up(separator(), 700); } finally { off(); }
    finish(); expect(useAgentPaneStore.getState().closing[tabId]).toBeUndefined();
    expect(useCompanion.getState().tabs.some((t) => t.id === tabId)).toBe(true);
    expect(usePaneWidthStore.getState().preferred).toBeNull();
  });
  it("end-preview starting a new drag cannot let the old release commit or close it", () => {
    let restarted = false;
    const preview = vi.fn((width: number | null) => {
      if (width === null && !restarted) { restarted = true; down(separator(), 2); }
    });
    render(<Host preview={preview} />); down(); up(separator(), 600);
    expect(usePaneWidthStore.getState().preferred).toBeNull(); expect(useAgentPaneStore.getState().closing[tabId]).toBeUndefined();
    up(separator(), 460, 2); expect(usePaneWidthStore.getState().preferred).toBe(360);
  });
  it("same-owner replacement tab incarnation is not the drag's close target", () => {
    render(<Host />); down(); const lease = captureAgentPaneLease(tabId);
    act(() => { useCompanion.getState().closeAgentTab(tabId); open(); });
    expect(captureAgentPaneLease(tabId)).not.toBe(lease); up(separator(), 600); finish();
    expect(useCompanion.getState().tabs.some((t) => t.id === tabId)).toBe(true);
  });
  it("unmounted pointer callbacks cannot affect a newly mounted resizer", () => {
    const h = render(<Host />); const old = separator(); down(old); h.unmount(); render(<Host />);
    up(old, 600); expect(usePaneWidthStore.getState().preferred).toBeNull();
    down(); up(); expect(usePaneWidthStore.getState().preferred).toBe(360);
  });
  it("another pointer cannot preview or commit the captured drag", () => {
    const preview = vi.fn(); render(<Host preview={preview} />); down();
    fireEvent.pointerMove(separator(), { clientX: 460, pointerId: 2 }); up(separator(), 460, 2);
    expect(preview).not.toHaveBeenCalled(); expect(usePaneWidthStore.getState().preferred).toBeNull();
    up(); expect(usePaneWidthStore.getState().preferred).toBe(360);
  });
  it("current threshold close retains its real linger and the pre-drag width", () => {
    usePaneWidthStore.getState().setPreferred(416); render(<Host />); down(); up(separator(), 700);
    expect(useCompanion.getState().tabs.some((t) => t.id === tabId)).toBe(true);
    expect(useAgentPaneStore.getState().closing[tabId]).toBe(true); expect(usePaneWidthStore.getState().preferred).toBe(416);
    finish(); expect(useCompanion.getState().tabs.some((t) => t.id === tabId)).toBe(false);
  });
  it("RTL drag and keyboard retain their inverted direction and clamp", () => {
    render(<Host />); separator().style.direction = "rtl";
    fireEvent.keyDown(separator(), { key: "ArrowLeft" }); expect(usePaneWidthStore.getState().preferred).toBe(288);
    down(); up(separator(), 540); expect(usePaneWidthStore.getState().preferred).toBe(328);
  });
  it("current Escape abort restores preference, clears owned preview and leaves the agent open", () => {
    const preview = vi.fn(); usePaneWidthStore.getState().setPreferred(416); render(<Host preview={preview} />); down();
    fireEvent.pointerMove(separator(), { clientX: 700, pointerId: 1 }); fireEvent.keyDown(separator(), { key: "Escape" });
    expect(preview).toHaveBeenLastCalledWith(null); expect(usePaneWidthStore.getState().preferred).toBe(416);
    finish(); expect(useCompanion.getState().tabs.some((t) => t.id === tabId)).toBe(true);
  });
  it("owner retirement releases only the captured pointer once and does not publish an old preview", async () => {
    const preview = vi.fn(); render(<Host preview={preview} />); const node = separator();
    const capture = vi.fn(); const release = vi.fn();
    Object.defineProperty(node, "setPointerCapture", { value: capture }); Object.defineProperty(node, "releasePointerCapture", { value: release });
    down(node, 7); await owner(B); up(node, 600, 7); fireEvent.pointerCancel(node, { pointerId: 7 });
    expect(capture).toHaveBeenCalledExactlyOnceWith(7); expect(release).toHaveBeenCalledExactlyOnceWith(7);
    expect(preview).not.toHaveBeenCalled();
  });
  it("StrictMode retains a current real drag and retires its own preview on unmount", () => {
    const preview = vi.fn(); const h = render(<StrictMode><Host preview={preview} /></StrictMode>);
    down(); up(); expect(usePaneWidthStore.getState().preferred).toBe(360);
    down(); fireEvent.pointerMove(separator(), { clientX: 480, pointerId: 1 }); h.unmount();
    expect(preview).toHaveBeenLastCalledWith(null); expect(usePaneWidthStore.getState().preferred).toBe(360);
  });
  it.each(["up", "cancel", "blur", "lost"])("suspended %s ends only its local gesture and cannot replay after resume", async (ending) => {
    const preview = vi.fn(); render(<Host preview={preview} />); down(); act(() => suspendWorkspaceOwner());
    if (ending === "up") up();
    else if (ending === "cancel") fireEvent.pointerCancel(separator(), { pointerId: 1 });
    else if (ending === "lost") fireEvent.lostPointerCapture(separator(), { pointerId: 1 });
    else fireEvent.blur(separator());
    expect(separator().hasAttribute("data-dragging")).toBe(false); expect(preview).not.toHaveBeenCalled();
    await resume(); up(); expect(usePaneWidthStore.getState().preferred).toBeNull();
    down(); up(); expect(usePaneWidthStore.getState().preferred).toBe(360);
  });
  it("synchronous pointer-capture owner replacement releases only the acquired old pointer", () => {
    const preview = vi.fn(); render(<Host preview={preview} />); const node = separator(); const release = vi.fn();
    Object.defineProperty(node, "releasePointerCapture", { value: release });
    Object.defineProperty(node, "setPointerCapture", { value: () => setWorkspaceOwner(B) });
    down(node, 9); expect(release).toHaveBeenCalledExactlyOnceWith(9);
    expect(node.hasAttribute("data-dragging")).toBe(false); expect(preview).not.toHaveBeenCalled();
    expect(usePaneWidthStore.getState().preferred).toBeNull();
  });
});
