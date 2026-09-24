/**
 * DocumentsIndex.test — a failed load is a designed error, not a raw string.
 *
 * The 2026-09-23 gallery (and the w3 after-shots) showed a bare red "Failed
 * to fetch" on /documents. Design spec §5: the error says what failed and
 * what is safe, offers one Try again, and keeps the raw message for Copy
 * error details.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import DocumentsIndex from "./index";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

afterEach(() => {
  cleanup();
  apiFetchMock.mockReset();
});

describe("DocumentsIndex load failure", () => {
  it("names a failed load, hides the raw message, and retries", async () => {
    apiFetchMock
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ documents: [] }) } as unknown as Response);
    render(
      <MemoryRouter>
        <DocumentsIndex />
      </MemoryRouter>,
    );

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Couldn’t load your documents");
    expect(document.body.textContent).not.toContain("Failed to fetch");

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(screen.getByText("No documents match this filter.")).toBeTruthy();
  });
});
