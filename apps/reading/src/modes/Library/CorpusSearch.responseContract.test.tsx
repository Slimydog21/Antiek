import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CorpusSearch from "./CorpusSearch";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function submit(query: string) {
  fireEvent.change(screen.getByRole("searchbox", { name: "Search the corpus" }), { target: { value: query } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
}

function pendingResponse() {
  let resolve: (response: Response) => void = () => { throw new Error("unassigned synthetic transport"); };
  const promise = new Promise<Response>((complete) => { resolve = complete; });
  return { promise, resolve };
}

function expectNoResults(onOpen: ReturnType<typeof vi.fn>) {
  expect(screen.queryByRole("list", { name: "Search results" })).toBeNull();
  expect(screen.queryByText(/Nothing in your corpus matched/)).toBeNull();
  expect(onOpen).not.toHaveBeenCalled();
}

describe("Search response admission through the real client (synthetic failures only)", () => {
  it("shows an honest contract failure and retries the identical themed GET", async () => {
    const transport = vi.fn<typeof fetch>().mockImplementation(async () => new Response(
      '{"query":"synthetic-private-body","hits":null,"count":0}', { status: 200 },
    ));
    vi.stubGlobal("fetch", transport);
    const onOpen = vi.fn();
    render(<CorpusSearch onOpen={onOpen} themeContext={["agency"]} />);
    submit("free will");
    expect((await screen.findByRole("alert")).textContent).toBe("Search returned an invalid response.Retry search");
    expectNoResults(onOpen);
    expect(screen.queryByText(/synthetic-private-body/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry search" }));
    await screen.findByRole("alert");
    expect(transport).toHaveBeenCalledTimes(2);
    expect(transport.mock.calls[1]).toEqual(transport.mock.calls[0]);
    const [input, init] = transport.mock.calls[0];
    expect(new URL(String(input), "https://synthetic.invalid").searchParams.get("q"))
      .toBe("free will\n\n(in the context of: agency)");
    expect(init?.credentials).toBe("include");
    expectNoResults(onOpen);
  });

  it("keeps undecodable private response text out of the alert", async () => {
    const transport = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      '<html>synthetic-private-body</html>', { status: 200 },
    ));
    vi.stubGlobal("fetch", transport);
    const onOpen = vi.fn();
    render(<CorpusSearch onOpen={onOpen} />);
    submit("query");
    expect((await screen.findByRole("alert")).textContent).toContain("Search returned an invalid response.");
    expect(screen.queryByText(/synthetic-private-body/)).toBeNull();
    expectNoResults(onOpen);
  });

  it("does not let an old malformed response interrupt the newer pending search", async () => {
    const old = pendingResponse();
    const current = pendingResponse();
    const transport = vi.fn<typeof fetch>().mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    vi.stubGlobal("fetch", transport);
    const onOpen = vi.fn();
    render(<CorpusSearch onOpen={onOpen} />);
    submit("old query");
    submit("current query");
    await act(async () => { old.resolve(new Response("{}", { status: 200 })); });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: "Searching…" }).getAttribute("disabled")).not.toBeNull();
    await act(async () => { current.resolve(new Response("synthetic failure", { status: 503 })); });
    expect(screen.getByRole("alert").textContent).toContain("Search is temporarily unavailable.");
    expect(transport).toHaveBeenCalledTimes(2);
    expectNoResults(onOpen);
  });

  it("clear retires a late malformed response without showing Empty or an error", async () => {
    const late = pendingResponse();
    const transport = vi.fn<typeof fetch>().mockReturnValue(late.promise);
    vi.stubGlobal("fetch", transport);
    const onOpen = vi.fn();
    render(<CorpusSearch onOpen={onOpen} />);
    submit("query");
    fireEvent.click(screen.getByRole("button", { name: "clear search" }));
    await act(async () => { late.resolve(new Response("{}", { status: 200 })); });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("searchbox").getAttribute("value")).toBe("");
    expect(screen.getByRole("button", { name: "Search" }).getAttribute("disabled")).toBeNull();
    expectNoResults(onOpen);
  });

  it("unmount retires the response before any alert or open effect", async () => {
    const late = pendingResponse();
    const transport = vi.fn<typeof fetch>().mockReturnValue(late.promise);
    vi.stubGlobal("fetch", transport);
    const onOpen = vi.fn();
    const view = render(<CorpusSearch onOpen={onOpen} />);
    submit("query");
    view.unmount();
    await act(async () => { late.resolve(new Response("{}", { status: 200 })); });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(transport).toHaveBeenCalledOnce();
    expectNoResults(onOpen);
  });
});
