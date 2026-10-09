import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { apiFetch, listInvestigations } from "../../lib/api";
import type { curateBooks } from "../../api/books";
import Library from "./index";

const { request, investigations, curate } = vi.hoisted(() => ({
  request: vi.fn<typeof apiFetch>(),
  investigations: vi.fn<typeof listInvestigations>(),
  curate: vi.fn<typeof curateBooks>(),
}));
vi.mock("../../lib/api", async (original) => ({
  ...await original<typeof import("../../lib/api")>(),
  apiFetch: request,
  listInvestigations: investigations,
}));
vi.mock("../../api/books", async (original) => ({
  ...await original<typeof import("../../api/books")>(),
  curateBooks: curate,
}));

function failure(hint: string | null, status = 503) {
  return new Response("Ignored failure payload", {
    status, headers: hint === null ? undefined : { "Retry-After": hint },
  });
}
function mount() { return render(<MemoryRouter><Library /></MemoryRouter>); }
async function flush() { await act(async () => {}); }
async function advance(ms: number) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}
function failedShelf() {
  expect(screen.getByRole("alert").textContent).toContain("library is busy");
  expect(screen.queryByRole("status")).toBeNull();
  expect(screen.getByRole("button", { name: "Retry catalog" })).toBeTruthy();
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "performance"] });
  request.mockReset().mockImplementation(async (input) => {
    expect(String(input)).toContain("/library?");
    return failure("2");
  });
  investigations.mockReset();
  curate.mockReset();
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false, media: query, onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  }));
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// Real client decoding and mounted scheduling over failure Responses only.
describe("Library server-directed automatic GET retries", () => {
  it("waits for the visible two-second server hint before retrying", async () => {
    mount(); await flush();
    expect(request).toHaveBeenCalledTimes(1);
    await advance(1999);
    expect(request).toHaveBeenCalledTimes(1);
    await advance(1);
    expect(request).toHaveBeenCalledTimes(2);
    await advance(1999);
    expect(request).toHaveBeenCalledTimes(2);
    await advance(1);
    expect(request).toHaveBeenCalledTimes(3);
    failedShelf();
    await advance(60000);
    expect(request).toHaveBeenCalledTimes(3);
    expect(investigations).not.toHaveBeenCalled();
    expect(curate).not.toHaveBeenCalled();
  });

  it("does not attribute an unknown 503 to a database holder", async () => {
    request.mockImplementation(async () => failure(null));
    mount(); await flush(); await advance(600);
    failedShelf();
    expect(screen.getByRole("alert").textContent).not.toContain("another job");
    expect(screen.getByRole("alert").textContent).not.toContain("database");
  });

  it("retains the explicit absent-hint 200ms and 400ms client policy", async () => {
    request.mockImplementation(async () => failure(null));
    mount(); await flush();
    await advance(199); expect(request).toHaveBeenCalledTimes(1);
    await advance(1); expect(request).toHaveBeenCalledTimes(2);
    await advance(399); expect(request).toHaveBeenCalledTimes(2);
    await advance(1); expect(request).toHaveBeenCalledTimes(3);
    failedShelf();
  });

  it.each(["", "0", "2.0", "Wed, 21 Oct 2015 07:28:00 GMT", "31"])(
    "requires manual recovery for malformed present hint %j", async (hint) => {
      request.mockImplementation(async () => failure(hint));
      mount(); await flush(); failedShelf();
      await advance(60000); expect(request).toHaveBeenCalledTimes(1);
      fireEvent.click(screen.getByRole("button", { name: "Retry catalog" }));
      await flush(); expect(request).toHaveBeenCalledTimes(2); failedShelf();
      expect(investigations).not.toHaveBeenCalled();
      expect(curate).not.toHaveBeenCalled();
    },
  );

  it("retires the timeout and abort listener when the Library unmounts", async () => {
    const view = mount(); await flush();
    const signal = request.mock.calls[0][1]?.signal;
    if (!signal) throw new Error("Catalogue GET lacks its captured signal");
    const removed = vi.spyOn(signal, "removeEventListener");
    view.unmount();
    expect(signal.aborted).toBe(true);
    expect(removed).toHaveBeenCalledWith("abort", expect.any(Function));
    expect(vi.getTimerCount()).toBe(0);
    await advance(60000); expect(request).toHaveBeenCalledTimes(1);
  });

  it("cancels an obsolete filter wait instead of issuing its late GET", async () => {
    mount(); await flush();
    const oldSignal = request.mock.calls[0][1]?.signal;
    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));
    await flush(); expect(request).toHaveBeenCalledTimes(2);
    expect(oldSignal?.aborted).toBe(true);
    await advance(2000); expect(request).toHaveBeenCalledTimes(3);
    expect(String(request.mock.calls[2][0])).toContain("filter=gated");
  });

  it("cancels an obsolete search wait and retains the submitted query", async () => {
    mount(); await flush();
    fireEvent.change(screen.getByRole("searchbox", { name: "Search catalog by title or author" }), {
      target: { value: "  epistemology  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search catalog" }));
    await flush(); expect(request).toHaveBeenCalledTimes(2);
    await advance(1999); expect(request).toHaveBeenCalledTimes(2);
    await advance(1); expect(request).toHaveBeenCalledTimes(3);
    expect(String(request.mock.calls[2][0])).toContain("search=epistemology");
  });

  it("counts the initial request time against the original retry cutoff", async () => {
    let release: (response: Response) => void = () => { throw new Error("Deferred request not admitted"); };
    request.mockImplementationOnce(() => new Promise<Response>((resolve) => { release = resolve; }));
    mount(); await flush();
    await advance(59000);
    await act(async () => { release(failure("2")); });
    failedShelf(); expect(request).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("does not renew the cutoff for a second thirty-second hint", async () => {
    request.mockImplementation(async () => failure("30"));
    mount(); await flush();
    await advance(30000); expect(request).toHaveBeenCalledTimes(2);
    failedShelf();
    await advance(30000); expect(request).toHaveBeenCalledTimes(2);
  });

  it("rechecks the cutoff after a wait settles and before the next GET", async () => {
    mount(); await flush();
    await act(async () => {
      vi.advanceTimersByTime(2000);
      vi.advanceTimersByTime(58000);
    });
    failedShelf(); expect(request).toHaveBeenCalledTimes(1);
  });

  it("does not retry a non-503 failure even with an admitted hint", async () => {
    request.mockImplementation(async () => failure("2", 500));
    mount(); await flush();
    expect(screen.getByRole("alert").textContent).toContain("catalog is unavailable");
    await advance(60000); expect(request).toHaveBeenCalledTimes(1);
  });
});
