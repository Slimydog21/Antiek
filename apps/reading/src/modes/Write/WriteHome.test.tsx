import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { emitTraceIntent } from "./Editor/traceIntent";
import type { TraceTarget } from "./writeApi";

/**
 * WriteHome.test — the re-homed Write door (Product Depth SPR-07 M1+M4).
 *
 * Load-bearing claims, mechanically checked:
 *  - the door opens on a real "start a piece" surface — NOT the legacy
 *    "Select or create a deliverable to begin." dead-end;
 *  - a citation chip's trace-to-source intent routes to the source reader
 *    when the source is servable, and falls back honestly (no dead page)
 *    when it isn't (§9.0 gated / unreachable).
 */

const {
  listDeliverablesMock, getTraceTargetMock, listInvestigationsMock,
  startInvestigationMock, createDeliverableMock, fetchHostedDocumentHtmlMock,
  createSectionMock, updateSectionProseMock, seedTwinNotesMock, getDeliverableMock,
  launchFloatingDeepResearchMock, hydratePublicationRefsMock, parsePublicationRefsMock,
  collectDeepResearchSpawnIdsMock, listRecentDeepResearchSpawnIdsMock,
  fetchDepthTiersMock,
} = vi.hoisted(() => ({
  listDeliverablesMock: vi.fn(),
  getTraceTargetMock: vi.fn(),
  listInvestigationsMock: vi.fn(),
  startInvestigationMock: vi.fn(),
  createDeliverableMock: vi.fn(),
  fetchHostedDocumentHtmlMock: vi.fn(),
  createSectionMock: vi.fn(),
  updateSectionProseMock: vi.fn(),
  seedTwinNotesMock: vi.fn(),
  getDeliverableMock: vi.fn(),
  launchFloatingDeepResearchMock: vi.fn(),
  hydratePublicationRefsMock: vi.fn(),
  parsePublicationRefsMock: vi.fn((raw: string) =>
    (raw || "")
      .split(/\r?\n+/)
      .map((l) => l.trim())
      .filter(Boolean),
  ),
  collectDeepResearchSpawnIdsMock: vi.fn(() => [] as string[]),
  listRecentDeepResearchSpawnIdsMock: vi.fn(() => [] as string[]),
  fetchDepthTiersMock: vi.fn(async () => ({
    active_depth_tier: null as string | null,
    active_preset: null,
    tiers: [],
  })),
}));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  listDeliverables: listDeliverablesMock,
  getDeliverable: (...args: unknown[]) => getDeliverableMock(...args),
  createDeliverable: createDeliverableMock,
  listInvestigations: listInvestigationsMock,
  startInvestigation: startInvestigationMock,
  createSection: (...args: unknown[]) => createSectionMock(...args),
  updateSectionProse: (...args: unknown[]) => updateSectionProseMock(...args),
}));

vi.mock("../../api/marketplaceHost", () => ({
  fetchHostedDocumentHtml: (...args: unknown[]) =>
    fetchHostedDocumentHtmlMock(...args),
}));

vi.mock("../../api/settings", () => ({
  fetchDepthTiers: (...args: unknown[]) => fetchDepthTiersMock(...args),
}));

vi.mock("../../api/engagement", () => ({
  seedTwinNotes: (...args: unknown[]) => seedTwinNotesMock(...args),
  fetchTwinNotes: vi.fn(async () => ({
    asset_id: "dlv-open",
    note_count: 0,
    insight_count: 0,
    question_count: 0,
    notes: [],
    view_format: "html",
    product_panel: "twin_notes",
    source: "test",
    messages: [],
    html: "",
  })),
  promoteTwinsToContext: vi.fn(),
  recordTwinNote: vi.fn(),
}));

vi.mock("../../components/engagement/TwinNotesPanel", () => ({
  TwinNotesPanel: (props: {
    assetId: string;
    autoLoad?: boolean;
    researchTier?: string | null;
    onPromoted?: (r: { promoted_count: number }) => void;
  }) => (
    <div
      data-testid="twin-notes-panel-stub"
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
    >
      {props.assetId}:auto={String(Boolean(props.autoLoad))}
      {props.researchTier ? `:tier=${props.researchTier}` : ""}
      {props.onPromoted ? (
        <button
          type="button"
          data-testid="write-twin-promote-notify"
          onClick={() => props.onPromoted?.({ promoted_count: 1 })}
        >
          notify-promote
        </button>
      ) : null}
    </div>
  ),
}));

vi.mock("../../components/engagement/ResearchContextPanel", () => ({
  ResearchContextPanel: (props: { assetId: string; autoLoad?: boolean }) => (
    <div data-testid="research-context-panel-stub">
      {props.assetId}:auto={String(Boolean(props.autoLoad))}
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
      driver
    </div>
  ),
}));

vi.mock("../../components/engagement/ResearchLaunchBudgetPanel", () => ({
  ResearchLaunchBudgetPanel: (props: {
    promptText?: string;
    researchTier?: string;
    onResearchTierChange?: (t: string) => void;
    onProjectionChange?: (p: { wouldExceedBudget: boolean }) => void;
  }) => (
    <div
      data-testid="research-launch-budget-panel-stub"
      data-research-tier={props.researchTier ?? ""}
    >
      budget len={props.promptText?.length ?? 0}
    </div>
  ),
}));

vi.mock("../../components/engagement/CollectiveResearchPanel", () => ({
  CollectiveResearchPanel: (props: {
    availableSpawnIds: string[];
    parentAssetId?: string | null;
    recentSpawnIds?: readonly string[] | null;
    openSpawnIds?: readonly string[] | null;
    onRecentSpawnsCleared?: () => void;
  }) => (
    <div
      data-testid="collective-research-panel-stub"
      data-recent={
        props.recentSpawnIds != null ? props.recentSpawnIds.join(",") : ""
      }
      data-open={
        props.openSpawnIds != null ? props.openSpawnIds.join(",") : ""
      }
      data-has-open-spawn-ids={props.openSpawnIds != null ? "1" : "0"}
      data-has-clear={props.onRecentSpawnsCleared ? "1" : "0"}
    >
      parent={props.parentAssetId ?? ""}:spawns={props.availableSpawnIds.join(",")}
    </div>
  ),
}));

vi.mock("../../workspace/windowsStore", () => ({
  useWindows: (sel: (s: { windows: Record<string, unknown> }) => unknown) =>
    sel({ windows: {} }),
}));

vi.mock("../../workspace/collectDeepResearchSpawnIds", () => ({
  collectDeepResearchSpawnIds: (...args: unknown[]) =>
    collectDeepResearchSpawnIdsMock(...args),
}));

vi.mock("../../workspace/recentDeepResearchSpawns", () => ({
  listRecentDeepResearchSpawnIds: (...args: unknown[]) =>
    listRecentDeepResearchSpawnIdsMock(...args),
}));

vi.mock("../Reading/launchFloatingDeepResearch", () => ({
  launchFloatingDeepResearch: (...args: unknown[]) =>
    launchFloatingDeepResearchMock(...args),
}));

vi.mock("../ResearchWorkstation/publicationRefs", () => ({
  parsePublicationRefs: (...args: unknown[]) =>
    parsePublicationRefsMock(...(args as [string])),
  hydratePublicationRefs: (...args: unknown[]) =>
    hydratePublicationRefsMock(...args),
}));

vi.mock("./Outline", () => ({
  default: () => <div data-testid="outline-stub">outline</div>,
}));

vi.mock("../DeepResearchWorkspace/Canvas/Canvas", () => ({
  default: () => <div data-testid="canvas-stub">canvas</div>,
}));

vi.mock("./BlockRepository", () => ({
  default: () => <div data-testid="block-repo-stub">repo</div>,
}));

vi.mock("./writeApi", async (orig) => ({
  ...(await orig<typeof import("./writeApi")>()),
  getTraceTarget: getTraceTargetMock,
}));

import WriteHome from "./WriteHome";

beforeEach(() => {
  listDeliverablesMock.mockReset().mockResolvedValue({ count: 0, deliverables: [] });
  getDeliverableMock.mockReset().mockResolvedValue(null);
  getTraceTargetMock.mockReset();
  listInvestigationsMock.mockReset().mockResolvedValue({ count: 0, investigations: [] });
  startInvestigationMock.mockReset().mockResolvedValue({
    investigation_id: "inv-spawned", status: "in_progress", start_event_id: "ev-1",
  });
  createDeliverableMock.mockReset().mockResolvedValue({
    deliverable_id: "dlv-new", title: "Memo", deliverable_kind: "general_essay",
    investigation_root_id: "inv-spawned", status: "draft",
    created_at: null, updated_at: null, section_count: 0,
  });
  createSectionMock.mockReset().mockResolvedValue({
    section_id: "sec_import_0",
    deliverable_id: "dlv-new",
    section_index: 0,
    title: "Imported",
    parent_section_id: null,
  });
  updateSectionProseMock.mockReset().mockResolvedValue({
    status: "saved",
    section_id: "sec_import_0",
    claim_node_id: null,
    claim_event_id: null,
  });
  seedTwinNotesMock.mockReset().mockResolvedValue({
    asset_id: "dlv-new",
    seeded: true,
    view_format: "html",
    notes: [],
    insight_count: 1,
    question_count: 1,
  });
  fetchHostedDocumentHtmlMock.mockReset().mockResolvedValue({
    document_id: "draft_merge_abc",
    view_format: "html",
    title: "Merged research draft",
    html: "<article><p>Attention is content-addressable memory.</p></article>",
  });
  launchFloatingDeepResearchMock.mockReset().mockResolvedValue({
    session_id: "sess_write",
    spawn_id: "spawn_write",
    investigation_id: "inv_write",
    parent_asset_id: "dlv-open",
    window_id: "win_write_dr",
    view_format: "html",
    view_mode: "floating",
    status: "open",
    model_id: null,
  });
  hydratePublicationRefsMock.mockReset().mockResolvedValue({
    ok: [{ asset_id: "pub_1", view_format: "html" }],
    failed: [],
    view_format: "html",
  });
  parsePublicationRefsMock.mockClear();
  collectDeepResearchSpawnIdsMock.mockReset().mockReturnValue([]);
  listRecentDeepResearchSpawnIdsMock.mockReset().mockReturnValue([]);
  fetchDepthTiersMock.mockReset().mockResolvedValue({
    active_depth_tier: null,
    active_preset: null,
    tiers: [],
  });
  // WriteHome now renders through GlassSurface (SPR-03 M2 landing-glass home /
  // M3 solid open-piece), which reads prefers-reduced-motion via
  // window.matchMedia. jsdom lacks it; stub the default (motion allowed → the
  // glass variant renders). Weakens nothing.
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});
afterEach(cleanup);

function mountAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/write" element={<WriteHome />} />
        <Route path="/write/:deliverableId" element={<WriteHome />} />
        <Route path="/read/:documentId" element={<div>READER</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("WriteHome — the re-homed door", () => {
  it("the no-piece Write home is LANDING-GLASS (SPR-03 M2 occlusion contract)", async () => {
    // Audit §3 item 5: the Write home (no piece) is a landing surface, rendered
    // through GlassSurface variant="glass" so the scene shows through the margins.
    // (The open-piece branch is dense-legible-keep-opaque = variant="solid"; that
    // contract is proven in GlassSurface.test.tsx + the audit §3 row + the source.)
    // A refactor swapping the home to an opaque body / solid would re-occlude the
    // mountain on /write; this enforces the variant per-route (rigor #5).
    const { container } = mountAt("/write");
    await screen.findByPlaceholderText(/what are you writing/i);
    const surface = container.querySelector("[data-glass-surface]");
    expect(surface, "the Write home must render through GlassSurface").toBeTruthy();
    expect(surface!.getAttribute("data-glass-variant")).toBe("glass");
  });

  it("opens on a real start-a-piece surface, not the 'select a deliverable' dead-end", async () => {
    mountAt("/write");
    // The action-first door (U-04): name the piece (SPR-09 M1 then prompts the
    // research connection before the piece is created).
    expect(
      await screen.findByPlaceholderText(/what are you writing/i),
    ).toBeTruthy();
    // The legacy dead-end sentence is gone.
    expect(screen.queryByText(/select or create a deliverable/i)).toBeNull();
    // And the brainstorm on-ramp is offered as the outline-optional entry.
    expect(screen.getByText(/brainstorm from an idea/i)).toBeTruthy();
  });

  it("shows HTML draft handoff banner from reading/research (fl)", async () => {
    mountAt("/write?html_draft=draft_merge_abc");
    await screen.findByPlaceholderText(/what are you writing/i);
    const banner = screen.getByTestId("write-html-draft-handoff");
    expect(banner.getAttribute("data-html-draft")).toBe("draft_merge_abc");
    expect(banner.getAttribute("data-view-format")).toBe("html");
    expect(banner.textContent).toMatch(/HTML draft handoff/);
    expect(banner.textContent).toMatch(/draft_merge_abc/);
  });

  it("loads twin_seed handoff and seeds brainstorm (pp)", async () => {
    const key = "antiek.twin_write_seed.writetest";
    window.sessionStorage.setItem(
      key,
      JSON.stringify({
        plain_text: "[question] Why twins?\n\n[insight] Recursive notes.",
        html: '<article data-twin-draft="true" data-view-format="html"><p>Why twins?</p></article>',
        title: "Twin draft · paper · 2 note(s)",
        asset_id: "paper-pp",
        note_ids: ["q1", "i1"],
        view_format: "html",
        source: "twin_draft_selected",
      }),
    );
    mountAt(`/write?twin_seed=${encodeURIComponent(key)}`);
    await waitFor(() => {
      expect(screen.getByTestId("write-twin-seed-handoff")).toBeTruthy();
    });
    const banner = screen.getByTestId("write-twin-seed-handoff");
    expect(banner.getAttribute("data-load-status")).toBe("ready");
    expect(banner.getAttribute("data-view-format")).toBe("html");
    expect(banner.getAttribute("data-note-count")).toBe("2");
    // Residual (pu): note_ids provenance on Write twin seed banner.
    expect(banner.getAttribute("data-note-ids")).toBe("q1,i1");
    expect(banner.getAttribute("data-asset-id")).toBe("paper-pp");
    expect(screen.getByTestId("write-twin-seed-ready").textContent).toMatch(
      /Twin draft seed/,
    );
    expect(screen.getByTestId("write-twin-seed-ready").textContent).toMatch(
      /note_ids=q1,i1/,
    );
    expect(screen.getByTestId("write-twin-seed-html-preview").innerHTML).toMatch(
      /twin-draft/,
    );
    expect(screen.getByTestId("write-twin-seed-handoff").getAttribute("data-source")).toBe(
      "twin_draft_selected",
    );
    expect(screen.getByTestId("write-twin-seed-source").textContent).toMatch(
      /twin_draft_selected/,
    );
    expect(screen.getByTestId("write-twin-seed-provenance").textContent).toMatch(
      /twin_seed:twin_draft_selected:2:paper-pp/,
    );
    const titleInput = screen.getByPlaceholderText(
      /what are you writing/i,
    ) as HTMLInputElement;
    expect(titleInput.value).toMatch(/Twin draft/);
    // Brainstorm on-ramp opened with seed.
    expect(screen.getByText(/brainstorm from an idea/i)).toBeTruthy();
    window.sessionStorage.removeItem(key);
  });

  it("stamps freeform provenance for deep_research_session source (qx)", async () => {
    const key = "antiek.twin_write_seed.dr_session_qx";
    window.sessionStorage.setItem(
      key,
      JSON.stringify({
        plain_text: "Selection passage.\n\nGoal: deep research",
        html: '<article data-source="deep_research_session"><p>seed</p></article>',
        title: "Deep research · spn_qx",
        asset_id: "book-qx",
        note_ids: [],
        view_format: "html",
        source: "deep_research_session",
      }),
    );
    mountAt(`/write?twin_seed=${encodeURIComponent(key)}`);
    await waitFor(() => {
      expect(screen.getByTestId("write-twin-seed-handoff").getAttribute("data-source")).toBe(
        "deep_research_session",
      );
    });
    expect(screen.getByTestId("write-twin-seed-provenance").textContent).toMatch(
      /twin_seed:deep_research_session:0:book-qx/,
    );
    window.sessionStorage.removeItem(key);
  });

  it("stamps freeform provenance for research_progress_complete source (qx)", async () => {
    const key = "antiek.twin_write_seed.progress_qx";
    window.sessionStorage.setItem(
      key,
      JSON.stringify({
        plain_text: "Spawn: spn_done\nTerminal stage: cite",
        html: '<article data-source="research_progress_complete" data-is-terminal="true"><p>done</p></article>',
        title: "Research complete · spn_done",
        asset_id: "deep_research:spn_done",
        note_ids: [],
        view_format: "html",
        source: "research_progress_complete",
      }),
    );
    mountAt(`/write?twin_seed=${encodeURIComponent(key)}`);
    await waitFor(() => {
      expect(screen.getByTestId("write-twin-seed-handoff").getAttribute("data-source")).toBe(
        "research_progress_complete",
      );
    });
    expect(screen.getByTestId("write-twin-seed-provenance").textContent).toMatch(
      /twin_seed:research_progress_complete:0:deep_research:spn_done/,
    );
    window.sessionStorage.removeItem(key);
  });

  it("loads hosted HTML draft, prefills title, seeds brainstorm (fm)", async () => {
    mountAt("/write?html_draft=draft_merge_abc");
    await waitFor(() => {
      expect(fetchHostedDocumentHtmlMock).toHaveBeenCalledWith("draft_merge_abc");
    });
    await waitFor(() => {
      expect(screen.getByTestId("write-html-draft-loaded")).toBeTruthy();
    });
    expect(
      screen.getByTestId("write-html-draft-handoff").getAttribute("data-load-status"),
    ).toBe("ready");
    expect(screen.getByTestId("write-html-draft-title").textContent).toMatch(
      /Merged research draft/,
    );
    expect(screen.getByTestId("write-html-draft-plain-preview").textContent).toMatch(
      /Attention is content-addressable/,
    );
    // Title prefilled from draft.
    const titleInput = screen.getByPlaceholderText(
      /what are you writing/i,
    ) as HTMLInputElement;
    expect(titleInput.value).toMatch(/Merged research draft/);
    // Residual (fp): provenance freeform stamped for html draft.
    await waitFor(() => {
      expect(
        screen.getByTestId("write-html-draft-provenance").getAttribute(
          "data-document-id",
        ),
      ).toBe("draft_merge_abc");
    });
    expect(screen.getByTestId("write-html-draft-provenance").textContent).toMatch(
      /html_draft:draft_merge_abc/,
    );
    // Residual (ft): import-on-create badge (section 0 prose).
    expect(
      screen
        .getByTestId("write-html-draft-import-outline")
        .getAttribute("data-import-on-create"),
    ).toBe("true");
    expect(screen.getByTestId("write-html-draft-import-deferred").textContent).toMatch(
      /outline sections|plain-text|h1–h3/i,
    );
    expect(
      screen
        .getByTestId("write-html-draft-import-outline")
        .getAttribute("data-section-count"),
    ).toBe("1");
    // Seed brainstorm opens idea dump with plain text.
    await userEvent.click(screen.getByTestId("write-html-draft-seed-brainstorm"));
    await waitFor(() => {
      expect(screen.getByDisplayValue(/Attention is content-addressable/)).toBeTruthy();
    });
  });

  it("imports HTML draft plain text into section 0 on create piece (ft)", async () => {
    mountAt("/write?html_draft=draft_merge_abc");
    await waitFor(() => {
      expect(screen.getByTestId("write-html-draft-loaded")).toBeTruthy();
    });
    const title = await screen.findByPlaceholderText(/what are you writing/i);
    // Title may already be prefilled; ensure non-empty for connect.
    await userEvent.clear(title);
    await userEvent.type(title, "Piece from draft");
    await userEvent.click(await screen.findByText(/start without a project/i));
    await waitFor(() => expect(createDeliverableMock).toHaveBeenCalled());
    await waitFor(() => {
      expect(createSectionMock).toHaveBeenCalledWith(
        expect.objectContaining({
          deliverable_id: "dlv-new",
          section_index: 0,
        }),
      );
    });
    await waitFor(() => {
      expect(updateSectionProseMock).toHaveBeenCalledWith(
        "sec_import_0",
        expect.objectContaining({
          prose_text: expect.stringMatching(/Attention is content-addressable/),
          promote_to_graph: false,
        }),
      );
    });
    // Residual (fz): twin seed on deliverable after import.
    await waitFor(() => {
      expect(seedTwinNotesMock).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "dlv-new",
          force_offline: true,
        }),
      );
    });
  });

  it("imports multi-heading HTML into multiple outline sections (fu)", async () => {
    createSectionMock
      .mockResolvedValueOnce({
        section_id: "sec_0",
        deliverable_id: "dlv-new",
        section_index: 0,
        title: "First",
        parent_section_id: null,
      })
      .mockResolvedValueOnce({
        section_id: "sec_1",
        deliverable_id: "dlv-new",
        section_index: 1,
        title: "Second",
        parent_section_id: null,
      });
    fetchHostedDocumentHtmlMock.mockResolvedValueOnce({
      document_id: "draft_multi",
      view_format: "html",
      title: "Multi draft",
      html: "<h1>First</h1><p>Alpha body.</p><h2>Second</h2><p>Beta body.</p>",
    });
    mountAt("/write?html_draft=draft_multi");
    await waitFor(() => {
      expect(screen.getByTestId("write-html-draft-loaded")).toBeTruthy();
    });
    expect(
      screen
        .getByTestId("write-html-draft-import-outline")
        .getAttribute("data-section-count"),
    ).toBe("2");
    // Residual (fw): section preview before create.
    const preview = screen.getByTestId("write-html-draft-section-preview");
    expect(preview.getAttribute("data-section-count")).toBe("2");
    const items = screen.getAllByTestId("write-html-draft-section-preview-item");
    expect(items).toHaveLength(2);
    expect(items[0].getAttribute("data-heading-level")).toBe("1");
    expect(items[1].getAttribute("data-heading-level")).toBe("2");
    expect(items[0].textContent).toMatch(/First/);
    expect(items[1].textContent).toMatch(/Second/);
    const title = await screen.findByPlaceholderText(/what are you writing/i);
    await userEvent.clear(title);
    await userEvent.type(title, "Multi section piece");
    await userEvent.click(await screen.findByText(/start without a project/i));
    await waitFor(() => expect(createDeliverableMock).toHaveBeenCalled());
    await waitFor(() => {
      expect(createSectionMock).toHaveBeenCalledTimes(2);
    });
    expect(createSectionMock).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        deliverable_id: "dlv-new",
        section_index: 0,
        title: "First",
      }),
    );
    // Residual (fv): h2 nests under preceding h1 via parent_section_id.
    expect(createSectionMock).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        deliverable_id: "dlv-new",
        section_index: 1,
        title: "Second",
        parent_section_id: "sec_0",
      }),
    );
    await waitFor(() => {
      expect(updateSectionProseMock).toHaveBeenCalledTimes(2);
    });
    // Residual (fx): prose prefers HTML fragment (HTML-first).
    expect(updateSectionProseMock).toHaveBeenCalledWith(
      "sec_0",
      expect.objectContaining({
        prose_text: expect.stringMatching(/<p>Alpha body\.<\/p>/i),
      }),
    );
    expect(updateSectionProseMock).toHaveBeenCalledWith(
      "sec_1",
      expect.objectContaining({
        prose_text: expect.stringMatching(/<p>Beta body\.<\/p>/i),
      }),
    );
  });

  it("refuses non-html draft view_format (fm)", async () => {
    fetchHostedDocumentHtmlMock.mockResolvedValueOnce({
      document_id: "bad",
      view_format: "pdf",
      title: "Nope",
      html: "%PDF",
    });
    mountAt("/write?html_draft=bad");
    await waitFor(() => {
      expect(screen.getByTestId("write-html-draft-error").textContent).toMatch(
        /html/i,
      );
    });
  });

  it("mounts TwinNotesPanel on open piece (ga)", async () => {
    getDeliverableMock.mockResolvedValue({
      deliverable_id: "dlv-open",
      title: "Open piece",
      deliverable_kind: "general_essay",
      investigation_root_id: "inv-1",
      status: "draft",
      sections: [],
      created_at: null,
      updated_at: null,
      section_count: 0,
    });
    mountAt("/write/dlv-open");
    await waitFor(() => {
      expect(screen.getByTestId("write-piece-twins-mount")).toBeTruthy();
    });
    expect(
      screen.getByTestId("write-piece-twins-mount").getAttribute("data-asset-id"),
    ).toBe("dlv-open");
    expect(screen.getByTestId("twin-notes-panel-stub").textContent).toMatch(
      /dlv-open:auto=true/,
    );
    // Residual (ks): write piece twins inherit writeResearchTier (default deep).
    expect(
      screen.getByTestId("twin-notes-panel-stub").getAttribute("data-research-tier"),
    ).toBe("deep");
    expect(screen.getByTestId("outline-stub")).toBeTruthy();
    // Residual (gg): twins share refresh key with context (starts at 0).
    expect(
      screen
        .getByTestId("write-piece-twins-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("0");
  });

  it("remounts TwinNotesPanel after twin promote (gg)", async () => {
    getDeliverableMock.mockResolvedValue({
      deliverable_id: "dlv-twins-gg",
      title: "Twins remount piece",
      deliverable_kind: "general_essay",
      investigation_root_id: null,
      status: "draft",
      sections: [],
      created_at: null,
      updated_at: null,
      section_count: 0,
    });
    mountAt("/write/dlv-twins-gg");
    await waitFor(() => {
      expect(screen.getByTestId("write-piece-twins-refresh")).toBeTruthy();
    });
    expect(
      screen
        .getByTestId("write-piece-twins-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("0");
    expect(
      screen
        .getByTestId("write-piece-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("0");
    fireEvent.click(screen.getByTestId("write-twin-promote-notify"));
    expect(
      screen
        .getByTestId("write-piece-twins-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("1");
    expect(
      screen
        .getByTestId("write-piece-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("1");
  });

  it("mounts ResearchContextPanel and remounts after twin promote (gb)", async () => {
    getDeliverableMock.mockResolvedValue({
      deliverable_id: "dlv-ctx",
      title: "Context piece",
      deliverable_kind: "general_essay",
      investigation_root_id: "inv-2",
      status: "draft",
      sections: [],
      created_at: null,
      updated_at: null,
      section_count: 0,
    });
    mountAt("/write/dlv-ctx");
    await waitFor(() => {
      expect(screen.getByTestId("write-piece-context-mount")).toBeTruthy();
    });
    expect(
      screen.getByTestId("write-piece-context-mount").getAttribute("data-asset-id"),
    ).toBe("dlv-ctx");
    expect(screen.getByTestId("research-context-panel-stub").textContent).toMatch(
      /dlv-ctx:auto=true/,
    );
    expect(
      screen
        .getByTestId("write-piece-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("0");
    fireEvent.click(screen.getByTestId("write-twin-promote-notify"));
    expect(
      screen
        .getByTestId("write-piece-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("1");
  });

  it("mounts DecisionTreeDriverBadge on open piece (gc)", async () => {
    getDeliverableMock.mockResolvedValue({
      deliverable_id: "dlv-drv",
      title: "Driver piece",
      deliverable_kind: "general_essay",
      investigation_root_id: null,
      status: "draft",
      sections: [],
      created_at: null,
      updated_at: null,
      section_count: 0,
    });
    mountAt("/write/dlv-drv");
    await waitFor(() => {
      expect(screen.getByTestId("write-piece-driver-badge")).toBeTruthy();
    });
    expect(
      screen.getByTestId("write-piece-driver-badge").getAttribute("data-view-format"),
    ).toBe("html");
    expect(screen.getByTestId("decision-tree-driver-badge-stub")).toBeTruthy();
    // Residual (ph): badge receives DR selection prompt for projection.
    expect(
      Number(
        screen
          .getByTestId("decision-tree-driver-badge-stub")
          .getAttribute("data-prompt-len") || 0,
      ),
    ).toBeGreaterThan(0);
    // Residual (if): Settings deep-link for driver + budget.
    const settings = screen.getByTestId("write-piece-settings-link");
    expect(settings.getAttribute("href")).toBe("/settings#decision-tree-panel");
    expect(settings.textContent).toMatch(/driver & budget/i);
  });

  it("mounts CollectiveResearchPanel when DR spawns exist (gf)", async () => {
    collectDeepResearchSpawnIdsMock.mockReturnValue(["spawn_a", "spawn_b"]);
    getDeliverableMock.mockResolvedValue({
      deliverable_id: "dlv-coll",
      title: "Collective piece",
      deliverable_kind: "general_essay",
      investigation_root_id: null,
      status: "draft",
      sections: [],
      created_at: null,
      updated_at: null,
      section_count: 0,
    });
    mountAt("/write/dlv-coll");
    await waitFor(() => {
      expect(screen.getByTestId("write-piece-collective-mount")).toBeTruthy();
    });
    const mount = screen.getByTestId("write-piece-collective-mount");
    expect(mount.getAttribute("data-asset-id")).toBe("dlv-coll");
    expect(mount.getAttribute("data-view-format")).toBe("html");
    expect(mount.getAttribute("data-available-spawn-count")).toBe("2");
    expect(screen.getByTestId("collective-research-panel-stub").textContent).toMatch(
      /parent=dlv-coll:spawns=spawn_a,spawn_b/,
    );
    // Residual (uf): openSpawnIds wired for Select open only (parity ue).
    expect(
      screen
        .getByTestId("collective-research-panel-stub")
        .getAttribute("data-has-open-spawn-ids"),
    ).toBe("1");
  });

  it("wires recent_ring into collect + collective mount (om)", async () => {
    listRecentDeepResearchSpawnIdsMock.mockReturnValue([
      "spn_chased_closed",
      "spn_older",
    ]);
    collectDeepResearchSpawnIdsMock.mockImplementation(
      (source: { recentSpawnIds?: readonly string[] | null }) =>
        [...(source.recentSpawnIds ?? [])],
    );
    getDeliverableMock.mockResolvedValue({
      deliverable_id: "dlv-recent",
      title: "Recent ring piece",
      deliverable_kind: "general_essay",
      investigation_root_id: null,
      status: "draft",
      sections: [],
      created_at: null,
      updated_at: null,
      section_count: 0,
    });
    mountAt("/write/dlv-recent");
    await waitFor(() => {
      expect(screen.getByTestId("write-piece-collective-mount")).toBeTruthy();
    });
    expect(collectDeepResearchSpawnIdsMock).toHaveBeenCalled();
    const lastCall = collectDeepResearchSpawnIdsMock.mock.calls.at(-1)?.[0] as {
      recentSpawnIds?: readonly string[];
    };
    expect(lastCall.recentSpawnIds).toEqual([
      "spn_chased_closed",
      "spn_older",
    ]);
    const mount = screen.getByTestId("write-piece-collective-mount");
    expect(mount.getAttribute("data-recent-count")).toBe("2");
    expect(mount.getAttribute("data-available-spawn-count")).toBe("2");
    const stub = screen.getByTestId("collective-research-panel-stub");
    expect(stub.getAttribute("data-recent")).toBe(
      "spn_chased_closed,spn_older",
    );
    expect(stub.getAttribute("data-has-clear")).toBe("1");
    expect(stub.textContent).toMatch(
      /parent=dlv-recent:spawns=spn_chased_closed,spn_older/,
    );
  });

  it("hides collective mount when no DR spawns (gf)", async () => {
    collectDeepResearchSpawnIdsMock.mockReturnValue([]);
    getDeliverableMock.mockResolvedValue({
      deliverable_id: "dlv-solo",
      title: "Solo piece",
      deliverable_kind: "general_essay",
      investigation_root_id: null,
      status: "draft",
      sections: [],
      created_at: null,
      updated_at: null,
      section_count: 0,
    });
    mountAt("/write/dlv-solo");
    await waitFor(() => {
      expect(screen.getByTestId("write-piece-twins-mount")).toBeTruthy();
    });
    expect(screen.queryByTestId("write-piece-collective-mount")).toBeNull();
  });

  it("launches deep research from open Write piece with pub refs (ge)", async () => {
    getDeliverableMock.mockResolvedValue({
      deliverable_id: "dlv-open",
      title: "Essay on attention",
      deliverable_kind: "general_essay",
      investigation_root_id: "inv-1",
      status: "draft",
      sections: [],
      created_at: null,
      updated_at: null,
      section_count: 0,
    });
    mountAt("/write/dlv-open");
    await waitFor(() => {
      expect(screen.getByTestId("write-piece-research-launch")).toBeTruthy();
    });
    const panel = screen.getByTestId("write-piece-research-launch");
    expect(panel.getAttribute("data-asset-id")).toBe("dlv-open");
    expect(panel.getAttribute("data-view-format")).toBe("html");
    expect(panel.getAttribute("data-from-highlight")).toBe("false");
    expect(screen.getByTestId("write-piece-pub-refs")).toBeTruthy();
    expect(screen.getByTestId("research-launch-budget-panel-stub")).toBeTruthy();
    expect(screen.getByTestId("write-piece-budget-mount")).toBeTruthy();
    expect(screen.getByTestId("write-piece-selection-fallback")).toBeTruthy();
    await waitFor(() => {
      expect(
        screen.getByTestId("write-piece-budget-mount").getAttribute(
          "data-depth-prefill",
        ),
      ).toBe("none");
    });
    await userEvent.type(
      screen.getByTestId("write-piece-refs-input"),
      "arxiv:1706.03762",
    );
    await userEvent.click(screen.getByTestId("write-piece-deep-research"));
    await waitFor(() => {
      expect(hydratePublicationRefsMock).toHaveBeenCalledWith([
        "arxiv:1706.03762",
      ]);
    });
    await waitFor(() => {
      expect(launchFloatingDeepResearchMock).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "dlv-open",
          view_mode: "floating",
          references: ["arxiv:1706.03762"],
          selection_text: expect.stringMatching(/Essay on attention/),
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("write-piece-research-window-id").textContent).toMatch(
        /win_write_dr/,
      );
    });
    expect(screen.getByTestId("write-piece-refs-status").textContent).toMatch(
      /Hydrated 1/,
    );
    // Full window path
    launchFloatingDeepResearchMock.mockClear();
    await userEvent.click(screen.getByTestId("write-piece-deep-research-full"));
    await waitFor(() => {
      expect(launchFloatingDeepResearchMock).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "dlv-open",
          view_mode: "full",
        }),
      );
    });
  });

  it("prefills Write piece DR research tier from Settings wrestle depth (jh)", async () => {
    fetchDepthTiersMock.mockResolvedValue({
      active_depth_tier: "wrestle",
      active_preset: null,
      tiers: [],
    });
    getDeliverableMock.mockResolvedValue({
      deliverable_id: "dlv-depth",
      title: "Wrestle write piece",
      deliverable_kind: "general_essay",
      investigation_root_id: null,
      status: "draft",
      sections: [],
      created_at: null,
      updated_at: null,
      section_count: 0,
    });
    mountAt("/write/dlv-depth");
    await waitFor(() => {
      expect(screen.getByTestId("write-piece-research-launch")).toBeTruthy();
    });
    await waitFor(() => {
      expect(fetchDepthTiersMock).toHaveBeenCalled();
    });
    const mount = screen.getByTestId("write-piece-budget-mount");
    await waitFor(() => {
      expect(mount.getAttribute("data-depth-prefill")).toBe("installed");
    });
    expect(mount.getAttribute("data-research-tier")).toBe("wrestle");
    expect(
      screen.getByTestId("research-launch-budget-panel-stub").getAttribute(
        "data-research-tier",
      ),
    ).toBe("wrestle");
    expect(screen.getByTestId("write-piece-depth-prefill").textContent).toMatch(
      /installed.*wrestle/,
    );
  });

  it("captures highlight for Write DR budget projection and launch (gh)", async () => {
    getDeliverableMock.mockResolvedValue({
      deliverable_id: "dlv-hl",
      title: "Highlight piece",
      deliverable_kind: "general_essay",
      investigation_root_id: null,
      status: "draft",
      sections: [],
      created_at: null,
      updated_at: null,
      section_count: 0,
    });
    // Seed a DOM selection so mouseup capture can read it.
    const rangeHolder = document.createElement("div");
    rangeHolder.textContent = "Selected claim about attention mechanisms.";
    document.body.appendChild(rangeHolder);
    const range = document.createRange();
    range.selectNodeContents(rangeHolder);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);

    mountAt("/write/dlv-hl");
    await waitFor(() => {
      expect(screen.getByTestId("write-piece-research-launch")).toBeTruthy();
    });
    fireEvent.mouseUp(screen.getByTestId("write-piece-research-launch"));
    await waitFor(() => {
      expect(
        screen
          .getByTestId("write-piece-research-launch")
          .getAttribute("data-from-highlight"),
      ).toBe("true");
    });
    expect(screen.getByTestId("write-piece-selection-text").textContent).toMatch(
      /Selected claim about attention/,
    );
    expect(
      screen.getByTestId("write-piece-selection-preview").getAttribute(
        "data-from-highlight",
      ),
    ).toBe("true");
    await userEvent.click(screen.getByTestId("write-piece-deep-research"));
    await waitFor(() => {
      expect(launchFloatingDeepResearchMock).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "dlv-hl",
          selection_text: expect.stringMatching(/Selected claim about attention/),
        }),
      );
    });
    await userEvent.click(screen.getByTestId("write-piece-clear-highlight"));
    expect(
      screen
        .getByTestId("write-piece-research-launch")
        .getAttribute("data-from-highlight"),
    ).toBe("false");
    expect(screen.getByTestId("write-piece-selection-fallback")).toBeTruthy();
    rangeHolder.remove();
  });

  it("re-imports html_draft into open piece with section index offset (gd)", async () => {
    getDeliverableMock.mockResolvedValue({
      deliverable_id: "dlv-open",
      title: "Existing piece",
      deliverable_kind: "general_essay",
      investigation_root_id: "inv-1",
      status: "draft",
      sections: [
        {
          section_id: "sec_existing",
          deliverable_id: "dlv-open",
          section_index: 0,
          title: "Already there",
          parent_section_id: null,
        },
      ],
      created_at: null,
      updated_at: null,
      section_count: 1,
    });
    createSectionMock.mockResolvedValue({
      section_id: "sec_reimport_0",
      deliverable_id: "dlv-open",
      section_index: 1,
      title: "Merged research draft",
      parent_section_id: null,
    });
    seedTwinNotesMock.mockClear();
    mountAt("/write/dlv-open?html_draft=draft_merge_abc");
    await waitFor(() => {
      expect(fetchHostedDocumentHtmlMock).toHaveBeenCalledWith("draft_merge_abc");
    });
    await waitFor(() => {
      expect(screen.getByTestId("write-piece-html-reimport")).toBeTruthy();
    });
    const panel = screen.getByTestId("write-piece-html-reimport");
    expect(panel.getAttribute("data-html-draft")).toBe("draft_merge_abc");
    expect(panel.getAttribute("data-view-format")).toBe("html");
    await waitFor(() => {
      expect(panel.getAttribute("data-load-status")).toBe("ready");
    });
    expect(screen.getByTestId("write-piece-reimport-title").textContent).toMatch(
      /Merged research draft/,
    );
    await userEvent.click(screen.getByTestId("write-piece-reimport-run"));
    await waitFor(() => {
      expect(createSectionMock).toHaveBeenCalledWith(
        expect.objectContaining({
          deliverable_id: "dlv-open",
          // One existing section → append at index 1
          section_index: 1,
        }),
      );
    });
    await waitFor(() => {
      expect(updateSectionProseMock).toHaveBeenCalledWith(
        "sec_reimport_0",
        expect.objectContaining({
          prose_text: expect.stringMatching(/Attention is content-addressable/),
          promote_to_graph: false,
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("write-piece-reimport-status").textContent).toMatch(
        /Imported 1 section/,
      );
    });
    // Re-import must not re-seed twins (seedTwins:false on open piece).
    expect(seedTwinNotesMock).not.toHaveBeenCalled();
  });

  it("M1 — 'none' auto-spawns a research folder and creates the piece linked to it", async () => {
    mountAt("/write");
    // Naming the piece reveals the connect-to-research step (M1).
    const title = await screen.findByPlaceholderText(/what are you writing/i);
    await userEvent.type(title, "A margins memo");
    // Choose "none" → auto-spawn + link.
    await userEvent.click(await screen.findByText(/start without a project/i));
    await waitFor(() => expect(createDeliverableMock).toHaveBeenCalled());
    // The piece is created WITH the spawned investigation_root_id (the link is
    // set at creation — verified by the create call carrying it, not a UI claim).
    expect(createDeliverableMock).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "A margins memo",
        investigation_root_id: "inv-spawned",
      }),
    );
  });

  it("seeds twin notes on create when twin_seed handoff is present (pq)", async () => {
    const key = "antiek.twin_write_seed.createtest";
    window.sessionStorage.setItem(
      key,
      JSON.stringify({
        plain_text: "[question] Why?\n\n[insight] Recursive notes.",
        html: '<article data-twin-draft="true"><p>Why?</p></article>',
        title: "Twin draft · paper · 2 note(s)",
        asset_id: "paper-pq",
        note_ids: ["q1", "i1"],
        view_format: "html",
        source: "twin_draft_selected",
      }),
    );
    seedTwinNotesMock.mockClear();
    mountAt(`/write?twin_seed=${encodeURIComponent(key)}`);
    await waitFor(() => {
      expect(screen.getByTestId("write-twin-seed-ready")).toBeTruthy();
    });
    const title = await screen.findByPlaceholderText(/what are you writing/i);
    await userEvent.clear(title);
    await userEvent.type(title, "Twin-seeded essay");
    await userEvent.click(await screen.findByText(/start without a project/i));
    await waitFor(() => expect(createDeliverableMock).toHaveBeenCalled());
    await waitFor(() => {
      expect(seedTwinNotesMock).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "dlv-new",
          force_offline: true,
          body_text: expect.stringMatching(/\[question\] Why\?/),
          title: "Twin-seeded essay",
          usage_source: "twin_draft_selected",
        }),
      );
    });
    window.sessionStorage.removeItem(key);
  });

  it("passes deep_research_session usage_source on create seed (qy)", async () => {
    const key = "antiek.twin_write_seed.qy_dr";
    window.sessionStorage.setItem(
      key,
      JSON.stringify({
        plain_text: "Selection.\n\nGoal: research",
        html: '<article data-source="deep_research_session"><p>x</p></article>',
        title: "Deep research · spn_qy",
        asset_id: "book-qy",
        note_ids: [],
        view_format: "html",
        source: "deep_research_session",
      }),
    );
    seedTwinNotesMock.mockClear();
    mountAt(`/write?twin_seed=${encodeURIComponent(key)}`);
    await waitFor(() => {
      expect(screen.getByTestId("write-twin-seed-ready")).toBeTruthy();
    });
    const title = await screen.findByPlaceholderText(/what are you writing/i);
    await userEvent.clear(title);
    await userEvent.type(title, "DR-seeded essay");
    await userEvent.click(await screen.findByText(/start without a project/i));
    await waitFor(() => {
      expect(seedTwinNotesMock).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_id: "dlv-new",
          usage_source: "deep_research_session",
        }),
      );
    });
    window.sessionStorage.removeItem(key);
  });

  it("routes a servable trace-to-source to the source reader", async () => {
    const target: TraceTarget = {
      kind: "document",
      full_text_allowed: true,
      document_id: "doc-1",
      document_title: "Source Book",
      chunk_ids: ["c1"],
      servability_status: "servable",
      detail: null,
    };
    getTraceTargetMock.mockResolvedValue(target);
    mountAt("/write");
    await screen.findByPlaceholderText(/what are you writing/i);

    emitTraceIntent({
      sectionId: "sec-1",
      outlineBlockId: "oblk-1",
      nodeId: "node-1",
      provenanceKind: "graph_node",
    });
    // The honest trip: a servable source opens the reader.
    await waitFor(() => expect(screen.getByText("READER")).toBeTruthy());
  });

  it("falls back honestly (no dead page) when the source is gated/unreachable", async () => {
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    const gated: TraceTarget = {
      kind: "document",
      full_text_allowed: false, // the no-leak bit
      document_id: "doc-gated",
      document_title: "Gated Book",
      chunk_ids: [],
      servability_status: "restricted_pending_opt_in",
      detail: "this source is gated",
    };
    getTraceTargetMock.mockResolvedValue(gated);
    mountAt("/write");
    await screen.findByPlaceholderText(/what are you writing/i);

    emitTraceIntent({
      sectionId: "sec-1",
      outlineBlockId: "oblk-gated",
      nodeId: "node-g",
      provenanceKind: "graph_node",
    });
    await waitFor(() => expect(alertSpy).toHaveBeenCalled());
    // It did NOT navigate to a dead reader page.
    expect(screen.queryByText("READER")).toBeNull();
    alertSpy.mockRestore();
  });
});
