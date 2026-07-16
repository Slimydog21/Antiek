import {
  lazy,
  Suspense,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type RefObject,
} from "react";

import LemonButton from "../../components/lemon/LemonButton";
import type { ArcadeGameKind } from "../../arcade/cartridgeFactory";
// Session brand key art (alpha-gated) unifies wait-arcade with ArcadeCabinet.
// Igloo ice-arcade invent — CRT TV + cursor-bait ice fishing wait card.
import iceFishingArt from "../../brand/werner/poses/session/werner_igloo_ice_arcade_cursor_session_v1.webp";
import paperclipArt from "../../brand/werner/poses/session/werner_paperclip_zombies_arcade_session_v1.webp";
import clamCatcherArt from "../../brand/werner/poses/session/werner_clam_catcher_cursor_session_v1.webp";
import { acquireStationInstrumentSuspension } from "../../werner/stationInstrumentSuspension";
import {
  RESEARCH_WAIT_ARCADE_OFFER_AFTER_MS,
  deriveResearchWaitArcadeMode,
} from "./researchWaitArcadePolicy";
import "./ResearchWaitArcade.css";

import { emitWernerExperience } from "../../werner/reactionBus";
const LazyResearchWaitArcadeGame = lazy(
  () => import("./ResearchWaitArcadeGame"),
);

const ARCADE_CHOICES: ReadonlyArray<{
  id: ArcadeGameKind;
  title: string;
  description: string;
  art: string;
}> = [
  {
    id: "zombies",
    title: "Paperclip Zombies",
    description: "Defend the archive while research keeps running.",
    art: paperclipArt,
  },
  {
    id: "ice-fishing",
    title: "Ice Fishing",
    description: "Drop the line, catch fish, avoid the boot.",
    art: iceFishingArt,
  },
  {
    id: "clam-catcher",
    title: "Clam Catcher",
    description: "Catch pearl clams. Let the jellyfish drift past.",
    art: clamCatcherArt,
  },
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
  const systemReducedMotion = useReducedMotionPreference();
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
    reducedMotion: effectiveReducedMotion,
    offerReady,
    optedIn,
  });
  const selectedChoice =
    ARCADE_CHOICES.find((choice) => choice.id === selectedGame) ??
    ARCADE_CHOICES[0];

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
        <div className="research-wait-arcade__drawer research-wait-arcade__offer">
          <fieldset className="research-wait-arcade__chooser">
            <legend className="font-serif text-sm font-semibold text-ink dark:text-bright">
              Choose a cartridge
            </legend>
            <p className="mt-1 text-xs text-shadow-1 dark:text-moonlight">
              Optional. Your research continues above either game.
            </p>
            <div className="research-wait-arcade__cartridges">
              {ARCADE_CHOICES.map((choice) => (
                <label
                  key={choice.id}
                  className="research-wait-arcade__cartridge"
                  data-selected={selectedGame === choice.id ? "true" : "false"}
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
                      {choice.title}
                    </span>
                    <span className="text-xs text-shadow-1 dark:text-moonlight">
                      {choice.description}
                    </span>
                  </span>
                  <span
                    className="research-wait-arcade__choice-mark"
                    aria-hidden="true"
                  />
                </label>
              ))}
            </div>
          </fieldset>
          <div className="research-wait-arcade__offer-action">
            <LemonButton
              ref={playRef}
              size="sm"
              variant="primary"
              onClick={() => { emitWernerExperience("highlight"); setOptedIn(true); }}
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
                {selectedChoice.title}
              </p>
              <p className="text-xs text-shadow-1 dark:text-moonlight">
                Research stays live above the game.
              </p>
            </div>
            <LemonButton size="sm" variant="secondary" onClick={() => { emitWernerExperience("note_saved"); exitGame(); }}>
              Exit game
            </LemonButton>
          </div>
          <div className="research-wait-arcade__canvas-shell">
            <Suspense fallback={null}>
              <LazyResearchWaitArcadeGame
                game={selectedGame}
                reducedMotion={effectiveReducedMotion}
                sceneArtSrc={selectedChoice.art}
              />
            </Suspense>
          </div>
        </div>
      )}
    </aside>
  );
}

function useReducedMotionPreference(): boolean {
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return reduced;
}
