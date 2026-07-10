/**
 * CollectiveResearchPanel — multi-select deep-research instances → one unit.
 *
 * Operator selects multiple spawn ids (from floating sessions) and can:
 * 1. Merge them via /engagement/collective into a cohesive prompt block
 * 2. Merge them into a draft-combined or parent document via /engagement/merge
 * 3. Residual (cf): Create written analysis draft (collective + draft document)
 * 4. Residual (dc): Continue the collective prompt as a new floating deep
 *    research session (cohesive unit re-entry).
 * 5. Residual (di): budget projection + soft-gate on continue-as-unit.
 * 6. Residual (em): auto-open draft_combined / written-analysis HTML via shared
 *    openMergedResearchWindow (parity with spawn merge el); into_parent manual.
 * 7. Residual (eo): seed twin notes on draft_combined document merge (parity
 *    with SpawnMergePanel cp / written-analysis ch); into_parent seeds too so
 *    the recursive note-taker always tracks the merge target.
 * 8. Residual (ep): onDocMerged notifies parent (DR host) to remount research
 *    context after document merge / written analysis (+ twin seed).
 * 9. Residual (ey): continue cohesive unit as full working-region window as
 *    well as floating (parity with ResearchThis et / hosted es).
 * 10. Residual (fn): Open Write handoff for merged draft document_id (fl/fm).
 * 25. Residual (qe): dual handoff html_draft + twin_seed on Open Write (parity qd).
 * 11. Residual (hm): collective-unit-metrics machine attrs for multi-spawn
 *     cohesive unit audit (parity twin/flywheel/progress metrics).
 * 12. Residual (ig): Settings deep-link for driver + budget before continue.
 * 13. Residual (jf): prefill researchTier from Settings depth-tier (parity je).
 * 14. Residual (ke): after merge, adopt unit.recommended_research_tier
 *     (depth-max of member spawn tiers) for continue-as-unit budget.
 * 15. Residual (lg): DecisionTreeDriverBadge with researchTier for model+depth.
 * 26. Residual (qg): DecisionTreeDriverBadge promptText from unit prompt_block
 *     (or selected spawn ids) for budget projection foresight (parity pg–pj).
 * 16. Residual (nk): select-all / invert / clear multi-select helpers
 *     (parity TwinNotes multi-select path for cohesive unit assembly).
 * 17. Residual (nl): dual-gate L1–L4 checklist deep-link for L6 live multi-
 *     agent collective prep (never enables injectors).
 * 18. Residual (ob): available list may include recent closed-window spawns
 *     (twin chase → collective cohesive unit without losing ids).
 * 19. Residual (oc): Clear recent closed-window spawns control (session ring).
 * 20. Residual (of): mark available rows from recent_ring (closed chase/float)
 *     so operators can see which multi-select ids survive window close.
 * 21. Residual (og): Select recent only — one-click multi-select of recent_ring
 *     rows (twin-chase batch merge path).
 * 29. Residual (ue): Select open only — multi-select currently open
 *     deep_research_session windows (excludes closed recent-only ids).
 * 30. Residual (vx): L6 live multi-agent council deferred honesty stamp
 *     (offline merge unit only · never silent live council).
 * 22. Residual (oj): surface usage_event from collective/merge on metrics
 *     (Antiek-bench recursive rewrite audit).
 * 23. Residual (ol): auto-select newest recent_ring spawn when selection is
 *     empty and preferredSpawnId is unset (chase → collective one less click).
 * 24. Residual (py / FUTURE-AGENT V2): persist cohesive unit membership
 * 27. Residual (ql): auto-restore last unit multi-select on mount when empty
 *     (preferredSpawnId wins; ≥2 restored ids for multi-select honesty).
 *     (spawn_ids by collective_id) in sessionStorage; restore last multi-select
 * Residual (adj): membership status stamps L6 live multi-agent deferred +
 * research_tier for offline cohesive unit honesty (parity panel L6 chrome).
 *     after continue-as-unit re-entry (intersection with available).
 * 28. Residual (tr): float|full cohesive unit prompt_block as HTML reading window
 *     without inventing a server document_id (parity research context pack sl).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchCollectiveResearch,
  mergeSpawnOutputs,
  seedTwinNotes,
  type CollectiveResponse,
  type MergeMode,
  type MergeProductResponse,
} from "../../api/engagement";
import { fetchDepthTiers } from "../../api/settings";
import { mapDepthTierToResearchTier } from "../../lib/researchTier";
import { launchFloatingDeepResearch } from "../../modes/Reading/launchFloatingDeepResearch";
import {
  getLastCollectiveUnitMembership,
  restoreCollectiveSelection,
  storeCollectiveUnitMembership,
  type CollectiveUnitMembership,
} from "../../workspace/collectiveUnitMembership";
import {
  clearRecentDeepResearchSpawnIds,
  listRecentDeepResearchSpawnIds,
} from "../../workspace/recentDeepResearchSpawns";
import type { WindowMode } from "../../workspace/windowsStore";
import { openWindow } from "../windows/openWindow";
import { DecisionTreeDriverBadge } from "./DecisionTreeDriverBadge";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
  type ResearchLaunchTier,
} from "./ResearchLaunchBudgetPanel";
import { openMergedResearchWindow } from "./SpawnMergePanel";
import {
  buildMergedDocWriteHref,
  plainTextFromHtml,
} from "../../workspace/twinWriteSeed";

/** Residual (tr): pure HTML body for cohesive unit prompt (no invented doc id). */
export function buildCollectiveUnitPromptHtml(opts: {
  collectiveId: string;
  promptBlock: string;
  spawnCount?: number | null;
  twinCount?: number | null;
  refCount?: number | null;
  researchTier?: string | null;
  spawnIds?: readonly string[] | null;
}): string {
  const escape = (s: string) =>
    String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  const cid = String(opts.collectiveId || "").trim() || "collective";
  const pb = String(opts.promptBlock || "").trim();
  const spawnIds = (opts.spawnIds || []).map((s) => String(s || "").trim()).filter(Boolean);
  return [
    `<article data-source="collective_unit_prompt" data-view-format="html" data-collective-id="${escape(cid)}">`,
    `<h1>Collective cohesive unit</h1>`,
    `<p class="meta">collective=${escape(cid)}`,
    opts.spawnCount != null ? ` · spawns=${opts.spawnCount}` : "",
    opts.twinCount != null ? ` · twins=${opts.twinCount}` : "",
    opts.refCount != null ? ` · refs=${opts.refCount}` : "",
    opts.researchTier ? ` · tier=${escape(String(opts.researchTier))}` : "",
    `</p>`,
    spawnIds.length
      ? `<p class="meta">spawn_ids=${escape(spawnIds.join(", "))}</p>`
      : "",
    pb ? `<section><h2>Cohesive prompt_block</h2><pre>${escape(pb)}</pre></section>` : "",
    `</article>`,
  ].join("");
}

export type CollectiveResearchPanelProps = {
  /** Pre-listed spawn ids available for multi-select */
  availableSpawnIds: string[];
  /** Parent asset for document merge (draft or into_parent). Required for doc merge. */
  parentAssetId?: string | null;
  /** Residual (cn): pre-select this spawn when present in available list. */
  preferredSpawnId?: string | null;
  /**
   * Residual (em): when true (default), open hosted HTML after draft_combined
   * document merge or written analysis. into_parent never auto-opens.
   */
  autoOpenDraft?: boolean;
  /** Residual (ep): after successful document merge or written analysis. */
  onDocMerged?: (result: MergeProductResponse) => void;
  /**
   * Residual (oc): parent re-reads recent spawn ring after clear
   * (sessionStorage does not fire same-tab storage events).
   */
  onRecentSpawnsCleared?: () => void;
  /**
   * Residual (of): spawn ids known to come from the session recent ring
   * (closed windows). When omitted, falls back to listRecentDeepResearchSpawnIds().
   */
  recentSpawnIds?: readonly string[] | null;
  /**
   * Residual (ue): spawn ids from currently open deep_research_session windows
   * (and current host spawn). When provided, enables Select open only so the
   * operator can merge live floats without closed recent-ring noise.
   */
  openSpawnIds?: readonly string[] | null;
  /**
   * Residual (ol): when true (default), auto-select newest recent_ring spawn
   * if selection is empty and preferredSpawnId is unset.
   */
  autoSelectNewestRecent?: boolean;
};

export function CollectiveResearchPanel({
  availableSpawnIds,
  parentAssetId = null,
  preferredSpawnId = null,
  autoOpenDraft = true,
  onDocMerged,
  onRecentSpawnsCleared,
  recentSpawnIds = null,
  openSpawnIds = null,
  autoSelectNewestRecent = true,
}: CollectiveResearchPanelProps) {
  const [selected, setSelected] = useState<string[]>([]);
  /** Residual (oc/of): local read of recent ring for chrome + origin badges. */
  const [recentRing, setRecentRing] = useState<string[]>(() =>
    listRecentDeepResearchSpawnIds(),
  );
  const recentCount = recentRing.length;
  /** Residual (ol): skip re-auto-selecting same newest after operator clears. */
  const lastAutoSelectedRecent = useRef<string | null>(null);
  /** Residual (ql): only auto-restore last unit once per mount (operator clear sticks). */
  const didAutoRestoreUnit = useRef(false);

  // Auto-select preferred spawn once when available (residual cn).
  useEffect(() => {
    const pref = (preferredSpawnId || "").trim();
    if (!pref) return;
    if (!availableSpawnIds.includes(pref)) return;
    setSelected((prev) => (prev.includes(pref) ? prev : [...prev, pref]));
  }, [preferredSpawnId, availableSpawnIds]);

  // Residual (ol): auto-select newest recent when no preferred + empty selection.
  useEffect(() => {
    if (!autoSelectNewestRecent) return;
    if ((preferredSpawnId || "").trim()) return;
    if (selected.length > 0) return;
    const newest = recentRing.find((id) => availableSpawnIds.includes(id));
    if (!newest) return;
    if (lastAutoSelectedRecent.current === newest) return;
    setSelected([newest]);
    lastAutoSelectedRecent.current = newest;
  }, [
    autoSelectNewestRecent,
    preferredSpawnId,
    selected.length,
    recentRing,
    availableSpawnIds,
  ]);

  // Residual (ql): auto-restore last cohesive unit multi-select once when
  // available list is known. Do not depend on selected.length so operator clear
  // does not re-restore. preferredSpawnId wins; require ≥2 restored ids.
  useEffect(() => {
    if (didAutoRestoreUnit.current) return;
    if ((preferredSpawnId || "").trim()) return;
    if (availableSpawnIds.length < 1) return;
    const last = getLastCollectiveUnitMembership();
    const restored = restoreCollectiveSelection(last, availableSpawnIds);
    if (restored.length < 2 || !last) return;
    didAutoRestoreUnit.current = true;
    setSelected((prev) => (prev.length > 0 ? prev : restored));
    setMembershipStatus({
      collective_id: last.collective_id,
      spawn_count: last.spawn_ids.length,
      restored_count: restored.length,
      action: "restored",
      document_id: last.document_id,
    });
  }, [preferredSpawnId, availableSpawnIds]);

  const [unit, setUnit] = useState<CollectiveResponse | null>(null);
  const [docMerge, setDocMerge] = useState<MergeProductResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [continueWindowId, setContinueWindowId] = useState<string | null>(null);
  const [autoOpenedWindowId, setAutoOpenedWindowId] = useState<string | null>(
    null,
  );
  const [budgetWarn, setBudgetWarn] = useState(false);
  const [forceOverBudget, setForceOverBudget] = useState(false);
  /** Residual (jf): Settings depth-tier prefill for continue-as-unit budget. */
  const [researchTier, setResearchTier] = useState<ResearchLaunchTier>("deep");
  const [depthPrefill, setDepthPrefill] = useState<
    "pending" | "installed" | "none" | "error"
  >("pending");
  /**
   * Residual (py): last cohesive unit membership chrome (sessionStorage).
   * Restored selection is an intersection with availableSpawnIds.
   */
  const [membershipStatus, setMembershipStatus] = useState<{
    collective_id: string;
    spawn_count: number;
    restored_count: number;
    action: "stored" | "restored" | "none";
    document_id?: string | null;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchDepthTiers()
      .then((resp) => {
        if (cancelled) return;
        const mapped = mapDepthTierToResearchTier(resp.active_depth_tier);
        if (mapped) {
          setResearchTier(mapped);
          setDepthPrefill("installed");
        } else {
          setDepthPrefill("none");
        }
      })
      .catch(() => {
        if (!cancelled) setDepthPrefill("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const onProjectionChange = useCallback((p: ResearchLaunchBudgetProjection) => {
    setBudgetWarn(p.wouldExceedBudget === true);
  }, []);

  const maybeAutoOpenDraft = useCallback(
    (
      result: MergeProductResponse,
      opts: { titleStem: string; source: string; idPrefix: string },
    ): MergeProductResponse => {
      if (
        !autoOpenDraft ||
        result.mode !== "draft_combined" ||
        result.view_format !== "html" ||
        !result.html?.trim()
      ) {
        return result;
      }
      const winId = openMergedResearchWindow(result, opts);
      if (!winId) return result;
      setAutoOpenedWindowId(winId);
      return {
        ...result,
        notes: [
          ...(result.notes || []),
          "Draft combined auto-opened in hosted HTML window (em).",
        ],
      };
    },
    [autoOpenDraft],
  );

  const toggle = (id: string) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  /** Residual (nk): select all available spawn ids. */
  const selectAllSpawns = useCallback(() => {
    setSelected([...availableSpawnIds]);
  }, [availableSpawnIds]);

  /** Residual (nk): invert selection over available list. */
  const invertSpawnSelection = useCallback(() => {
    setSelected((prev) => {
      const set = new Set(prev);
      const next: string[] = [];
      for (const id of availableSpawnIds) {
        if (!set.has(id)) next.push(id);
      }
      return next;
    });
  }, [availableSpawnIds]);

  /** Residual (nk): clear multi-select. */
  const clearSpawnSelection = useCallback(() => {
    setSelected([]);
  }, []);

  /**
   * Residual (oc): clear session recent-spawn ring so closed-window ids
   * leave the available list (after parent re-collects).
   */
  const clearRecentSpawns = useCallback(() => {
    clearRecentDeepResearchSpawnIds();
    setRecentRing([]);
    onRecentSpawnsCleared?.();
  }, [onRecentSpawnsCleared]);

  // Keep recent origin chrome honest when parent re-renders with new available list.
  useEffect(() => {
    const fromProp =
      recentSpawnIds != null
        ? [...recentSpawnIds].map((x) => String(x || "").trim()).filter(Boolean)
        : listRecentDeepResearchSpawnIds();
    setRecentRing(fromProp);
  }, [availableSpawnIds, recentSpawnIds]);

  /** Residual (of): set of recent-ring ids for origin badges on list rows. */
  const recentSet = useMemo(() => new Set(recentRing), [recentRing]);
  const recentInAvailable = useMemo(
    () => availableSpawnIds.filter((id) => recentSet.has(id)).length,
    [availableSpawnIds, recentSet],
  );

  /**
   * Residual (og): select only spawns present in both available list and
   * recent_ring (closed chase/float batch → collective unit).
   */
  const selectRecentOnly = useCallback(() => {
    const next = availableSpawnIds.filter((id) => recentSet.has(id));
    setSelected(next);
  }, [availableSpawnIds, recentSet]);

  /** Residual (ue): open-window spawn ids intersected with available list. */
  const openSet = useMemo(() => {
    if (openSpawnIds == null) return null;
    return new Set(
      [...openSpawnIds].map((x) => String(x || "").trim()).filter(Boolean),
    );
  }, [openSpawnIds]);
  const openInAvailable = useMemo(() => {
    if (!openSet) return 0;
    return availableSpawnIds.filter((id) => openSet.has(id)).length;
  }, [availableSpawnIds, openSet]);

  /**
   * Residual (ue): select only currently open deep_research_session spawns
   * (excludes closed recent-ring-only ids when openSpawnIds is provided).
   */
  const selectOpenOnly = useCallback(() => {
    if (!openSet) return;
    const next = availableSpawnIds.filter((id) => openSet.has(id));
    setSelected(next);
  }, [availableSpawnIds, openSet]);

  /** Residual (py): remember unit membership after merge / analysis / continue. */
  const rememberUnitMembership = useCallback(
    (
      collectiveId: string,
      spawnIds: readonly string[],
      opts?: { document_id?: string | null },
    ): CollectiveUnitMembership | null => {
      const m = storeCollectiveUnitMembership({
        collective_id: collectiveId,
        spawn_ids: spawnIds,
        parent_asset_id: parentAssetId,
        document_id: opts?.document_id ?? null,
      });
      if (m) {
        setMembershipStatus({
          collective_id: m.collective_id,
          spawn_count: m.spawn_ids.length,
          restored_count: 0,
          action: "stored",
          document_id: m.document_id,
        });
      }
      return m;
    },
    [parentAssetId],
  );

  /**
   * Residual (py): restore last cohesive unit multi-select (intersection with
   * available). After continue-as-unit re-entry, one click restores the set.
   */
  const restoreLastUnitSelection = useCallback(() => {
    const last = getLastCollectiveUnitMembership();
    if (!last) {
      setError("No cohesive unit membership stored in this session");
      return;
    }
    const restored = restoreCollectiveSelection(last, availableSpawnIds);
    if (restored.length < 1) {
      setError(
        `Last unit ${last.collective_id} has no spawn_ids still available (${last.spawn_ids.length} stored)`,
      );
      setMembershipStatus({
        collective_id: last.collective_id,
        spawn_count: last.spawn_ids.length,
        restored_count: 0,
        action: "restored",
        document_id: last.document_id,
      });
      return;
    }
    setSelected(restored);
    setError(null);
    setMembershipStatus({
      collective_id: last.collective_id,
      spawn_count: last.spawn_ids.length,
      restored_count: restored.length,
      action: "restored",
      document_id: last.document_id,
    });
  }, [availableSpawnIds]);

  const mergeCollective = useCallback(async () => {
    if (selected.length < 1) return;
    setBusy(true);
    setError(null);
    try {
      const result = await fetchCollectiveResearch({ spawn_ids: selected });
      if (result.view_format !== "html") {
        throw new Error("collective view_format must be html");
      }
      setUnit(result);
      // Residual (py): persist multi-select membership for re-open.
      rememberUnitMembership(result.collective_id, selected);
      // Residual (ke): depth-max of member spawn tiers for continue budget.
      const rec = (result.recommended_research_tier || "")
        .toString()
        .trim()
        .toLowerCase();
      if (rec === "fast" || rec === "deep" || rec === "wrestle") {
        setResearchTier(rec);
        setDepthPrefill("installed");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [selected, rememberUnitMembership]);

  const mergeDocument = useCallback(
    async (mode: MergeMode) => {
      if (selected.length < 1) return;
      if (!parentAssetId?.trim()) {
        setError("parentAssetId is required for document merge");
        return;
      }
      setBusy(true);
      setError(null);
      setAutoOpenedWindowId(null);
      try {
        const result = await mergeSpawnOutputs({
          parent_asset_id: parentAssetId,
          spawn_ids: selected,
          mode,
          include_html: true,
        });
        if (result.view_format !== "html") {
          throw new Error("merge view_format must be html");
        }
        // Residual (eo): recursive note-taker on merge target document.
        let notes = [...(result.notes || [])];
        try {
          const twins = await seedTwinNotes({
            asset_id: result.document_id,
            title: `Collective merge (${mode}) · ${selected.length} spawn(s)`,
            body_text: `Parent ${parentAssetId} · spawns ${selected.join(", ")} · mode ${mode}`,
            source_spawn_id: selected[0] || undefined,
            include_html: false,
            force_offline: true,
          });
          notes = [
            ...notes,
            twins.seeded
              ? "Twin notes seeded on merged document (recursive note-taker)."
              : `Twin seed: ${twins.seed_skipped || "skipped"}`,
          ];
        } catch {
          notes = [...notes, "Twin seed skipped (API unavailable)."];
        }
        const withTwins: MergeProductResponse = { ...result, notes };
        // Residual (em): draft_combined auto-opens hosted HTML flywheel.
        const final =
          mode === "draft_combined"
            ? maybeAutoOpenDraft(withTwins, {
                titleStem: "Collective draft merge",
                source: "collective_doc_merge",
                idPrefix: "win:collective-merge",
              })
            : withTwins;
        setDocMerge(final);
        // Residual (ep): parent remounts research context after merge + twin seed.
        onDocMerged?.(final);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [selected, parentAssetId, maybeAutoOpenDraft, onDocMerged],
  );

  /** Residual (cf): cohesive unit prompt + draft HTML analysis document. */
  const createWrittenAnalysis = useCallback(async () => {
    if (selected.length < 1) return;
    if (!parentAssetId?.trim()) {
      setError("parentAssetId is required for written analysis draft");
      return;
    }
    setBusy(true);
    setError(null);
    setAutoOpenedWindowId(null);
    try {
      const collective = await fetchCollectiveResearch({ spawn_ids: selected });
      if (collective.view_format !== "html") {
        throw new Error("collective view_format must be html");
      }
      setUnit(collective);
      // Residual (ke): depth-max of member spawn tiers for continue budget.
      const rec = (collective.recommended_research_tier || "")
        .toString()
        .trim()
        .toLowerCase();
      if (rec === "fast" || rec === "deep" || rec === "wrestle") {
        setResearchTier(rec);
        setDepthPrefill("installed");
      }
      const draft = await mergeSpawnOutputs({
        parent_asset_id: parentAssetId,
        spawn_ids: selected,
        mode: "draft_combined",
        include_html: true,
      });
      if (draft.view_format !== "html") {
        throw new Error("analysis draft view_format must be html");
      }
      // Residual (py): membership on analysis asset (document_id provenance).
      rememberUnitMembership(collective.collective_id, selected, {
        document_id: draft.document_id,
      });
      // Residual (ch): recursive note-taker seed on the analysis draft asset.
      let twinNote = "";
      try {
        const twins = await seedTwinNotes({
          asset_id: draft.document_id,
          title: `Written analysis of ${selected.length} spawn(s)`,
          body_text: collective.prompt_block?.slice(0, 500) || "",
          include_html: false,
          force_offline: true,
        });
        twinNote = twins.seeded
          ? "Twin notes seeded on analysis draft (recursive note-taker)."
          : `Twin seed: ${twins.seed_skipped || "skipped"}`;
      } catch {
        twinNote = "Twin seed skipped (API unavailable).";
      }
      const withNotes: MergeProductResponse = {
        ...draft,
        notes: [
          ...(draft.notes || []),
          "Written analysis draft from collective deep research (residual cf).",
          twinNote,
        ],
      };
      // Residual (em): written analysis draft auto-opens hosted HTML.
      const final = maybeAutoOpenDraft(withNotes, {
        titleStem: "Written analysis",
        source: "collective_written_analysis",
        idPrefix: "win:analysis",
      });
      setDocMerge(final);
      // Residual (ep): parent remounts research context after analysis + twin seed.
      onDocMerged?.(final);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [
    selected,
    parentAssetId,
    maybeAutoOpenDraft,
    onDocMerged,
    rememberUnitMembership,
  ]);

  /**
   * Residual (dc/ey): re-enter research with the collective prompt as one unit.
   * Requires parent asset + a merged unit (prompt_block). Uses launchFloatingDeepResearch
   * so decision-tree model_id chokepoint (cy) applies. view_mode floating | full.
   */
  const continueAsCohesiveUnit = useCallback(
    async (viewMode: WindowMode = "floating") => {
      if (!unit?.prompt_block?.trim()) {
        setError("Merge spawns as prompt first");
        return;
      }
      const asset = (parentAssetId || unit.asset_ids?.[0] || "").trim();
      if (!asset) {
        setError("parentAssetId (or collective asset_ids) required to continue");
        return;
      }
      if (budgetWarn && !forceOverBudget) {
        setError(
          "Projected cost may exceed remaining daily budget — enable force override or reduce scope.",
        );
        return;
      }
      setBusy(true);
      setError(null);
      try {
        const selection = unit.prompt_block.trim().slice(0, 8000);
        const out = await launchFloatingDeepResearch({
          asset_id: asset,
          selection_text: selection,
          goal_hint: `Continue collective deep research unit ${unit.collective_id} as one cohesive prompt`,
          view_mode: viewMode,
          research_tier: researchTier,
        });
        setContinueWindowId(out.window_id);
        // Residual (py): re-persist membership at continue so re-open restores set.
        const fromUnit = (unit.spawn_ids || []).filter(Boolean);
        const memberSpawns = fromUnit.length > 0 ? fromUnit : selected;
        rememberUnitMembership(unit.collective_id, memberSpawns);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [
      unit,
      parentAssetId,
      budgetWarn,
      forceOverBudget,
      researchTier,
      selected,
      rememberUnitMembership,
    ],
  );

  return (
    <section
      className="collective-research-panel"
      data-view-format="html"
      data-testid="collective-research-panel"
      data-auto-open-draft={autoOpenDraft ? "true" : "false"}
      data-l6-live-multiagent="deferred"
      data-offline-merge-unit="true"
      aria-label="Collective deep research"
    >
      <header>
        <h2>Collective deep research</h2>
        {/* Residual (vx/wi): L6 live multi-agent deferred honesty + checklist deep-link. */}
        <p
          className="meta font-mono text-[11px] opacity-80"
          data-testid="collective-l6-honesty"
          data-l6-live-multiagent="deferred"
          data-offline-merge-unit="true"
          role="status"
        >
          L6 live multi-agent council: deferred · offline merge unit only · never
          silent live council ·{" "}
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l6-collective"
            data-testid="collective-l6-checklist-link"
            className="underline opacity-90 hover:opacity-100"
            title="L6 live multi-agent deferred — dual-gate checklist (offline merge unit only)"
          >
            L6 checklist
          </a>
        </p>
        <p className="meta">
          Merge multiple subagent instances into one prompt unit, or into a
          draft-combined / parent HTML document
          {autoOpenDraft
            ? " · draft auto-opens HTML window"
            : " · draft open is manual"}
        </p>
        {parentAssetId ? (
          <p className="meta" data-testid="collective-parent-asset">
            Parent asset: <code>{parentAssetId}</code>
          </p>
        ) : null}
        {/* Residual (ig/nl): Settings + dual-gate checklist (L6 collective prep). */}
        <p className="meta font-mono text-[11px] space-x-3">
          <a
            href="/settings#decision-tree-panel"
            data-testid="collective-settings-link"
            title="Open Settings decision-tree: driver, budget bar, sample cost projection"
          >
            Settings · driver & budget
          </a>
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l6-collective"
            data-testid="collective-dual-gate-checklist-link"
            title="Dual-gate L6 live multi-agent checklist (prep only · offline merge unit)"
          >
            {/* Residual (aat): label matches #l6-collective href (was L1–L4). */}
            Dual-gate L6 collective checklist
          </a>
        </p>
        {/* Residual (lg): model driver + budget + depth co-display (parity ku). */}
        <div
          className="mt-1"
          data-testid="collective-driver-badge-mount"
          data-view-format="html"
          data-research-tier={researchTier}
        >
          <DecisionTreeDriverBadge
            researchTier={researchTier}
            promptText={
              (unit?.prompt_block || "").trim() ||
              (selected.length
                ? `collective merge · ${selected.length} spawn(s): ${selected.join(",")}`
                : "")
            }
          />
        </div>
      </header>

      <ul
        className="spawn-list"
        data-testid="collective-spawn-list"
        data-recent-in-available={String(recentInAvailable)}
        data-view-format="html"
      >
        {availableSpawnIds.map((id) => {
          const fromRecent = recentSet.has(id);
          return (
            <li
              key={id}
              data-spawn-id={id}
              data-selected={String(selected.includes(id))}
              data-origin-recent={String(fromRecent)}
              data-testid={`collective-spawn-row-${id}`}
            >
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  data-testid={`collective-select-${id}`}
                  checked={selected.includes(id)}
                  onChange={() => toggle(id)}
                  disabled={busy}
                />{" "}
                <code>{id}</code>
                {/* Residual (of): recent_ring origin for closed chase/float. */}
                {fromRecent ? (
                  <span
                    className="text-[10px] font-mono opacity-70 border rounded px-1"
                    data-testid={`collective-origin-recent-${id}`}
                    title="From session recent ring — survives floating window close"
                  >
                    recent
                  </span>
                ) : null}
              </label>
            </li>
          );
        })}
      </ul>
      {/* Residual (nk): multi-select helpers (parity TwinNotes select path). */}
      <div
        className="flex flex-wrap gap-2 mb-2"
        data-testid="collective-select-controls"
        data-selected-count={String(selected.length)}
        data-available-count={String(availableSpawnIds.length)}
        data-recent-count={String(recentCount)}
        data-recent-in-available={String(recentInAvailable)}
        data-open-in-available={String(openInAvailable)}
        data-has-open-spawn-ids={String(openSet != null)}
        data-auto-select-newest-recent={String(autoSelectNewestRecent)}
        data-view-format="html"
        title="Includes open deep-research windows and recent session opens (twin chase / float)"
      >
        <button
          type="button"
          data-testid="collective-select-all"
          onClick={() => selectAllSpawns()}
          disabled={busy || availableSpawnIds.length === 0}
          title="Select all available deep-research spawns"
        >
          Select all ({availableSpawnIds.length})
        </button>
        {/* Residual (og): one-click select recent_ring rows only. */}
        <button
          type="button"
          data-testid="collective-select-recent"
          onClick={() => selectRecentOnly()}
          disabled={busy || recentInAvailable === 0}
          title="Select only spawns from the session recent ring (twin chase / float opens)"
        >
          Select recent ({recentInAvailable})
        </button>
        {/* Residual (ue): one-click select currently open DR windows only. */}
        {openSet != null ? (
          <button
            type="button"
            data-testid="collective-select-open"
            onClick={() => selectOpenOnly()}
            disabled={busy || openInAvailable === 0}
            title="Select only spawns from currently open deep-research windows (excludes closed recent-only)"
          >
            Select open ({openInAvailable})
          </button>
        ) : null}
        <button
          type="button"
          data-testid="collective-invert-selection"
          onClick={() => invertSpawnSelection()}
          disabled={busy || availableSpawnIds.length === 0}
          title="Invert multi-select over available spawns"
        >
          Invert
        </button>
        <button
          type="button"
          data-testid="collective-clear-selection"
          onClick={() => clearSpawnSelection()}
          disabled={busy || selected.length === 0}
        >
          Clear selection
        </button>
        {/* Residual (oc): drop closed-window ring without inventing ids. */}
        <button
          type="button"
          data-testid="collective-clear-recent-spawns"
          onClick={() => clearRecentSpawns()}
          disabled={busy || recentCount === 0}
          title="Clear session recent deep-research spawn ids (closed windows leave the list)"
        >
          Clear recent ({recentCount})
        </button>
        {/* Residual (py): restore last cohesive unit multi-select. */}
        <button
          type="button"
          data-testid="collective-restore-last-unit"
          onClick={() => restoreLastUnitSelection()}
          disabled={busy}
          title="Restore multi-select from last cohesive unit membership (sessionStorage)"
        >
          Restore last unit
        </button>
        <span
          className="text-[11px] font-mono opacity-70"
          data-testid="collective-selection-count"
          data-selected-count={String(selected.length)}
          data-recent-count={String(recentCount)}
          data-recent-in-available={String(recentInAvailable)}
        >
          Selected: {selected.length}/{availableSpawnIds.length}
          {recentCount > 0 ? ` · recent=${recentCount}` : ""}
          {recentInAvailable > 0
            ? ` · recent_in_list=${recentInAvailable}`
            : ""}
        </span>
        {membershipStatus ? (
          <span
            className="text-[11px] font-mono opacity-80 w-full"
            data-testid="collective-unit-membership-status"
            data-action={membershipStatus.action}
            data-collective-id={membershipStatus.collective_id}
            data-spawn-count={String(membershipStatus.spawn_count)}
            data-restored-count={String(membershipStatus.restored_count)}
            data-document-id={membershipStatus.document_id ?? ""}
            data-view-format="html"
            // Residual (adj): offline cohesive unit only — L6 live multi-agent deferred.
            data-l6-live-multiagent="deferred"
            data-research-tier={researchTier || ""}
            role="status"
          >
            Unit membership · {membershipStatus.action} · id=
            {membershipStatus.collective_id} · stored=
            {membershipStatus.spawn_count}
            {membershipStatus.action === "restored"
              ? ` · restored=${membershipStatus.restored_count}`
              : ""}
            {researchTier ? ` · tier=${researchTier}` : ""}
            {membershipStatus.document_id
              ? ` · doc=${membershipStatus.document_id}`
              : ""}{" "}
            · L6 live multi-agent deferred
          </span>
        ) : null}
      </div>

      <div className="collective-actions" style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        <button
          type="button"
          data-testid="collective-merge-prompt"
          onClick={() => void mergeCollective()}
          disabled={busy || selected.length < 1}
        >
          {busy ? "Merging…" : `Merge ${selected.length} spawn(s) as prompt`}
        </button>
        <button
          type="button"
          data-testid="collective-merge-draft"
          onClick={() => void mergeDocument("draft_combined")}
          disabled={busy || selected.length < 1 || !parentAssetId}
          title={
            parentAssetId
              ? "Create draft-combined document; parent unchanged"
              : "Requires parentAssetId"
          }
        >
          Merge to draft document
        </button>
        <button
          type="button"
          data-testid="collective-merge-parent"
          onClick={() => void mergeDocument("into_parent")}
          disabled={busy || selected.length < 1 || !parentAssetId}
          title={
            parentAssetId
              ? "Merge into parent asset in-place"
              : "Requires parentAssetId"
          }
        >
          Merge into parent
        </button>
        <button
          type="button"
          data-testid="collective-written-analysis"
          onClick={() => void createWrittenAnalysis()}
          disabled={busy || selected.length < 1 || !parentAssetId}
          title={
            parentAssetId
              ? "Collective prompt unit + draft-combined HTML analysis"
              : "Requires parentAssetId"
          }
        >
          Create written analysis
        </button>
      </div>

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      {unit ? (
        <div className="collective-result" data-testid="collective-unit-result">
          {/* Residual (hm): machine-readable multi-spawn collective metrics. */}
          <div
            data-testid="collective-unit-metrics"
            data-collective-id={unit.collective_id ?? ""}
            data-spawn-count={String(unit.spawn_count ?? 0)}
            data-twin-count={String(unit.twin_count ?? 0)}
            data-ref-count={String(unit.ref_count ?? 0)}
            data-research-tiers={(unit.research_tiers || []).join(",")}
            data-recommended-research-tier={
              unit.recommended_research_tier || ""
            }
            data-usage-source={unit.usage_event?.source ?? ""}
            data-usage-task-class={unit.usage_event?.task_class ?? ""}
            data-view-format="html"
            role="status"
          >
            Collective unit · spawns={unit.spawn_count ?? 0} · twins=
            {unit.twin_count ?? 0} · refs={unit.ref_count ?? 0}
            {unit.recommended_research_tier
              ? ` · tier=${unit.recommended_research_tier}`
              : ""}
            {unit.usage_event?.source
              ? ` · bench=${unit.usage_event.source}/${unit.usage_event.task_class ?? "?"}`
              : ""}
          </div>
          <p>
            collective <code>{unit.collective_id}</code> · spawns=
            {unit.spawn_count} · twins={unit.twin_count} · refs={unit.ref_count}
            {unit.recommended_research_tier ? (
              <>
                {" "}
                · recommended tier=
                <code data-testid="collective-recommended-tier">
                  {unit.recommended_research_tier}
                </code>
              </>
            ) : null}
          </p>
          <pre className="prompt-block" data-testid="collective-prompt-block">
            {unit.prompt_block}
          </pre>
          {/* Residual (tr): cohesive unit prompt → float|full HTML reading windows. */}
          {(unit.prompt_block || "").trim() ? (
            <p className="meta font-mono text-[11px] space-x-3">
              <button
                type="button"
                data-testid="collective-unit-open-float"
                data-view-format="html"
                data-window-mode="floating"
                data-collective-id={unit.collective_id ?? ""}
                data-spawn-count={String(unit.spawn_count ?? 0)}
                className="underline opacity-90 hover:opacity-100 bg-transparent border-0 p-0 cursor-pointer font-mono text-[11px]"
                title="Open cohesive unit prompt as floating HTML window (no invented document_id · never PDF)"
                onClick={() => {
                  const cid =
                    String(unit.collective_id || "").trim() || "collective";
                  const id = `collective_unit:${cid}:${Date.now().toString(36)}`;
                  const html = buildCollectiveUnitPromptHtml({
                    collectiveId: cid,
                    promptBlock: unit.prompt_block || "",
                    spawnCount: unit.spawn_count,
                    twinCount: unit.twin_count,
                    refCount: unit.ref_count,
                    researchTier: unit.recommended_research_tier || researchTier,
                    spawnIds: selected,
                  });
                  openWindow(
                    "hosted_html_document",
                    {
                      document_id: id,
                      title: `Collective unit · ${cid}`,
                      html,
                      view_format: "html",
                      source: "collective_unit_prompt",
                      research_tier:
                        unit.recommended_research_tier || researchTier || null,
                      collective_id: cid,
                      spawn_count: unit.spawn_count ?? selected.length,
                    },
                    {
                      id: `win:collective_unit:${id}`,
                      title: "Collective unit",
                      mode: "floating",
                    },
                  );
                }}
              >
                Open float (unit HTML)
              </button>
              <button
                type="button"
                data-testid="collective-unit-open-full"
                data-view-format="html"
                data-window-mode="full"
                data-collective-id={unit.collective_id ?? ""}
                data-spawn-count={String(unit.spawn_count ?? 0)}
                className="underline opacity-90 hover:opacity-100 bg-transparent border-0 p-0 cursor-pointer font-mono text-[11px]"
                title="Open cohesive unit prompt as full working-region HTML window (never PDF)"
                onClick={() => {
                  const cid =
                    String(unit.collective_id || "").trim() || "collective";
                  const id = `collective_unit:${cid}:full:${Date.now().toString(36)}`;
                  const html = buildCollectiveUnitPromptHtml({
                    collectiveId: cid,
                    promptBlock: unit.prompt_block || "",
                    spawnCount: unit.spawn_count,
                    twinCount: unit.twin_count,
                    refCount: unit.ref_count,
                    researchTier: unit.recommended_research_tier || researchTier,
                    spawnIds: selected,
                  });
                  openWindow(
                    "hosted_html_document",
                    {
                      document_id: id,
                      title: `Collective unit · ${cid} (full)`,
                      html,
                      view_format: "html",
                      source: "collective_unit_prompt",
                      research_tier:
                        unit.recommended_research_tier || researchTier || null,
                      collective_id: cid,
                      spawn_count: unit.spawn_count ?? selected.length,
                    },
                    {
                      id: `win:collective_unit:${id}:full`,
                      title: "Collective unit (full)",
                      mode: "full",
                    },
                  );
                }}
              >
                Open full (unit HTML)
              </button>
            </p>
          ) : null}
          {/* Residual (dc/di/jf): continue unit + budget soft-gate + depth prefill. */}
          <div
            className="space-y-2"
            style={{ marginTop: "0.5rem" }}
            data-testid="collective-continue-budget-mount"
            data-view-format="html"
            data-research-tier={researchTier}
            data-depth-prefill={depthPrefill}
          >
            <p
              className="text-[11px] font-mono opacity-80"
              data-testid="collective-depth-prefill"
              role="status"
            >
              Depth prefill: {depthPrefill}
              {depthPrefill === "installed"
                ? ` → ${researchTier}`
                : depthPrefill === "none"
                  ? " (default deep)"
                  : ""}
            </p>
            <ResearchLaunchBudgetPanel
              promptText={unit.prompt_block || ""}
              researchTier={researchTier}
              allowTierPick
              onResearchTierChange={setResearchTier}
              onProjectionChange={onProjectionChange}
            />
            {budgetWarn ? (
              <label
                className="flex items-center gap-2 text-[11px] font-mono text-emperor"
                data-testid="collective-over-budget-warn"
              >
                <input
                  type="checkbox"
                  data-testid="collective-force-over-budget"
                  checked={forceOverBudget}
                  onChange={(e) => setForceOverBudget(e.target.checked)}
                  disabled={busy}
                />
                Force continue despite budget projection
              </label>
            ) : null}
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                data-testid="collective-continue-as-unit"
                onClick={() => void continueAsCohesiveUnit("floating")}
                disabled={
                  busy ||
                  !unit.prompt_block?.trim() ||
                  (budgetWarn && !forceOverBudget)
                }
                title="Open a new floating deep research session seeded with this collective prompt"
              >
                {busy ? "Opening…" : "Continue as cohesive unit (window)"}
              </button>
              <button
                type="button"
                data-testid="collective-continue-as-unit-full"
                onClick={() => void continueAsCohesiveUnit("full")}
                disabled={
                  busy ||
                  !unit.prompt_block?.trim() ||
                  (budgetWarn && !forceOverBudget)
                }
                title="Open collective unit deep research expanded to full working region"
              >
                {busy ? "Opening…" : "Continue as unit (full)"}
              </button>
              {continueWindowId ? (
                <span
                  className="meta"
                  data-testid="collective-continue-window-id"
                  role="status"
                >
                  Window {continueWindowId}
                </span>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {docMerge ? (
        <div
          className="document-merge-result"
          data-testid="collective-doc-merge-result"
          data-view-format="html"
          data-usage-source={docMerge.usage_event?.source ?? ""}
          data-usage-task-class={docMerge.usage_event?.task_class ?? ""}
        >
          {/* Residual (oj): Antiek-bench usage audit for document merge path. */}
          {docMerge.usage_event?.source ? (
            <p
              className="text-[11px] font-mono opacity-80"
              data-testid="collective-doc-merge-usage"
              data-usage-source={docMerge.usage_event.source}
              data-usage-task-class={docMerge.usage_event.task_class ?? ""}
              role="status"
            >
              Bench feed · {docMerge.usage_event.source}/
              {docMerge.usage_event.task_class ?? "?"}
            </p>
          ) : null}
          <p>
            mode=<code>{docMerge.mode}</code> · document=
            <code>{docMerge.document_id}</code> · draft_leaves_parent=
            {String(docMerge.draft_leaves_parent)}
          </p>
          {autoOpenedWindowId ? (
            <p
              className="meta"
              data-testid="collective-auto-open-window"
              role="status"
            >
              Auto-opened window {autoOpenedWindowId}
            </p>
          ) : null}
          {docMerge.notes?.map((n) => (
            <p key={n} className="meta">
              {n}
            </p>
          ))}
          {/* Residual (cg/em/ev): open draft analysis HTML via shared chokepoint. */}
          {docMerge.html && docMerge.view_format === "html" ? (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                data-testid="collective-open-analysis-window"
                onClick={() => {
                  openMergedResearchWindow(docMerge, {
                    titleStem: "Written analysis",
                    source: "collective_written_analysis",
                    idPrefix: "win:analysis",
                  });
                }}
              >
                Open analysis in window
              </button>
              <button
                type="button"
                data-testid="collective-open-analysis-full"
                onClick={() => {
                  openMergedResearchWindow(docMerge, {
                    titleStem: "Written analysis",
                    source: "collective_written_analysis",
                    idPrefix: "win:analysis",
                    windowMode: "full",
                  });
                }}
              >
                Open analysis full
              </button>
              {/* Residual (fn/qe): dual handoff html_draft + twin_seed. */}
              <a
                href={buildMergedDocWriteHref({
                  documentId: docMerge.document_id,
                  title: `Collective merge · ${docMerge.document_id}`,
                  html: docMerge.html,
                  source: "collective_doc_merge",
                })}
                data-testid="collective-open-write"
                data-view-format="html"
                data-has-twin-seed="1"
                // Residual (acm): body honesty on twin_seed (parity spawn merge acl).
                data-write-seed-has-body={String(
                  Boolean(
                    docMerge.view_format === "html" &&
                      plainTextFromHtml(docMerge.html || "").trim(),
                  ),
                )}
                className="underline"
                title="Open Write with collective HTML merge + twin_seed (seeds note-taker when empty)"
              >
                Open Write (HTML draft)
              </a>
            </div>
          ) : null}
          {docMerge.html ? (
            <div
              className="merge-html"
              data-testid="collective-doc-merge-html"
              dangerouslySetInnerHTML={{ __html: docMerge.html }}
            />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default CollectiveResearchPanel;
