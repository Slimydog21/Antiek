// SPR-07 M3 — Pill hover preview.
//
// Shows: doc title, page, 200-char snippet, score explanation,
// source-leg badge, "Open" button. Acceptance: appears within 150ms
// of hover (the hover handler in Gutter sets state synchronously;
// React commit + paint is well under 150ms for a card this small).
//
// The 200-char snippet trim happens in the Python query layer
// (services/cross_doc/query.py:_truncate_snippet). The UI surface
// trusts that the snippet is already at the right length and only
// adds presentation.

import type { CrossDocLink } from "../../../api/cross_doc/links";

interface CitePreviewProps {
  link: CrossDocLink;
  /** Click on the "Open" button — routes through the parent's
   *  cite-jump handler so a single funnel-event emission point
   *  records the click. */
  onOpen: () => void;
}

const SOURCE_BADGE_LABEL: Record<CrossDocLink["source"], string> = {
  similarity: "similarity",
  user_asserted: "user-asserted",
  citation: "citation",
};

const SOURCE_BADGE_STYLE: Record<CrossDocLink["source"], string> = {
  similarity: "bg-stone-200 text-stone-700",
  user_asserted: "bg-violet-100 text-violet-800",
  citation: "bg-amber-100 text-amber-800",
};

export default function CitePreview({ link, onOpen }: CitePreviewProps) {
  return (
    <div
      data-testid="cite-preview"
      className={
        "w-[320px] rounded-md border border-stone-300 bg-white " +
        "shadow-lg p-3 flex flex-col gap-2 text-sm"
      }
      // Stop hover-out events from propagating up to the Gutter while
      // the operator is reading the preview. Without this, moving
      // the mouse from the pill to the preview re-triggers the
      // pill's mouseleave and dismisses the preview before they can
      // click Open. The 200ms grace-period on dismiss (M3) is
      // implemented at the Gutter level.
      onMouseEnter={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-stone-900 font-semibold text-[13px] leading-tight truncate">
          {link.doc_title}
        </h4>
        <span
          className={
            "text-[10px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded " +
            SOURCE_BADGE_STYLE[link.source]
          }
        >
          {SOURCE_BADGE_LABEL[link.source]}
        </span>
      </div>
      <div className="text-[11px] font-mono text-stone-500">
        page {link.page} ·{" "}
        <span title={`fused score ${link.score}`}>
          score {link.score.toFixed(2)}
        </span>
      </div>
      <blockquote className="text-stone-700 text-[13px] leading-snug border-l-2 border-stone-200 pl-2">
        {link.snippet}
      </blockquote>
      <div className="flex justify-end">
        <button
          type="button"
          data-testid="cite-preview-open"
          onClick={onOpen}
          className={
            "text-xs px-3 py-1 bg-stone-900 text-white rounded " +
            "hover:bg-stone-700 transition-colors"
          }
        >
          Open
        </button>
      </div>
    </div>
  );
}
