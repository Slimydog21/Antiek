// One border creative — a matched advertiser fill or the house promo (SPR-07 M5).
//
// House fill is the DEFAULT, fully-rendered path (rigor #1): when no advertiser
// matched, we promote a genuinely servable book (HousePromo), or a neutral
// house card when there is nothing to promote — never blank/filler. §9.0: a
// creative carries promo display (title/author/headline), never gated body text.

import type { SlotFill } from "./adFillClient";

/** Orientation drives the layout: horizontal rails (top/bottom) lay out in a
 *  row; vertical rails (left/right) stack. */
type Orientation = "horizontal" | "vertical";

const wrapCls =
  "w-full h-full flex items-center gap-3 px-3 py-1 overflow-hidden bg-ice-1 dark:bg-charcoal-2";

function Label({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[10px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight shrink-0">
      {children}
    </span>
  );
}

export function AdCreative({
  fill,
  orientation,
}: {
  fill: SlotFill;
  orientation: Orientation;
}) {
  const stack = orientation === "vertical";
  const cls = stack ? `${wrapCls} flex-col text-center justify-center` : wrapCls;

  if (fill.kind === "ad" && fill.ad) {
    const ad = fill.ad;
    return (
      <div className={cls}>
        <Label>Sponsored</Label>
        <a
          href={ad.landing_url}
          target="_blank"
          // sponsored rel per the existing AdSlot convention; the border never
          // steals focus order (M6) — it lives after the working region.
          rel="noreferrer noopener sponsored"
          className="min-w-0 truncate font-serif text-sm text-ink dark:text-bright underline-offset-2 hover:underline"
        >
          {ad.advertiser_display_name}
        </a>
      </div>
    );
  }

  // House fill — the default. A real servable-book promo when present, else a
  // neutral house card. Both are honest house seconds (0 advertiser revenue).
  const promo = fill.house ?? null;
  return (
    <div className={cls}>
      <Label>From the library</Label>
      {promo?.title ? (
        <a
          href={promo.promoted_document_id ? `/read/${promo.promoted_document_id}` : "/library"}
          className="min-w-0 truncate font-serif text-sm text-ink dark:text-bright underline-offset-2 hover:underline"
        >
          <span className="italic">{promo.title}</span>
          {promo.author ? <span className="text-shadow-1 dark:text-moonlight">{` · ${promo.author}`}</span> : null}
        </a>
      ) : (
        <a
          href="/library"
          className="min-w-0 truncate font-serif text-sm text-ink dark:text-bright underline-offset-2 hover:underline"
        >
          Explore the antiek library
        </a>
      )}
    </div>
  );
}

export default AdCreative;
