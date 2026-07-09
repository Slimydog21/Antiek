import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { LemonButton } from "../../components/lemon";
import { spinResearch } from "../../api/books";
import { ResearchLaunchBudgetPanel } from "../../components/engagement/ResearchLaunchBudgetPanel";
import { track } from "../../lib/analytics";
import {
  hydratePublicationRefs,
  parsePublicationRefs,
} from "../ResearchWorkstation/publicationRefs";
import { launchFloatingDeepResearch } from "./launchFloatingDeepResearch";

/**
 * ResearchThis (Read SPR-08 + residual cc/cu/cx/cy) — spin deep research from
 * the current passage.
 *
 * Residual (cc): primary path opens a **floating** deep_research_session
 * window via engagement sessions/open + openDeepResearchFromHighlight.
 * Residual (cu): optional arxiv/substack/URL refs hydrate + attach on open.
 * Residual (cx): budget projection before fire (parity with StartResearch).
 * Residual (cy): decision-tree model_id resolved inside launchFloatingDeepResearch
 * (shared chokepoint with float-menu / HighlightToolbar).
 * Full-page workstation handoff remains an explicit secondary action.
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastWindowId, setLastWindowId] = useState<string | null>(null);
  const [pubRefs, setPubRefs] = useState("");
  const [pubRefStatus, setPubRefStatus] = useState<string | null>(null);

  const selection =
    (passageText || "").trim() ||
    `Page ${pageIndex + 1} of document ${documentId}`;

  const spinFloating = async () => {
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
      const out = await launchFloatingDeepResearch({
        asset_id: documentId,
        selection_text: selection,
        page: pageIndex,
        goal_hint: "Deep-research the highlighted passage from reading",
        view_mode: "floating",
        references: refs.length ? refs : undefined,
      });
      track("reading_research_spun", {
        document_id: documentId,
        page_index: pageIndex,
        has_passage: Boolean(passageText),
        mode: "floating_window",
        session_id: out.session_id,
        publication_ref_count: refs.length,
        model_id: out.model_id,
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
      {/* Residual (cx): daily budget + prompt projection before float open. */}
      <div
        className="max-w-md"
        data-testid="research-this-budget-mount"
        data-view-format="html"
      >
        <ResearchLaunchBudgetPanel
          promptText={selection}
          researchTier="deep"
        />
      </div>
      <div className="inline-flex flex-wrap items-center gap-2">
        <LemonButton
          type="button"
          variant="secondary"
          size="sm"
          disabled={busy}
          onClick={() => void spinFloating()}
          title="Open deep research in a floating window over the scene"
          data-testid="research-this-floating"
        >
          {busy ? "Opening…" : "Deep research (window)"}
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
    </div>
  );
}
