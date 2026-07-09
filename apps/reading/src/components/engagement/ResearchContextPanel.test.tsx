import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ResearchContextPanel, twinNoteMetrics } from "./ResearchContextPanel";

const fetchResearchContext = vi.fn();
const attachSourceRefs = vi.fn();
const fetchEvidencePack = vi.fn();
const hydratePublicationRef = vi.fn();
const searchEngagementContext = vi.fn();
const promoteTwinsToContext = vi.fn();

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
  });

  it("links dual-gate L1–L4 checklist for hydrate prep (mu)", () => {
    render(
      <ResearchContextPanel assetId="a1" spawnId="spn_1" />,
    );
    const dual = screen.getByTestId("research-context-dual-gate-checklist-link");
    expect(dual.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4/);
    expect(dual.textContent).toMatch(/dual-gate/i);
  });

  it("links to Settings hydrate readiness (ie)", () => {
    render(<ResearchContextPanel assetId="paper" />);
    const link = screen.getByTestId("research-context-settings-link");
    expect(link.getAttribute("href")).toBe("/settings");
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
    expect(screen.getByTestId("evidence-citation-trust").textContent).toMatch(
      /grounded/i,
    );
    // Residual (hu): machine-readable evidence pack metrics.
    const metrics = screen.getByTestId("evidence-pack-metrics");
    expect(metrics.getAttribute("data-insight-count")).toBe("1");
    expect(metrics.getAttribute("data-question-count")).toBe("0");
    expect(metrics.getAttribute("data-ref-count")).toBe("1");
    expect(metrics.getAttribute("data-citation-trust")).toBe("grounded");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.textContent).toMatch(/Evidence pack/);
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
    expect(screen.getByTestId("evidence-citation-trust").textContent).toMatch(
      /ungrounded/i,
    );
  });
});
