import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ReadingTypography, { ReadingTypographyControls } from "./ReadingTypography";
import ReadingColumn from "./ReadingColumn";
import { DEFAULT_READING_TYPOGRAPHY, resetReadingTypography, TYPOGRAPHY_STORAGE_KEY } from "../../lib/readingTypography";

beforeEach(() => {
  window.localStorage.clear();
  resetReadingTypography();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

function view() {
  return render(<><ReadingTypographyControls /><ReadingColumn assetId="book-font-fixture" chunkId="chunk-font-fixture" text="A passage worth reading." /></>);
}

describe("reading type", () => {
  it("explains a failed font load and allows the installed-font choice", async () => {
    const load = vi.fn().mockRejectedValue(new Error("Font download failed"));
    Object.defineProperty(document, "fonts", { configurable: true, value: { load } });
    try {
      const { container } = view();
      await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Reload this page or choose another font"));
      fireEvent.change(screen.getByRole("combobox", { name: "Reading font" }), { target: { value: "system" } });
      expect(screen.queryByRole("status")).toBeNull();
      expect(container.querySelector("article")?.style.fontFamily).toContain("Georgia");
      expect(load).toHaveBeenCalledTimes(1);
    } finally {
      Reflect.deleteProperty(document, "fonts");
    }
  });
  it("offers the curated portfolio and applies the chosen face to the actual attributed reader", () => {
    const { container } = view();
    expect(screen.getByRole("combobox", { name: "Reading font" }).querySelectorAll("option")).toHaveLength(5);
    fireEvent.change(screen.getByRole("combobox", { name: "Reading font" }), { target: { value: "atkinson" } });
    const article = container.querySelector("article");
    expect(article?.style.fontFamily).toContain("Atkinson Hyperlegible Next");
    expect(article?.getAttribute("data-akb-asset-id")).toBe("book-font-fixture");
    expect(article?.getAttribute("data-akb-chunk-id")).toBe("chunk-font-fixture");
    expect(JSON.parse(window.localStorage.getItem(TYPOGRAPHY_STORAGE_KEY) ?? "null").font).toBe("atkinson");
  });

  it("changes size, spacing and width independently, then resets them", () => {
    const { container } = view();
    fireEvent.change(screen.getByRole("slider", { name: /Text size/ }), { target: { value: "24" } });
    fireEvent.change(screen.getByRole("slider", { name: /Line spacing/ }), { target: { value: "1.9" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Line width" }), { target: { value: "78" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Letter spacing" }), { target: { value: "0.03" } });
    const article = container.querySelector("article");
    expect(article?.style.fontSize).toBe("1.5rem");
    expect(article?.style.lineHeight).toBe("1.9");
    expect(article?.style.maxWidth).toBe("78ch");
    expect(article?.style.letterSpacing).toBe("0.03em");
    fireEvent.click(screen.getByRole("button", { name: "Reset reading type" }));
    expect(article?.style.fontSize).toBe("1.25rem");
    expect(article?.style.maxWidth).toBe("66ch");
  });

  it("updates mounted readers from other tabs and falls back when that tab clears storage", () => {
    const { container } = view();
    act(() => {
      window.localStorage.setItem(TYPOGRAPHY_STORAGE_KEY, JSON.stringify({ ...DEFAULT_READING_TYPOGRAPHY, version: 1, font: "literata", size: 21 }));
      window.dispatchEvent(new StorageEvent("storage", { key: TYPOGRAPHY_STORAGE_KEY, storageArea: window.localStorage }));
    });
    expect(container.querySelector("article")?.style.fontFamily).toContain("Literata");
    expect(screen.getByRole("slider", { name: /Text size/ }).getAttribute("aria-valuetext")).toBe("21 pixels");
    act(() => {
      window.localStorage.clear();
      window.dispatchEvent(new StorageEvent("storage", { key: null, storageArea: window.localStorage }));
    });
    expect(container.querySelector("article")?.style.fontFamily).toContain("Source Serif 4");
  });

  it("ignores unrelated and session-storage events", () => {
    const { container } = view();
    fireEvent.change(screen.getByRole("combobox", { name: "Reading font" }), { target: { value: "source-sans" } });
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "unrelated" }));
      window.dispatchEvent(new StorageEvent("storage", { key: TYPOGRAPHY_STORAGE_KEY, storageArea: window.sessionStorage }));
    });
    expect(container.querySelector("article")?.style.fontFamily).toContain("Source Sans 3");
  });

  it("restores persisted changes made while no reading surface was mounted", () => {
    const first = view();
    first.unmount();
    window.localStorage.setItem(TYPOGRAPHY_STORAGE_KEY, JSON.stringify({ ...DEFAULT_READING_TYPOGRAPHY, version: 1, font: "source-sans", size: 25 }));
    const next = view();
    expect(next.container.querySelector("article")?.style.fontFamily).toContain("Source Sans 3");
    expect(next.container.querySelector("article")?.style.fontSize).toBe("1.5625rem");
  });

  it("keeps a session choice when persistence fails and recovers from corrupt stored data", () => {
    const { container } = view();
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("Storage blocked"); });
    fireEvent.change(screen.getByRole("combobox", { name: "Reading font" }), { target: { value: "source-sans" } });
    expect(container.querySelector("article")?.style.fontFamily).toContain("Source Sans 3");
    vi.restoreAllMocks();
    act(() => {
      window.localStorage.setItem(TYPOGRAPHY_STORAGE_KEY, "{bad json");
      window.dispatchEvent(new StorageEvent("storage", { key: TYPOGRAPHY_STORAGE_KEY }));
    });
    expect(container.querySelector("article")?.style.fontFamily).toContain("Source Serif 4");
  });

  it("preserves the non-attributed preview and sanitized HTML structure while changing fonts", () => {
    const { container } = render(<ReadingColumn text="<h2>Evidence</h2><p><em>Read carefully.</em> <strong>Keep citations.</strong></p>" contentFormat="html" />);
    const article = container.querySelector("article");
    expect(article?.getAttribute("data-akb-asset-id")).toBeNull();
    expect(article?.style.fontFamily).toContain("Source Serif 4");
    expect(container.querySelector("h2")?.textContent).toBe("Evidence");
    expect(container.querySelector("em")?.textContent).toBe("Read carefully.");
  });

  it("opens in a portal and returns focus on Escape", () => {
    render(<ReadingTypography />);
    const trigger = screen.getByRole("button", { name: "Reading type" });
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "Reading type" })).toBeTruthy();
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});
