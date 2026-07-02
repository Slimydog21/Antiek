import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async () => {
  const actual =
    await vi.importActual<typeof import("../../lib/api")>("../../lib/api");
  return {
    ...actual,
    API_BASE: "https://api.test",
    apiFetch: apiFetchMock,
  };
});

import { ApiError } from "../../lib/api";
import { savePerDocNotebook } from "./by-doc";

describe("savePerDocNotebook", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
  });

  it("posts the document-bound notebook save payload to the backend", async () => {
    const payload = {
      notebook_id: "nb-doc-1",
      content_json: { type: "doc", content: [] },
      blocks: [],
      save_kind: "explicit" as const,
    };
    apiFetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          notebook_id: "nb-doc-1",
          content_json: payload.content_json,
          blocks: [],
          updated_at: "2026-06-30T00:00:00Z",
          version: 1,
          archive_url: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const saved = await savePerDocNotebook(" doc/with space ", {
      ...payload,
      notebook_id: " nb-doc-1 ",
    });

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetchMock.mock.calls[0];
    expect(url).toBe(
      "https://api.test/notebooks/by-doc/doc%2Fwith%20space/save",
    );
    expect(init).toMatchObject({
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    expect(JSON.parse(init.body as string)).toEqual(payload);
    expect(saved.notebook_id).toBe("nb-doc-1");
  });

  it("normalizes malformed optional request fields without fabricating body blocks", async () => {
    apiFetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ notebook_id: "nb-doc-1", blocks: [] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await savePerDocNotebook("doc-1", {
      notebook_id: " nb-doc-1 ",
      content_json: undefined,
      blocks: "not-array" as unknown as unknown[],
      save_kind: "autosave",
    });

    const [, init] = apiFetchMock.mock.calls[0];
    expect(JSON.parse(init.body as string)).toEqual({
      notebook_id: "nb-doc-1",
      content_json: null,
      blocks: [],
      save_kind: "autosave",
    });
  });

  it("rejects malformed save request fields before sending", async () => {
    const payload = {
      notebook_id: "nb-doc-1",
      content_json: { type: "doc", content: [] },
      blocks: [],
      save_kind: "explicit" as const,
    };

    await expect(savePerDocNotebook(" ", payload)).rejects.toThrow(/documentId/);
    await expect(savePerDocNotebook("doc-1", { ...payload, notebook_id: " " })).rejects.toThrow(/notebook_id/);
    await expect(
      savePerDocNotebook("doc-1", { ...payload, save_kind: "draft" as "explicit" }),
    ).rejects.toThrow(/save_kind/);

    expect(apiFetchMock).not.toHaveBeenCalled();
  });

  it("sanitizes optional save response fields", async () => {
    const payload = {
      notebook_id: "nb-doc-1",
      content_json: { type: "doc", content: [] },
      blocks: [],
      save_kind: "explicit" as const,
    };
    apiFetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          notebook_id: " nb-doc-1 ",
          document_id: " ",
          content_json: undefined,
          blocks: "not-array",
          updated_at: " 2026-06-30T00:00:00Z ",
          version: Number.POSITIVE_INFINITY,
          archive_url: " ",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const saved = await savePerDocNotebook("doc-1", payload);

    expect(saved).toEqual({
      notebook_id: "nb-doc-1",
      document_id: "doc-1",
      content_json: null,
      blocks: [],
      updated_at: "2026-06-30T00:00:00Z",
      version: undefined,
      archive_url: undefined,
    });
  });

  it("throws ApiError when the save response has no usable notebook id", async () => {
    apiFetchMock.mockResolvedValue(
      new Response(JSON.stringify({ notebook_id: " ", blocks: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const promise = savePerDocNotebook("doc-1", {
      notebook_id: "nb-doc-1",
      content_json: { type: "doc", content: [] },
      blocks: [],
      save_kind: "autosave",
    });

    await expect(promise).rejects.toBeInstanceOf(ApiError);
    await expect(promise).rejects.toMatchObject({ status: 502 });
  });

  it("throws ApiError with response text on backend failure", async () => {
    apiFetchMock.mockResolvedValue(
      new Response("bound elsewhere", { status: 409 }),
    );

    const promise = savePerDocNotebook("doc-1", {
      notebook_id: "nb-doc-1",
      content_json: { type: "doc", content: [] },
      blocks: [],
      save_kind: "autosave",
    });

    await expect(promise).rejects.toBeInstanceOf(ApiError);
    await expect(promise).rejects.toMatchObject({
      status: 409,
      body: "bound elsewhere",
    });
  });
});
