import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import BookFreeCopyPanel from "./BookFreeCopyPanel";
import type { FreeCopyPreflightResult } from "../../api/bookFreeCopy";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const found: FreeCopyPreflightResult = {
  freely_available: true,
  title: "Walden",
  author: "Thoreau",
  source: "gutenberg",
  rights_basis: "copyright=false",
  retrieved_at: "2026-07-11T00:00:00+00:00",
  candidate_kind: "PublicDomainWork",
  candidate_ref_withheld: true,
  outcomes: [],
  checked_at: "2026-07-11T00:00:00+00:00",
};

const notFound: FreeCopyPreflightResult = {
  freely_available: false,
  title: "Unknown",
  author: null,
  source: null,
  rights_basis: null,
  retrieved_at: null,
  candidate_kind: null,
  candidate_ref_withheld: true,
  outcomes: [
    {
      source: "gutenberg",
      found: false,
      query: "Unknown",
      timestamp: "t",
      error: null,
    },
  ],
  checked_at: "2026-07-11T00:00:00+00:00",
};

describe("BookFreeCopyPanel", () => {
  it("shows free hit via injectable preflightFn", async () => {
    const preflightFn = vi.fn(async () => found);
    render(
      <BookFreeCopyPanel
        preflightFn={preflightFn}
        initialTitle="Walden"
        initialAuthor="Thoreau"
      />,
    );
    fireEvent.click(screen.getByTestId("book-free-copy-run"));
    await waitFor(() => {
      expect(screen.getByTestId("book-free-copy-available").textContent).toMatch(
        /Free copy found/,
      );
    });
    expect(
      screen.getByTestId("book-free-copy-available").getAttribute("data-available"),
    ).toBe("true");
    expect(preflightFn).toHaveBeenCalledWith({
      title: "Walden",
      author: "Thoreau",
    });
  });

  it("shows not-found outcomes honestly", async () => {
    const preflightFn = vi.fn(async () => notFound);
    render(
      <BookFreeCopyPanel preflightFn={preflightFn} initialTitle="Unknown" />,
    );
    fireEvent.click(screen.getByTestId("book-free-copy-run"));
    await waitFor(() => {
      expect(screen.getByTestId("book-free-copy-available").textContent).toMatch(
        /No free copy/,
      );
    });
    expect(screen.getByTestId("book-free-copy-outcomes").textContent).toMatch(
      /gutenberg/,
    );
  });

  it("surfaces errors without inventing a free hit", async () => {
    const preflightFn = vi.fn(async () => {
      throw new Error("upstream failed");
    });
    render(
      <BookFreeCopyPanel preflightFn={preflightFn} initialTitle="Walden" />,
    );
    fireEvent.click(screen.getByTestId("book-free-copy-run"));
    await waitFor(() => {
      expect(screen.getByTestId("book-free-copy-error").textContent).toMatch(
        /upstream failed/,
      );
    });
    expect(screen.queryByTestId("book-free-copy-result")).toBeNull();
  });

  it("rejects injectable missing freely_available without success", async () => {
    const preflightFn = vi.fn(async () => {
      const { freely_available: _f, ...rest } = found;
      return rest;
    });
    render(
      <BookFreeCopyPanel preflightFn={preflightFn} initialTitle="Walden" />,
    );
    fireEvent.click(screen.getByTestId("book-free-copy-run"));
    await waitFor(() => {
      expect(screen.getByTestId("book-free-copy-error").textContent).toMatch(
        /freely_available/,
      );
    });
    expect(screen.queryByTestId("book-free-copy-result")).toBeNull();
  });
});
