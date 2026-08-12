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

const stylesWithFork = {
  styles: [
    ...styles.styles,
    {
      name: "field-notes",
      label: "Field notes",
      description: "A personal fork",
      builtin: false,
      source_fidelity: true,
      theme_css: ":root { --x: 1; }",
    },
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
      if (url === "/styles" && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        return Promise.resolve(
          json(
            {
              name: body.name,
              label: body.label,
              description: body.description ?? "",
              builtin: false,
              source_fidelity: Boolean(body.source_fidelity),
              theme_css: body.theme_css ?? "",
            },
            201,
          ),
        );
      }
      if (typeof url === "string" && url.startsWith("/styles/") && init?.method === "DELETE") {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
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
    expect(apiFetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/artifacts/artifact-7/render"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows an honest unavailable state", async () => {
    apiFetchMock.mockRejectedValueOnce(new Error("backend offline"));
    render(<StyleWheel artifactId="artifact-7" />);
    expect((await screen.findByRole("alert")).textContent).toContain("Styles unavailable · backend offline");
  });

  it("shows an honest empty wheel when no styles load", async () => {
    apiFetchMock.mockImplementation((input: RequestInfo | URL) => {
      if (String(input) === "/styles") return Promise.resolve(json({ styles: [] }));
      return Promise.resolve(html());
    });
    render(<StyleWheel artifactId="artifact-7" />);
    expect((await screen.findByText(/Empty wheel/)).textContent).toContain("Empty wheel");
    expect(screen.getByRole("button", { name: /Create a style/ })).toBeTruthy();
  });

  it("restores the persisted style from the style-less preview", async () => {
    apiFetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/styles") return Promise.resolve(json(styles));
      return Promise.resolve(html("preview", "folio"));
    });
    render(<StyleWheel artifactId="artifact-7" />);
    expect((await screen.findByRole("option", { name: /Folio/ })).getAttribute("aria-selected")).toBe("true");
    expect(apiFetchMock).toHaveBeenCalledWith(
      "/artifacts/artifact-7/render",
      expect.objectContaining({ method: "GET" }),
    );
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
    await waitFor(() =>
      expect(
        apiFetchMock.mock.calls.some(
          ([url, init]) =>
            String(url) === "/styles" &&
            init?.method === "POST" &&
            String(init.body).includes(secretCss),
        ),
      ).toBe(true),
    );
    for (const [url] of apiFetchMock.mock.calls.filter(([url]) => String(url).includes("/render"))) {
      expect(String(url)).not.toContain("private-preview-token");
    }
  });

  it("seeds the fork form from the selected builtin with provenance", async () => {
    render(<StyleWheel artifactId="artifact-7" />);
    await screen.findByRole("option", { name: /Antiek/ });
    fireEvent.click(screen.getByRole("button", { name: /Fork “Antiek”/ }));
    expect((screen.getByLabelText("Slug") as HTMLInputElement).value).toBe("antiek-fork");
    expect((screen.getByLabelText("Label") as HTMLInputElement).value).toContain("fork");
    expect(screen.getByText(/seeded from/).textContent).toContain("Antiek");
    fireEvent.change(screen.getByLabelText("Slug"), { target: { value: "field-notes" } });
    fireEvent.change(screen.getByLabelText("Label"), { target: { value: "Field notes" } });
    fireEvent.submit(screen.getByRole("button", { name: "Save fork" }).closest("form")!);
    await screen.findByRole("option", { name: /Field notes/ });
    expect(screen.getByText(/forked from Antiek/)).toBeTruthy();
  });

  it("deletes a user fork with confirm and refuses to offer delete on builtins", async () => {
    apiFetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/styles") return Promise.resolve(json(stylesWithFork));
      if (url === "/styles/field-notes" && init?.method === "DELETE") {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (url.includes("/render")) {
        const style = new URL(url, "http://test").searchParams.get("style") ?? "antiek";
        return Promise.resolve(html("preview", style));
      }
      return Promise.resolve(html());
    });
    render(<StyleWheel artifactId="artifact-7" />);
    await screen.findByRole("option", { name: /Field notes/ });
    // Builtin selected first — no delete affordance
    expect(screen.queryByRole("button", { name: /Delete fork/ })).toBeNull();
    fireEvent.click(screen.getByRole("option", { name: /Field notes/ }));
    const del = await screen.findByRole("button", { name: /Delete fork Field notes/ });
    fireEvent.click(del);
    // Two-step confirm
    fireEvent.click(screen.getByRole("button", { name: /Confirm delete Field notes/ }));
    await waitFor(() =>
      expect(
        apiFetchMock.mock.calls.some(
          ([url, init]) => String(url) === "/styles/field-notes" && init?.method === "DELETE",
        ),
      ).toBe(true),
    );
    await waitFor(() => expect(screen.queryByRole("option", { name: /Field notes/ })).toBeNull());
  });

  it("surfaces delete errors honestly without removing the fork", async () => {
    apiFetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/styles") return Promise.resolve(json(stylesWithFork));
      if (url === "/styles/field-notes" && init?.method === "DELETE") {
        return Promise.resolve(
          json({ detail: "cannot remove builtin style 'field-notes'" }, 409),
        );
      }
      if (url.includes("/render")) {
        const style = new URL(url, "http://test").searchParams.get("style") ?? "field-notes";
        return Promise.resolve(html("preview", style));
      }
      return Promise.resolve(html());
    });
    render(<StyleWheel artifactId="artifact-7" />);
    fireEvent.click(await screen.findByRole("option", { name: /Field notes/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Delete fork Field notes/ }));
    fireEvent.click(screen.getByRole("button", { name: /Confirm delete Field notes/ }));
    expect((await screen.findByRole("alert")).textContent).toContain("cannot remove builtin");
    expect(screen.getByRole("option", { name: /Field notes/ })).toBeTruthy();
  });

  it("aborts and ignores an old apply when the selected style changes", async () => {
    let resolveApply!: (value: Response) => void;
    let applySignal: AbortSignal | undefined;
    apiFetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/styles") return Promise.resolve(json(styles));
      if (init?.method === "POST" && url.includes("/render")) {
        applySignal = init.signal ?? undefined;
        return new Promise<Response>((resolve) => {
          resolveApply = resolve;
        });
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
