import { describe, expect, it, vi } from "vitest";

import {
  fetchTwinForAsset,
  parseTwinDocument,
  twinUrlForAsset,
} from "./fetchTwin";

describe("parseTwinDocument", () => {
  it("accepts a well-formed live twin", () => {
    const twin = parseTwinDocument(
      {
        id: "twin-1",
        parentAssetId: "doc-9",
        isTwin: true,
        status: "ready",
        insights: [{ id: "i1", text: "Insight A" }],
        questions: [{ id: "q1", text: "Why?", open: true }],
      },
      "doc-9",
    );
    expect(twin?.id).toBe("twin-1");
    expect(twin?.isTwin).toBe(true);
    expect(twin?.insights).toHaveLength(1);
    expect(twin?.questions[0]?.open).toBe(true);
  });

  it("rejects parent mismatch and non-twins (anti-recursion)", () => {
    expect(
      parseTwinDocument(
        { id: "t", parentAssetId: "other", isTwin: true, insights: [], questions: [] },
        "doc-9",
      ),
    ).toBeNull();
    expect(
      parseTwinDocument(
        { id: "t", parentAssetId: "doc-9", isTwin: false, insights: [], questions: [] },
        "doc-9",
      ),
    ).toBeNull();
  });

  it("accepts snake_case parent_asset_id alias", () => {
    const twin = parseTwinDocument(
      {
        id: "t",
        parent_asset_id: "doc-9",
        is_twin: true,
        insights: [],
        questions: [],
      },
      "doc-9",
    );
    expect(twin?.parentAssetId).toBe("doc-9");
  });
});

describe("fetchTwinForAsset", () => {
  it("returns live twin on 200", async () => {
    const fetchImpl = vi.fn(async () =>
      new Response(
        JSON.stringify({
          id: "twin-live",
          parentAssetId: "doc-42",
          isTwin: true,
          status: "ready",
          insights: [{ id: "i", text: "Live insight" }],
          questions: [],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    const result = await fetchTwinForAsset("doc-42", { fetchImpl: fetchImpl as unknown as typeof fetch });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.source).toBe("live");
      expect(result.twin.insights[0]?.text).toBe("Live insight");
    }
    const firstCall = fetchImpl.mock.calls.at(0);
    expect(firstCall).toBeDefined();
    expect(String(firstCall?.[0])).toContain("/twins/doc-42");
  });

  it("returns not_found on 404 without throwing", async () => {
    const fetchImpl = vi.fn(async () => new Response("gone", { status: 404 }));
    const result = await fetchTwinForAsset("missing", {
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(result).toEqual({ ok: false, reason: "not_found", status: 404 });
  });

  it("returns shape_rejected when body is not a twin", async () => {
    const fetchImpl = vi.fn(async () =>
      new Response(JSON.stringify({ hello: "world" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const result = await fetchTwinForAsset("doc", {
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe("shape_rejected");
  });
});

describe("twinUrlForAsset", () => {
  it("encodes parent id in path", () => {
    expect(twinUrlForAsset("a/b")).toContain("/twins/a%2Fb");
  });
});
