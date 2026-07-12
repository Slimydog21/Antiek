/**
 * DeepResearchSessionHost + WINDOW_PAGES eligibility for deep_research_session.
 * Residual (ag): mounts ResearchContextPanel with asset/spawn identity.
 * Residual (ah): mounts CollectiveResearchPanel with available spawn ids.
 * Residual (bx): mounts ResearchLaunchBudgetPanel for goal/selection projection.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEEP_RESEARCH_WINDOW_KIND } from "../../workspace/deepResearchWindow";
import {
  clearRecentDeepResearchSpawnIds,
  pushRecentDeepResearchSpawnId,
} from "../../workspace/recentDeepResearchSpawns";
import DeepResearchSessionHost from "./DeepResearchSessionHost";
import { WINDOW_PAGES, isWindowEligible, openWindow } from "./openWindow";
import { useWindows } from "../../workspace/windowsStore";

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
const updateEngagementSessionView = vi.hoisted(() =>
  vi.fn(async (body: { session_id: string; mode: "floating" | "full" }) => ({
    session_id: body.session_id,
    view_mode: body.mode,
    view_format: "html" as const,
  })),
);
const mergeEngagementSessions = vi.hoisted(() => vi.fn());
const fetchSessionsCollective = vi.hoisted(() => vi.fn());
const listOwnedEngagementSessions = vi.hoisted(() => vi.fn());

vi.mock("../../api/engagement", () => ({
  updateEngagementSessionView: (body: {
    session_id: string;
    mode: "floating" | "full";
  }) => updateEngagementSessionView(body),
  listEngagementSessions: vi.fn(),
  mergeEngagementSessions,
  fetchSessionsCollective,
  listOwnedEngagementSessions,
}));

vi.mock("../../api/settings", () => ({
  fetchSettingsBudget: vi.fn(async () => ({
    daily_cap_usd: 5,
    spent_usd: 1,
    remaining_usd: 4,
    spent_status: "known",
    cap_env: null,
    notes: [],
  })),
  estimatePromptCost: vi.fn(async () => ({
    estimated_usd_low: 0.1,
    estimated_usd_high: 0.15,
    would_exceed_budget: false,
    pricing_known: true,
    notes: [],
    assumed_input_tokens: 50,
    assumed_output_tokens: 2500,
    tier: "pro",
    provider: null,
    model: null,
  })),
  fetchDecisionTreeSelection: vi.fn(async () => ({
    model_id: null,
    provider_id: null,
    installed: false,
    notes: [],
    source: "test",
  })),
  fetchDepthTiers: (...args: unknown[]) => fetchDepthTiers(...(args as Parameters<typeof fetchDepthTiers>)),
}));

vi.mock("../engagement/SpawnMergePanel", () => ({
  SpawnMergePanel: (props: {
    spawnId: string;
    parentAssetId: string;
    researchTier?: string | null;
    onMerged?: (r: { document_id: string }) => void;
  }) => (
    <div
      data-testid="spawn-merge-panel-stub"
      data-research-tier={(props.researchTier || "").trim().toLowerCase() || ""}
    >
      {props.spawnId}→{props.parentAssetId}
      {props.onMerged ? (
        <button
          type="button"
          data-testid="spawn-merge-notify"
          onClick={() =>
            props.onMerged?.({ document_id: "draft_from_merge" })
          }
        >
          notify-merge
        </button>
      ) : null}
    </div>
  ),
}));

vi.mock("../engagement/PublicationAttachPanel", () => ({
  PublicationAttachPanel: (props: {
    spawnId: string;
    researchTier?: string | null;
    onAttached?: (r: { spawnId: string }) => void;
  }) => (
    <div
      data-testid="publication-attach-panel-stub"
      data-research-tier={props.researchTier || ""}
    >
      {props.spawnId}
      {props.researchTier ? ` · tier=${props.researchTier}` : ""}
      {props.onAttached ? (
        <button
          type="button"
          data-testid="publication-attach-notify"
          onClick={() => props.onAttached?.({ spawnId: props.spawnId })}
        >
          notify-attach
        </button>
      ) : null}
    </div>
  ),
}));

vi.mock("../engagement/SessionFlywheelPanel", () => ({
  SessionFlywheelPanel: (props: {
    sessionId: string;
    onCompleted?: (r: { status: string }) => void;
  }) => (
    <div data-testid="session-flywheel-panel-stub">
      {props.sessionId}
      {props.onCompleted ? (
        <button
          type="button"
          data-testid="session-flywheel-notify"
          onClick={() => props.onCompleted?.({ status: "complete" })}
        >
          notify-flywheel
        </button>
      ) : null}
    </div>
  ),
}));

vi.mock("../engagement/ResearchProgressPanel", () => ({
  ResearchProgressPanel: (props: {
    spawnId: string;
    autoLoad?: boolean;
    autoSeedIfEmpty?: boolean;
    pollIntervalMs?: number;
    researchTier?: string | null;
  }) => (
    <div
      data-testid="research-progress-panel-stub"
      data-research-tier={props.researchTier ?? ""}
    >
      {props.spawnId}:auto={String(Boolean(props.autoLoad))}:seed=
      {String(Boolean(props.autoSeedIfEmpty))}:poll=
      {String(props.pollIntervalMs ?? 0)}:tier=
      {props.researchTier ?? ""}
    </div>
  ),
}));

vi.mock("../engagement/TwinNotesPanel", () => ({
  TwinNotesPanel: (props: {
    assetId: string;
    spawnId?: string | null;
    autoLoad?: boolean;
    domainSubjects?: readonly string[] | null;
    onPromoted?: (r: { promoted_count: number }) => void;
  }) => (
    <div
      data-testid="twin-notes-panel-stub"
      data-domain-subjects={(props.domainSubjects || []).join(",") || ""}
    >
      {props.assetId}:auto={String(Boolean(props.autoLoad))}
      {props.onPromoted ? (
        <button
          type="button"
          data-testid="twin-notes-promote-notify"
          onClick={() => props.onPromoted?.({ promoted_count: 1 })}
        >
          notify
        </button>
      ) : null}
    </div>
  ),
}));

vi.mock("../engagement/DecisionTreeDriverBadge", () => ({
  DecisionTreeDriverBadge: () => (
    <div data-testid="decision-tree-driver-badge">Driver badge</div>
  ),
}));

const FIXTURE = {
  owner_id: "alice",
  session_id: "fsess_launch_1",
  spawn_id: "spn_launch_1",
  investigation_id: "inv_launch_1",
  parent_asset_id: "launch-asset",
  selection_text: "Transformer attention is content-addressable memory.",
  status: "reserved",
  view_format: "html" as const,
  model_id: "launch-model",
  region_id: "r-launch-1",
  goal: "Deep-research the highlighted passage",
};

describe("DeepResearchSessionHost", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    mergeEngagementSessions.mockReset();
    fetchSessionsCollective.mockReset();
    listOwnedEngagementSessions.mockReset().mockResolvedValue({
      owner_id: "alice",
      sessions: [{ ...FIXTURE, source_references: [] }],
      count: 1,
      next_cursor: null,
      status_filter: null,
      view_format: "html",
    });
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
  });

  it("renders session identity and selection from payload", () => {
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(screen.getByTestId("deep-research-session-host")).toBeTruthy();
    // Session id appears in identity rows + flywheel stub after residual cl
    expect(screen.getAllByText("fsess_launch_1").length).toBeGreaterThanOrEqual(1);
    // Spawn/parent appear in identity rows and ResearchContextPanel meta
    expect(screen.getAllByText("spn_launch_1").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("launch-asset").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("reserved")).toBeTruthy();
    expect(screen.getByTestId("deep-research-selection").textContent).toContain(
      "content-addressable",
    );
    expect(screen.getByText(/not PDF/i)).toBeTruthy();
    expect(
      screen.getByTestId("deep-research-session-host").getAttribute("data-view-format"),
    ).toBe("html");
  });

  it("links Open Write twin_seed handoff for selection+goal (qv)", () => {
    render(<DeepResearchSessionHost {...FIXTURE} />);
    const write = screen.getByTestId("deep-research-open-write");
    const href = write.getAttribute("href") || "";
    expect(href).toMatch(/^\/write\?twin_seed=antiek\.twin_write_seed\./);
    expect(href).not.toMatch(/html_draft=/);
    expect(write.getAttribute("data-has-twin-seed")).toBe("1");
    expect(write.getAttribute("data-view-format")).toBe("html");
    expect(write.textContent).toMatch(/Open Write \(twin seed\)/i);
    // Residual (acv): selection body → has-body true.
    expect(write.getAttribute("data-write-seed-has-body")).toBe("true");
    // Residual (ael): parent reading asset → seamless reading→research→Write path.
    expect(write.getAttribute("data-parent-asset-id")).toBe("launch-asset");
    expect(write.getAttribute("data-seamless-reading-research-write")).toBe(
      "true",
    );
    expect(write.getAttribute("data-spawn-id")).toBe("spn_launch_1");
  });

  it("Open Write has-body false when goal-only without selection (acv)", () => {
    render(
      <DeepResearchSessionHost
        session_id="fsess_goal"
        spawn_id="spn_goal"
        parent_asset_id="book-1"
        selection_text="  "
        goal="Goal only meta seed"
        view_format="html"
      />,
    );
    const write = screen.getByTestId("deep-research-open-write");
    expect(write.getAttribute("href") || "").toMatch(
      /^\/write\?twin_seed=antiek\.twin_write_seed\./,
    );
    expect(write.getAttribute("data-write-seed-has-body")).toBe("false");
  });

  it("hides Open Write when selection and goal are empty (qv)", () => {
    render(
      <DeepResearchSessionHost
        session_id="fsess_empty"
        spawn_id="spn_empty"
        parent_asset_id="book-1"
        selection_text="  "
        goal=""
        view_format="html"
      />,
    );
    expect(screen.queryByTestId("deep-research-open-write")).toBeNull();
  });

  it("prefills research tier from Settings wrestle (je)", async () => {
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
      <DeepResearchSessionHost
        session_id="fsess_1"
        spawn_id="spn_1"
        parent_asset_id="book-1"
        selection_text="Attention is routing."
        view_format="html"
      />,
    );
    await waitFor(() => {
      const mount = screen.getByTestId("deep-research-budget-mount");
      expect(mount.getAttribute("data-depth-prefill")).toBe("installed");
      expect(mount.getAttribute("data-research-tier")).toBe("wrestle");
    });
    expect(screen.getByTestId("deep-research-depth-prefill").textContent).toMatch(
      /installed.*wrestle/i,
    );
  });

  it("session payload research_tier wins over Settings prefill (jk)", async () => {
    fetchDepthTiers.mockResolvedValue({
      active_depth_tier: "flash",
      active_preset: null,
      presets: [],
      projection_hints: null,
      view_format: "html",
      settings_panel: "depth_tier_presets",
      source: "test",
      notes: [],
    });
    render(
      <DeepResearchSessionHost
        session_id="fsess_sess"
        spawn_id="spn_sess"
        parent_asset_id="book-1"
        selection_text="Reserved wrestle spawn."
        view_format="html"
        research_tier="wrestle"
      />,
    );
    const chrome = screen.getByTestId("deep-research-session-tier");
    expect(chrome.getAttribute("data-session-research-tier")).toBe("wrestle");
    expect(chrome.getAttribute("data-depth-prefill")).toBe("session");
    expect(chrome.textContent).toMatch(/wrestle/i);
    const mount = screen.getByTestId("deep-research-budget-mount");
    expect(mount.getAttribute("data-depth-prefill")).toBe("session");
    expect(mount.getAttribute("data-research-tier")).toBe("wrestle");
    // Session payload wins for host budget even if child panels also fetch Settings.
    expect(screen.getByTestId("deep-research-depth-prefill").textContent).toMatch(
      /session.*wrestle/i,
    );
  });

  it("mounts ResearchLaunchBudgetPanel for goal/selection (bx)", async () => {
    render(<DeepResearchSessionHost {...FIXTURE} />);
    const mount = screen.getByTestId("deep-research-budget-mount");
    expect(mount).toBeTruthy();
    expect(mount.getAttribute("data-view-format")).toBe("html");
    // Host budget + nested engagement panels may each mount a budget panel.
    expect(
      screen.getAllByTestId("research-launch-budget-panel").length,
    ).toBeGreaterThanOrEqual(1);
    expect(
      mount.querySelector('[data-testid="research-launch-budget-panel"]'),
    ).toBeTruthy();
  });

  it("quarantines legacy spawn merge for an owner-native session", () => {
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(screen.queryByTestId("deep-research-spawn-merge-mount")).toBeNull();
    expect(screen.queryByTestId("spawn-merge-panel-stub")).toBeNull();
    expect(screen.getByTestId("durable-session-merge-panel")).toBeTruthy();
  });

  it("keeps durable session merge independent of the legacy tier-gated panel", () => {
    render(
      <DeepResearchSessionHost {...FIXTURE} research_tier="wrestle" />,
    );
    expect(screen.getByTestId("durable-session-merge-panel")).toBeTruthy();
    expect(screen.queryByTestId("spawn-merge-panel-stub")).toBeNull();
  });

  it("mounts PublicationAttachPanel when spawn present (ck)", () => {
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(
      screen.getByTestId("deep-research-publication-attach-mount"),
    ).toBeTruthy();
    expect(screen.getByTestId("publication-attach-panel-stub").textContent).toMatch(
      /spn_launch_1/,
    );
  });

  it("wires session researchTier into PublicationAttachPanel (lz)", () => {
    render(
      <DeepResearchSessionHost {...FIXTURE} research_tier="wrestle" />,
    );
    const stub = screen.getByTestId("publication-attach-panel-stub");
    expect(stub.getAttribute("data-research-tier")).toBe("wrestle");
    expect(stub.textContent).toMatch(/tier=wrestle/);
  });

  it("mounts SessionFlywheelPanel when session present (cl)", () => {
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(screen.getByTestId("deep-research-flywheel-mount")).toBeTruthy();
    expect(screen.getByTestId("session-flywheel-panel-stub").textContent).toMatch(
      /fsess_launch_1/,
    );
  });

  it("remounts research context after flywheel complete notify (ee)", () => {
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(
      screen
        .getByTestId("deep-research-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("0");
    fireEvent.click(screen.getByTestId("session-flywheel-notify"));
    expect(
      screen
        .getByTestId("deep-research-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("1");
  });

  it("enables merge immediately after in-place session completion", () => {
    render(<DeepResearchSessionHost {...FIXTURE} status="reserved" />);
    const preview = screen.getByTestId("preview-session-merge") as HTMLButtonElement;
    expect(preview.disabled).toBe(true);
    fireEvent.click(screen.getByTestId("session-flywheel-notify"));
    expect(preview.disabled).toBe(false);
    expect(screen.getByTestId("session-merge-readiness").textContent).toMatch(
      /1 of 1 selected sessions are complete/i,
    );
  });

  it("remounts research context after spawn merge notify (eh)", () => {
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(
      screen
        .getByTestId("deep-research-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("0");
    fireEvent.click(screen.getByTestId("publication-attach-notify"));
    expect(
      screen
        .getByTestId("deep-research-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("1");
  });

  it("remounts twin notes with context refresh key (fa)", () => {
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(
      screen
        .getByTestId("deep-research-twins-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("0");
    fireEvent.click(screen.getByTestId("publication-attach-notify"));
    expect(
      screen
        .getByTestId("deep-research-twins-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("1");
    expect(
      screen
        .getByTestId("deep-research-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("1");
  });

  it("loads progress without silently seeding an authenticated session", () => {
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(screen.getByTestId("deep-research-progress-mount")).toBeTruthy();
    expect(screen.getByTestId("research-progress-panel-stub").textContent).toMatch(
      /spn_launch_1:auto=true:seed=false:poll=4000/,
    );
    // Residual (jo): default deep → 4s poll.
    expect(
      screen.getByTestId("deep-research-progress-tier-poll").getAttribute(
        "data-poll-ms",
      ),
    ).toBe("4000");
  });

  it("wrestle research_tier uses 8s progress poll cadence (jo)", () => {
    render(
      <DeepResearchSessionHost
        {...FIXTURE}
        research_tier="wrestle"
      />,
    );
    const wrap = screen.getByTestId("deep-research-progress-tier-poll");
    expect(wrap.getAttribute("data-research-tier")).toBe("wrestle");
    expect(wrap.getAttribute("data-poll-ms")).toBe("8000");
    expect(screen.getByTestId("research-progress-panel-stub").textContent).toMatch(
      /:poll=8000/,
    );
    // Residual (jq): progress panel receives researchTier.
    expect(
      screen.getByTestId("research-progress-panel-stub").getAttribute(
        "data-research-tier",
      ),
    ).toBe("wrestle");
  });

  it("mounts TwinNotesPanel with autoLoad (cq)", () => {
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(screen.getByTestId("deep-research-twins-mount")).toBeTruthy();
    expect(screen.getByTestId("twin-notes-panel-stub").textContent).toMatch(
      /launch-asset:auto=true/,
    );
  });

  it("parses research_domains from goal into twin domainSubjects (aoe)", () => {
    render(
      <DeepResearchSessionHost
        {...FIXTURE}
        goal="Twin chase on launch-asset: 2 note(s) · research_domains=heat,signal_processing"
      />,
    );
    const host = screen.getByTestId("deep-research-session-host");
    expect(host.getAttribute("data-research-domains")).toBe(
      "heat,signal_processing",
    );
    expect(
      screen
        .getByTestId("twin-notes-panel-stub")
        .getAttribute("data-domain-subjects"),
    ).toBe("heat,signal_processing");
    // ResearchContextPanel (real) stamps domain subjects on query controls.
    const ctx = screen.getByTestId("research-context-query-controls");
    const ctxDomains = String(ctx.getAttribute("data-domain-subjects") || "");
    expect(ctxDomains).toContain("heat");
    expect(ctxDomains).toContain("signal_processing");
    expect(
      screen.getByTestId("research-context-domain-search-coverage"),
    ).toBeTruthy();
    // Residual (aol): operator-visible Research domains chrome.
    const domainChrome = screen.getByTestId("deep-research-session-domains");
    expect(domainChrome.getAttribute("data-research-domains")).toBe(
      "heat,signal_processing",
    );
    expect(domainChrome.getAttribute("data-domain-count")).toBe("2");
    expect(domainChrome.textContent).toMatch(/heat/i);
  });

  it("remounts research context after twin promote notify (ec)", () => {
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(
      screen
        .getByTestId("deep-research-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("0");
    fireEvent.click(screen.getByTestId("twin-notes-promote-notify"));
    expect(
      screen
        .getByTestId("deep-research-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("1");
  });

  it("remounts research context after publication attach notify (ed)", () => {
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(
      screen
        .getByTestId("deep-research-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("0");
    fireEvent.click(screen.getByTestId("publication-attach-notify"));
    expect(
      screen
        .getByTestId("deep-research-context-refresh")
        .getAttribute("data-refresh-key"),
    ).toBe("1");
  });

  it("mounts DecisionTreeDriverBadge (cw)", () => {
    render(<DeepResearchSessionHost {...FIXTURE} />);
    // Residual (lz): host + PublicationAttach each mount a driver badge.
    expect(
      screen.getAllByTestId("decision-tree-driver-badge").length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("omits SpawnMergePanel without parent_asset_id", () => {
    const { parent_asset_id: _drop, ...noParent } = FIXTURE;
    render(<DeepResearchSessionHost {...noParent} />);
    expect(screen.queryByTestId("deep-research-spawn-merge-mount")).toBeNull();
  });

  it("exposes expand full / restore floating controls (ce)", async () => {
    useWindows.getState().reset();
    const id = openWindow(
      DEEP_RESEARCH_WINDOW_KIND,
      { ...FIXTURE },
      { id: "wdr_fsess_launch_1", title: "Deep research", mode: "floating" },
    );
    render(
      <DeepResearchSessionHost
        {...FIXTURE}
        session_id="fsess_launch_1"
        __windowId={id}
      />,
    );
    expect(screen.getByTestId("deep-research-mode-controls")).toBeTruthy();
    const expand = screen.getByTestId("deep-research-expand-full");
    const restore = screen.getByTestId("deep-research-restore-floating");
    expect((expand as HTMLButtonElement).disabled).toBe(false);
    expect((restore as HTMLButtonElement).disabled).toBe(true);
    // Residual (aqw): float|full path stamps + operator path choices chrome.
    expect(expand.getAttribute("data-view-mode-target")).toBe("full");
    expect(restore.getAttribute("data-view-mode-target")).toBe("floating");
    expect(expand.getAttribute("data-view-format")).toBe("html");
    // Residual (asg): float|full CTAs stamp pathChoices.float_full_ready.
    expect(expand.getAttribute("data-float-full-ready")).toBe("true");
    expect(restore.getAttribute("data-float-full-ready")).toBe("true");
    expect(expand.getAttribute("data-html-first")).toBe("true");
    const path = screen.getByTestId("deep-research-path-choices");
    expect(path.getAttribute("data-html-first")).toBe("true");
    expect(path.getAttribute("data-float-full-ready")).toBe("true");
    expect(path.getAttribute("data-draft-merge-ready")).toBe("true");
    expect(path.getAttribute("data-into-parent-ready")).toBe("true");
    expect(path.getAttribute("data-path-choices-source")).toBe(
      "researchPathChoicesReadiness",
    );
    expect(path.textContent).toMatch(/float\|full/i);
    expect(path.textContent).toMatch(/into parent/i);
    expect(path.textContent).toMatch(/1 selected|ready/i);
    fireEvent.click(expand);
    await waitFor(() => {
      expect(useWindows.getState().windows[id]?.mode).toBe("full");
    });
  });

  it("previews then confirms a receipt-bound session merge", async () => {
    mergeEngagementSessions
      .mockResolvedValueOnce({
        mode: "draft_combined",
        parent_asset_id: "launch-asset",
        document_id: "draft_launch",
        source_spawn_ids: ["spn_launch_1"],
        source_session_ids: ["fsess_launch_1"],
        sections_merged: 2,
        document_sha256: "b".repeat(64),
        parent_revision_sha256: "a".repeat(64),
        result_parent_sha256: "a".repeat(64),
        draft_leaves_parent: true,
        view_format: "html",
        html: "<article><p>Safe draft preview</p></article>",
      })
      .mockResolvedValueOnce({
        mode: "into_parent",
        parent_asset_id: "launch-asset",
        document_id: "launch-asset",
        source_spawn_ids: ["spn_launch_1"],
        source_session_ids: ["fsess_launch_1"],
        sections_merged: 2,
        document_sha256: "b".repeat(64),
        parent_revision_sha256: "a".repeat(64),
        result_parent_sha256: "b".repeat(64),
        draft_leaves_parent: false,
        view_format: "html",
        merge_receipt_id: "mrcpt_0123456789abcdef01234567",
        merge_receipt_state: "applied",
      });
    render(<DeepResearchSessionHost {...FIXTURE} status="complete" />);
    fireEvent.click(screen.getByTestId("preview-session-merge"));
    await screen.findByTestId("session-merge-draft-preview");
    const confirm = screen.getByTestId("confirm-session-merge");
    expect((confirm as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(confirm);
    await screen.findByTestId("session-merge-receipt");
    expect(mergeEngagementSessions).toHaveBeenCalledTimes(2);
    expect(mergeEngagementSessions.mock.calls[1][0]).toEqual(
      expect.objectContaining({
        mode: "into_parent",
        confirm_parent_write: true,
        expected_parent_sha256: "a".repeat(64),
      }),
    );
    expect(mergeEngagementSessions.mock.calls[1][0].idempotency_key).toMatch(
      /^browser-merge-/,
    );
  });

  it("rotates receipt authority for a new preview and retains it for retry", async () => {
    listOwnedEngagementSessions.mockResolvedValueOnce({
      owner_id: "alice",
      sessions: [
        { ...FIXTURE, status: "complete", source_references: [] },
        {
          ...FIXTURE,
          session_id: "fsess_second_receipt",
          spawn_id: "spn_second_receipt",
          goal: "Second receipt selection",
          status: "complete",
          source_references: [],
        },
      ],
      count: 2,
      next_cursor: null,
      view_format: "html",
    });
    const draft = (revision: string) => ({
      mode: "draft_combined",
      parent_revision_sha256: revision,
      html: "<article>draft</article>",
    });
    mergeEngagementSessions
      .mockResolvedValueOnce(draft("a".repeat(64)))
      .mockResolvedValueOnce({ mode: "into_parent", merge_receipt_state: "applied" })
      .mockResolvedValueOnce(draft("b".repeat(64)))
      .mockRejectedValueOnce(new Error("ambiguous network failure"))
      .mockResolvedValueOnce({ mode: "into_parent", merge_receipt_state: "applied" });
    render(<DeepResearchSessionHost {...FIXTURE} status="complete" />);
    await screen.findByText(/2 owned · 1 selected/i);

    fireEvent.click(screen.getByTestId("preview-session-merge"));
    await screen.findByTestId("session-merge-draft-preview");
    fireEvent.click(screen.getByTestId("confirm-session-merge"));
    await waitFor(() => expect(mergeEngagementSessions).toHaveBeenCalledTimes(2));
    const firstKey = mergeEngagementSessions.mock.calls[1][0].idempotency_key;

    fireEvent.click(screen.getByLabelText("Select Second receipt selection"));
    fireEvent.click(screen.getByTestId("preview-session-merge"));
    await waitFor(() => expect(mergeEngagementSessions).toHaveBeenCalledTimes(3));
    fireEvent.click(screen.getByTestId("confirm-session-merge"));
    await screen.findByRole("alert");
    const secondKey = mergeEngagementSessions.mock.calls[3][0].idempotency_key;
    expect(secondKey).not.toBe(firstKey);
    fireEvent.click(screen.getByTestId("confirm-session-merge"));
    await waitFor(() => expect(mergeEngagementSessions).toHaveBeenCalledTimes(5));
    expect(mergeEngagementSessions.mock.calls[4][0].idempotency_key).toBe(secondKey);
  });

  it("excludes incomplete sibling sessions from merge authority", async () => {
    useWindows.getState().reset();
    openWindow(
      DEEP_RESEARCH_WINDOW_KIND as keyof typeof WINDOW_PAGES,
      {
        owner_id: "alice",
        session_id: "fsess_incomplete",
        spawn_id: "spn_incomplete",
        parent_asset_id: "launch-asset",
        selection_text: "unfinished",
        status: "reserved",
        view_format: "html",
        investigation_id: "inv_incomplete",
      },
      { id: "wdr_fsess_incomplete", mode: "floating" },
    );
    mergeEngagementSessions.mockResolvedValueOnce({
      mode: "draft_combined",
      parent_revision_sha256: "a".repeat(64),
      html: "<article>complete only</article>",
    });
    listOwnedEngagementSessions.mockResolvedValueOnce({
      owner_id: "alice",
      sessions: [
        { ...FIXTURE, status: "complete", source_references: [] },
        {
          ...FIXTURE,
          session_id: "fsess_incomplete",
          spawn_id: "spn_incomplete",
          selection_text: "unfinished",
          goal: "Unfinished sibling",
          status: "reserved",
          source_references: [],
        },
      ],
      count: 2,
      next_cursor: null,
      status_filter: null,
      view_format: "html",
    });
    render(<DeepResearchSessionHost {...FIXTURE} status="complete" />);
    await screen.findByText(/2 owned · 1 selected/i);
    fireEvent.click(screen.getByLabelText("Select Unfinished sibling"));
    expect(screen.getByTestId("session-merge-readiness").textContent).toMatch(
      /1 of 2 selected sessions are complete/i,
    );
    fireEvent.click(screen.getByTestId("preview-session-merge"));
    await waitFor(() => expect(mergeEngagementSessions).toHaveBeenCalledOnce());
    expect(mergeEngagementSessions.mock.calls[0][0].session_ids).toEqual([
      "fsess_launch_1",
    ]);
  });

  it("path choices require parent+spawn for draft/into-parent readiness (aqw)", () => {
    const { parent_asset_id: _drop, ...noParent } = FIXTURE;
    render(
      <DeepResearchSessionHost
        {...noParent}
        session_id="fsess_no_parent"
      />,
    );
    const path = screen.getByTestId("deep-research-path-choices");
    expect(path.getAttribute("data-draft-merge-ready")).toBe("false");
    expect(path.getAttribute("data-into-parent-ready")).toBe("false");
    expect(path.getAttribute("data-parent-bound")).toBe("false");
    expect(path.getAttribute("data-path-choices-source")).toBe(
      "researchPathChoicesReadiness",
    );
    expect(path.textContent).toMatch(/bind parent/i);
  });

  it("mounts ResearchContextPanel with parent asset and spawn identity", () => {
    const first = render(<DeepResearchSessionHost {...FIXTURE} />);
    const mount = screen.getByTestId("deep-research-research-context-mount");
    expect(mount).toBeTruthy();
    expect(mount.getAttribute("data-view-format")).toBe("html");
    // Shipped panel chrome (not a reimplementation)
    expect(screen.getByRole("heading", { name: /research context/i })).toBeTruthy();
    expect(mount.textContent).toContain("launch-asset");
    expect(screen.getByTestId("load-research-context")).toBeTruthy();
    first.unmount();
    // Double-run: remount still binds panel
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(screen.getByTestId("deep-research-research-context-mount")).toBeTruthy();
    expect(screen.getByTestId("load-research-context")).toBeTruthy();
  });

  it("passes session research_tier into ResearchContext host prefill (aml)", () => {
    render(
      <DeepResearchSessionHost {...FIXTURE} research_tier="wrestle" />,
    );
    const prefill = screen.getByTestId("research-context-host-tier-prefill");
    expect(prefill.getAttribute("data-host-tier")).toBe("wrestle");
    expect(prefill.textContent).toMatch(/Host depth prefill/i);
    expect(prefill.textContent).toMatch(/wrestle/i);
  });

  it("omits ResearchContextPanel when parent_asset_id is missing", () => {
    const { parent_asset_id: _drop, ...noParent } = FIXTURE;
    render(<DeepResearchSessionHost {...noParent} />);
    expect(screen.queryByTestId("deep-research-research-context-mount")).toBeNull();
  });

  it("quarantines the legacy collective panel for owner-native sessions", () => {
    useWindows.getState().reset();
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(screen.queryByTestId("deep-research-collective-mount")).toBeNull();
    expect(
      (screen.getByTestId("build-session-collective") as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("builds collective context from other owner-native session windows", async () => {
    useWindows.getState().reset();
    fetchSessionsCollective.mockResolvedValueOnce({
      session_ids: ["fsess_launch_1", "fsess_other"],
      html: "<!doctype html><title>Owner collective</title>",
    });
    listOwnedEngagementSessions.mockResolvedValueOnce({
      owner_id: "alice",
      sessions: [
        { ...FIXTURE, source_references: [] },
        {
          ...FIXTURE,
          session_id: "fsess_other",
          spawn_id: "spn_other_2",
          goal: "Other session",
          selection_text: "other",
          source_references: [],
        },
      ],
      count: 2,
      next_cursor: null,
      status_filter: null,
      view_format: "html",
    });
    openWindow(
      DEEP_RESEARCH_WINDOW_KIND as keyof typeof WINDOW_PAGES,
      {
        session_id: "fsess_other",
        owner_id: "alice",
        spawn_id: "spn_other_2",
        parent_asset_id: "launch-asset",
        selection_text: "other",
        status: "reserved",
        view_format: "html",
        investigation_id: "inv_other",
      },
      { id: "wdr_fsess_other", mode: "floating" },
    );
    render(
      <DeepResearchSessionHost
        {...FIXTURE}
        available_spawn_ids={["spn_extra_3"]}
      />,
    );
    await screen.findByText(/2 owned · 1 selected/i);
    expect(
      (screen.getByTestId("build-session-collective") as HTMLButtonElement).disabled,
    ).toBe(true);
    fireEvent.click(screen.getByLabelText("Select Other session"));
    fireEvent.click(screen.getByTestId("build-session-collective"));
    await waitFor(() => expect(fetchSessionsCollective).toHaveBeenCalledOnce());
    expect(fetchSessionsCollective).toHaveBeenCalledWith({
      session_ids: ["fsess_launch_1", "fsess_other"],
      include_twin_preview: true,
      allow_cross_asset: false,
      include_prompt_block: true,
      include_html: true,
    });
    expect(await screen.findByTestId("session-collective-preview")).toBeTruthy();
    expect(screen.queryByTestId("deep-research-collective-mount")).toBeNull();
  });

  it("requires explicit cross-asset consent and sends only checked sessions", async () => {
    listOwnedEngagementSessions.mockResolvedValueOnce({
      owner_id: "alice",
      sessions: [
        { ...FIXTURE, source_references: [] },
        {
          ...FIXTURE,
          session_id: "fsess_cross_asset",
          parent_asset_id: "other-asset",
          goal: "Compare another paper",
          source_references: [],
        },
        {
          ...FIXTURE,
          session_id: "fsess_unselected",
          parent_asset_id: "third-asset",
          goal: "Leave this out",
          source_references: [],
        },
      ],
      count: 3,
      next_cursor: null,
      status_filter: null,
      view_format: "html",
    });
    fetchSessionsCollective.mockResolvedValueOnce({ html: "<article>Exact preview</article>" });
    render(<DeepResearchSessionHost {...FIXTURE} />);
    await screen.findByText(/3 owned · 1 selected/i);
    fireEvent.click(screen.getByLabelText("Select Compare another paper"));
    const build = screen.getByTestId("build-session-collective") as HTMLButtonElement;
    expect(build.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/Include selected sessions from 2 assets/i));
    expect(build.disabled).toBe(false);
    fireEvent.click(build);
    await waitFor(() => expect(fetchSessionsCollective).toHaveBeenCalledOnce());
    expect(fetchSessionsCollective).toHaveBeenCalledWith({
      session_ids: ["fsess_launch_1", "fsess_cross_asset"],
      include_twin_preview: true,
      allow_cross_asset: true,
      include_prompt_block: true,
      include_html: true,
    });
  });

  it("loads owner discovery incrementally instead of walking every page on mount", async () => {
    listOwnedEngagementSessions
      .mockResolvedValueOnce({
        owner_id: "alice",
        sessions: [{ ...FIXTURE, source_references: [] }],
        count: 1,
        next_cursor: "fsess_launch_1",
        view_format: "html",
      })
      .mockResolvedValueOnce({
        owner_id: "alice",
        sessions: [
          {
            ...FIXTURE,
            session_id: "fsess_page_two",
            goal: "Page two session",
            source_references: [],
          },
        ],
        count: 1,
        next_cursor: null,
        view_format: "html",
      });
    render(<DeepResearchSessionHost {...FIXTURE} />);
    const loadMore = await screen.findByText("Load more sessions");
    expect(listOwnedEngagementSessions).toHaveBeenCalledTimes(1);
    fireEvent.click(loadMore);
    await screen.findByText("Page two session");
    expect(listOwnedEngagementSessions).toHaveBeenNthCalledWith(2, {
      cursor: "fsess_launch_1",
      limit: 100,
    });
    expect(screen.queryByText("Load more sessions")).toBeNull();
  });

  it("retries a failed later page without dropping loaded selected sessions", async () => {
    const pageTwo = {
      ...FIXTURE,
      session_id: "fsess_page_two_selected",
      goal: "Keep selected page two",
      source_references: [],
    };
    listOwnedEngagementSessions
      .mockResolvedValueOnce({
        sessions: [{ ...FIXTURE, source_references: [] }],
        next_cursor: "fsess_page_one_cursor",
      })
      .mockResolvedValueOnce({
        sessions: [pageTwo],
        next_cursor: "fsess_page_two_cursor",
      })
      .mockRejectedValueOnce(new Error("later page offline"))
      .mockResolvedValueOnce({ sessions: [], next_cursor: null });
    render(<DeepResearchSessionHost {...FIXTURE} />);
    fireEvent.click(await screen.findByText("Load more sessions"));
    const selected = await screen.findByLabelText("Select Keep selected page two");
    fireEvent.click(selected);
    fireEvent.click(screen.getByText("Load more sessions"));
    const retry = await screen.findByText("Retry discovery");
    expect((selected as HTMLInputElement).checked).toBe(true);
    fireEvent.click(retry);
    await waitFor(() => expect(listOwnedEngagementSessions).toHaveBeenCalledTimes(4));
    expect(screen.getByLabelText("Select Keep selected page two")).toBeTruthy();
    expect(
      (screen.getByLabelText("Select Keep selected page two") as HTMLInputElement).checked,
    ).toBe(true);
  });

  it("invalidates draft and confirmation authority when selection changes", async () => {
    listOwnedEngagementSessions.mockResolvedValueOnce({
      owner_id: "alice",
      sessions: [
        { ...FIXTURE, status: "complete", source_references: [] },
        {
          ...FIXTURE,
          session_id: "fsess_same_parent",
          spawn_id: "spn_same_parent",
          goal: "Second completed session",
          status: "complete",
          source_references: [],
        },
      ],
      count: 2,
      next_cursor: null,
      status_filter: null,
      view_format: "html",
    });
    mergeEngagementSessions.mockResolvedValueOnce({
      mode: "draft_combined",
      parent_revision_sha256: "a".repeat(64),
      html: "<article>Reviewed pair</article>",
    });
    render(<DeepResearchSessionHost {...FIXTURE} status="complete" />);
    await screen.findByText(/2 owned · 1 selected/i);
    fireEvent.click(screen.getByLabelText("Select Second completed session"));
    fireEvent.click(screen.getByTestId("preview-session-merge"));
    await screen.findByTestId("session-merge-draft-preview");
    expect((screen.getByTestId("confirm-session-merge") as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(screen.getByLabelText("Select Second completed session"));
    expect(screen.queryByTestId("session-merge-draft-preview")).toBeNull();
    expect((screen.getByTestId("confirm-session-merge") as HTMLButtonElement).disabled).toBe(true);
  });

  it("discards late collective and draft responses after selection drift", async () => {
    let resolveCollective!: (value: { html: string }) => void;
    let resolveDraft!: (value: {
      mode: string;
      parent_revision_sha256: string;
      html: string;
    }) => void;
    fetchSessionsCollective.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveCollective = resolve;
      }),
    );
    mergeEngagementSessions.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveDraft = resolve;
      }),
    );
    listOwnedEngagementSessions.mockResolvedValueOnce({
      owner_id: "alice",
      sessions: [
        { ...FIXTURE, status: "complete", source_references: [] },
        {
          ...FIXTURE,
          session_id: "fsess_late",
          spawn_id: "spn_late",
          goal: "Late response sibling",
          status: "complete",
          source_references: [],
        },
      ],
      count: 2,
      next_cursor: null,
      view_format: "html",
    });
    render(<DeepResearchSessionHost {...FIXTURE} status="complete" />);
    await screen.findByText(/2 owned · 1 selected/i);
    const sibling = screen.getByLabelText("Select Late response sibling");
    fireEvent.click(sibling);
    fireEvent.click(screen.getByTestId("build-session-collective"));
    fireEvent.click(screen.getByTestId("preview-session-merge"));
    fireEvent.click(sibling);
    resolveCollective({ html: "<article>stale collective</article>" });
    resolveDraft({
      mode: "draft_combined",
      parent_revision_sha256: "a".repeat(64),
      html: "<article>stale draft</article>",
    });
    await waitFor(() => expect(screen.getByText("2 owned · 1 selected")).toBeTruthy());
    expect(screen.queryByTestId("session-collective-preview")).toBeNull();
    expect(screen.queryByTestId("session-merge-draft-preview")).toBeNull();
    expect((screen.getByTestId("confirm-session-merge") as HTMLButtonElement).disabled).toBe(true);
  });

  it("reconciles a selected sibling completing in another owned window", async () => {
    let resolveDraft!: (value: {
      mode: string;
      parent_revision_sha256: string;
      html: string;
    }) => void;
    mergeEngagementSessions.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveDraft = resolve;
      }),
    );
    listOwnedEngagementSessions.mockResolvedValueOnce({
      owner_id: "alice",
      sessions: [
        { ...FIXTURE, status: "complete", source_references: [] },
        {
          ...FIXTURE,
          session_id: "fsess_live_sibling",
          spawn_id: "spn_live_sibling",
          goal: "Live sibling",
          status: "reserved",
          source_references: [],
        },
      ],
      count: 2,
      next_cursor: null,
      view_format: "html",
    });
    openWindow(
      DEEP_RESEARCH_WINDOW_KIND as keyof typeof WINDOW_PAGES,
      {
        ...FIXTURE,
        session_id: "fsess_live_sibling",
        spawn_id: "spn_live_sibling",
        status: "reserved",
      },
      { id: "wdr_live_sibling", mode: "floating" },
    );
    render(<DeepResearchSessionHost {...FIXTURE} status="complete" />);
    await screen.findByText(/2 owned · 1 selected/i);
    fireEvent.click(screen.getByLabelText("Select Live sibling"));
    expect(screen.getByTestId("session-merge-readiness").textContent).toMatch(
      /1 of 2 selected sessions are complete/i,
    );
    fireEvent.click(screen.getByTestId("preview-session-merge"));
    useWindows.getState().patchPayload("wdr_live_sibling", { status: "complete" });
    await waitFor(() =>
      expect(screen.getByTestId("session-merge-readiness").textContent).toMatch(
        /2 of 2 selected sessions are complete/i,
      ),
    );
    expect(screen.getAllByText(/complete · mergeable/i).length).toBe(2);
    resolveDraft({
      mode: "draft_combined",
      parent_revision_sha256: "a".repeat(64),
      html: "<article>stale one-session draft</article>",
    });
    await waitFor(() => expect(mergeEngagementSessions).toHaveBeenCalledOnce());
    expect(screen.queryByTestId("session-merge-draft-preview")).toBeNull();
    expect((screen.getByTestId("confirm-session-merge") as HTMLButtonElement).disabled).toBe(true);
  });

  it("does not grant recent global spawn ids authority in a session collective", () => {
    useWindows.getState().reset();
    clearRecentDeepResearchSpawnIds();
    pushRecentDeepResearchSpawnId("spn_chased_closed");
    render(<DeepResearchSessionHost {...FIXTURE} />);
    expect(screen.queryByTestId("deep-research-collective-mount")).toBeNull();
    expect(
      screen
        .getByTestId("durable-session-merge-panel")
        .getAttribute("data-session-count"),
    ).toBe("1");
    clearRecentDeepResearchSpawnIds();
  });

  it("omits CollectiveResearchPanel when no spawn ids available", () => {
    useWindows.getState().reset();
    const { spawn_id: _s, ...noSpawn } = FIXTURE;
    render(<DeepResearchSessionHost {...noSpawn} />);
    expect(screen.queryByTestId("deep-research-collective-mount")).toBeNull();
  });

  it("kind is window-eligible in WINDOW_PAGES registry", () => {
    expect(isWindowEligible(DEEP_RESEARCH_WINDOW_KIND)).toBe(true);
    expect(WINDOW_PAGES[DEEP_RESEARCH_WINDOW_KIND]?.title).toMatch(/deep research/i);
    expect(WINDOW_PAGES[DEEP_RESEARCH_WINDOW_KIND]?.renderer).toBeTruthy();
  });

  it("openWindow registers hostable deep_research_session window with payload", () => {
    useWindows.getState().reset();
    const id = openWindow(
      DEEP_RESEARCH_WINDOW_KIND as keyof typeof WINDOW_PAGES,
      FIXTURE as unknown as Record<string, unknown>,
      { id: "wdr_fsess_launch_1", mode: "floating" },
    );
    expect(id).toBe("wdr_fsess_launch_1");
    const win = useWindows.getState().windows[id];
    expect(win).toBeTruthy();
    expect(win.kind).toBe(DEEP_RESEARCH_WINDOW_KIND);
    expect(win.payload.session_id).toBe("fsess_launch_1");
    expect(win.payload.parent_asset_id).toBe("launch-asset");
    expect(win.payload.view_format).toBe("html");
    // Second open focuses same id
    const again = openWindow(
      DEEP_RESEARCH_WINDOW_KIND as keyof typeof WINDOW_PAGES,
      FIXTURE as unknown as Record<string, unknown>,
      { id: "wdr_fsess_launch_1" },
    );
    expect(again).toBe(id);
  });
});
