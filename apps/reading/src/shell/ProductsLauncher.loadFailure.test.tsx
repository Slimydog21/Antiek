/**
 * ProductsLauncher.loadFailure.test — a launcher chunk that fails to load
 * must not take the shell down.
 *
 * The More drawer is fetched on demand (ProductsLauncher.lazy.test). Nothing
 * above the NavRail catches a render error, so a React.lazy import that
 * rejected (offline, or a deploy that retired the chunk) would throw through
 * the whole app and blank it. A failed load closes the drawer instead, and
 * the shell stays up.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("./ProductsLauncher", () => {
  throw new Error("Failed to fetch dynamically imported module");
});

import { NavRail } from "./NavRail";

afterEach(cleanup);

describe("a launcher chunk that fails to load", () => {
  it("leaves the rail standing and More unlit", async () => {
    render(
      <MemoryRouter>
        <NavRail />
      </MemoryRouter>,
    );
    const more = screen.getByTitle(/More - all products/);
    fireEvent.click(more);
    // Let the rejected import settle.
    await new Promise((r) => setTimeout(r, 50));
    // The rail is still mounted: the failed import did not throw through the
    // tree (with no boundary above it, a throw unmounts everything).
    expect(document.querySelector('[aria-label="Primary navigation"]')).toBeTruthy();
    expect(screen.getByTitle(/More - all products/)).toBeTruthy();
    expect(screen.queryByRole("dialog", { name: "More" })).toBeNull();
    await waitFor(() => expect(screen.getByTitle(/More - all products/).getAttribute("aria-current")).toBeNull());
  });
});
