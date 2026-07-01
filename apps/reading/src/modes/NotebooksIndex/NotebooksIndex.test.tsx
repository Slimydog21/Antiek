import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";

import NotebooksIndex from "./index";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderIndex() {
  return render(
    <MemoryRouter initialEntries={["/notebooks"]}>
      <NotebooksIndex />
      <LocationProbe />
    </MemoryRouter>,
  );
}

const LIST_RESPONSE = {
  count: 2,
  notebooks: [
    {
      notebook_id: "nb-private-1",
      title: "Source workbench",
      investigation_id: "inv-private-123456",
      document_id: null,
      content_class: "user_owned",
      created_at: "2026-07-01T00:00:00Z",
      updated_at: "2026-07-01T01:00:00Z",
    },
    {
      notebook_id: "nb-public-2",
      title: "Shared reading notes",
      investigation_id: null,
      document_id: "doc-linked",
      content_class: "user_public_contribution",
      created_at: "2026-07-01T00:00:00Z",
      updated_at: "2026-07-01T02:00:00Z",
    },
  ],
};

beforeEach(() => {
  apiFetchMock.mockReset().mockResolvedValue({
    ok: true,
    json: async () => LIST_RESPONSE,
  });
});

afterEach(() => {
  cleanup();
});

describe("NotebooksIndex", () => {
  it("renders notebook rows with user-facing labels instead of raw handles", async () => {
    renderIndex();

    expect(await screen.findByText("Source workbench")).toBeTruthy();
    expect(screen.getByText("Shared reading notes")).toBeTruthy();
    expect(
      screen.getByRole("row", {
        name: /Source workbench.*linked research.*Private/i,
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("row", {
        name: /Shared reading notes.*linked document.*Public contribution/i,
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("columnheader", { name: "Visibility" }),
    ).toBeTruthy();
    expect(screen.getByText(/linked research/)).toBeTruthy();
    expect(screen.getByText(/linked document/)).toBeTruthy();

    expect(screen.queryByText("nb-private-1")).toBeNull();
    expect(screen.queryByText(/inv:/i)).toBeNull();
    expect(screen.queryByText(/user_owned/i)).toBeNull();
  });

  it("opens a notebook row on the canonical detail route", async () => {
    renderIndex();

    await userEvent.click(await screen.findByText("Source workbench"));

    expect(screen.getByTestId("location").textContent).toBe(
      "/notebook/nb-private-1",
    );
  });

  it("creates a notebook and navigates into it", async () => {
    apiFetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
      if (path === "/notebooks" && init?.method === "POST") {
        return {
          ok: true,
          json: async () => ({
            ...LIST_RESPONSE.notebooks[0],
            notebook_id: "nb-created-3",
            title: "New synthesis",
          }),
        };
      }
      return {
        ok: true,
        json: async () => LIST_RESPONSE,
      };
    });

    renderIndex();
    await screen.findByText("Source workbench");

    await userEvent.type(screen.getByPlaceholderText("Title"), "New synthesis");
    await userEvent.type(
      screen.getByLabelText("Link to research"),
      "inv-created-123",
    );
    await userEvent.click(screen.getByRole("button", { name: "Create notebook" }));

    await waitFor(() => {
      expect(screen.getByTestId("location").textContent).toBe(
        "/notebook/nb-created-3",
      );
    });
    expect(apiFetchMock).toHaveBeenCalledWith(
      "/notebooks",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          title: "New synthesis",
          investigation_id: "inv-created-123",
        }),
      }),
    );
  });
});
