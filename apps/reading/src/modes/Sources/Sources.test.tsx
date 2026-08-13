import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const uploadSourceMock = vi.fn();
vi.mock("../../lib/sourceUploadApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/sourceUploadApi")>();
  return { ...actual, uploadSource: (...args: unknown[]) => uploadSourceMock(...args) };
});

import Sources from "./index";

function renderSources() {
  return render(
    <MemoryRouter initialEntries={["/sources"]}>
      <Routes>
        <Route path="/sources" element={<Sources />} />
        <Route path="/read/:documentId" element={<p>Canonical reader</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Sources document upload", () => {
  beforeEach(() => uploadSourceMock.mockReset());
  afterEach(cleanup);

  it("does not upload until a file and provenance choice are confirmed", async () => {
    renderSources();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["body"], "held.pdf", { type: "application/pdf" })] } });
    expect(uploadSourceMock).not.toHaveBeenCalled();
    expect((screen.getByRole("button", { name: "Upload and convert" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/I lawfully hold this copy/));
    expect((screen.getByRole("button", { name: "Upload and convert" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("turns the conversion ticket into the canonical reader route", async () => {
    uploadSourceMock.mockResolvedValue({ document_id: "doc-upload-1", detected_kind: "pdf", reader_html_available: true, chunk_count: 0 });
    renderSources();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["body"], "held.pdf")] } });
    fireEvent.click(screen.getByLabelText(/I lawfully hold this copy/));
    fireEvent.click(screen.getByRole("button", { name: "Upload and convert" }));
    await waitFor(() => expect(uploadSourceMock).toHaveBeenCalledTimes(1));
    fireEvent.click(await screen.findByRole("button", { name: "Open in reader" }));
    expect(await screen.findByText("Canonical reader")).toBeTruthy();
  });

  it("keeps the active file stable while its conversion is pending", async () => {
    let finish!: (value: unknown) => void;
    uploadSourceMock.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    renderSources();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["A"], "first.pdf")] } });
    fireEvent.click(screen.getByLabelText(/I lawfully hold this copy/));
    fireEvent.click(screen.getByRole("button", { name: "Upload and convert" }));

    const chooser = screen.getByRole("button", { name: /Document selected/ }) as HTMLButtonElement;
    expect(chooser.disabled).toBe(true);
    fireEvent.drop(chooser, { dataTransfer: { files: [new File(["B"], "second.pdf")] } });
    expect(screen.getByText("first.pdf")).toBeTruthy();
    expect(screen.queryByText("second.pdf")).toBeNull();

    finish({ document_id: "doc-A", detected_kind: "pdf", reader_html_available: true, chunk_count: 0 });
    expect(await screen.findByRole("button", { name: "Open in reader" })).toBeTruthy();
  });
});
