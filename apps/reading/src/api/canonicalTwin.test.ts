import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getCanonicalTwin,
  getCurrentPromotion,
  getReviewedPromotions,
  trustedCanonicalHtml,
} from "./canonicalTwin";

afterEach(() => vi.restoreAllMocks());

describe("canonical twin API", () => {
  it("encodes source identity and includes owner credentials", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        document_id: "twin-doc",
        source_asset_id: "asset / one",
        source_hash: "revision?one",
        title: "Twin",
        html_fragment: "<p>Body</p>",
        authority: "advisory",
        authority_label: "Verify against sources",
        shareable: false,
        reviewed_promotions_href: "/reader/sources/asset%20%2F%20one/reviewed-promotions?source_hash=revision%3Fone",
      }), { status: 200 }),
    );
    await getCanonicalTwin("asset / one", "revision?one");
    expect(fetch).toHaveBeenCalledWith(
      "/reader/sources/asset%20%2F%20one/canonical-twin?source_hash=revision%3Fone",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("follows only exact server-owned private links", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({
        source_asset_id: "source-a",
        source_hash: "revision-a",
        items: [],
        complete: true,
        authority: "current_owner_reviewed_source_promotions_v1",
      }), { status: 200 })),
    );
    await getReviewedPromotions(
      "/reader/sources/source-a/reviewed-promotions?source_hash=revision-a",
    );
    expect(fetch).toHaveBeenNthCalledWith(
      1,
      "/reader/sources/source-a/reviewed-promotions?source_hash=revision-a",
      expect.any(Object),
    );
    await expect(getCurrentPromotion("https://attacker.invalid/candidate-a")).rejects.toThrow(
      "private_reader_link_invalid",
    );
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("rejects malformed and unknown response fields", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ source_asset_id: "source-a", extra: true }), { status: 200 }),
    );
    await expect(getCanonicalTwin("source-a", "revision-a")).rejects.toThrow(
      "canonical_twin_fields_invalid",
    );
  });

  it("rejects active HTML and external navigation before DOM insertion", () => {
    expect(() => trustedCanonicalHtml("<script>alert(1)</script>")).toThrow(
      "canonical_html_tag_invalid",
    );
    expect(() => trustedCanonicalHtml('<p onclick="alert(1)">Body</p>')).toThrow(
      "canonical_html_attribute_invalid",
    );
    expect(() => trustedCanonicalHtml('<a href="https://attacker.invalid">leave</a>')).toThrow(
      "canonical_html_link_invalid",
    );
    expect(trustedCanonicalHtml('<h2 id="section">Safe</h2><a href="#section">Return</a>')).toContain(
      "#section",
    );
  });
});
