import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MarketplaceHost, {
  groupCatalogBySource,
  groupCatalogBySubject,
} from "./index";

const {
  fetchMarketplaceCatalog,
  hostBookIntoAccount,
  fetchAccountLibrary,
  purchaseAndHost,
  fetchHostedDocumentHtml,
  openWindow,
  seedTwinNotes,
  launchFloatingDeepResearch,
  fetchDepthTiers,
  hydratePublicationRefs,
  collectDeepResearchSpawnIds,
  listRecentDeepResearchSpawnIds,
} = vi.hoisted(() => ({
  fetchMarketplaceCatalog: vi.fn(),
  hostBookIntoAccount: vi.fn(),
  fetchAccountLibrary: vi.fn(),
  purchaseAndHost: vi.fn(),
  fetchHostedDocumentHtml: vi.fn(),
  openWindow: vi.fn(() => "win:hosted:hdoc_abc"),
  seedTwinNotes: vi.fn(),
  launchFloatingDeepResearch: vi.fn(),
  hydratePublicationRefs: vi.fn(),
  fetchDepthTiers: vi.fn(async () => ({
    active_depth_tier: null as string | null,
    active_preset: null,
    presets: [],
    projection_hints: null,
    view_format: "html" as const,
    settings_panel: "depth_tier_presets",
    source: "test",
    notes: [] as string[],
  })),
  collectDeepResearchSpawnIds: vi.fn(() => [] as string[]),
  listRecentDeepResearchSpawnIds: vi.fn(() => [] as string[]),
}));

vi.mock("../../api/marketplaceHost", () => ({
  fetchMarketplaceCatalog,
  hostBookIntoAccount,
  fetchAccountLibrary,
  purchaseAndHost,
  fetchHostedDocumentHtml,
}));

vi.mock("../../api/engagement", () => ({
  seedTwinNotes: (...args: unknown[]) => seedTwinNotes(...args),
}));

vi.mock("../../components/windows/openWindow", () => ({
  openWindow,
}));

vi.mock("../Reading/launchFloatingDeepResearch", () => ({
  launchFloatingDeepResearch,
}));

vi.mock("../ResearchWorkstation/publicationRefs", () => ({
  parsePublicationRefs: (raw: string) =>
    String(raw || "")
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean),
  hydratePublicationRefs: (...args: unknown[]) =>
    hydratePublicationRefs(...args),
}));

vi.mock("../../api/settings", () => ({
  fetchDepthTiers: (...args: unknown[]) => fetchDepthTiers(...args),
}));

vi.mock("../../components/engagement/DecisionTreeDriverBadge", () => ({
  DecisionTreeDriverBadge: (props: {
    researchTier?: string | null;
  }) => (
    <div
      data-testid="decision-tree-driver-badge-stub"
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
    >
      driver badge{props.researchTier ? `:tier=${props.researchTier}` : ""}
    </div>
  ),
}));

// Residual (alx/aly): TwinNotes + ResearchContext on host land — stub APIs.
vi.mock("../../components/engagement/TwinNotesPanel", () => ({
  TwinNotesPanel: (props: {
    assetId: string;
    researchTier?: string | null;
    domainSubjects?: readonly string[] | null;
    autoLoad?: boolean;
    autoSeedIfEmpty?: boolean;
    autoPromoteAfterLoad?: boolean;
    onPromoted?: (result: unknown) => void;
  }) => (
    <div
      data-testid="twin-notes-panel-stub"
      data-asset-id={props.assetId}
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
      data-domain-subjects={(props.domainSubjects || []).join(",") || ""}
      data-auto-load={String(Boolean(props.autoLoad))}
      data-auto-seed={String(Boolean(props.autoSeedIfEmpty))}
      data-auto-promote={String(Boolean(props.autoPromoteAfterLoad))}
    >
      twins={props.assetId}
      {props.onPromoted ? (
        <button
          type="button"
          data-testid="twin-notes-promote-notify"
          onClick={() =>
            props.onPromoted?.({
              unit_count: 1,
              view_format: "html",
            })
          }
        >
          notify promote
        </button>
      ) : null}
    </div>
  ),
}));

vi.mock("../../components/engagement/ResearchContextPanel", () => ({
  ResearchContextPanel: (props: {
    assetId: string;
    autoLoad?: boolean;
    domainSubjects?: readonly string[] | null;
    researchTier?: string | null;
  }) => (
    <div
      data-testid="research-context-panel-stub"
      data-asset-id={props.assetId}
      data-domain-subjects={(props.domainSubjects || []).join(",") || ""}
      data-auto-load={String(Boolean(props.autoLoad))}
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
    >
      context={props.assetId}
    </div>
  ),
  domainSearchCoverage: (
    subjects?: readonly string[] | null,
  ): {
    subjects: string[];
    has_default: boolean;
    default_query: string;
    covered: string[];
    uncovered: string[];
  } => {
    // Prefer pure util if present — marketplace imports domainSearchCoverage
    // from workspace/domainSearchDefaults, not this module. Stub unused.
    const list = (subjects || [])
      .map((s) => String(s || "").trim().toLowerCase())
      .filter(Boolean);
    return {
      subjects: list,
      has_default: list.length > 0,
      default_query: list.join(" "),
      covered: list,
      uncovered: [],
    };
  },
  domainAwareSearchDefault: () => "",
}));

// Residual (ani): collective multi-select on marketplace host land.
vi.mock("../../workspace/collectDeepResearchSpawnIds", () => ({
  collectDeepResearchSpawnIds: (...args: unknown[]) =>
    collectDeepResearchSpawnIds(...args),
}));

vi.mock("../../workspace/recentDeepResearchSpawns", () => ({
  listRecentDeepResearchSpawnIds: (...args: unknown[]) =>
    listRecentDeepResearchSpawnIds(...args),
}));

vi.mock("../../workspace/windowsStore", () => ({
  useWindows: (sel: (s: { windows: Record<string, unknown> }) => unknown) =>
    sel({ windows: {} }),
}));

vi.mock("../../components/engagement/CollectiveResearchPanel", () => ({
  CollectiveResearchPanel: (props: {
    availableSpawnIds: string[];
    parentAssetId?: string | null;
    recentSpawnIds?: readonly string[] | null;
    openSpawnIds?: readonly string[] | null;
    onRecentSpawnsCleared?: () => void;
    onDocMerged?: () => void;
  }) => (
    <div
      data-testid="collective-research-panel-stub"
      data-recent={
        props.recentSpawnIds != null ? props.recentSpawnIds.join(",") : ""
      }
      data-has-clear={props.onRecentSpawnsCleared ? "1" : "0"}
      data-has-merged={props.onDocMerged ? "1" : "0"}
    >
      {props.parentAssetId}:{props.availableSpawnIds.join(",")}
      {props.onDocMerged ? (
        <button
          type="button"
          data-testid="marketplace-host-collective-merge-notify"
          onClick={() => props.onDocMerged?.()}
        >
          notify merge
        </button>
      ) : null}
    </div>
  ),
}));

vi.mock("../../components/engagement/ResearchLaunchBudgetPanel", async () => {
  const React = await import("react");
  return {
    ResearchLaunchBudgetPanel: (props: {
      promptText?: string;
      researchTier?: string;
      onProjectionChange?: (p: {
        wouldExceedBudget: boolean | null;
        pricingKnown: boolean;
        estimatedUsdHigh: number | null;
        remainingUsd: number | null;
        modelId: string | null;
      }) => void;
    }) => {
      // Residual (iy): notify parent of projection for soft-gate tests.
      React.useEffect(() => {
        props.onProjectionChange?.({
          wouldExceedBudget: false,
          pricingKnown: true,
          estimatedUsdHigh: 0.1,
          remainingUsd: 4,
          modelId: "glm-5.2",
        });
      }, [props]);
      return React.createElement(
        "div",
        {
          "data-testid": "research-launch-budget-panel-stub",
          "data-research-tier": props.researchTier || "deep",
        },
        `budget stub · ${(props.promptText || "").slice(0, 24)}`,
      );
    },
  };
});

describe("MarketplaceHost mode", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    fetchMarketplaceCatalog.mockReset();
    hostBookIntoAccount.mockReset();
    fetchAccountLibrary.mockReset();
    purchaseAndHost.mockReset();
    fetchHostedDocumentHtml.mockReset();
    openWindow.mockClear();
    collectDeepResearchSpawnIds.mockReset().mockReturnValue([]);
    listRecentDeepResearchSpawnIds.mockReset().mockReturnValue([]);
    fetchDepthTiers.mockReset().mockResolvedValue({
      active_depth_tier: null,
      active_preset: null,
      presets: [],
      projection_hints: null,
      view_format: "html",
      settings_panel: "depth_tier_presets",
      source: "test",
      notes: [],
    });
    launchFloatingDeepResearch.mockReset().mockResolvedValue({
      session_id: "fsess_mkt",
      spawn_id: "spn_mkt",
      investigation_id: "inv_mkt",
      parent_asset_id: "hdoc_abc",
      window_id: "win:dr:mkt",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
      model_id: null,
    });
    hydratePublicationRefs.mockReset().mockResolvedValue({
      ok: [{ asset_id: "pub_arxiv_1" }],
      failed: [],
    });
    seedTwinNotes.mockReset().mockResolvedValue({
      asset_id: "hdoc_abc",
      seeded: true,
      view_format: "html",
      notes: [],
      insight_count: 1,
      question_count: 1,
      live_seed: false,
      seed_source: "engagement_spine.twin.seed_twins_for_asset",
    });
    // Residual (dq): library loads on mount — default empty honest library.
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "operator",
      documents: [],
      count: 0,
      view_format: "html",
      html: "",
    });
  });

  it("loads catalog and hosts public domain book", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
          subjects: ["literature"],
        },
      ],
      count: 1,
      view_format: "html",
      // Residual (iq/ir): server honesty fields.
      by_source: { standard_ebooks: 1 },
      public_domain_count: 1,
      purchased_count: 0,
      free_count: 1,
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_abc",
      owner_id: "operator",
      book_id: "pd-pride",
      content_hash: "x",
      title: "Pride and Prejudice",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_abc"],
      view_format: "html",
      html: "<p>It is a truth universally acknowledged</p>",
      // Residual (ma/mb): Antiek-bench book_qa usage from host path.
      usage_event: {
        task_class: "book_qa",
        outcome: "worked",
        source: "marketplace_host",
        prompt_hint: "host pd-pride · Pride and Prejudice",
      },
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "operator",
      documents: [
        {
          document_id: "hdoc_abc",
          title: "Pride",
          license_class: "public_domain",
          view_format: "html",
          is_free: true,
        },
      ],
      count: 1,
      free_count: 1,
      view_format: "html",
      html: "<p>Library</p>",
    });

    render(<MarketplaceHost ownerId="operator" />);
    // Residual (dz): decision-tree driver badge on marketplace (reading ≡ research).
    expect(screen.getByTestId("marketplace-driver-badge-mount")).toBeTruthy();
    expect(
      screen
        .getByTestId("marketplace-driver-badge-mount")
        .getAttribute("data-view-format"),
    ).toBe("html");
    expect(screen.getByTestId("decision-tree-driver-badge-stub")).toBeTruthy();
    // Residual (kx): marketplace wires hostDrTier into driver badge (ku).
    expect(
      screen
        .getByTestId("decision-tree-driver-badge-stub")
        .getAttribute("data-research-tier"),
    ).toBe("deep");
    // Residual (id): Settings deep-link for driver + twin seed readiness.
    const settings = screen.getByTestId("marketplace-settings-link");
    expect(settings.getAttribute("href")).toBe("/settings#decision-tree-panel");
    expect(settings.textContent).toMatch(/driver & twin seed/i);
    // Residual (mm): dual-gate checklist (prep only).
    const dual = screen.getByTestId("marketplace-dual-gate-checklist-link");
    // Residual (ye): marketplace dual-gate → L5 payment section.
    expect(dual.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4.*#l5-payment/);
    expect(dual.textContent).toMatch(/L5 payment checklist/i);
    // Residual (ajl): free STEM marketplace → competitive DR honesty map.
    expect(
      screen
        .getByTestId("marketplace-competitive-scorecard-link")
        .getAttribute("href"),
    ).toBe("/settings#settings-competitive-dr-scorecard");
    expect(
      screen
        .getByTestId("marketplace-competitive-dr-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-competitive-deep-research-quality/);
    await waitFor(() => {
      expect(screen.getByText("Pride and Prejudice")).toBeTruthy();
    });
    // Residual (aph): free Host into account stamps HTML-first seamless port.
    const freeHost = screen.getByTestId("free-host-pd-pride");
    expect(freeHost.getAttribute("data-html-first")).toBe("true");
    expect(freeHost.getAttribute("data-view-format")).toBe("html");
    expect(freeHost.getAttribute("data-free-host")).toBe("true");
    expect(freeHost.getAttribute("data-is-free")).toBe("true");
    expect(freeHost.getAttribute("data-seamless-port")).toBe("true");
    expect(freeHost.getAttribute("data-live-payment")).toBe("false");
    expect(freeHost.getAttribute("title") || "").toMatch(/never PDF/i);
    // Residual (il/io): HTML-first catalog honesty + by_source.
    const catMetrics = screen.getByTestId("marketplace-catalog-metrics");
    expect(catMetrics.getAttribute("data-view-format")).toBe("html");
    expect(catMetrics.getAttribute("data-payment-rails")).toBe(
      "manual_receipt_only",
    );
    // Residual (uy): L5 payment rails honesty (manual receipt · no live checkout).
    const l5 = screen.getByTestId("marketplace-l5-payment-honesty");
    expect(l5.getAttribute("data-payment-rails")).toBe("manual_receipt_only");
    expect(l5.getAttribute("data-l5-payment-rails")).toBe("deferred");
    expect(l5.getAttribute("data-live-payment")).toBe("false");
    expect(l5.textContent).toMatch(/manual_receipt_only|live checkout deferred/i);
    // Residual (aks): Sprint 1 payment_adapter boundary shipped offline (akr).
    expect(l5.getAttribute("data-payment-adapter-sprint")).toBe("1");
    expect(l5.getAttribute("data-payment-adapter-boundary")).toBe(
      "shipped_offline",
    );
    expect(l5.getAttribute("data-payment-adapter-env")).toBe(
      "ANTIEK_MARKETPLACE_LIVE_PAYMENT",
    );
    const adapterStatus = screen.getByTestId(
      "marketplace-l5-payment-adapter-status",
    );
    expect(adapterStatus.getAttribute("data-payment-adapter-boundary")).toBe(
      "shipped_offline",
    );
    expect(adapterStatus.getAttribute("data-live-payment")).toBe("false");
    expect(adapterStatus.textContent).toMatch(/Sprint 1 shipped offline/i);
    expect(adapterStatus.textContent).toMatch(/DeferredPaymentAdapter/i);
    expect(adapterStatus.textContent).toMatch(/Sprint 2/i);
    // Residual (wj): L5 checklist section deep-link.
    expect(
      screen.getByTestId("marketplace-l5-dual-gate-link").getAttribute("href") ||
        "",
    ).toMatch(/DUAL-GATE-L1-L4.*#l5-payment/);
    expect(
      screen.getByTestId("marketplace-l5-dual-gate-link").textContent,
    ).toMatch(/L5 payment checklist/i);
    // Residual (ir): server honesty preferred.
    expect(catMetrics.getAttribute("data-honesty-source")).toBe("server");
    expect(catMetrics.getAttribute("data-public-domain-count")).toBe("1");
    expect(catMetrics.getAttribute("data-free-count")).toBe("1");
    expect(Number(catMetrics.getAttribute("data-entry-count"))).toBeGreaterThan(
      0,
    );
    expect(catMetrics.textContent).toMatch(/HTML/);
    expect(screen.getByTestId("marketplace-catalog-by-source").textContent).toMatch(
      /standard_ebooks/,
    );
    expect(
      screen.getByTestId("catalog-entry-pd-pride").getAttribute("data-source"),
    ).toBe("standard_ebooks");
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(screen.getByTestId("host-result").textContent).toContain("hdoc_abc");
    });
    // Residual (in/ip): host land metrics + catalog source + research substrate.
    const hostMetrics = screen.getByTestId("marketplace-host-metrics");
    expect(hostMetrics.getAttribute("data-document-id")).toBe("hdoc_abc");
    expect(hostMetrics.getAttribute("data-view-format")).toBe("html");
    expect(hostMetrics.getAttribute("data-already-hosted")).toBe("false");
    expect(hostMetrics.getAttribute("data-catalog-source")).toBe(
      "standard_ebooks",
    );
    // Residual (mh): research-domain subjects on host land.
    expect(hostMetrics.getAttribute("data-subjects")).toBe("literature");
    expect(hostMetrics.textContent).toMatch(/subjects=literature/);
    expect(hostMetrics.textContent).toMatch(/Host land/);
    // Residual (alm): domain-search coverage honesty after host (alj).
    expect(hostMetrics.getAttribute("data-domain-search-has-default")).toBe(
      "true",
    );
    expect(hostMetrics.getAttribute("data-domain-search-covered")).toMatch(
      /literature/,
    );
    expect(
      Number(hostMetrics.getAttribute("data-domain-search-covered-count")),
    ).toBeGreaterThanOrEqual(1);
    const domainCov = screen.getByTestId(
      "marketplace-host-domain-search-coverage",
    );
    expect(domainCov.getAttribute("data-has-default")).toBe("true");
    expect(domainCov.textContent).toMatch(/default active/i);
    expect(domainCov.textContent).toMatch(/literature/i);
    // Residual (alx): TwinNotes recursive note-taker on host land with subjects.
    const twinsMount = screen.getByTestId("marketplace-host-twins-mount");
    expect(twinsMount.getAttribute("data-document-id")).toBe("hdoc_abc");
    expect(twinsMount.getAttribute("data-domain-subjects")).toMatch(
      /literature/,
    );
    expect(twinsMount.getAttribute("data-domain-search-has-default")).toBe(
      "true",
    );
    expect(twinsMount.getAttribute("data-seamless-marketplace-twins")).toBe(
      "true",
    );
    const twinsStub = screen.getByTestId("twin-notes-panel-stub");
    expect(twinsStub.getAttribute("data-asset-id")).toBe("hdoc_abc");
    expect(twinsStub.getAttribute("data-domain-subjects")).toMatch(
      /literature/,
    );
    expect(twinsStub.getAttribute("data-auto-load")).toBe("true");
    expect(twinsStub.getAttribute("data-auto-seed")).toBe("true");
    // Residual (aly): ResearchContext intelligent search on host land.
    const ctxMount = screen.getByTestId("marketplace-host-context-mount");
    expect(ctxMount.getAttribute("data-document-id")).toBe("hdoc_abc");
    expect(ctxMount.getAttribute("data-domain-subjects")).toMatch(/literature/);
    expect(ctxMount.getAttribute("data-domain-search-has-default")).toBe(
      "true",
    );
    expect(ctxMount.getAttribute("data-seamless-marketplace-context")).toBe(
      "true",
    );
    const ctxStub = screen.getByTestId("research-context-panel-stub");
    expect(ctxStub.getAttribute("data-asset-id")).toBe("hdoc_abc");
    expect(ctxStub.getAttribute("data-domain-subjects")).toMatch(/literature/);
    expect(ctxStub.getAttribute("data-auto-load")).toBe("true");
    // Residual (amj): host depth prefill into ResearchContext.
    expect(ctxStub.getAttribute("data-research-tier")).toMatch(/deep|wrestle|fast/);
    // Residual (alz/ama): remount after seed then promote (parity HostedHtml).
    expect(twinsStub.getAttribute("data-auto-promote")).toBe("true");
    // Residual (ama): offline twin seed completion bumps refresh key.
    await waitFor(() => {
      expect(seedTwinNotes).toHaveBeenCalled();
    });
    await waitFor(() => {
      const key = Number(
        screen
          .getByTestId("marketplace-host-twins-refresh")
          .getAttribute("data-refresh-key") || "0",
      );
      expect(key).toBeGreaterThanOrEqual(1);
    });
    const keyAfterSeed = Number(
      screen
        .getByTestId("marketplace-host-twins-refresh")
        .getAttribute("data-refresh-key") || "0",
    );
    fireEvent.click(screen.getByTestId("twin-notes-promote-notify"));
    await waitFor(() => {
      expect(
        Number(
          screen
            .getByTestId("marketplace-host-twins-refresh")
            .getAttribute("data-refresh-key") || "0",
        ),
      ).toBe(keyAfterSeed + 1);
    });
    expect(
      Number(
        screen
          .getByTestId("marketplace-host-context-mount")
          .getAttribute("data-refresh-key") || "0",
      ),
    ).toBe(keyAfterSeed + 1);
    // Residual (tc): free/PD host path honesty.
    expect(hostMetrics.getAttribute("data-license-class")).toBe("public_domain");
    expect(hostMetrics.getAttribute("data-is-public-domain")).toBe("true");
    expect(hostMetrics.getAttribute("data-is-free-host")).toBe("true");
    expect(hostMetrics.getAttribute("data-payment-rails")).toBe(
      "manual_receipt_only",
    );
    // Residual (adh): L5 deferred + HTML-first host land honesty.
    expect(hostMetrics.getAttribute("data-l5-payment-rails")).toBe("deferred");
    expect(hostMetrics.getAttribute("data-html-first")).toBe("true");
    // Residual (aeb): free host seamless port parity with purchase path (aea).
    expect(hostMetrics.getAttribute("data-seamless-port")).toBe("true");
    expect(hostMetrics.getAttribute("data-library-landed")).toBe("true");
    const seamless = screen.getByTestId("marketplace-seamless-port");
    expect(seamless.getAttribute("data-seamless-port")).toBe("true");
    expect(seamless.getAttribute("data-library-landed")).toBe("true");
    expect(seamless.textContent).toMatch(/Seamless port/i);
    expect(seamless.textContent).toMatch(/account library=landed/);
    const freeHonesty = screen.getByTestId("marketplace-host-free-pd-honesty");
    expect(freeHonesty.getAttribute("data-is-public-domain")).toBe("true");
    expect(freeHonesty.getAttribute("data-is-free-host")).toBe("true");
    expect(freeHonesty.getAttribute("data-l5-payment-rails")).toBe("deferred");
    expect(freeHonesty.getAttribute("data-html-first")).toBe("true");
    expect(freeHonesty.textContent).toMatch(/free_host=true/);
    expect(freeHonesty.textContent).toMatch(/manual_receipt_only/);
    // Residual (akb): host land L5 FUTURE + dual-gate + scorecard navigation.
    // Residual (aks): host land Sprint 1 payment_adapter stamps (akr).
    const l5nav = screen.getByTestId("marketplace-host-l5-nav");
    expect(l5nav.getAttribute("data-l5-payment-rails")).toBe("deferred");
    expect(l5nav.getAttribute("data-payment-rails")).toBe("manual_receipt_only");
    expect(l5nav.getAttribute("data-html-first")).toBe("true");
    expect(l5nav.getAttribute("data-payment-adapter-sprint")).toBe("1");
    expect(l5nav.getAttribute("data-payment-adapter-boundary")).toBe(
      "shipped_offline",
    );
    expect(l5nav.getAttribute("data-payment-adapter-env")).toBe(
      "ANTIEK_MARKETPLACE_LIVE_PAYMENT",
    );
    expect(l5nav.getAttribute("data-live-payment")).toBe("false");
    expect(
      screen
        .getByTestId("marketplace-host-l5-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-l5-digital-book-seamless-port/);
    expect(
      screen
        .getByTestId("marketplace-host-l5-future-agent-link")
        .getAttribute("title") || "",
    ).toMatch(/Sprint 1 payment adapter shipped offline/i);
    expect(
      screen
        .getByTestId("marketplace-host-l5-dual-gate-link")
        .getAttribute("href") || "",
    ).toMatch(/DUAL-GATE-L1-L4.*#l5-payment/);
    expect(
      screen
        .getByTestId("marketplace-host-competitive-scorecard-link")
        .getAttribute("href"),
    ).toBe("/settings#settings-competitive-dr-scorecard");
    expect(freeHonesty.textContent).toMatch(/L5 rails deferred/i);
    expect(
      screen.getByTestId("marketplace-host-research-substrate").textContent,
    ).toMatch(/recursive note-taker/i);
    // Residual (mb): Antiek-bench usage event chrome after host.
    expect(hostMetrics.getAttribute("data-usage-task-class")).toBe("book_qa");
    expect(hostMetrics.getAttribute("data-usage-source")).toBe(
      "marketplace_host",
    );
    const usageChrome = screen.getByTestId("marketplace-host-usage-event");
    expect(usageChrome.getAttribute("data-task-class")).toBe("book_qa");
    expect(usageChrome.getAttribute("data-source")).toBe("marketplace_host");
    expect(usageChrome.getAttribute("data-propose-not-promote")).toBe("true");
    expect(usageChrome.textContent).toMatch(/book_qa/);
    expect(usageChrome.textContent).toMatch(/propose/);
    expect(hostBookIntoAccount).toHaveBeenCalledWith({
      owner_id: "operator",
      book_id: "pd-pride",
    });
    expect(screen.getByTestId("hosted-html").innerHTML).toContain("truth");
    // Residual (iy): budget panel mounted before DR launch.
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-host-dr-budget-mount")).toBeTruthy();
    });
    expect(
      screen.getByTestId("research-launch-budget-panel-stub"),
    ).toBeTruthy();
    // Residual (jc): default depth prefill none when Settings unset.
    await waitFor(() => {
      expect(fetchDepthTiers).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(
        screen
          .getByTestId("marketplace-host-dr-budget-mount")
          .getAttribute("data-depth-prefill"),
      ).toBe("none");
    });
    // Residual (mp): budget mount surfaces catalog domains for DR.
    expect(
      screen
        .getByTestId("marketplace-host-dr-budget-mount")
        .getAttribute("data-domains"),
    ).toBe("literature");
    // Residual (iu/mp): one-click floating deep research with domain context.
    fireEvent.click(screen.getByTestId("marketplace-host-deep-research"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "hdoc_abc",
          view_mode: "floating",
          selection_text: expect.stringMatching(/Research domains: literature/i),
          goal_hint: expect.stringMatching(/domains=literature/i),
        }),
      );
    });
    await waitFor(() => {
      const st = screen.getByTestId("marketplace-host-dr-status");
      expect(st.textContent).toMatch(/Deep research launched \(floating\)/);
      // Residual (ja): research tier on DR status.
      expect(st.getAttribute("data-research-tier")).toBe("deep");
      expect(st.textContent).toMatch(/tier=deep/);
      // Residual (mp): domains in DR status chrome.
      expect(st.textContent).toMatch(/domains=literature/);
    });
    // Residual (iv): full working-region deep research.
    fireEvent.click(screen.getByTestId("marketplace-host-deep-research-full"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "hdoc_abc",
          view_mode: "full",
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-host-dr-status").textContent).toMatch(
        /Deep research launched \(full\)/,
      );
    });
    // Residual (gi/aeo): host-result → Write HTML draft + seamless-port path.
    const writeLink = screen.getByTestId("marketplace-open-write");
    expect(writeLink.getAttribute("href") || "").toMatch(/html_draft=hdoc_abc/);
    expect(writeLink.getAttribute("href") || "").toMatch(/twin_seed=antiek\.twin_write_seed\./);
    expect(writeLink.getAttribute("data-has-twin-seed")).toBe("1");
    expect(writeLink.getAttribute("data-view-format")).toBe("html");
    expect(writeLink.getAttribute("data-document-id")).toBe("hdoc_abc");
    expect(writeLink.getAttribute("data-write-seed-has-body")).toBe("true");
    expect(writeLink.getAttribute("data-seamless-host-write")).toBe("true");
    expect(writeLink.getAttribute("data-seamless-port")).toBe("true");
    expect(writeLink.getAttribute("data-library-landed")).toBe("true");
    // Residual (gj/mo/aho): offline twin seed after host with domain subjects + free port honesty.
    await waitFor(() => {
      expect(seedTwinNotes).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "hdoc_abc",
          force_offline: true,
          body_text: expect.stringMatching(/Research domains: literature/i),
        }),
      );
      const body = String(
        (seedTwinNotes.mock.calls.at(-1)?.[0] as { body_text?: string })
          ?.body_text || "",
      );
      expect(body).toMatch(/free public-domain HTML host/i);
    });
    await waitFor(() => {
      const status = screen.getByTestId("marketplace-twin-seed-status");
      // Residual (hl): offline-honest copy + machine-readable attrs.
      expect(status.textContent).toMatch(/offline-honest identity stubs/);
      expect(status.getAttribute("data-offline-honest")).toBe("true");
      expect(status.getAttribute("data-live-seed")).toBe("false");
      expect(status.getAttribute("data-force-offline")).toBe("true");
      expect(status.getAttribute("data-seeded")).toBe("true");
      expect(status.getAttribute("data-asset-id")).toBe("hdoc_abc");
      expect(status.getAttribute("data-seed-source")).toBe(
        "engagement_spine.twin.seed_twins_for_asset",
      );
    });
    // Residual (dk): auto-open hosted window after host (default on).
    await waitFor(() => {
      expect(openWindow).toHaveBeenCalledWith(
        "hosted_html_document",
        expect.objectContaining({
          document_id: "hdoc_abc",
          view_format: "html",
        }),
        expect.objectContaining({ id: "win:hosted:hdoc_abc" }),
      );
    });
    // Residual (dl): structured library list after host.
    await waitFor(() => {
      expect(screen.getByTestId("library-doc-list")).toBeTruthy();
      expect(screen.getByTestId("library-doc-hdoc_abc")).toBeTruthy();
    });
    // Residual (gi/acf): library row → Write dual handoff with in-session body.
    const libWrite = screen.getByTestId("library-open-write-hdoc_abc");
    expect(libWrite.getAttribute("href") || "").toMatch(/html_draft=hdoc_abc/);
    expect(libWrite.getAttribute("href") || "").toMatch(/twin_seed=antiek\.twin_write_seed\./);
    expect(libWrite.getAttribute("data-has-twin-seed")).toBe("1");
    expect(libWrite.getAttribute("data-view-format")).toBe("html");
    // Residual (acf): after host, library Open Write seeds twin with body (not title-only).
    expect(libWrite.getAttribute("data-write-seed-has-body")).toBe("true");
    expect(libWrite.getAttribute("data-is-free")).toBe("true");
    expect(libWrite.getAttribute("title") || "").toMatch(/in-session host body/i);
    // Residual (aeo): library Open Write seamless-port when host body present.
    expect(libWrite.getAttribute("data-library-landed")).toBe("true");
    expect(libWrite.getAttribute("data-seamless-port")).toBe("true");
    expect(libWrite.getAttribute("data-seamless-host-write")).toBe("true");
    // Residual (iw): library row deep research float|full.
    fireEvent.click(screen.getByTestId("library-deep-research-hdoc_abc"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "hdoc_abc",
          view_mode: "floating",
        }),
      );
    });
    fireEvent.click(screen.getByTestId("library-deep-research-full-hdoc_abc"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "hdoc_abc",
          view_mode: "full",
        }),
      );
    });
    expect(screen.getByTestId("library-filter-count").textContent).toMatch(
      /Showing 1 of 1/,
    );
    // Residual (im): HTML-first library metrics.
    const libMetrics = screen.getByTestId("marketplace-library-metrics");
    expect(libMetrics.getAttribute("data-doc-count")).toBe("1");
    expect(libMetrics.getAttribute("data-view-format")).toBe("html");
    expect(libMetrics.textContent).toMatch(/Library/);
    // Residual (tb): free inventory honesty (unfiltered).
    expect(libMetrics.getAttribute("data-free-count")).toBe("1");
    expect(libMetrics.getAttribute("data-filtered-free-count")).toBe("1");
    expect(libMetrics.getAttribute("data-filters-active")).toBe("false");
    // Residual (ace): free_count provenance from API free_count (acb/acc).
    expect(libMetrics.getAttribute("data-free-count-source")).toBe("api");
    expect(libMetrics.getAttribute("data-library-api-free-count")).toBe("1");
    expect(libMetrics.textContent).toMatch(/free_count_source=api/);
    // Residual (ace): library row free inventory machine attrs (parity catalog).
    const libRow = screen.getByTestId("library-doc-hdoc_abc");
    expect(libRow.getAttribute("data-is-free")).toBe("true");
    expect(libRow.getAttribute("data-license-class")).toBe("public_domain");
    expect(libRow.textContent).toMatch(/free/);
    fireEvent.change(screen.getByTestId("library-filter"), {
      target: { value: "hdoc_abc" },
    });
    expect(screen.getByTestId("library-doc-hdoc_abc")).toBeTruthy();
    // Residual (tb): filtered free honesty strip when library filter active.
    expect(
      screen
        .getByTestId("marketplace-library-metrics")
        .getAttribute("data-filters-active"),
    ).toBe("true");
    expect(
      screen
        .getByTestId("marketplace-library-metrics")
        .getAttribute("data-filtered-free-count"),
    ).toBe("1");
    const libHonesty = screen.getByTestId(
      "marketplace-library-filtered-free-honesty",
    );
    expect(libHonesty.getAttribute("data-filtered-free-count")).toBe("1");
    expect(libHonesty.getAttribute("data-library-free-count")).toBe("1");
    expect(libHonesty.textContent).toMatch(/visible_free_pd=1/);
    fireEvent.change(screen.getByTestId("library-filter"), {
      target: { value: "nope" },
    });
    expect(screen.getByTestId("library-filter-empty")).toBeTruthy();
    expect(
      screen
        .getByTestId("marketplace-library-metrics")
        .getAttribute("data-filtered-free-count"),
    ).toBe("0");
  });

  it("loads account library on mount and rehydrates open (dq/do)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-x",
          title: "New",
          author: "A",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
        },
      ],
      count: 1,
      view_format: "html",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "operator",
      documents: [
        {
          document_id: "hdoc_old",
          title: "Old Hosted Book",
          license_class: "public_domain",
          view_format: "html",
        },
      ],
      count: 1,
      view_format: "html",
      html: "<p>Library</p>",
    });
    fetchHostedDocumentHtml.mockResolvedValue({
      document_id: "hdoc_old",
      view_format: "html",
      title: "Old Hosted Book",
      license_class: "public_domain",
      html: "<article><h1>Old Hosted Book</h1><p>Rehydrated body.</p></article>",
    });

    render(<MarketplaceHost ownerId="operator" />);
    // Residual (dq): library visible without host first.
    await waitFor(() => {
      expect(fetchAccountLibrary).toHaveBeenCalledWith("operator");
    });
    await waitFor(() => {
      expect(screen.getByTestId("library-doc-hdoc_old")).toBeTruthy();
    });
    // Residual (aci): before rehydrate, library Open Write is title-only twin seed.
    const writeBefore = screen.getByTestId("library-open-write-hdoc_old");
    expect(writeBefore.getAttribute("data-write-seed-has-body")).toBe("false");
    openWindow.mockClear();
    fireEvent.click(screen.getByTestId("library-open-hdoc_old"));
    await waitFor(() => {
      expect(fetchHostedDocumentHtml).toHaveBeenCalledWith("hdoc_old");
    });
    await waitFor(() => {
      expect(openWindow).toHaveBeenCalledWith(
        "hosted_html_document",
        expect.objectContaining({
          document_id: "hdoc_old",
          view_format: "html",
          source: "marketplace_library_rehydrate",
        }),
        expect.objectContaining({ id: "win:hosted:hdoc_old" }),
      );
    });
    const payload = openWindow.mock.calls.at(-1)?.[1] as { html?: string };
    expect(payload.html).toMatch(/Rehydrated body/);
    // Residual (acg): after rehydrate, library Open Write twin_seed has body.
    await waitFor(() => {
      const libWrite = screen.getByTestId("library-open-write-hdoc_old");
      expect(libWrite.getAttribute("data-write-seed-has-body")).toBe("true");
      expect(libWrite.getAttribute("title") || "").toMatch(
        /in-session host body/i,
      );
    });
    // Residual (ach): offline twin seed after library rehydrate (recursive note-taker).
    await waitFor(() => {
      expect(seedTwinNotes).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "hdoc_old",
          force_offline: true,
        }),
      );
    });
    await waitFor(() => {
      const status = screen.getByTestId("marketplace-twin-seed-status");
      expect(status.getAttribute("data-offline-honest")).toBe("true");
      expect(status.getAttribute("data-asset-id")).toBe("hdoc_old");
    });
  });

  it("filters catalog by title/author substring (dj)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
        },
        {
          book_id: "pd-moby",
          title: "Moby-Dick",
          author: "Herman Melville",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
        },
      ],
      count: 2,
      view_format: "html",
    });

    render(<MarketplaceHost ownerId="operator" />);
    await waitFor(() => {
      expect(screen.getByText("Pride and Prejudice")).toBeTruthy();
      expect(screen.getByText("Moby-Dick")).toBeTruthy();
    });
    expect(screen.getByTestId("catalog-filter-count").textContent).toMatch(
      /Showing 2 of 2/,
    );
    fireEvent.change(screen.getByTestId("catalog-filter"), {
      target: { value: "melville" },
    });
    expect(screen.getByTestId("catalog-filter-count").textContent).toMatch(
      /Showing 1 of 2/,
    );
    expect(screen.getByText("Moby-Dick")).toBeTruthy();
    expect(screen.queryByText("Pride and Prejudice")).toBeNull();
    fireEvent.change(screen.getByTestId("catalog-filter"), {
      target: { value: "zzz-no-match" },
    });
    expect(screen.getByTestId("catalog-filter-empty")).toBeTruthy();
  });

  it("opens hosted book in floating HTML window (bt)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
        },
      ],
      count: 1,
      view_format: "html",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_abc",
      owner_id: "operator",
      book_id: "pd-pride",
      content_hash: "x",
      title: "Pride and Prejudice",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_abc"],
      view_format: "html",
      html: "<p>It is a truth universally acknowledged</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "operator",
      documents: [{ document_id: "hdoc_abc" }],
      count: 1,
      view_format: "html",
      html: "<p>Library</p>",
    });

    render(<MarketplaceHost ownerId="operator" />);
    await waitFor(() => {
      expect(screen.getByText("Pride and Prejudice")).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(screen.getByTestId("open-hosted-in-window")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("open-hosted-in-window"));
    expect(openWindow).toHaveBeenCalled();
    const call = openWindow.mock.calls.at(-1) as unknown as [
      string,
      Record<string, unknown>,
      Record<string, unknown>?,
    ];
    expect(call[0]).toBe("hosted_html_document");
    expect(call[1].document_id).toBe("hdoc_abc");
    expect(call[1].view_format).toBe("html");
    expect(String(call[1].html)).toMatch(/truth/);
  });

  it("purchases and hosts paid catalog title with receipt ref", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "buy-modern",
          title: "Modern Systems",
          author: "Author X",
          license_class: "purchased",
          is_free: false,
          source: "bookstore",
        },
      ],
      count: 1,
      view_format: "html",
    });
    purchaseAndHost.mockResolvedValue({
      document_id: "hdoc_buy",
      owner_id: "operator",
      book_id: "buy-modern",
      content_hash: "y",
      title: "Modern Systems",
      license_class: "purchased",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_buy"],
      view_format: "html",
      html: "<p>Hosted after manual purchase receipt</p>",
      receipt_id: "rcpt_1",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "operator",
      documents: [{ document_id: "hdoc_buy", title: "Modern Systems" }],
      count: 1,
      view_format: "html",
      html: "<p>Library with purchase</p>",
    });

    render(<MarketplaceHost ownerId="operator" />);
    await waitFor(() => {
      // Catalog purchase button (library may also list "Modern Systems" after mount).
      expect(screen.getByTestId("purchase-host-buy-modern")).toBeTruthy();
    });
    // Residual (ahe): paid purchase+host seamless port honesty (L5 deferred).
    const purchaseBtn = screen.getByTestId("purchase-host-buy-modern");
    expect(purchaseBtn.getAttribute("data-seamless-purchase-port")).toBe("true");
    expect(purchaseBtn.getAttribute("data-l5-payment-rails")).toBe("deferred");
    expect(purchaseBtn.getAttribute("data-live-payment")).toBe("false");
    expect(purchaseBtn.getAttribute("data-view-format")).toBe("html");
    expect(purchaseBtn.getAttribute("data-payment-rails")).toBe(
      "manual_receipt_only",
    );
    expect(purchaseBtn.getAttribute("data-receipt-required")).toBe("true");
    expect(screen.getByTestId("purchase-receipt-ref")).toBeTruthy();
    // Residual (apd): L5 offline receipt readiness chrome (demo default).
    const readiness = screen.getByTestId("marketplace-receipt-readiness");
    expect(readiness.getAttribute("data-receipt-ready")).toBe("true");
    expect(readiness.getAttribute("data-receipt-demo-default")).toBe("true");
    expect(readiness.getAttribute("data-l5-payment-rails")).toBe("deferred");
    expect(readiness.getAttribute("data-live-payment")).toBe("false");
    expect(Number(readiness.getAttribute("data-paid-catalog-visible") || 0)).toBeGreaterThan(
      0,
    );
    expect(readiness.textContent).toMatch(/demo default/i);
    expect(readiness.textContent).toMatch(/L5 live deferred/i);
    expect(purchaseBtn.getAttribute("data-receipt-ready")).toBe("true");
    expect(purchaseBtn.getAttribute("data-receipt-demo-default")).toBe("true");
    // Residual (apg): free-host readiness chrome always present (HTML path).
    const freeReady = screen.getByTestId("marketplace-free-host-readiness");
    expect(freeReady.getAttribute("data-html-first")).toBe("true");
    expect(freeReady.getAttribute("data-view-format")).toBe("html");
    expect(freeReady.getAttribute("data-live-payment")).toBe("false");
    expect(freeReady.textContent).toMatch(/Free HTML host path/i);
    expect(freeReady.textContent).toMatch(/never PDF/i);
    // Clear receipt → not ready (purchase disabled).
    fireEvent.change(screen.getByTestId("purchase-receipt-ref"), {
      target: { value: "" },
    });
    expect(
      screen.getByTestId("marketplace-receipt-readiness").getAttribute(
        "data-receipt-ready",
      ),
    ).toBe("false");
    expect(
      (screen.getByTestId("purchase-host-buy-modern") as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(
      screen.getByTestId("marketplace-receipt-readiness").textContent,
    ).toMatch(/Enter receipt token/i);
    // Restore demo token for purchase path below.
    fireEvent.change(screen.getByTestId("purchase-receipt-ref"), {
      target: { value: "manual-order-token-demo" },
    });
    // Residual (ala): L5 Sprint 3 offline live-checkout CTA stays deferred/disabled.
    const liveCta = screen.getByTestId("live-checkout-deferred-buy-modern");
    expect(liveCta.getAttribute("data-l5-payment-rails")).toBe("deferred");
    expect(liveCta.getAttribute("data-live-payment")).toBe("false");
    expect(liveCta.getAttribute("data-checkout-cta")).toBe("deferred");
    expect(liveCta.getAttribute("data-live-checkout-available")).toBe("false");
    expect(liveCta.getAttribute("data-payment-adapter-boundary")).toBe(
      "shipped_offline",
    );
    expect((liveCta as HTMLButtonElement).disabled).toBe(true);
    expect(liveCta.textContent).toMatch(/Live checkout \(L5 deferred\)/i);
    const liveNote = screen.getByTestId("live-checkout-deferred-note-buy-modern");
    expect(liveNote.getAttribute("data-checkout-cta")).toBe("deferred");
    expect(liveNote.textContent).toMatch(/manual receipt token/i);
    expect(liveNote.textContent).toMatch(/dual-gate/i);
    fireEvent.click(screen.getByTestId("purchase-host-buy-modern"));
    await waitFor(() => {
      expect(purchaseAndHost).toHaveBeenCalled();
    });
    const call = purchaseAndHost.mock.calls.at(-1)?.[0] as {
      owner_id: string;
      book_id: string;
      opaque_reference: string;
      content_b64: string;
    };
    expect(call.owner_id).toBe("operator");
    expect(call.book_id).toBe("buy-modern");
    expect(call.opaque_reference).toBeTruthy();
    expect(call.content_b64).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByTestId("host-result").textContent).toContain("hdoc_buy");
    });
    // Residual (aho): twin seed after purchase includes purchased port honesty.
    await waitFor(() => {
      expect(seedTwinNotes).toHaveBeenCalled();
      const body = String(
        (seedTwinNotes.mock.calls.at(-1)?.[0] as { body_text?: string })
          ?.body_text || "",
      );
      expect(body).toMatch(/purchased HTML host via manual receipt/i);
      expect(body).toMatch(/L5 live payment deferred/i);
    });
    expect(screen.getByTestId("hosted-html").innerHTML).toMatch(/purchase|Hosted/i);
    expect(
      screen.getByTestId("marketplace-host-mode").getAttribute("data-view-format"),
    ).toBe("html");
    // Residual (tg): purchase-host is NOT free_host (negative honesty).
    const hostMetrics = screen.getByTestId("marketplace-host-metrics");
    expect(hostMetrics.getAttribute("data-license-class")).toBe("purchased");
    expect(hostMetrics.getAttribute("data-is-public-domain")).toBe("false");
    expect(hostMetrics.getAttribute("data-is-free-host")).toBe("false");
    expect(hostMetrics.getAttribute("data-payment-rails")).toBe(
      "manual_receipt_only",
    );
    // Residual (ahe): purchased path seamless port after manual receipt host.
    expect(hostMetrics.getAttribute("data-purchased-path")).toBe("true");
    expect(hostMetrics.getAttribute("data-seamless-purchase-port")).toBe("true");
    expect(hostMetrics.getAttribute("data-live-payment")).toBe("false");
    expect(hostMetrics.getAttribute("data-l5-payment-rails")).toBe("deferred");
    // Residual (aea): seamless port catalog → account library → HTML host.
    expect(hostMetrics.getAttribute("data-seamless-port")).toBe("true");
    expect(hostMetrics.getAttribute("data-library-landed")).toBe("true");
    expect(hostMetrics.getAttribute("data-html-first")).toBe("true");
    expect(hostMetrics.getAttribute("data-view-format")).toBe("html");
    const seamless = screen.getByTestId("marketplace-seamless-port");
    expect(seamless.getAttribute("data-seamless-port")).toBe("true");
    expect(seamless.getAttribute("data-library-landed")).toBe("true");
    expect(seamless.getAttribute("data-view-format")).toBe("html");
    expect(seamless.textContent).toMatch(/Seamless port/i);
    expect(seamless.textContent).toMatch(/account library=landed/);
    const freeHonesty = screen.getByTestId("marketplace-host-free-pd-honesty");
    expect(freeHonesty.getAttribute("data-is-free-host")).toBe("false");
    expect(freeHonesty.getAttribute("data-is-public-domain")).toBe("false");
    expect(freeHonesty.textContent).toMatch(/free_host=false/);
    expect(freeHonesty.textContent).toMatch(/manual_receipt_only/);
  });

  it("prefills host DR depth tier from Settings wrestle (jc)", async () => {
    fetchDepthTiers.mockResolvedValue({
      active_depth_tier: "wrestle",
      active_preset: {
        depth_tier: "wrestle",
        label: "Wrestle",
        description: "deep",
        dispatch_tier: "pro",
        task_class: "wrestle",
        default_input_chars: 8000,
        default_expected_output_tokens: 4000,
        competitor_posture: "depth",
      },
      presets: [],
      projection_hints: null,
      view_format: "html",
      settings_panel: "depth_tier_presets",
      source: "test",
      notes: [],
    });
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-origin",
          title: "On the Origin of Species",
          author: "Charles Darwin",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
        },
      ],
      count: 1,
      view_format: "html",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_origin",
      owner_id: "operator",
      book_id: "pd-origin",
      content_hash: "o",
      title: "On the Origin of Species",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_origin"],
      view_format: "html",
      html: "<p>Beagle voyage</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "operator",
      documents: [],
      count: 0,
      view_format: "html",
      html: "",
    });
    render(<MarketplaceHost ownerId="operator" />);
    await waitFor(() => {
      expect(screen.getByText("On the Origin of Species")).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-host-dr-budget-mount")).toBeTruthy();
    });
    await waitFor(() => {
      const mount = screen.getByTestId("marketplace-host-dr-budget-mount");
      expect(mount.getAttribute("data-depth-prefill")).toBe("installed");
      expect(mount.getAttribute("data-research-tier")).toBe("wrestle");
    });
    expect(
      screen.getByTestId("marketplace-host-dr-depth-prefill").textContent,
    ).toMatch(/installed.*wrestle/i);
    expect(
      screen
        .getByTestId("research-launch-budget-panel-stub")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
  });

  it("groups catalog entries by knowledge source (io)", () => {
    const g = groupCatalogBySource([
      {
        book_id: "pd-origin",
        title: "Origin",
        author: "Darwin",
        license_class: "public_domain",
        is_free: true,
        source: "project_gutenberg",
      },
      {
        book_id: "pd-wealth",
        title: "Wealth",
        author: "Smith",
        license_class: "public_domain",
        is_free: true,
        source: "project_gutenberg",
      },
      {
        book_id: "pd-pride",
        title: "Pride",
        author: "Austen",
        license_class: "public_domain",
        is_free: true,
        source: "standard_ebooks",
      },
    ]);
    expect(g.project_gutenberg).toBe(2);
    expect(g.standard_ebooks).toBe(1);
  });

  it("filters catalog by knowledge source (io)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-origin",
          title: "On the Origin of Species",
          author: "Charles Darwin",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
        },
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
        },
      ],
      count: 2,
      view_format: "html",
    });
    render(<MarketplaceHost ownerId="operator" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-entry-pd-origin")).toBeTruthy();
    });
    fireEvent.change(screen.getByTestId("catalog-filter"), {
      target: { value: "project_gutenberg" },
    });
    expect(screen.getByTestId("catalog-entry-pd-origin")).toBeTruthy();
    expect(screen.queryByTestId("catalog-entry-pd-pride")).toBeNull();
    expect(screen.getByTestId("marketplace-catalog-by-source").textContent).toMatch(
      /project_gutenberg=1/,
    );
  });

  it("filters free public-domain research spine (is/abq)", async () => {
    // Residual (abq): free chip uses is_free only (parity free_count / free_only HTML).
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-origin",
          title: "On the Origin of Species",
          author: "Charles Darwin",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
        },
        {
          book_id: "buy-modern",
          title: "Modern Systems Research",
          author: "Example Press",
          license_class: "purchased",
          is_free: false,
          source: "marketplace_stub",
        },
      ],
      count: 2,
      view_format: "html",
      by_source: { project_gutenberg: 1, marketplace_stub: 1 },
      free_count: 1,
      public_domain_count: 1,
      purchased_count: 1,
      payment_rails: "manual_receipt_only",
    });
    render(<MarketplaceHost ownerId="operator" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-entry-pd-origin")).toBeTruthy();
      expect(screen.getByTestId("purchase-host-buy-modern")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-free-pd-only"));
    expect(screen.getByTestId("catalog-entry-pd-origin")).toBeTruthy();
    expect(screen.queryByTestId("purchase-host-buy-modern")).toBeNull();
    expect(
      screen
        .getByTestId("marketplace-catalog-metrics")
        .getAttribute("data-free-pd-only"),
    ).toBe("true");
    expect(
      (screen.getByTestId("catalog-filter") as HTMLInputElement).placeholder,
    ).toMatch(/subject/i);
    // Residual (ta): filtered free honesty vs full-catalog free_count.
    const metrics = screen.getByTestId("marketplace-catalog-metrics");
    expect(metrics.getAttribute("data-filters-active")).toBe("true");
    expect(metrics.getAttribute("data-free-count")).toBe("1");
    expect(metrics.getAttribute("data-filtered-free-count")).toBe("1");
    expect(metrics.getAttribute("data-filtered-public-domain-count")).toBe("1");
    const honesty = screen.getByTestId(
      "marketplace-catalog-filtered-free-honesty",
    );
    expect(honesty.getAttribute("data-filtered-free-count")).toBe("1");
    expect(honesty.getAttribute("data-catalog-free-count")).toBe("1");
    expect(honesty.getAttribute("data-free-pd-only")).toBe("true");
    expect(honesty.textContent).toMatch(/visible_free=1/);
    expect(honesty.textContent).toMatch(/catalog_free=1/);
    // Residual (abz): free inventory chip copy is free-only (is_free doctrine).
    expect(honesty.textContent).toMatch(/free-only=on/);
  });

  it("groups catalog entries by research subject (lw)", () => {
    const g = groupCatalogBySubject([
      {
        book_id: "pd-elements",
        title: "Elements",
        author: "Euclid",
        license_class: "public_domain",
        is_free: true,
        source: "project_gutenberg",
        subjects: ["mathematics", "science"],
      },
      {
        book_id: "pd-principia",
        title: "Principia",
        author: "Newton",
        license_class: "public_domain",
        is_free: true,
        source: "project_gutenberg",
        subjects: ["physics", "mathematics", "science"],
      },
      {
        book_id: "pd-pride",
        title: "Pride",
        author: "Austen",
        license_class: "public_domain",
        is_free: true,
        source: "standard_ebooks",
        subjects: ["literature"],
      },
    ]);
    expect(g.mathematics).toBe(2);
    expect(g.science).toBe(2);
    expect(g.physics).toBe(1);
    expect(g.literature).toBe(1);
  });

  it("filters catalog by research-domain subject chip (lw)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-elements",
          title: "Euclid's Elements",
          author: "Euclid",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["mathematics", "science"],
        },
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
          subjects: ["literature"],
        },
        {
          book_id: "pd-novum",
          title: "Novum Organum",
          author: "Francis Bacon",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
          subjects: ["philosophy", "science", "method"],
        },
      ],
      count: 3,
      view_format: "html",
      by_source: { project_gutenberg: 1, standard_ebooks: 2 },
      by_subject: {
        mathematics: 1,
        science: 2,
        literature: 1,
        philosophy: 1,
        method: 1,
      },
      free_count: 3,
      public_domain_count: 3,
      purchased_count: 0,
      payment_rails: "manual_receipt_only",
    });
    render(<MarketplaceHost ownerId="operator" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-entry-pd-elements")).toBeTruthy();
      expect(screen.getByTestId("catalog-subject-chips")).toBeTruthy();
    });
    // Server honesty by_subject strip.
    expect(
      screen.getByTestId("marketplace-catalog-by-subject").textContent,
    ).toMatch(/mathematics=1/);
    expect(
      screen.getByTestId("marketplace-catalog-metrics").getAttribute(
        "data-subject-count",
      ),
    ).toBe("5");
    // Chip filters to mathematics only.
    fireEvent.click(screen.getByTestId("catalog-subject-mathematics"));
    expect(screen.getByTestId("catalog-entry-pd-elements")).toBeTruthy();
    expect(screen.queryByTestId("catalog-entry-pd-pride")).toBeNull();
    expect(screen.queryByTestId("catalog-entry-pd-novum")).toBeNull();
    expect(
      screen
        .getByTestId("marketplace-catalog-metrics")
        .getAttribute("data-subject-filter"),
    ).toBe("mathematics");
    expect(
      screen.getByTestId("catalog-entry-pd-elements").getAttribute(
        "data-subjects",
      ),
    ).toBe("mathematics,science");
    // Clear via all domains.
    fireEvent.click(screen.getByTestId("catalog-subject-all"));
    expect(screen.getByTestId("catalog-entry-pd-pride")).toBeTruthy();
    expect(screen.getByTestId("catalog-entry-pd-novum")).toBeTruthy();
  });

  it("opens catalog as HTML asset window (ly)", async () => {
    const catalogHtmlBody =
      "<!DOCTYPE html><html><body><h1>Antiek marketplace catalog</h1>" +
      "<p>Entries=2 · view=HTML · payment=manual_receipt_only</p>" +
      "<p>[public_domain/free] Origin — Darwin · source=project_gutenberg</p>" +
      "</body></html>";
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-origin",
          title: "On the Origin of Species",
          author: "Charles Darwin",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["science", "biology"],
        },
      ],
      count: 1,
      view_format: "html",
      by_source: { project_gutenberg: 1 },
      by_subject: { science: 1, biology: 1 },
      free_count: 1,
      public_domain_count: 1,
      purchased_count: 0,
      payment_rails: "manual_receipt_only",
      html: catalogHtmlBody,
    });
    render(<MarketplaceHost ownerId="operator" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-open-html")).toBeTruthy();
    });
    // Load already called once; open re-fetches with chips.
    fetchMarketplaceCatalog.mockClear();
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-origin",
          title: "On the Origin of Species",
          author: "Charles Darwin",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["science", "biology"],
        },
      ],
      count: 1,
      view_format: "html",
      html: catalogHtmlBody,
      payment_rails: "manual_receipt_only",
    });
    fireEvent.click(screen.getByTestId("catalog-open-html"));
    await waitFor(() => {
      expect(openWindow).toHaveBeenCalled();
    });
    const call = openWindow.mock.calls.find(
      (c) => c[0] === "hosted_html_document",
    );
    expect(call).toBeTruthy();
    // Residual (mi): chip-aware catalog document id (default chips = all/any).
    expect(call![1].document_id).toMatch(/^marketplace-catalog-/);
    expect(call![1].view_format).toBe("html");
    expect(call![1].html).toContain("marketplace catalog");
    expect(call![1].source).toBe("marketplace_catalog");
  });

  it("filters catalog by knowledge-source chip (lx)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-elements",
          title: "Euclid's Elements",
          author: "Euclid",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["mathematics", "science"],
        },
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
          subjects: ["literature"],
        },
        {
          book_id: "buy-modern",
          title: "Modern Systems Research",
          author: "Example Press",
          license_class: "purchased",
          is_free: false,
          source: "marketplace_stub",
          subjects: ["technology"],
        },
      ],
      count: 3,
      view_format: "html",
      by_source: {
        project_gutenberg: 1,
        standard_ebooks: 1,
        marketplace_stub: 1,
      },
      by_subject: {
        mathematics: 1,
        science: 1,
        literature: 1,
        technology: 1,
      },
      free_count: 2,
      public_domain_count: 2,
      purchased_count: 1,
      payment_rails: "manual_receipt_only",
    });
    render(<MarketplaceHost ownerId="operator" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-source-chips")).toBeTruthy();
      expect(screen.getByTestId("catalog-entry-pd-elements")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-source-project_gutenberg"));
    expect(screen.getByTestId("catalog-entry-pd-elements")).toBeTruthy();
    expect(screen.queryByTestId("catalog-entry-pd-pride")).toBeNull();
    expect(screen.queryByTestId("purchase-host-buy-modern")).toBeNull();
    expect(
      screen
        .getByTestId("marketplace-catalog-metrics")
        .getAttribute("data-source-filter"),
    ).toBe("project_gutenberg");
    // Compose with free-PD still shows gutenberg PD.
    fireEvent.click(screen.getByTestId("catalog-free-pd-only"));
    expect(screen.getByTestId("catalog-entry-pd-elements")).toBeTruthy();
    // Residual (ta): source + free-PD filters stamp filtered free honesty.
    const metrics = screen.getByTestId("marketplace-catalog-metrics");
    expect(metrics.getAttribute("data-filters-active")).toBe("true");
    expect(metrics.getAttribute("data-source-filter")).toBe(
      "project_gutenberg",
    );
    expect(metrics.getAttribute("data-filtered-free-count")).toBe("1");
    expect(metrics.getAttribute("data-free-count")).toBe("2");
    expect(
      screen.getByTestId("marketplace-catalog-filtered-free-honesty")
        .textContent,
    ).toMatch(/visible_free=1/);
    expect(
      screen.getByTestId("marketplace-catalog-filtered-free-honesty")
        .textContent,
    ).toMatch(/catalog_free=2/);
    // Clear source → free-PD shows pride too.
    fireEvent.click(screen.getByTestId("catalog-source-all"));
    expect(screen.getByTestId("catalog-entry-pd-pride")).toBeTruthy();
    expect(screen.queryByTestId("purchase-host-buy-modern")).toBeNull();
    expect(
      screen
        .getByTestId("marketplace-catalog-metrics")
        .getAttribute("data-filtered-free-count"),
    ).toBe("2");
  });

  it("composes free-PD-only + electricity chip across Faraday Maxwell Heaviside (xw)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-faraday-electricity",
          title: "Experimental Researches in Electricity",
          author: "Michael Faraday",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["electricity", "physics", "technology"],
        },
        {
          book_id: "pd-maxwell-em",
          title: "A Treatise on Electricity and Magnetism",
          author: "James Clerk Maxwell",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["electricity", "physics", "mathematics"],
        },
        {
          book_id: "pd-heaviside-em",
          title: "Electromagnetic Theory",
          author: "Oliver Heaviside",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["electricity", "engineering", "physics"],
        },
        {
          book_id: "buy-modern",
          title: "Modern Systems Research",
          author: "Example Press",
          license_class: "purchased",
          is_free: false,
          source: "marketplace_stub",
          subjects: ["electricity", "technology"],
        },
      ],
      count: 4,
      view_format: "html",
      free_count: 3,
      public_domain_count: 3,
      by_subject: { electricity: 4 },
      payment_rails: "manual_receipt_only",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-free-pd-only")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-free-pd-only"));
    await waitFor(() => {
      expect(screen.getByTestId("catalog-subject-electricity")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-subject-electricity"));
    expect(screen.getByTestId("catalog-entry-pd-faraday-electricity")).toBeTruthy();
    expect(screen.getByTestId("catalog-entry-pd-maxwell-em")).toBeTruthy();
    expect(screen.getByTestId("catalog-entry-pd-heaviside-em")).toBeTruthy();
    expect(screen.queryByTestId("catalog-entry-buy-modern")).toBeNull();
    const metrics = screen.getByTestId("marketplace-catalog-metrics");
    expect(metrics.getAttribute("data-free-pd-only")).toBe("true");
    expect(metrics.getAttribute("data-subject-filter")).toBe("electricity");
  });

  it("filters catalog by electricity subject chip for Faraday/Maxwell (tk)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-faraday-electricity",
          title: "Experimental Researches in Electricity",
          author: "Michael Faraday",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["physics", "science", "technology", "electricity"],
        },
        {
          book_id: "pd-maxwell-em",
          title: "A Treatise on Electricity and Magnetism",
          author: "James Clerk Maxwell",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "physics",
            "mathematics",
            "science",
            "technology",
            "electricity",
          ],
        },
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
          subjects: ["literature"],
        },
      ],
      count: 3,
      view_format: "html",
      by_source: { project_gutenberg: 2, standard_ebooks: 1 },
      by_subject: {
        electricity: 2,
        physics: 2,
        technology: 2,
        literature: 1,
        science: 2,
        mathematics: 1,
      },
      free_count: 3,
      public_domain_count: 3,
      purchased_count: 0,
      payment_rails: "manual_receipt_only",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-subject-electricity")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-subject-electricity"));
    expect(screen.getByTestId("catalog-entry-pd-faraday-electricity")).toBeTruthy();
    expect(screen.getByTestId("catalog-entry-pd-maxwell-em")).toBeTruthy();
    expect(screen.queryByTestId("catalog-entry-pd-pride")).toBeNull();
    const metrics = screen.getByTestId("marketplace-catalog-metrics");
    expect(metrics.getAttribute("data-subject-filter")).toBe("electricity");
    expect(metrics.getAttribute("data-filtered-free-count")).toBe("2");
    expect(metrics.getAttribute("data-free-count")).toBe("3");
    expect(
      screen.getByTestId("marketplace-catalog-filtered-free-honesty").textContent,
    ).toMatch(/visible_free=2/);
    expect(
      screen
        .getByTestId("catalog-entry-pd-faraday-electricity")
        .getAttribute("data-is-free"),
    ).toBe("true");
  });

  it("hosts Faraday free PD with electricity subjects on host land (tm)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-faraday-electricity",
          title: "Experimental Researches in Electricity",
          author: "Michael Faraday",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["physics", "science", "technology", "electricity"],
        },
      ],
      count: 1,
      view_format: "html",
      by_source: { project_gutenberg: 1 },
      by_subject: { electricity: 1, physics: 1, technology: 1, science: 1 },
      free_count: 1,
      public_domain_count: 1,
      purchased_count: 0,
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_faraday",
      owner_id: "tech-researcher",
      book_id: "pd-faraday-electricity",
      content_hash: "f1",
      title: "Experimental Researches in Electricity",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_faraday"],
      view_format: "html",
      html: "<p>Induction of electric currents</p>",
      usage_event: {
        task_class: "book_qa",
        outcome: "worked",
        source: "marketplace_host",
        prompt_hint: "host pd-faraday-electricity",
      },
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "tech-researcher",
      documents: [
        {
          document_id: "hdoc_faraday",
          title: "Experimental Researches in Electricity",
          license_class: "public_domain",
          view_format: "html",
        },
      ],
      count: 1,
      view_format: "html",
      html: "<p>Library Faraday</p>",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(
        screen.getByTestId("catalog-entry-pd-faraday-electricity"),
      ).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(screen.getByTestId("host-result").textContent).toContain(
        "hdoc_faraday",
      );
    });
    const hostMetrics = screen.getByTestId("marketplace-host-metrics");
    expect(hostMetrics.getAttribute("data-book-id")).toBe(
      "pd-faraday-electricity",
    );
    expect(hostMetrics.getAttribute("data-is-free-host")).toBe("true");
    expect(hostMetrics.getAttribute("data-is-public-domain")).toBe("true");
    expect(hostMetrics.getAttribute("data-subjects")).toMatch(/electricity/);
    expect(hostMetrics.getAttribute("data-catalog-source")).toBe(
      "project_gutenberg",
    );
    expect(
      screen.getByTestId("marketplace-host-free-pd-honesty").textContent,
    ).toMatch(/free_host=true/);
    expect(hostBookIntoAccount).toHaveBeenCalledWith(
      expect.objectContaining({
        owner_id: "tech-researcher",
        book_id: "pd-faraday-electricity",
      }),
    );
  });

  it("hosts Maxwell free PD with electricity subjects on host land (tn)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-maxwell-em",
          title: "A Treatise on Electricity and Magnetism",
          author: "James Clerk Maxwell",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "physics",
            "mathematics",
            "science",
            "technology",
            "electricity",
          ],
        },
      ],
      count: 1,
      view_format: "html",
      by_source: { project_gutenberg: 1 },
      by_subject: {
        electricity: 1,
        physics: 1,
        technology: 1,
        science: 1,
        mathematics: 1,
      },
      free_count: 1,
      public_domain_count: 1,
      purchased_count: 0,
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_maxwell",
      owner_id: "tech-researcher",
      book_id: "pd-maxwell-em",
      content_hash: "m1",
      title: "A Treatise on Electricity and Magnetism",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_maxwell"],
      view_format: "html",
      html: "<p>electromagnetic field waves</p>",
      usage_event: {
        task_class: "book_qa",
        outcome: "worked",
        source: "marketplace_host",
        prompt_hint: "host pd-maxwell-em",
      },
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "tech-researcher",
      documents: [
        {
          document_id: "hdoc_maxwell",
          title: "A Treatise on Electricity and Magnetism",
          license_class: "public_domain",
          view_format: "html",
        },
      ],
      count: 1,
      view_format: "html",
      html: "<p>Library Maxwell</p>",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-entry-pd-maxwell-em")).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(screen.getByTestId("host-result").textContent).toContain(
        "hdoc_maxwell",
      );
    });
    const hostMetrics = screen.getByTestId("marketplace-host-metrics");
    expect(hostMetrics.getAttribute("data-book-id")).toBe("pd-maxwell-em");
    expect(hostMetrics.getAttribute("data-is-free-host")).toBe("true");
    expect(hostMetrics.getAttribute("data-subjects")).toMatch(/electricity/);
    expect(hostMetrics.getAttribute("data-subjects")).toMatch(/mathematics/);
    expect(
      screen.getByTestId("marketplace-host-free-pd-honesty").textContent,
    ).toMatch(/free_host=true/);
  });

  it("launches Faraday DR with electricity domains in goal_hint (to)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-faraday-electricity",
          title: "Experimental Researches in Electricity",
          author: "Michael Faraday",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["physics", "science", "technology", "electricity"],
        },
      ],
      count: 1,
      view_format: "html",
      free_count: 1,
      public_domain_count: 1,
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_faraday_dr",
      owner_id: "tech-researcher",
      book_id: "pd-faraday-electricity",
      content_hash: "f2",
      title: "Experimental Researches in Electricity",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_faraday_dr"],
      view_format: "html",
      html: "<p>Induction of electric currents</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "tech-researcher",
      documents: [],
      count: 0,
      view_format: "html",
      html: "",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(
        screen.getByTestId("catalog-entry-pd-faraday-electricity"),
      ).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-host-deep-research")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("marketplace-host-deep-research"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalled();
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      asset_id: string;
      goal_hint: string;
      view_mode: string;
      research_tier: string;
    };
    expect(call.asset_id).toBe("hdoc_faraday_dr");
    expect(call.view_mode).toBe("floating");
    expect(call.goal_hint).toMatch(/domains=.*electricity/);
    expect(call.goal_hint).toMatch(/marketplace HTML host/);
    expect(call.goal_hint).toMatch(/Experimental Researches/);
  });

  it("launches Maxwell DR with electricity domains in goal_hint (tp)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-maxwell-em",
          title: "A Treatise on Electricity and Magnetism",
          author: "James Clerk Maxwell",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "physics",
            "mathematics",
            "science",
            "technology",
            "electricity",
          ],
        },
      ],
      count: 1,
      view_format: "html",
      free_count: 1,
      public_domain_count: 1,
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_maxwell_dr",
      owner_id: "tech-researcher",
      book_id: "pd-maxwell-em",
      content_hash: "m2",
      title: "A Treatise on Electricity and Magnetism",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_maxwell_dr"],
      view_format: "html",
      html: "<p>electromagnetic field waves</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "tech-researcher",
      documents: [],
      count: 0,
      view_format: "html",
      html: "",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-entry-pd-maxwell-em")).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(
        screen.getByTestId("marketplace-host-deep-research-full"),
      ).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("marketplace-host-deep-research-full"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalled();
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      asset_id: string;
      goal_hint: string;
      view_mode: string;
    };
    expect(call.asset_id).toBe("hdoc_maxwell_dr");
    expect(call.view_mode).toBe("full");
    expect(call.goal_hint).toMatch(/domains=.*electricity/);
    expect(call.goal_hint).toMatch(/domains=.*mathematics/);
    expect(call.goal_hint).toMatch(/Treatise on Electricity/);
  });

  it("composes free-PD-only + technology chip for tech-researcher STEM (yo)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-faraday-electricity",
          title: "Experimental Researches in Electricity",
          author: "Michael Faraday",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["electricity", "technology", "physics"],
        },
        {
          book_id: "pd-shannon-communication",
          title: "A Mathematical Theory of Communication",
          author: "Claude E. Shannon",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["computing", "technology", "information_theory"],
        },
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
          subjects: ["literature"],
        },
        {
          book_id: "buy-modern",
          title: "Modern Systems Research",
          author: "Example Press",
          license_class: "purchased",
          is_free: false,
          source: "marketplace_stub",
          subjects: ["technology", "systems"],
        },
      ],
      count: 4,
      view_format: "html",
      free_count: 3,
      public_domain_count: 3,
      by_subject: { technology: 3, literature: 1 },
      payment_rails: "manual_receipt_only",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-free-pd-only")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-free-pd-only"));
    await waitFor(() => {
      expect(screen.getByTestId("catalog-subject-technology")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-subject-technology"));
    expect(screen.getByTestId("catalog-entry-pd-faraday-electricity")).toBeTruthy();
    expect(
      screen.getByTestId("catalog-entry-pd-shannon-communication"),
    ).toBeTruthy();
    expect(screen.queryByTestId("catalog-entry-pd-pride")).toBeNull();
    expect(screen.queryByTestId("catalog-entry-buy-modern")).toBeNull();
    const metrics = screen.getByTestId("marketplace-catalog-metrics");
    expect(metrics.getAttribute("data-free-pd-only")).toBe("true");
    expect(metrics.getAttribute("data-subject-filter")).toBe("technology");
  });

  it("composes free-PD-only + computing chip across Boole Shannon Turing Lovelace (xp)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-boole-laws-of-thought",
          title: "An Investigation of the Laws of Thought",
          author: "George Boole",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["computing", "logic", "mathematics"],
        },
        {
          book_id: "pd-shannon-communication",
          title: "A Mathematical Theory of Communication",
          author: "Claude E. Shannon",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["computing", "information_theory"],
        },
        {
          book_id: "pd-turing-computable-numbers",
          title: "On Computable Numbers",
          author: "Alan M. Turing",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["computing", "computability"],
        },
        {
          book_id: "pd-lovelace-analytical-engine",
          title: "Sketch of the Analytical Engine",
          author: "Ada Lovelace",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["computing", "history"],
        },
        {
          book_id: "buy-modern",
          title: "Modern Systems Research",
          author: "Example Press",
          license_class: "purchased",
          is_free: false,
          source: "marketplace_stub",
          subjects: ["computing", "technology"],
        },
      ],
      count: 5,
      view_format: "html",
      free_count: 4,
      public_domain_count: 4,
      by_subject: { computing: 5 },
      payment_rails: "manual_receipt_only",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-free-pd-only")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-free-pd-only"));
    await waitFor(() => {
      expect(screen.getByTestId("catalog-subject-computing")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-subject-computing"));
    expect(
      screen.getByTestId("catalog-entry-pd-boole-laws-of-thought"),
    ).toBeTruthy();
    expect(
      screen.getByTestId("catalog-entry-pd-shannon-communication"),
    ).toBeTruthy();
    expect(
      screen.getByTestId("catalog-entry-pd-turing-computable-numbers"),
    ).toBeTruthy();
    expect(
      screen.getByTestId("catalog-entry-pd-lovelace-analytical-engine"),
    ).toBeTruthy();
    expect(screen.queryByTestId("catalog-entry-buy-modern")).toBeNull();
    const metrics = screen.getByTestId("marketplace-catalog-metrics");
    expect(metrics.getAttribute("data-free-pd-only")).toBe("true");
    expect(metrics.getAttribute("data-subject-filter")).toBe("computing");
  });

  it("stamps foundations count + Gödel free PD catalog honesty (agl)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-godel-incompleteness",
          title: "On Formally Undecidable Propositions",
          author: "Kurt Gödel",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["foundations", "logic", "computing", "mathematics"],
        },
        {
          book_id: "pd-turing-computable-numbers",
          title: "On Computable Numbers",
          author: "Alan M. Turing",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["computing", "computability"],
        },
      ],
      count: 2,
      view_format: "html",
      free_count: 2,
      public_domain_count: 2,
      by_subject: { foundations: 1, computing: 2, logic: 1 },
      payment_rails: "manual_receipt_only",
    });
    render(<MarketplaceHost ownerId="foundations-reader" />);
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-catalog-metrics")).toBeTruthy();
    });
    const metrics = screen.getByTestId("marketplace-catalog-metrics");
    expect(metrics.getAttribute("data-has-godel-pd")).toBe("true");
    expect(metrics.getAttribute("data-foundations-count")).toBe("1");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.textContent).toMatch(/foundations=1/);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-subject-foundations")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-subject-foundations"));
    expect(
      screen.getByTestId("catalog-entry-pd-godel-incompleteness"),
    ).toBeTruthy();
    expect(
      screen.queryByTestId("catalog-entry-pd-turing-computable-numbers"),
    ).toBeNull();
    expect(
      screen
        .getByTestId("marketplace-catalog-metrics")
        .getAttribute("data-subject-filter"),
    ).toBe("foundations");
  });

  it("stamps heat + signal_processing counts + Fourier free PD catalog honesty (agt)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-fourier-heat",
          title: "The Analytical Theory of Heat",
          author: "Joseph Fourier",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "heat",
            "signal_processing",
            "engineering",
            "physics",
            "mathematics",
          ],
        },
        {
          book_id: "pd-maxwell-em",
          title: "A Treatise on Electricity and Magnetism",
          author: "James Clerk Maxwell",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["electricity", "physics", "science"],
        },
      ],
      count: 2,
      view_format: "html",
      free_count: 2,
      public_domain_count: 2,
      by_subject: {
        heat: 1,
        signal_processing: 1,
        engineering: 1,
        physics: 2,
        electricity: 1,
      },
      payment_rails: "manual_receipt_only",
    });
    render(<MarketplaceHost ownerId="heat-reader" />);
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-catalog-metrics")).toBeTruthy();
    });
    const metrics = screen.getByTestId("marketplace-catalog-metrics");
    expect(metrics.getAttribute("data-has-fourier-pd")).toBe("true");
    expect(metrics.getAttribute("data-heat-count")).toBe("1");
    expect(metrics.getAttribute("data-signal-processing-count")).toBe("1");
    expect(metrics.getAttribute("data-view-format")).toBe("html");
    expect(metrics.textContent).toMatch(/heat=1/);
    expect(metrics.textContent).toMatch(/signal_processing=1/);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-subject-heat")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-subject-heat"));
    expect(screen.getByTestId("catalog-entry-pd-fourier-heat")).toBeTruthy();
    expect(screen.queryByTestId("catalog-entry-pd-maxwell-em")).toBeNull();
    expect(
      screen
        .getByTestId("marketplace-catalog-metrics")
        .getAttribute("data-subject-filter"),
    ).toBe("heat");
    fireEvent.click(screen.getByTestId("catalog-subject-signal_processing"));
    expect(screen.getByTestId("catalog-entry-pd-fourier-heat")).toBeTruthy();
    expect(screen.queryByTestId("catalog-entry-pd-maxwell-em")).toBeNull();
    expect(
      screen
        .getByTestId("marketplace-catalog-metrics")
        .getAttribute("data-subject-filter"),
    ).toBe("signal_processing");
  });

  it("filters catalog by computing subject chip for Boole (ty)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-boole-laws-of-thought",
          title: "An Investigation of the Laws of Thought",
          author: "George Boole",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "mathematics",
            "logic",
            "philosophy",
            "science",
            "technology",
            "computing",
          ],
        },
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
          subjects: ["literature"],
        },
      ],
      count: 2,
      view_format: "html",
      free_count: 2,
      public_domain_count: 2,
      by_subject: {
        computing: 1,
        logic: 1,
        mathematics: 1,
        literature: 1,
      },
      payment_rails: "manual_receipt_only",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-subject-computing")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-subject-computing"));
    expect(
      screen.getByTestId("catalog-entry-pd-boole-laws-of-thought"),
    ).toBeTruthy();
    expect(screen.queryByTestId("catalog-entry-pd-pride")).toBeNull();
    const metrics = screen.getByTestId("marketplace-catalog-metrics");
    expect(metrics.getAttribute("data-subject-filter")).toBe("computing");
  });

  it("hosts Boole free PD with computing subjects on host land (ty)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-boole-laws-of-thought",
          title: "An Investigation of the Laws of Thought",
          author: "George Boole",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "mathematics",
            "logic",
            "philosophy",
            "science",
            "technology",
            "computing",
          ],
        },
      ],
      count: 1,
      view_format: "html",
      free_count: 1,
      public_domain_count: 1,
      by_subject: {
        computing: 1,
        logic: 1,
        mathematics: 1,
        technology: 1,
      },
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_boole",
      owner_id: "tech-researcher",
      book_id: "pd-boole-laws-of-thought",
      content_hash: "b1",
      title: "An Investigation of the Laws of Thought",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_boole"],
      view_format: "html",
      html: "<p>symbolical language of a Calculus of Logic</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "tech-researcher",
      documents: [],
      count: 0,
      view_format: "html",
      html: "<p>Library Boole</p>",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(
        screen.getByTestId("catalog-entry-pd-boole-laws-of-thought"),
      ).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(hostBookIntoAccount).toHaveBeenCalledWith(
        expect.objectContaining({
          owner_id: "tech-researcher",
          book_id: "pd-boole-laws-of-thought",
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-host-metrics")).toBeTruthy();
    });
    const hostMetrics = screen.getByTestId("marketplace-host-metrics");
    expect(hostMetrics.getAttribute("data-subjects")).toMatch(/computing/);
    expect(hostMetrics.getAttribute("data-subjects")).toMatch(/logic/);
    expect(
      screen.getByTestId("marketplace-host-free-pd-honesty").textContent,
    ).toMatch(/free_host=true/);
  });

  it("launches Boole DR with computing+logic domains in goal_hint (ty)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-boole-laws-of-thought",
          title: "An Investigation of the Laws of Thought",
          author: "George Boole",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "mathematics",
            "logic",
            "philosophy",
            "science",
            "technology",
            "computing",
          ],
        },
      ],
      count: 1,
      view_format: "html",
      free_count: 1,
      public_domain_count: 1,
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_boole_dr",
      owner_id: "tech-researcher",
      book_id: "pd-boole-laws-of-thought",
      content_hash: "b2",
      title: "An Investigation of the Laws of Thought",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_boole_dr"],
      view_format: "html",
      html: "<p>Laws of Thought and the Calculus of Logic</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "tech-researcher",
      documents: [],
      count: 0,
      view_format: "html",
      html: "",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(
        screen.getByTestId("catalog-entry-pd-boole-laws-of-thought"),
      ).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-host-deep-research")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("marketplace-host-deep-research"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalled();
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      asset_id: string;
      goal_hint: string;
      view_mode: string;
    };
    expect(call.asset_id).toBe("hdoc_boole_dr");
    expect(call.view_mode).toBe("floating");
    expect(call.goal_hint).toMatch(/domains=.*computing/);
    expect(call.goal_hint).toMatch(/domains=.*logic/);
    expect(call.goal_hint).toMatch(/marketplace HTML host/);
    expect(call.goal_hint).toMatch(/Laws of Thought/);
  });

  it("hosts Heaviside free PD with electricity subjects on host land (uc)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-heaviside-em",
          title: "Electromagnetic Theory",
          author: "Oliver Heaviside",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "physics",
            "mathematics",
            "science",
            "technology",
            "electricity",
            "engineering",
          ],
        },
      ],
      count: 1,
      view_format: "html",
      free_count: 1,
      public_domain_count: 1,
      by_subject: {
        electricity: 1,
        engineering: 1,
        physics: 1,
      },
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_heaviside",
      owner_id: "tech-researcher",
      book_id: "pd-heaviside-em",
      content_hash: "h1",
      title: "Electromagnetic Theory",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_heaviside"],
      view_format: "html",
      html: "<p>Heaviside operational calculus and Maxwell vector form</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "tech-researcher",
      documents: [],
      count: 0,
      view_format: "html",
      html: "<p>Library Heaviside</p>",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-entry-pd-heaviside-em")).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(hostBookIntoAccount).toHaveBeenCalledWith(
        expect.objectContaining({
          owner_id: "tech-researcher",
          book_id: "pd-heaviside-em",
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-host-metrics")).toBeTruthy();
    });
    const hostMetrics = screen.getByTestId("marketplace-host-metrics");
    expect(hostMetrics.getAttribute("data-subjects")).toMatch(/electricity/);
    expect(hostMetrics.getAttribute("data-subjects")).toMatch(/engineering/);
    expect(
      screen.getByTestId("marketplace-host-free-pd-honesty").textContent,
    ).toMatch(/free_host=true/);
  });

  it("launches Heaviside DR with electricity+engineering domains in goal_hint (uc)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-heaviside-em",
          title: "Electromagnetic Theory",
          author: "Oliver Heaviside",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "physics",
            "mathematics",
            "science",
            "technology",
            "electricity",
            "engineering",
          ],
        },
      ],
      count: 1,
      view_format: "html",
      free_count: 1,
      public_domain_count: 1,
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_heaviside_dr",
      owner_id: "tech-researcher",
      book_id: "pd-heaviside-em",
      content_hash: "h2",
      title: "Electromagnetic Theory",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_heaviside_dr"],
      view_format: "html",
      html: "<p>Electromagnetic waves and operational calculus</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "tech-researcher",
      documents: [],
      count: 0,
      view_format: "html",
      html: "",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-entry-pd-heaviside-em")).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-host-deep-research")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("marketplace-host-deep-research"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalled();
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      asset_id: string;
      goal_hint: string;
      view_mode: string;
    };
    expect(call.asset_id).toBe("hdoc_heaviside_dr");
    expect(call.view_mode).toBe("floating");
    expect(call.goal_hint).toMatch(/domains=.*electricity/);
    expect(call.goal_hint).toMatch(/domains=.*engineering/);
    expect(call.goal_hint).toMatch(/marketplace HTML host/);
    expect(call.goal_hint).toMatch(/Electromagnetic Theory/);
  });

  it("composes free-PD-only + information_theory chip for Shannon (ww)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-shannon-communication",
          title: "A Mathematical Theory of Communication",
          author: "Claude E. Shannon",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["computing", "information_theory", "mathematics"],
        },
        {
          book_id: "buy-modern",
          title: "Modern Systems Research",
          author: "Example Press",
          license_class: "purchased",
          is_free: false,
          source: "marketplace_stub",
          subjects: ["technology", "systems", "information_theory"],
        },
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
          subjects: ["literature"],
        },
      ],
      count: 3,
      view_format: "html",
      free_count: 2,
      public_domain_count: 2,
      by_subject: {
        information_theory: 2,
        computing: 1,
        literature: 1,
      },
      payment_rails: "manual_receipt_only",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-free-pd-only")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-free-pd-only"));
    await waitFor(() => {
      expect(
        screen.getByTestId("catalog-subject-information_theory"),
      ).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-subject-information_theory"));
    expect(
      screen.getByTestId("catalog-entry-pd-shannon-communication"),
    ).toBeTruthy();
    expect(screen.queryByTestId("catalog-entry-buy-modern")).toBeNull();
    expect(screen.queryByTestId("catalog-entry-pd-pride")).toBeNull();
    const metrics = screen.getByTestId("marketplace-catalog-metrics");
    expect(metrics.getAttribute("data-free-pd-only")).toBe("true");
    expect(metrics.getAttribute("data-subject-filter")).toBe(
      "information_theory",
    );
  });

  it("filters catalog by information_theory subject chip for Shannon (wq)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-shannon-communication",
          title: "A Mathematical Theory of Communication",
          author: "Claude E. Shannon",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "mathematics",
            "science",
            "technology",
            "computing",
            "information_theory",
            "engineering",
          ],
        },
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
          subjects: ["literature"],
        },
      ],
      count: 2,
      view_format: "html",
      free_count: 2,
      public_domain_count: 2,
      by_subject: {
        information_theory: 1,
        computing: 1,
        literature: 1,
      },
      payment_rails: "manual_receipt_only",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(
        screen.getByTestId("catalog-subject-information_theory"),
      ).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-subject-information_theory"));
    expect(
      screen.getByTestId("catalog-entry-pd-shannon-communication"),
    ).toBeTruthy();
    expect(screen.queryByTestId("catalog-entry-pd-pride")).toBeNull();
    const metrics = screen.getByTestId("marketplace-catalog-metrics");
    expect(metrics.getAttribute("data-subject-filter")).toBe(
      "information_theory",
    );
  });

  it("hosts Shannon free PD with information_theory subjects on host land (wd)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-shannon-communication",
          title: "A Mathematical Theory of Communication",
          author: "Claude E. Shannon",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "mathematics",
            "science",
            "technology",
            "computing",
            "information_theory",
            "engineering",
          ],
        },
      ],
      count: 1,
      view_format: "html",
      free_count: 1,
      public_domain_count: 1,
      by_subject: {
        computing: 1,
        information_theory: 1,
        mathematics: 1,
      },
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_shannon",
      owner_id: "tech-researcher",
      book_id: "pd-shannon-communication",
      content_hash: "s1",
      title: "A Mathematical Theory of Communication",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_shannon"],
      view_format: "html",
      html: "<p>Shannon entropy and the fundamental problem of communication</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "tech-researcher",
      documents: [],
      count: 0,
      view_format: "html",
      html: "<p>Library Shannon</p>",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(
        screen.getByTestId("catalog-entry-pd-shannon-communication"),
      ).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(hostBookIntoAccount).toHaveBeenCalledWith(
        expect.objectContaining({
          owner_id: "tech-researcher",
          book_id: "pd-shannon-communication",
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-host-metrics")).toBeTruthy();
    });
    const hostMetrics = screen.getByTestId("marketplace-host-metrics");
    expect(hostMetrics.getAttribute("data-subjects")).toMatch(/information_theory/);
    expect(hostMetrics.getAttribute("data-subjects")).toMatch(/computing/);
    expect(
      screen.getByTestId("marketplace-host-free-pd-honesty").textContent,
    ).toMatch(/free_host=true/);
  });

  it("launches Shannon DR with computing+information_theory domains in goal_hint (wd)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-shannon-communication",
          title: "A Mathematical Theory of Communication",
          author: "Claude E. Shannon",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "mathematics",
            "science",
            "technology",
            "computing",
            "information_theory",
            "engineering",
          ],
        },
      ],
      count: 1,
      view_format: "html",
      free_count: 1,
      public_domain_count: 1,
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_shannon_dr",
      owner_id: "tech-researcher",
      book_id: "pd-shannon-communication",
      content_hash: "s2",
      title: "A Mathematical Theory of Communication",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_shannon_dr"],
      view_format: "html",
      html: "<p>Logarithmic information measure and communication channels</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "tech-researcher",
      documents: [],
      count: 0,
      view_format: "html",
      html: "",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(
        screen.getByTestId("catalog-entry-pd-shannon-communication"),
      ).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-host-deep-research")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("marketplace-host-deep-research"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalled();
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      asset_id: string;
      goal_hint: string;
      view_mode: string;
    };
    expect(call.asset_id).toBe("hdoc_shannon_dr");
    expect(call.view_mode).toBe("floating");
    expect(call.goal_hint).toMatch(/domains=.*computing/);
    expect(call.goal_hint).toMatch(/domains=.*information_theory/);
    expect(call.goal_hint).toMatch(/marketplace HTML host/);
    expect(call.goal_hint).toMatch(/Mathematical Theory of Communication/);
  });

  it("composes free-PD-only + computability chip for Turing (wv)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-turing-computable-numbers",
          title: "On Computable Numbers",
          author: "Alan M. Turing",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["computing", "computability", "logic"],
        },
        {
          book_id: "buy-modern",
          title: "Modern Systems Research",
          author: "Example Press",
          license_class: "purchased",
          is_free: false,
          source: "marketplace_stub",
          subjects: ["technology", "systems", "computability"],
        },
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
          subjects: ["literature"],
        },
      ],
      count: 3,
      view_format: "html",
      free_count: 2,
      public_domain_count: 2,
      by_subject: {
        computability: 2,
        computing: 1,
        literature: 1,
      },
      payment_rails: "manual_receipt_only",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-free-pd-only")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-free-pd-only"));
    await waitFor(() => {
      expect(screen.getByTestId("catalog-subject-computability")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-subject-computability"));
    expect(
      screen.getByTestId("catalog-entry-pd-turing-computable-numbers"),
    ).toBeTruthy();
    expect(screen.queryByTestId("catalog-entry-buy-modern")).toBeNull();
    expect(screen.queryByTestId("catalog-entry-pd-pride")).toBeNull();
    const metrics = screen.getByTestId("marketplace-catalog-metrics");
    expect(metrics.getAttribute("data-free-pd-only")).toBe("true");
    expect(metrics.getAttribute("data-subject-filter")).toBe("computability");
  });

  it("filters catalog by computability subject chip for Turing (wp)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-turing-computable-numbers",
          title: "On Computable Numbers",
          author: "Alan M. Turing",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "mathematics",
            "science",
            "technology",
            "computing",
            "logic",
            "computability",
          ],
        },
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
          subjects: ["literature"],
        },
      ],
      count: 2,
      view_format: "html",
      free_count: 2,
      public_domain_count: 2,
      by_subject: {
        computability: 1,
        computing: 1,
        literature: 1,
      },
      payment_rails: "manual_receipt_only",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-subject-computability")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-subject-computability"));
    expect(
      screen.getByTestId("catalog-entry-pd-turing-computable-numbers"),
    ).toBeTruthy();
    expect(screen.queryByTestId("catalog-entry-pd-pride")).toBeNull();
    const metrics = screen.getByTestId("marketplace-catalog-metrics");
    expect(metrics.getAttribute("data-subject-filter")).toBe("computability");
  });

  it("launches Lovelace DR with computing+history domains in goal_hint (xk)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-lovelace-analytical-engine",
          title: "Sketch of the Analytical Engine Invented by Charles Babbage",
          author: "Ada Lovelace",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "mathematics",
            "science",
            "technology",
            "computing",
            "history",
            "engineering",
          ],
        },
      ],
      count: 1,
      view_format: "html",
      free_count: 1,
      public_domain_count: 1,
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_lovelace_dr",
      owner_id: "tech-researcher",
      book_id: "pd-lovelace-analytical-engine",
      content_hash: "l2",
      title: "Sketch of the Analytical Engine",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_lovelace_dr"],
      view_format: "html",
      html: "<p>Algebraical patterns and the Jacquard-loom metaphor</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "tech-researcher",
      documents: [],
      count: 0,
      view_format: "html",
      html: "",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(
        screen.getByTestId("catalog-entry-pd-lovelace-analytical-engine"),
      ).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-host-deep-research")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("marketplace-host-deep-research"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalled();
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      asset_id: string;
      goal_hint: string;
      view_mode: string;
    };
    expect(call.asset_id).toBe("hdoc_lovelace_dr");
    expect(call.view_mode).toBe("floating");
    expect(call.goal_hint).toMatch(/domains=.*computing/);
    expect(call.goal_hint).toMatch(/domains=.*history/);
    expect(call.goal_hint).toMatch(/marketplace HTML host/);
    expect(call.goal_hint).toMatch(/Analytical Engine|Lovelace|Babbage/i);
  });

  it("composes free-PD-only + history chip for Lovelace (xl)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-lovelace-analytical-engine",
          title: "Sketch of the Analytical Engine",
          author: "Ada Lovelace",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["computing", "history", "mathematics"],
        },
        {
          book_id: "buy-modern",
          title: "Modern Systems Research",
          author: "Example Press",
          license_class: "purchased",
          is_free: false,
          source: "marketplace_stub",
          subjects: ["technology", "history", "systems"],
        },
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
          subjects: ["literature"],
        },
      ],
      count: 3,
      view_format: "html",
      free_count: 2,
      public_domain_count: 2,
      by_subject: {
        history: 2,
        computing: 1,
        literature: 1,
      },
      payment_rails: "manual_receipt_only",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-free-pd-only")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-free-pd-only"));
    await waitFor(() => {
      expect(screen.getByTestId("catalog-subject-history")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-subject-history"));
    expect(
      screen.getByTestId("catalog-entry-pd-lovelace-analytical-engine"),
    ).toBeTruthy();
    expect(screen.queryByTestId("catalog-entry-buy-modern")).toBeNull();
    expect(screen.queryByTestId("catalog-entry-pd-pride")).toBeNull();
    const metrics = screen.getByTestId("marketplace-catalog-metrics");
    expect(metrics.getAttribute("data-free-pd-only")).toBe("true");
    expect(metrics.getAttribute("data-subject-filter")).toBe("history");
  });

  it("filters catalog by history subject chip for Lovelace (xj)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-lovelace-analytical-engine",
          title: "Sketch of the Analytical Engine",
          author: "Ada Lovelace",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["computing", "history", "mathematics"],
        },
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
          subjects: ["literature"],
        },
      ],
      count: 2,
      view_format: "html",
      free_count: 2,
      public_domain_count: 2,
      by_subject: {
        history: 1,
        computing: 1,
        literature: 1,
      },
      payment_rails: "manual_receipt_only",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(screen.getByTestId("catalog-subject-history")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("catalog-subject-history"));
    expect(
      screen.getByTestId("catalog-entry-pd-lovelace-analytical-engine"),
    ).toBeTruthy();
    expect(screen.queryByTestId("catalog-entry-pd-pride")).toBeNull();
    const metrics = screen.getByTestId("marketplace-catalog-metrics");
    expect(metrics.getAttribute("data-subject-filter")).toBe("history");
  });

  it("hosts Lovelace free PD with computing history subjects on host land (xi)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-lovelace-analytical-engine",
          title: "Sketch of the Analytical Engine Invented by Charles Babbage",
          author: "Ada Lovelace",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "mathematics",
            "science",
            "technology",
            "computing",
            "history",
            "engineering",
          ],
        },
      ],
      count: 1,
      view_format: "html",
      free_count: 1,
      public_domain_count: 1,
      by_subject: {
        computing: 1,
        history: 1,
        engineering: 1,
      },
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_lovelace",
      owner_id: "tech-researcher",
      book_id: "pd-lovelace-analytical-engine",
      content_hash: "l1",
      title: "Sketch of the Analytical Engine",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_lovelace"],
      view_format: "html",
      html: "<p>Lovelace weaves algebraical patterns on the Analytical Engine</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "tech-researcher",
      documents: [],
      count: 0,
      view_format: "html",
      html: "<p>Library Lovelace</p>",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(
        screen.getByTestId("catalog-entry-pd-lovelace-analytical-engine"),
      ).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(hostBookIntoAccount).toHaveBeenCalledWith(
        expect.objectContaining({
          owner_id: "tech-researcher",
          book_id: "pd-lovelace-analytical-engine",
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-host-metrics")).toBeTruthy();
    });
    const hostMetrics = screen.getByTestId("marketplace-host-metrics");
    expect(hostMetrics.getAttribute("data-subjects")).toMatch(/computing/);
    expect(hostMetrics.getAttribute("data-subjects")).toMatch(/history/);
    expect(
      screen.getByTestId("marketplace-host-free-pd-honesty").textContent,
    ).toMatch(/free_host=true/);
  });

  it("hosts Turing free PD with computability subjects on host land (wl)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-turing-computable-numbers",
          title: "On Computable Numbers, with an Application to the Entscheidungsproblem",
          author: "Alan M. Turing",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "mathematics",
            "science",
            "technology",
            "computing",
            "logic",
            "computability",
          ],
        },
      ],
      count: 1,
      view_format: "html",
      free_count: 1,
      public_domain_count: 1,
      by_subject: {
        computing: 1,
        computability: 1,
        logic: 1,
      },
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_turing",
      owner_id: "tech-researcher",
      book_id: "pd-turing-computable-numbers",
      content_hash: "t1",
      title: "On Computable Numbers",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_turing"],
      view_format: "html",
      html: "<p>Turing machines and the Entscheidungsproblem</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "tech-researcher",
      documents: [],
      count: 0,
      view_format: "html",
      html: "<p>Library Turing</p>",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(
        screen.getByTestId("catalog-entry-pd-turing-computable-numbers"),
      ).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(hostBookIntoAccount).toHaveBeenCalledWith(
        expect.objectContaining({
          owner_id: "tech-researcher",
          book_id: "pd-turing-computable-numbers",
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-host-metrics")).toBeTruthy();
    });
    const hostMetrics = screen.getByTestId("marketplace-host-metrics");
    expect(hostMetrics.getAttribute("data-subjects")).toMatch(/computability/);
    expect(hostMetrics.getAttribute("data-subjects")).toMatch(/computing/);
    expect(
      screen.getByTestId("marketplace-host-free-pd-honesty").textContent,
    ).toMatch(/free_host=true/);
  });

  it("launches Turing DR with computing+computability domains in goal_hint (wm)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-turing-computable-numbers",
          title: "On Computable Numbers, with an Application to the Entscheidungsproblem",
          author: "Alan M. Turing",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: [
            "mathematics",
            "science",
            "technology",
            "computing",
            "logic",
            "computability",
          ],
        },
      ],
      count: 1,
      view_format: "html",
      free_count: 1,
      public_domain_count: 1,
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_turing_dr",
      owner_id: "tech-researcher",
      book_id: "pd-turing-computable-numbers",
      content_hash: "t2",
      title: "On Computable Numbers",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_turing_dr"],
      view_format: "html",
      html: "<p>Machine calculation and undecidability</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "tech-researcher",
      documents: [],
      count: 0,
      view_format: "html",
      html: "",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(
        screen.getByTestId("catalog-entry-pd-turing-computable-numbers"),
      ).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-host-deep-research")).toBeTruthy();
    });
    fireEvent.click(screen.getByTestId("marketplace-host-deep-research"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalled();
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      asset_id: string;
      goal_hint: string;
      view_mode: string;
    };
    expect(call.asset_id).toBe("hdoc_turing_dr");
    expect(call.view_mode).toBe("floating");
    expect(call.goal_hint).toMatch(/domains=.*computing/);
    expect(call.goal_hint).toMatch(/domains=.*computability/);
    expect(call.goal_hint).toMatch(/marketplace HTML host/);
    expect(call.goal_hint).toMatch(/Computable Numbers|Entscheidungsproblem/);
  });

  it("grounds marketplace DR with optional arxiv pub refs (uu)", async () => {
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-boole-laws-of-thought",
          title: "An Investigation of the Laws of Thought",
          author: "George Boole",
          license_class: "public_domain",
          is_free: true,
          source: "project_gutenberg",
          subjects: ["computing", "logic", "mathematics"],
        },
      ],
      count: 1,
      view_format: "html",
      free_count: 1,
      public_domain_count: 1,
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_boole_pub",
      owner_id: "tech-researcher",
      book_id: "pd-boole-laws-of-thought",
      content_hash: "b3",
      title: "An Investigation of the Laws of Thought",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_boole_pub"],
      view_format: "html",
      html: "<p>Laws of Thought calculus of logic</p>",
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "tech-researcher",
      documents: [],
      count: 0,
      view_format: "html",
      html: "",
    });
    render(<MarketplaceHost ownerId="tech-researcher" />);
    await waitFor(() => {
      expect(
        screen.getByTestId("catalog-entry-pd-boole-laws-of-thought"),
      ).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(screen.getByTestId("marketplace-host-pub-refs")).toBeTruthy();
    });
    const pubRefs = screen.getByTestId("marketplace-host-pub-refs");
    expect(pubRefs.getAttribute("data-offline-default")).toBe("true");
    expect(pubRefs.getAttribute("data-l1-l2-hydrate-prep")).toBe("true");
    // Residual (ahb): marketplace host DR knowledge-dense quick-call.
    expect(pubRefs.getAttribute("data-seamless-pub-quick-call")).toBe("true");
    expect(
      Number(pubRefs.getAttribute("data-knowledge-dense-presets") || 0),
    ).toBeGreaterThanOrEqual(4);
    expect(
      screen
        .getByTestId("marketplace-host-publication-quick-call")
        .getAttribute("data-auto-hydrate"),
    ).toBe("false");
    expect(
      screen
        .getByTestId("marketplace-host-hydrate-settings-link")
        .getAttribute("href"),
    ).toBe("/settings#hydrate-live-status");
    // Residual (xd): L1 arxiv checklist section deep-link.
    expect(
      screen
        .getByTestId("marketplace-host-hydrate-dual-gate-link")
        .getAttribute("href") || "",
    ).toMatch(/DUAL-GATE-L1-L4.*#l1-arxiv/);
    // Residual (aal): L2 Substack checklist section (parity Settings xr).
    expect(
      screen
        .getByTestId("marketplace-host-hydrate-dual-gate-l2-link")
        .getAttribute("href") || "",
    ).toMatch(/DUAL-GATE-L1-L4.*#l2-substack/);
    fireEvent.click(
      screen.getByTestId("marketplace-host-preset-attention-is-all-you-need"),
    );
    expect(
      (screen.getByTestId("marketplace-host-refs-input") as HTMLTextAreaElement)
        .value,
    ).toMatch(/arxiv:1706\.03762/);
    // Residual (ahm/aif): marketplace host DR budget foresight includes pub refs + chrome.
    const budgetMount = screen.getByTestId("marketplace-host-dr-budget-mount");
    expect(budgetMount.getAttribute("data-pub-ref-count")).toBe("1");
    expect(budgetMount.getAttribute("data-has-pub-refs")).toBe("true");
    expect(
      Number(budgetMount.getAttribute("data-prompt-chars") || 0),
    ).toBeGreaterThan(10);
    expect(
      screen.getByTestId("marketplace-host-pub-ref-foresight-chrome").textContent,
    ).toMatch(/1 ref/i);
    fireEvent.click(screen.getByTestId("marketplace-host-deep-research"));
    await waitFor(() => {
      expect(hydratePublicationRefs).toHaveBeenCalledWith(["arxiv:1706.03762"]);
    });
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "hdoc_boole_pub",
          references: ["arxiv:1706.03762"],
          view_mode: "floating",
        }),
      );
    });
    await waitFor(() => {
      expect(
        screen.getByTestId("marketplace-host-refs-status").textContent,
      ).toMatch(/Hydrated 1|HTML-first|offline-default/i);
    });
  });

  it("mounts collective panel on host land when open DR spawns exist (ani)", async () => {
    collectDeepResearchSpawnIds.mockReturnValue(["spn_mkt_1", "spn_mkt_2"]);
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
          subjects: ["literature"],
        },
      ],
      count: 1,
      view_format: "html",
      by_source: { standard_ebooks: 1 },
      public_domain_count: 1,
      purchased_count: 0,
      free_count: 1,
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_abc",
      owner_id: "operator",
      book_id: "pd-pride",
      content_hash: "x",
      title: "Pride and Prejudice",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_abc"],
      view_format: "html",
      html: "<p>It is a truth universally acknowledged</p>",
      usage_event: {
        task_class: "book_qa",
        outcome: "worked",
        source: "marketplace_host",
        prompt_hint: "host pd-pride · Pride and Prejudice",
      },
    });
    fetchAccountLibrary.mockResolvedValue({
      owner_id: "operator",
      documents: [
        {
          document_id: "hdoc_abc",
          title: "Pride",
          license_class: "public_domain",
          view_format: "html",
          is_free: true,
        },
      ],
      count: 1,
      free_count: 1,
      view_format: "html",
      html: "<p>Library</p>",
    });
    render(<MarketplaceHost ownerId="operator" />);
    await waitFor(() => {
      expect(screen.getByText("Pride and Prejudice")).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(screen.getByTestId("host-result")).toBeTruthy();
    });
    const mount = screen.getByTestId("marketplace-host-collective-mount");
    expect(mount.getAttribute("data-view-format")).toBe("html");
    expect(mount.getAttribute("data-document-id")).toBe("hdoc_abc");
    expect(mount.getAttribute("data-seamless-marketplace-collective")).toBe(
      "true",
    );
    expect(mount.getAttribute("data-available-spawn-count")).toBe("2");
    expect(screen.getByTestId("collective-research-panel-stub").textContent).toMatch(
      /hdoc_abc:spn_mkt_1,spn_mkt_2/,
    );
    expect(
      screen
        .getByTestId("collective-research-panel-stub")
        .getAttribute("data-has-merged"),
    ).toBe("1");
    // Collective merge remounts twins + context (parity alz promote path).
    await waitFor(() => {
      expect(seedTwinNotes).toHaveBeenCalled();
    });
    await waitFor(() => {
      const key = Number(
        screen
          .getByTestId("marketplace-host-twins-refresh")
          .getAttribute("data-refresh-key") || "0",
      );
      expect(key).toBeGreaterThanOrEqual(1);
    });
    const keyBeforeMerge = Number(
      screen
        .getByTestId("marketplace-host-twins-refresh")
        .getAttribute("data-refresh-key") || "0",
    );
    fireEvent.click(screen.getByTestId("marketplace-host-collective-merge-notify"));
    await waitFor(() => {
      expect(
        Number(
          screen
            .getByTestId("marketplace-host-twins-refresh")
            .getAttribute("data-refresh-key") || "0",
        ),
      ).toBe(keyBeforeMerge + 1);
    });
    expect(
      Number(
        screen
          .getByTestId("marketplace-host-context-mount")
          .getAttribute("data-refresh-key") || "0",
      ),
    ).toBe(keyBeforeMerge + 1);
  });

  it("omits collective panel on host land when no open spawns (ani)", async () => {
    collectDeepResearchSpawnIds.mockReturnValue([]);
    fetchMarketplaceCatalog.mockResolvedValue({
      entries: [
        {
          book_id: "pd-pride",
          title: "Pride and Prejudice",
          author: "Jane Austen",
          license_class: "public_domain",
          is_free: true,
          source: "standard_ebooks",
          subjects: ["literature"],
        },
      ],
      count: 1,
      view_format: "html",
      by_source: { standard_ebooks: 1 },
      public_domain_count: 1,
      purchased_count: 0,
      free_count: 1,
      payment_rails: "manual_receipt_only",
    });
    hostBookIntoAccount.mockResolvedValue({
      document_id: "hdoc_abc",
      owner_id: "operator",
      book_id: "pd-pride",
      content_hash: "x",
      title: "Pride and Prejudice",
      license_class: "public_domain",
      already_hosted: false,
      source_format: "html",
      library_document_ids: ["hdoc_abc"],
      view_format: "html",
      html: "<p>body</p>",
    });
    render(<MarketplaceHost ownerId="operator" />);
    await waitFor(() => {
      expect(screen.getByText("Pride and Prejudice")).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /host into account/i }));
    await waitFor(() => {
      expect(screen.getByTestId("host-result")).toBeTruthy();
    });
    expect(screen.queryByTestId("marketplace-host-collective-mount")).toBeNull();
  });
});
