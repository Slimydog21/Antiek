import { LemonTag } from "../../components/lemon";
import { cardLift } from "../../design/motion";
import type { BookSummary } from "../../api/books";
import { servabilityLabel } from "../../api/books";
import { emitWernerExperience } from "../../werner/reactionBus";

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

export default function BookCard({ book, onOpen }: BookCardProps) {
  const { label, colour } = servabilityLabel(book.servability);
  const title = book.title ?? book.document_id;
  const hue = placeholderHue(book.document_id);

  return (
    <button
      type="button"
      onClick={() => {
        // Living-TV: opening a shelf book is a curious highlight glance.
        emitWernerExperience("highlight");
        onOpen?.(book.document_id);
      }}
      className="group flex flex-col text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-sun rounded-hog"
      aria-label={`Open ${title}${book.author ? ` by ${book.author}` : ""}`}
    >
      <div
        className={`relative aspect-[2/3] w-full rounded-hog border-edge border-sun overflow-hidden shadow-z1 dark:shadow-z1-night ${cardLift}`}
        style={
          book.cover_uri
            ? undefined
            : { background: `linear-gradient(160deg, hsl(${hue} 45% 32%), hsl(${(hue + 40) % 360} 50% 22%))` }
        }
      >
        {book.cover_uri ? (
          <img
            src={book.cover_uri}
            alt={`Cover of ${title}`}
            className="absolute inset-0 h-full w-full object-cover"
          />
        ) : (
          // Decorative cover spine — the caption below + the button's
          // aria-label carry the real, announced title.
          <span
            aria-hidden="true"
            className="absolute inset-0 flex items-center p-3 font-serif text-ice-1 text-sm leading-tight line-clamp-6"
          >
            {title}
          </span>
        )}
        <span className="absolute top-1.5 right-1.5">
          <LemonTag colour={colour} dot>
            {label}
          </LemonTag>
        </span>
      </div>
      <p className="mt-2 font-serif text-sm text-ink dark:text-bright truncate" title={title}>
        {title}
      </p>
      <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight truncate">
        {book.author ?? "Unknown author"}
        {book.page_count > 0 && <> · {book.page_count}p</>}
      </p>
    </button>
  );
}
