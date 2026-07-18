import { ReactNode } from "react";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * AdSlot — Sprint 23-24 + 25+ page-border banner.
 *
 * Per master-spec §9.4 lead-gen ads + §5.5 voice-and-style discipline:
 * the ad slot is suppressed when the surrounding context fails the
 * voice-discipline test. The suppression hook is a caller-provided
 * predicate; in tests / Storybook a static `false` makes the slot
 * always render, while production wires the §5.5 voice rubric.
 *
 * Two slot patterns:
 *   - "page-border" — bottom-of-page banner (default; Sprint 23-24)
 *   - "inline-sponsor" — between top-level synthesis sections
 *     (Sprint 25+; §5.5 voice test is more stringent for inline)
 *
 * The component does NOT enforce voice discipline itself — that's
 * the caller's contract. If `shouldSuppress` is true, the slot
 * silently renders nothing and reports the suppression upstream
 * via `onSuppressed`.
 */

export interface AdItem {
  campaign_id: string;
  advertiser_name: string;
  creative_headline: string;
  creative_url: string;
  sector: string;
  intent: string;
}

export type SlotPattern = "page-border" | "inline-sponsor";

export interface AdSlotProps {
  ad: AdItem | null;
  pattern?: SlotPattern;
  shouldSuppress?: boolean;
  onImpression?: (campaignId: string) => void;
  onSuppressed?: (campaignId: string, reason: string) => void;
  onClick?: (campaignId: string) => void;
  voiceContext?: string;
}

export default function AdSlot({
  ad,
  pattern = "page-border",
  shouldSuppress = false,
  onImpression,
  onSuppressed,
  onClick,
  voiceContext,
}: AdSlotProps): ReactNode {
  if (!ad) {
    return null;
  }

  if (shouldSuppress) {
    if (onSuppressed) {
      onSuppressed(
        ad.campaign_id,
        voiceContext
          ? `§5.5 voice-discipline suppression in context: ${voiceContext}`
          : "§5.5 voice-discipline suppression",
      );
    }
    return null;
  }

  if (onImpression) {
    // Fire-and-forget impression tracking. The anti-gaming layer
    // (substrate/anti_gaming/view_fraud.py) scores this on the
    // server side.
    onImpression(ad.campaign_id);
  }

  if (pattern === "inline-sponsor") {
    return (
      <aside
        role="complementary"
        aria-label={`Sponsored: ${ad.advertiser_name}`}
        className="my-6 border border-rule dark:border-charcoal-1 rounded-md px-4 py-3 bg-ice-1 dark:bg-charcoal-2"
      >
        <div className="flex items-center justify-between">
          <div className="flex flex-col">
            <span className="text-[10px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
              Sponsored · {ad.sector}
            </span>
            <a
              href={ad.creative_url}
              target="_blank"
              rel="noreferrer noopener sponsored"
              onClick={() => { emitWernerExperience("highlight"); onClick?.(ad.campaign_id); }}
              className="text-sm font-serif text-ink dark:text-bright hover:text-ink dark:text-bright underline-offset-2 hover:underline"
            >
              {ad.creative_headline}
            </a>
          </div>
          <span className="text-[10px] font-mono text-ink-mute dark:text-moonlight">
            {ad.advertiser_name}
          </span>
        </div>
      </aside>
    );
  }

  // page-border default
  return (
    <aside
      role="complementary"
      aria-label={`Sponsored: ${ad.advertiser_name}`}
      className="border-t border-rule dark:border-charcoal-1 mt-8 pt-3 pb-2"
    >
      <div className="flex items-center justify-between text-sm">
        <span className="text-[10px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Sponsored · {ad.sector} · {ad.intent}
        </span>
        <a
          href={ad.creative_url}
          target="_blank"
          rel="noreferrer noopener sponsored"
          onClick={() => { emitWernerExperience("highlight"); onClick?.(ad.campaign_id); }}
          className="text-ink dark:text-bright hover:text-ink dark:text-bright underline-offset-2 hover:underline"
        >
          {ad.creative_headline}
        </a>
        <span className="text-[10px] font-mono text-ink-mute dark:text-moonlight">
          {ad.advertiser_name}
        </span>
      </div>
    </aside>
  );
}
