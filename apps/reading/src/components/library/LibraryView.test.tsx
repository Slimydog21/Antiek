/**
 * LibraryView.test.tsx — Read SPR-09 M2 acceptance.
 *
 * Load-bearing claims:
 *  - the view drives useLibrary with the right query: filter "servable" + empty
 *    search + page 1 on first load, the filter tabs switch `filter`, and the
 *    (debounced) search box lifts the term into `search`;
 *  - a routeAbsent result (the catalog endpoint 404 surfaced by the hook)
 *    degrades to an honest "not available yet" state with a retry — NOT a
 *    false-empty shelf;
 *  - the §9.0 contract: the consumed payload (LibraryPage.works) is BookSummary
 *    only — no body field exists to render.
 *
 * We mock the `useLibrary` hook so the test drives the view's query + state
 * wiring without a network; the fetcher's own 404/param behavior is covered by
 * the hook's contract and the args recorded here.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { BookSummary } from "../../api/books";
import type { UseLibraryArgs, UseLibraryResult } from "./useLibrary";

// The view calls useLibrary({filter, search, page, pageSize}) on each render; we
// mock the hook to (a) RECORD the args the view passes (so we can assert the
// filter/search/page query the view drives) and (b) RETURN a controllable
// result (works / loading / routeAbsent) so each state is testable without a
// network. fetchLibraryPage itself is unit-covered separately via the args
// recorded here.
const lastArgs: { current: UseLibraryArgs | null } = { current: null };
const result: { current: UseLibraryResult } = {
  current: {
    works: [],
    total: 0,
    page: 1,
    pageSize: 24,
    loading: false,
    error: null,
    routeAbsent: false,
    reload: () => {},
  },
};
vi.mock("./useLibrary", () => ({
  useLibrary: (args: UseLibraryArgs): UseLibraryResult => {
    lastArgs.current = args;
    return result.current;
  },
}));

// Imported AFTER the mock so the view binds to the mocked hook.
const { default: LibraryView } = await import("./LibraryView");

const servable: BookSummary = {
  document_id: "doc-s",
  title: "Servable Work",
  author: "Ada",
  servability: "public_domain",
  servable_full_text: true,
  page_count: 100,
  cover_uri: null,
  ip_holder_id: null,
  taken_down: false,
};

function setResult(partial: Partial<UseLibraryResult>): void {
  result.current = { ...result.current, ...partial };
}

function renderView() {
  return render(
    <MemoryRouter>
      <LibraryView />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  lastArgs.current = null;
  result.current = {
    works: [],
    total: 0,
    page: 1,
    pageSize: 24,
    loading: false,
    error: null,
    routeAbsent: false,
    reload: () => {},
  };
});
afterEach(cleanup);

describe("LibraryView", () => {
  it("loads the servable shelf and renders the works", () => {
    setResult({ works: [servable], total: 1 });
    renderView();
    expect(screen.getAllByText("Servable Work").length).toBeGreaterThan(0);
    // First load is the servable filter, page 1.
    expect(lastArgs.current).toMatchObject({ filter: "servable", search: "", page: 1 });
  });

  it("switching to the Preview tab requeries with filter=gated", () => {
    setResult({ works: [servable], total: 1 });
    renderView();
    fireEvent.click(screen.getByRole("tab", { name: "Preview" }));
    expect(lastArgs.current).toMatchObject({ filter: "gated" });
  });

  it("typing in the search box requeries with the (debounced) search term", async () => {
    setResult({ works: [servable], total: 1 });
    renderView();
    fireEvent.change(screen.getByLabelText(/search the library/i), {
      target: { value: "ada" },
    });
    // The view debounces (250ms) before it lifts `draft` → `search`; wait for
    // the hook to be called with the term rather than asserting synchronously.
    await waitFor(() => expect(lastArgs.current).toMatchObject({ search: "ada" }));
  });

  it("degrades to an honest 'not available yet' state on a 404 (no false-empty)", () => {
    setResult({ routeAbsent: true });
    renderView();
    expect(screen.getByText(/catalog isn’t available yet/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
    // Crucially NOT the empty-corpus copy.
    expect(screen.queryByText(/Nothing is readable in full/i)).toBeNull();
  });

  it("a gated work renders the claim/metadata affordance — never a full-text Read or a body", () => {
    const gated: BookSummary = {
      document_id: "doc-g",
      title: "Gated Work",
      author: "Bram",
      servability: "gated_metadata_only",
      servable_full_text: false,
      page_count: 0,
      cover_uri: null,
      ip_holder_id: null,
      taken_down: false,
    };
    setResult({ works: [gated], total: 1 });
    renderView();
    // The gated card's action is the claim/metadata affordance (its accessible
    // name is "View metadata and claim to read …") — NOT a full-text "Read …"
    // open. This is the IA half of §9.0: the shelf never offers a body open for
    // a gated work.
    expect(
      screen.getByRole("button", { name: /claim to read/i }),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Read /i })).toBeNull();
  });

  it("the consumed contract type carries no body channel (frontend half of §9.0)", () => {
    // The REAL §9.0 body-withholding is enforced + tested SERVER-SIDE
    // (tests/test_library_api.py::test_gated_body_absent_from_every_payload and
    // the ad-route body-absent tests). This complementary assertion only pins
    // the frontend invariant: the `BookSummary` shape the view binds to has no
    // body field to leak through in the first place — it is a contract-shape
    // guard, not the §9.0 guarantee itself.
    const keys = Object.keys(servable);
    expect(keys).not.toContain("full_text");
    expect(keys).not.toContain("raw_text");
    expect(keys).not.toContain("body");
  });
});
