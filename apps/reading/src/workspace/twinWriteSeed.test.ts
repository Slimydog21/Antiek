import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  TWIN_WRITE_SEED_KEY_PREFIX,
  buildDeepResearchWriteHref,
  buildTwinWriteHref,
  buildHostedHtmlWriteHref,
  buildMarketplaceWriteHref,
  buildMergedDocWriteHref,
  buildWriteHtmlDraftHref,
  loadTwinWriteSeed,
  plainTextFromHtml,
  storeTwinWriteSeed,
} from "./twinWriteSeed";

describe("twinWriteSeed (pp)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });
  afterEach(() => {
    window.sessionStorage.clear();
  });

  it("stores and loads twin write seed", () => {
    const key = storeTwinWriteSeed({
      plain_text: "[question] Why?\n\n[insight] Because.",
      html: "<article data-twin-draft=\"true\"><p>Why?</p></article>",
      title: "Twin draft · asset · 2 note(s)",
      asset_id: "asset-1",
      note_ids: ["q1", "i1"],
    });
    expect(key).toBeTruthy();
    expect(key!.startsWith(TWIN_WRITE_SEED_KEY_PREFIX)).toBe(true);
    const loaded = loadTwinWriteSeed(key!);
    expect(loaded?.plain_text).toMatch(/\[question\] Why\?/);
    expect(loaded?.view_format).toBe("html");
    expect(loaded?.source).toBe("twin_draft_selected");
    expect(loaded?.note_ids).toEqual(["q1", "i1"]);
  });

  it("rejects empty plain_text and foreign keys", () => {
    expect(
      storeTwinWriteSeed({
        plain_text: "  ",
        html: "<p>x</p>",
        title: "t",
        asset_id: "a",
        note_ids: [],
      }),
    ).toBeNull();
    expect(loadTwinWriteSeed("evil.key")).toBeNull();
    expect(loadTwinWriteSeed(`${TWIN_WRITE_SEED_KEY_PREFIX}missing`)).toBeNull();
  });

  it("builds write handoff href", () => {
    expect(buildTwinWriteHref("antiek.twin_write_seed.abc")).toBe(
      "/write?twin_seed=antiek.twin_write_seed.abc",
    );
    expect(buildTwinWriteHref("")).toBe("/write");
  });

  it("builds dual html_draft + twin_seed Write href (pz)", () => {
    expect(
      buildWriteHtmlDraftHref({ documentId: "draft_moil_1" }),
    ).toBe("/write?html_draft=draft_moil_1");
    expect(
      buildWriteHtmlDraftHref({
        documentId: "draft_moil_1",
        twinSeedKey: "antiek.twin_write_seed.xyz",
      }),
    ).toBe(
      "/write?html_draft=draft_moil_1&twin_seed=antiek.twin_write_seed.xyz",
    );
    expect(buildWriteHtmlDraftHref({ documentId: "  " })).toBe("/write");
  });

  it("strips HTML for MO deposit twin_seed plain text (pz)", () => {
    expect(plainTextFromHtml("<p>Hello <b>world</b></p>")).toBe("Hello world");
    expect(plainTextFromHtml("   ")).toBe("");
  });

  it("builds merged-doc dual Write href with twin_seed (qd/qe)", () => {
    const href = buildMergedDocWriteHref({
      documentId: "draft_merge_1",
      title: "Merged",
      html: "<article><p>Merge body</p></article>",
      source: "spawn_merge",
    });
    expect(href).toMatch(/html_draft=draft_merge_1/);
    expect(href).toMatch(/twin_seed=antiek\.twin_write_seed\./);
  });

  it("builds marketplace dual Write href with twin_seed (qc)", () => {
    const href = buildMarketplaceWriteHref({
      documentId: "hdoc_abc",
      title: "Principia",
      html: "<article><p>Book body</p></article>",
    });
    expect(href).toMatch(/html_draft=hdoc_abc/);
    expect(href).toMatch(/twin_seed=antiek\.twin_write_seed\./);
  });

  it("stores midnight_oil_deposit source provenance (pz)", () => {
    const key = storeTwinWriteSeed({
      plain_text: "MO deposit body",
      html: "<article>MO deposit body</article>",
      title: "Midnight Oil · moil_1",
      asset_id: "draft_moil_1",
      note_ids: [],
      source: "midnight_oil_deposit",
    });
    expect(loadTwinWriteSeed(key!)?.source).toBe("midnight_oil_deposit");
  });

  it("builds hosted HTML dual Write href with twin_seed (qu)", () => {
    const href = buildHostedHtmlWriteHref({
      documentId: "doc_abc",
      title: "Attention",
      html: "<article><p>Transformers.</p></article>",
    });
    expect(href).toMatch(/html_draft=doc_abc/);
    expect(href).toMatch(/twin_seed=antiek\.twin_write_seed\./);
  });

  it("builds deep research twin_seed Write href without inventing document_id (qv)", () => {
    const href = buildDeepResearchWriteHref({
      selectionText: "Attention is routing.",
      goal: "Deep-research the highlight",
      spawnId: "spn_qv_1",
      parentAssetId: "book-1",
    });
    expect(href).toBeTruthy();
    expect(href!).toMatch(/^\/write\?twin_seed=antiek\.twin_write_seed\./);
    expect(href!).not.toMatch(/html_draft=/);
    const key = decodeURIComponent(
      (href!.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    const seed = loadTwinWriteSeed(key);
    expect(seed?.source).toBe("deep_research_session");
    expect(seed?.view_format).toBe("html");
    expect(seed?.asset_id).toBe("book-1");
    expect(seed?.plain_text).toMatch(/Attention is routing/);
    expect(seed?.plain_text).toMatch(/Deep-research the highlight/);
    expect(seed?.html).toMatch(/data-source="deep_research_session"/);
    expect(seed?.html).toMatch(/data-spawn-id="spn_qv_1"/);
  });

  it("returns null for empty deep research selection+goal (qv)", () => {
    expect(
      buildDeepResearchWriteHref({
        selectionText: "  ",
        goal: "",
        spawnId: "spn_empty",
      }),
    ).toBeNull();
  });

  it("falls back asset_id to deep_research:spawn when parent missing (qv)", () => {
    const href = buildDeepResearchWriteHref({
      selectionText: "Only selection",
      spawnId: "spn_orphan",
    });
    expect(href).toBeTruthy();
    const key = decodeURIComponent(
      (href!.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    expect(loadTwinWriteSeed(key)?.asset_id).toBe("deep_research:spn_orphan");
  });

});
