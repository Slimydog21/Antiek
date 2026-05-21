// SPR-07 M2 — One pill. Small (24px), bordered, subtle until hover.
//
// The pill is the in-gutter affordance for a single cross-doc link.
// Its visual budget is 24px square (per the M2 acceptance criterion).
// Inside the pill we show:
//   - a 1-2 character summary derived from the source doc title
//   - a source-leg tint (similarity/user-asserted/citation)
//
// Hover is the discovery affordance — full preview (title, snippet,
// score) is rendered by ``CitePreview`` and positioned by the parent.

import { useCallback, useState } from "react";

import type { CrossDocLink } from "../../../../api/cross_doc/links";

interface GutterPillProps {
  link: CrossDocLink;
  /** Fires on click — propagates the cite-jump intent up to the
   *  Gutter, which routes the navigation and emits the click
   *  event. */
  onOpen: () => void;
  /** Hover callback — true on enter, false on leave. */
  onHoverChange?: (isHovered: boolean) => void;
}

const SOURCE_STYLES: Record<CrossDocLink["source"], string> = {
  // Similarity is the workhorse leg — neutral grey.
  similarity: "border-stone-300 bg-stone-50 text-stone-700",
  // User-asserted carries operator intent — distinguish with a
  // violet (matches the legacy CrossDocSidebar's bridging color so
  // operators don't relearn meaning).
  user_asserted: "border-violet-300 bg-violet-50 text-violet-800",
  // Citation edges are amber — matches the cite-jump pulse colour.
  citation: "border-amber-300 bg-amber-50 text-amber-800",
};

function abbreviateTitle(title: string): string {
  // Take the first letter of the first one or two words. Falls back
  // to "?" if the title is empty.
  const words = title.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

export default function GutterPill({
  link,
  onOpen,
  onHoverChange,
}: GutterPillProps) {
  const [hovered, setHovered] = useState(false);
  const onEnter = useCallback(() => {
    setHovered(true);
    onHoverChange?.(true);
  }, [onHoverChange]);
  const onLeave = useCallback(() => {
    setHovered(false);
    onHoverChange?.(false);
  }, [onHoverChange]);

  const sourceStyle = SOURCE_STYLES[link.source];

  return (
    <button
      type="button"
      data-testid="gutter-pill"
      data-source={link.source}
      data-document-id={link.document_id}
      data-chunk-id={link.chunk_id}
      title={link.doc_title}
      onClick={onOpen}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      className={
        "w-[24px] h-[24px] rounded-full border flex items-center " +
        "justify-center text-[10px] font-mono font-semibold " +
        "transition-all duration-150 cursor-pointer " +
        sourceStyle +
        (hovered ? " ring-2 ring-stone-400 scale-110" : " opacity-70")
      }
    >
      {abbreviateTitle(link.doc_title)}
    </button>
  );
}
