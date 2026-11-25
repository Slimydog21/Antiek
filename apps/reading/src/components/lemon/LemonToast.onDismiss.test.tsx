/**
 * LemonToast.onDismiss.test.tsx — SPR-10: `dismiss(id)` runs the item's
 * onDismiss exactly once, after the listeners have seen the removal; items
 * without one behave as before.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";

import { LemonToastViewport, toast } from "./LemonToast";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("LemonToast onDismiss", () => {
  it("runs once per dismiss, after the item has left the queue (a re-entrant dismiss inside the hook is a no-op)", () => {
    vi.useFakeTimers();
    render(<LemonToastViewport />);
    let id = 0;
    const onDismiss = vi.fn(() => { toast.dismiss(id); });
    act(() => { id = toast.info("with hook", { ttl: 60_000, onDismiss }); });
    expect(screen.getByText("with hook")).toBeTruthy();
    act(() => { toast.dismiss(id); });
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("with hook")).toBeNull();
    act(() => { toast.dismiss(id); });
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("the ttl timer and the ✕ button both reach onDismiss; an item without it dismisses as before", () => {
    vi.useFakeTimers();
    render(<LemonToastViewport />);
    const byTtl = vi.fn();
    const byButton = vi.fn();
    act(() => { toast.ok("ttl one", { ttl: 500, onDismiss: byTtl }); });
    act(() => { toast.ok("button one", { ttl: 60_000, onDismiss: byButton }); });
    act(() => { toast.ok("plain one", { ttl: 60_000 }); });
    act(() => { vi.advanceTimersByTime(500); });
    expect(byTtl).toHaveBeenCalledTimes(1);
    const dismissButtons = screen.getAllByRole("button", { name: "Dismiss" });
    expect(dismissButtons).toHaveLength(2);
    act(() => { dismissButtons[0].click(); });
    expect(byButton).toHaveBeenCalledTimes(1);
    act(() => { screen.getAllByRole("button", { name: "Dismiss" })[0].click(); });
    expect(screen.queryByText("plain one")).toBeNull();
  });
});
