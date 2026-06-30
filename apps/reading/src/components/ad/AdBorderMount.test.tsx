import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AdBorderMount } from "./AdBorderMount";
import type { AdBorderProps } from "./AdBorder";
import { READ_POSITION_EVENT } from "../../modes/Reading/usePosition";

const { adBorderMock } = vi.hoisted(() => ({
  adBorderMock: vi.fn((_props: AdBorderProps) => null),
}));

vi.mock("./AdBorder", () => ({
  AdBorder: (props: AdBorderProps) => adBorderMock(props),
}));

afterEach(() => {
  cleanup();
  adBorderMock.mockClear();
  window.sessionStorage.clear();
});

describe("AdBorderMount", () => {
  it("passes the active reader document and page to the live fill client path", () => {
    render(
      <MemoryRouter initialEntries={["/read/doc%201?page=4"]}>
        <AdBorderMount />
      </MemoryRouter>,
    );

    expect(adBorderMock).toHaveBeenCalledWith(
      expect.objectContaining({
        lens: "read",
        documentId: "doc 1",
        pageIndex: 4,
      }),
    );
  });

  it("omits reader slot identity outside /read/:documentId", () => {
    render(
      <MemoryRouter initialEntries={["/write"]}>
        <AdBorderMount />
      </MemoryRouter>,
    );

    expect(adBorderMock).toHaveBeenCalledWith(
      expect.objectContaining({
        lens: "write",
        documentId: null,
        pageIndex: null,
      }),
    );
  });

  it("does not treat the reserved meta-reading routes as BookReader document ids", () => {
    render(
      <MemoryRouter initialEntries={["/read/meta-reading/asset-1"]}>
        <AdBorderMount />
      </MemoryRouter>,
    );

    expect(adBorderMock).toHaveBeenCalledWith(
      expect.objectContaining({
        documentId: null,
        pageIndex: null,
      }),
    );
  });

  it("tracks the reader's session-stored active page after in-reader navigation", async () => {
    window.sessionStorage.setItem("antiek.read.pos.doc-1", "2");
    render(
      <MemoryRouter initialEntries={["/read/doc-1"]}>
        <AdBorderMount />
      </MemoryRouter>,
    );

    expect(adBorderMock).toHaveBeenCalledWith(
      expect.objectContaining({ documentId: "doc-1", pageIndex: 2 }),
    );

    window.dispatchEvent(
      new CustomEvent(READ_POSITION_EVENT, {
        detail: { documentId: "doc-1", pageIndex: 7 },
      }),
    );

    await waitFor(() =>
      expect(adBorderMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ documentId: "doc-1", pageIndex: 7 }),
      ),
    );
  });

  it("falls back to the stored reader page when the URL page param is malformed", () => {
    window.sessionStorage.setItem("antiek.read.pos.doc-2", "6");
    render(
      <MemoryRouter initialEntries={["/read/doc-2?page=not-a-number"]}>
        <AdBorderMount />
      </MemoryRouter>,
    );

    expect(adBorderMock).toHaveBeenCalledWith(
      expect.objectContaining({
        documentId: "doc-2",
        pageIndex: 6,
      }),
    );
  });
});
