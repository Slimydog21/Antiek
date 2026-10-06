/** Synthetic failure-only controls. No successful book or HTTP 200 fixture. */
import { useLayoutEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ApiError } from "../../lib/api";
import type { BookDetail, FullTextResponse } from "../../api/books";
import { setReadingStateOwner } from "../../hooks/useReadingState";
import { notifyReadingPositionOwner, setReadingPositionOwner } from "./usePosition";

const { detail, body, houses, retries } = vi.hoisted(() => {
  const retries: Array<(() => void) | undefined> = [];
  return {
  detail: vi.fn<(id: string) => Promise<BookDetail>>(),
  body: vi.fn<(id: string) => Promise<FullTextResponse>>(),
  houses: vi.fn(),
  retries,
  };
});
vi.mock("../../api/books", async (original) => ({
  ...await original<typeof import("../../api/books")>(),
  getBook: detail,
  getBookFullText: body,
  listBooks: houses,
}));
vi.mock("../../components/states", async (original) => {
  const actual = await original<typeof import("../../components/states")>();
  return {
    ...actual,
    ErrorState: (props: Parameters<typeof actual.ErrorState>[0]) => {
      retries.push(props.onRetry);
      return <actual.ErrorState {...props} />;
    },
  };
});
import BookReader from "./index";

function unavailable() {
  return new ApiError("controlled book read failure", 503, "synthetic failure-only control");
}

function pendingFailure<T>() {
  let reject: (cause: unknown) => void = () => { throw new Error("deferred failure not initialized"); };
  const promise = new Promise<T>((_resolve, fail) => { reject = fail; });
  return { promise, reject };
}

function tree(id: string) {
  return <MemoryRouter><BookReader documentId={id} /></MemoryRouter>;
}

async function settle() {
  await act(async () => { await Promise.resolve(); });
}

function retryCallback() {
  const retry = retries.at(-1);
  if (!retry) throw new Error("failure did not expose a retry");
  return retry;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("controlled ancillary transport failure")));
  detail.mockReset();
  body.mockReset();
  houses.mockReset();
  retries.length = 0;
  detail.mockRejectedValue(unavailable());
  body.mockRejectedValue(unavailable());
  houses.mockRejectedValue(unavailable());
  setReadingStateOwner("control-a");
});
afterEach(() => {
  cleanup();
  setReadingStateOwner(null);
  vi.unstubAllGlobals();
});

describe("generic reader failure and lifetime controls", () => {
  it("shows typed unavailability and allows a manual retry", async () => {
    render(tree("control-doc"));
    await settle();
    expect(screen.getByRole("alert").textContent).toContain("Antiek is busy or restarting");
    expect(screen.getByRole("alert").textContent).toContain("Your library and notes are unchanged");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await settle();
    expect(detail).toHaveBeenCalledTimes(2);
    expect(body).toHaveBeenCalledTimes(2);
    expect(houses).not.toHaveBeenCalled();
  });

  it("distinguishes sign-out without offering an identical retry", async () => {
    detail.mockRejectedValue(new ApiError("controlled unauthorized", 401, ""));
    render(tree("control-doc"));
    await settle();
    expect(screen.getByRole("alert").textContent).toContain("You're signed out");
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("keeps missing-book behavior distinct", async () => {
    detail.mockRejectedValue(new Error("book_not_found"));
    render(tree("control-doc"));
    await settle();
    expect(screen.getByText("That book isn't in the library.")).not.toBeNull();
    expect(screen.getByRole("link", { name: "Go to the library" })).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("describes a transport failure separately", async () => {
    detail.mockRejectedValue(new TypeError("controlled offline failure"));
    render(tree("control-doc"));
    await settle();
    expect(screen.getByRole("alert").textContent).toContain("Antiek can't be reached right now");
    expect(screen.getByRole("button", { name: "Try again" })).not.toBeNull();
  });

  it("retires an original load when the document changes", async () => {
    const old = pendingFailure<BookDetail>();
    detail.mockImplementation((id) => id === "control-a" ? old.promise : Promise.reject(new ApiError("controlled signed out", 401, "")));
    body.mockImplementation(() => new Promise<FullTextResponse>(() => {}));
    const view = render(tree("control-a"));
    view.rerender(tree("control-b"));
    await settle();
    await act(async () => old.reject(unavailable()));
    expect(screen.getByRole("alert").textContent).toContain("You're signed out");
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    expect(detail.mock.calls.map(([id]) => id)).toEqual(["control-a", "control-b"]);
  });

  it("refuses an old A result after document A-B-A", async () => {
    const first = pendingFailure<BookDetail>();
    const middle = pendingFailure<BookDetail>();
    const last = pendingFailure<BookDetail>();
    detail.mockReturnValueOnce(first.promise).mockReturnValueOnce(middle.promise).mockReturnValueOnce(last.promise);
    body.mockImplementation(() => new Promise<FullTextResponse>(() => {}));
    const view = render(tree("control-a"));
    view.rerender(tree("control-b"));
    view.rerender(tree("control-a"));
    await act(async () => first.reject(new ApiError("controlled signed out", 401, "")));
    expect(screen.getByRole("status").textContent).toContain("Opening the book");
    await act(async () => last.reject(unavailable()));
    expect(screen.getByRole("alert").textContent).toContain("Antiek is busy or restarting");
    await act(async () => middle.reject(new Error("book_not_found")));
    expect(screen.getByRole("alert").textContent).toContain("Antiek is busy or restarting");
  });

  it("retires a pending manual retry when the document changes", async () => {
    const oldRetry = pendingFailure<BookDetail>();
    detail.mockRejectedValueOnce(unavailable()).mockReturnValueOnce(oldRetry.promise).mockRejectedValueOnce(new ApiError("controlled signed out", 401, ""));
    const view = render(tree("control-a"));
    await settle();
    body.mockImplementation(() => new Promise<FullTextResponse>(() => {}));
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    view.rerender(tree("control-b"));
    await settle();
    await act(async () => oldRetry.reject(unavailable()));
    expect(screen.getByRole("alert").textContent).toContain("You're signed out");
  });

  it("refuses a queued old retry after document A-B-A", async () => {
    const view = render(tree("control-a"));
    await settle();
    const oldRetry = retryCallback();
    view.rerender(tree("control-b"));
    await settle();
    view.rerender(tree("control-a"));
    await settle();
    const count = detail.mock.calls.length;
    act(oldRetry);
    await settle();
    expect(detail).toHaveBeenCalledTimes(count);
  });

  it("lets the latest retry own the failure", async () => {
    const earlier = pendingFailure<BookDetail>();
    const latest = pendingFailure<BookDetail>();
    render(tree("control-a"));
    await settle();
    const retry = retryCallback();
    detail.mockReturnValueOnce(earlier.promise).mockReturnValueOnce(latest.promise);
    body.mockImplementation(() => new Promise<FullTextResponse>(() => {}));
    act(() => { retry(); retry(); });
    await act(async () => latest.reject(unavailable()));
    await act(async () => earlier.reject(new ApiError("controlled signed out", 401, "")));
    expect(screen.getByRole("alert").textContent).toContain("Antiek is busy or restarting");
  });

  it("refuses an old result after the existing owner bridge batches A-B-A", async () => {
    const old = pendingFailure<BookDetail>();
    detail.mockReturnValueOnce(old.promise).mockRejectedValueOnce(unavailable());
    body.mockImplementation(() => new Promise<FullTextResponse>(() => {}));
    render(tree("control-doc"));
    act(() => { setReadingStateOwner("control-b"); setReadingStateOwner("control-a"); });
    await settle();
    await act(async () => old.reject(new ApiError("controlled signed out", 401, "")));
    expect(screen.getByRole("alert").textContent).toContain("Antiek is busy or restarting");
    expect(detail).toHaveBeenCalledTimes(2);
  });

  it("refuses an old failure during silent A-B-A before notification", async () => {
    const old = pendingFailure<BookDetail>();
    detail.mockReturnValueOnce(old.promise).mockRejectedValueOnce(unavailable());
    body.mockImplementation(() => new Promise<FullTextResponse>(() => {}));
    render(tree("control-doc"));
    act(() => { setReadingPositionOwner("control-b", false); setReadingPositionOwner("control-a", false); });
    await act(async () => old.reject(new ApiError("controlled signed out", 401, "")));
    // Other real reader hooks can cause a render and observe the silent epoch.
    // The old failure must be refused in either loading or current-failure UI.
    expect(document.body.textContent).not.toContain("You're signed out");
    act(notifyReadingPositionOwner);
    await settle();
    expect(screen.getByRole("alert").textContent).toContain("Antiek is busy or restarting");
  });

  it("refuses an old queued retry during silent owner A-B-A", async () => {
    render(tree("control-doc"));
    await settle();
    const oldRetry = retryCallback();
    const count = detail.mock.calls.length;
    act(() => { setReadingPositionOwner("control-b", false); setReadingPositionOwner("control-a", false); oldRetry(); });
    await settle();
    expect(detail).toHaveBeenCalledTimes(count);
    act(notifyReadingPositionOwner);
    await settle();
    expect(detail).toHaveBeenCalledTimes(count + 1);
  });

  it("keeps a same-document, same-owner verification stable", async () => {
    const view = render(tree("control-doc"));
    await settle();
    act(() => setReadingStateOwner("control-a"));
    view.rerender(tree("control-doc"));
    await settle();
    expect(detail).toHaveBeenCalledTimes(1);
  });

  it("removes the old failure before the new document's passive load effect", async () => {
    const atLayout: string[] = [];
    function Observed({ id }: { id: string }) {
      useLayoutEffect(() => { atLayout.push(document.body.textContent ?? ""); }, [id]);
      return <BookReader documentId={id} />;
    }
    detail.mockRejectedValueOnce(new ApiError("controlled signed out", 401, ""));
    const view = render(<MemoryRouter><Observed id="control-a" /></MemoryRouter>);
    await settle();
    detail.mockImplementation(() => new Promise<BookDetail>(() => {}));
    body.mockImplementation(() => new Promise<FullTextResponse>(() => {}));
    view.rerender(<MemoryRouter><Observed id="control-b" /></MemoryRouter>);
    expect(atLayout.at(-1)).toContain("Opening the book");
    expect(atLayout.at(-1)).not.toContain("You're signed out");
  });

  it("retires both a queued retry and pending original on unmount", async () => {
    const old = pendingFailure<BookDetail>();
    const view = render(tree("control-doc"));
    await settle();
    const retry = retryCallback();
    detail.mockReturnValueOnce(old.promise);
    body.mockImplementation(() => new Promise<FullTextResponse>(() => {}));
    act(retry);
    view.unmount();
    const count = detail.mock.calls.length;
    const renderedFailures = retries.length;
    act(retry);
    await act(async () => old.reject(unavailable()));
    expect(detail).toHaveBeenCalledTimes(count);
    expect(retries).toHaveLength(renderedFailures);
    expect(houses).not.toHaveBeenCalled();
  });
});
