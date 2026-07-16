/**
 * Twin notes panel — insights + open questions companion for an asset.
 *
 * Read-only advisory surface. Auto-generation is merge-gated; demo twin is
 * shown when no live twin is provided so the operator can live in the UX now.
 *
 * Optional autoLoad hits GET /twins/:parentAssetId (see fetchTwin.ts). Live
 * success replaces demo and emits a highlight reaction for the living mascot.
 */

import { useEffect, useState } from "react";

import thinkingArt from "../../../brand/werner/poses/session/werner_thinking_session_v1.png";
// Float-merge invent — recursive note-taker + multi-agent merge product door.
import livingTvArt from "../../../brand/werner/poses/session/werner_float_research_merge_session_v1.webp";
import { emitWernerExperience } from "../../../werner/reactionBus";
import { fetchTwinForAsset } from "./fetchTwin";
import type { TwinDocument } from "./twinDocument";
import { demoTwinForAsset } from "./twinDocument";

export type TwinNotesPanelProps = {
  parentAssetId: string;
  /** Live twin when available; otherwise a clearly labeled demo fixture. */
  twin?: TwinDocument | null;
  /** When true and twin is null, show demo. Default true for offline UX. */
  allowDemo?: boolean;
  /**
   * When true, fetch GET /twins/:parentAssetId on mount / parent change.
   * Prop twin still wins when provided. Failures stay silent (demo/empty).
   */
  autoLoad?: boolean;
};

export function TwinNotesPanel({
  parentAssetId,
  twin: twinProp,
  allowDemo = true,
  autoLoad = false,
}: TwinNotesPanelProps) {
  const [liveTwin, setLiveTwin] = useState<TwinDocument | null>(null);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "live" | "miss">(
    "idle",
  );

  useEffect(() => {
    if (!autoLoad || twinProp) return;
    let cancelled = false;
    setLoadState("loading");
    void fetchTwinForAsset(parentAssetId).then((result) => {
      if (cancelled) return;
      if (result.ok) {
        setLiveTwin(result.twin);
        setLoadState("live");
        // Twin insights arrived — curious glance, same ambient as highlight.
        emitWernerExperience("highlight");
      } else {
        setLiveTwin(null);
        setLoadState("miss");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [autoLoad, parentAssetId, twinProp]);

  const twin = twinProp ?? liveTwin;
  const doc = twin ?? (allowDemo ? demoTwinForAsset(parentAssetId) : null);
  const isDemo = !twin && allowDemo && !!doc;
  const isLive = !!twin && !twinProp ? loadState === "live" : !!twinProp;

  if (!doc) {
    return (
      <aside
        data-testid="twin-notes-panel-empty"
        data-load-state={loadState}
        className="rounded border border-rule p-3 text-[12px] text-shadow-1 dark:border-charcoal-1 dark:text-moonlight"
      >
        {loadState === "loading"
          ? `Loading twin for ${parentAssetId}…`
          : `No twin yet for ${parentAssetId}. Auto-generation is merge-gated.`}
      </aside>
    );
  }

  return (
    <aside
      data-testid="twin-notes-panel"
      data-twin-status={doc.status}
      data-is-demo={isDemo ? "true" : "false"}
      data-is-live={isLive ? "true" : "false"}
      data-load-state={loadState}
      className="flex max-h-[50vh] flex-col overflow-hidden rounded-lg border border-rule bg-ice-1/95 shadow-md dark:border-charcoal-1 dark:bg-charcoal-2/95"
      aria-label="Twin notes"
    >
      <header className="space-y-2 border-b border-rule px-3 py-2 dark:border-charcoal-1">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            {/* Session thinking mark — twin notes are the recursive note-taker
                companion; densify so invent is not inventory-only. */}
            <img
              src={thinkingArt}
              alt=""
              aria-hidden="true"
              data-testid="twin-notes-werner-brand"
              className="h-7 w-7 shrink-0 object-contain"
            />
            <div className="truncate font-mono text-[10px] uppercase tracking-wide text-shadow-1 dark:text-moonlight">
              Twin notes · {doc.authority}
              {isDemo ? " · demo fixture" : isLive ? " · live" : ""}
            </div>
          </div>
          <div className="shrink-0 font-mono text-[10px] text-shadow-1 dark:text-moonlight">
            isTwin={String(doc.isTwin)} · {doc.status}
          </div>
        </div>
        {/* Living-TV invent strip — recursive note-taker is a product door. */}
        <img
          src={livingTvArt}
          alt=""
          aria-hidden="true"
          data-testid="twin-notes-living-tv-art"
          className="h-10 w-full max-w-xs rounded object-cover object-center"
          loading="lazy"
          decoding="async"
        />
      </header>
      <div className="min-h-0 flex-1 overflow-auto p-3 space-y-3">
        <section>
          <h3 className="mb-1 font-mono text-[10px] uppercase text-shadow-1 dark:text-moonlight">
            Insights
          </h3>
          <ul data-testid="twin-notes-insights" className="space-y-1.5">
            {doc.insights.map((i) => (
              <li
                key={i.id}
                className="font-serif text-[12.5px] leading-relaxed text-ink dark:text-bright"
              >
                {i.text}
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h3 className="mb-1 font-mono text-[10px] uppercase text-shadow-1 dark:text-moonlight">
            Questions
          </h3>
          <ul data-testid="twin-notes-questions" className="space-y-1.5">
            {doc.questions.map((q) => (
              <li
                key={q.id}
                className="font-serif text-[12.5px] leading-relaxed text-ink dark:text-bright"
              >
                <span className="font-mono text-[10px] uppercase text-sun">
                  {q.open ? "open" : "closed"}
                </span>{" "}
                {q.text}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </aside>
  );
}

export default TwinNotesPanel;
