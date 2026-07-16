import {
  lazy,
  Suspense,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type RefObject,
  type Ref,
} from "react";

import LemonButton from "../../components/lemon/LemonButton";
import Werner from "../../brand/Werner";
import type { ArcadeGameKind } from "../../arcade/cartridgeFactory";
import iceFishingArt from "../../brand/werner/arcade/ice-fishing-station-key-art-v1.webp";
import paperclipArt from "../../brand/werner/arcade/paperclip-archive-key-art-v1.webp";
import clamCatcherArt from "../../brand/werner/arcade/clam-catcher-station-key-art-v1.webp";
import { acquireStationInstrumentSuspension } from "../../werner/stationInstrumentSuspension";
import {
  RESEARCH_WAIT_ARCADE_OFFER_AFTER_MS,
  deriveResearchWaitArcadeMode,
} from "./researchWaitArcadePolicy";
import "./ResearchWaitArcade.css";
import {
  deriveResearchBroadcasts,
  researchStateBaseline,
  type ResearchBroadcast,
  type ResearchBroadcastSnapshot,
} from "./researchBroadcast";

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
  researches?: readonly ResearchBroadcastSnapshot[];
  allTerminal?: boolean;
  onViewResearch?: (investigationId: string) => void;
}

export default function ResearchWaitArcade({
  episodeId,
  activeResearchCount,
  offerAfterMs = RESEARCH_WAIT_ARCADE_OFFER_AFTER_MS,
  returnFocusRef,
  reducedMotion,
  researches = [],
  allTerminal = false,
  onViewResearch = () => {},
}: ResearchWaitArcadeProps) {
  const systemReducedMotion = useReducedMotionPreference();
  const effectiveReducedMotion = reducedMotion ?? systemReducedMotion;
  const [offerReady, setOfferReady] = useState(false);
  const [optedIn, setOptedIn] = useState(false);
  const [selectedGame, setSelectedGame] = useState<ArcadeGameKind>("zombies");
  const [broadcasts, setBroadcasts] = useState<ResearchBroadcast[]>([]);
  const hostRef = useRef<HTMLElement | null>(null);
  const playRef = useRef<HTMLButtonElement | null>(null);
  const focusedInsideRef = useRef(false);
  const restoreOfferFocusRef = useRef(false);
  const previousResearchRef = useRef(researchStateBaseline(researches));
  const finalActionRef = useRef<HTMLButtonElement | null>(null);

  useLayoutEffect(() => {
    setOfferReady(false);
    setOptedIn(false);
    setSelectedGame("zombies");
    setBroadcasts([]);
    previousResearchRef.current = researchStateBaseline(researches);
    const timeout = window.setTimeout(
      () => setOfferReady(true),
      Math.max(0, offerAfterMs),
    );
    return () => window.clearTimeout(timeout);
  }, [episodeId, offerAfterMs]);

  useLayoutEffect(() => {
    const arrivals = deriveResearchBroadcasts(
      previousResearchRef.current,
      researches,
    );
    previousResearchRef.current = researchStateBaseline(researches);
    if (arrivals.length > 0) {
      setBroadcasts((queued) => [...queued, ...arrivals]);
    }
  }, [researches]);

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

  const policyMode = deriveResearchWaitArcadeMode({
    featureEnabled: true,
    hasAuthoritativeSnapshot: true,
    researchCount: activeResearchCount,
    allTerminal,
    reducedMotion: effectiveReducedMotion,
    offerReady,
    optedIn,
  });
  const mode = allTerminal && optedIn ? "playing" : policyMode;
  const activeBroadcast = broadcasts[0] ?? null;
  const broadcastVisible = mode === "playing" && activeBroadcast !== null;
  const finalBroadcast = allTerminal && broadcasts.length === 1;
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

  useEffect(() => {
    if (!broadcastVisible || !finalBroadcast) return;
    finalActionRef.current?.focus();
  }, [finalBroadcast, broadcastVisible, activeBroadcast?.investigationId]);

  const exitGame = () => {
    focusedInsideRef.current = true;
    restoreOfferFocusRef.current = true;
    setOptedIn(false);
  };

  const viewBroadcastResearch = () => {
    if (!activeBroadcast) return;
    focusedInsideRef.current = false;
    setBroadcasts((queued) => queued.slice(1));
    onViewResearch(activeBroadcast.investigationId);
    setOptedIn(false);
  };

  const continueGame = () => {
    setBroadcasts((queued) => queued.slice(1));
    if (activeResearchCount > 0) {
      window.requestAnimationFrame(() => {
        hostRef.current?.querySelector<HTMLCanvasElement>("canvas")?.focus();
      });
    }
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
                {selectedChoice.title}
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
              <LazyResearchWaitArcadeGame
                game={selectedGame}
                reducedMotion={effectiveReducedMotion}
                sceneArtSrc={selectedChoice.art}
                paused={broadcastVisible}
              />
              {activeBroadcast && (
                <ResearchArrivalBroadcast
                  broadcast={activeBroadcast}
                  remaining={activeResearchCount}
                  final={finalBroadcast}
                  onContinue={continueGame}
                  onView={viewBroadcastResearch}
                  finalActionRef={finalActionRef}
                />
              )}
            </Suspense>
          </div>
        </div>
      )}
    </aside>
  );
}

function ResearchArrivalBroadcast({
  broadcast,
  remaining,
  final,
  onContinue,
  onView,
  finalActionRef,
}: {
  broadcast: ResearchBroadcast;
  remaining: number;
  final: boolean;
  onContinue: () => void;
  onView: () => void;
  finalActionRef: RefObject<HTMLButtonElement | null>;
}) {
  const copy = broadcastCopy(broadcast);
  return (
    <section
      className="research-wait-arcade__broadcast"
      aria-label="Research arrival"
      aria-live="polite"
      data-final={final ? "true" : "false"}
    >
      <Werner
        mood={copy.mood}
        size={88}
        label={`Werner ${copy.wernerLabel}`}
        className="research-wait-arcade__broadcast-werner"
      />
      <div className="research-wait-arcade__broadcast-copy">
        <p className="research-wait-arcade__broadcast-kicker">{copy.kicker}</p>
        <h3>{broadcast.subQuestion}</h3>
        <p>{copy.detail}</p>
        {!final && remaining > 0 && (
          <p className="font-mono text-[11px]">
            {remaining} {remaining === 1 ? "research" : "researches"} still
            running
          </p>
        )}
      </div>
      <div className="research-wait-arcade__broadcast-actions">
        {!final && (
          <LemonButton size="sm" variant="secondary" onClick={onContinue}>
            {remaining > 0 ? "Continue game" : "Next arrival"}
          </LemonButton>
        )}
        <LemonButton
          ref={final ? (finalActionRef as Ref<HTMLButtonElement>) : undefined}
          size="sm"
          variant="primary"
          onClick={onView}
        >
          {broadcast.kind === "arrived"
            ? final
              ? "View result"
              : "View this result"
            : "View details"}
        </LemonButton>
      </div>
    </section>
  );
}

function broadcastCopy(broadcast: ResearchBroadcast): {
  kicker: string;
  detail: string;
  mood: "celebrate" | "empty";
  wernerLabel: string;
} {
  if (broadcast.kind === "arrived") {
    return {
      kicker: "Research arrived",
      detail: "Werner kept your place in the game.",
      mood: "celebrate",
      wernerLabel: "delivers completed research",
    };
  }
  if (broadcast.kind === "failed") {
    return {
      kicker: "Research needs attention",
      detail: "This line of inquiry ended without a result.",
      mood: "empty",
      wernerLabel: "reports a research failure",
    };
  }
  if (broadcast.kind === "budget_halted") {
    return {
      kicker: "Research paused at the budget ceiling",
      detail: "No additional spend was authorized.",
      mood: "empty",
      wernerLabel: "guards the research budget",
    };
  }
  return {
    kicker: "Research stopped",
    detail: "This line of inquiry ended before completion.",
    mood: "empty",
    wernerLabel: "reports stopped research",
  };
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
