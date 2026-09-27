/** Uses the real upload client to distinguish user titles from filename placeholders. */
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

  it("shows the filename as a placeholder without choosing a title", () => {
    chooseAndConfirm("field-notes-on-spaced-repetition.md");
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("");
    expect(screen.getByLabelText("Title").getAttribute("placeholder")).toBe("field-notes-on-spaced-repetition");
  });

  it("omits an untouched title", async () => {
    chooseAndConfirm("draft.v2.md");
    expect((await submittedForm()).has("title")).toBe(false);
  });

  it("resets an explicit title and attestation on file replacement", () => {
    chooseAndConfirm("first.md");
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Old title" } });
    const fileInput = document.querySelector('input[type="file"]');
    if (!fileInput) throw new Error("File input missing");
    fireEvent.change(fileInput, { target: { files: [new File(["# Second"], "second.md")] } });
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("");
    expect(screen.getByLabelText("Title").getAttribute("placeholder")).toBe("second");
    expect((screen.getByLabelText(/I confirm the attestation above/) as HTMLInputElement).checked).toBe(false);
  });

  it("sends the edited title in the multipart body", async () => {
    chooseAndConfirm("draft.v2.md");
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "  My draft on retrieval practice " } });
    const form = await submittedForm();
    expect(form.get("title")).toBe("My draft on retrieval practice");
    expect(form.get("acquisition_attestation")).toBe("personal_reading");
  });

  it("omits the title when the field is cleared", async () => {
    chooseAndConfirm("draft.v2.md");
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "   " } });
    const form = await submittedForm();
    expect(form.has("title")).toBe(false);
  });
});
