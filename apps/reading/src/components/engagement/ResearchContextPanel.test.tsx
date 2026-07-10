import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ResearchContextPanel,
  domainAwareSearchDefault,
  twinNoteMetrics,
} from "./ResearchContextPanel";

const fetchResearchContext = vi.fn();
const attachSourceRefs = vi.fn();
const fetchEvidencePack = vi.fn();
const hydratePublicationRef = vi.fn();
const searchEngagementContext = vi.fn();
const promoteTwinsToContext = vi.fn();
const openWindow = vi.fn(() => "win:evidence:test");

vi.mock("../windows/openWindow", () => ({
  openWindow: (...args: unknown[]) => openWindow(...args),
}));

vi.mock("./DecisionTreeDriverBadge", () => ({
  DecisionTreeDriverBadge: (props: {
    researchTier?: string | null;
    promptText?: string | null;
  }) => (
    <div
      data-testid="decision-tree-driver-badge-stub"
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
      data-prompt-len={String((props.promptText || "").length)}
    >
      driver badge
    </div>
  ),
}));
vi.mock("../../api/engagement", () => ({
  fetchResearchContext: (...args: unknown[]) => fetchResearchContext(...args),
  attachSourceRefs: (...args: unknown[]) => attachSourceRefs(...args),
  fetchEvidencePack: (...args: unknown[]) => fetchEvidencePack(...args),
  hydratePublicationRef: (...args: unknown[]) => hydratePublicationRef(...args),
  searchEngagementContext: (...args: unknown[]) =>
    searchEngagementContext(...args),
  promoteTwinsToContext: (...args: unknown[]) => promoteTwinsToContext(...args),
}));

describe("ResearchContextPanel", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    fetchResearchContext.mockReset();
    attachSourceRefs.mockReset();
    fetchEvidencePack.mockReset();
    hydratePublicationRef.mockReset();
    searchEngagementContext.mockReset();
    promoteTwinsToContext.mockReset();
    openWindow.mockClear();
  });

  it("domainAwareSearchDefault maps free STEM subjects (ahr/aiy)", () => {
    expect(domainAwareSearchDefault(["heat", "signal_processing"])).toMatch(
      /heat signal processing/i,
    );
    expect(domainAwareSearchDefault(["foundations", "logic"])).toMatch(
      /foundations incompleteness/i,
    );
    // Residual (aiy): biology / method / physics / mathematics free STEM.
    expect(domainAwareSearchDefault(["biology", "science"])).toMatch(
      /biology instruments micrographia/i,
    );
    expect(domainAwareSearchDefault(["method", "philosophy"])).toMatch(
      /method observation novum organum/i,
    );
    expect(domainAwareSearchDefault(["physics", "science"])).toMatch(
      /physics motion forces principia/i,
    );
    expect(domainAwareSearchDefault(["mathematics"])).toMatch(
      /mathematics geometry elements/i,
    );
    // Electricity still wins over bare physics when both present.
    expect(
      domainAwareSearchDefault(["physics", "electricity"]),
    ).toMatch(/electricity electromagnetism/i);
    expect(domainAwareSearchDefault([])).toBe("");
    expect(domainAwareSearchDefault(null)).toBe("");
  });

  it("prefills intelligent search query from domain subjects (ahr)", () => {
    render(
      <ResearchContextPanel
        assetId="pd-fourier-heat"
        domainSubjects={["heat", "signal_processing", "engineering"]}
      />,
    );
    const controls = screen.getByTestId("research-context-query-controls");
    expect(controls.getAttribute("data-domain-aware-default")).toBe("true");
    expect(controls.getAttribute("data-domain-subjects")).toMatch(/heat/);
    expect(
      (screen.getByTestId("research-context-query-input") as HTMLInputElement)
        .value,
    ).toMatch(/heat signal processing/i);
  });

  it("links dual-gate L1–L4 checklist for hydrate prep (mu)", () => {
    render(
      <ResearchContextPanel assetId="a1" spawnId="spn_1" />,
    );
    const dual = screen.getByTestId("research-context-dual-gate-checklist-link");
    // Residual (xe): L1 arxiv checklist section deep-link.
    expect(dual.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4.*#l1-arxiv/);
    expect(dual.textContent).toMatch(/L1 arxiv checklist/i);
    // Residual (aaq): L2 Substack checklist (parity aal–aap).
    const dualL2 = screen.getByTestId("research-context-dual-gate-l2-link");
    expect(dualL2.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4.*#l2-substack/);
    expect(dualL2.textContent).toMatch(/L2 Substack checklist/i);
  });

  it("links to Settings hydrate readiness (ie)", () => {
    render(<ResearchContextPanel assetId="paper" />);
    const link = screen.getByTestId("research-context-settings-link");
    expect(link.getAttribute("href")).toBe("/settings#hydrate-live-status");
    expect(link.textContent).toMatch(/hydrate readiness/i);
  });

  it("auto-loads context and evidence on mount when autoLoad (co)", async () => {
    fetchResearchContext.mockResolvedValue({
      asset_id: "paper",
      view_format: "html",
      twin_units: [],
      source_references: [],
      twin_count: 0,
      ref_count: 0,
      prompt_block: "# auto pack",
    });
    fetchEvidencePack.mockResolvedValue({
      asset_id: "paper",
      insight_count: 0,
      question_count: 0,
      ref_count: 0,
      insights: [],
      questions: [],
      source_references: [],
      view_format: "html",
      product_panel: "evidence",
      source: "test",
      notes: [],
      html: "<p>evidence</p>",
    });
    render(<ResearchContextPanel assetId="paper" autoLoad />);
    await waitFor(() => {
      expect(fetchResearchContext).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(fetchEvidencePack).toHaveBeenCalled();
    });
  });

  it("loads and renders prompt block", async () => {
    fetchResearchContext.mockResolvedValue({
      asset_id: "paper",
      view_format: "html",
      twin_units: [
        {
          unit_id: "u1",
          twin_note_id: "t1",
          kind: "insight",
          text: "Attention is routing.",
          canonical_text: "attention is routing.",
          asset_id: "paper",
          investigation_id: "inv",
        },
      ],
      source_references: [
        {
          ref_id: "s1",
          kind: "arxiv",
          raw: "1706.03762",
          canonical_url: "https://arxiv.org/abs/1706.03762",
        },
      ],
      twin_count: 1,
      ref_count: 1,
      research_tier: "wrestle",
      prompt_block:
        "# Research context for asset `paper`\nresearch_tier: wrestle\n",
    });

    render(<ResearchContextPanel assetId="paper" spawnId="spn_1" />);
    fireEvent.click(screen.getByTestId("load-research-context"));

    await waitFor(() => {
      expect(screen.getByTestId("prompt-block").textContent).toContain("paper");
    });
    expect(screen.getByText(/Attention is routing/)).toBeTruthy();
    expect(screen.getByText(/1706.03762/)).toBeTruthy();
    expect(fetchResearchContext).toHaveBeenCalledWith(
      expect.objectContaining({ asset_id: "paper", spawn_id: "spn_1" }),
    );
    // Residual (ri/aes): Open Write twin_seed from context pack + path honesty.
    const write = screen.getByTestId("research-context-open-write");
    const href = write.getAttribute("href") || "";
    expect(href).toMatch(/^\/write\?twin_seed=antiek\.twin_write_seed\./);
    expect(href).not.toMatch(/html_draft=/);
    expect(write.getAttribute("data-has-twin-seed")).toBe("1");
    // Residual (acr): prompt_block body → has-body true.
    expect(write.getAttribute("data-write-seed-has-body")).toBe("true");
    // Residual (aes): research context pack → Write path honesty.
    expect(write.getAttribute("data-asset-id")).toBe("paper");
    expect(write.getAttribute("data-spawn-id")).toBe("spn_1");
    expect(write.getAttribute("data-seamless-context-write")).toBe("true");
    // Residual (sl): float|full research context pack HTML.
    fireEvent.click(screen.getByTestId("research-context-open-float"));
    const floatCall = openWindow.mock.calls.at(-1) as [
      string,
      { source?: string; html?: string; view_format?: string },
      { mode?: string },
    ];
    expect(floatCall[0]).toBe("hosted_html_document");
    expect(floatCall[1].source).toBe("research_context_pack");
    expect(floatCall[1].view_format).toBe("html");
    expect(floatCall[1].html).toMatch(/Research context pack/);
    expect(floatCall[1].html).toMatch(/data-source="research_context_pack"/);
    expect(floatCall[2].mode).toBe("floating");
    fireEvent.click(screen.getByTestId("research-context-open-full"));
    const fullCall = openWindow.mock.calls.at(-1) as [
      string,
      { source?: string },
      { mode?: string },
    ];
    expect(fullCall[1].source).toBe("research_context_pack");
    expect(fullCall[2].mode).toBe("full");
    // Residual (ff): recursive note-taker metrics strip.
    const metrics = screen.getByTestId("research-context-twin-metrics");
    expect(metrics.getAttribute("data-twin-insights")).toBe("1");
    expect(metrics.getAttribute("data-twin-questions")).toBe("0");
    expect(metrics.getAttribute("data-twin-total")).toBe("1");
    expect(metrics.textContent).toMatch(/insights=1/);
    // Residual (kl): pack research_tier chrome (parity evidence kd).
    expect(metrics.getAttribute("data-research-tier")).toBe("wrestle");
    expect(
      screen.getByTestId("research-context-pack").getAttribute("data-research-tier"),
    ).toBe("wrestle");
    expect(
      screen.getByTestId("research-context-research-tier").textContent,
    ).toMatch(/wrestle/i);
    expect(
      screen.getByTestId("research-context-research-tier").textContent,
    ).toMatch(/long-horizon/i);
  });

  it("twinNoteMetrics counts insight/question/other (ff)", () => {
    expect(twinNoteMetrics(null)).toEqual({
      total: 0,
      insights: 0,
      questions: 0,
      other: 0,
    });
    expect(
      twinNoteMetrics({
        twin_count: 4,
        twin_units: [
          { kind: "insight" },
          { kind: "insight" },
          { kind: "question" },
          { kind: "note" },
        ] as { kind: string }[],
      }),
    ).toEqual({ total: 4, insights: 2, questions: 1, other: 1 });
  });

  it("attaches a ref then reloads", async () => {
    attachSourceRefs.mockResolvedValue({
      spawn_id: "spn_1",
      source_references: [],
      view_format: "html",
    });
    fetchResearchContext.mockResolvedValue({
      asset_id: "paper",
      view_format: "html",
      twin_units: [],
      source_references: [],
      twin_count: 0,
      ref_count: 0,
      prompt_block: "# empty\n",
    });

    render(<ResearchContextPanel assetId="paper" spawnId="spn_1" />);
    fireEvent.change(screen.getByPlaceholderText(/arxiv\.org/), {
      target: { value: "https://arxiv.org/abs/1706.03762" },
    });
    fireEvent.click(screen.getByRole("button", { name: /attach ref/i }));

    await waitFor(() => {
      expect(attachSourceRefs).toHaveBeenCalledWith("spn_1", [
        "https://arxiv.org/abs/1706.03762",
      ]);
    });
    await waitFor(() => {
      expect(fetchResearchContext).toHaveBeenCalled();
    });
  });

  it("hydrates publication ref into HTML asset", async () => {
    hydratePublicationRef.mockResolvedValue({
      asset_id: "pub_arxiv_abc",
      ref: {
        ref_id: "s1",
        kind: "arxiv",
        raw: "1706.03762",
        canonical_url: "https://arxiv.org/abs/1706.03762",
      },
      title: "arxiv: 1706.03762",
      body_text: "Publication reference",
      fetched: false,
      offline_honest: true,
      view_format: "html",
      notes: ["identity-only"],
      product_panel: "engagement_hydrate",
      source: "engagement_spine.hydrate",
      html: "<p>Asset pub_arxiv_abc · view: HTML</p>",
    });
    fetchResearchContext.mockResolvedValue({
      asset_id: "paper",
      view_format: "html",
      twin_units: [],
      source_references: [],
      twin_count: 0,
      ref_count: 0,
      prompt_block: "# empty\n",
    });

    render(<ResearchContextPanel assetId="paper" spawnId="spn_1" />);
    fireEvent.change(screen.getByPlaceholderText(/arxiv\.org/), {
      target: { value: "https://arxiv.org/abs/1706.03762" },
    });
    fireEvent.click(screen.getByTestId("hydrate-publication-ref"));
    await waitFor(() => {
      expect(screen.getByTestId("hydrate-ref-result").textContent).toMatch(
        /pub_arxiv_abc/,
      );
    });
    expect(hydratePublicationRef).toHaveBeenCalledWith({
      reference: "https://arxiv.org/abs/1706.03762",
      include_html: true,
      attach_spawn_id: "spn_1",
    });
    expect(screen.getByTestId("hydrate-ref-html").innerHTML).toMatch(/HTML/);
    // Residual (hd): offline-honest identity path.
    expect(
      screen.getByTestId("hydrate-ref-result").getAttribute("data-offline-honest"),
    ).toBe("true");
    expect(
      screen.getByTestId("hydrate-ref-offline-honest").textContent,
    ).toMatch(/offline-honest identity/i);
    // Residual (rh/aet): Open Write twin_seed from hydrate-ref + path honesty.
    const write = screen.getByTestId("hydrate-ref-open-write");
    const href = write.getAttribute("href") || "";
    expect(href).toMatch(/^\/write\?twin_seed=antiek\.twin_write_seed\./);
    expect(href).not.toMatch(/html_draft=/);
    expect(write.getAttribute("data-has-twin-seed")).toBe("1");
    expect(write.getAttribute("data-asset-id")).toBe("pub_arxiv_abc");
    // Residual (acr): body_text/html body → has-body true.
    expect(write.getAttribute("data-write-seed-has-body")).toBe("true");
    // Residual (aet): offline-honest hydrate → Write path honesty.
    expect(write.getAttribute("data-spawn-id")).toBe("spn_1");
    expect(write.getAttribute("data-offline-honest")).toBe("true");
    expect(write.getAttribute("data-fetched")).toBe("false");
    expect(write.getAttribute("data-seamless-context-write")).toBe("true");
    expect(write.getAttribute("title") || "").toMatch(/offline-honest/i);
    // Residual (sk): float|full hydrated publication HTML.
    fireEvent.click(screen.getByTestId("hydrate-ref-open-float"));
    const floatCall = openWindow.mock.calls.at(-1) as [
      string,
      { source?: string; document_id?: string; view_format?: string },
      { mode?: string },
    ];
    expect(floatCall[0]).toBe("hosted_html_document");
    expect(floatCall[1].source).toBe("publication_hydrate");
    expect(floatCall[1].document_id).toBe("pub_arxiv_abc");
    expect(floatCall[1].view_format).toBe("html");
    expect(floatCall[2].mode).toBe("floating");
    fireEvent.click(screen.getByTestId("hydrate-ref-open-full"));
    const fullCall = openWindow.mock.calls.at(-1) as [
      string,
      { source?: string },
      { mode?: string },
    ];
    expect(fullCall[1].source).toBe("publication_hydrate");
    expect(fullCall[2].mode).toBe("full");
  });

  it("runs promote twins → load context flywheel", async () => {
    promoteTwinsToContext.mockResolvedValue({
      asset_id: "paper",
      promoted_count: 1,
      context_unit_count: 1,
      promoted: [],
      context_units: [
        {
          unit_id: "u1",
          twin_note_id: "t1",
          kind: "insight",
          text: "Attention is routing.",
        },
      ],
      view_format: "html",
      product_panel: "twin_promote_context",
      source: "engagement_spine.twin_promote",
      notes: [],
      html: "<p>Twin promote context</p>",
    });
    fetchResearchContext.mockResolvedValue({
      asset_id: "paper",
      view_format: "html",
      twin_units: [
        {
          unit_id: "u1",
          twin_note_id: "t1",
          kind: "insight",
          text: "Attention is routing.",
          canonical_text: "attention is routing.",
          asset_id: "paper",
          investigation_id: "inv",
        },
      ],
      source_references: [],
      twin_count: 1,
      ref_count: 0,
      prompt_block: "# Research context for asset `paper`\n",
    });

    render(<ResearchContextPanel assetId="paper" spawnId="spn_1" />);
    fireEvent.click(screen.getByTestId("context-flywheel"));
    await waitFor(() => {
      expect(promoteTwinsToContext).toHaveBeenCalled();
      expect(fetchResearchContext).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByTestId("context-flywheel-result").textContent).toMatch(
        /promoted=1/,
      );
    });
    expect(screen.getByTestId("prompt-block").textContent).toContain("paper");
  });

  it("searches twins/refs via context-search", async () => {
    searchEngagementContext.mockResolvedValue({
      query: "attention",
      asset_id: "paper",
      spawn_id: "spn_1",
      hit_count: 1,
      hits: [
        {
          kind: "twin_insight",
          id: "twin_1",
          asset_id: "paper",
          text: "Attention is routing.",
          source: "twin",
        },
      ],
      research_tier: "wrestle",
      view_format: "html",
      product_panel: "engagement_context_search",
      source: "engagement_spine.context_search",
      notes: [],
      html: "<p>Query: attention · hits=1</p>",
    });

    render(<ResearchContextPanel assetId="paper" spawnId="spn_1" />);
    fireEvent.change(screen.getByPlaceholderText(/filter twins/i), {
      target: { value: "attention" },
    });
    fireEvent.click(screen.getByTestId("context-search"));
    await waitFor(() => {
      expect(screen.getByTestId("context-search-result").textContent).toMatch(
        /hits=1/,
      );
    });
    // Residual (fi): intelligent search metrics.
    const metrics = screen.getByTestId("context-search-metrics");
    expect(metrics.getAttribute("data-hit-count")).toBe("1");
    expect(metrics.getAttribute("data-query")).toBe("attention");
    expect(metrics.textContent).toMatch(/Intelligent search/);
    // Residual (kg): spawn research_tier on intelligent search results.
    expect(metrics.getAttribute("data-research-tier")).toBe("wrestle");
    expect(screen.getByTestId("context-search-research-tier").textContent).toBe(
      "wrestle",
    );
    // Residual (rf/aes): Open Write twin_seed from search hits + path honesty.
    const write = screen.getByTestId("context-search-open-write");
    const href = write.getAttribute("href") || "";
    expect(href).toMatch(/^\/write\?twin_seed=antiek\.twin_write_seed\./);
    expect(href).not.toMatch(/html_draft=/);
    expect(write.getAttribute("data-has-twin-seed")).toBe("1");
    expect(write.getAttribute("data-hit-count")).toBe("1");
    // Residual (acr): hit text body → has-body true.
    expect(write.getAttribute("data-write-seed-has-body")).toBe("true");
    // Residual (aes): intelligent search → Write path honesty.
    expect(write.getAttribute("data-query")).toBe("attention");
    expect(write.getAttribute("data-asset-id")).toBe("paper");
    expect(write.getAttribute("data-spawn-id")).toBe("spn_1");
    expect(write.getAttribute("data-research-tier")).toBe("wrestle");
    expect(write.getAttribute("data-seamless-context-write")).toBe("true");
    // Residual (sj/tq): float|full HTML reading windows for search hits.
    const floatBtn = screen.getByTestId("context-search-open-float");
    expect(floatBtn.getAttribute("data-window-mode")).toBe("floating");
    fireEvent.click(floatBtn);
    expect(openWindow).toHaveBeenCalled();
    const floatCall = openWindow.mock.calls.at(-1) as [
      string,
      {
        source?: string;
        view_format?: string;
        html?: string;
        search_query?: string;
        search_hit_count?: number;
      },
      { mode?: string },
    ];
    expect(floatCall[0]).toBe("hosted_html_document");
    expect(floatCall[1].source).toBe("context_search");
    expect(floatCall[1].view_format).toBe("html");
    expect(floatCall[1].html).toMatch(/Query: attention/);
    // Residual (tq): query + hit_count honesty into hosted window payload.
    expect(floatCall[1].search_query).toBe("attention");
    expect(floatCall[1].search_hit_count).toBe(1);
    expect(floatCall[2].mode).toBe("floating");
    fireEvent.click(screen.getByTestId("context-search-open-full"));
    const fullCall = openWindow.mock.calls.at(-1) as [
      string,
      {
        source?: string;
        search_query?: string;
        search_hit_count?: number;
      },
      { mode?: string },
    ];
    expect(fullCall[1].source).toBe("context_search");
    expect(fullCall[1].search_query).toBe("attention");
    expect(fullCall[1].search_hit_count).toBe(1);
    expect(fullCall[2].mode).toBe("full");
    expect(searchEngagementContext).toHaveBeenCalledWith({
      query: "attention",
      asset_id: "paper",
      spawn_id: "spn_1",
      include_html: true,
    });
  });

  it("loads evidence pack HTML", async () => {
    fetchEvidencePack.mockResolvedValue({
      asset_id: "paper",
      spawn_id: "spn_1",
      insight_count: 1,
      question_count: 0,
      ref_count: 1,
      insights: ["Attention is routing."],
      questions: [],
      source_references: [
        {
          ref_id: "s1",
          kind: "arxiv",
          raw: "1706.03762",
          canonical_url: "https://arxiv.org/abs/1706.03762",
        },
      ],
      // Residual (air): multi-hop citation chain hops from substrate.
      chain_complete: true,
      citation_chain: [
        {
          hop: "insights",
          label: "Insights (claims)",
          count: 1,
          items: [
            {
              hop: "insight",
              index: 0,
              text: "Attention is routing.",
              anchor: "evidence-insight-0",
            },
          ],
        },
        {
          hop: "sources",
          label: "Source references",
          count: 1,
          items: [
            {
              hop: "source",
              index: 0,
              text: "[arxiv] https://arxiv.org/abs/1706.03762",
              kind: "arxiv",
              raw: "1706.03762",
              canonical_url: "https://arxiv.org/abs/1706.03762",
              anchor: "evidence-source-0",
            },
          ],
        },
      ],
      research_tier: "wrestle",
      view_format: "html",
      product_panel: "evidence_pack",
      source: "engagement_spine.evidence",
      notes: [],
      html: "<p>Evidence pack · Insight: Attention is routing.</p>",
    });

    render(<ResearchContextPanel assetId="paper" spawnId="spn_1" />);
    fireEvent.click(screen.getByTestId("load-evidence-pack"));
    await waitFor(() => {
      expect(screen.getByTestId("evidence-pack-result").textContent).toMatch(
        /insights=1/,
      );
    });
    expect(fetchEvidencePack).toHaveBeenCalledWith({
      asset_id: "paper",
      spawn_id: "spn_1",
      include_html: true,
    });
    expect(screen.getByTestId("evidence-pack-html").innerHTML).toMatch(
      /Attention is routing/,
    );
    expect(
      screen.getByTestId("research-context-panel").getAttribute("data-view-format"),
    ).toBe("html");
    // Residual (dm): citation trust honesty.
    expect(
      screen.getByTestId("evidence-pack-result").getAttribute("data-citation-trust"),
    ).toBe("grounded");
    const grounded = screen.getByTestId("evidence-citation-trust");
    expect(grounded.textContent).toMatch(/grounded/i);
    // Residual (va): grounded packs still deep-link hydrate maintain-prep.
    expect(grounded.getAttribute("data-citation-trust")).toBe("grounded");
    expect(grounded.getAttribute("data-ref-count")).toBe("1");
    expect(
      screen
        .getByTestId("evidence-citation-trust-hydrate-settings-link")
        .getAttribute("href"),
    ).toBe("/settings#hydrate-live-status");
    expect(
      screen
        .getByTestId("evidence-citation-trust-dual-gate-link")
        .getAttribute("href") || "",
    ).toMatch(/DUAL-GATE-L1-L4.*#l1-arxiv/);
    expect(
      screen
        .getByTestId("evidence-citation-trust-dual-gate-l2-link")
        .getAttribute("href") || "",
    ).toMatch(/DUAL-GATE-L1-L4.*#l2-substack/);
    // Residual (hu): machine-readable evidence pack metrics.
    const metrics = screen.getByTestId("evidence-pack-metrics");
    expect(metrics.getAttribute("data-insight-count")).toBe("1");
    expect(metrics.getAttribute("data-question-count")).toBe("0");
    expect(metrics.getAttribute("data-ref-count")).toBe("1");
    expect(metrics.getAttribute("data-citation-trust")).toBe("grounded");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.textContent).toMatch(/Evidence pack/);
    // Residual (aij): competitive citation chain honesty (insight→question→ref).
    const chain = screen.getByTestId("evidence-citation-chain");
    expect(chain.getAttribute("data-insight-count")).toBe("1");
    expect(chain.getAttribute("data-ref-count")).toBe("1");
    expect(chain.getAttribute("data-citation-trust")).toBe("grounded");
    expect(chain.getAttribute("data-chain-complete")).toBe("true");
    expect(chain.getAttribute("data-hop-stage-count")).toBe("2");
    expect(chain.textContent).toMatch(/Citation chain/i);
    expect(chain.textContent).toMatch(/multi-hop grounding/i);
    // Residual (air): multi-hop hop list with stable anchors (claim→source nav).
    const hops = screen.getByTestId("evidence-citation-chain-hops");
    expect(hops.getAttribute("data-chain-complete")).toBe("true");
    expect(hops.getAttribute("data-hop-stage-count")).toBe("2");
    expect(
      screen.getByTestId("evidence-citation-chain-hop-strip").textContent,
    ).toMatch(/Insights.*→.*Source/i);
    expect(
      screen.getByTestId("evidence-citation-hop-stage-insights"),
    ).toBeTruthy();
    expect(
      screen.getByTestId("evidence-citation-hop-stage-sources"),
    ).toBeTruthy();
    const insightItem = screen.getByTestId(
      "evidence-citation-hop-item-evidence-insight-0",
    );
    expect(insightItem.getAttribute("data-anchor")).toBe("evidence-insight-0");
    expect(insightItem.getAttribute("id")).toBe("evidence-insight-0");
    expect(insightItem.textContent).toMatch(/Attention is routing/);
    const sourceLink = screen.getByTestId(
      "evidence-citation-hop-link-evidence-source-0",
    );
    expect(sourceLink.getAttribute("href")).toBe("#evidence-source-0");
    expect(
      screen.getByTestId("evidence-citation-hop-item-evidence-source-0")
        .textContent,
    ).toMatch(/arxiv|1706\.03762/i);
    // Residual (ait): evidence pack → competitive DR scorecard deep-links (parity aim).
    expect(
      screen
        .getByTestId("evidence-competitive-scorecard-link")
        .getAttribute("href"),
    ).toBe("/settings#settings-competitive-dr-scorecard");
    expect(
      screen
        .getByTestId("evidence-competitive-dr-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-competitive-deep-research-quality/);
    expect(
      screen
        .getByTestId("evidence-citation-hops-scorecard-link")
        .getAttribute("href"),
    ).toBe("/settings#settings-competitive-dr-scorecard");
    expect(
      screen.getByTestId("evidence-citation-hops-scorecard-link").textContent,
    ).toMatch(/multi-hop hops/i);
    // Residual (kd): spawn research_tier chrome on evidence pack.
    expect(metrics.getAttribute("data-research-tier")).toBe("wrestle");
    expect(
      screen.getByTestId("evidence-pack-result").getAttribute("data-research-tier"),
    ).toBe("wrestle");
    expect(screen.getByTestId("evidence-research-tier").textContent).toMatch(
      /wrestle/i,
    );
    expect(screen.getByTestId("evidence-research-tier").textContent).toMatch(
      /long-horizon/i,
    );
    // Residual (rb/aet): Open Write twin_seed from evidence pack + path honesty.
    const write = screen.getByTestId("evidence-pack-open-write");
    const href = write.getAttribute("href") || "";
    expect(href).toMatch(/^\/write\?twin_seed=antiek\.twin_write_seed\./);
    expect(href).not.toMatch(/html_draft=/);
    expect(write.getAttribute("data-has-twin-seed")).toBe("1");
    expect(write.getAttribute("data-ref-count")).toBe("1");
    // Residual (acr): insights/questions/html body → has-body true.
    expect(write.getAttribute("data-write-seed-has-body")).toBe("true");
    // Residual (aet): citation-trust evidence → Write path honesty.
    expect(write.getAttribute("data-citation-trust")).toBe("grounded");
    expect(write.getAttribute("data-research-tier")).toBe("wrestle");
    expect(write.getAttribute("data-seamless-context-write")).toBe("true");
    expect(write.getAttribute("title") || "").toMatch(/grounded/i);
    // Residual (sf): float evidence pack as HTML reading window.
    const floatBtn = screen.getByTestId("evidence-pack-open-float");
    expect(floatBtn.getAttribute("data-view-format")).toBe("html");
    expect(floatBtn.getAttribute("data-window-mode")).toBe("floating");
    expect(floatBtn.getAttribute("data-ref-count")).toBe("1");
    fireEvent.click(floatBtn);
    expect(openWindow).toHaveBeenCalled();
    const [kind, payload, winOpts] = openWindow.mock.calls.at(-1) as [
      string,
      { html?: string; view_format?: string; source?: string; title?: string },
      { mode?: string },
    ];
    expect(kind).toBe("hosted_html_document");
    expect(payload.view_format).toBe("html");
    expect(payload.source).toBe("evidence_pack");
    expect(payload.html).toMatch(/Attention is routing/);
    expect(payload.title).toMatch(/Evidence pack/i);
    expect(winOpts.mode).toBe("floating");
    // Residual (sg): full working-region evidence window (float|full parity).
    const fullBtn = screen.getByTestId("evidence-pack-open-full");
    expect(fullBtn.getAttribute("data-window-mode")).toBe("full");
    fireEvent.click(fullBtn);
    const fullCall = openWindow.mock.calls.at(-1) as [
      string,
      { source?: string; view_format?: string },
      { mode?: string },
    ];
    expect(fullCall[0]).toBe("hosted_html_document");
    expect(fullCall[1].source).toBe("evidence_pack");
    expect(fullCall[1].view_format).toBe("html");
    expect(fullCall[2].mode).toBe("full");
  });

  it("flags ungrounded evidence when ref_count is zero (dm)", async () => {
    fetchEvidencePack.mockResolvedValue({
      asset_id: "paper",
      spawn_id: "spn_1",
      insight_count: 1,
      question_count: 1,
      ref_count: 0,
      insights: ["A claim without sources."],
      questions: ["Where is the citation?"],
      source_references: [],
      view_format: "html",
      product_panel: "evidence_pack",
      source: "engagement_spine.evidence",
      notes: [],
      html: "<p>Evidence pack · no refs</p>",
    });

    render(<ResearchContextPanel assetId="paper" spawnId="spn_1" />);
    fireEvent.click(screen.getByTestId("load-evidence-pack"));
    await waitFor(() => {
      expect(
        screen.getByTestId("evidence-pack-result").getAttribute("data-citation-trust"),
      ).toBe("ungrounded");
    });
    const trust = screen.getByTestId("evidence-citation-trust");
    expect(trust.textContent).toMatch(/ungrounded/i);
    // Residual (up): ungrounded pack deep-links hydrate prep (never silent live).
    expect(trust.getAttribute("data-citation-trust")).toBe("ungrounded");
    expect(trust.getAttribute("data-offline-hydrate-default")).toBe("true");
    expect(
      screen
        .getByTestId("evidence-citation-trust-hydrate-settings-link")
        .getAttribute("href"),
    ).toBe("/settings#hydrate-live-status");
    expect(
      screen
        .getByTestId("evidence-citation-trust-dual-gate-link")
        .getAttribute("href") || "",
    ).toMatch(/DUAL-GATE-L1-L4.*#l1-arxiv/);
    expect(
      screen
        .getByTestId("evidence-citation-trust-dual-gate-l2-link")
        .getAttribute("href") || "",
    ).toMatch(/DUAL-GATE-L1-L4.*#l2-substack/);
  });

  it("mounts DecisionTreeDriverBadge with prompt_block foresight (qq)", async () => {
    fetchResearchContext.mockResolvedValue({
      asset_id: "paper",
      spawn_id: "spn_1",
      twin_count: 2,
      ref_count: 0,
      twin_units: [
        { unit_id: "u1", kind: "insight", text: "I1" },
        { unit_id: "u2", kind: "question", text: "Q1" },
      ],
      source_references: [],
      view_format: "html",
      research_tier: "deep",
      prompt_block: "# Research context for asset paper\n\n## Twin notes\n- [insight] I1",
      product_panel: "research_context",
      source: "engagement_spine.context",
    });
    render(
      <ResearchContextPanel assetId="paper" spawnId="spn_1" autoLoad />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("research-context-driver-badge-mount")).toBeTruthy();
    });
    // Before load, badge still mounts with asset fallback prompt.
    expect(screen.getByTestId("decision-tree-driver-badge-stub")).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByTestId("research-context-pack")).toBeTruthy();
    });
    const badge = screen.getByTestId("decision-tree-driver-badge-stub");
    expect(badge.getAttribute("data-research-tier")).toBe("deep");
    expect(Number(badge.getAttribute("data-prompt-len") || 0)).toBeGreaterThan(20);
  });

});
