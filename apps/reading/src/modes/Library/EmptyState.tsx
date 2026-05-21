// SPR-06 / M2 — Empty-state onboarding for the library.
//
// Triggered when the user has no documents in their library. Shows a
// large "Paste a URL to get started" affordance + 3 suggested URLs
// the user can click to seed their library. The suggestions are
// hand-picked low-friction examples (one essay, one paper, one
// long-form article) — public, free, no paywall, representative of
// the 3 content types the SPR-03 backend handles natively.
//
// Per rigor #2 (fairness, steelman "drop folders/tags entirely"):
// the empty state lives WITHOUT the sidebar — when there's nothing
// to organise, hiding the sidebar lets the paste bar + suggestions
// own the page. The steelman wins for the empty state; folders
// only matter once a user has documents.

import { LemonButton, LemonCard } from "../../components/lemon";

export interface SuggestedUrl {
  label: string;
  url: string;
  kind: "essay" | "paper" | "article";
}

/** Hand-picked suggestions. Stable, public, no-paywall — confirmed
 * importable through the SPR-03 pipeline at sprint start. Each one
 * exercises a different content-type extractor so onboarding gives
 * a tour of what the substrate can do.
 *
 * Caveat: link rot is a real risk for hard-coded URLs over multi-
 * year horizons. If any of these break, swap them with the SAME
 * shape (one HTML essay, one arXiv paper, one general article). */
export const DEFAULT_SUGGESTIONS: SuggestedUrl[] = [
  {
    label: "Paul Graham — Cities and Ambition",
    url: "https://paulgraham.com/cities.html",
    kind: "essay",
  },
  {
    label: "arXiv — Attention Is All You Need",
    url: "https://arxiv.org/abs/1706.03762",
    kind: "paper",
  },
  {
    label: "Stratechery — Aggregation Theory",
    url: "https://stratechery.com/2015/aggregation-theory/",
    kind: "article",
  },
];

export interface EmptyStateProps {
  /** Called when the user clicks one of the suggested URLs. Parent
   * pre-fills the paste bar with the chosen URL (not auto-submit —
   * the user still sees what they're importing). */
  onSuggestionClick?: (url: string) => void;
  suggestions?: SuggestedUrl[];
}

export function EmptyState({ onSuggestionClick, suggestions }: EmptyStateProps) {
  const items = suggestions ?? DEFAULT_SUGGESTIONS;
  return (
    <div
      className="max-w-2xl mx-auto py-12 px-4 text-center space-y-6"
      data-testid="library-empty-state"
    >
      <div>
        <h2 className="font-serif text-[28px] text-ink dark:text-bright mb-2">
          Paste a URL to get started
        </h2>
        <p className="text-[14px] text-shadow-2 dark:text-starlight">
          Antiek is a Kindle for the internet. Paste any article, PDF, or
          arXiv link and we'll keep it here for you to read, annotate,
          and revisit.
        </p>
      </div>

      <LemonCard elevation="z2" colour="card">
        <p className="font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-3 text-left">
          Or try one of these
        </p>
        <ul className="space-y-2">
          {items.map((s) => (
            <li key={s.url} className="flex items-center justify-between gap-3">
              <div className="flex-1 min-w-0 text-left">
                <p className="font-sans text-[13px] text-ink dark:text-bright truncate">
                  {s.label}
                </p>
                <p className="font-mono text-[11px] text-shadow-1 dark:text-moonlight truncate">
                  {s.url}
                </p>
              </div>
              <LemonButton
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => onSuggestionClick?.(s.url)}
                data-testid="library-empty-suggestion"
                data-url={s.url}
              >
                Try this
              </LemonButton>
            </li>
          ))}
        </ul>
      </LemonCard>
    </div>
  );
}

export default EmptyState;
