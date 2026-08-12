import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>("../../lib/api");
  return { ...actual, API_BASE: "", apiFetch: apiFetchMock };
});

import StyleWheel from "./StyleWheel";

const styles = {
  styles: [
    { name: "antiek", label: "Antiek", description: "Default", builtin: true, source_fidelity: true, theme_css: "" },
    { name: "folio", label: "Folio", description: "Editorial", builtin: true, source_fidelity: false, theme_css: "" },
  ],
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const HASH = "a".repeat(64);

function html(version = "preview", style = "antiek") {
  return new Response("<!doctype html><title>Preview</title>", {
    headers: {
      "Content-Type": "text/html",
      "X-Artifact-ID": "artifact-7",
      "X-Artifact-Style": style,
      "X-Artifact-Version": version,
      "X-Content-SHA256": HASH,
    },
  });
}

describe("StyleWheel", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:preview");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    apiFetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/styles" && init?.method === "POST") return Promise.resolve(json(styles.styles[1], 201));
      if (url === "/styles") return Promise.resolve(json(styles));
      if (url.includes("/render")) {
        const style = new URL(url, "http://test").searchParams.get("style") ?? "antiek";
        return Promise.resolve(html(init?.method === "POST" ? "3" : "preview", style));
      }
      return Promise.resolve(html("3"));
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("loads styles and gives keyboard selection parity", async () => {
    render(<StyleWheel artifactId="artifact-7" />);
    const first = await screen.findByRole("option", { name: /Antiek/ });
    await waitFor(() => expect(first.getAttribute("aria-selected")).toBe("true"));
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(screen.getByRole("option", { name: /Folio/ }).getAttribute("aria-selected")).toBe("true");
  });

  it("supports vertical arrow parity and declares horizontal orientation", async () => {
    render(<StyleWheel artifactId="artifact-7" />);
    const listbox = await screen.findByRole("listbox");
    expect(listbox.getAttribute("aria-orientation")).toBe("horizontal");
    const first = screen.getByRole("option", { name: /Antiek/ });
    fireEvent.keyDown(first, { key: "ArrowDown" });
    expect(screen.getByRole("option", { name: /Folio/ }).getAttribute("aria-selected")).toBe("true");
  });

  it("previews with a sandbox and applies a durable version receipt", async () => {
    render(<StyleWheel artifactId="artifact-7" />);
    const frame = await screen.findByTitle("Antiek artifact preview");
    expect(frame.getAttribute("sandbox")).toBe("");
    fireEvent.click(screen.getByRole("button", { name: /Apply Antiek/ }));
    expect((await screen.findByText("Version 3 saved")).textContent).toBe("Version 3 saved");
    expect(apiFetchMock).toHaveBeenCalledWith(expect.stringContaining("/artifacts/artifact-7/render"), expect.objectContaining({ method: "POST" }));
  });

  it("shows an honest unavailable state", async () => {
    apiFetchMock.mockRejectedValueOnce(new Error("backend offline"));
    render(<StyleWheel artifactId="artifact-7" />);
    expect((await screen.findByRole("alert")).textContent).toContain("Styles unavailable · backend offline");
  });

  it("restores the persisted style from the style-less preview", async () => {
    apiFetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/styles") return Promise.resolve(json(styles));
      return Promise.resolve(html("preview", "folio"));
    });
    render(<StyleWheel artifactId="artifact-7" />);
    expect((await screen.findByRole("option", { name: /Folio/ })).getAttribute("aria-selected")).toBe("true");
    expect(apiFetchMock).toHaveBeenCalledWith("/artifacts/artifact-7/render", expect.objectContaining({ method: "GET" }));
  });

  it("keeps fork CSS confined to the style save body", async () => {
    render(<StyleWheel artifactId="artifact-7" />);
    await screen.findByRole("listbox");
    fireEvent.click(screen.getByRole("button", { name: "Fork a style" }));
    fireEvent.change(screen.getByLabelText("Slug"), { target: { value: "field-notes" } });
    fireEvent.change(screen.getByLabelText("Label"), { target: { value: "Field notes" } });
    const secretCss = ":root { --private-preview-token: rgb(18 52 86); }";
    fireEvent.change(screen.getByLabelText("Theme CSS"), { target: { value: secretCss } });
    fireEvent.submit(screen.getByRole("button", { name: "Save fork" }).closest("form")!);
    await waitFor(() => expect(apiFetchMock.mock.calls.some(([url, init]) =>
      String(url) === "/styles" && init?.method === "POST" && String(init.body).includes(secretCss),
    )).toBe(true));
    for (const [url] of apiFetchMock.mock.calls.filter(([url]) => String(url).includes("/render"))) {
      expect(String(url)).not.toContain("private-preview-token");
    }
  });

  it("aborts and ignores an old apply when the selected style changes", async () => {
    let resolveApply!: (value: Response) => void;
    let applySignal: AbortSignal | undefined;
    apiFetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/styles") return Promise.resolve(json(styles));
      if (init?.method === "POST" && url.includes("/render")) {
        applySignal = init.signal ?? undefined;
        return new Promise<Response>((resolve) => { resolveApply = resolve; });
      }
      const style = new URL(url, "http://test").searchParams.get("style") ?? "antiek";
      return Promise.resolve(html("preview", style));
    });
    render(<StyleWheel artifactId="artifact-7" />);
    await screen.findByTitle("Antiek artifact preview");
    fireEvent.click(screen.getByRole("button", { name: "Apply Antiek" }));
    fireEvent.click(screen.getByRole("option", { name: /Folio/ }));
    expect(applySignal?.aborted).toBe(true);
    resolveApply(html("8", "antiek"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByText("Version 8 saved")).toBeNull();
  });

  it("revokes preview blobs when replaced and unmounted", async () => {
    const { unmount } = render(<StyleWheel artifactId="artifact-7" />);
    await screen.findByTitle("Antiek artifact preview");
    fireEvent.click(screen.getByRole("option", { name: /Folio/ }));
    await screen.findByTitle("Folio artifact preview");
    expect(URL.revokeObjectURL).toHaveBeenCalled();
    const before = vi.mocked(URL.revokeObjectURL).mock.calls.length;
    unmount();
    expect(vi.mocked(URL.revokeObjectURL).mock.calls.length).toBeGreaterThan(before);
  });
});
