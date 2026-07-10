import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  TWIN_WRITE_SEED_KEY_PREFIX,
  buildContextSearchWriteHref,
  buildDeepResearchWriteHref,
  buildResearchContextWriteHref,
  buildEvidencePackWriteHref,
  buildPublicationHydrateWriteHref,
  buildResearchProgressWriteHref,
  buildSessionFlywheelWriteHref,
  buildTwinPromoteWriteHref,
  buildTwinWriteHref,
  buildHostedHtmlWriteHref,
  buildMarketplaceWriteHref,
  buildMergedDocWriteHref,
  buildWriteHtmlDraftHref,
  formatTwinWriteSeedFreeform,
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

  it("preserves twin_cross_asset_merge source (vd)", () => {
    const key = storeTwinWriteSeed({
      plain_text: "[insight] Cross asset claim.",
      html: '<article data-source="twin_cross_asset_merge"><p>Cross</p></article>',
      title: "Twin draft · a+b · 1 note(s)",
      asset_id: "a+b",
      note_ids: ["n1"],
      source: "twin_cross_asset_merge",
    });
    expect(key).toBeTruthy();
    const loaded = loadTwinWriteSeed(key!);
    expect(loaded?.source).toBe("twin_cross_asset_merge");
    expect(loaded?.asset_id).toBe("a+b");
  });

  it("builds hosted twin_cross_asset_merge Write seed source (vg)", () => {
    const href = buildHostedHtmlWriteHref({
      documentId: "twin_draft_a_b",
      title: "Twin draft · a+b",
      html: '<article data-source="twin_cross_asset_merge"><p>Cross merge.</p></article>',
      source: "twin_cross_asset_merge",
    });
    expect(href).toMatch(/twin_seed=antiek\.twin_write_seed\./);
    const key = decodeURIComponent(
      (href.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    const seed = loadTwinWriteSeed(key);
    expect(seed?.source).toBe("twin_cross_asset_merge");
    expect(seed?.title).toMatch(/Twin draft|Cross-asset|a\+b/i);
  });

  it("builds hosted collective_written_analysis Write seed source (vk)", () => {
    const href = buildHostedHtmlWriteHref({
      documentId: "analysis:col_1",
      title: "Written analysis · 3 spawns",
      html: '<article data-source="collective_written_analysis"><p>Analysis.</p></article>',
      source: "collective_written_analysis",
    });
    const key = decodeURIComponent(
      (href.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    const seed = loadTwinWriteSeed(key);
    expect(seed?.source).toBe("collective_written_analysis");
    expect(seed?.title).toMatch(/Written analysis|Collective written analysis/i);
  });

  it("builds hosted spawn_merge and collective_doc_merge Write seed sources (vp)", () => {
    const hrefSpawn = buildHostedHtmlWriteHref({
      documentId: "merge_spawn_1",
      title: "Spawn merge",
      html: "<p>Merged spawns.</p>",
      source: "spawn_merge",
    });
    const keySpawn = decodeURIComponent(
      (hrefSpawn.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    expect(loadTwinWriteSeed(keySpawn)?.source).toBe("spawn_merge");

    const hrefCol = buildHostedHtmlWriteHref({
      documentId: "merge_col_1",
      title: "Collective merge",
      html: "<p>Merged collective docs.</p>",
      source: "collective_doc_merge",
    });
    const keyCol = decodeURIComponent(
      (hrefCol.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    expect(loadTwinWriteSeed(keyCol)?.source).toBe("collective_doc_merge");
  });

  it("builds hosted marketplace_host and midnight_oil_deposit Write seed sources (vr)", () => {
    const hrefMkt = buildHostedHtmlWriteHref({
      documentId: "hdoc_mkt",
      title: "Hosted book",
      html: "<p>Marketplace book body.</p>",
      source: "marketplace_host",
    });
    const keyMkt = decodeURIComponent(
      (hrefMkt.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    expect(loadTwinWriteSeed(keyMkt)?.source).toBe("marketplace_host");

    const hrefMo = buildHostedHtmlWriteHref({
      documentId: "draft_moil_1",
      title: "MO deposit",
      html: "<p>Deposit body.</p>",
      source: "midnight_oil_deposit",
    });
    const keyMo = decodeURIComponent(
      (hrefMo.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    expect(loadTwinWriteSeed(keyMo)?.source).toBe("midnight_oil_deposit");
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
    const key = decodeURIComponent(
      (href.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    expect(loadTwinWriteSeed(key)?.source).toBe("hosted_html_document");
  });

  it("builds evidence_pack hosted Write seed source (si)", () => {
    const href = buildHostedHtmlWriteHref({
      documentId: "evidence:paper:abc",
      title: "Evidence pack (citation trust)",
      html: "<p>Insight: routing.</p>",
      source: "evidence_pack",
    });
    expect(href).toMatch(/html_draft=evidence%3Apaper%3Aabc|html_draft=evidence:paper:abc/);
    expect(href).toMatch(/twin_seed=antiek\.twin_write_seed\./);
    const key = decodeURIComponent(
      (href.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    const seed = loadTwinWriteSeed(key);
    expect(seed?.source).toBe("evidence_pack");
    expect(seed?.title).toMatch(/Evidence pack/);
  });

  it("builds context_search hosted Write seed source (sj)", () => {
    const href = buildHostedHtmlWriteHref({
      documentId: "context_search:paper:abc",
      title: "Context search · attention",
      html: "<p>Query: attention · hits=1</p>",
      source: "context_search",
    });
    expect(href).toMatch(/twin_seed=antiek\.twin_write_seed\./);
    const key = decodeURIComponent(
      (href.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    expect(loadTwinWriteSeed(key)?.source).toBe("context_search");
  });

  it("builds collective_unit_prompt hosted Write seed source (tu)", () => {
    const href = buildHostedHtmlWriteHref({
      documentId: "collective_unit:col_abc:xyz",
      title: "Collective unit · col_abc",
      html: '<article data-source="collective_unit_prompt"><p>Unit prompt.</p></article>',
      source: "collective_unit_prompt",
    });
    expect(href).toMatch(/html_draft=/);
    expect(href).toMatch(/twin_seed=antiek\.twin_write_seed\./);
    const key = decodeURIComponent(
      (href.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    const seed = loadTwinWriteSeed(key);
    // Residual (tu): must not collapse to twin_draft_selected (allowlist gap).
    expect(seed?.source).toBe("collective_unit_prompt");
    expect(seed?.title).toBe("Collective unit · col_abc");
    expect(seed?.asset_id).toBe("collective_unit:col_abc:xyz");
    expect(seed?.plain_text).toMatch(/Unit prompt/);

    // Default title when host title empty.
    const href2 = buildHostedHtmlWriteHref({
      documentId: "collective_unit:col_def:1",
      html: "<p>Unit B</p>",
      source: "collective_unit_prompt",
    });
    const key2 = decodeURIComponent(
      (href2.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    expect(loadTwinWriteSeed(key2)?.title).toMatch(/Collective cohesive unit/);
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

  it("builds twin promote Write twin_seed (rr)", () => {
    const href = buildTwinPromoteWriteHref({
      assetId: "paper-1",
      query: "attention",
      contextUnits: [
        { kind: "insight", text: "Attention is routing.", unit_id: "u1" },
        { kind: "question", text: "Why multi-head?", unit_id: "u2" },
      ],
      noteIds: ["n1", "n2"],
      promotedCount: 2,
    });
    expect(href).toBeTruthy();
    expect(href!).toMatch(/^\/write\?twin_seed=antiek\.twin_write_seed\./);
    const key = decodeURIComponent(
      (href!.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    const seed = loadTwinWriteSeed(key);
    expect(seed?.source).toBe("twin_promote_context");
    expect(seed?.note_ids).toEqual(["n1", "n2"]);
    expect(seed?.plain_text).toMatch(/\[insight\] Attention is routing/);
    expect(seed?.html).toMatch(/data-source="twin_promote_context"/);
  });

  it("builds research context pack Write twin_seed (ri)", () => {
    const href = buildResearchContextWriteHref({
      assetId: "paper-1",
      spawnId: "spn_1",
      promptBlock: "# Research context pack\n\nInsight: attention.",
      query: "attention",
      researchTier: "wrestle",
      twinCount: 2,
      refCount: 1,
    });
    expect(href).toBeTruthy();
    expect(href!).toMatch(/^\/write\?twin_seed=antiek\.twin_write_seed\./);
    const key = decodeURIComponent(
      (href!.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    const seed = loadTwinWriteSeed(key);
    expect(seed?.source).toBe("research_context_pack");
    expect(seed?.plain_text).toMatch(/Research context pack/);
    expect(seed?.html).toMatch(/data-source="research_context_pack"/);
  });

  it("builds context search Write twin_seed (rf)", () => {
    const href = buildContextSearchWriteHref({
      assetId: "paper-1",
      query: "attention",
      hits: [{ kind: "insight", id: "i1", text: "Attention is routing." }],
      researchTier: "deep",
    });
    expect(href).toBeTruthy();
    expect(href!).toMatch(/^\/write\?twin_seed=antiek\.twin_write_seed\./);
    const key = decodeURIComponent(
      (href!.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    const seed = loadTwinWriteSeed(key);
    expect(seed?.source).toBe("context_search");
    expect(seed?.plain_text).toMatch(/Query: attention/);
    expect(seed?.html).toMatch(/data-source="context_search"/);
  });

  it("builds session flywheel Write twin_seed (re)", () => {
    const href = buildSessionFlywheelWriteHref({
      sessionId: "fsess_1",
      spawnId: "spn_1",
      outputText: "Attention is routing.",
      promptBlock: "# pack",
      status: "complete",
      researchTier: "wrestle",
    });
    expect(href).toBeTruthy();
    expect(href!).toMatch(/^\/write\?twin_seed=antiek\.twin_write_seed\./);
    const key = decodeURIComponent(
      (href!.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    const seed = loadTwinWriteSeed(key);
    expect(seed?.source).toBe("session_flywheel_complete");
    expect(seed?.plain_text).toMatch(/Attention is routing/);
    expect(seed?.html).toMatch(/data-source="session_flywheel_complete"/);
  });

  it("builds publication hydrate Write twin_seed (rc)", () => {
    const href = buildPublicationHydrateWriteHref({
      spawnId: "spn_pub",
      assets: [
        {
          asset_id: "pub_arxiv_1",
          title: "Attention Is All You Need",
          body_text: "Transformers.",
          html: "<p>Transformers.</p>",
          ref: {
            kind: "arxiv",
            raw: "arxiv:1706.03762",
            canonical_url: "https://arxiv.org/abs/1706.03762",
          },
        },
      ],
    });
    expect(href).toBeTruthy();
    expect(href!).toMatch(/^\/write\?twin_seed=antiek\.twin_write_seed\./);
    const key = decodeURIComponent(
      (href!.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    const seed = loadTwinWriteSeed(key);
    expect(seed?.source).toBe("publication_hydrate");
    expect(seed?.plain_text).toMatch(/\[pub\] Attention/);
    expect(seed?.html).toMatch(/data-source="publication_hydrate"/);
  });

  it("builds evidence pack Write twin_seed (rb)", () => {
    const href = buildEvidencePackWriteHref({
      assetId: "paper-1",
      spawnId: "spn_1",
      insights: ["Attention is routing."],
      questions: ["Why multi-head?"],
      sourceReferences: [
        {
          title_hint: "Attention Is All You Need",
          canonical_url: "https://arxiv.org/abs/1706.03762",
          kind: "arxiv",
          raw: "1706.03762",
        },
      ],
      researchTier: "wrestle",
      html: "<p>Evidence pack body</p>",
    });
    expect(href).toBeTruthy();
    expect(href!).toMatch(/^\/write\?twin_seed=antiek\.twin_write_seed\./);
    expect(href!).not.toMatch(/html_draft=/);
    const key = decodeURIComponent(
      (href!.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    const seed = loadTwinWriteSeed(key);
    expect(seed?.source).toBe("evidence_pack");
    expect(seed?.asset_id).toBe("paper-1");
    expect(seed?.plain_text).toMatch(/\[insight\] Attention is routing/);
    expect(seed?.plain_text).toMatch(/\[question\] Why multi-head/);
    expect(seed?.plain_text).toMatch(/\[ref\]/);
    expect(seed?.html).toMatch(/data-source="evidence_pack"/);
  });

  it("returns null for empty evidence pack (rb)", () => {
    expect(
      buildEvidencePackWriteHref({
        assetId: "paper",
        insights: [],
        questions: [],
        sourceReferences: [],
      }),
    ).toBeNull();
  });

  it("formats freeform provenance with source (qx)", () => {
    expect(
      formatTwinWriteSeedFreeform({
        source: "deep_research_session",
        asset_id: "book-1",
        note_ids: [],
      }),
    ).toBe("twin_seed:deep_research_session:0:book-1");
    expect(
      formatTwinWriteSeedFreeform({
        source: "research_progress_complete",
        asset_id: "deep_research:spn_1",
        note_ids: ["n1"],
      }),
    ).toBe("twin_seed:research_progress_complete:1:deep_research:spn_1");
    expect(
      formatTwinWriteSeedFreeform({
        source: "twin_draft_selected",
        asset_id: "paper-pp",
        note_ids: ["q1", "i1"],
      }),
    ).toBe("twin_seed:twin_draft_selected:2:paper-pp");
  });

  it("builds mid-flight progress draft Write twin_seed when allowInProgress (rp)", () => {
    const href = buildResearchProgressWriteHref({
      spawnId: "spn_draft",
      isTerminal: false,
      allowInProgress: true,
      latestStage: "gather",
      events: [{ stage: "plan", message: "planned" }, { stage: "gather", message: "g" }],
    });
    expect(href).toBeTruthy();
    const key = decodeURIComponent(
      (href!.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    const seed = loadTwinWriteSeed(key);
    expect(seed?.source).toBe("research_progress_draft");
    expect(seed?.plain_text).toMatch(/In-progress stage: gather/);
    expect(seed?.html).toMatch(/data-is-terminal="false"/);
  });

  it("builds terminal progress Write twin_seed only when isTerminal (qw)", () => {
    expect(
      buildResearchProgressWriteHref({
        spawnId: "spn_prog",
        isTerminal: false,
        latestStage: "cite",
        events: [{ stage: "cite", message: "done" }],
      }),
    ).toBeNull();
    const href = buildResearchProgressWriteHref({
      spawnId: "spn_prog",
      parentAssetId: "book-1",
      researchTier: "wrestle",
      latestStage: "cite",
      isTerminal: true,
      goal: "Prove attention",
      events: [
        { stage: "plan", message: "planned" },
        { stage: "cite", message: "cited" },
      ],
      html: "<p>Synthesis body</p>",
    });
    expect(href).toBeTruthy();
    expect(href!).toMatch(/^\/write\?twin_seed=antiek\.twin_write_seed\./);
    expect(href!).not.toMatch(/html_draft=/);
    const key = decodeURIComponent(
      (href!.match(/twin_seed=([^&]+)/) || [])[1] || "",
    );
    const seed = loadTwinWriteSeed(key);
    expect(seed?.source).toBe("research_progress_complete");
    expect(seed?.asset_id).toBe("book-1");
    expect(seed?.plain_text).toMatch(/Prove attention/);
    expect(seed?.plain_text).toMatch(/\[cite\] cited/);
    expect(seed?.html).toMatch(/data-source="research_progress_complete"/);
    expect(seed?.html).toMatch(/data-is-terminal="true"/);
  });

});
