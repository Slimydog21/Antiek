import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { LemonButton } from "../../components/lemon";
import { spinResearch } from "../../api/books";
import { track } from "../../lib/analytics";
import { notifyResearchStarted } from "../../werner";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * ResearchThis (Read SPR-08) — spin a deep research from the current
 * passage and hand off to the Research workflow.
 *
 * The seed is built server-side and is gate-safe: a gated book contributes
 * only its snippet + metadata, never full text (the endpoint enforces it,
 * so this button cannot leak gated content into a research even if it
 * tried). On success it navigates to the spawned investigation. Return-to-
 * reading is free: the reader's page position is persisted by
 * `usePosition`, so coming back to /read/:id lands on the same page.
 *
 * This complements — does not replace — the quick rabbit hole (SPR-07):
 * a rabbit hole answers a passing question inline; spin-research is for
 * when a passage warrants real depth.
 */

export interface ResearchThisProps {
  documentId: string;
  pageIndex: number;
  /** The reader's selected text, if any. Ignored server-side for gated
   * books — passed only as a convenience for servable ones. */
  passageText?: string;
}

export default function ResearchThis({ documentId, pageIndex, passageText }: ResearchThisProps) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const spin = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await spinResearch(documentId, pageIndex, passageText);
      track("reading_research_spun", {
        document_id: documentId,
        page_index: pageIndex,
        has_passage: Boolean(passageText),
      });
      // Living-TV: spinning research from a page is a real DR start beat.
      notifyResearchStarted(res.investigation_id);
      // Hand off to the Research workflow. Return-to-reading is handled by
      // usePosition persisting this page.
      navigate(`/inv/${encodeURIComponent(res.investigation_id)}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      emitWernerExperience("deep_research_error");
      setBusy(false);
    }
  };

  return (
    <div className="inline-flex items-center gap-2">
      <LemonButton
        type="button"
        variant="secondary"
        size="sm"
        disabled={busy}
        onClick={() => void spin()}
        title="Spin a deep research from this page and hand off to the Research workflow"
      >
        {busy ? "Spinning research…" : "Research this page"}
      </LemonButton>
      {error && (
        <span className="text-[11px] font-mono text-emperor" role="alert">
          {error === "book_not_found" ? "Book not found." : error}
        </span>
      )}
    </div>
  );
}
