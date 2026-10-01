import { useRef, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { LemonModal } from "./LemonModal";
import ReadingAppearance from "../reader/ReadingAppearance";
import { READING_LIGHT_KEY, THEME_KEY } from "../../design/theme";
import { LemonSelect } from "./LemonSelect";

afterEach(cleanup);

function DialogStack({ forceTop = false, showOlder = true }: { forceTop?: boolean; showOlder?: boolean }) {
  const [olderOpen, setOlderOpen] = useState(true);
  const [newerOpen, setNewerOpen] = useState(true);
  return <>
    {showOlder && <LemonModal open={olderOpen} title="Project" onClose={() => setOlderOpen(false)}>
      <p>Project content</p>
    </LemonModal>}
    <LemonModal open={newerOpen} title="Shortcuts" forceUserAction={forceTop} onClose={() => setNewerOpen(false)}>
      <LemonSelect aria-label="Scope" value="all" onChange={() => {}} options={[
        { value: "all", label: "All actions" },
        { value: "reading", label: "Reading" },
      ]} />
    </LemonModal>
  </>;
}

describe("LemonModal nested Escape ownership", () => {
  it.each(["dialog", "body"])("closes the newest dialog first when Escape targets %s", (target) => {
    render(<DialogStack />);
    const newer = screen.getByRole("dialog", { name: "Shortcuts" });
    if (target === "body" && document.activeElement instanceof HTMLElement) document.activeElement.blur();
    fireEvent.keyDown(target === "body" ? document.body : newer, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Shortcuts" })).toBeNull();
    expect(screen.queryByRole("dialog", { name: "Project" })).not.toBeNull();
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Project" })).toBeNull();
  });

  it("does not dismiss an older dialog behind a top dialog that requires user action", () => {
    render(<DialogStack forceTop />);
    const newer = screen.getByRole("dialog", { name: "Shortcuts" });
    fireEvent.keyDown(newer, { key: "Escape" });
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Project" })).not.toBeNull();
    expect(screen.queryByRole("dialog", { name: "Shortcuts" })).not.toBeNull();
    expect(newer.contains(document.activeElement)).toBe(true);
  });

  it("lets a select inside the newest dialog consume Escape before either dialog closes", () => {
    render(<DialogStack />);
    const newer = screen.getByRole("dialog", { name: "Shortcuts" });
    fireEvent.click(within(newer).getByRole("button", { name: /All actions/ }));
    expect(screen.queryByRole("listbox")).not.toBeNull();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getAllByRole("dialog")).toHaveLength(2);
    fireEvent.keyDown(newer, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Shortcuts" })).toBeNull();
    expect(screen.queryByRole("dialog", { name: "Project" })).not.toBeNull();
  });

  it("keeps focus in the newest dialog when an older dialog unmounts", () => {
    const { rerender } = render(<DialogStack />);
    const newer = screen.getByRole("dialog", { name: "Shortcuts" });
    const focused = within(newer).getByRole("button", { name: /All actions/ });
    focused.focus();
    rerender(<DialogStack showOlder={false} />);
    expect(document.activeElement).toBe(focused);
    expect(screen.queryByRole("dialog", { name: "Project" })).toBeNull();
  });
});


function RestoringDialog({ forceUserAction = false, onClose = () => {} }: { forceUserAction?: boolean; onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  return <>
    <button ref={opener} onClick={() => setOpen(true)}>Open task</button>
    <LemonModal open={open} title="Task" forceUserAction={forceUserAction} onClose={() => {
      onClose(); setOpen(false); opener.current?.focus();
    }}><label>Task name<input /></label><button>Inside action</button></LemonModal>
  </>;
}

function backdrop(dialog: HTMLElement): Element {
  return dialog.parentElement!.firstElementChild!;
}

describe("LemonModal outside dismissal default action", () => {
  it("cancels the outside mousedown before the caller restores its opener", () => {
    const event = new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 });
    let preventedAtClose = false;
    const closed = vi.fn(() => { preventedAtClose = event.defaultPrevented; });
    render(<RestoringDialog onClose={closed} />);
    const opener = screen.getByRole("button", { name: "Open task" }); opener.focus(); fireEvent.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Task" });
    fireEvent(backdrop(dialog), event);
    expect(closed).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog", { name: "Task" })).toBeNull();
    expect(document.activeElement).toBe(opener);
    expect(preventedAtClose).toBe(true);
    expect(event.defaultPrevented).toBe(true);
  });

  it("does not cancel default pointer actions or close for controls inside the dialog", () => {
    const closed = vi.fn(); render(<RestoringDialog onClose={closed} />);
    fireEvent.click(screen.getByRole("button", { name: "Open task" }));
    for (const target of [screen.getByRole("textbox", { name: "Task name" }), screen.getByRole("button", { name: "Inside action" })]) {
      const event = new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 });
      fireEvent(target, event); expect(event.defaultPrevented).toBe(false);
    }
    expect(closed).not.toHaveBeenCalled(); expect(screen.getByRole("dialog", { name: "Task" })).toBeTruthy();
  });

  it("leaves a forced-action modal and its outside default action untouched", () => {
    const closed = vi.fn(); render(<RestoringDialog forceUserAction onClose={closed} />);
    fireEvent.click(screen.getByRole("button", { name: "Open task" }));
    const dialog = screen.getByRole("dialog", { name: "Task" });
    const event = new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 });
    fireEvent(backdrop(dialog), event);
    expect(event.defaultPrevented).toBe(false); expect(closed).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Task" })).toBe(dialog);
  });

  it("does not let a lower backdrop dismiss its dialog behind a newer modal", () => {
    render(<DialogStack />);
    const older = screen.getByRole("dialog", { name: "Project" });
    const newer = screen.getByRole("dialog", { name: "Shortcuts" });
    const lowerEvent = new MouseEvent("mousedown", { bubbles: true, cancelable: true });
    fireEvent(backdrop(older), lowerEvent);
    expect(screen.queryByRole("dialog", { name: "Project" })).toBe(older);
    expect(lowerEvent.defaultPrevented).toBe(false);
    const topEvent = new MouseEvent("mousedown", { bubbles: true, cancelable: true });
    fireEvent(backdrop(newer), topEvent);
    expect(topEvent.defaultPrevented).toBe(true);
    expect(screen.queryByRole("dialog", { name: "Shortcuts" })).toBeNull();
    expect(screen.getByRole("dialog", { name: "Project" })).toBe(older);
  });
});

describe("main reading appearance dismissal", () => {
  it("preserves the chosen appearance and returns focus after outside dismissal", async () => {
    const preferences = [THEME_KEY, READING_LIGHT_KEY].map((key) => ({ key, value: localStorage.getItem(key) }));
    const attributes = ["data-theme", "data-theme-pref", "data-reading-light"]
      .map((name) => ({ name, value: document.documentElement.getAttribute(name) }));
    try {
      render(<ReadingAppearance />);
      const trigger = screen.getByRole("button", { name: "Reading appearance" });
      trigger.focus();
      fireEvent.click(trigger);
      fireEvent.change(screen.getByLabelText("Reading theme"), { target: { value: "dark" } });
      fireEvent.change(screen.getByLabelText("Page light"), { target: { value: "soft" } });
      const dialog = screen.getByRole("dialog", { name: "Make yourself comfortable" });
      const outside = new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 });
      fireEvent(backdrop(dialog), outside);
      expect(outside.defaultPrevented).toBe(true);
      expect(screen.queryByRole("dialog", { name: "Make yourself comfortable" })).toBeNull();
      await waitFor(() => expect(document.activeElement).toBe(trigger));
      expect(localStorage.getItem(THEME_KEY)).toBe("dark");
      expect(localStorage.getItem(READING_LIGHT_KEY)).toBe("soft");
      fireEvent.click(trigger);
      expect(screen.getByLabelText<HTMLSelectElement>("Reading theme").value).toBe("dark");
      expect(screen.getByLabelText<HTMLSelectElement>("Page light").value).toBe("soft");
      fireEvent.keyDown(screen.getByLabelText("Reading theme"), { key: "Escape" });
      expect(screen.queryByRole("dialog", { name: "Make yourself comfortable" })).toBeNull();
      await waitFor(() => expect(document.activeElement).toBe(trigger));
    } finally {
      cleanup();
      for (const { key, value } of preferences) {
        if (value === null) localStorage.removeItem(key);
        else localStorage.setItem(key, value);
      }
      for (const { name, value } of attributes) {
        if (value === null) document.documentElement.removeAttribute(name);
        else document.documentElement.setAttribute(name, value);
      }
    }
  });
});
