import {
  lazy,
  Suspense,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import { LemonButton } from "../../components/lemon";
import Werner from "../../brand/Werner";
import { acquireStationInstrumentSuspension } from "../../werner/stationInstrumentSuspension";

const LazyFjordSkipGame = lazy(() => import("./FjordSkipGame"));

/**
 * Brainstorm true-empty-state host for Fjord Skip.
 *
 * Shows a compact offer card only when Brainstorm has zero parked questions
 * and no selected question. Lazy-loads the cartridge and backdrop after the
 * operator presses Play. Escape or button exit restores focus to the Play
 * button and releases station-instrument suspension.
 */
export default function FjordSkipHost() {
  const [playing, setPlaying] = useState(false);
  const playRef = useRef<HTMLButtonElement | null>(null);
  const restoreFocusRef = useRef(false);

  useLayoutEffect(() => {
    if (!playing) return;
    return acquireStationInstrumentSuspension("brainstorm-fjord-skip");
  }, [playing]);

  useEffect(() => {
    if (playing || !restoreFocusRef.current) return;
    restoreFocusRef.current = false;
    playRef.current?.focus();
  }, [playing]);

  const exit = () => {
    restoreFocusRef.current = true;
    setPlaying(false);
  };

  return (
    <aside
      className="fjord-skip-host"
      data-mode={playing ? "playing" : "offer"}
      aria-label="Fjord Skip — an optional thinking break"
      onKeyDownCapture={(event) => {
        if (playing && event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          exit();
        }
      }}
    >
      {!playing ? (
        <div className="fjord-skip-host__offer flex max-w-md items-center gap-4 rounded-xl border border-rule bg-ice-1 p-4 shadow-sm dark:border-charcoal-1 dark:bg-space-2">
          <Werner
            mood="empty"
            size={88}
            label="Werner by the fjord"
            className="shrink-0"
          />
          <div className="space-y-2">
            <p className="fjord-skip-host__eyebrow text-xs uppercase tracking-wide text-shadow-1 dark:text-moonlight">
              Thinking break
            </p>
            <h2 className="text-lg font-serif text-ink dark:text-bright">
              Fjord Skip
            </h2>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Skip a pebble across the fjord. Optional play — a thinking break,
              nothing more.
            </p>
            <LemonButton
              ref={playRef}
              size="sm"
              variant="primary"
              onClick={() => setPlaying(true)}
            >
              Play Fjord Skip
            </LemonButton>
          </div>
        </div>
      ) : (
        <div className="fjord-skip-host__game">
          <div className="fjord-skip-host__game-head flex items-center gap-2 mb-2">
            <p className="text-xs text-shadow-1 dark:text-moonlight">
              ← → aim · press and release Space · Enter starts/retries
            </p>
            <LemonButton size="sm" variant="secondary" onClick={exit}>
              Exit game
            </LemonButton>
          </div>
          <div className="fjord-skip-host__canvas-shell">
            <Suspense
              fallback={
                <p className="text-sm text-shadow-1 dark:text-moonlight p-4">
                  Opening the fjord…
                </p>
              }
            >
              <LazyFjordSkipGame />
            </Suspense>
          </div>
        </div>
      )}
    </aside>
  );
}
