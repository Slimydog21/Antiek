// SPR-11 / M6 — Suggested-themes stub.
//
// Auto-clustering across Tier-2 notebooks is the AI-native answer
// to "what themes should the operator be considering?" — but it
// requires a topic model that doesn't exist yet. The product
// decision (locked in the Wrestle Evolution master spec): hand-
// curation is the cold-start answer; auto-suggest activates when
// (a) Tier-2 notebook count ≥ 10k AND (b) the topic model trained
// on the corpus passes operator review.
//
// At launch we ship a feature-flagged empty section that explains
// the gate honestly. NO lorem-ipsum, no fake suggestions. The
// future engineer who flips the feature flag must see the unlock
// criteria first; services/notebooks/AUTO_SUGGEST.md documents
// the contract the topic-model output will fulfill.
//
// Acceptance gate (sprint HTML M6):
//   - Section visible but empty by default.
//   - Feature-flagged: auto_suggest_themes: false.
//   - Documented stub interface in AUTO_SUGGEST.md.
//   - Unlock criteria documented.

import { useEffect, useState } from "react";

/** Feature flag. Setting this to ``true`` does NOT magically make
 *  suggestions appear — the topic model has to ship first. The
 *  flag is here so the swap is a one-line change when the criteria
 *  in AUTO_SUGGEST.md are met. */
export const AUTO_SUGGEST_THEMES_FLAG = false;

/** Shape future suggestions will take. Mirrors the contract
 *  documented in services/notebooks/AUTO_SUGGEST.md.
 *
 *  The topic-model writer is required to populate THIS shape; the
 *  surface won't render a flag-on row that doesn't match. */
export interface SuggestedTheme {
  cluster_id: string;
  title: string;
  /** Quick rationale shown in the card. */
  rationale: string;
  /** Confidence score in [0, 1] from the topic model. UI uses this
   *  to sort and to grey out low-confidence cards. */
  confidence: number;
  /** Tier-2 block ids the cluster draws from. The "Promote all"
   *  action calls promoteBlocksToTheme with these. */
  source_block_ids: string[];
}

export interface SuggestedThemesProps {
  /** Optional injection so future production code can pass real
   *  cluster data without rewriting this component. Today this is
   *  unused (the flag-off branch ignores it); tomorrow's flag-on
   *  branch reads from it. */
  suggestions?: SuggestedTheme[];
}

export default function SuggestedThemes(
  props: SuggestedThemesProps,
): JSX.Element {
  const [suggestions, setSuggestions] = useState<SuggestedTheme[]>(
    props.suggestions ?? [],
  );

  // The flag-on fetch path lands when the topic model ships. Today
  // it's a no-op so the empty state is stable.
  useEffect(() => {
    if (!AUTO_SUGGEST_THEMES_FLAG) return;
    // future: void fetchSuggestedThemes().then(setSuggestions);
    setSuggestions(props.suggestions ?? []);
  }, [props.suggestions]);

  return (
    <section
      className="mt-10 border-t border-stone-200 pt-6"
      data-testid="suggested-themes"
    >
      <h2 className="text-xs font-mono uppercase tracking-wider text-stone-500 mb-3">
        Auto-suggested themes
      </h2>

      {!AUTO_SUGGEST_THEMES_FLAG ? (
        <div
          className={
            "rounded-md border border-dashed border-stone-300 " +
            "bg-stone-50/60 px-4 py-6 text-center"
          }
          data-testid="suggested-themes-stub"
        >
          <p className="text-sm text-stone-700">
            Auto-suggested themes will appear when your library has
            more notebooks.
          </p>
          <p className="mt-2 text-[11px] font-mono text-stone-500">
            Unlock criteria: Tier-2 notebook count ≥ 10k + topic model
            passes operator review.
          </p>
          <p className="mt-1 text-[11px] font-mono text-stone-500">
            See{" "}
            <code className="bg-stone-100 px-1 rounded">
              services/notebooks/AUTO_SUGGEST.md
            </code>{" "}
            for the contract.
          </p>
        </div>
      ) : suggestions.length === 0 ? (
        <p
          className="text-sm text-stone-500 italic"
          data-testid="suggested-themes-empty-flag-on"
        >
          The topic model is enabled but produced no suggestions yet.
          This can happen on a small corpus — keep curating.
        </p>
      ) : (
        <ul className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {suggestions.map((s) => (
            <li
              key={s.cluster_id}
              className={
                "rounded-md border border-stone-200 bg-white p-3 " +
                "hover:shadow-sm transition-shadow"
              }
              data-testid={`suggested-theme-${s.cluster_id}`}
            >
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-serif text-stone-900">{s.title}</h3>
                <span className="text-[10px] font-mono text-stone-500">
                  conf {s.confidence.toFixed(2)}
                </span>
              </div>
              <p className="mt-1 text-xs text-stone-600">{s.rationale}</p>
              <p className="mt-2 text-[11px] font-mono text-stone-500">
                {s.source_block_ids.length} block
                {s.source_block_ids.length === 1 ? "" : "s"}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
