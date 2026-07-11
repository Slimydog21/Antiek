import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import LibraryCatalogPanel from "./LibraryCatalogPanel";
import type { LibraryPage } from "../../api/libraryCatalog";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const SECRET_BODY = "SECRET_BODY_SENTINEL_NEVER_RENDER";
const SECRET_RAW = "SECRET_RAW_TEXT_SENTINEL_NEVER_RENDER";

/** Injectable page may carry extra runtime keys; panel must not display them. */
const sample = {
  works: [
    {
      document_id: "doc-1",
      title: "Scaling Laws",
      author: "Kaplan",
      servability: "servable",
      servable_full_text: true,
      page_count: 12,
      cover_uri: null,
      ip_holder_id: null,
      taken_down: false,
      // adversarial extras (not on BookSummary type)
      full_text: SECRET_BODY,
      raw_text: SECRET_RAW,
      body: SECRET_BODY,
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
} as LibraryPage;

describe("LibraryCatalogPanel", () => {
  it("loads catalog via injectable fetchFn and shows metadata only", async () => {
    const fetchFn = vi.fn(async () => sample);
    render(
      <LibraryCatalogPanel
        fetchFn={fetchFn}
        initialFilter="servable"
        initialSearch="scaling"
      />,
    );
    fireEvent.click(screen.getByTestId("library-catalog-load"));
    await waitFor(() => {
      expect(screen.getByTestId("library-catalog-result")).toBeTruthy();
    });
    expect(fetchFn).toHaveBeenCalledWith({
      filter: "servable",
      search: "scaling",
      page: 1,
      page_size: 20,
    });
    expect(screen.getByTestId("library-work-title-doc-1").textContent).toMatch(
      /Scaling Laws/,
    );
    expect(
      screen.getByTestId("library-work-servability-doc-1").textContent,
    ).toMatch(/servable/i);
    // adversarial body payloads from injectable fetch must never appear
    expect(document.body.textContent).not.toContain(SECRET_BODY);
    expect(document.body.textContent).not.toContain(SECRET_RAW);
    expect(screen.queryByTestId("library-work-body-doc-1")).toBeNull();
  });

  it("surfaces fetch errors without a result list", async () => {
    const fetchFn = vi.fn(async () => {
      throw new Error("catalog unavailable");
    });
    render(<LibraryCatalogPanel fetchFn={fetchFn} />);
    fireEvent.click(screen.getByTestId("library-catalog-load"));
    await waitFor(() => {
      expect(screen.getByTestId("library-catalog-error").textContent).toMatch(
        /catalog unavailable/,
      );
    });
    expect(screen.queryByTestId("library-catalog-result")).toBeNull();
  });

  it("shows empty match state", async () => {
    const fetchFn = vi.fn(async () => ({
      works: [],
      total: 0,
      page: 1,
      page_size: 20,
    }));
    render(<LibraryCatalogPanel fetchFn={fetchFn} />);
    fireEvent.click(screen.getByTestId("library-catalog-load"));
    await waitFor(() => {
      expect(screen.getByTestId("library-catalog-empty").textContent).toMatch(
        /No works match/i,
      );
    });
  });
});
