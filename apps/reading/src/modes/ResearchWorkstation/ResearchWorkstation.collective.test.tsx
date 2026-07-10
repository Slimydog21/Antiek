/**
 * Residual (afr): ResearchWorkstation /inv/:id mounts CollectiveResearchPanel
 * when open or recent deep_research_session spawns exist (parity ResearchThis).
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const useInvestigationMock = vi.fn();
const collectDeepResearchSpawnIdsMock = vi.fn(() => [] as string[]);
const listRecentDeepResearchSpawnIdsMock = vi.fn(() => [] as string[]);
const windowsState = { windows: {} as Record<string, unknown> };

vi.mock("../../hooks/useInvestigation", () => ({
  useInvestigation: (id: string) => useInvestigationMock(id),
}));

vi.mock("../../workspace/collectDeepResearchSpawnIds", () => ({
  collectDeepResearchSpawnIds: (...args: unknown[]) =>
    collectDeepResearchSpawnIdsMock(...args),
}));

vi.mock("../../workspace/recentDeepResearchSpawns", () => ({
  listRecentDeepResearchSpawnIds: () => listRecentDeepResearchSpawnIdsMock(),
}));

vi.mock("../../workspace/windowsStore", () => ({
  useWindows: (sel: (s: { windows: Record<string, unknown> }) => unknown) =>
    sel(windowsState),
}));

vi.mock("../../workspace/WorkspaceStore", () => ({
  useWorkspace: (sel: (s: { open: () => void }) => unknown) =>
    sel({ open: vi.fn() }),
}));

vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="panel-host-stub">{children}</div>
  ),
}));

vi.mock("../../shell/GlassSurface", () => ({
  default: ({
    children,
    className,
  }: {
    children?: React.ReactNode;
    className?: string;
  }) => (
    <div data-testid="glass-surface-stub" className={className}>
      {children}
    </div>
  ),
}));

vi.mock("../../components/engagement/CollectiveResearchPanel", () => ({
  CollectiveResearchPanel: (props: {
    availableSpawnIds: readonly string[];
    parentAssetId?: string | null;
    openSpawnIds?: readonly string[] | null;
    recentSpawnIds?: readonly string[] | null;
  }) => (
    <div
      data-testid="collective-research-panel-stub"
      data-parent={props.parentAssetId ?? ""}
      data-spawns={props.availableSpawnIds.join(",")}
      data-has-open-spawn-ids={props.openSpawnIds != null ? "1" : "0"}
      data-open-spawns={
        props.openSpawnIds != null ? props.openSpawnIds.join(",") : ""
      }
      data-recent-spawns={
        props.recentSpawnIds != null ? props.recentSpawnIds.join(",") : ""
      }
    >
      parent={props.parentAssetId}:spawns={props.availableSpawnIds.join(",")}
    </div>
  ),
}));

vi.mock("../../components/engagement/TwinNotesPanel", () => ({
  TwinNotesPanel: (props: {
    assetId: string;
    autoLoad?: boolean;
    autoSeedIfEmpty?: boolean;
    autoPromoteAfterLoad?: boolean;
    seedTitle?: string;
    researchTier?: string | null;
  }) => (
    <div
      data-testid="twin-notes-panel-stub"
      data-asset-id={props.assetId}
      data-auto-load={String(Boolean(props.autoLoad))}
      data-auto-seed={String(Boolean(props.autoSeedIfEmpty))}
      data-auto-promote={String(Boolean(props.autoPromoteAfterLoad))}
      data-seed-title={props.seedTitle ?? ""}
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

const fetchDepthTiers = vi.hoisted(() =>
  vi.fn(async () => ({
    active_depth_tier: "wrestle" as string | null,
    active_preset: null,
    presets: [],
    view_format: "html" as const,
  })),
);

vi.mock("../../api/settings", () => ({
  fetchDepthTiers: (...args: unknown[]) => fetchDepthTiers(...args),
}));

vi.mock("./HighlightToolbar", () => ({
  default: () => <div data-testid="highlight-toolbar-stub" />,
}));

vi.mock("./ThinkingStream", () => ({
  default: () => <div data-testid="thinking-stream-stub" />,
}));

vi.mock("./NotesPanel", () => ({
  default: () => <div data-testid="notes-panel-stub" />,
}));

vi.mock("./StartResearch", () => ({
  default: () => <div data-testid="start-research-stub" />,
}));

import ResearchWorkstation from "./index";

afterEach(() => {
  cleanup();
  useInvestigationMock.mockReset();
  collectDeepResearchSpawnIdsMock.mockReset();
  collectDeepResearchSpawnIdsMock.mockReturnValue([]);
  listRecentDeepResearchSpawnIdsMock.mockReset();
  listRecentDeepResearchSpawnIdsMock.mockReturnValue([]);
  windowsState.windows = {};
  fetchDepthTiers.mockReset().mockResolvedValue({
    active_depth_tier: "wrestle",
    active_preset: null,
    presets: [],
    view_format: "html",
  });
});

function mountInv(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/inv/${id}`]}>
      <Routes>
        <Route path="/inv/:investigationId" element={<ResearchWorkstation />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ResearchWorkstation collective multi-select (afr)", () => {
  it("mounts CollectiveResearchPanel when DR spawns exist", () => {
    useInvestigationMock.mockReturnValue({
      id: "inv_afr",
      status: "in_progress",
      question: "Q",
      events: [],
      terminalPayload: null,
      costTotal: 0,
      completedAt: null,
      streamStatus: "open",
      reconnects: 0,
    });
    collectDeepResearchSpawnIdsMock.mockReturnValue(["spn_a", "spn_b"]);
    listRecentDeepResearchSpawnIdsMock.mockReturnValue(["spn_b"]);

    mountInv("inv_afr");

    const mount = screen.getByTestId("research-workstation-collective-mount");
    expect(mount.getAttribute("data-view-format")).toBe("html");
    expect(mount.getAttribute("data-available-spawn-count")).toBe("2");
    expect(mount.getAttribute("data-investigation-id")).toBe("inv_afr");
    expect(mount.getAttribute("data-seamless-workstation-collective")).toBe(
      "true",
    );
    const panel = screen.getByTestId("collective-research-panel-stub");
    expect(panel.getAttribute("data-parent")).toBe("inv_afr");
    expect(panel.getAttribute("data-spawns")).toBe("spn_a,spn_b");
    expect(panel.getAttribute("data-has-open-spawn-ids")).toBe("1");
    expect(panel.textContent).toMatch(/parent=inv_afr:spawns=spn_a,spn_b/);
  });

  it("always mounts TwinNotesPanel recursive note-taker (afs)", () => {
    useInvestigationMock.mockReturnValue({
      id: "inv_afs",
      status: "in_progress",
      question: "What is attention?",
      events: [],
      terminalPayload: null,
      costTotal: 0,
      completedAt: null,
      streamStatus: "open",
      reconnects: 0,
    });
    collectDeepResearchSpawnIdsMock.mockReturnValue([]);

    mountInv("inv_afs");

    const mount = screen.getByTestId("research-workstation-twins-mount");
    expect(mount.getAttribute("data-view-format")).toBe("html");
    expect(mount.getAttribute("data-investigation-id")).toBe("inv_afs");
    expect(mount.getAttribute("data-seamless-workstation-twins")).toBe("true");
    const twins = screen.getByTestId("twin-notes-panel-stub");
    expect(twins.getAttribute("data-asset-id")).toBe("inv_afs");
    expect(twins.getAttribute("data-auto-load")).toBe("true");
    expect(twins.getAttribute("data-auto-seed")).toBe("true");
    expect(twins.getAttribute("data-seed-title")).toBe("What is attention?");
    // Residual (aft): auto-promote into research context after load.
    expect(twins.getAttribute("data-auto-promote")).toBe("true");
  });

  it("prefills investigation twins and context researchTier from Settings (amn)", async () => {
    fetchDepthTiers.mockResolvedValue({
      active_depth_tier: "wrestle",
      active_preset: null,
      presets: [],
      view_format: "html",
    });
    useInvestigationMock.mockReturnValue({
      id: "inv_amn",
      status: "in_progress",
      question: "Depth prefill?",
      events: [],
      terminalPayload: null,
      costTotal: 0,
      completedAt: null,
      streamStatus: "open",
      reconnects: 0,
    });
    collectDeepResearchSpawnIdsMock.mockReturnValue([]);

    mountInv("inv_amn");

    await waitFor(() => {
      expect(
        screen
          .getByTestId("research-workstation-twins-mount")
          .getAttribute("data-research-tier"),
      ).toBe("wrestle");
    });
    // Residual (amx): context mount stamps Settings depth honesty.
    expect(
      screen
        .getByTestId("research-workstation-context-mount")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
    expect(
      screen
        .getByTestId("research-workstation-context-mount")
        .getAttribute("data-seamless-workstation-depth"),
    ).toBe("true");
    expect(
      screen.getByTestId("twin-notes-panel-stub").getAttribute("data-research-tier"),
    ).toBe("wrestle");
    expect(
      screen
        .getByTestId("research-context-panel-stub")
        .getAttribute("data-research-tier"),
    ).toBe("wrestle");
  });

  it("mounts ResearchContextPanel with remount key (aft)", () => {
    useInvestigationMock.mockReturnValue({
      id: "inv_aft",
      status: "in_progress",
      question: "Context pack?",
      events: [],
      terminalPayload: null,
      costTotal: 0,
      completedAt: null,
      streamStatus: "open",
      reconnects: 0,
    });
    collectDeepResearchSpawnIdsMock.mockReturnValue([]);

    mountInv("inv_aft");

    const mount = screen.getByTestId("research-workstation-context-mount");
    expect(mount.getAttribute("data-view-format")).toBe("html");
    expect(mount.getAttribute("data-investigation-id")).toBe("inv_aft");
    expect(mount.getAttribute("data-seamless-workstation-context")).toBe(
      "true",
    );
    const refresh = screen.getByTestId("research-workstation-context-refresh");
    expect(refresh.getAttribute("data-refresh-key")).toBe("0");
    const ctx = screen.getByTestId("research-context-panel-stub");
    expect(ctx.getAttribute("data-asset-id")).toBe("inv_aft");
    expect(ctx.getAttribute("data-auto-load")).toBe("true");
    const twinsRefresh = screen.getByTestId(
      "research-workstation-twins-refresh",
    );
    expect(twinsRefresh.getAttribute("data-refresh-key")).toBe("0");
  });

  it("mounts dual-gate L3/L6 checklist prep deep-links (age)", () => {
    useInvestigationMock.mockReturnValue({
      id: "inv_age",
      status: "in_progress",
      question: "Dual-gate?",
      events: [],
      terminalPayload: null,
      costTotal: 0,
      completedAt: null,
      streamStatus: "open",
      reconnects: 0,
    });
    collectDeepResearchSpawnIdsMock.mockReturnValue([]);

    mountInv("inv_age");

    const prep = screen.getByTestId("research-workstation-dual-gate-prep");
    expect(prep.getAttribute("data-view-format")).toBe("html");
    expect(prep.getAttribute("data-l3-twin-seed")).toBe("deferred");
    expect(prep.getAttribute("data-l6-live-multiagent")).toBe("deferred");
    const l3 = screen.getByTestId("research-workstation-l3-checklist-link");
    expect(l3.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4.*#l3-twin/);
    expect(l3.getAttribute("data-l3-twin-seed")).toBe("deferred");
    const l6 = screen.getByTestId("research-workstation-l6-checklist-link");
    expect(l6.getAttribute("href")).toMatch(/DUAL-GATE-L1-L4.*#l6-collective/);
    expect(l6.getAttribute("data-l6-live-multiagent")).toBe("deferred");
  });

  it("omits collective mount when no spawn ids available", () => {
    useInvestigationMock.mockReturnValue({
      id: "inv_empty",
      status: "in_progress",
      question: "Q",
      events: [],
      terminalPayload: null,
      costTotal: 0,
      completedAt: null,
      streamStatus: "open",
      reconnects: 0,
    });
    collectDeepResearchSpawnIdsMock.mockReturnValue([]);

    mountInv("inv_empty");

    expect(
      screen.queryByTestId("research-workstation-collective-mount"),
    ).toBeNull();
    expect(
      screen.queryByTestId("collective-research-panel-stub"),
    ).toBeNull();
    // Residual (afs): twins still present without DR spawns.
    expect(screen.getByTestId("research-workstation-twins-mount")).toBeTruthy();
  });

  it("wires open + recent into collectDeepResearchSpawnIds (afr)", () => {
    useInvestigationMock.mockReturnValue({
      id: "inv_wire",
      status: "in_progress",
      question: "Q",
      events: [],
      terminalPayload: null,
      costTotal: 0,
      completedAt: null,
      streamStatus: "open",
      reconnects: 0,
    });
    listRecentDeepResearchSpawnIdsMock.mockReturnValue(["spn_recent"]);
    collectDeepResearchSpawnIdsMock.mockImplementation(
      (src: { recentSpawnIds?: readonly string[] | null }) => {
        if (src.recentSpawnIds != null) {
          return ["spn_open", "spn_recent"];
        }
        return ["spn_open"];
      },
    );

    mountInv("inv_wire");

    expect(collectDeepResearchSpawnIdsMock).toHaveBeenCalled();
    const withRecent = collectDeepResearchSpawnIdsMock.mock.calls.find(
      (c) =>
        (c[0] as { recentSpawnIds?: readonly string[] })?.recentSpawnIds !=
        null,
    );
    expect(withRecent).toBeTruthy();
    expect(
      (withRecent?.[0] as { recentSpawnIds: string[] }).recentSpawnIds,
    ).toEqual(["spn_recent"]);

    const panel = screen.getByTestId("collective-research-panel-stub");
    expect(panel.getAttribute("data-spawns")).toBe("spn_open,spn_recent");
    expect(panel.getAttribute("data-open-spawns")).toBe("spn_open");
    expect(panel.getAttribute("data-recent-spawns")).toBe("spn_recent");
  });
});
