import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import ResearchThis from "./ResearchThis";

const launchFloatingDeepResearch = vi.fn();
const spinResearch = vi.fn();
const navigate = vi.fn();
const hydratePublicationRefs = vi.fn();
const parsePublicationRefs = vi.fn();
const collectDeepResearchSpawnIds = vi.fn(() => [] as string[]);
const listRecentDeepResearchSpawnIds = vi.fn(() => [] as string[]);

const fetchDepthTiers = vi.hoisted(() =>
  vi.fn(async () => ({
    active_depth_tier: null as string | null,
    active_preset: null,
    tiers: [],
  })),
);

vi.mock("./launchFloatingDeepResearch", () => ({
  launchFloatingDeepResearch: (...args: unknown[]) =>
    launchFloatingDeepResearch(...args),
}));

vi.mock("../ResearchWorkstation/publicationRefs", () => ({
  parsePublicationRefs: (...args: unknown[]) => parsePublicationRefs(...args),
  hydratePublicationRefs: (...args: unknown[]) => hydratePublicationRefs(...args),
  questionWithPublicationRefs: (q: string) => q,
}));

vi.mock("../../api/books", () => ({
  spinResearch: (...args: unknown[]) => spinResearch(...args),
}));

vi.mock("../../api/settings", () => ({
  fetchDepthTiers: (...args: unknown[]) => fetchDepthTiers(...args),
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

vi.mock("../../components/engagement/CollectiveResearchPanel", () => ({
  CollectiveResearchPanel: (props: {
    availableSpawnIds: string[];
    parentAssetId?: string | null;
    recentSpawnIds?: readonly string[] | null;
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
    </div>
  ),
}));

vi.mock("../../components/engagement/TwinNotesPanel", () => ({
  TwinNotesPanel: (props: {
    assetId: string;
    autoLoad?: boolean;
    autoSeedIfEmpty?: boolean;
    seedBodyText?: string;
    researchTier?: string | null;
  }) => (
    <div
      data-testid="twin-notes-panel-stub"
      data-asset-id={props.assetId}
      data-auto-load={String(Boolean(props.autoLoad))}
      data-auto-seed={String(Boolean(props.autoSeedIfEmpty))}
      data-body-len={String((props.seedBodyText || "").length)}
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
    >
      twins={props.assetId}
    </div>
  ),
}));

vi.mock("../../components/engagement/ResearchContextPanel", () => ({
  ResearchContextPanel: (props: {
    assetId: string;
    autoLoad?: boolean;
    researchTier?: string | null;
  }) => (
    <div
      data-testid="research-context-panel-stub"
      data-asset-id={props.assetId}
      data-auto-load={String(Boolean(props.autoLoad))}
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
    >
      context={props.assetId}
    </div>
  ),
}));

vi.mock("../../components/engagement/DecisionTreeDriverBadge", () => ({
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

vi.mock("../../components/engagement/ResearchLaunchBudgetPanel", () => {
  // Lazy require React inside factory so vitest mock is isolated.
  const React = require("react") as typeof import("react");
  return {
    ResearchLaunchBudgetPanel: (props: {
      promptText: string;
      researchTier: string;
      onResearchTierChange?: (t: string) => void;
      onProjectionChange?: (p: {
        wouldExceedBudget: boolean | null;
        pricingKnown: boolean;
        estimatedUsdHigh: number | null;
        remainingUsd: number | null;
        modelId: string | null;
      }) => void;
    }) => {
      // Residual (de): notify after mount — never during render.
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
          data-prompt-len={String(props.promptText.length)}
          data-research-tier={props.researchTier}
        >
          budget stub
        </div>
      );
    },
  };
});

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => navigate,
  };
});

vi.mock("../../lib/analytics", () => ({
  track: vi.fn(),
}));

describe("ResearchThis residual cc/cu/cx/jg", () => {
  beforeEach(() => {
    launchFloatingDeepResearch.mockReset();
    spinResearch.mockReset();
    navigate.mockReset();
    hydratePublicationRefs.mockReset();
    parsePublicationRefs.mockReset();
    parsePublicationRefs.mockReturnValue([]);
    collectDeepResearchSpawnIds.mockReset();
    collectDeepResearchSpawnIds.mockReturnValue([]);
    listRecentDeepResearchSpawnIds.mockReset();
    listRecentDeepResearchSpawnIds.mockReturnValue([]);
    fetchDepthTiers.mockReset().mockResolvedValue({
      active_depth_tier: null,
      active_preset: null,
      tiers: [],
    });
  });

  afterEach(() => cleanup());

  it("mounts DecisionTreeDriverBadge with researchTier (ll)", async () => {
    render(
      <MemoryRouter>
        <ResearchThis documentId="doc-1" pageIndex={0} passageText="sel" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("research-this-driver-badge-mount")).toBeTruthy();
    });
    expect(
      screen
        .getByTestId("research-this-driver-badge-mount")
        .getAttribute("data-research-tier"),
    ).toBe("deep");
    expect(
      screen
        .getByTestId("decision-tree-driver-badge-stub")
        .getAttribute("data-research-tier"),
    ).toBe("deep");
    // Residual (pi): selection passage feeds badge prompt projection.
    expect(
      Number(
        screen
          .getByTestId("decision-tree-driver-badge-stub")
          .getAttribute("data-prompt-len") || 0,
      ),
    ).toBeGreaterThan(0);
  });

  it("mounts budget projection panel before float open (cx)", async () => {
    render(
      <MemoryRouter>
        <ResearchThis
          documentId="doc-1"
          pageIndex={0}
          passageText="Attention is content-addressable memory."
        />
      </MemoryRouter>,
    );
    const mount = screen.getByTestId("research-this-budget-mount");
    expect(mount).toBeTruthy();
    expect(mount.getAttribute("data-view-format")).toBe("html");
    await waitFor(() => {
      expect(mount.getAttribute("data-depth-prefill")).toBe("none");
    });
    const stub = screen.getByTestId("research-launch-budget-panel-stub");
    expect(stub.getAttribute("data-research-tier")).toBe("deep");
    expect(Number(stub.getAttribute("data-prompt-len"))).toBeGreaterThan(3);
  });

  it("prefills research tier from Settings wrestle depth (jg)", async () => {
    fetchDepthTiers.mockResolvedValue({
      active_depth_tier: "wrestle",
      active_preset: null,
      tiers: [],
    });
    render(
      <MemoryRouter>
        <ResearchThis
          documentId="doc-1"
          pageIndex={0}
          passageText="Wrestle this claim in the passage."
        />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(fetchDepthTiers).toHaveBeenCalled();
    });
    const mount = screen.getByTestId("research-this-budget-mount");
    await waitFor(() => {
      expect(mount.getAttribute("data-depth-prefill")).toBe("installed");
    });
    expect(mount.getAttribute("data-research-tier")).toBe("wrestle");
    expect(
      screen.getByTestId("research-launch-budget-panel-stub").getAttribute(
        "data-research-tier",
      ),
    ).toBe("wrestle");
    expect(screen.getByTestId("research-this-depth-prefill").textContent).toMatch(
      /installed.*wrestle/,
    );
  });

  it("forwards research_tier on floating launch (ji)", async () => {
    fetchDepthTiers.mockResolvedValue({
      active_depth_tier: "wrestle",
      active_preset: null,
      tiers: [],
    });
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "fsess_tier",
      spawn_id: "spn_tier",
      investigation_id: "inv_tier",
      parent_asset_id: "doc-1",
      window_id: "wdr_tier",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
      research_tier: "wrestle",
    });
    render(
      <MemoryRouter>
        <ResearchThis
          documentId="doc-1"
          pageIndex={0}
          passageText="Pass tier to spawn reservation."
        />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(
        screen.getByTestId("research-this-budget-mount").getAttribute(
          "data-depth-prefill",
        ),
      ).toBe("installed");
    });
    fireEvent.click(screen.getByTestId("research-this-floating"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          research_tier: "wrestle",
          view_mode: "floating",
        }),
      );
    });
  });

  it("opens floating deep research window from passage", async () => {
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "fsess_1",
      spawn_id: "spn_1",
      investigation_id: "inv_1",
      parent_asset_id: "doc-1",
      window_id: "wdr_fsess_1",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
    });

    render(
      <MemoryRouter>
        <ResearchThis
          documentId="doc-1"
          pageIndex={0}
          passageText="Attention is content-addressable memory."
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId("research-this-floating"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalled();
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      asset_id: string;
      selection_text: string;
      view_mode: string;
    };
    expect(call.asset_id).toBe("doc-1");
    expect(call.selection_text).toMatch(/Attention/);
    expect(call.view_mode).toBe("floating");
    await waitFor(() => {
      expect(screen.getByTestId("research-this-window-id").textContent).toMatch(
        /wdr_fsess_1/,
      );
    });
  });

  it("hydrates pub refs and passes references to floating launch (cu)", async () => {
    parsePublicationRefs.mockReturnValue(["arxiv:1706.03762"]);
    hydratePublicationRefs.mockResolvedValue({
      ok: [{ asset_id: "pub_1", view_format: "html" }],
      failed: [],
      view_format: "html",
    });
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "fsess_2",
      spawn_id: "spn_2",
      investigation_id: "inv_2",
      parent_asset_id: "doc-1",
      window_id: "wdr_fsess_2",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
    });

    render(
      <MemoryRouter>
        <ResearchThis documentId="doc-1" pageIndex={0} passageText="hello world" />
      </MemoryRouter>,
    );
    const pubRefs = screen.getByTestId("research-this-pub-refs");
    expect(pubRefs).toBeTruthy();
    // Residual (uk): L1/L2 hydrate prep honesty + deep-links (parity uj).
    expect(pubRefs.getAttribute("data-offline-default")).toBe("true");
    expect(pubRefs.getAttribute("data-l1-l2-hydrate-prep")).toBe("true");
    // Residual (ahc): highlight DR knowledge-dense quick-call.
    expect(pubRefs.getAttribute("data-seamless-pub-quick-call")).toBe("true");
    expect(
      Number(pubRefs.getAttribute("data-knowledge-dense-presets") || 0),
    ).toBeGreaterThanOrEqual(4);
    expect(
      screen
        .getByTestId("research-this-publication-quick-call")
        .getAttribute("data-auto-hydrate"),
    ).toBe("false");
    expect(
      screen
        .getByTestId("research-this-hydrate-settings-link")
        .getAttribute("href"),
    ).toBe("/settings#hydrate-live-status");
    // Residual (xd): L1 arxiv checklist section deep-link.
    expect(
      screen
        .getByTestId("research-this-hydrate-dual-gate-link")
        .getAttribute("href") || "",
    ).toMatch(/DUAL-GATE-L1-L4.*#l1-arxiv/);
    // Residual (aao): L2 Substack checklist (parity aal–aan).
    expect(
      screen
        .getByTestId("research-this-hydrate-dual-gate-l2-link")
        .getAttribute("href") || "",
    ).toMatch(/DUAL-GATE-L1-L4.*#l2-substack/);
    fireEvent.click(
      screen.getByTestId("research-this-preset-attention-is-all-you-need"),
    );
    expect(
      (screen.getByTestId("research-this-refs-input") as HTMLTextAreaElement)
        .value,
    ).toMatch(/arxiv:1706\.03762/);
    // Residual (ahi/aie): budget foresight pub-ref count + chrome after quick-call.
    const budgetMount = screen.getByTestId("research-this-budget-mount");
    expect(budgetMount.getAttribute("data-pub-ref-count")).toBe("1");
    expect(budgetMount.getAttribute("data-has-pub-refs")).toBe("true");
    expect(
      Number(budgetMount.getAttribute("data-prompt-chars") || 0),
    ).toBeGreaterThan(10);
    expect(
      screen.getByTestId("research-this-pub-ref-foresight-chrome").textContent,
    ).toMatch(/1 ref/i);
    fireEvent.click(screen.getByTestId("research-this-floating"));
    await waitFor(() => {
      expect(hydratePublicationRefs).toHaveBeenCalledWith(["arxiv:1706.03762"]);
    });
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          references: ["arxiv:1706.03762"],
          view_mode: "floating",
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("research-this-refs-status").textContent).toMatch(
        /Hydrated 1/,
      );
    });
  });

  it("mounts collective panel when open DR spawns exist (fc)", () => {
    collectDeepResearchSpawnIds.mockReturnValue(["spn_r1", "spn_r2"]);
    render(
      <MemoryRouter>
        <ResearchThis documentId="doc-read" pageIndex={0} passageText="hi" />
      </MemoryRouter>,
    );
    const mount = screen.getByTestId("research-this-collective-mount");
    expect(mount.getAttribute("data-available-spawn-count")).toBe("2");
    expect(screen.getByTestId("collective-research-panel-stub").textContent).toMatch(
      /doc-read:spn_r1,spn_r2/,
    );
  });

  it("wires recent_ring into collect + collective mount (ou)", () => {
    listRecentDeepResearchSpawnIds.mockReturnValue([
      "spn_chased_closed",
      "spn_older",
    ]);
    collectDeepResearchSpawnIds.mockImplementation(
      (source: { recentSpawnIds?: readonly string[] | null }) =>
        [...(source.recentSpawnIds ?? [])],
    );
    render(
      <MemoryRouter>
        <ResearchThis documentId="doc-recent" pageIndex={0} passageText="hi" />
      </MemoryRouter>,
    );
    expect(collectDeepResearchSpawnIds).toHaveBeenCalled();
    const lastCall = collectDeepResearchSpawnIds.mock.calls.at(-1)?.[0] as {
      recentSpawnIds?: readonly string[];
    };
    expect(lastCall.recentSpawnIds).toEqual([
      "spn_chased_closed",
      "spn_older",
    ]);
    const mount = screen.getByTestId("research-this-collective-mount");
    expect(mount.getAttribute("data-recent-count")).toBe("2");
    expect(mount.getAttribute("data-available-spawn-count")).toBe("2");
    const stub = screen.getByTestId("collective-research-panel-stub");
    expect(stub.getAttribute("data-recent")).toBe(
      "spn_chased_closed,spn_older",
    );
    expect(stub.getAttribute("data-has-clear")).toBe("1");
    expect(stub.textContent).toMatch(
      /doc-recent:spn_chased_closed,spn_older/,
    );
  });

  it("omits collective panel when no open spawns", () => {
    collectDeepResearchSpawnIds.mockReturnValue([]);
    render(
      <MemoryRouter>
        <ResearchThis documentId="doc-read" pageIndex={0} passageText="hi" />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("research-this-collective-mount")).toBeNull();
  });

  it("opens full working-region deep research window (et)", async () => {
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "fsess_full",
      spawn_id: "spn_full",
      investigation_id: "inv_w",
      parent_asset_id: "doc-1",
      window_id: "wdr_full",
      view_format: "html",
      view_mode: "full",
      status: "reserved",
    });
    render(
      <MemoryRouter>
        <ResearchThis
          documentId="doc-1"
          pageIndex={0}
          passageText="Full window highlight"
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("research-this-deep-full"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "doc-1",
          view_mode: "full",
          selection_text: expect.stringMatching(/Full window/),
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("research-this-window-id").textContent).toMatch(
        /wdr_full/,
      );
    });
    // Legacy full-page handoff remains separate.
    expect(screen.getByTestId("research-this-full")).toBeTruthy();
  });

  it("full workstation path still navigates via spinResearch", async () => {
    spinResearch.mockResolvedValue({ investigation_id: "inv_full" });
    render(
      <MemoryRouter>
        <ResearchThis documentId="doc-1" pageIndex={0} passageText="hello world" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(
        screen.getByTestId("research-this-budget-mount").getAttribute(
          "data-depth-prefill",
        ),
      ).toBe("none");
    });
    fireEvent.click(screen.getByTestId("research-this-full"));
    await waitFor(() => {
      // Residual (jm): opts.researchTier defaults to deep when Settings unset.
      expect(spinResearch).toHaveBeenCalledWith("doc-1", 0, "hello world", {
        researchTier: "deep",
      });
    });
    expect(navigate).toHaveBeenCalledWith("/inv/inv_full");
  });

  it("full workstation spin forwards Settings wrestle research_tier (jm)", async () => {
    fetchDepthTiers.mockResolvedValue({
      active_depth_tier: "wrestle",
      active_preset: null,
      tiers: [],
    });
    spinResearch.mockResolvedValue({ investigation_id: "inv_wrestle" });
    render(
      <MemoryRouter>
        <ResearchThis
          documentId="doc-1"
          pageIndex={0}
          passageText="Wrestle full workstation"
        />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(
        screen.getByTestId("research-this-budget-mount").getAttribute(
          "data-depth-prefill",
        ),
      ).toBe("installed");
    });
    fireEvent.click(screen.getByTestId("research-this-full"));
    await waitFor(() => {
      expect(spinResearch).toHaveBeenCalledWith(
        "doc-1",
        0,
        "Wrestle full workstation",
        { researchTier: "wrestle" },
      );
    });
    expect(navigate).toHaveBeenCalledWith("/inv/inv_wrestle");
  });

  it("mounts TwinNotes recursive note-taker for the book asset (agq)", async () => {
    render(
      <MemoryRouter>
        <ResearchThis
          documentId="doc-twins"
          pageIndex={2}
          passageText="Selection for twin seed body"
        />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("research-this-twins-mount")).toBeTruthy();
    });
    const mount = screen.getByTestId("research-this-twins-mount");
    expect(mount.getAttribute("data-view-format")).toBe("html");
    expect(mount.getAttribute("data-document-id")).toBe("doc-twins");
    expect(mount.getAttribute("data-seamless-research-this-twins")).toBe(
      "true",
    );
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-asset-id")).toBe("doc-twins");
    expect(twins.getAttribute("data-auto-load")).toBe("true");
    expect(twins.getAttribute("data-auto-seed")).toBe("true");
    // Residual (amr): ResearchContext with depth prefill on highlight DR path.
    const ctxMount = screen.getByTestId("research-this-context-mount");
    expect(ctxMount.getAttribute("data-document-id")).toBe("doc-twins");
    expect(ctxMount.getAttribute("data-seamless-research-this-context")).toBe(
      "true",
    );
    expect(ctxMount.getAttribute("data-research-tier")).toMatch(
      /deep|fast|wrestle/,
    );
    const ctx = screen.getByTestId("research-context-panel-stub");
    expect(ctx.getAttribute("data-asset-id")).toBe("doc-twins");
    expect(ctx.getAttribute("data-auto-load")).toBe("true");
    expect(ctx.getAttribute("data-research-tier")).toMatch(/deep|fast|wrestle/);
    expect(Number(twins.getAttribute("data-body-len") || 0)).toBeGreaterThan(0);
  });
});
