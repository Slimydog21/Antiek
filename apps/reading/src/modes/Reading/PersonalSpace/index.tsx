import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import thinkingArt from "../../../brand/werner/poses/session/werner_thinking_session_v1.png";
import livingTvArt from "../../../brand/werner/poses/session/werner_living_tv_session_v1.webp";
import { LemonButton, LemonTag } from "../../../components/lemon";
import {
  getFileSuggestion,
  listPersonalSpace,
  listPersonalSpaceCategories,
} from "../../../api/books";
import type {
  AssetCategory,
  PersonalAsset,
  ProjectMatch,
} from "../../../api/books";
import { acceptFiling, suggestFiling } from "../../../lib/researchSuggestion";
import { emitWernerExperience } from "../../../werner/reactionBus";

/**
 * PersonalSpace — the reader's "personal bed of information that labels itself"
 * (Read SPR-13). Their CREATED deliverables (SPR-08 meta-readings) + saved reads
 * (SPR-07 source.read), grouped into SYSTEM-named categories, each offering a
 * suggest-not-autoship "file into a research project" affordance.
 *
 * REUSES the DocumentsIndex PATTERN (apiFetch-driven list + Lemon primitives) —
 * NOT a fork of its store, NOT bolted onto the `shared` operator surface (which
 * is acquisition/governance tooling). This is a READ-workflow personal surface
 * backed by the substrate read-path (the /meta-readings endpoints reconstruct
 * from the event log; there is NO new document store, NO localStorage of
 * substrate truth).
 *
 *   M1 — the list (created deliverables + saved reads), each opening back into
 *        the reader / meta-doc view; an empty state guides.
 *   M2 — categories EMERGE from clustering (system-named); the surface shows
 *        the honest "recency" fallback label when the corpus is too small.
 *   M3 — a per-asset continuous suggestion naming the matched project; accept
 *        files it (via the funnel), decline leaves it, NEVER auto-ships.
 *   M4 — ``metaDocsOnly`` filters to the created deliverables (the meta-docs
 *        tab), visually distinguished from source-book reads.
 */

interface Props {
  /** M4 — the meta-docs tab: filter to created deliverables only. */
  metaDocsOnly?: boolean;
}

export default function PersonalSpace({ metaDocsOnly = false }: Props) {
  const navigate = useNavigate();
  const [assets, setAssets] = useState<PersonalAsset[]>([]);
  const [categories, setCategories] = useState<AssetCategory[]>([]);
  const [ordering, setOrdering] = useState<"theme" | "recency">("recency");
  const [stabilityBound, setStabilityBound] = useState<number>(4);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [space, cats] = await Promise.all([
        listPersonalSpace(),
        listPersonalSpaceCategories(),
      ]);
      setAssets(space.assets);
      setCategories(cats.categories);
      setOrdering(cats.ordering);
      setStabilityBound(cats.stability_bound);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  // The visible asset set (M4 filter applied). Source-book reads drop out of
  // the meta-docs tab; created deliverables stay.
  const visibleAssets = useMemo(
    () => (metaDocsOnly ? assets.filter((a) => a.kind === "meta_reading") : assets),
    [assets, metaDocsOnly],
  );
  const visibleIds = useMemo(
    () => new Set(visibleAssets.map((a) => a.asset_id)),
    [visibleAssets],
  );
  const byId = useMemo(
    () => new Map(visibleAssets.map((a) => [a.asset_id, a])),
    [visibleAssets],
  );

  // Categories restricted to the visible set; a category that becomes empty
  // under the M4 filter is dropped (never an empty heading).
  const visibleCategories = useMemo(() => {
    if (ordering === "recency") {
      // Honest single bucket in recency order — no theme labels claimed.
      return [
        {
          category_id: "recency",
          label: "Recently read & created",
          asset_ids: visibleAssets.map((a) => a.asset_id),
          ordering: "recency" as const,
        },
      ].filter((c) => c.asset_ids.length > 0);
    }
    return categories
      .map((c) => ({
        ...c,
        asset_ids: c.asset_ids.filter((id) => visibleIds.has(id)),
      }))
      .filter((c) => c.asset_ids.length > 0);
  }, [categories, ordering, visibleAssets, visibleIds]);

  const openAsset = useCallback(
    (a: PersonalAsset) => navigate(a.open_route),
    [navigate],
  );

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-3xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <div className="flex items-center gap-3">
              <img
                src={thinkingArt}
                alt=""
                aria-hidden="true"
                data-testid="personal-space-werner-brand"
                className="h-12 w-12 shrink-0 object-contain"
              />
              <h1 className="text-2xl font-serif text-ink dark:text-bright">
                {metaDocsOnly ? "Meta-docs" : "Your readings"}
              </h1>
            </div>
            <img
              src={livingTvArt}
              alt=""
              aria-hidden="true"
              data-testid="personal-space-living-tv-art"
              className="h-16 w-full max-w-md rounded-md object-cover object-center"
              loading="lazy"
              decoding="async"
            />
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              {metaDocsOnly
                ? "The readings you’ve created from your books — distinct from the source books themselves."
                : "A personal bed of what you’ve read and made — your created readings and the books you’ve read. It organizes itself."}
            </p>
            {/* M2 honesty: SAY which ordering is active rather than dress
                recency up as themes. */}
            {!loading && visibleAssets.length > 0 && (
              <p
                className="text-[12px] font-mono text-shadow-2 dark:text-moonlight"
                data-testid="personal-space-ordering"
              >
                {ordering === "theme"
                  ? "Organized into categories the system found in what you’ve read."
                  : `Sorted by recency — categories kick in once you have ${stabilityBound}+ readings.`}
              </p>
            )}
          </header>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded" role="alert">
              {error}
            </p>
          )}

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
          )}

          {/* M1 empty state — guides the user (rigor #3 a: no crash, no phantom). */}
          {!loading && !error && visibleAssets.length === 0 && (
            <div
              className="rounded-md border border-rule dark:border-charcoal-1 px-5 py-8 text-center space-y-2"
              data-testid="personal-space-empty"
            >
              <p className="text-sm font-serif text-ink dark:text-bright">
                {metaDocsOnly
                  ? "You haven’t made any readings yet."
                  : "Your reading space is empty."}
              </p>
              <p className="text-[13px] text-shadow-1 dark:text-moonlight">
                Read a book in your{" "}
                <button type="button" className="underline" onClick={() => { emitWernerExperience("highlight"); navigate("/library"); }}>
                  library
                </button>
                , or{" "}
                <button type="button" className="underline" onClick={() => { emitWernerExperience("highlight"); navigate("/read/meta-reading"); }}>
                  make a reading
                </button>{" "}
                across your corpus — they’ll collect here and organize themselves.
              </p>
            </div>
          )}

          {!loading &&
            visibleCategories.map((cat) => (
              <section key={cat.category_id} className="space-y-2" data-testid="personal-space-category">
                <div className="flex items-center gap-2">
                  <h2 className="text-[13px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
                    {cat.label}
                  </h2>
                  {cat.ordering === "theme" && (
                    <span className="text-[10px] font-mono text-aurora-deep dark:text-aurora">
                      auto
                    </span>
                  )}
                </div>
                <ul className="space-y-2">
                  {cat.asset_ids.map((id) => {
                    const a = byId.get(id);
                    if (!a) return null;
                    return (
                      <li key={id}>
                        <AssetRow asset={a} onOpen={openAsset} />
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
        </div>
      </main>
    </div>
  );
}

/** One asset row — opens into the reader/meta-doc view + carries the
 * suggest-not-autoship "file into a project" affordance. */
function AssetRow({
  asset,
  onOpen,
}: {
  asset: PersonalAsset;
  onOpen: (a: PersonalAsset) => void;
}) {
  const [matches, setMatches] = useState<ProjectMatch[] | null>(null);
  const [filing, setFiling] = useState(false);
  const [filedInto, setFiledInto] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);

  // The doc this asset is about — the first owned doc, the match subject.
  const subjectDocId = asset.document_ids[0];

  // Fetch the suggestion lazily once per row (a READ, never a mutation — the
  // backend match selector only ranks). No suggestion fetched ⇒ none shown.
  useEffect(() => {
    let cancelled = false;
    if (!subjectDocId) return;
    void getFileSuggestion(subjectDocId)
      .then((r) => {
        if (!cancelled) setMatches(r.matches);
      })
      .catch(() => {
        if (!cancelled) setMatches([]);
      });
    return () => {
      cancelled = true;
    };
  }, [subjectDocId]);

  // PURE: shape the suggestion. No mutation here — the accept handler is the
  // only mutator, and it fires on an explicit click (never on render/effect).
  const suggestion = matches ? suggestFiling({ matches }) : null;

  const onAccept = useCallback(
    async (m: ProjectMatch) => {
      if (!subjectDocId || filing) return;
      setFiling(true);
      try {
        await acceptFiling({
          documentId: subjectDocId,
          investigationId: m.investigation_id,
          matchScore: m.score,
          question: m.question,
        });
        setFiledInto(m.question);
      } finally {
        setFiling(false);
      }
    },
    [subjectDocId, filing],
  );

  return (
    <div className="rounded-md border border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-2 px-4 py-3 space-y-2">
      <button
        type="button"
        onClick={() => onOpen(asset)}
        className="block w-full text-left"
        data-testid="personal-asset-open"
      >
        <div className="flex items-center justify-between gap-3">
          <span className="font-serif text-ink dark:text-bright truncate">{asset.title}</span>
          {/* M4 — the visible created-asset vs source-book distinction. */}
          <LemonTag colour={asset.kind === "meta_reading" ? "aurora" : "muted"}>
            {asset.kind === "meta_reading" ? "reading" : "book"}
          </LemonTag>
        </div>
      </button>

      {/* M3 — the continuous suggestion: appears, never auto-fires; accept files
          into the ONE chosen project, decline (dismiss) leaves it. */}
      {filedInto && (
        <p className="text-[12px] text-aurora-deep dark:text-aurora" data-testid="personal-asset-filed">
          Filed into “{filedInto}.”
        </p>
      )}
      {!filedInto && !dismissed && suggestion && (
        <div
          className="rounded border border-sun/40 bg-sun/10 px-3 py-2 space-y-2"
          data-testid="personal-asset-suggestion"
        >
          <p className="text-[12px] text-ink dark:text-bright">{suggestion.rationale}</p>
          <div className="flex flex-wrap items-center gap-1.5">
            {suggestion.candidates.map((m) => (
              <LemonButton
                key={m.investigation_id}
                type="button"
                variant="secondary"
                size="sm"
                disabled={filing}
                onClick={() => { emitWernerExperience("note_saved"); void onAccept(m); }}
              >
                {filing ? "Filing…" : `File into “${truncate(m.question)}”`}
              </LemonButton>
            ))}
            <button
              type="button"
              onClick={() => setDismissed(true)}
              className="text-[11px] font-mono text-shadow-1 dark:text-moonlight underline"
              data-testid="personal-asset-decline"
            >
              not now
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function truncate(s: string, max = 40): string {
  return s.length <= max ? s : s.slice(0, max - 1) + "…";
}
