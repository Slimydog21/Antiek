/**
 * HostedHtmlDocumentHost — window-native page for marketplace / account
 * hosted books (residual bt). HTML-first only; PDF never required as view.
 *
 * Residual (bw): mounts TwinNotesPanel + ResearchContextPanel so reading
 * and research share the recursive note-taker / context flywheel on the
 * same document_id used as engagement asset_id after host seed (bv).
 * Residual (cv): ResearchContextPanel autoLoad.
 * Residual (da): DecisionTreeDriverBadge + budget projection + deep research
 * float launch from the hosted book (reading ≡ research).
 * Residual (dg): soft-gate deep research when budget would exceed.
 * Residual (ec): remount ResearchContextPanel after twin promote.
 * Residual (en): highlight inside hosted HTML body → selection drives float
 * DR + budget projection (fallback: title+asset when no selection).
 * Residual (er): optional arxiv/substack/URL pub refs hydrate + attach on
 * float open (parity with ResearchThis cu) — knowledge-dense grounding from
 * marketplace/hosted books.
 * Residual (es): launch deep research as full window (view_mode full) as well
 * as floating — north-star “open in full screen” without leaving the hosted book.
 * Residual (eu): mount CollectiveResearchPanel when open deep_research_session
 * spawns exist so multi-select merge/analysis runs against this book as parent
 * (reading ≡ research collective unit).
 * Residual (ez): remount TwinNotesPanel on the same refresh key as research
 * context so collective merge / promote reload recursive note-taker twins.
 * Residual (gn): allowTierPick on ResearchLaunchBudgetPanel (flash|pro|wrestle).
 * Residual (jd): prefill researchTier from Settings depth-tier (parity marketplace jc).
 *
 * Props arrive via WindowsLayer: `<Renderer {...win.payload} />`.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchDepthTiers } from "../../api/settings";
import { mapDepthTierToResearchTier } from "../../lib/researchTier";
import { launchFloatingDeepResearch } from "../../modes/Reading/launchFloatingDeepResearch";
import {
  hydratePublicationRefs,
  parsePublicationRefs,
} from "../../modes/ResearchWorkstation/publicationRefs";
import { collectDeepResearchSpawnIds } from "../../workspace/collectDeepResearchSpawnIds";
import { listRecentDeepResearchSpawnIds } from "../../workspace/recentDeepResearchSpawns";
import type { WindowMode } from "../../workspace/windowsStore";
import { useWindows } from "../../workspace/windowsStore";
import { CollectiveResearchPanel } from "../engagement/CollectiveResearchPanel";
import { DecisionTreeDriverBadge } from "../engagement/DecisionTreeDriverBadge";
import { ResearchContextPanel } from "../engagement/ResearchContextPanel";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
  type ResearchLaunchTier,
} from "../engagement/ResearchLaunchBudgetPanel";
import { TwinNotesPanel } from "../engagement/TwinNotesPanel";
import { useInWindow } from "./windowHostContext";

export type HostedHtmlDocumentHostProps = {
  document_id?: string;
  title?: string;
  html?: string;
  view_format?: string;
  license_class?: string;
  owner_id?: string;
  source?: string;
  __windowId?: string;
};

/** Residual (en): highlight passage wins; else whole-document fallback. */
export function resolveHostedResearchSelection(opts: {
  title: string;
  assetId: string;
  fallbackDocId: string;
  highlightText?: string | null;
}): { selection_text: string; from_highlight: boolean } {
  const highlight = (opts.highlightText || "").trim();
  if (highlight) {
    return { selection_text: highlight, from_highlight: true };
  }
  const id = opts.assetId || opts.fallbackDocId;
  return {
    selection_text: `Deep-research hosted document: ${opts.title} (${id})`,
    from_highlight: false,
  };
}

export default function HostedHtmlDocumentHost(
  props: HostedHtmlDocumentHostProps,
) {
  useInWindow();

  const docId = props.document_id?.trim() || "(missing document_id)";
  const title = props.title?.trim() || "Hosted document";
  const viewFormat = (props.view_format?.trim() || "html").toLowerCase();
  const isHtml = viewFormat === "html";
  const html = props.html?.trim() || "";
  const assetId = props.document_id?.trim() || "";

  // Residual (eu/ob): open + recent DR session spawns for collective multi-select.
  const windows = useWindows((s) => s.windows);
  const availableSpawnIds = useMemo(
    () =>
      collectDeepResearchSpawnIds({
        currentSpawnId: null,
        windows,
        recentSpawnIds: listRecentDeepResearchSpawnIds(),
      }),
    [windows],
  );

  const [highlightText, setHighlightText] = useState("");
  const [pubRefs, setPubRefs] = useState("");
  const [pubRefStatus, setPubRefStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastWindowId, setLastWindowId] = useState<string | null>(null);
  const [budgetWarn, setBudgetWarn] = useState(false);
  const [forceOverBudget, setForceOverBudget] = useState(false);
  const [contextRefreshKey, setContextRefreshKey] = useState(0);
  /** Residual (jd): Settings depth-tier prefill for hosted book DR. */
  const [researchTier, setResearchTier] = useState<ResearchLaunchTier>("deep");
  const [depthPrefill, setDepthPrefill] = useState<
    "pending" | "installed" | "none" | "error"
  >("pending");

  // Residual (jd): prefill depth from Settings (parity marketplace jc / Midnight Oil gt).
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

  // Residual (en): selection identity for float DR + budget.
  const { selection_text: researchSelection, from_highlight: fromHighlight } =
    useMemo(
      () =>
        resolveHostedResearchSelection({
          title,
          assetId,
          fallbackDocId: docId,
          highlightText,
        }),
      [title, assetId, docId, highlightText],
    );

  const captureHighlight = useCallback(() => {
    if (typeof window === "undefined" || !window.getSelection) return;
    const text = (window.getSelection()?.toString() || "").trim();
    // Only replace when the user actually selected something; empty
    // mouseup (click) keeps the last highlight so budget/DR stay stable.
    if (text) {
      setHighlightText(text.slice(0, 8000));
    }
  }, []);

  const clearHighlight = useCallback(() => {
    setHighlightText("");
  }, []);

  const onProjectionChange = useCallback(
    (p: ResearchLaunchBudgetProjection) => {
      setBudgetWarn(p.wouldExceedBudget === true);
    },
    [],
  );
  // Residual (ej): same naming as DR host context refresh chokepoint.
  const onContextNeedsRefresh = useCallback(() => {
    setContextRefreshKey((k) => k + 1);
  }, []);

  const spinDeepResearch = async (viewMode: WindowMode = "floating") => {
    if (!assetId) {
      setError("document_id is required for deep research");
      return;
    }
    if (!isHtml) {
      setError("view_format must be html");
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
    setPubRefStatus(null);
    try {
      // Capture latest selection at fire time (mouseup may lag React state).
      let selection = researchSelection;
      let goal = fromHighlight
        ? `Deep-research the highlighted passage from hosted book «${title}»`
        : `Deep-research the hosted book/document «${title}»`;
      if (typeof window !== "undefined" && window.getSelection) {
        const live = (window.getSelection()?.toString() || "").trim();
        if (live) {
          selection = live.slice(0, 8000);
          goal = `Deep-research the highlighted passage from hosted book «${title}»`;
          setHighlightText(selection);
        }
      }
      // Residual (er): optional knowledge-dense publication refs (HTML-first hydrate).
      const refs = parsePublicationRefs(pubRefs);
      if (refs.length > 0) {
        const hydrated = await hydratePublicationRefs(refs);
        setPubRefStatus(
          `Hydrated ${hydrated.ok.length} pub asset(s)` +
            (hydrated.failed.length
              ? ` · ${hydrated.failed.length} failed`
              : "") +
            " · HTML-first",
        );
      }
      const out = await launchFloatingDeepResearch({
        asset_id: assetId,
        selection_text: selection,
        goal_hint: goal,
        view_mode: viewMode,
        references: refs.length ? refs : undefined,
        research_tier: researchTier,
      });
      setLastWindowId(out.window_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="flex h-full flex-col gap-3 bg-transparent p-6"
      data-testid="hosted-html-document-host"
      data-view-format={viewFormat}
      data-document-id={props.document_id ?? ""}
    >
      <header className="space-y-1 border-b border-black/10 pb-3 dark:border-white/10">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h1 className="font-serif text-lg text-ink dark:text-parchment">
              {title}
            </h1>
            <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
              {docId}
              {props.license_class ? ` · ${props.license_class}` : ""}
              {" · "}
              content stance: {isHtml ? "HTML" : viewFormat} · not PDF
            </p>
          </div>
          {/* Residual (da): driver readout on reading host (parity with DR). */}
          <div className="flex flex-col items-end gap-1">
            <DecisionTreeDriverBadge researchTier={researchTier} />
            {/* Residual (fl): handoff draft HTML into Write mode (import lands later). */}
            {assetId && isHtml ? (
              <a
                href={`/write?html_draft=${encodeURIComponent(assetId)}`}
                data-testid="hosted-html-open-write"
                data-view-format="html"
                className="text-[11px] font-mono underline opacity-80 hover:opacity-100"
                title="Open Write with this HTML document as draft handoff (full import residual fl+)"
              >
                Open Write (HTML draft handoff)
              </a>
            ) : null}
          </div>
        </div>
      </header>

      {!isHtml ? (
        <p
          className="text-sm font-mono text-emperor"
          data-testid="hosted-html-reject-pdf"
        >
          view_format must be html — PDF is not a valid reading surface.
        </p>
      ) : html ? (
        <div
          className="prose min-h-0 flex-1 overflow-auto text-sm text-ink dark:text-parchment"
          data-testid="hosted-html-body"
          // Residual (en): capture highlight for float deep research.
          onMouseUp={captureHighlight}
          onKeyUp={captureHighlight}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : (
        <p
          className="text-sm font-mono text-ink-mute"
          data-testid="hosted-html-empty"
        >
          No HTML body yet — host the book into your account first.
        </p>
      )}

      {/* Residual (da/en): budget + float deep research from hosted book. */}
      {assetId && isHtml ? (
        <section
          className="mt-2 space-y-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="hosted-html-research-launch"
          data-view-format="html"
          data-from-highlight={fromHighlight ? "true" : "false"}
        >
          <div
            className="rounded border border-ink/10 p-2 text-[11px] font-mono dark:border-bright/10"
            data-testid="hosted-html-selection-preview"
            data-from-highlight={fromHighlight ? "true" : "false"}
          >
            <p className="text-shadow-1 dark:text-moonlight">
              {fromHighlight
                ? "Deep research will use your highlight:"
                : "No highlight — deep research uses whole document identity:"}
            </p>
            <p
              className="mt-1 max-h-16 overflow-auto text-ink dark:text-parchment"
              data-testid="hosted-html-selection-text"
            >
              {researchSelection.slice(0, 400)}
              {researchSelection.length > 400 ? "…" : ""}
            </p>
            {fromHighlight ? (
              <button
                type="button"
                className="mt-1 underline"
                data-testid="hosted-html-clear-highlight"
                onClick={clearHighlight}
                disabled={busy}
              >
                Clear highlight (use whole document)
              </button>
            ) : (
              <p className="mt-1 text-ink-mute dark:text-moonlight">
                Select text in the book above, then open deep research.
              </p>
            )}
          </div>
          {/* Residual (er): ground float DR with arxiv/substack/URL refs. */}
          <div
            className="space-y-1"
            data-testid="hosted-html-pub-refs"
            data-view-format="html"
          >
            <label
              className="text-[10px] font-mono uppercase tracking-wider text-ink-mute dark:text-moonlight"
              htmlFor="hosted-html-refs-input"
            >
              Ground with pubs (optional)
            </label>
            <textarea
              id="hosted-html-refs-input"
              data-testid="hosted-html-refs-input"
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
                data-testid="hosted-html-refs-status"
                role="status"
              >
                {pubRefStatus}
              </p>
            ) : null}
          </div>
          {/* Residual (jd): Settings depth prefill + tier pick for hosted book DR. */}
          <div
            data-testid="hosted-html-dr-depth-mount"
            data-research-tier={researchTier}
            data-depth-prefill={depthPrefill}
            data-view-format="html"
          >
            <p
              className="text-[10px] font-mono text-ink-mute dark:text-moonlight mb-1"
              data-testid="hosted-html-dr-depth-prefill"
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
              promptText={researchSelection}
              researchTier={researchTier}
              allowTierPick
              onResearchTierChange={setResearchTier}
              onProjectionChange={onProjectionChange}
            />
          </div>
          {budgetWarn ? (
            <label
              className="flex items-center gap-2 text-[11px] font-mono text-emperor"
              data-testid="hosted-html-over-budget-warn"
            >
              <input
                type="checkbox"
                data-testid="hosted-html-force-over-budget"
                checked={forceOverBudget}
                onChange={(e) => setForceOverBudget(e.target.checked)}
                disabled={busy}
              />
              Force open despite budget projection
            </label>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="rounded border border-ink/20 px-3 py-1.5 text-xs font-mono dark:border-bright/20"
              data-testid="hosted-html-deep-research"
              disabled={busy || (budgetWarn && !forceOverBudget)}
              onClick={() => void spinDeepResearch("floating")}
            >
              {busy
                ? "Opening…"
                : fromHighlight
                  ? "Deep research highlight (window)"
                  : "Deep research (window)"}
            </button>
            {/* Residual (es): full window over the working region. */}
            <button
              type="button"
              className="rounded border border-ink/20 px-3 py-1.5 text-xs font-mono dark:border-bright/20"
              data-testid="hosted-html-deep-research-full"
              disabled={busy || (budgetWarn && !forceOverBudget)}
              onClick={() => void spinDeepResearch("full")}
              title="Open deep research expanded to full working region"
            >
              {busy ? "Opening…" : "Deep research (full)"}
            </button>
            {lastWindowId ? (
              <span
                className="text-[11px] font-mono text-aurora"
                data-testid="hosted-html-research-window-id"
                role="status"
              >
                Window {lastWindowId}
              </span>
            ) : null}
            {error ? (
              <span
                className="text-[11px] font-mono text-emperor"
                role="alert"
                data-testid="hosted-html-research-error"
              >
                {error}
              </span>
            ) : null}
          </div>
        </section>
      ) : null}

      {assetId ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="hosted-html-twins-mount"
          data-view-format="html"
        >
          {/* Residual (ez): remount twins with context refresh key. */}
          <div
            data-testid="hosted-html-twins-refresh"
            data-refresh-key={String(contextRefreshKey)}
          >
            <TwinNotesPanel
              key={`twins-${assetId}-${contextRefreshKey}`}
              assetId={assetId}
              spawnId={null}
              autoLoad
              autoSeedIfEmpty
              autoPromoteAfterLoad
              onPromoted={onContextNeedsRefresh}
              seedTitle={title}
              seedBodyText={
                html ? html.replace(/<[^>]+>/g, " ").slice(0, 500) : title
              }
              researchTier={researchTier}
            />
          </div>
        </section>
      ) : null}

      {assetId ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="hosted-html-context-mount"
          data-view-format="html"
        >
          <div
            data-testid="hosted-html-context-refresh"
            data-refresh-key={String(contextRefreshKey)}
          >
            <ResearchContextPanel
              key={`ctx-${assetId}-${contextRefreshKey}`}
              assetId={assetId}
              spawnId={null}
              autoLoad
            />
          </div>
        </section>
      ) : null}

      {/* Residual (eu): multi-select open DR spawns → merge into this book. */}
      {assetId && isHtml && availableSpawnIds.length > 0 ? (
        <section
          className="mt-2 border-t border-black/10 pt-4 dark:border-white/10"
          data-testid="hosted-html-collective-mount"
          data-view-format="html"
          data-available-spawn-count={String(availableSpawnIds.length)}
        >
          <CollectiveResearchPanel
            availableSpawnIds={availableSpawnIds}
            parentAssetId={assetId}
            onDocMerged={onContextNeedsRefresh}
          />
        </section>
      ) : null}
    </div>
  );
}
