import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StrictMode } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import Stats, { StatsView } from "./index";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));
beforeEach(() => apiFetchMock.mockReset());
afterEach(cleanup);

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
function response(body: unknown, ok = true) {
  return { ok, json: async () => body } as Response;
}

describe("Substrate Atlas", () => {
  it("shows Unknown for missing and invalid keys, but locale-formats known counts", () => {
    render(
      <StatsView
        data={{
          counts: {
            investigations: 1234567,
            documents: -1,
            chunks: Number.NaN,
          },
          warnings: [],
        }}
      />,
    );
    expect(screen.getByText((1234567).toLocaleString())).toBeTruthy();
    expect(screen.getAllByText("Unknown").length).toBeGreaterThan(2);
  });

  it("reduces warnings to a bounded count and never displays payload strings", () => {
    render(
      <StatsView
        data={{
          counts: {},
          warnings: ["secret_table failed at db.internal", { detail: "token" }],
        }}
      />,
    );
    expect(
      screen.getByText(/Some substrate areas could not be measured/),
    ).toBeTruthy();
    expect(screen.getByText("2 areas")).toBeTruthy();
    expect(screen.queryByText(/secret_table|db\.internal|token/)).toBeNull();
  });

  it("uses fixed safe error copy and does not display transport details", async () => {
    apiFetchMock.mockResolvedValue(response({}, false));
    render(<Stats />);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Survey unavailable",
    );
    expect(document.body.textContent).not.toContain("HTTP");
    expect(document.body.textContent).not.toContain("/stats");
  });

  it("disables refresh while loading and ignores an older response", async () => {
    const first = deferred<Response>();
    const second = deferred<Response>();
    apiFetchMock
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    render(<Stats />);
    const button = screen.getByRole("button");
    expect(button.hasAttribute("disabled")).toBe(true);
    first.resolve(response({ counts: { investigations: 1 }, warnings: [] }));
    await screen.findByText("1");
    fireEvent.click(button);
    expect(button.hasAttribute("disabled")).toBe(true);
    second.resolve(response({ counts: { investigations: 22 }, warnings: [] }));
    await screen.findByText("22");
  });

  it("suppresses an older StrictMode request after the newer request completes", async () => {
    const first = deferred<Response>();
    const second = deferred<Response>();
    apiFetchMock
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    render(
      <StrictMode>
        <Stats />
      </StrictMode>,
    );
    second.resolve(response({ counts: { investigations: 22 }, warnings: [] }));
    await screen.findByText("22");
    first.resolve(response({ counts: { investigations: 1 }, warnings: [] }));
    await waitFor(() => expect(screen.queryByText("1")).toBeNull());
  });

  it("keeps the environment decorative and pointer-inert", () => {
    const { container } = render(
      <StatsView data={{ counts: {}, warnings: [] }} />,
    );
    const image = container.querySelector("img")!;
    expect(image.getAttribute("alt")).toBe("");
    expect(image.getAttribute("aria-hidden")).toBe("true");
    expect(image.getAttribute("draggable")).toBe("false");
  });
});
