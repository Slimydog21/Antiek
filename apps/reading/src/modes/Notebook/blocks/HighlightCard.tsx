// SPR-08 / M4 — highlight_card renderer.
//
// Source event: highlight_created. Shows the captured passage + its
// page-ish location (chunk_id) and offers a cite-jump back to the
// PDF region. Click on the passage routes through onCiteJump if a
// chunk_id is available.
//
// TipTap node-view shape
// ----------------------
// node.attrs maps 1:1 to the block fields:
//   - node.attrs.passage_text → content_json.passage_text
//   - node.attrs.color        → content_json.color
//   - node.attrs.chunk_id     → content_json.chunk_id (for cite-jump)
// updateAttributes(attrs) is the framing-edit; the substrate text
// is read-only.

import BlockShell from "./BlockShell";
import type { PerDocBlockProps } from "./types";

interface HighlightContent {
  passage_text?: string | null;
  color?: string | null;
  tag?: string | null;
  chunk_id?: string | null;
  highlight_id?: string | null;
}

export default function HighlightCard(props: PerDocBlockProps): JSX.Element {
  const content = (props.block.content_json as unknown as HighlightContent) || {};
  const passage = (content.passage_text || "").trim();
  const chunkId = content.chunk_id;

  const onPassageClick = () => {
    if (!chunkId) return;
    if (!props.onCiteJump) return;
    // The highlight always belongs to the document the notebook is
    // scoped to; the cite-jump just scrolls within that document.
    if (props.block.document_id) {
      props.onCiteJump(props.block.document_id, chunkId);
    }
  };

  return (
    <BlockShell {...props} typeLabel="highlight">
      <blockquote
        className={
          "border-l-2 pl-3 italic text-stone-800 " +
          (chunkId
            ? "cursor-pointer hover:bg-stone-50"
            : "")
        }
        style={{
          borderColor: highlightColor(content.color),
        }}
        onClick={onPassageClick}
        data-testid={`highlight-passage-${props.block.block_id}`}
      >
        {passage || (
          <span className="text-stone-400 not-italic">
            (no passage text recorded)
          </span>
        )}
      </blockquote>
      {content.tag && (
        <p className="mt-1 text-[11px] font-mono text-stone-500">
          tag: {content.tag}
        </p>
      )}
    </BlockShell>
  );
}

function highlightColor(c?: string | null): string {
  switch (c) {
    case "yellow":
      return "#facc15";
    case "green":
      return "#22c55e";
    case "blue":
      return "#3b82f6";
    case "pink":
      return "#ec4899";
    default:
      return "#a8a29e";
  }
}
