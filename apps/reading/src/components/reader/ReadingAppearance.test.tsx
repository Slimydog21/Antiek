import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { READING_LIGHT_KEY } from "../../design/theme";
import ReadingAppearance, { ReadingLightControl } from "./ReadingAppearance";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
  for (const name of ["data-reading-light", "data-theme", "data-theme-pref"]) document.documentElement.removeAttribute(name);
});

describe("reading appearance", () => {
  it("applies Softer immediately, saves it, and restores it on remount", () => {
    const first = render(<ReadingLightControl />);
    fireEvent.change(screen.getByLabelText("Page light"), { target: { value: "soft" } });
    expect(document.documentElement.dataset.readingLight).toBe("soft");
    expect(localStorage.getItem(READING_LIGHT_KEY)).toBe("soft");
    first.unmount();
    document.documentElement.removeAttribute("data-reading-light");
    render(<ReadingLightControl />);
    expect(screen.getByRole<HTMLSelectElement>("combobox").value).toBe("soft");
  });

  it("updates mounted controls when another tab changes or clears the preference", () => {
    render(<ReadingLightControl />);
    act(() => window.dispatchEvent(new StorageEvent("storage", { key: READING_LIGHT_KEY, newValue: "soft" })));
    expect(screen.getByRole<HTMLSelectElement>("combobox").value).toBe("soft");
    act(() => window.dispatchEvent(new StorageEvent("storage", { key: null })));
    expect(screen.getByRole<HTMLSelectElement>("combobox").value).toBe("standard");
  });

  it("keeps the choice for the session if storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    render(<ReadingLightControl />);
    expect(() => fireEvent.change(screen.getByLabelText("Page light"), { target: { value: "soft" } })).not.toThrow();
    expect(document.documentElement.dataset.readingLight).toBe("soft");
    expect(screen.getByRole<HTMLSelectElement>("combobox").value).toBe("soft");
  });

  it("lets readers change theme and closes on Escape with focus returned", async () => {
    render(<ReadingAppearance />);
    const trigger = screen.getByRole("button", { name: "Reading appearance" });
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "Make yourself comfortable" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Reading theme"), { target: { value: "dark" } });
    expect(document.documentElement.dataset.theme).toBe("dark");
    fireEvent.keyDown(screen.getByLabelText("Reading theme"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });
});
