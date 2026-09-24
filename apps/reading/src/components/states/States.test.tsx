/**
 * States.test.tsx — the shared loading / empty / error primitives (design
 * spec §5, audit-components M9, audit-type-copy C2/C3).
 *
 * The contract each primitive owes its callers, asserted rather than eyeballed:
 *  - LoadingState names the thing that is opening (role=status, polite) and
 *    draws a skeleton of the real geometry (rows for a list, lines for a page)
 *    that assistive tech never reads;
 *  - EmptyState is NEUTRAL: no role=alert, no danger colour, and it offers the
 *    first action;
 *  - ErrorState says what failed and what is safe, offers ONE primary
 *    "Try again", and keeps the raw technical message ("Failed to fetch",
 *    "HTTP 500") out of the visible copy: it is reachable only through
 *    "Copy error details", which writes it to the clipboard.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

import { EmptyState, ErrorState, LoadingState } from "./index";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("LoadingState", () => {
  it("names what is opening in a polite status region", () => {
    render(<LoadingState label="Opening the library" />);
    const status = screen.getByRole("status");
    expect(status.getAttribute("aria-live")).toBe("polite");
    expect(status.textContent).toContain("Opening the library");
    // Not the anonymous "Loading…" the audit counted 19 times.
    expect(status.textContent).not.toMatch(/^\s*Loading…\s*$/);
  });

  it("inline, draws no box of its own: the skeleton rows are the list's geometry", () => {
    // A bordered .st-inline card around skeleton rows would be a box around
    // boxes, and the loaded rows would land inside a frame that then vanishes.
    const { container } = render(<LoadingState variant="inline" label="Opening your notebooks" />);
    const status = screen.getByRole("status");
    expect(status.classList.contains("st-inline")).toBe(false);
    expect(status.classList.contains("st-page")).toBe(false);
    expect(container.querySelectorAll("[data-skeleton] > span")).toHaveLength(3);
  });

  it("draws list rows by default and prose lines for a page, hidden from assistive tech", () => {
    const { container, rerender } = render(<LoadingState label="Opening your research" rows={4} />);
    let skel = container.querySelector("[data-skeleton]")!;
    expect(skel.getAttribute("aria-hidden")).toBe("true");
    expect(skel.getAttribute("data-skeleton")).toBe("list");
    expect(skel.children.length).toBe(4);
    rerender(<LoadingState label="Opening the book" shape="page" />);
    skel = container.querySelector("[data-skeleton]")!;
    expect(skel.getAttribute("data-skeleton")).toBe("page");
    expect(skel.children.length).toBeGreaterThan(3);
  });
});

describe("EmptyState", () => {
  it("is neutral: no alert role, no danger colour, and it offers the first action", () => {
    const onStart = vi.fn();
    const { container } = render(
      <EmptyState
        title="No research yet"
        body="Research you start shows up here."
        action={<button onClick={onStart}>Start a research</button>}
      />,
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(container.innerHTML).not.toMatch(/emperor|danger/);
    expect(screen.getByText("No research yet")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Start a research" }));
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it("carries the empty mascot pose as decoration only", () => {
    const { container } = render(<EmptyState title="Nothing here yet" />);
    const art = container.querySelector("[data-state-art]");
    expect(art).toBeTruthy();
    expect(art!.getAttribute("aria-hidden")).toBe("true");
    const noArt = render(<EmptyState title="Nothing here yet" art={false} />);
    expect(noArt.container.querySelector("[data-state-art]")).toBeNull();
  });
});

describe("ErrorState", () => {
  it("says what failed and what is safe, with one primary Try again", () => {
    const onRetry = vi.fn();
    render(
      <ErrorState
        title="Couldn't open this book"
        body="Your library and notes are unchanged."
        detail="Failed to fetch"
        onRetry={onRetry}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Couldn't open this book");
    expect(alert.textContent).toContain("Your library and notes are unchanged.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("keeps the raw technical message out of the copy and puts it on the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(
      <ErrorState
        title="Couldn't load your research"
        detail="GET /investigations failed: HTTP 500"
        onRetry={() => {}}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert.textContent).not.toContain("HTTP 500");
    expect(alert.textContent).not.toContain("Failed to fetch");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Copy error details" }));
    });
    expect(writeText).toHaveBeenCalledWith("GET /investigations failed: HTTP 500");
    expect(screen.getByRole("button", { name: "Copied" })).toBeTruthy();
  });

  it("says so when the clipboard refuses, instead of claiming a copy", async () => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
    });
    render(<ErrorState title="Couldn't start the research" detail="HTTP 500" />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Copy error details" }));
    });
    expect(screen.getByRole("button", { name: "Couldn't copy" })).toBeTruthy();
  });

  it("sets its sentences in the interface face, never mono", () => {
    const { container } = render(
      <ErrorState title="Couldn't open this book" body="Your notes are unchanged." detail="x" />,
    );
    const sentences = [...container.querySelectorAll("p")];
    expect(sentences.length).toBe(2);
    for (const p of sentences) {
      expect(p.className).not.toContain("font-mono");
      expect(p.closest(".font-mono")).toBeNull();
    }
  });
});
