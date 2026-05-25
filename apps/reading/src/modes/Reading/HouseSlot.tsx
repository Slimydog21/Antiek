import { LemonTag } from "../../components/lemon";

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
    // Nothing to promote — a neutral, non-broken house card.
    return (
      <div className="flex items-center justify-center text-[11px] font-mono text-ink-mute dark:text-moonlight">
        <LemonTag colour="muted">From the library</LemonTag>
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={() => onOpen?.(promo.documentId)}
      className="flex items-center gap-3 w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-sun rounded-md px-2 py-1"
      aria-label={`Recommended from the library: ${promo.title}`}
    >
      <LemonTag colour="aurora">Next read</LemonTag>
      <span className="min-w-0">
        <span className="font-serif text-sm text-ink dark:text-bright truncate block">
          {promo.title}
        </span>
        <span className="text-[11px] font-mono text-shadow-1 dark:text-moonlight truncate block">
          {promo.author ?? "Unknown author"} · from the library
        </span>
      </span>
    </button>
  );
}
