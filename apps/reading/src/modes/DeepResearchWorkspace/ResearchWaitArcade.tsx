import {
  Component,
  lazy,
  Suspense,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";

import LemonButton from "../../components/lemon/LemonButton";
import ErrorBanner from "../../components/lemon/ErrorBanner";
import type { ArcadeGameKind } from "../../arcade/cartridgeFactory";
import { ARCADE_CARTRIDGE_META } from "../../arcade/cartridgeMeta";
import { press } from "../../design/motion";
import { usePrefersReducedMotion } from "../../workspace/usePrefersReducedMotion";
import iceFishingArt from "../../brand/mascot/arcade/ice-fishing-station-key-art-v1.webp";
import paperclipArt from "../../brand/mascot/arcade/paperclip-archive-key-art-v1.webp";
import { acquireStationInstrumentSuspension } from "../../mascot/stationInstrumentSuspension";
import {
  RESEARCH_WAIT_ARCADE_OFFER_AFTER_MS,
  deriveResearchWaitArcadeMode,
} from "./researchWaitArcadePolicy";
import "./ResearchWaitArcade.css";

const LazyResearchWaitArcadeGame = lazy(
  () => import("./ResearchWaitArcadeGame"),
);

// Key art is the only per-choice asset; title/description come from
// ARCADE_CARTRIDGE_META so the chooser can never drift from the cartridge.
const ARCADE_CHOICES: ReadonlyArray<{
  id: ArcadeGameKind;
  art: string;
}> = [
  { id: "zombies", art: paperclipArt },
  { id: "ice-fishing", art: iceFishingArt },
];

export interface ResearchWaitArcadeProps {
  episodeId: string;
  activeResearchCount: number;
  offerAfterMs?: number;
  returnFocusRef: RefObject<HTMLElement | null>;
  reducedMotion?: boolean;
}

export default function ResearchWaitArcade({
  episodeId,
  activeResearchCount,
  offerAfterMs = RESEARCH_WAIT_ARCADE_OFFER_AFTER_MS,
  returnFocusRef,
  reducedMotion,
}: ResearchWaitArcadeProps) {
  const systemReducedMotion = usePrefersReducedMotion();
  const effectiveReducedMotion = reducedMotion ?? systemReducedMotion;
  const [offerReady, setOfferReady] = useState(false);
  const [optedIn, setOptedIn] = useState(false);
  const [selectedGame, setSelectedGame] = useState<ArcadeGameKind>("zombies");
  const hostRef = useRef<HTMLElement | null>(null);
  const playRef = useRef<HTMLButtonElement | null>(null);
  const focusedInsideRef = useRef(false);
  const restoreOfferFocusRef = useRef(false);

  useEffect(() => {
    setOfferReady(false);
    setOptedIn(false);
    setSelectedGame("zombies");
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
    offerReady,
    optedIn,
  });

  // The focused canvas becomes the pointer instrument during explicit play.
  // Acquire before paint so the route-derived research lens cannot flash over
  // the game; every state transition and unmount releases this ephemeral lease.
  useLayoutEffect(() => {
    if (mode !== "playing") return;
    return acquireStationInstrumentSuspension(
      `research-wait-arcade:${episodeId}`,
    );
  }, [episodeId, mode]);

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
      data-selected-game={selectedGame}
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
        // Escape has ONE owner: this shell. It intercepts in the capture
        // phase, so the canvas never sees the key and the cartridge's own
        // Escape→exited phase (kept for shell-less hosts) stays dormant.
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
        <span className="research-wait-arcade__rail-status font-mono text-xs text-shadow-1 dark:text-moonlight">
          {activeResearchCount}{" "}
          {activeResearchCount === 1 ? "research" : "researches"} still running
        </span>
      </div>

      {mode === "offer" && (
        <div className="research-wait-arcade__drawer research-wait-arcade__offer">
          <fieldset className="research-wait-arcade__chooser">
            <legend className="font-serif text-sm font-semibold text-ink dark:text-bright">
              Choose a cartridge
            </legend>
            <p className="mt-1 text-xs text-shadow-1 dark:text-moonlight">
              Optional. Your research continues above either game.
            </p>
            <div className="research-wait-arcade__cartridges">
              {ARCADE_CHOICES.map((choice) => {
                const meta = ARCADE_CARTRIDGE_META[choice.id];
                return (
                  <label
                    key={choice.id}
                    className={`research-wait-arcade__cartridge ${press}`}
                    data-selected={
                      selectedGame === choice.id ? "true" : "false"
                    }
                  >
                    <input
                      type="radio"
                      name={`research-wait-cartridge-${episodeId}`}
                      value={choice.id}
                      checked={selectedGame === choice.id}
                      onChange={() => setSelectedGame(choice.id)}
                    />
                    <img
                      src={choice.art}
                      alt=""
                      aria-hidden="true"
                      decoding="async"
                    />
                    <span className="research-wait-arcade__cartridge-copy">
                      <span className="font-serif text-sm font-semibold text-ink dark:text-bright">
                        {meta.title}
                      </span>
                      <span className="text-xs text-shadow-1 dark:text-moonlight">
                        {meta.blurb}
                      </span>
                    </span>
                    <span
                      className="research-wait-arcade__choice-mark"
                      aria-hidden="true"
                    />
                  </label>
                );
              })}
            </div>
          </fieldset>
          <div className="research-wait-arcade__offer-action">
            <LemonButton
              ref={playRef}
              size="sm"
              variant="primary"
              onClick={() => setOptedIn(true)}
            >
              Play while waiting
            </LemonButton>
          </div>
        </div>
      )}

      {mode === "playing" && (
        <div className="research-wait-arcade__drawer research-wait-arcade__game">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="font-serif text-sm font-semibold text-ink dark:text-bright">
                {ARCADE_CARTRIDGE_META[selectedGame].title}
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
            <ArcadeChunkBoundary>
              <Suspense fallback={<GameSkeleton />}>
                <LazyResearchWaitArcadeGame
                  game={selectedGame}
                  reducedMotion={effectiveReducedMotion}
                />
              </Suspense>
            </ArcadeChunkBoundary>
          </div>
        </div>
      )}
    </aside>
  );
}

// Skeleton while the game chunk loads. The block matches the mounted
// canvas's 480×300 (8:5) ratio so the shell does not jump when the game
// lands; the named-step label keeps the wait honest instead of a blank box.
function GameSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading game"
      className="flex aspect-[8/5] w-full items-center justify-center rounded-hog bg-ice-3 dark:bg-space-2"
    >
      <span className="font-mono text-xs uppercase text-shadow-1 dark:text-moonlight">
        Loading game…
      </span>
    </div>
  );
}

// If the lazy chunk fails (offline, deploy skew), the failure is stated
// plainly and the header's Exit game control above still leads back — the
// boundary unmounts with the drawer, so Play again is a real retry.
class ArcadeChunkBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return (
        <ErrorBanner>
          The game failed to load. Your research is still running — Exit game
          above returns to the monitor.
        </ErrorBanner>
      );
    }
    return this.props.children;
  }
}
