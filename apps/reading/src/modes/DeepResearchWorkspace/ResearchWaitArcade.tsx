import {
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from "react";

import LemonButton from "../../components/lemon/LemonButton";
import {
  RESEARCH_WAIT_ARCADE_OFFER_AFTER_MS,
  deriveResearchWaitArcadeMode,
} from "./researchWaitArcadePolicy";
import "./ResearchWaitArcade.css";

const LazyResearchWaitArcadeGame = lazy(
  () => import("./ResearchWaitArcadeGame"),
);

export interface ResearchWaitArcadeProps {
  episodeId: string;
  activeResearchCount: number;
  offerAfterMs?: number;
  returnFocusRef: RefObject<HTMLElement | null>;
}

export default function ResearchWaitArcade({
  episodeId,
  activeResearchCount,
  offerAfterMs = RESEARCH_WAIT_ARCADE_OFFER_AFTER_MS,
  returnFocusRef,
}: ResearchWaitArcadeProps) {
  const [offerReady, setOfferReady] = useState(false);
  const [optedIn, setOptedIn] = useState(false);
  const hostRef = useRef<HTMLElement | null>(null);
  const playRef = useRef<HTMLButtonElement | null>(null);
  const focusedInsideRef = useRef(false);
  const restoreOfferFocusRef = useRef(false);

  useEffect(() => {
    setOfferReady(false);
    setOptedIn(false);
    const timeout = window.setTimeout(
      () => setOfferReady(true),
      Math.max(0, offerAfterMs),
    );
    return () => window.clearTimeout(timeout);
  }, [episodeId, offerAfterMs]);

  useEffect(
    () => () => {
      const active = document.activeElement;
      if (
        focusedInsideRef.current ||
        (active instanceof Node && hostRef.current?.contains(active))
      ) {
        returnFocusRef.current?.focus();
      }
    },
    [returnFocusRef],
  );

  const mode = deriveResearchWaitArcadeMode({
    featureEnabled: true,
    hasAuthoritativeSnapshot: true,
    researchCount: activeResearchCount,
    allTerminal: false,
    reducedMotion: false,
    offerReady,
    optedIn,
  });

  useEffect(() => {
    if (mode !== "offer" || !restoreOfferFocusRef.current) return;
    restoreOfferFocusRef.current = false;
    playRef.current?.focus();
  }, [mode]);

  const exitGame = () => {
    focusedInsideRef.current = true;
    restoreOfferFocusRef.current = true;
    setOptedIn(false);
  };

  if (mode === "waiting" || mode === "hidden") return null;

  return (
    <aside
      ref={hostRef}
      className="research-wait-arcade"
      data-testid="research-wait-arcade"
      data-mode={mode}
      data-episode-id={episodeId}
      aria-label="Optional research wait game"
      onFocusCapture={() => {
        focusedInsideRef.current = true;
      }}
      onBlurCapture={(event) => {
        const next = event.relatedTarget;
        if (!(next instanceof Node) || !event.currentTarget.contains(next)) {
          focusedInsideRef.current = false;
        }
      }}
      onKeyDownCapture={(event) => {
        if (mode === "playing" && event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          exitGame();
        }
      }}
    >
      <div className="research-wait-arcade__rail">
        <span className="research-wait-arcade__pulse" aria-hidden="true" />
        <span className="research-wait-arcade__trace" aria-hidden="true" />
        <span className="research-wait-arcade__rail-status font-mono text-[11px] text-shadow-1 dark:text-moonlight">
          {activeResearchCount}{" "}
          {activeResearchCount === 1 ? "research" : "researches"} still running
        </span>
      </div>

      {mode === "offer" && (
        <div className="research-wait-arcade__drawer">
          <div className="min-w-0">
            <p className="font-serif text-sm font-semibold text-ink dark:text-bright">
              Paperclip Zombies
            </p>
            <p className="mt-1 text-xs text-shadow-1 dark:text-moonlight">
              Optional. Defend the archive while research keeps running.
            </p>
          </div>
          <LemonButton
            ref={playRef}
            size="sm"
            variant="primary"
            onClick={() => setOptedIn(true)}
          >
            Play while waiting
          </LemonButton>
        </div>
      )}

      {mode === "playing" && (
        <div className="research-wait-arcade__drawer research-wait-arcade__game">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="font-serif text-sm font-semibold text-ink dark:text-bright">
                Paperclip Zombies
              </p>
              <p className="text-xs text-shadow-1 dark:text-moonlight">
                Research stays live above the game.
              </p>
            </div>
            <LemonButton size="sm" variant="secondary" onClick={exitGame}>
              Exit game
            </LemonButton>
          </div>
          <div className="research-wait-arcade__canvas-shell">
            <Suspense fallback={null}>
              <LazyResearchWaitArcadeGame />
            </Suspense>
          </div>
        </div>
      )}
    </aside>
  );
}
