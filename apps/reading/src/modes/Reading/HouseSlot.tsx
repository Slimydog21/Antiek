import { LemonTag } from "../../components/lemon";
// Book marketplace port invent — zero-buyer house next-read is the marketplace door.
import bookMarketplaceArt from "../../brand/werner/poses/session/werner_book_marketplace_port_session_v1.webp";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * The zero-buyer house state (Read SPR-05 M3). v1 ships with no ad
 * buyers, so this is the DEFAULT fill, fully designed — not a stub behind
 * a "no fill" branch. It surfaces a genuinely useful recommendation (a
 * servable book worth reading next), never blank/filler spam. Honest: it
 * is clearly labelled "From the library", not dressed up as a paid ad.
 */

export interface HousePromoView {
  documentId: string;
  title: string;
  author: string | null;
}

export interface HouseSlotProps {
  promo: HousePromoView | null;
  onOpen?: (documentId: string) => void;
}

export default function HouseSlot({ promo, onOpen }: HouseSlotProps) {
  if (!promo) {
    // Nothing to promote — a neutral, non-broken house card. The slot NEVER
    // blanks: this is the fully-designed default fill, not a "no fill" branch.
    // The "From the library" tag is the SINGLE provenance label here (and the
    // text the AdBorder / WindowAdBorder never-blank guards assert against).
    return (
      <div className="flex items-center justify-center text-[11px] font-mono text-ink-mute dark:text-moonlight">
        <LemonTag colour="muted">From the library</LemonTag>
      </div>
    );
  }
  // SPR-07 M4 — declutter the doubled "from the library" provenance. Before,
  // the card said the SAME phrase TWICE: once in the aria-label ("Recommended
  // from the library: …") and again, redundantly, suffixed onto the visible
  // author line ("<author> · from the library"). Now the provenance appears
  // exactly ONCE — in the aria-label, as a single clear phrase. The visible
  // card keeps its useful framing: the "Next read" recommendation tag (the
  // honest "a book worth reading next, not a paid ad" signal this file ships),
  // the title, and the author alone (no provenance suffix cluttering it). The
  // slot still fully fills — the promo card renders exactly as before minus
  // the redundant copy — and AdBorder's never-blank fill logic is untouched.
  return (
    <button
      type="button"
      onClick={() => {
        // Living-TV: next-read house promo is a curious highlight glance.
        emitWernerExperience("highlight");
        onOpen?.(promo.documentId);
      }}
      className="flex items-center gap-3 w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-sun rounded-md px-2 py-1"
      aria-label={`Next read from the library: ${promo.title}`}
    >
      {/* Living-TV invent — marketplace port / next-read product door. */}
      <img
        src={bookMarketplaceArt}
        alt=""
        aria-hidden="true"
        data-testid="house-slot-living-tv-art"
        className="h-9 w-14 shrink-0 rounded object-cover object-center"
        loading="lazy"
        decoding="async"
      />
      <LemonTag colour="aurora">Next read</LemonTag>
      <span className="min-w-0">
        <span className="font-serif text-sm text-ink dark:text-bright truncate block">
          {promo.title}
        </span>
        <span className="text-[11px] font-mono text-shadow-1 dark:text-moonlight truncate block">
          {promo.author ?? "Unknown author"}
        </span>
      </span>
    </button>
  );
}
