/**
 * Uploads carry the title the user sees (FFX SPR-02 M3, finding A-04 client
 * half). Before this, the form had no title field and the multipart body had
 * no `title`, so every upload was named by its hex id in the reader,
 * Documents and Library. interfaces/research/api/upload_routes.py accepts
 * `title: str | None = Form(None)` and writes it for every upload kind.
 *
 * Mocked at the network boundary (apiFetch), so the real uploadSource builds
 * the FormData this test inspects.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return { ...actual, apiFetch: (...args: unknown[]) => apiFetchMock(...args) };
});

import Sources from "./index";

function ticket() {
  return new Response(
    JSON.stringify({ document_id: "doc-upload-1", detected_kind: "md", reader_html_available: true, chunk_count: 0 }),
    { status: 201, headers: { "Content-Type": "application/json" } },
  );
}

function chooseAndConfirm(fileName: string) {
  render(
    <MemoryRouter initialEntries={["/sources"]}>
      <Sources />
    </MemoryRouter>,
  );
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["# Notes"], fileName, { type: "text/markdown" })] } });
  fireEvent.click(screen.getByLabelText(/I confirm the attestation above/));
}

async function submittedForm(): Promise<FormData> {
  fireEvent.click(screen.getByRole("button", { name: "Upload and convert" }));
  await waitFor(() => expect(apiFetchMock).toHaveBeenCalled());
  const call = apiFetchMock.mock.calls.find(([url]) => String(url).endsWith("/sources/upload"));
  expect(call).toBeDefined();
  return (call![1] as RequestInit).body as FormData;
}

describe("Sources upload title", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockImplementation(() => Promise.resolve(ticket()));
  });
  afterEach(cleanup);

  it("pre-fills the title from the file name without its extension", () => {
    chooseAndConfirm("field-notes-on-spaced-repetition.md");
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe(
      "field-notes-on-spaced-repetition",
    );
  });

  it("sends the edited title in the multipart body", async () => {
    chooseAndConfirm("draft.v2.md");
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "  My draft on retrieval practice " } });
    const form = await submittedForm();
    expect(form.get("title")).toBe("My draft on retrieval practice");
    expect(form.get("acquisition_attestation")).toBe("personal_reading");
  });

  it("sends the file stem when the title field is cleared", async () => {
    chooseAndConfirm("draft.v2.md");
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "   " } });
    const form = await submittedForm();
    expect(form.get("title")).toBe("draft.v2");
  });
});
