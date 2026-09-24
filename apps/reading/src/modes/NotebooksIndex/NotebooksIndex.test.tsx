/**
 * NotebooksIndex.test — a failed load is a designed error, not a raw string.
 *
 * The 2026-09-23 gallery showed a bare red "Failed to fetch" on /notebooks
 * (design spec §5: never "Failed to fetch" or "HTTP 500" in user copy). The
 * list now says what failed and what is safe, offers Try again, and keeps the
 * raw message for Copy error details. A failed create keeps the draft.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import NotebooksIndex from "./index";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

const ok = (payload: unknown) =>
  ({ ok: true, status: 200, json: async () => payload }) as unknown as Response;

afterEach(() => {
  cleanup();
  apiFetchMock.mockReset();
});

function renderIndex() {
  return render(
    <MemoryRouter>
      <NotebooksIndex />
    </MemoryRouter>,
  );
}

describe("NotebooksIndex load and create failures", () => {
  it("names a failed load, hides the raw message, and retries", async () => {
    apiFetchMock
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(ok({ notebooks: [] }));
    renderIndex();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Couldn’t load your notebooks");
    expect(document.body.textContent).not.toContain("Failed to fetch");

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(screen.getByText("No notebooks match this filter.")).toBeTruthy();
  });

  it("keeps a failed create's title and says so, without the HTTP status", async () => {
    apiFetchMock
      .mockResolvedValueOnce(ok({ notebooks: [] }))
      .mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) } as unknown as Response);
    renderIndex();
    await screen.findByText("No notebooks match this filter.");

    fireEvent.change(screen.getByPlaceholderText("Title"), { target: { value: "Field notes" } });
    fireEvent.click(screen.getByRole("button", { name: "Create notebook" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Couldn’t create the notebook");
    expect(document.body.textContent).not.toMatch(/HTTP \d{3}/);
    expect((screen.getByPlaceholderText("Title") as HTMLInputElement).value).toBe("Field notes");
  });
});

describe("NotebooksIndex filters", () => {
  it("sets the filter buttons in the interface face, not mono (spec §3)", async () => {
    // Mono never sets a button label. The three filter chips were the last
    // hand-rolled buttons on this page still in JetBrains Mono.
    apiFetchMock.mockResolvedValueOnce(ok({ notebooks: [] }));
    renderIndex();
    await screen.findByText("No notebooks match this filter.");
    for (const name of ["all", "user owned", "user public contribution"]) {
      const chip = screen.getByRole("button", { name });
      expect(chip.className).not.toMatch(/\bfont-mono\b/);
      expect(chip.className).toMatch(/\bfont-sans\b/);
    }
  });
});
