/**
 * SlashMenu.test.tsx — the slash menu's window-level keys are its own only
 * while nothing above it owns them: a key another handler already claimed
 * (defaultPrevented) and a key pressed inside an open aria-modal dialog
 * that does not contain the menu never run a block command or close the
 * menu (one Esc reaches exactly one handler, workspace/escapeOverlay.ts;
 * the same gate FloatMenu uses). Repair round 2026-10-07T22:40Z.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SlashMenu } from "./SlashMenu";

function fakeEditor() {
  const calls: string[] = [];
  const chain: Record<string, unknown> = new Proxy({}, {
    get: (_t, p: string) => (...args: unknown[]) => {
      void args;
      calls.push(p);
      return p === "run" ? true : chain;
    },
  });
  const editor = { state: { selection: { from: 2 }, doc: { resolve: () => ({ start: () => 1 }), textBetween: () => "/" } }, chain: () => chain };
  return { editor, calls };
}

function press(target: EventTarget, key: string, preventFirst = false): KeyboardEvent {
  const e = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
  if (preventFirst) e.preventDefault();
  target.dispatchEvent(e);
  return e;
}

afterEach(() => {
  cleanup();
  document.body.innerHTML = "";
});

describe("SlashMenu — key ownership", () => {
  it("control: a plain Enter runs the highlighted command and closes; a plain Esc closes", () => {
    const { editor, calls } = fakeEditor();
    const onClose = vi.fn();
    render(<SlashMenu editor={editor as never} query="" onClose={onClose} />);
    press(document.body, "Enter");
    expect(calls).toContain("run");
    expect(onClose).toHaveBeenCalledTimes(1);
    press(document.body, "Escape");
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("a key another handler already claimed (defaultPrevented) is not the menu's", () => {
    const { editor, calls } = fakeEditor();
    const onClose = vi.fn();
    render(<SlashMenu editor={editor as never} query="" onClose={onClose} />);
    press(document.body, "Enter", true);
    press(document.body, "Escape", true);
    press(document.body, "ArrowDown", true);
    expect(calls).toEqual([]);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("a key pressed inside an open modal that does not contain the menu is the modal's, never the menu's", () => {
    const { editor, calls } = fakeEditor();
    const onClose = vi.fn();
    render(<SlashMenu editor={editor as never} query="" onClose={onClose} />);
    const modal = document.createElement("div");
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    const button = document.createElement("button");
    modal.append(button);
    document.body.append(modal);
    button.focus();
    press(button, "Enter");
    press(button, "Escape");
    expect(calls).toEqual([]);
    expect(onClose).not.toHaveBeenCalled();
    modal.remove();
    press(document.body, "Escape");
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
