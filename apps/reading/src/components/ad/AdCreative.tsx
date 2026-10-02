// The slot's creative — a matched advertiser fill or the house promo (SPR-07 M5).
//
// House fill is the DEFAULT, fully-rendered path (rigor #1): when no advertiser
// matched, we promote a genuinely servable book (HousePromo), or a neutral
// house card when there is nothing to promote — never blank/filler. §9.0: a
// creative carries promo display (title/author/headline), never gated body text.
//
// One row: a label that always says what this is ("Sponsored", or
// "Sponsored · house" for the house's own promo), then one link that
// truncates with an ellipsis instead of clipping mid-word.

import type { SlotFill } from "./adFillClient";

const link = "min-w-0 truncate font-serif text-sm text-1 underline-offset-2 hover:underline";

export function AdCreative({ fill }: { fill: SlotFill }) {
  const ad = fill.kind === "ad" ? fill.ad : null;
  const promo = fill.house ?? null;
  return (
    <div className="h-full flex items-center gap-3 px-4 overflow-hidden">
      <span className="shrink-0 font-mono text-xxs font-semibold uppercase tracking-[0.08em] text-3">
        {ad ? "Sponsored" : "Sponsored · house"}
      </span>
      {ad ? (
        // sponsored rel per the existing AdSlot convention; the slot never
        // steals focus order (M6) — it lives after the working region.
        <a href={ad.landing_url} target="_blank" rel="noreferrer noopener sponsored" className={link}>
          {ad.advertiser_display_name}
        </a>
      ) : promo?.title ? (
        <a href={promo.promoted_document_id ? `/read/${promo.promoted_document_id}` : "/library"} className={link}>
          <span className="italic">{promo.title}</span>
          {promo.author ? <span className="text-2">{` · ${promo.author}`}</span> : null}
        </a>
      ) : (
        <a href="/library" className={link}>
          Explore the Antiek library
        </a>
      )}
    </div>
  );
}

export default AdCreative;
