import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { BookSummary } from "../../api/books";
import BookCard from "./BookCard";
import Library from "./index";

// Hoisted mocks so the static `import Library` above binds to them.
const { listBooksMock, curateBooksMock, navigateMock } = vi.hoisted(() => ({
  listBooksMock: vi.fn(),
  curateBooksMock: vi.fn(),
  navigateMock: vi.fn(),
}));

vi.mock("../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../api/books")>();
  return { ...actual, listBooks: listBooksMock, curateBooks: curateBooksMock };
});

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const servableBook: BookSummary = {
  document_id: "doc-pd",
  title: "Meditations",
  author: "Marcus Aurelius",
  servability: "public_domain",
  servable_full_text: true,
  page_count: 254,
  cover_uri: null,
  ip_holder_id: null,
  taken_down: false,
};

const gatedBook: BookSummary = {
  ...servableBook,
  document_id: "doc-gated",
  title: "A Licensed Title",
  author: "Some Author",
  servability: "gated_metadata_only",
  servable_full_text: false,
};

beforeEach(() => {
  listBooksMock.mockReset();
  curateBooksMock.mockReset();
  navigateMock.mockReset();
});
afterEach(() => cleanup());

describe("BookCard", () => {
  it("renders title, author, and a servability badge", () => {
    render(<BookCard book={servableBook} />);
    // Title is the button's accessible name (the cover spine is decorative).
    expect(screen.getByRole("button", { name: /Open Meditations/ })).toBeTruthy();
    expect(screen.getByText(/Marcus Aurelius/)).toBeTruthy();
    expect(screen.getByText("Public domain")).toBeTruthy();
  });

  it("flags a gated book as preview-only (never implies full read)", () => {
    render(<BookCard book={gatedBook} />);
    expect(screen.getByText("Preview only")).toBeTruthy();
  });

  it("calls onOpen with the document id when clicked", () => {
    const onOpen = vi.fn();
    render(<BookCard book={servableBook} onOpen={onOpen} />);
    fireEvent.click(screen.getByRole("button", { name: /Open Meditations/ }));
    expect(onOpen).toHaveBeenCalledWith("doc-pd");
  });
});

describe("Library", () => {
  function renderLibrary() {
    return render(
      <MemoryRouter>
        <Library />
      </MemoryRouter>,
    );
  }

  it("loads the servable shelf and routes to the reader on open", async () => {
    listBooksMock.mockResolvedValue({ books: [servableBook], count: 1 });
    renderLibrary();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Open Meditations/ })).toBeTruthy(),
    );
    expect(listBooksMock).toHaveBeenCalledWith("servable");
    fireEvent.click(screen.getByRole("button", { name: /Open Meditations/ }));
    expect(navigateMock).toHaveBeenCalledWith("/read/doc-pd");
  });

  it("switching to Preview reloads the gated set", async () => {
    listBooksMock
      .mockResolvedValueOnce({ books: [servableBook], count: 1 })
      .mockResolvedValueOnce({ books: [gatedBook], count: 1 });
    renderLibrary();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Open Meditations/ })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Open A Licensed Title/ })).toBeTruthy(),
    );
    expect(listBooksMock).toHaveBeenLastCalledWith("gated");
  });

  it("shows an honest empty-state (what's available to read, not an uploader)", async () => {
    listBooksMock.mockResolvedValue({ books: [], count: 0 });
    renderLibrary();
    // Read SPR-06: an empty shelf is honest about the servable corpus — it
    // points to Preview / bring-your-own, never prompts an operator ingest.
    await waitFor(() =>
      expect(screen.getByText(/only shows what can be legally aggregated/)).toBeTruthy(),
    );
    // It is the Read door's honest "nothing to read in full yet" state — not
    // an upload prompt as the home (the wrestler is a demoted side affordance).
    expect(screen.queryByText(/Load a PDF to wrestle/)).toBeNull();
  });

  it("curates the shelf by prompt, re-ranking to the curated order", async () => {
    const second = { ...servableBook, document_id: "doc-2", title: "Second Book" };
    listBooksMock.mockResolvedValue({ books: [servableBook, second], count: 2 });
    // Curate returns the two in REVERSE relevance order.
    curateBooksMock.mockResolvedValue({
      prompt: "stoicism",
      books: [
        { document_id: "doc-2", title: "Second Book", author: "A", score: 0.9 },
        { document_id: "doc-pd", title: "Meditations", author: "Marcus Aurelius", score: 0.4 },
      ],
    });
    renderLibrary();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Open Meditations/ })).toBeTruthy(),
    );
    const input = screen.getByLabelText("Curate the library by prompt");
    fireEvent.change(input, { target: { value: "stoicism" } });
    fireEvent.click(screen.getByRole("button", { name: "Curate" }));
    await waitFor(() => expect(screen.getByText(/Curated for/)).toBeTruthy());
    expect(curateBooksMock).toHaveBeenCalledWith("stoicism");
    // Curated order: Second Book first, Meditations second.
    const cards = screen.getAllByRole("button", { name: /^Open / });
    expect(cards[0].getAttribute("aria-label")).toMatch(/Second Book/);
  });
});
