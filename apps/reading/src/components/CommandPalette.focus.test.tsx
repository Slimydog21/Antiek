/**
 * CommandPalette — a modal dialog that behaves like one (audit M7, B2):
 * Tab stays inside it, closing it gives focus back to what opened it, and
 * it sits on the modal rung of the z ladder instead of a hand-rolled z-50.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import CommandPalette from "./CommandPalette";

const apiFetchMock = apiFetch as unknown as ReturnType<typeof vi.fn>;

function openPalette(): void {
  fireEvent(window, new Event("antiek:palette:toggle"));
}

function renderWithOpener() {
  render(
    <MemoryRouter>
      <button type="button">Search</button>
      <CommandPalette />
    </MemoryRouter>,
  );
  const opener = screen.getByRole("button", { name: "Search" });
  opener.focus();
  return opener;
}

describe("CommandPalette — focus contract", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue({ ok: false, status: 404 });
  });
  afterEach(cleanup);

  it("Esc closes it and gives focus back to the opener", async () => {
    const opener = renderWithOpener();
    act(() => openPalette());
    const input = await screen.findByPlaceholderText(/Type a route/);
    await waitFor(() => expect(document.activeElement).toBe(input));
    act(() => {
      fireEvent.keyDown(window, { key: "Escape" });
    });
    expect(screen.queryByRole("dialog", { name: "Command palette" })).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it("Tab from the last control wraps to the first, Shift-Tab from the first to the last", async () => {
    renderWithOpener();
    act(() => openPalette());
    const dialog = await screen.findByRole("dialog", { name: "Command palette" });
    const input = await screen.findByPlaceholderText(/Type a route/);
    await waitFor(() => expect(document.activeElement).toBe(input));
    const controls = Array.from(dialog.querySelectorAll<HTMLElement>("button, input"));
    const last = controls[controls.length - 1];
    last.focus();
    fireEvent.keyDown(last, { key: "Tab" });
    expect(document.activeElement).toBe(input);
    fireEvent.keyDown(input, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
  });

  it("is the dialog itself (not its scrim) and sits on the modal rung", async () => {
    renderWithOpener();
    act(() => openPalette());
    const dialog = await screen.findByRole("dialog", { name: "Command palette" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    const scrim = dialog.parentElement as HTMLElement;
    expect(scrim.className).toMatch(/\bz-modal\b/);
    expect(scrim.className).not.toMatch(/\bz-50\b/);
    expect(dialog.className).toMatch(/\bshadow-island\b/);
    expect(dialog.className).not.toMatch(/shadow-2xl/);
  });

  it("the typed query keeps the ink colour at night (no bare dark:text-moonlight)", async () => {
    renderWithOpener();
    act(() => openPalette());
    const input = await screen.findByPlaceholderText(/Type a route/);
    expect(input.className).not.toMatch(/(^|\s)dark:text-moonlight(\s|$)/);
    expect(input.className).toMatch(/dark:placeholder:text-moonlight/);
  });
});
