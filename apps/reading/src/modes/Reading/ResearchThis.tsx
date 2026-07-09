import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { LemonButton } from "../../components/lemon";
import { spinResearch } from "../../api/books";
import { CollectiveResearchPanel } from "../../components/engagement/CollectiveResearchPanel";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
  type ResearchLaunchTier,
} from "../../components/engagement/ResearchLaunchBudgetPanel";
import { fetchDepthTiers } from "../../api/settings";
import { mapDepthTierToResearchTier } from "../../lib/researchTier";
import { track } from "../../lib/analytics";
import {
  hydratePublicationRefs,
  parsePublicationRefs,
} from "../ResearchWorkstation/publicationRefs";
import { collectDeepResearchSpawnIds } from "../../workspace/collectDeepResearchSpawnIds";
import type { WindowMode } from "../../workspace/windowsStore";
import { useWindows } from "../../workspace/windowsStore";
import { launchFloatingDeepResearch } from "./launchFloatingDeepResearch";

/**
 * ResearchThis (Read SPR-08 + residual cc/cu/cx/cy/de) — spin deep research from
 * the current passage.
 *
 * Residual (cc): primary path opens a **floating** deep_research_session
 * window via engagement sessions/open + openDeepResearchFromHighlight.
 * Residual (cu): optional arxiv/substack/URL refs hydrate + attach on open.
 * Residual (cx): budget projection before fire (parity with StartResearch).
 * Residual (cy): decision-tree model_id resolved inside launchFloatingDeepResearch
 * (shared chokepoint with float-menu / HighlightToolbar).
 * Residual (et): full working-region deep_research_session window (view_mode
 * full) — distinct from legacy full-page ResearchWorkstation handoff.
 * Residual (fc): CollectiveResearchPanel when open DR spawns exist so the
 * main reading surface multi-select merges into this document (parity eu).
 * Residual (jg): Settings depth-tier prefill for budget projection (parity jc–jf).
 * Full-page workstation handoff remains an explicit tertiary action.
 *
 * Gate-safe: passageText for gated books is still constrained server-side;
 * floating path uses the same asset_id + selection identity.
 */

export interface ResearchThisProps {
  documentId: string;
  pageIndex: number;
  /** The reader's selected text, if any. Ignored server-side for gated
   * books — passed only as a convenience for servable ones. */
  passageText?: string;
}

export default function ResearchThis({
  documentId,
  pageIndex,
  passageText,
}: ResearchThisProps) {
  const navigate = useNavigate();
  // Residual (fc): open DR session spawns for collective multi-select.
  const windows = useWindows((s) => s.windows);
  const availableSpawnIds = useMemo(
    () =>
      collectDeepResearchSpawnIds({
        currentSpawnId: null,
        windows,
      }),
    [windows],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastWindowId, setLastWindowId] = useState<string | null>(null);
  const [pubRefs, setPubRefs] = useState("");
  const [pubRefStatus, setPubRefStatus] = useState<string | null>(null);
  const [budgetWarn, setBudgetWarn] = useState(false);
  const [forceOverBudget, setForceOverBudget] = useState(false);
  /** Residual (jg): Settings depth-tier prefill for reading DR budget. */
  const [researchTier, setResearchTier] = useState<ResearchLaunchTier>("deep");
  const [depthPrefill, setDepthPrefill] = useState<
    "pending" | "installed" | "none" | "error"
  >("pending");

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

  const selection =
    (passageText || "").trim() ||
    `Page ${pageIndex + 1} of document ${documentId}`;

  const onProjectionChange = useCallback(
    (p: ResearchLaunchBudgetProjection) => {
      setBudgetWarn(p.wouldExceedBudget === true);
    },
    [],
  );

  const spinDeepResearchWindow = async (viewMode: WindowMode = "floating") => {
    if (budgetWarn && !forceOverBudget) {
      setError(
        "Projected cost may exceed remaining daily budget — enable force override or reduce scope.",
      );
      return;
    }
    setBusy(true);
    setError(null);
    setPubRefStatus(null);
    try {
      const refs = parsePublicationRefs(pubRefs);
      if (refs.length > 0) {
        const hydrated = await hydratePublicationRefs(refs);
        setPubRefStatus(
          `Hydrated ${hydrated.ok.length} pub asset(s)` +
            (hydrated.failed.length ? ` · ${hydrated.failed.length} failed` : "") +
            " · HTML-first",
        );
      }
      // Residual (cy): model_id resolved inside launchFloatingDeepResearch
      // (decision-tree driver when installed; never invented).
      // Residual (et): view_mode floating | full for window host (not /inv).
      const out = await launchFloatingDeepResearch({
        asset_id: documentId,
        selection_text: selection,
        page: pageIndex,
        goal_hint: "Deep-research the highlighted passage from reading",
        view_mode: viewMode,
        references: refs.length ? refs : undefined,
        // Residual (ji): pass Settings/picker tier onto reserved spawn.
        research_tier: researchTier,
      });
      track("reading_research_spun", {
        document_id: documentId,
        page_index: pageIndex,
        has_passage: Boolean(passageText),
        mode: viewMode === "full" ? "full_window" : "floating_window",
        session_id: out.session_id,
        publication_ref_count: refs.length,
        model_id: out.model_id,
        research_tier: out.research_tier,
      });
      setLastWindowId(out.window_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const spinFullWorkstation = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await spinResearch(documentId, pageIndex, passageText);
      track("reading_research_spun", {
        document_id: documentId,
        page_index: pageIndex,
        has_passage: Boolean(passageText),
        mode: "full_workstation",
      });
      navigate(`/inv/${encodeURIComponent(res.investigation_id)}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-2" data-testid="research-this">
      <div
        className="space-y-1 max-w-md"
        data-testid="research-this-pub-refs"
        data-view-format="html"
      >
        <label
          className="text-[10px] font-mono uppercase tracking-wider text-ink-mute dark:text-moonlight"
          htmlFor="research-this-refs-input"
        >
          Ground with pubs (optional)
        </label>
        <textarea
          id="research-this-refs-input"
          data-testid="research-this-refs-input"
          value={pubRefs}
          onChange={(e) => setPubRefs(e.target.value)}
          disabled={busy}
          rows={2}
          placeholder={"arxiv:1706.03762\nhttps://…"}
          className="w-full rounded border border-ink/20 bg-transparent px-2 py-1 text-[11px] font-mono dark:border-bright/20"
        />
        {pubRefStatus ? (
          <p
            className="text-[10px] font-mono text-aurora"
            data-testid="research-this-refs-status"
            role="status"
          >
            {pubRefStatus}
          </p>
        ) : null}
      </div>
      {/* Residual (cx/jg): daily budget + prompt projection + depth prefill. */}
      <div
        className="max-w-md"
        data-testid="research-this-budget-mount"
        data-view-format="html"
        data-research-tier={researchTier}
        data-depth-prefill={depthPrefill}
      >
        <p
          className="text-[11px] font-mono opacity-80"
          data-testid="research-this-depth-prefill"
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
          promptText={selection}
          researchTier={researchTier}
          allowTierPick
          onResearchTierChange={setResearchTier}
          onProjectionChange={onProjectionChange}
        />
        {budgetWarn ? (
          <label
            className="flex items-center gap-2 text-[11px] font-mono text-emperor"
            data-testid="research-this-over-budget-warn"
          >
            <input
              type="checkbox"
              data-testid="research-this-force-over-budget"
              checked={forceOverBudget}
              onChange={(e) => setForceOverBudget(e.target.checked)}
              disabled={busy}
            />
            Force open despite budget projection
          </label>
        ) : null}
      </div>
      <div className="inline-flex flex-wrap items-center gap-2">
        <LemonButton
          type="button"
          variant="secondary"
          size="sm"
          disabled={busy || (budgetWarn && !forceOverBudget)}
          onClick={() => void spinDeepResearchWindow("floating")}
          title="Open deep research in a floating window over the scene"
          data-testid="research-this-floating"
        >
          {busy ? "Opening…" : "Deep research (window)"}
        </LemonButton>
        <LemonButton
          type="button"
          variant="secondary"
          size="sm"
          disabled={busy || (budgetWarn && !forceOverBudget)}
          onClick={() => void spinDeepResearchWindow("full")}
          title="Open deep research expanded to full working region"
          data-testid="research-this-deep-full"
        >
          {busy ? "Opening…" : "Deep research (full)"}
        </LemonButton>
        <LemonButton
          type="button"
          variant="tertiary"
          size="sm"
          disabled={busy}
          onClick={() => void spinFullWorkstation()}
          title="Spin full Research workstation (legacy handoff)"
          data-testid="research-this-full"
        >
          {busy ? "Spinning…" : "Research this page"}
        </LemonButton>
        {lastWindowId ? (
          <span
            className="text-[11px] font-mono text-aurora"
            data-testid="research-this-window-id"
            role="status"
          >
            Window {lastWindowId}
          </span>
        ) : null}
        {error && (
          <span
            className="text-[11px] font-mono text-emperor"
            role="alert"
            data-testid="research-this-error"
          >
            {error === "book_not_found" ? "Book not found." : error}
          </span>
        )}
      </div>
      {/* Residual (fc): multi-select open DR spawns → merge into this book. */}
      {documentId.trim() && availableSpawnIds.length > 0 ? (
        <section
          className="mt-2 max-w-md space-y-1 border-t border-ink/10 pt-2 dark:border-bright/10"
          data-testid="research-this-collective-mount"
          data-view-format="html"
          data-available-spawn-count={String(availableSpawnIds.length)}
        >
          <CollectiveResearchPanel
            availableSpawnIds={availableSpawnIds}
            parentAssetId={documentId.trim()}
          />
        </section>
      ) : null}
    </div>
  );
}
