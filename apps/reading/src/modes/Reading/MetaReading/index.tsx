import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import thinkingArt from "../../../brand/werner/poses/session/werner_thinking_session_v1.png";
import livingTvArt from "../../../brand/werner/poses/session/werner_living_tv_session_v1.webp";
import { LemonButton } from "../../../components/lemon";
import { generateMetaReading, getSavedMetaReading } from "../../../api/books";
import type { BookCitation, MetaReadingResponse } from "../../../api/books";
import ReadAloud from "../../../components/voice/ReadAloud";
import { acceptPromotion, suggestPromotion } from "../../../lib/researchSuggestion";
import {
  emitWernerExperience,
  notifyResearchStarted,
} from "../../../werner";

/**
 * MetaReading — the one-shot, READ-ONLY, page-cited synthesis over the OWNED
 * corpus (Read SPR-08 M4).
 *
 * "Deep-research my owned corpus → make me an asset (X pages / X minutes)."
 * The deliverable is generated + SAVED by `POST /corpus/meta-reading` (a Read
 * asset persisted through the single-writer funnel), then rendered here as a
 * read-only report:
 *   • OWNED-CORPUS-ONLY / internet-agnostic (the backend retrieves only over
 *     owned docs — no open-web path);
 *   • HARD length-box (X pages / X minutes), built to size; a too-long
 *     synthesis is labelled `truncated`; a degenerate size is rejected server-
 *     side with a stated bound (surfaced honestly);
 *   • citations OPEN the SPR-07 in-book reader (an unresolved page is shown as
 *     "open the book", never a fake page);
 *   • narratable via the SPR-14 shared TTS service;
 *   • a SUGGEST-NOT-AUTOSHIP promote-into-Research link (never auto).
 *
 * PROPOSED BOUNDARY (operator decision 2, sign-off pending): the surface
 * carries the "proposed (sign-off pending)" banner. Reversible to a soft corpus
 * scope (docs/decisions/spr-08-meta-reading-boundary.md).
 */

const PROPOSED_BANNER_TEXT =
  "Proposed — sign-off pending. Meta-reading is built to a proposed Research↔Read boundary: a one-shot, read-only synthesis over your OWNED books only (never the open internet). The boundary isn’t ratified yet, and reverts to a softer corpus scope if sign-off is withheld.";

type LengthUnit = "pages" | "minutes";

export default function MetaReading() {
  const navigate = useNavigate();
  // SPR-13 M1 — when an assetId is in the route, this surface RE-OPENS a saved
  // meta-reading asset (read-only) rather than acting as the generator. The
  // saved asset is loaded from the event log via the substrate read-path.
  const { assetId } = useParams<{ assetId?: string }>();
  const [prompt, setPrompt] = useState("");
  const [unit, setUnit] = useState<LengthUnit>("pages");
  const [amount, setAmount] = useState(3);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deliverable, setDeliverable] = useState<MetaReadingResponse | null>(null);
  const [promoted, setPromoted] = useState<string | null>(null);
  const [promoting, setPromoting] = useState(false);

  // Re-open a saved asset by id. Maps the saved shape onto MetaReadingResponse
  // (the read-only render path is identical); the generation-only fields
  // (word_budget / empty / context_chunk_count) are filled with honest
  // re-open values (the asset already exists + is non-empty).
  useEffect(() => {
    if (!assetId) return;
    let cancelled = false;
    setBusy(true);
    setError(null);
    void getSavedMetaReading(assetId)
      .then((saved) => {
        if (cancelled) return;
        setPrompt(saved.prompt);
        setUnit(saved.length_unit);
        setAmount(saved.length_amount);
        setDeliverable({
          asset_id: saved.asset_id,
          report: saved.report,
          citations: saved.citations,
          length_unit: saved.length_unit,
          length_amount: saved.length_amount,
          word_budget: 0,
          truncated: saved.truncated,
          corpus_scope: saved.corpus_scope,
          corpus_document_ids: saved.corpus_document_ids,
          empty: false,
          context_chunk_count: saved.citations.length,
        });
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [assetId]);

  // Open a cited book at a resolved page — seeds the SAME sessionStorage locator
  // usePosition owns, then routes to the reader (no parallel navigation).
  const openCitation = useCallback(
    (c: BookCitation) => {
      if (c.page_resolved && c.page_index !== null && c.page_index >= 0) {
        try {
          window.sessionStorage.setItem(`antiek.read.pos.${c.document_id}`, String(c.page_index));
        } catch {
          /* private mode — opens at the saved page */
        }
      }
      navigate(`/read/${encodeURIComponent(c.document_id)}`);
    },
    [navigate],
  );

  const generate = useCallback(async () => {
    if (!prompt.trim() || busy) return;
    setBusy(true);
    setError(null);
    setDeliverable(null);
    setPromoted(null);
    try {
      const res = await generateMetaReading({
        prompt: prompt.trim(),
        length_unit: unit,
        length_amount: amount,
      });
      setDeliverable(res);
      // Living-TV: a saved meta-reading is a noted craft beat.
      emitWernerExperience("note_saved");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      emitWernerExperience("fail");
    } finally {
      setBusy(false);
    }
  }, [prompt, unit, amount, busy]);

  const suggestion = deliverable && !deliverable.empty
    ? suggestPromotion({
        prompt: deliverable.report ? prompt.trim() : "",
        corpusDocumentIds: deliverable.corpus_document_ids,
      })
    : null;

  const onAcceptPromotion = useCallback(async () => {
    if (!deliverable || promoting) return;
    setPromoting(true);
    try {
      const res = await acceptPromotion({
        assetId: deliverable.asset_id,
        prompt: prompt.trim(),
        documentId: deliverable.corpus_document_ids[0],
      });
      setPromoted(res.investigation_id);
      // Living-TV: promote into Research is a real DR start.
      notifyResearchStarted(res.investigation_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      emitWernerExperience("fail");
    } finally {
      setPromoting(false);
    }
  }, [deliverable, prompt, promoting]);

  return (
    <div className="flex flex-col h-screen">
      <ProposedBanner />
      <main className="flex-1 min-h-0 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-3xl mx-auto px-8 py-8 space-y-5">
          <header className="space-y-2">
            <div className="flex items-center gap-3">
              <img
                src={thinkingArt}
                alt=""
                aria-hidden="true"
                data-testid="meta-reading-werner-brand"
                className="h-12 w-12 shrink-0 object-contain"
              />
              <h1 className="text-2xl font-serif text-ink dark:text-bright">
                Meta-read your corpus
              </h1>
            </div>
            <img
              src={livingTvArt}
              alt=""
              aria-hidden="true"
              data-testid="meta-reading-living-tv-art"
              className="h-16 w-full max-w-md rounded-md object-cover object-center antiek-living-tv-invent"
              loading="lazy"
              decoding="async"
            />
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Deep-read across the books you own and get one cited report — built
              to the length you choose. It reads only your corpus, never the open
              internet.
            </p>
          </header>

          {/* The ask + the HARD length-box. */}
          <section className="space-y-3 rounded-md border border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-2 px-4 py-3">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="What should this reading be about? (e.g. how my books treat free will)"
              rows={3}
              className="w-full bg-ice-0 dark:bg-charcoal-1 text-ink dark:text-bright rounded-md px-3 py-2 text-sm resize-none outline-none border border-rule dark:border-charcoal-1"
            />
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-2 text-[13px] text-ink dark:text-bright">
                Length
                <input
                  type="number"
                  min={1}
                  value={amount}
                  onChange={(e) => setAmount(parseInt(e.target.value, 10) || 0)}
                  aria-label="Length amount"
                  className="w-16 bg-ice-0 dark:bg-charcoal-1 rounded px-2 py-1 text-sm outline-none border border-rule dark:border-charcoal-1"
                />
              </label>
              <div role="radiogroup" aria-label="Length unit" className="flex items-center gap-1">
                {(["pages", "minutes"] as LengthUnit[]).map((u) => (
                  <button
                    key={u}
                    type="button"
                    role="radio"
                    aria-checked={unit === u}
                    onClick={() => setUnit(u)}
                    className={`px-3 py-1 rounded-md text-xs font-mono ${
                      unit === u
                        ? "bg-ink text-white"
                        : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright hover:bg-ice-4"
                    }`}
                  >
                    {u}
                  </button>
                ))}
              </div>
              <LemonButton type="button" variant="primary" size="sm" disabled={busy || !prompt.trim()} onClick={() => void generate()}>
                {busy ? "Reading your corpus…" : "Make the reading"}
              </LemonButton>
            </div>
            <p className="text-[12px] text-shadow-1 dark:text-moonlight">
              Built to about {unit === "pages" ? `${amount} page(s)` : `${amount} minute(s)`} up
              front — a hard budget, not a trim afterward.
            </p>
          </section>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded" role="alert">
              {error}
            </p>
          )}

          {deliverable && deliverable.empty && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">
              Your readable corpus is empty, so there’s nothing to synthesize yet.
              Add some books you can read in full, then try again.
            </p>
          )}

          {deliverable && !deliverable.empty && (
            <section className="space-y-4" data-testid="meta-reading-deliverable">
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-lg font-serif text-ink dark:text-bright">Your reading</h2>
                {/* TTS via the SPR-14 shared service — narrate the report. The
                    minutes box scopes the narration when the asset was sized in
                    minutes (the SPR-14 budget math). */}
                <ReadAloud
                  text={deliverable.report}
                  label="🔊 Narrate"
                  minutes={deliverable.length_unit === "minutes" ? deliverable.length_amount : undefined}
                />
              </div>

              {deliverable.truncated && (
                <p className="text-[13px] text-sun-deep dark:text-sun italic" data-testid="meta-reading-truncated">
                  This synthesis ran longer than the {deliverable.length_amount}-{deliverable.length_unit.replace(/s$/, "")}
                  {" "}budget and was cut to fit — it’s truncated, not the full synthesis.
                </p>
              )}

              {/* READ-ONLY report (not an editable document — operator decision). */}
              <article className="font-serif text-[15px] leading-[1.7] text-ink dark:text-bright whitespace-pre-wrap rounded-md border border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-2 px-4 py-3">
                {deliverable.report}
              </article>

              {/* Page-cited links back into the SPR-07 reader. */}
              {deliverable.citations.length > 0 && (
                <div>
                  <h3 className="text-[13px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight mb-1.5">
                    Cited in your books
                  </h3>
                  <ul className="flex flex-wrap gap-1.5" aria-label="Citations">
                    {deliverable.citations.map((c) => (
                      <li key={c.chunk_id}>
                        <button
                          type="button"
                          onClick={() => openCitation(c)}
                          title={c.snippet}
                          className="rounded bg-aurora/15 text-aurora-deep dark:text-aurora px-2 py-0.5 text-[11px] font-mono hover:bg-aurora/25"
                        >
                          {c.page_resolved && c.page_index !== null
                            ? `open at p.${c.page_index + 1}`
                            : "open the book"}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* SUGGEST-NOT-AUTOSHIP promote into Research. Appears, never
                  auto-fires; the user must click Accept. */}
              {suggestion && !promoted && (
                <div className="rounded-md border border-sun/40 bg-sun/10 px-4 py-3 space-y-2" data-testid="promote-suggestion">
                  <p className="text-[13px] font-serif text-ink dark:text-bright">{suggestion.rationale}</p>
                  <LemonButton type="button" variant="secondary" size="sm" disabled={promoting} onClick={() => void onAcceptPromotion()}>
                    {promoting ? "Promoting…" : "Chase it as a research →"}
                  </LemonButton>
                </div>
              )}
              {promoted && (
                <p className="text-[13px] text-aurora-deep dark:text-aurora" data-testid="promote-done">
                  Promoted to a research.{" "}
                  <button
                    type="button"
                    onClick={() => navigate(`/inv/${encodeURIComponent(promoted)}`)}
                    className="underline"
                  >
                    Open it →
                  </button>
                </p>
              )}
            </section>
          )}
        </div>
      </main>
    </div>
  );
}

/** The "proposed (sign-off pending)" banner — reuses the SPR-06 idiom
 * (AutoNotebook.tsx ProposedBanner): sun palette, honest copy, always renders
 * when the surface is mounted, data-testid for the gate. */
function ProposedBanner() {
  return (
    <div
      role="note"
      aria-label="Proposed feature — sign-off pending"
      data-testid="meta-reading-proposed-banner"
      className="flex items-start gap-2 border-b border-sun/40 bg-sun/15 px-6 py-2.5 text-[13px] leading-relaxed text-ink dark:text-bright"
    >
      <span className="mt-[2px] font-mono text-[10px] font-bold uppercase tracking-wider text-sun-deep dark:text-sun shrink-0">
        proposed
      </span>
      <p className="font-serif">{PROPOSED_BANNER_TEXT}</p>
    </div>
  );
}
