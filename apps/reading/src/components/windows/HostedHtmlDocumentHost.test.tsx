import { describe, expect, it, vi, afterEach, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import HostedHtmlDocumentHost, {
  resolveHostedResearchSelection,
} from "./HostedHtmlDocumentHost";

const launchFloatingDeepResearch = vi.fn();
const hydratePublicationRefs = vi.fn();
const parsePublicationRefs = vi.fn((raw: string) =>
  raw
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean),
);
const collectDeepResearchSpawnIds = vi.fn(() => [] as string[]);
const listRecentDeepResearchSpawnIds = vi.fn(() => [] as string[]);

vi.mock("./windowHostContext", () => ({
  useInWindow: () => undefined,
}));

vi.mock("../../modes/Reading/launchFloatingDeepResearch", () => ({
  launchFloatingDeepResearch: (...args: unknown[]) =>
    launchFloatingDeepResearch(...args),
}));

vi.mock("../../modes/ResearchWorkstation/publicationRefs", () => ({
  parsePublicationRefs: (...args: unknown[]) =>
    parsePublicationRefs(...(args as [string])),
  hydratePublicationRefs: (...args: unknown[]) =>
    hydratePublicationRefs(...args),
}));

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

vi.mock("../engagement/CollectiveResearchPanel", () => ({
  CollectiveResearchPanel: (props: {
    availableSpawnIds: string[];
    parentAssetId?: string | null;
    recentSpawnIds?: readonly string[] | null;
    onDocMerged?: (r: { document_id: string }) => void;
    onRecentSpawnsCleared?: () => void;
  }) => (
    <div
      data-testid="collective-research-panel-stub"
      data-recent={
        props.recentSpawnIds != null ? props.recentSpawnIds.join(",") : ""
      }
      data-has-clear={props.onRecentSpawnsCleared ? "1" : "0"}
    >
      {props.parentAssetId}:{props.availableSpawnIds.join(",")}
      {props.onDocMerged ? (
        <button
          type="button"
          data-testid="collective-doc-merged-notify"
          onClick={() => props.onDocMerged?.({ document_id: "draft_eu" })}
        >
          notify
        </button>
      ) : null}
    </div>
  ),
}));

vi.mock("../engagement/TwinNotesPanel", () => ({
  TwinNotesPanel: (props: {
    assetId: string;
    researchTier?: string | null;
    seedTitle?: string | null;
    seedBodyText?: string | null;
    autoSeedIfEmpty?: boolean;
    domainSubjects?: readonly string[] | null;
  }) => (
    <div
      data-testid="twin-notes-panel-stub"
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
      data-seed-title={props.seedTitle || ""}
      data-seed-body={props.seedBodyText || ""}
      data-auto-seed={String(Boolean(props.autoSeedIfEmpty))}
      data-domain-subjects={(props.domainSubjects || []).join(",") || ""}
    >
      {props.assetId}
      {props.researchTier ? `:tier=${props.researchTier}` : ""}
    </div>
  ),
}));

vi.mock("../engagement/ResearchContextPanel", () => ({
  ResearchContextPanel: (props: {
    assetId: string;
    autoLoad?: boolean;
    domainSubjects?: readonly string[] | null;
    researchTier?: string | null;
  }) => (
    <div
      data-testid="research-context-panel-stub"
      data-domain-subjects={(props.domainSubjects || []).join(",") || ""}
      data-auto-load={String(Boolean(props.autoLoad))}
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
    >
      {props.assetId}:auto={String(Boolean(props.autoLoad))}
    </div>
  ),
}));

const fetchDepthTiers = vi.hoisted(() =>
  vi.fn(async () => ({
    active_depth_tier: null as string | null,
    active_preset: null,
    presets: [],
    projection_hints: null,
    view_format: "html" as const,
    settings_panel: "depth_tier_presets",
    source: "test",
    notes: [] as string[],
  })),
);

vi.mock("../../api/settings", () => ({
  fetchDepthTiers: (...args: unknown[]) => fetchDepthTiers(...args),
}));

vi.mock("../engagement/ResearchLaunchBudgetPanel", () => {
  const React = require("react") as typeof import("react");
  return {
    ResearchLaunchBudgetPanel: (props: {
      promptText: string;
      researchTier: string;
      allowTierPick?: boolean;
      onProjectionChange?: (p: {
        wouldExceedBudget: boolean | null;
        pricingKnown: boolean;
        estimatedUsdHigh: number | null;
        remainingUsd: number | null;
        modelId: string | null;
      }) => void;
    }) => {
      React.useEffect(() => {
        props.onProjectionChange?.({
          wouldExceedBudget: false,
          pricingKnown: true,
          estimatedUsdHigh: 0.1,
          remainingUsd: 5,
          modelId: null,
        });
      }, [props.onProjectionChange]);
      return (
        <div
          data-testid="research-launch-budget-panel-stub"
          data-research-tier={props.researchTier}
          data-prompt-len={String(props.promptText.length)}
          data-allow-tier-pick={props.allowTierPick ? "true" : "false"}
        >
          budget
        </div>
      );
    },
  };
});

vi.mock("../engagement/DecisionTreeDriverBadge", () => ({
  DecisionTreeDriverBadge: (props: {
    researchTier?: string | null;
    promptText?: string | null;
  }) => (
    <div
      data-testid="decision-tree-driver-badge-stub"
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
      data-prompt-len={String((props.promptText || "").length)}
    >
      driver
    </div>
  ),
}));

describe("HostedHtmlDocumentHost residual bt/bw/cv/da", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    launchFloatingDeepResearch.mockReset();
    hydratePublicationRefs.mockReset();
    collectDeepResearchSpawnIds.mockReset();
    collectDeepResearchSpawnIds.mockReturnValue([]);
    listRecentDeepResearchSpawnIds.mockReset();
    listRecentDeepResearchSpawnIds.mockReturnValue([]);
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
    hydratePublicationRefs.mockResolvedValue({
      ok: [{ handle: "arxiv:1706.03762", asset_id: "pub_1" }],
      failed: [],
    });
    parsePublicationRefs.mockImplementation((raw: string) =>
      raw
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
    );
  });

  it("renders HTML body for hosted book", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="doc_abc"
        title="Attention Is All You Need"
        view_format="html"
        license_class="public_domain"
        html="<article><h1>Attention</h1><p>Transformers.</p></article>"
      />,
    );
    expect(screen.getByTestId("hosted-html-document-host").getAttribute(
      "data-view-format",
    )).toBe("html");
    expect(screen.getByTestId("hosted-html-body").innerHTML).toMatch(
      /Attention/,
    );
    expect(screen.getByTestId("hosted-html-document-host").textContent).toMatch(
      /not PDF/,
    );
    // Residual (fl/qu/acn): Write dual handoff html_draft + twin_seed body honesty.
    const write = screen.getByTestId("hosted-html-open-write");
    const href = write.getAttribute("href") || "";
    expect(href).toMatch(/html_draft=doc_abc/);
    expect(href).toMatch(/twin_seed=antiek\.twin_write_seed\./);
    expect(write.getAttribute("data-has-twin-seed")).toBe("1");
    expect(write.getAttribute("data-write-seed-has-body")).toBe("true");
    // Residual (aen): seamless host→Write path on Open Write link.
    expect(write.getAttribute("data-document-id")).toBe("doc_abc");
    expect(write.getAttribute("data-seamless-host-write")).toBe("true");
  });

  it("stamps seamless host→Write path on marketplace_host Open Write (aen)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="hdoc_seamless"
        title="Hosted book seamless"
        view_format="html"
        source="marketplace_host"
        html="<p>Seamless host body</p>"
      />,
    );
    const write = screen.getByTestId("hosted-html-open-write");
    expect(write.getAttribute("data-document-id")).toBe("hdoc_seamless");
    expect(write.getAttribute("data-seamless-host-write")).toBe("true");
    expect(write.getAttribute("data-write-seed-source")).toBe("marketplace_host");
    expect(write.getAttribute("data-write-seed-has-body")).toBe("true");
  });

  it("stamps research_progress_complete host honesty (so)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="research_progress:spn_1:abc"
        title="Research progress · complete"
        view_format="html"
        source="research_progress_complete"
        html="<p>Final synthesis</p>"
      />,
    );
    const host = screen.getByTestId("hosted-html-document-host");
    expect(host.getAttribute("data-source")).toBe("research_progress_complete");
    expect(host.getAttribute("data-research-progress")).toBe("true");
    expect(screen.getByTestId("twin-notes-panel-stub").getAttribute("data-seed-title") || "").toMatch(
      /Research progress/,
    );
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute("data-write-seed-source"),
    ).toBe("research_progress_complete");
  });

  it("stamps spawn_merge Open Write source from auto-open float (aah)", () => {
    // Residual (aah): openMergedResearchWindow defaults to source=spawn_merge so
    // HostedHtml Open Write preserves Antiek-bench write-seed provenance.
    render(
      <HostedHtmlDocumentHost
        document_id="draft_spawn_merge_1"
        title="Merged research (draft_combined)"
        view_format="html"
        source="spawn_merge"
        html="<p>Spawn merge body</p>"
      />,
    );
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute(
        "data-write-seed-source",
      ),
    ).toBe("spawn_merge");
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute("title") || "",
    ).toMatch(/spawn merge/i);
    expect(
      screen.getByTestId("twin-notes-panel-stub").getAttribute("data-seed-title") ||
        "",
    ).toMatch(/Spawn merge/i);
  });

  it("stamps marketplace_host and midnight_oil_deposit Open Write sources (vv)", () => {
    const { unmount } = render(
      <HostedHtmlDocumentHost
        document_id="hdoc_mkt"
        title="Hosted book"
        view_format="html"
        source="marketplace_host"
        html="<p>Marketplace body</p>"
      />,
    );
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute(
        "data-write-seed-source",
      ),
    ).toBe("marketplace_host");
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute("title") || "",
    ).toMatch(/marketplace/i);
    unmount();

    render(
      <HostedHtmlDocumentHost
        document_id="draft_moil_1"
        title="MO deposit"
        view_format="html"
        source="midnight_oil_deposit"
        html="<p>Deposit body</p>"
      />,
    );
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute(
        "data-write-seed-source",
      ),
    ).toBe("midnight_oil_deposit");
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute("title") || "",
    ).toMatch(/Midnight Oil deposit/i);
  });

  it("stamps marketplace_host free twin seed path honesty (apk)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="hdoc_free_apk"
        title="Fourier free PD"
        view_format="html"
        source="marketplace_host"
        license_class="public_domain"
        is_free={true}
        html='<article><h1>Fourier</h1><p>Free PD body.</p></article>'
      />,
    );
    const host = screen.getByTestId("hosted-html-document-host");
    expect(host.getAttribute("data-marketplace-host")).toBe("true");
    expect(host.getAttribute("data-marketplace-path-kind")).toBe("free");
    expect(host.getAttribute("data-is-free")).toBe("true");
    const honesty = screen.getByTestId("hosted-html-marketplace-host-honesty");
    expect(honesty.getAttribute("data-path-kind")).toBe("free");
    expect(honesty.getAttribute("data-is-free")).toBe("true");
    expect(honesty.getAttribute("data-l5-live-payment")).toBe("deferred");
    expect(honesty.textContent).toMatch(/free\/public-domain path/i);
    expect(honesty.textContent).toMatch(/twin auto-seed if empty/i);
    expect(honesty.textContent).toMatch(/never invent entitlement/i);
    expect(
      screen
        .getByTestId("hosted-html-marketplace-host-l5-future-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-l5-digital-book-seamless-port/);
    expect(
      screen
        .getByTestId("hosted-html-marketplace-host-dual-gate-l5-link")
        .getAttribute("href") || "",
    ).toMatch(/#l5-payment/);
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-seed-title") || "").toMatch(
      /Marketplace host/,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /free\/public-domain HTML host/i,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /path_kind=free/,
    );
    expect(
      screen.getByTestId("hosted-html-twins-mount").getAttribute(
        "data-marketplace-path-kind",
      ),
    ).toBe("free");
  });

  it("stamps marketplace_host purchased twin seed path honesty (apk)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="hdoc_paid_apk"
        title="Purchased title"
        view_format="html"
        source="marketplace_host"
        is_free={false}
        html="<p>Purchased body after manual receipt.</p>"
      />,
    );
    const host = screen.getByTestId("hosted-html-document-host");
    expect(host.getAttribute("data-marketplace-path-kind")).toBe("purchased");
    expect(host.getAttribute("data-is-free")).toBe("false");
    const honesty = screen.getByTestId("hosted-html-marketplace-host-honesty");
    expect(honesty.getAttribute("data-path-kind")).toBe("purchased");
    expect(honesty.textContent).toMatch(/purchased path/i);
    expect(honesty.textContent).toMatch(/manual receipt/i);
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /purchased HTML host via manual receipt/i,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /L5 live payment deferred/i,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /path_kind=purchased/,
    );
  });

  it("stamps marketplace_library free path honesty for twin seed (apl)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="hdoc_lib_free_apl"
        title="Library free book"
        view_format="html"
        source="marketplace_library"
        is_free={true}
        license_class="public_domain"
        html="<p>Library-opened free PD body.</p>"
      />,
    );
    const host = screen.getByTestId("hosted-html-document-host");
    expect(host.getAttribute("data-source")).toBe("marketplace_library");
    expect(host.getAttribute("data-marketplace-host")).toBe("true");
    expect(host.getAttribute("data-marketplace-path-kind")).toBe("free");
    const honesty = screen.getByTestId("hosted-html-marketplace-host-honesty");
    expect(honesty.getAttribute("data-twin-seed-path")).toBe(
      "marketplace_library",
    );
    expect(honesty.getAttribute("data-path-kind")).toBe("free");
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-seed-title") || "").toMatch(
      /Marketplace host/,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /path_kind=free/,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /source=marketplace_library/,
    );
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute(
        "data-write-seed-source",
      ),
    ).toBe("marketplace_host");
  });

  it("stamps marketplace_library_rehydrate purchased path honesty (apl)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="hdoc_lib_paid_apl"
        title="Library purchased book"
        view_format="html"
        source="marketplace_library_rehydrate"
        is_free={false}
        html="<p>Rehydrated purchased body.</p>"
      />,
    );
    const host = screen.getByTestId("hosted-html-document-host");
    expect(host.getAttribute("data-source")).toBe(
      "marketplace_library_rehydrate",
    );
    expect(host.getAttribute("data-marketplace-path-kind")).toBe("purchased");
    const honesty = screen.getByTestId("hosted-html-marketplace-host-honesty");
    expect(honesty.getAttribute("data-twin-seed-path")).toBe(
      "marketplace_library_rehydrate",
    );
    expect(honesty.getAttribute("data-path-kind")).toBe("purchased");
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /path_kind=purchased/,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /source=marketplace_library_rehydrate/,
    );
  });

  it("stamps midnight_oil_deposit twin seed path honesty (apj)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="draft_moil_asset_apj"
        title="MO deposit · goals"
        view_format="html"
        source="midnight_oil_deposit"
        html='<article data-source="midnight_oil_deposit"><h1>Deposit</h1><p>Autonomous research result.</p></article>'
      />,
    );
    const host = screen.getByTestId("hosted-html-document-host");
    expect(host.getAttribute("data-source")).toBe("midnight_oil_deposit");
    expect(host.getAttribute("data-midnight-oil-deposit")).toBe("true");
    const honesty = screen.getByTestId("hosted-html-moil-deposit-honesty");
    expect(honesty.getAttribute("data-twin-seed-path")).toBe(
      "midnight_oil_deposit",
    );
    expect(honesty.getAttribute("data-auto-seed-if-empty")).toBe("true");
    expect(honesty.getAttribute("data-l4-live-step")).toBe("deferred");
    expect(honesty.getAttribute("data-html-first")).toBe("true");
    expect(honesty.textContent).toMatch(/Midnight Oil deposit/i);
    expect(honesty.textContent).toMatch(/twin auto-seed if empty/i);
    expect(honesty.textContent).toMatch(/L4 live step deferred/i);
    expect(honesty.textContent).toMatch(/never invent live worker/i);
    expect(
      screen
        .getByTestId("hosted-html-moil-deposit-scorecard-link")
        .getAttribute("href"),
    ).toBe("/settings#settings-competitive-dr-scorecard");
    expect(
      screen
        .getByTestId("hosted-html-moil-deposit-twin-matrix-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-twin-note-taker-completeness-matrix/);
    expect(
      screen
        .getByTestId("hosted-html-moil-deposit-dual-gate-l4-link")
        .getAttribute("href") || "",
    ).toMatch(/DUAL-GATE-L1-L4.*#l4-moil/);
    const twinsMount = screen.getByTestId("hosted-html-twins-mount");
    expect(twinsMount.getAttribute("data-midnight-oil-deposit")).toBe("true");
    expect(twinsMount.getAttribute("data-auto-seed-if-empty")).toBe("true");
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-auto-seed")).toBe("true");
    expect(twins.getAttribute("data-seed-title") || "").toMatch(
      /Midnight Oil deposit/,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /Port path: Midnight Oil deposit HTML float/i,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /document_id=draft_moil_asset_apj/,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /source=midnight_oil_deposit/,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /L4 deferred|never invent L4/i,
    );
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute(
        "data-write-seed-source",
      ),
    ).toBe("midnight_oil_deposit");
  });

  it("stamps marketplace_catalog twin seed path honesty (apm)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="marketplace-catalog-freepd_science_any-source"
        title="Marketplace catalog (HTML) · freepd_science"
        view_format="html"
        source="marketplace_catalog"
        html="<article><h1>Catalog</h1><p>Filter-aware free PD listing.</p></article>"
      />,
    );
    const host = screen.getByTestId("hosted-html-document-host");
    expect(host.getAttribute("data-source")).toBe("marketplace_catalog");
    expect(host.getAttribute("data-marketplace-catalog")).toBe("true");
    expect(host.getAttribute("data-marketplace-host")).toBe("false");
    const honesty = screen.getByTestId(
      "hosted-html-marketplace-catalog-honesty",
    );
    expect(honesty.getAttribute("data-twin-seed-path")).toBe(
      "marketplace_catalog",
    );
    expect(honesty.getAttribute("data-auto-seed-if-empty")).toBe("true");
    expect(honesty.getAttribute("data-l5-live-payment")).toBe("deferred");
    expect(honesty.textContent).toMatch(/filter-aware HTML listing/i);
    expect(honesty.textContent).toMatch(/not a hosted book/i);
    expect(honesty.textContent).toMatch(/never invent host entitlement/i);
    expect(
      screen
        .getByTestId("hosted-html-marketplace-catalog-l5-future-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-l5-digital-book-seamless-port/);
    const twinsMount = screen.getByTestId("hosted-html-twins-mount");
    expect(twinsMount.getAttribute("data-marketplace-catalog")).toBe("true");
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-seed-title") || "").toMatch(
      /Marketplace catalog/,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /Port path: marketplace catalog HTML projection/i,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /source=marketplace_catalog/,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /not a hosted book/i,
    );
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute(
        "data-write-seed-source",
      ),
    ).toBe("marketplace_catalog");
  });

  it("stamps marketplace_catalog Open Write source (aaj)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="marketplace-catalog-freepd_science_any-source"
        title="Marketplace catalog (HTML) · freepd_science"
        view_format="html"
        source="marketplace_catalog"
        html="<article><p>By subject: science=3</p></article>"
      />,
    );
    expect(
      screen.getByTestId("hosted-html-document-host").getAttribute("data-source"),
    ).toBe("marketplace_catalog");
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute(
        "data-write-seed-source",
      ),
    ).toBe("marketplace_catalog");
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute("title") || "",
    ).toMatch(/marketplace catalog/i);
    expect(
      screen.getByTestId("twin-notes-panel-stub").getAttribute("data-seed-title") ||
        "",
    ).toMatch(/Marketplace catalog/i);
  });

  it("maps marketplace_library* window sources to marketplace_host Open Write (aai)", () => {
    // Residual (aai): library open / rehydrate floats must not collapse Write
    // seed provenance away from the marketplace_host Antiek-bench feed.
    const { unmount } = render(
      <HostedHtmlDocumentHost
        document_id="hdoc_lib"
        title="Library book"
        view_format="html"
        source="marketplace_library"
        html="<p>Library body</p>"
      />,
    );
    expect(
      screen.getByTestId("hosted-html-document-host").getAttribute("data-source"),
    ).toBe("marketplace_library");
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute(
        "data-write-seed-source",
      ),
    ).toBe("marketplace_host");
    expect(
      screen.getByTestId("twin-notes-panel-stub").getAttribute("data-seed-title") ||
        "",
    ).toMatch(/Marketplace host/i);
    unmount();

    render(
      <HostedHtmlDocumentHost
        document_id="hdoc_rehydrate"
        title="Rehydrated book"
        view_format="html"
        source="marketplace_library_rehydrate"
        html="<p>Rehydrate body</p>"
      />,
    );
    expect(
      screen.getByTestId("hosted-html-document-host").getAttribute("data-source"),
    ).toBe("marketplace_library_rehydrate");
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute(
        "data-write-seed-source",
      ),
    ).toBe("marketplace_host");
  });

  it("stamps collective_written_analysis Open Write source (vn)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="analysis:col_1"
        title="Written analysis · 3 spawns"
        view_format="html"
        source="collective_written_analysis"
        html='<article data-source="collective_written_analysis"><h1>Analysis</h1></article>'
      />,
    );
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute(
        "data-write-seed-source",
      ),
    ).toBe("collective_written_analysis");
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute("title") || "",
    ).toMatch(/written analysis/i);
    expect(
      screen.getByTestId("twin-notes-panel-stub").getAttribute("data-seed-title") ||
        "",
    ).toMatch(/Collective written analysis/i);
  });

  it("stamps twin_cross_asset_merge Open Write source (vg)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="twin_draft_a_b"
        title="Twin draft · a+b"
        view_format="html"
        source="twin_cross_asset_merge"
        html='<article data-source="twin_cross_asset_merge"><h1>Cross</h1></article>'
      />,
    );
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute(
        "data-write-seed-source",
      ),
    ).toBe("twin_cross_asset_merge");
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute("title") || "",
    ).toMatch(/cross-asset merge/i);
    // Residual (vi): twin notes offline-seed title for cross-asset merge floats.
    expect(
      screen.getByTestId("twin-notes-panel-stub").getAttribute("data-seed-title") ||
        "",
    ).toMatch(/Twin cross-asset merge/i);
  });

  it("stamps collective_unit_prompt honesty (ts)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="collective_unit:col_abc:xyz"
        title="Collective unit · col_abc"
        view_format="html"
        source="collective_unit_prompt"
        collective_id="col_abc"
        spawn_count={3}
        html='<article data-source="collective_unit_prompt"><h1>Collective</h1></article>'
      />,
    );
    const host = screen.getByTestId("hosted-html-document-host");
    expect(host.getAttribute("data-source")).toBe("collective_unit_prompt");
    expect(host.getAttribute("data-collective-unit-prompt")).toBe("true");
    expect(host.getAttribute("data-collective-id")).toBe("col_abc");
    expect(host.getAttribute("data-spawn-count")).toBe("3");
    const honesty = screen.getByTestId("hosted-html-collective-unit-honesty");
    expect(honesty.getAttribute("data-collective-id")).toBe("col_abc");
    expect(honesty.getAttribute("data-spawn-count")).toBe("3");
    expect(honesty.textContent).toMatch(/Collective cohesive unit/i);
    expect(honesty.textContent).toMatch(/spawns=3/);
    expect(honesty.textContent).toMatch(/no invented server doc/i);
    expect(
      screen.getByTestId("twin-notes-panel-stub").getAttribute("data-seed-title") ||
        "",
    ).toMatch(/Collective cohesive unit/);
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute(
        "data-write-seed-source",
      ),
    ).toBe("collective_unit_prompt");
    // Residual (tu): Open Write title honesty for multi-spawn cohesive unit.
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute("title") || "",
    ).toMatch(/collective cohesive unit/i);
    // Residual (aiz): twin seed path honesty + completeness matrix deep-links.
    expect(honesty.getAttribute("data-twin-seed-path")).toBe(
      "collective_unit_prompt",
    );
    expect(honesty.getAttribute("data-auto-seed-if-empty")).toBe("true");
    expect(honesty.textContent).toMatch(/twin auto-seed if empty/i);
    expect(
      screen
        .getByTestId("hosted-html-collective-unit-scorecard-link")
        .getAttribute("href"),
    ).toBe("/settings#settings-competitive-dr-scorecard");
    expect(
      screen
        .getByTestId("hosted-html-collective-unit-twin-matrix-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-twin-note-taker-completeness-matrix/);
    const twinsMount = screen.getByTestId("hosted-html-twins-mount");
    expect(twinsMount.getAttribute("data-collective-unit-prompt")).toBe("true");
    expect(twinsMount.getAttribute("data-auto-seed-if-empty")).toBe("true");
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-auto-seed")).toBe("true");
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /Port path: Collective cohesive unit/i,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /collective_id=col_abc/,
    );
  });

  it("stamps context_search query + hit count honesty (tq)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="context_search:paper:abc"
        title="Context search · attention"
        view_format="html"
        source="context_search"
        search_query="attention"
        search_hit_count={3}
        html="<p>Query: attention · hits=3</p>"
      />,
    );
    const host = screen.getByTestId("hosted-html-document-host");
    expect(host.getAttribute("data-source")).toBe("context_search");
    expect(host.getAttribute("data-context-search")).toBe("true");
    expect(host.getAttribute("data-search-query")).toBe("attention");
    expect(host.getAttribute("data-search-hit-count")).toBe("3");
    const honesty = screen.getByTestId("hosted-html-context-search-honesty");
    expect(honesty.getAttribute("data-search-query")).toBe("attention");
    expect(honesty.getAttribute("data-search-hit-count")).toBe("3");
    expect(honesty.textContent).toMatch(/Intelligent search/i);
    expect(honesty.textContent).toMatch(/attention/);
    expect(honesty.textContent).toMatch(/hits=3/);
    expect(honesty.textContent).toMatch(/not PDF/i);
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-seed-title") || "").toMatch(
      /Context search/,
    );
    expect(twins.getAttribute("data-seed-title") || "").toMatch(/attention/);
    expect(
      screen.getByTestId("hosted-html-open-write").getAttribute(
        "data-write-seed-source",
      ),
    ).toBe("context_search");
  });

  it("stamps evidence_pack source and twin seed title (sh/si)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="evidence:paper:abc"
        title="Evidence pack (citation trust)"
        view_format="html"
        source="evidence_pack"
        html="<p>Evidence pack · Insight: routing.</p>"
      />,
    );
    const host = screen.getByTestId("hosted-html-document-host");
    expect(host.getAttribute("data-source")).toBe("evidence_pack");
    expect(host.getAttribute("data-evidence-pack")).toBe("true");
    const twinsMount = screen.getByTestId("hosted-html-twins-mount");
    expect(twinsMount.getAttribute("data-evidence-pack")).toBe("true");
    expect(twinsMount.getAttribute("data-auto-seed-if-empty")).toBe("true");
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-auto-seed")).toBe("true");
    expect(twins.getAttribute("data-seed-title") || "").toMatch(
      /Evidence pack \(citation trust\)/,
    );
    // Residual (si): Open Write dual handoff stamps evidence_pack seed source.
    const write = screen.getByTestId("hosted-html-open-write");
    expect(write.getAttribute("data-write-seed-source")).toBe("evidence_pack");
    const href = write.getAttribute("href") || "";
    expect(href).toMatch(/twin_seed=antiek\.twin_write_seed\./);
  });

  it("passes free STEM catalog subjects into ResearchContext domainSubjects (ajf)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="marketplace:pd-fourier-heat"
        title="Fourier Heat"
        view_format="html"
        source="marketplace_host"
        subjects={["heat", "signal_processing", "engineering"]}
        html="<p>Analytical Theory of Heat</p>"
      />,
    );
    const mount = screen.getByTestId("hosted-html-context-mount");
    expect(mount.getAttribute("data-has-domain-subjects")).toBe("true");
    expect(mount.getAttribute("data-domain-subjects")).toMatch(/heat/);
    // Residual (alo): domain-search coverage honesty on reading host mount.
    expect(mount.getAttribute("data-domain-search-has-default")).toBe("true");
    expect(mount.getAttribute("data-domain-search-covered")).toMatch(/heat/);
    expect(
      Number(mount.getAttribute("data-domain-search-covered-count")),
    ).toBeGreaterThanOrEqual(1);
    // Residual (alt): twin note-taker receives domainSubjects for coverage.
    expect(
      screen
        .getByTestId("twin-notes-panel-stub")
        .getAttribute("data-domain-subjects") || "",
    ).toMatch(/heat/);
    expect(mount.getAttribute("data-domain-subjects")).toMatch(
      /signal_processing/,
    );
    const ctx = screen.getByTestId("research-context-panel-stub");
    expect(ctx.getAttribute("data-domain-subjects")).toBe(
      "heat,signal_processing,engineering",
    );
    expect(ctx.getAttribute("data-auto-load")).toBe("true");
  });

  it("passes host researchTier into ResearchContext prefill (amk)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="marketplace:pd-fourier-heat"
        title="Fourier Heat"
        view_format="html"
        source="marketplace_host"
        subjects={["heat"]}
        research_tier="wrestle"
        html="<p>Analytical Theory of Heat</p>"
      />,
    );
    const ctx = screen.getByTestId("research-context-panel-stub");
    expect(ctx.getAttribute("data-research-tier")).toBe("wrestle");
    expect(ctx.getAttribute("data-domain-subjects")).toMatch(/heat/);
  });

  it("surfaces multi-hop hop honesty and scorecard links for evidence_pack (aiw)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="evidence:paper:hops"
        title="Evidence pack multi-hop"
        view_format="html"
        source="evidence_pack"
        html={
          "<p>chain_complete=true</p>" +
          "<p>Citation chain hops: Insights (claims)(1) → Source references(1)</p>" +
          "<p>[evidence-insight-0] Insight: routing</p>" +
          "<p>[evidence-source-0] Source: arxiv</p>"
        }
      />,
    );
    const host = screen.getByTestId("hosted-html-document-host");
    expect(host.getAttribute("data-evidence-pack")).toBe("true");
    expect(host.getAttribute("data-evidence-chain-complete")).toBe("true");
    expect(host.getAttribute("data-evidence-has-hop-strip")).toBe("true");
    // Residual (apo): hop strip implies hop pipeline territory on float.
    expect(host.getAttribute("data-evidence-has-hop-pipeline")).toBe("true");
    const honesty = screen.getByTestId("hosted-html-evidence-pack-honesty");
    expect(honesty.getAttribute("data-chain-complete")).toBe("true");
    expect(honesty.getAttribute("data-has-hop-strip")).toBe("true");
    expect(honesty.getAttribute("data-has-hop-pipeline")).toBe("true");
    expect(honesty.textContent).toMatch(/chain_complete=true/i);
    expect(honesty.textContent).toMatch(/multi-hop hop strip present/i);
    expect(honesty.textContent).toMatch(
      /citation hop pipeline \(insights → questions → sources\)/i,
    );
    expect(
      screen
        .getByTestId("hosted-html-evidence-scorecard-link")
        .getAttribute("href"),
    ).toBe("/settings#settings-competitive-dr-scorecard");
    expect(
      screen
        .getByTestId("hosted-html-evidence-future-agent-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-competitive-deep-research-quality/);
  });

  it("stamps collective_written_analysis twin seed path honesty (app)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="draft_analysis_app"
        title="Written analysis"
        view_format="html"
        source="collective_written_analysis"
        collective_id="col_app"
        spawn_count={3}
        html="<article><h1>Analysis</h1><p>Multi-agent synthesis.</p></article>"
      />,
    );
    const host = screen.getByTestId("hosted-html-document-host");
    expect(host.getAttribute("data-source")).toBe(
      "collective_written_analysis",
    );
    expect(host.getAttribute("data-collective-written-analysis")).toBe("true");
    const honesty = screen.getByTestId(
      "hosted-html-collective-analysis-honesty",
    );
    expect(honesty.getAttribute("data-twin-seed-path")).toBe(
      "collective_written_analysis",
    );
    expect(honesty.getAttribute("data-l6-live-council")).toBe("deferred");
    expect(honesty.textContent).toMatch(/multi-agent/i);
    expect(honesty.textContent).toMatch(/L6 live council deferred/i);
    expect(
      screen
        .getByTestId("hosted-html-collective-analysis-l6-future-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-l6-live-multiagent-collective/);
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-seed-title") || "").toMatch(
      /Collective written analysis/,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /Port path: Collective multi-agent written analysis/i,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /spawn_count=3/,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /source=collective_written_analysis/,
    );
  });

  it("stamps research_context_pack twin seed path honesty (apq)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="context:paper:apq"
        title="Research context pack"
        view_format="html"
        source="research_context_pack"
        html="<article><h1>Context</h1><p>Prompt block substrate.</p></article>"
      />,
    );
    const host = screen.getByTestId("hosted-html-document-host");
    expect(host.getAttribute("data-source")).toBe("research_context_pack");
    expect(host.getAttribute("data-research-context-pack")).toBe("true");
    const honesty = screen.getByTestId(
      "hosted-html-research-context-pack-honesty",
    );
    expect(honesty.getAttribute("data-twin-seed-path")).toBe(
      "research_context_pack",
    );
    expect(honesty.textContent).toMatch(/prompt_block substrate/i);
    expect(honesty.textContent).toMatch(/next deep-research turn/i);
    expect(honesty.textContent).toMatch(/L3 live twin seed deferred/i);
    expect(
      screen
        .getByTestId("hosted-html-research-context-pack-twin-matrix-link")
        .getAttribute("href") || "",
    ).toMatch(/FUTURE-AGENT-SPEC-twin-note-taker-completeness-matrix/);
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-seed-title") || "").toMatch(
      /Research context pack/,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /Port path: Research context pack float/i,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /source=research_context_pack/,
    );
  });

  it("stamps spawn_merge twin seed path honesty (app)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="draft_spawn_merge_app"
        title="Spawn merge"
        view_format="html"
        source="spawn_merge"
        html="<article><h1>Merged spawn</h1></article>"
      />,
    );
    const host = screen.getByTestId("hosted-html-document-host");
    expect(host.getAttribute("data-spawn-merge")).toBe("true");
    const honesty = screen.getByTestId("hosted-html-spawn-merge-honesty");
    expect(honesty.getAttribute("data-twin-seed-path")).toBe("spawn_merge");
    expect(honesty.textContent).toMatch(/single-spawn/i);
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /Port path: Spawn merge float/i,
    );
    expect(twins.getAttribute("data-seed-body") || "").toMatch(
      /source=spawn_merge/,
    );
  });

  it("stamps evidence hop pipeline completeness from Competitive citation hops HTML (apo)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="evidence:paper:hop-pipe"
        title="Evidence pack hop pipeline"
        view_format="html"
        source="evidence_pack"
        html={
          '<div data-testid="evidence-citation-hop-pipeline">' +
          "Competitive citation hops · 2/3 · missing=questions · never invent sources" +
          "</div>" +
          "<p>[evidence-insight-0] Insight</p>" +
          "<p>[evidence-source-0] Source</p>"
        }
      />,
    );
    const host = screen.getByTestId("hosted-html-document-host");
    expect(host.getAttribute("data-evidence-has-hop-pipeline")).toBe("true");
    const honesty = screen.getByTestId("hosted-html-evidence-pack-honesty");
    expect(honesty.getAttribute("data-has-hop-pipeline")).toBe("true");
    expect(honesty.textContent).toMatch(/citation hop pipeline/i);
    expect(honesty.textContent).toMatch(/questions hop may be missing/i);
  });

  it("prefills research tier from Settings wrestle (jd)", async () => {
    fetchDepthTiers.mockResolvedValue({
      active_depth_tier: "wrestle",
      active_preset: null,
      presets: [],
      projection_hints: null,
      view_format: "html",
      settings_panel: "depth_tier_presets",
      source: "test",
      notes: [],
    });
    render(
      <HostedHtmlDocumentHost
        document_id="doc_wrestle"
        title="Origin"
        view_format="html"
        html="<p>Species</p>"
      />,
    );
    await waitFor(() => {
      const mount = screen.getByTestId("hosted-html-dr-depth-mount");
      expect(mount.getAttribute("data-depth-prefill")).toBe("installed");
      expect(mount.getAttribute("data-research-tier")).toBe("wrestle");
    });
    expect(
      screen.getByTestId("hosted-html-dr-depth-prefill").textContent,
    ).toMatch(/installed.*wrestle/i);
    expect(
      screen
        .getByTestId("research-launch-budget-panel-stub")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
  });

  it("mounts twin notes + research context for document_id (bw/cv)", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="hdoc_xyz"
        title="Pride"
        view_format="html"
        html="<p>It is a truth</p>"
      />,
    );
    expect(screen.getByTestId("hosted-html-twins-mount")).toBeTruthy();
    expect(screen.getByTestId("twin-notes-panel-stub").textContent).toMatch(
      /hdoc_xyz/,
    );
    // Residual (ks): hosted twins inherit researchTier (default deep).
    expect(
      screen.getByTestId("twin-notes-panel-stub").getAttribute("data-research-tier"),
    ).toBe("deep");
    expect(screen.getByTestId("hosted-html-context-mount")).toBeTruthy();
    expect(screen.getByTestId("research-context-panel-stub").textContent).toMatch(
      /hdoc_xyz:auto=true/,
    );
  });

  it("mounts driver badge + budget + deep research launch (da)", async () => {
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "fsess_h",
      spawn_id: "spn_h",
      investigation_id: "inv_h",
      parent_asset_id: "doc_host",
      window_id: "wdr_host_1",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
      model_id: "claude-opus-4-8",
    });

    render(
      <HostedHtmlDocumentHost
        document_id="doc_host"
        title="Hosted Book"
        view_format="html"
        html="<p>Body</p>"
      />,
    );

    expect(screen.getByTestId("decision-tree-driver-badge-stub")).toBeTruthy();
    // Residual (pj): whole-document selection feeds badge prompt projection.
    expect(
      Number(
        screen
          .getByTestId("decision-tree-driver-badge-stub")
          .getAttribute("data-prompt-len") || 0,
      ),
    ).toBeGreaterThan(0);
    const launch = screen.getByTestId("hosted-html-research-launch");
    expect(launch.getAttribute("data-view-format")).toBe("html");
    await waitFor(() => {
      expect(fetchDepthTiers).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(
        screen
          .getByTestId("hosted-html-dr-depth-mount")
          .getAttribute("data-depth-prefill"),
      ).toBe("none");
    });
    const budget = screen.getByTestId("research-launch-budget-panel-stub");
    expect(budget.getAttribute("data-research-tier")).toBe("deep");
    // Residual (gn): depth-tier picker enabled on hosted book DR.
    expect(budget.getAttribute("data-allow-tier-pick")).toBe("true");
    expect(Number(budget.getAttribute("data-prompt-len"))).toBeGreaterThan(3);

    fireEvent.click(screen.getByTestId("hosted-html-deep-research"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "doc_host",
          view_mode: "floating",
        }),
      );
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      selection_text: string;
      goal_hint: string;
    };
    expect(call.selection_text).toMatch(/Hosted Book/);
    expect(call.goal_hint).toMatch(/Hosted Book/);
    expect(call.goal_hint).not.toMatch(/research_domains=/);
    await waitFor(() => {
      expect(
        screen.getByTestId("hosted-html-research-window-id").textContent,
      ).toMatch(/wdr_host_1/);
    });
  });

  it("appends research_domains to float DR goal_hint when subjects present (aod)", async () => {
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "fsess_domain",
      spawn_id: "spn_domain",
      investigation_id: "inv_domain",
      parent_asset_id: "doc_fourier",
      window_id: "wdr_domain",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
      model_id: null,
    });
    render(
      <HostedHtmlDocumentHost
        document_id="doc_fourier"
        title="Analytical Theory of Heat"
        view_format="html"
        html="<p>Heat conduction equations.</p>"
        subjects={["Heat", "signal_processing", "heat"]}
      />,
    );
    const launch = screen.getByTestId("hosted-html-research-launch");
    expect(launch.getAttribute("data-research-domains")).toBe(
      "heat,signal_processing",
    );
    // Residual (aoq): deep research buttons stamp domain-aware foresight.
    expect(
      screen
        .getByTestId("hosted-html-deep-research")
        .getAttribute("data-domain-aware-dr"),
    ).toBe("true");
    expect(
      screen
        .getByTestId("hosted-html-deep-research")
        .getAttribute("data-research-domains"),
    ).toBe("heat,signal_processing");
    expect(
      screen.getByTestId("hosted-html-deep-research").getAttribute("title") ||
        "",
    ).toMatch(/research_domains=heat,signal_processing/);
    fireEvent.click(screen.getByTestId("hosted-html-deep-research"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "doc_fourier",
          goal_hint: expect.stringMatching(
            /research_domains=heat,signal_processing/,
          ),
        }),
      );
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      goal_hint: string;
    };
    expect(call.goal_hint).toMatch(/Analytical Theory of Heat/);
    // Domain tags lower-cased + deduped (title may still contain Heat).
    expect(call.goal_hint).toMatch(
      /research_domains=heat,signal_processing/,
    );
    expect(call.goal_hint).not.toMatch(/research_domains=Heat/);
  });

  it("rejects non-html view_format", () => {
    render(
      <HostedHtmlDocumentHost
        document_id="doc_x"
        view_format="pdf"
        html="%PDF-1.4"
      />,
    );
    expect(screen.getByTestId("hosted-html-reject-pdf")).toBeTruthy();
    expect(screen.queryByTestId("hosted-html-research-launch")).toBeNull();
  });

  it("resolveHostedResearchSelection prefers highlight (en)", () => {
    const hit = resolveHostedResearchSelection({
      title: "Book",
      assetId: "doc_1",
      fallbackDocId: "doc_1",
      highlightText: "  attention is all you need  ",
    });
    expect(hit.from_highlight).toBe(true);
    expect(hit.selection_text).toBe("attention is all you need");
    const miss = resolveHostedResearchSelection({
      title: "Book",
      assetId: "doc_1",
      fallbackDocId: "doc_1",
      highlightText: "   ",
    });
    expect(miss.from_highlight).toBe(false);
    expect(miss.selection_text).toMatch(/Deep-research hosted document: Book/);
  });

  it("uses window selection for deep research when highlighted (en)", async () => {
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "fsess_sel",
      spawn_id: "spn_sel",
      investigation_id: "inv_sel",
      parent_asset_id: "doc_sel",
      window_id: "wdr_sel",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
      model_id: null,
    });
    const getSelection = vi.fn(() => ({
      toString: () => "Transformers changed NLP forever",
    }));
    vi.stubGlobal("getSelection", getSelection);

    render(
      <HostedHtmlDocumentHost
        document_id="doc_sel"
        title="Attention"
        view_format="html"
        html="<p>Transformers changed NLP forever in 2017.</p>"
      />,
    );

    expect(
      screen.getByTestId("hosted-html-research-launch").getAttribute(
        "data-from-highlight",
      ),
    ).toBe("false");

    fireEvent.mouseUp(screen.getByTestId("hosted-html-body"));
    await waitFor(() => {
      expect(
        screen.getByTestId("hosted-html-selection-preview").getAttribute(
          "data-from-highlight",
        ),
      ).toBe("true");
    });
    expect(screen.getByTestId("hosted-html-selection-text").textContent).toMatch(
      /Transformers changed NLP forever/,
    );

    fireEvent.click(screen.getByTestId("hosted-html-deep-research"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "doc_sel",
          selection_text: "Transformers changed NLP forever",
          view_mode: "floating",
        }),
      );
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      goal_hint: string;
    };
    expect(call.goal_hint).toMatch(/highlighted passage/i);

    fireEvent.click(screen.getByTestId("hosted-html-clear-highlight"));
    await waitFor(() => {
      expect(
        screen.getByTestId("hosted-html-selection-preview").getAttribute(
          "data-from-highlight",
        ),
      ).toBe("false");
    });

    vi.unstubAllGlobals();
  });

  it("mounts collective panel when open DR spawns exist (eu)", () => {
    collectDeepResearchSpawnIds.mockReturnValue(["spn_a", "spn_b"]);
    render(
      <HostedHtmlDocumentHost
        document_id="doc_col"
        title="Book"
        view_format="html"
        html="<p>Body</p>"
      />,
    );
    const mount = screen.getByTestId("hosted-html-collective-mount");
    expect(mount.getAttribute("data-available-spawn-count")).toBe("2");
    expect(screen.getByTestId("collective-research-panel-stub").textContent).toMatch(
      /doc_col:spn_a,spn_b/,
    );
    // Residual (eu/ep/ez): onDocMerged remounts context + twins.
    const beforeCtx = screen
      .getByTestId("hosted-html-context-refresh")
      .getAttribute("data-refresh-key");
    const beforeTwins = screen
      .getByTestId("hosted-html-twins-refresh")
      .getAttribute("data-refresh-key");
    fireEvent.click(screen.getByTestId("collective-doc-merged-notify"));
    expect(
      screen.getByTestId("hosted-html-context-refresh").getAttribute(
        "data-refresh-key",
      ),
    ).not.toBe(beforeCtx);
    expect(
      screen.getByTestId("hosted-html-twins-refresh").getAttribute(
        "data-refresh-key",
      ),
    ).not.toBe(beforeTwins);
  });

  it("wires recent_ring into collect + collective mount (ov)", () => {
    listRecentDeepResearchSpawnIds.mockReturnValue([
      "spn_chased_closed",
      "spn_older",
    ]);
    collectDeepResearchSpawnIds.mockImplementation(
      (source: { recentSpawnIds?: readonly string[] | null }) =>
        [...(source.recentSpawnIds ?? [])],
    );
    render(
      <HostedHtmlDocumentHost
        document_id="doc_recent"
        title="Book"
        view_format="html"
        html="<p>Body</p>"
      />,
    );
    expect(collectDeepResearchSpawnIds).toHaveBeenCalled();
    const lastCall = collectDeepResearchSpawnIds.mock.calls.at(-1)?.[0] as {
      recentSpawnIds?: readonly string[];
    };
    expect(lastCall.recentSpawnIds).toEqual([
      "spn_chased_closed",
      "spn_older",
    ]);
    const mount = screen.getByTestId("hosted-html-collective-mount");
    expect(mount.getAttribute("data-recent-count")).toBe("2");
    expect(mount.getAttribute("data-available-spawn-count")).toBe("2");
    const stub = screen.getByTestId("collective-research-panel-stub");
    expect(stub.getAttribute("data-recent")).toBe(
      "spn_chased_closed,spn_older",
    );
    expect(stub.getAttribute("data-has-clear")).toBe("1");
    expect(stub.textContent).toMatch(
      /doc_recent:spn_chased_closed,spn_older/,
    );
  });

  it("omits collective panel when no open spawns", () => {
    collectDeepResearchSpawnIds.mockReturnValue([]);
    render(
      <HostedHtmlDocumentHost
        document_id="doc_none"
        title="Book"
        view_format="html"
        html="<p>Body</p>"
      />,
    );
    expect(screen.queryByTestId("hosted-html-collective-mount")).toBeNull();
  });

  it("launches deep research in full window mode (es)", async () => {
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "fsess_full",
      spawn_id: "spn_full",
      investigation_id: "inv_full",
      parent_asset_id: "doc_full",
      window_id: "wdr_full",
      view_format: "html",
      view_mode: "full",
      status: "reserved",
      model_id: null,
    });
    render(
      <HostedHtmlDocumentHost
        document_id="doc_full"
        title="Full"
        view_format="html"
        html="<p>Body</p>"
      />,
    );
    fireEvent.click(screen.getByTestId("hosted-html-deep-research-full"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "doc_full",
          view_mode: "full",
        }),
      );
    });
    await waitFor(() => {
      expect(
        screen.getByTestId("hosted-html-research-window-id").textContent,
      ).toMatch(/wdr_full/);
    });
  });

  it("hydrates optional pub refs and passes references on launch (er)", async () => {
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "fsess_pub",
      spawn_id: "spn_pub",
      investigation_id: "inv_pub",
      parent_asset_id: "doc_pub",
      window_id: "wdr_pub",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
      model_id: null,
    });
    render(
      <HostedHtmlDocumentHost
        document_id="doc_pub"
        title="Hosted"
        view_format="html"
        html="<p>Body</p>"
      />,
    );
    const pubRefs = screen.getByTestId("hosted-html-pub-refs");
    expect(pubRefs).toBeTruthy();
    // Residual (uj): L1/L2 hydrate prep honesty + deep-links.
    expect(pubRefs.getAttribute("data-offline-default")).toBe("true");
    expect(pubRefs.getAttribute("data-l1-l2-hydrate-prep")).toBe("true");
    // Residual (aha): knowledge-dense quick-call on hosted book DR path.
    expect(pubRefs.getAttribute("data-seamless-pub-quick-call")).toBe("true");
    expect(
      Number(pubRefs.getAttribute("data-knowledge-dense-presets") || 0),
    ).toBeGreaterThanOrEqual(4);
    expect(
      screen
        .getByTestId("hosted-html-publication-quick-call")
        .getAttribute("data-auto-hydrate"),
    ).toBe("false");
    expect(
      screen.getByTestId("hosted-html-hydrate-settings-link").getAttribute("href"),
    ).toBe("/settings#hydrate-live-status");
    // Residual (xd): L1 arxiv checklist section deep-link.
    expect(
      screen
        .getByTestId("hosted-html-hydrate-dual-gate-link")
        .getAttribute("href") || "",
    ).toMatch(/DUAL-GATE-L1-L4.*#l1-arxiv/);
    // Residual (aam): L2 Substack checklist (parity marketplace aal).
    expect(
      screen
        .getByTestId("hosted-html-hydrate-dual-gate-l2-link")
        .getAttribute("href") || "",
    ).toMatch(/DUAL-GATE-L1-L4.*#l2-substack/);
    fireEvent.click(
      screen.getByTestId("hosted-html-preset-attention-is-all-you-need"),
    );
    expect(
      (screen.getByTestId("hosted-html-refs-input") as HTMLTextAreaElement)
        .value,
    ).toMatch(/arxiv:1706\.03762/);
    // Residual (ahl/aif): hosted book DR budget foresight pub-ref count + chrome.
    const depthMount = screen.getByTestId("hosted-html-dr-depth-mount");
    expect(depthMount.getAttribute("data-pub-ref-count")).toBe("1");
    expect(depthMount.getAttribute("data-has-pub-refs")).toBe("true");
    expect(
      Number(depthMount.getAttribute("data-prompt-chars") || 0),
    ).toBeGreaterThan(10);
    expect(
      screen.getByTestId("hosted-html-pub-ref-foresight-chrome").textContent,
    ).toMatch(/1 ref/i);
    fireEvent.click(screen.getByTestId("hosted-html-deep-research"));
    await waitFor(() => {
      expect(hydratePublicationRefs).toHaveBeenCalledWith(["arxiv:1706.03762"]);
    });
    await waitFor(() => {
      expect(screen.getByTestId("hosted-html-refs-status").textContent).toMatch(
        /Hydrated 1|HTML-first/,
      );
    });
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "doc_pub",
          references: ["arxiv:1706.03762"],
          view_mode: "floating",
        }),
      );
    });
  });
});
