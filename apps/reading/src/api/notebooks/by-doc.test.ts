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

    const saved = await savePerDocNotebook("doc/with space", payload);

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
