import HouseSlot from "./HouseSlot";
import type { HousePromoView } from "./HouseSlot";

/**
 * Ad-border slot at a page-window border (Read SPR-05 M2 + M3).
 *
 * Renders as a thin rail ABOVE or BELOW the reading column — never beside
 * it, so the reading column is never narrowed (the reading column is
 * sacred; left/right rails are a wide-viewport concern handled by the
 * reader's layout, not here). The slot is anchored to a page-window
 * locator (`slotId`, from `substrate/ad_inventory/reader_slots`), so an
 * impression dedups per (session, slot).
 *
 * Two fills: a paid `ad` (when a buyer matched) or the zero-buyer `house`
 * state (the v1 default). A slow/missing ad never blocks the page — it
 * falls through to house.
 */

export interface AdFillView {
  kind: "ad" | "house";
  /** Present when kind === "ad". */
  ad?: { advertiserName: string; creativeUrl: string; landingUrl: string };
  /** Present when kind === "house" (may be null = neutral house card). */
  house?: HousePromoView | null;
}

export interface AdBorderProps {
  slotId: string;
  position: "top" | "bottom";
  fill: AdFillView;
  onOpenHouse?: (documentId: string) => void;
}

export default function AdBorder({ slotId, position, fill, onOpenHouse }: AdBorderProps) {
  const isAd = fill.kind === "ad" && fill.ad;
  return (
    <aside
      data-slot-id={slotId}
      data-slot-position={position}
      aria-label={isAd ? "Advertisement" : "Recommended reading"}
      // SPR-10 M3 — explain the placeholder honestly. This is where an ad
      // would sit; when one someday runs, the §9.1 split sends a share to the
      // work that drove this page. No ad runs and no revenue flows today — the
      // house fill below is the real, default state, not a paid ad.
      title={
        isAd
          ? undefined
          : "Where an ad would sit. When ads run, a share would go to the sources behind this page — there's no live ad or revenue yet."
      }
      className="w-full min-h-[44px] flex items-center px-3 py-1.5 border-edge border-rule dark:border-charcoal-1 rounded-md bg-ice-1 dark:bg-charcoal-1"
    >
      {isAd ? (
        <a
          href={fill.ad!.landingUrl}
          target="_blank"
          rel="noopener noreferrer sponsored"
          className="flex items-center gap-3 w-full min-w-0"
        >
          <img
            src={fill.ad!.creativeUrl}
            alt=""
            aria-hidden="true"
            className="h-8 w-8 rounded object-cover flex-shrink-0"
          />
          <span className="min-w-0">
            <span className="font-serif text-sm text-ink dark:text-bright truncate block">
              {fill.ad!.advertiserName}
            </span>
            <span className="text-[10px] font-mono uppercase tracking-wider text-ink-mute dark:text-moonlight">
              Sponsored
            </span>
          </span>
        </a>
      ) : (
        <HouseSlot promo={fill.house ?? null} onOpen={onOpenHouse} />
      )}
    </aside>
  );
}
