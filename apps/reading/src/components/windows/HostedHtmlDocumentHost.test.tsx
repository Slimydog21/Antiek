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

vi.mock("../../workspace/windowsStore", () => ({
  useWindows: (sel: (s: { windows: Record<string, unknown> }) => unknown) =>
    sel({ windows: {} }),
}));

vi.mock("../engagement/CollectiveResearchPanel", () => ({
  CollectiveResearchPanel: (props: {
    availableSpawnIds: string[];
    parentAssetId?: string | null;
    onDocMerged?: (r: { document_id: string }) => void;
  }) => (
    <div data-testid="collective-research-panel-stub">
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
  }) => (
    <div
      data-testid="twin-notes-panel-stub"
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
    >
      {props.assetId}
      {props.researchTier ? `:tier=${props.researchTier}` : ""}
    </div>
  ),
}));

vi.mock("../engagement/ResearchContextPanel", () => ({
  ResearchContextPanel: (props: { assetId: string; autoLoad?: boolean }) => (
    <div data-testid="research-context-panel-stub">
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
  DecisionTreeDriverBadge: () => (
    <div data-testid="decision-tree-driver-badge-stub">driver</div>
  ),
}));

describe("HostedHtmlDocumentHost residual bt/bw/cv/da", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    launchFloatingDeepResearch.mockReset();
    hydratePublicationRefs.mockReset();
    collectDeepResearchSpawnIds.mockReset();
    collectDeepResearchSpawnIds.mockReturnValue([]);
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
    // Residual (fl): Write handoff for HTML draft.
    const write = screen.getByTestId("hosted-html-open-write");
    expect(write.getAttribute("href")).toBe("/write?html_draft=doc_abc");
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
    await waitFor(() => {
      expect(
        screen.getByTestId("hosted-html-research-window-id").textContent,
      ).toMatch(/wdr_host_1/);
    });
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
    expect(screen.getByTestId("hosted-html-pub-refs")).toBeTruthy();
    fireEvent.change(screen.getByTestId("hosted-html-refs-input"), {
      target: { value: "arxiv:1706.03762" },
    });
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
