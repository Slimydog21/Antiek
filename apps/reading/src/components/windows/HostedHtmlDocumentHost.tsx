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
 *
 * Props arrive via WindowsLayer: `<Renderer {...win.payload} />`.
 */

import { useCallback, useMemo, useState } from "react";

import { launchFloatingDeepResearch } from "../../modes/Reading/launchFloatingDeepResearch";
import { DecisionTreeDriverBadge } from "../engagement/DecisionTreeDriverBadge";
import { ResearchContextPanel } from "../engagement/ResearchContextPanel";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
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

  const [highlightText, setHighlightText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastWindowId, setLastWindowId] = useState<string | null>(null);
  const [budgetWarn, setBudgetWarn] = useState(false);
  const [forceOverBudget, setForceOverBudget] = useState(false);
  const [contextRefreshKey, setContextRefreshKey] = useState(0);

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

  const spinFloating = async () => {
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
      const out = await launchFloatingDeepResearch({
        asset_id: assetId,
        selection_text: selection,
        goal_hint: goal,
        view_mode: "floating",
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
          <DecisionTreeDriverBadge />
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
          <ResearchLaunchBudgetPanel
            promptText={researchSelection}
            researchTier="deep"
            onProjectionChange={onProjectionChange}
          />
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
              onClick={() => void spinFloating()}
            >
              {busy
                ? "Opening…"
                : fromHighlight
                  ? "Deep research highlight (window)"
                  : "Deep research (window)"}
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
          <TwinNotesPanel
            assetId={assetId}
            spawnId={null}
            autoLoad
            autoSeedIfEmpty
            autoPromoteAfterLoad
            onPromoted={onContextNeedsRefresh}
            seedTitle={title}
            seedBodyText={html ? html.replace(/<[^>]+>/g, " ").slice(0, 500) : title}
          />
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
    </div>
  );
}
