// SPR-08 / M4 — Block shell.
//
// The frame around every block: shows the source-event badge, the
// demote affordance on hover, and the editable operator-framing
// prose textarea below the substrate content. Each block-type-
// specific component renders its body inside ``<BlockShell>``.
//
// No "+ new block" button anywhere. The shell exposes demote +
// edit-framing only; creation is exclusively the auto-populator's
// path. See services/notebooks/BLOCK_TAXONOMY.md "Why no + new block".

import type { ReactNode } from "react";
import { useCallback, useState } from "react";

import type { PerDocBlockProps } from "./types";
import { readFraming } from "./types";

interface ShellProps extends PerDocBlockProps {
  /** Short label shown in the source-event badge. */
  typeLabel: string;
  /** The block's substrate-sourced body. */
  children: ReactNode;
}

export default function BlockShell({
  block,
  typeLabel,
  children,
  onDemote,
  onEditFraming,
}: ShellProps): JSX.Element {
  const isDemoted = block.demoted_at !== null;
  const [framing, setFraming] = useState<string>(() => readFraming(block));

  const commitFraming = useCallback(() => {
    if (onEditFraming) onEditFraming(block.block_id, framing);
  }, [block.block_id, framing, onEditFraming]);

  return (
    <section
      className={
        "group relative border border-stone-200 rounded-md bg-white " +
        "shadow-sm hover:shadow-md transition-shadow"
      }
      data-block-id={block.block_id}
      data-block-type={block.block_type}
      data-demoted={isDemoted ? "true" : "false"}
    >
      <header className="flex items-center justify-between px-4 py-2 border-b border-stone-100">
        <span className="text-[10px] font-mono uppercase tracking-wider text-stone-500">
          {typeLabel}
          {block.source_event_ids.length > 0 && (
            <span className="ml-2 text-stone-300">
              · evt {block.source_event_ids[0].slice(-8)}
              {block.source_event_ids.length > 1 &&
                ` +${block.source_event_ids.length - 1}`}
            </span>
          )}
        </span>
        {onDemote && (
          <button
            type="button"
            className={
              "text-[11px] font-mono px-2 py-0.5 rounded " +
              "opacity-0 group-hover:opacity-100 transition-opacity " +
              "text-stone-500 hover:text-stone-900 hover:bg-stone-100"
            }
            onClick={() => onDemote(block.block_id, !isDemoted)}
            aria-label={isDemoted ? "restore block" : "demote block"}
            data-testid={`demote-button-${block.block_id}`}
          >
            {isDemoted ? "↑ restore" : "↓ demote"}
          </button>
        )}
      </header>

      <div className="px-4 py-3 text-sm text-stone-800 font-serif leading-relaxed">
        {children}
      </div>

      {/* Operator framing — the only editable affordance. The
        underlying substrate content (passage_text, voice id, etc.)
        stays read-only. */}
      {onEditFraming && (
        <footer className="px-4 py-2 border-t border-stone-100 bg-stone-50/50">
          <textarea
            className={
              "w-full bg-transparent text-xs font-serif text-stone-700 " +
              "border-0 focus:outline-none focus:ring-1 focus:ring-stone-300 " +
              "rounded-sm px-1 py-0.5 resize-none"
            }
            rows={Math.max(1, framing.split("\n").length)}
            placeholder="add operator framing (optional)…"
            value={framing}
            onChange={(e) => setFraming(e.target.value)}
            onBlur={commitFraming}
            data-testid={`framing-textarea-${block.block_id}`}
          />
        </footer>
      )}
    </section>
  );
}
