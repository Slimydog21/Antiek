// SPR-11 / M3 — Per-theme block renderer.
//
// One theme_blocks row, rendered:
//
//   - Promoted block: dispatch to the Tier-2 renderer (the per-doc
//     block components in apps/reading/src/modes/Notebook/blocks/)
//     so highlight cards, voice blocks, etc. look identical to how
//     they appear in the per-doc surface. Back-link "From: <doc>
//     / <notebook>" hangs above the dispatched body.
//
//   - Prose block: render the operator's TipTap node payload as
//     plain prose. Operator-authored framing IS allowed at Tier 3
//     (the SPR-08 no-authoring rule was Tier-2-only).
//
//   - Stale placeholder: when the source Tier-2 block has been
//     deleted (is_stale === true), we still render the cached
//     content but greyed-out + with a "Source removed" banner.
//     Dismiss removes it from the visible list (the DB row stays
//     for audit; see ThemePersistence.dismiss_stale).
//
// Drag handle + remove button live in the right rail. The drag
// handle uses HTML5 native drag (no react-dnd dep) so we don't
// bloat the bundle for a feature with low interaction volume.

import { useState } from "react";

import type { ThemeBlock } from "../../../api/themes/by-slug";
import { renderBlock } from "./blocks";
import type { PerDocNotebookBlock } from "../../../api/notebooks/by-doc";

export interface ThemeBlockViewProps {
  block: ThemeBlock;
  /** Drag handlers for HTML5 reordering. The outer PerThemeNotebook
   * wires drag start/end into reorderThemeBlocks. */
  onDragStart?: (themeBlockId: string) => void;
  onDragOver?: (themeBlockId: string) => void;
  onDrop?: (themeBlockId: string) => void;
  /** Remove the theme_blocks row. The source Tier-2 block stays. */
  onRemove?: (themeBlockId: string) => void;
  /** Dismiss a stale placeholder (soft-delete). */
  onDismissStale?: (themeBlockId: string) => void;
  /** Cite-jump callback (mirrors PerDocBlockProps.onCiteJump). */
  onCiteJump?: (targetDocumentId: string, targetChunkId?: string | null) => void;
  /** Edit prose content (for prose blocks only). Same shape as the
   * Tier-2 onEditFraming so the existing BlockShell renderer can
   * be reused — but Tier-3 prose is the whole block body, not just
   * the framing. */
  onEditProseContent?: (themeBlockId: string, text: string) => void;
}

/** Convert a ThemeBlock into the shape the Tier-2 renderer accepts
 *  (PerDocNotebookBlock). The fields are isomorphic except for the
 *  block_id key — we adapt the wire shape transparently. */
function asPerDocBlock(tb: ThemeBlock): PerDocNotebookBlock {
  return {
    block_id: tb.theme_block_id,
    notebook_id: tb.source_notebook_id ?? tb.theme_id,
    block_type: tb.block_type as PerDocNotebookBlock["block_type"],
    source_event_ids: [],
    content_json: tb.content_json,
    position: tb.sort_order,
    demoted_at: null,
    edited_at: null,
    created_at: tb.created_at,
    document_id: tb.source_document_id,
  };
}

export default function ThemeBlockView(props: ThemeBlockViewProps): JSX.Element {
  const { block } = props;
  const [isDragOver, setIsDragOver] = useState(false);

  const handleDragStart = (e: React.DragEvent<HTMLDivElement>) => {
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", block.theme_block_id);
    if (props.onDragStart) props.onDragStart(block.theme_block_id);
  };
  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(true);
    if (props.onDragOver) props.onDragOver(block.theme_block_id);
  };
  const handleDragLeave = () => setIsDragOver(false);
  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    if (props.onDrop) props.onDrop(block.theme_block_id);
  };

  // Stale placeholder
  if (block.is_stale) {
    return (
      <div
        className="relative border border-amber-200 rounded-md bg-amber-50/60 p-3"
        data-theme-block-id={block.theme_block_id}
        data-stale="true"
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] font-mono text-amber-700">
            ⚠ Source removed — showing last-known content
          </span>
          {props.onDismissStale && (
            <button
              type="button"
              onClick={() => props.onDismissStale?.(block.theme_block_id)}
              className="text-[11px] font-mono text-amber-700 hover:text-amber-900 underline"
              data-testid={`dismiss-stale-${block.theme_block_id}`}
            >
              dismiss
            </button>
          )}
        </div>
        <div className="opacity-60 grayscale">
          {renderBlock({ block: asPerDocBlock(block) })}
        </div>
      </div>
    );
  }

  // Prose: render an inline editable body
  if (block.block_type === "prose") {
    return (
      <div
        className={
          "relative border border-stone-200 rounded-md bg-stone-50/40 px-4 py-3 " +
          (isDragOver ? "ring-2 ring-blue-300" : "")
        }
        draggable
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        data-theme-block-id={block.theme_block_id}
        data-block-type="prose"
      >
        <ProseEditor block={block} onEdit={props.onEditProseContent} />
        <BlockRail
          themeBlockId={block.theme_block_id}
          onRemove={props.onRemove}
        />
      </div>
    );
  }

  // Promoted block: back-link header + dispatched body
  return (
    <div
      className={
        "relative " +
        (isDragOver ? "ring-2 ring-blue-300 rounded-md" : "")
      }
      draggable
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      data-theme-block-id={block.theme_block_id}
    >
      {/* Back-link */}
      <p
        className="text-[11px] font-mono text-stone-500 mb-1"
        data-testid={`backlink-${block.theme_block_id}`}
      >
        From:{" "}
        {block.source_document_id ? (
          <a
            href={`/wrestle/${encodeURIComponent(block.source_document_id)}/notebook`}
            className="underline hover:text-stone-900"
          >
            {block.source_notebook_title ||
              block.source_document_id.slice(-10) ||
              "source notebook"}
          </a>
        ) : (
          <span className="italic">unknown source</span>
        )}
      </p>
      {renderBlock({
        block: asPerDocBlock(block),
        onCiteJump: props.onCiteJump,
      })}
      <BlockRail
        themeBlockId={block.theme_block_id}
        onRemove={props.onRemove}
      />
    </div>
  );
}

function BlockRail({
  themeBlockId,
  onRemove,
}: {
  themeBlockId: string;
  onRemove?: (id: string) => void;
}): JSX.Element {
  return (
    <div className="absolute -right-8 top-0 flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
      {onRemove && (
        <button
          type="button"
          onClick={() => onRemove(themeBlockId)}
          className="text-[10px] font-mono px-1.5 py-0.5 rounded text-stone-500 hover:text-red-700 hover:bg-red-50"
          data-testid={`remove-theme-block-${themeBlockId}`}
          title="Remove from theme (source block untouched)"
        >
          ×
        </button>
      )}
    </div>
  );
}

function ProseEditor({
  block,
  onEdit,
}: {
  block: ThemeBlock;
  onEdit?: (themeBlockId: string, text: string) => void;
}): JSX.Element {
  const initial =
    typeof block.content_json?.text === "string"
      ? (block.content_json.text as string)
      : "";
  const [value, setValue] = useState<string>(initial);

  return (
    <textarea
      className={
        "w-full bg-transparent text-sm font-serif text-stone-800 leading-relaxed " +
        "border-0 focus:outline-none focus:ring-1 focus:ring-stone-300 rounded-sm " +
        "resize-none px-1 py-0.5"
      }
      rows={Math.max(2, value.split("\n").length)}
      placeholder="Operator framing… (this is the Tier-3 narrative the theme builds)"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => onEdit?.(block.theme_block_id, value)}
      data-testid={`prose-editor-${block.theme_block_id}`}
    />
  );
}
