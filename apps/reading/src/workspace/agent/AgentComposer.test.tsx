/**
 * AgentComposer.test.tsx — SPR-07 M2: invariants 13 (ladder, pane-level
 * in AgentPane.test), 14 (paste-anywhere), 15 (digits), 16 (focus on
 * mount), 17 (combobox ARIA + chip announcement).
 */
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { createRef } from "react";

import { AgentComposer, type AgentComposerProps } from "./AgentComposer";

beforeAll(() => {
  // jsdom lays nothing out, so every element reports one rect: the [hidden]
  // case below is caught by the guard's own closest("[hidden]") check, not
  // by this stub (a stub that consulted [hidden] masked that mutation).
  Element.prototype.getClientRects = function () {
    return [{}] as unknown as DOMRectList;
  };
});
afterEach(() => { cleanup(); document.body.innerHTML = ""; });

function mount(over: Partial<AgentComposerProps> = {}, hostAttrs: Record<string, unknown> = {}) {
  const rootRef = createRef<HTMLElement>();
  const props: AgentComposerProps = {
    tabId: "agent:pane:p:proj-1",
    draft: "", onDraftChange: vi.fn(),
    chips: [], onChipsChange: vi.fn(),
    candidates: { agents: [{ id: "x:1", label: "Cross" }], sources: [{ id: "doc-1", label: "Finches" }, { id: "doc-2", label: "Origin" }] },
    threadEmpty: true,
    onSend: vi.fn(), onCannedPrompt: vi.fn(), onEscapeRung: vi.fn(),
    hasContextChip: false, recording: false, onStopRecording: vi.fn(),
    active: true, openNonce: 0, rootRef, announce: vi.fn(),
    ...over,
  };
  const Host = (p: AgentComposerProps) => (
    <section ref={rootRef as never} data-agent-pane tabIndex={-1} {...hostAttrs}>
      <AgentComposer {...p} />
    </section>
  );
  const utils = render(<Host {...props} />);
  const textarea = () => document.querySelector<HTMLTextAreaElement>("[data-agent-pane] textarea")!;
  return { ...utils, props, textarea, rerender: (next: Partial<AgentComposerProps>) => utils.rerender(<Host {...props} {...next} />) };
}

function paste(text: string, target: EventTarget = document) {
  const e = new Event("paste", { bubbles: true, cancelable: true }) as ClipboardEvent;
  Object.defineProperty(e, "clipboardData", { value: { getData: (t: string) => (t === "text/plain" ? text : "") } });
  act(() => { target.dispatchEvent(e); });
  return e;
}

describe("focus on mount (invariant 16)", () => {
  it("focuses the textarea synchronously after commit and again on an openNonce bump", () => {
    const m = mount();
    expect(document.activeElement).toBe(m.textarea());
    m.textarea().blur();
    expect(document.activeElement).not.toBe(m.textarea());
    m.rerender({ openNonce: 1 });
    expect(document.activeElement).toBe(m.textarea());
  });
});

describe("the key contract on the element (never window/document)", () => {
  it("Enter sends and is consumed; Shift+Enter is left to the textarea; a composing Enter is ignored", () => {
    const m = mount({ draft: "hello" });
    const enter = fireEvent.keyDown(m.textarea(), { key: "Enter" });
    expect(enter).toBe(false); // defaultPrevented
    expect(m.props.onSend).toHaveBeenCalledWith("hello");
    expect(fireEvent.keyDown(m.textarea(), { key: "Enter", shiftKey: true })).toBe(true);
    fireEvent.keyDown(m.textarea(), { key: "Enter", isComposing: true });
    expect(m.props.onSend).toHaveBeenCalledTimes(1);
  });

  it("Escape walks picker → recording → chip → blur, every event consumed; a document listener never sees it", () => {
    const seen: string[] = [];
    const onDoc = (e: KeyboardEvent) => { if (e.key === "Escape") seen.push(e.defaultPrevented ? "prevented" : "raw"); };
    document.addEventListener("keydown", onDoc);
    const m = mount({ draft: "@C", recording: true, hasContextChip: true });
    // The picker is open on the "@C" token (matches the Cross agent).
    expect(m.textarea().getAttribute("aria-expanded")).toBe("true");
    expect(fireEvent.keyDown(m.textarea(), { key: "Escape" })).toBe(false);
    expect(m.textarea().getAttribute("aria-expanded")).toBe("false");
    expect(fireEvent.keyDown(m.textarea(), { key: "Escape" })).toBe(false);
    expect(m.props.onStopRecording).toHaveBeenCalledTimes(1);
    m.rerender({ draft: "", recording: false, hasContextChip: true });
    expect(fireEvent.keyDown(m.textarea(), { key: "Escape" })).toBe(false);
    expect(m.props.onEscapeRung).toHaveBeenLastCalledWith("chip");
    m.rerender({ draft: "", recording: false, hasContextChip: false });
    expect(fireEvent.keyDown(m.textarea(), { key: "Escape" })).toBe(false);
    expect(m.props.onEscapeRung).toHaveBeenLastCalledWith("blur");
    expect(document.activeElement).toBe(m.props.rootRef.current);
    // stopPropagation: the document never saw a single Escape.
    expect(seen).toEqual([]);
    document.removeEventListener("keydown", onDoc);
  });
});

describe("digits (invariant 15)", () => {
  it("1 sends canned prompt 1 only with an empty thread and an untouched empty draft", () => {
    const m = mount();
    expect(fireEvent.keyDown(m.textarea(), { key: "1" })).toBe(false);
    expect(m.props.onCannedPrompt).toHaveBeenCalledWith(1);
    expect(m.props.onDraftChange).not.toHaveBeenCalled();
    expect(fireEvent.keyDown(m.textarea(), { key: "1", ctrlKey: true })).toBe(true);
    expect(fireEvent.keyDown(m.textarea(), { key: "2", metaKey: true })).toBe(true);
    expect(fireEvent.keyDown(m.textarea(), { key: "3", altKey: true })).toBe(true);
    expect(m.props.onCannedPrompt).toHaveBeenCalledTimes(1);
  });

  it("a non-empty draft, a non-empty thread, or a touched draft all type the digit", () => {
    const a = mount({ draft: "x" });
    expect(fireEvent.keyDown(a.textarea(), { key: "1" })).toBe(true);
    cleanup();
    const b = mount({ threadEmpty: false });
    expect(fireEvent.keyDown(b.textarea(), { key: "1" })).toBe(true);
    cleanup();
    const c = mount();
    fireEvent.change(c.textarea(), { target: { value: "typed" } });
    c.rerender({ draft: "" }); // the user deleted it: touched
    expect(fireEvent.keyDown(c.textarea(), { key: "1" })).toBe(true);
    expect(c.props.onCannedPrompt).not.toHaveBeenCalled();
  });
});

describe("paste-anywhere (invariant 14, fix 2)", () => {
  it("a document paste with body focused lands at the end of the draft, focuses the textarea, and is consumed", () => {
    const m = mount({ draft: "before" });
    m.textarea().blur();
    document.body.tabIndex = -1; document.body.focus();
    expect(document.activeElement).toBe(document.body);
    const e = paste(" pasted");
    expect(e.defaultPrevented).toBe(true);
    expect(m.props.onDraftChange).toHaveBeenLastCalledWith("before pasted");
    expect(document.activeElement).toBe(m.textarea());
  });

  it.each([
    ["another textarea is focused", () => { const t = document.createElement("textarea"); document.body.append(t); t.focus(); }, {}],
    ["an aria-modal dialog is open", () => { const d = document.createElement("div"); d.setAttribute("role", "dialog"); d.setAttribute("aria-modal", "true"); document.body.append(d); }, {}],
    ["the root is inert", () => {}, { inert: "" }],
    ["the root is under a [hidden] ancestor", () => {}, { hidden: true }],
  ])("does nothing while %s", (_label, prepare, hostAttrs) => {
    const m = mount({ draft: "before" }, hostAttrs);
    m.textarea().blur();
    document.body.tabIndex = -1; document.body.focus();
    prepare();
    const before = document.activeElement;
    const e = paste(" pasted");
    expect(e.defaultPrevented).toBe(false);
    expect(m.props.onDraftChange).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(before);
  });

  it("is not installed while the composer is not the active tab's", () => {
    const m = mount({ draft: "before", active: false });
    m.textarea().blur();
    document.body.tabIndex = -1; document.body.focus();
    expect(paste(" pasted").defaultPrevented).toBe(false);
    expect(m.props.onDraftChange).not.toHaveBeenCalled();
  });
});

describe("the picker (invariant 17, refs §2.1)", () => {
  it("the textarea is a combobox whose aria-expanded and aria-activedescendant follow the picker", () => {
    const m = mount({ draft: "" });
    const t = m.textarea();
    expect(t.getAttribute("role")).toBe("combobox");
    expect(t.getAttribute("aria-expanded")).toBe("false");
    m.rerender({ draft: "see #Fi" });
    expect(t.getAttribute("aria-expanded")).toBe("true");
    const listbox = document.getElementById(t.getAttribute("aria-controls")!)!;
    expect(listbox.getAttribute("role")).toBe("listbox");
    const options = [...listbox.querySelectorAll('[role="option"]')];
    expect(options.map((o) => o.textContent)).toEqual(["Finches"]);
    expect(t.getAttribute("aria-activedescendant")).toBe(options[0].id);
    fireEvent.keyDown(t, { key: "Enter" });
    expect(m.props.onChipsChange).toHaveBeenCalledWith([{ kind: "source", id: "doc-1", label: "Finches" }]);
    expect(m.props.onDraftChange).toHaveBeenLastCalledWith("see ");
    expect(m.props.onSend).not.toHaveBeenCalled();
  });

  it("ArrowDown wraps the highlight; a chip × announces and keeps focus in the textarea; Backspace on an empty body removes the last chip", () => {
    const m = mount({ draft: "@", chips: [{ kind: "source", id: "doc-2", label: "Origin" }] });
    const t = m.textarea();
    fireEvent.keyDown(t, { key: "ArrowDown" });
    expect(t.getAttribute("aria-activedescendant")).toMatch(/0$/);
    const remove = document.querySelector<HTMLButtonElement>('[data-agent-chip="doc-2"] button')!;
    fireEvent.click(remove);
    expect(m.props.announce).toHaveBeenCalledWith("Context removed");
    expect(document.activeElement).toBe(t);
    m.rerender({ draft: "", chips: [{ kind: "source", id: "doc-2", label: "Origin" }] });
    expect(fireEvent.keyDown(t, { key: "Backspace" })).toBe(false);
    expect(m.props.onChipsChange).toHaveBeenLastCalledWith([]);
  });
});

describe("IME composition owns every key, Escape included (finding 8)", () => {
  it("an Escape with isComposing=true walks no rung, is not consumed, and leaves focus in the textarea", () => {
    const m = mount({ draft: "か", recording: true });
    m.textarea().focus();
    const notPrevented = fireEvent.keyDown(m.textarea(), { key: "Escape", isComposing: true });
    expect(notPrevented).toBe(true);
    expect(m.props.onEscapeRung).not.toHaveBeenCalled();
    expect(m.props.onStopRecording).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(m.textarea());
    // The same Escape outside a composition walks the recording rung.
    expect(fireEvent.keyDown(m.textarea(), { key: "Escape" })).toBe(false);
    expect(m.props.onEscapeRung).toHaveBeenCalledWith("recording");
  });
});
