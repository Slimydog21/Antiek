import { Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { act, cleanup, render } from "@testing-library/react";
import { createElement, StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SlashMenu } from "../modes/Notebook/SlashMenu";
import { escOverlayOpen, registerEscapeListenerOwnership } from "./escapeOverlay";

const retirements: (() => void)[] = [];
const editors: Editor[] = [];

function register(owner: Document) {
  const retire = registerEscapeListenerOwnership(owner);
  retirements.push(retire);
  return retire;
}

function menu(query = "no-slash-entry-matches-this-control", onClose = vi.fn()) {
  const editor = new Editor({ extensions: [StarterKit], content: "<p>/</p>" });
  editors.push(editor);
  return createElement(SlashMenu, { editor, query, onClose });
}

afterEach(() => {
  cleanup();
  for (const retire of retirements.splice(0)) retire();
  for (const editor of editors.splice(0)) editor.destroy();
});

describe("F1 document and actual mounted-menu ownership (source controls, NOT_RUN)", () => {
  it("keeps independent registrations in their own document until each retires", () => {
    const a = document.implementation.createHTMLDocument("F1 document A");
    const b = document.implementation.createHTMLDocument("F1 document B");
    const retireA = register(a);
    const retireB = register(b);
    expect(escOverlayOpen(a)).toBe(true);
    expect(escOverlayOpen(b)).toBe(true);
    expect(escOverlayOpen(document)).toBe(false);
    retireA();
    expect(escOverlayOpen(a)).toBe(false);
    expect(escOverlayOpen(b)).toBe(true);
    retireB();
    expect(escOverlayOpen(b)).toBe(false);
  });

  it("does not let duplicate old cleanup release another instance or a newer registration", () => {
    const owner = document.implementation.createHTMLDocument("F1 cleanup control");
    const old = register(owner);
    const peer = register(owner);
    old(); old();
    expect(escOverlayOpen(owner)).toBe(true);
    peer();
    expect(escOverlayOpen(owner)).toBe(false);
    const current = register(owner);
    old(); peer();
    expect(escOverlayOpen(owner)).toBe(true);
    current(); current();
    expect(escOverlayOpen(owner)).toBe(false);
  });

  it("admits listener ownership only for a document query and does not clear it through except", () => {
    const owner = document.implementation.createHTMLDocument("F1 query boundary");
    const retire = register(owner);
    expect(escOverlayOpen(owner, owner.body)).toBe(true);
    expect(escOverlayOpen(owner.body)).toBe(false);
    const fragment = owner.createDocumentFragment();
    expect(escOverlayOpen(fragment)).toBe(false);
    retire();
    expect(escOverlayOpen(owner)).toBe(false);
  });

  it("retires only the unmounted real empty menu and keeps its still-mounted peer", () => {
    const firstClose = vi.fn();
    const secondClose = vi.fn();
    const first = render(menu(undefined, firstClose));
    const second = render(menu(undefined, secondClose));
    expect(first.container.querySelector("[data-esc-overlay]")).toBeNull();
    expect(second.container.querySelector("[data-esc-overlay]")).toBeNull();
    expect(escOverlayOpen(document)).toBe(true);
    first.unmount();
    expect(escOverlayOpen(document)).toBe(true);
    first.unmount();
    expect(escOverlayOpen(document)).toBe(true);
    act(() => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", cancelable: true })); });
    expect(firstClose).not.toHaveBeenCalled();
    expect(secondClose).toHaveBeenCalledTimes(1);
    second.unmount();
    expect(escOverlayOpen(document)).toBe(false);
    act(() => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", cancelable: true })); });
    expect(firstClose).not.toHaveBeenCalled();
    expect(secondClose).toHaveBeenCalledTimes(1);
  });

  it("leaves no stale lifetime after real StrictMode effect replay and final cleanup", () => {
    const result = render(createElement(StrictMode, null, menu()));
    expect(escOverlayOpen(document)).toBe(true);
    result.unmount();
    expect(escOverlayOpen(document)).toBe(false);
    const later = render(menu());
    expect(escOverlayOpen(document)).toBe(true);
    later.unmount();
    expect(escOverlayOpen(document)).toBe(false);
  });
});
