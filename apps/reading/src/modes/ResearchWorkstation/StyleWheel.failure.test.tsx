/**
 * FFX SPR-03 (F-07): the version download rendered
 * "Download unavailable (HTTP n)." (StyleWheel.tsx:315).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StyleWheel from "./StyleWheel";

const STYLES = {
  styles: [
    { name: "antiek", label: "Antiek", description: "Default", builtin: true, source_fidelity: true, theme_css: "" },
  ],
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function html(version: string) {
  return new Response("<!doctype html><title>Preview</title>", {
    headers: {
      "Content-Type": "text/html",
      "X-Artifact-ID": "artifact-7",
      "X-Artifact-Style": "antiek",
      "X-Artifact-Version": version,
      "X-Content-SHA256": "a".repeat(64),
      "X-Source-SHA256": "b".repeat(64),
    },
  });
}

/** The `what` passed to describeFailure is plain words, so the title is
 *  "Couldn't <what>." and not the "That didn't work." fallback (#3538). */
function expectPlainTitle(text: string) {
  expect(text).toMatch(/^Couldn't [a-z][a-z ']*\./i);
}

function expectHonest(text: string) {
  expect(text).not.toMatch(/\b[45]\d\d\b/);
  expect(text).not.toMatch(/\/[a-z-]+/);
  expect(text).not.toContain("Failed to fetch");
  expect(text).not.toContain("HTTP");
}

const fetchMock = vi.fn();
let download: () => Promise<Response>;

beforeEach(() => {
  vi.stubEnv("VITE_ANTIEK_FEEDBACK_ENABLED", "false");
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:preview");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/versions/")) return download();
    if (url.endsWith("/styles")) return json(STYLES);
    if (url.includes("/render")) return html(init?.method === "POST" ? "3" : "preview");
    return json({ detail: "unexpected" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function applyAndDownload() {
  render(<StyleWheel artifactId="artifact-7" investigationId="inv-7" />);
  await screen.findByTitle("Antiek artifact preview", {}, { timeout: 5000 });
  const apply = screen.getByRole("button", { name: /Apply Antiek/ }) as HTMLButtonElement;
  await waitFor(() => expect(apply.disabled).toBe(false));
  fireEvent.click(apply);
  await screen.findByText("Version 3 saved", {}, { timeout: 5000 });
  fireEvent.click(screen.getByRole("button", { name: "Download version 3" }));
}

describe("StyleWheel version download — honest failure", () => {
  it("a 503 shows plain copy and Try again re-requests the same version", async () => {
    let calls = 0;
    download = async () => (++calls === 1 ? json({ detail: "x" }, 503) : new Response("<p>v3</p>"));
    await applyAndDownload();
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expectPlainTitle(alert.textContent ?? "");
    expect(alert.textContent).toContain("Couldn't download this version.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    const versionCalls = fetchMock.mock.calls.filter(([u]) => String(u).includes("/versions/"));
    expect(versionCalls).toHaveLength(2);
    expect(String(versionCalls[1][0])).toBe(String(versionCalls[0][0]));
  });

  it("a network TypeError never shows 'Failed to fetch'", async () => {
    download = async () => {
      throw new TypeError("Failed to fetch");
    };
    await applyAndDownload();
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expectPlainTitle(alert.textContent ?? "");
  });
});
