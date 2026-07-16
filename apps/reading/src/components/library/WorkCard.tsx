import { LemonTag } from "../lemon";
import { emitWernerExperience } from "../../werner/reactionBus";
import { cardLift } from "../../design/motion";
import type { BookSummary } from "../../api/books";
import { servabilityLabel } from "../../api/books";

/**
 * WorkCard — one work on the M2 Library browse shelf (Read SPR-09).
 *
 * Title / author / source / servability, with a CLEAR servable-vs-gated
 * affordance:
 *   • servable (full text) → "Read" — opens the reader (/read/:id).
 *   • gated (metadata only) → "Claim to read" — opens the reader's gate-safe
 *     surface (the record + a bounded, server-gated preview; the reader passes
 *     `assetId=null` for a gated work so its column is untagged and no attention
 *     can accrue). It NEVER requests or renders the full-text body — a claim/
 *     metadata affordance, not a body request. (The caller, LibraryView, routes
 *     both Read and Claim through the reader, which branches servable-vs-gated;
 *     see its grid comment. This card itself only chooses which handler fires.)
 *   • taken down → no action, labelled "Removed".
 *
 * §9.0 at the UI boundary: this card renders ONLY the metadata the `/library`
 * payload carries (title, author, servability flags) — there is no body text in
 * the payload to leak, and the card requests none. Spotify-for-books: a licensed
 * shelf, flagged, never a pirate aggregator.
 */

export interface WorkCardProps {
  work: BookSummary;
  /** Open a servable work in the reader. */
  onRead?: (documentId: string) => void;
  /** Surface the gated work's metadata + claim affordance (NO body request). */
  onClaim?: (documentId: string) => void;
}

// Deterministic cover hue from the document id so a placeholder spine is stable
// across renders (no flicker) without storing a colour. Mirrors the existing
// BookCard so the two shelves never disagree on a placeholder.
function placeholderHue(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) % 360;
  return h;
}

/** A short, human source line from the servability basis — "what kind of thing
 *  this is", distinct from the author. */
function sourceLine(work: BookSummary): string {
  switch (work.servability) {
    case "public_domain":
      return "Public domain";
    case "platform_authored":
      return "Antiek original";
    case "publisher_opted_in":
      return "Publisher licensed";
    case "source_declared_open":
      return "Open license";
    case "gated_metadata_only":
      return "Catalog record";
    case "taken_down":
      return "Removed from the shelf";
  }
}

export default function WorkCard({ work, onRead, onClaim }: WorkCardProps) {
  const { label, colour } = servabilityLabel(work.servability);
  const title = work.title ?? work.document_id;
  const hue = placeholderHue(work.document_id);
  const servable = work.servable_full_text;
  const removed = work.taken_down || work.servability === "taken_down";

  const action = () => {
    if (removed) return;
    // Living-TV: shelf open / claim — curious glance (marketplace→read door).
    emitWernerExperience("highlight");
    if (servable) onRead?.(work.document_id);
    else onClaim?.(work.document_id);
  };

  const actionLabel = removed ? "Removed" : servable ? "Read" : "Claim to read";
  const ariaLabel = removed
    ? `${title} — removed from the shelf`
    : servable
      ? `Read ${title}${work.author ? ` by ${work.author}` : ""}`
      : `View metadata and claim to read ${title}${work.author ? ` by ${work.author}` : ""}`;

  return (
    <button
      type="button"
      onClick={action}
      disabled={removed}
      aria-label={ariaLabel}
      className="group flex flex-col text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-sun rounded-hog disabled:opacity-60 disabled:cursor-not-allowed"
    >
      <div
        className={`relative aspect-[2/3] w-full rounded-hog border-edge border-sun overflow-hidden shadow-z1 dark:shadow-z1-night ${
          removed ? "" : cardLift
        }`}
        style={
          work.cover_uri
            ? undefined
            : {
                background: `linear-gradient(160deg, hsl(${hue} 45% 32%), hsl(${
                  (hue + 40) % 360
                } 50% 22%))`,
              }
        }
      >
        {work.cover_uri ? (
          <img
            src={work.cover_uri}
            alt={`Cover of ${title}`}
            className="absolute inset-0 h-full w-full object-cover"
          />
        ) : (
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
        {/* The servable-vs-gated affordance, surfaced on the cover so it reads
            before the click: a servable work invites a Read, a gated one offers
            metadata + claim, a removed one shows nothing actionable. */}
        <span className="absolute bottom-0 inset-x-0 bg-ink/70 px-2 py-1 text-[11px] font-mono text-ice-0 opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 transition-opacity">
          {actionLabel}
        </span>
      </div>
      <p className="mt-2 font-serif text-sm text-ink dark:text-bright truncate" title={title}>
        {title}
      </p>
      <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight truncate">
        {work.author ?? "Unknown author"}
        {work.page_count > 0 && <> · {work.page_count}p</>}
      </p>
      <p className="text-[10.5px] font-mono text-shadow-2 dark:text-moonlight truncate">
        {sourceLine(work)}
      </p>
    </button>
  );
}
