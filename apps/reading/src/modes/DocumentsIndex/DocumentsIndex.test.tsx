import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import DocumentsIndex from "./index";

const { apiFetchMock, openDocumentMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  openDocumentMock: vi.fn(),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

vi.mock("../../lib/openDocument", async (orig) => ({
  ...(await orig<typeof import("../../lib/openDocument")>()),
  useOpenDocument: () => openDocumentMock,
}));

function renderIndex() {
  return render(
    <MemoryRouter initialEntries={["/documents"]}>
      <DocumentsIndex />
    </MemoryRouter>,
  );
}

const LIST_RESPONSE = {
  documents: [
    {
      document_id: "doc-private-1",
      title: "Neutral atoms primer",
      source_uri: "https://example.test/neutral-atoms",
      document_type: "pdf",
      source_tier: 1,
      investigation_id: "inv-private-123456",
      content_class: "user_owned",
      ip_holder_id: null,
    },
    {
      document_id: "doc-public-2",
      title: null,
      source_uri: null,
      document_type: "web_page",
      source_tier: 5,
      investigation_id: null,
      content_class: "opt_in_licensed",
      ip_holder_id: null,
    },
    {
      document_id: "doc-restricted-3",
      title: "Archive scan",
      source_uri: null,
      document_type: "book",
      source_tier: 4,
      investigation_id: null,
      content_class: "restricted_pending_opt_in",
      ip_holder_id: null,
    },
  ],
};

beforeEach(() => {
  apiFetchMock.mockReset().mockResolvedValue({
    ok: true,
    json: async () => LIST_RESPONSE,
  });
  openDocumentMock.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("DocumentsIndex", () => {
  it("renders source rows with user-facing labels instead of raw handles", async () => {
    renderIndex();

    expect(await screen.findByText("Neutral atoms primer")).toBeTruthy();
    expect(screen.getByText("Untitled source")).toBeTruthy();
    expect(
      screen.getByRole("row", {
        name: /Neutral atoms primer.*PDF.*Private.*Research handle private-123456.*Primary source/i,
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("row", {
        name: /Untitled source.*Web Page.*Publisher licensed.*No linked research.*Unverified/i,
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("row", {
        name: /Archive scan.*Book.*Preview only.*No linked research.*Needs review/i,
      }),
    ).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Research" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Quality" })).toBeTruthy();

    expect(screen.queryByText("doc-private-1")).toBeNull();
    expect(screen.queryByText(/inv-private/i)).toBeNull();
    expect(screen.queryByText(/investigation_id/i)).toBeNull();
    expect(screen.queryByText(/user_owned/i)).toBeNull();
    expect(screen.queryByText(/opt_in_licensed/i)).toBeNull();
    expect(screen.queryByText(/restricted_pending_opt_in/i)).toBeNull();
  });

  it("opens a document row through the one reader door", async () => {
    renderIndex();

    await userEvent.click(await screen.findByText("Neutral atoms primer"));

    expect(openDocumentMock).toHaveBeenCalledWith("doc-private-1");
  });

  it("keeps the linked-research filter user-facing while querying the backend contract", async () => {
    renderIndex();

    await screen.findByText("Neutral atoms primer");
    await userEvent.type(
      screen.getByLabelText("Filter by research handle"),
      "private-123456",
    );

    await waitFor(() => {
      expect(
        apiFetchMock.mock.calls.some(([path]) =>
          String(path).includes("investigation_id=inv-private-123456"),
        ),
      ).toBe(true);
    });
    expect(screen.queryByPlaceholderText(/investigation_id/i)).toBeNull();
    expect(screen.getByPlaceholderText("Paste research handle to filter")).toBeTruthy();
  });

  it("sanitizes document rows before rendering and opening them", async () => {
    apiFetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        documents: [
          {
            document_id: " doc dirty ",
            title: "  Dirty source  ",
            source_uri: "  https://example.test/dirty  ",
            document_type: "  web_page  ",
            source_tier: 99,
            investigation_id: " inv-dirty ",
            content_class: " ",
            ip_holder_id: 17,
          },
          {
            document_id: " ",
            title: "Skipped source",
            source_tier: 1,
          },
        ],
      }),
    });

    renderIndex();

    expect(await screen.findByText("Dirty source")).toBeTruthy();
    expect(screen.queryByText("Skipped source")).toBeNull();
    expect(screen.getByText("Unrated source")).toBeTruthy();
    expect(screen.getByText("Web Page")).toBeTruthy();
    expect(screen.getByText("https://example.test/dirty")).toBeTruthy();
    expect(
      screen.getByRole("row", {
        name: /Dirty source.*Web Page.*Research handle dirty.*Unrated source/i,
      }),
    ).toBeTruthy();

    await userEvent.click(screen.getByText("Dirty source"));
    expect(openDocumentMock).toHaveBeenCalledWith("doc dirty");
  });
});
