import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.fn();

vi.mock("./api", () => ({
  API_BASE: "https://api.example.test",
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
}));

import {
  SOURCE_UPLOAD_MAX_BYTES,
  SourceUploadError,
  uploadSource,
  validateSourceUpload,
} from "./sourceUploadApi";

describe("sourceUploadApi", () => {
  beforeEach(() => apiFetchMock.mockReset());

  it("pins client validation to the backend's 64 MiB ceiling", () => {
    const tooLarge = new File(["x"], "private.pdf");
    Object.defineProperty(tooLarge, "size", { value: SOURCE_UPLOAD_MAX_BYTES + 1 });
    expect(validateSourceUpload(tooLarge)).toBe("too_large");
    expect(validateSourceUpload(new File(["x"], "private.epub"))).toBe("unsupported");
    expect(validateSourceUpload(new File(["x"], "private.docx"))).toBeNull();
  });

  it("posts multipart attestation and returns the conversion ticket", async () => {
    apiFetchMock.mockResolvedValue(new Response(JSON.stringify({
      document_id: "doc-upload-safe",
      detected_kind: "pdf",
      reader_html_available: true,
      chunk_count: 0,
    }), { status: 201, headers: { "Content-Type": "application/json" } }));

    const result = await uploadSource(new File(["body"], "private.pdf"), "personal_reading");
    expect(result.document_id).toBe("doc-upload-safe");
    const [url, init] = apiFetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://api.example.test/sources/upload");
    expect(init.method).toBe("POST");
    expect((init.body as FormData).get("acquisition_attestation")).toBe("personal_reading");
  });

  it("maps server failures to value-free typed errors", async () => {
    apiFetchMock.mockResolvedValue(new Response("private.pdf failed conversion", { status: 422 }));
    const promise = uploadSource(new File(["body"], "private.pdf"), "personal_reading");
    await expect(promise).rejects.toMatchObject({ code: "conversion_failed" } satisfies Partial<SourceUploadError>);
    await expect(promise).rejects.not.toThrow(/private\.pdf/);
  });
});
