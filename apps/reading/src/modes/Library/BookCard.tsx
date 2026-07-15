import { useEffect, useState } from "react";

import { LemonTag } from "../../components/lemon";
import { cardLift } from "../../design/motion";
import type { BookSummary } from "../../api/books";
import { servabilityLabel } from "../../api/books";

/**
 * One book on the Library shelf. Cover-forward: a real cover when the
 * book has one, otherwise a generated spine from the title (never a
 * broken image). The servability tag is always present — a gated
 * ("Preview only") book is shown, flagged, and clickable, but the card
 * never implies you can read it cover-to-cover. Spotify, not a pirate
 * shelf.
 */

export interface BookCardProps {
  book: BookSummary;
  onOpen?: (documentId: string) => void;
}

// Deterministic cover hue from the document id so a placeholder spine is
// stable across renders (no flicker) without storing a colour.
function placeholderHue(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) % 360;
  return h;
}

const COVER_VARIANTS = ["glacier", "walnut", "midnight", "parchment"] as const;

export default function BookCard({ book, onOpen }: BookCardProps) {
  const { label, colour } = servabilityLabel(book.servability);
  const title = book.title ?? book.document_id;
  const hue = placeholderHue(book.document_id);
  const [failedCover, setFailedCover] = useState<string | null>(null);
  const realCover = book.cover_uri && failedCover !== book.cover_uri ? book.cover_uri : null;
  const coverVariant = COVER_VARIANTS[hue % COVER_VARIANTS.length];

  useEffect(() => {
    if (failedCover && failedCover !== book.cover_uri) setFailedCover(null);
  }, [book.cover_uri, failedCover]);

  return (
    <button
      type="button"
      onClick={() => onOpen?.(book.document_id)}
      className="group flex min-w-0 w-full max-w-full flex-col overflow-hidden text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-sun rounded-hog"
      aria-label={`Open ${title}${book.author ? ` by ${book.author}` : ""}`}
    >
      <div
        data-cover-variant={coverVariant}
        className={`library-cover library-cover--${coverVariant} relative aspect-[2/3] w-full rounded-hog border-edge border-sun overflow-hidden shadow-z1 dark:shadow-z1-night ${cardLift}`}
      >
        {realCover ? (
          <img
            key={realCover}
            src={realCover}
            alt={`Cover of ${title}`}
            className="absolute inset-0 h-full w-full object-cover"
            onError={(event) => {
              if (event.currentTarget.currentSrc === realCover || event.currentTarget.getAttribute("src") === realCover) {
                setFailedCover(realCover);
              }
            }}
          />
        ) : (
          // Decorative cover spine — the caption below + the button's
          // aria-label carry the real, announced title.
          <span
            aria-hidden="true"
            data-testid="library-fallback-cover"
            className="library-cover__fallback absolute inset-0 flex items-end p-3 font-serif text-sm leading-tight"
          >
            <span className="line-clamp-6">{title}</span>
          </span>
        )}
        <span className="absolute top-1.5 right-1.5">
          <LemonTag colour={colour} dot>
            {label}
          </LemonTag>
        </span>
      </div>
      <p className="mt-2 w-full truncate font-serif text-sm text-ink dark:text-bright" title={title}>
        {title}
      </p>
      <p className="w-full truncate text-[11px] font-mono text-shadow-1 dark:text-moonlight">
        {book.author ?? "Unknown author"}
        {book.page_count > 0 && <> · {book.page_count}p</>}
      </p>
    </button>
  );
}
