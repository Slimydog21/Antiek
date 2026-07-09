import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { LemonButton } from "../../components/lemon";
import { spinResearch } from "../../api/books";
import { track } from "../../lib/analytics";
import { launchFloatingDeepResearch } from "./launchFloatingDeepResearch";

/**
 * ResearchThis (Read SPR-08 + residual cc) — spin deep research from the
 * current passage.
 *
 * Residual (cc): primary path opens a **floating** deep_research_session
 * window via engagement sessions/open + openDeepResearchFromHighlight
 * (HTML-first host with twins/collective/merge). Full-page workstation
 * handoff remains available as an explicit secondary action.
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

  const selection =
    (passageText || "").trim() ||
    `Page ${pageIndex + 1} of document ${documentId}`;

  const spinFloating = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await launchFloatingDeepResearch({
        asset_id: documentId,
        selection_text: selection,
        page: pageIndex,
        goal_hint: "Deep-research the highlighted passage from reading",
        view_mode: "floating",
      });
      track("reading_research_spun", {
        document_id: documentId,
        page_index: pageIndex,
        has_passage: Boolean(passageText),
        mode: "floating_window",
        session_id: out.session_id,
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
    <div
      className="inline-flex flex-wrap items-center gap-2"
      data-testid="research-this"
    >
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
  );
}
