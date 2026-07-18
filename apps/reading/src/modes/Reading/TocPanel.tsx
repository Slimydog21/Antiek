import type { TocItem } from "../../api/books";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * Table-of-contents navigation (Read SPR-03 M-TOC). Each entry jumps to
 * its page-window locator. Nesting reflects the book outline (level). An
 * entry whose page couldn't be resolved (`page_index === null`) is shown
 * disabled rather than dropped — honest about what the PDF outline gave us.
 */

export interface TocPanelProps {
  toc: TocItem[];
  currentPageIndex: number;
  onJump: (pageIndex: number) => void;
}

export default function TocPanel({ toc, currentPageIndex, onJump }: TocPanelProps) {
  if (toc.length === 0) {
    return (
      <p className="text-[11px] font-mono text-ink-mute dark:text-moonlight italic px-2">
        No table of contents in this book.
      </p>
    );
  }
  return (
    <nav aria-label="Table of contents" className="space-y-0.5">
      {toc.map((entry, i) => {
        const resolvable = entry.page_index !== null;
        const active = resolvable && entry.page_index === currentPageIndex;
        return (
          <button
            key={`${entry.title}-${i}`}
            type="button"
            disabled={!resolvable}
            onClick={() => {
              if (!resolvable) return;
              // Living-TV: TOC jump is a curious highlight glance.
              emitWernerExperience("highlight");
              onJump(entry.page_index as number);
            }}
            style={{ paddingLeft: `${8 + entry.level * 14}px` }}
            className={`w-full text-left pr-2 py-1 rounded text-[13px] font-serif truncate transition-colors ${
              active
                ? "bg-ink text-white"
                : resolvable
                  ? "text-ink dark:text-bright hover:bg-ice-3 dark:hover:bg-charcoal-1"
                  : "text-ink-mute dark:text-moonlight cursor-default"
            }`}
            title={entry.title}
          >
            {entry.title}
          </button>
        );
      })}
    </nav>
  );
}
