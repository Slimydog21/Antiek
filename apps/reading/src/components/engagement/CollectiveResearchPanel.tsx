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
 * 11. Residual (hm): collective-unit-metrics machine attrs for multi-spawn
 *     cohesive unit audit (parity twin/flywheel/progress metrics).
 */

import { useCallback, useEffect, useState } from "react";
import {
  fetchCollectiveResearch,
  mergeSpawnOutputs,
  seedTwinNotes,
  type CollectiveResponse,
  type MergeMode,
  type MergeProductResponse,
} from "../../api/engagement";
import { launchFloatingDeepResearch } from "../../modes/Reading/launchFloatingDeepResearch";
import type { WindowMode } from "../../workspace/windowsStore";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
} from "./ResearchLaunchBudgetPanel";
import { openMergedResearchWindow } from "./SpawnMergePanel";

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
};

export function CollectiveResearchPanel({
  availableSpawnIds,
  parentAssetId = null,
  preferredSpawnId = null,
  autoOpenDraft = true,
  onDocMerged,
}: CollectiveResearchPanelProps) {
  const [selected, setSelected] = useState<string[]>([]);

  // Auto-select preferred spawn once when available (residual cn).
  useEffect(() => {
    const pref = (preferredSpawnId || "").trim();
    if (!pref) return;
    if (!availableSpawnIds.includes(pref)) return;
    setSelected((prev) => (prev.includes(pref) ? prev : [...prev, pref]));
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [selected]);

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
      const draft = await mergeSpawnOutputs({
        parent_asset_id: parentAssetId,
        spawn_ids: selected,
        mode: "draft_combined",
        include_html: true,
      });
      if (draft.view_format !== "html") {
        throw new Error("analysis draft view_format must be html");
      }
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
  }, [selected, parentAssetId, maybeAutoOpenDraft, onDocMerged]);

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
        });
        setContinueWindowId(out.window_id);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [unit, parentAssetId, budgetWarn, forceOverBudget],
  );

  return (
    <section
      className="collective-research-panel"
      data-view-format="html"
      data-testid="collective-research-panel"
      data-auto-open-draft={autoOpenDraft ? "true" : "false"}
      aria-label="Collective deep research"
    >
      <header>
        <h2>Collective deep research</h2>
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
      </header>

      <ul className="spawn-list">
        {availableSpawnIds.map((id) => (
          <li key={id}>
            <label>
              <input
                type="checkbox"
                checked={selected.includes(id)}
                onChange={() => toggle(id)}
                disabled={busy}
              />{" "}
              <code>{id}</code>
            </label>
          </li>
        ))}
      </ul>

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
            data-view-format="html"
            role="status"
          >
            Collective unit · spawns={unit.spawn_count ?? 0} · twins=
            {unit.twin_count ?? 0} · refs={unit.ref_count ?? 0}
          </div>
          <p>
            collective <code>{unit.collective_id}</code> · spawns=
            {unit.spawn_count} · twins={unit.twin_count} · refs={unit.ref_count}
          </p>
          <pre className="prompt-block" data-testid="collective-prompt-block">
            {unit.prompt_block}
          </pre>
          {/* Residual (dc/di): continue unit + budget soft-gate. */}
          <div
            className="space-y-2"
            style={{ marginTop: "0.5rem" }}
            data-testid="collective-continue-budget-mount"
            data-view-format="html"
          >
            <ResearchLaunchBudgetPanel
              promptText={unit.prompt_block || ""}
              researchTier="deep"
              allowTierPick
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
        >
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
              {/* Residual (fn): handoff collective draft into Write mode. */}
              <a
                href={`/write?html_draft=${encodeURIComponent(docMerge.document_id)}`}
                data-testid="collective-open-write"
                data-view-format="html"
                className="underline"
                title="Open Write with this HTML merge document as draft handoff"
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
