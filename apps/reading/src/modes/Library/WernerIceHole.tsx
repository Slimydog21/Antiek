import {
  lazy,
  Suspense,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

import { LemonButton } from "../../components/lemon";
import { acquireStationInstrumentSuspension } from "../../werner/stationInstrumentSuspension";
import fishingWernerUrl from "../../brand/werner/poses/werner_station_fishing_v1_transparent.png";
import "./WernerIceHole.css";

const LazyWernerIceHoleGame = lazy(() => import("./WernerIceHoleGame"));

export default function WernerIceHole() {
  const [playing, setPlaying] = useState(false);
  const hostRef = useRef<HTMLElement | null>(null);
  const playRef = useRef<HTMLButtonElement | null>(null);
  const restoreFocusRef = useRef(false);

  useLayoutEffect(() => {
    if (!playing) return;
    return acquireStationInstrumentSuspension("library-werner-ice-hole");
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
      ref={hostRef}
      className="werner-ice-hole"
      data-mode={playing ? "playing" : "offer"}
      aria-label="Werner's optional ice fishing game"
      onKeyDownCapture={(event) => {
        if (playing && event.key === "Escape") {
          // The host owns exit before the canvas can treat Escape as game input.
          event.preventDefault();
          event.stopPropagation();
          exit();
        }
      }}
    >
      <img
        className="werner-ice-hole__werner"
        src={fishingWernerUrl}
        alt=""
        aria-hidden="true"
      />
      <div className="werner-ice-hole__copy">
        <p className="werner-ice-hole__eyebrow">Werner's corner</p>
        <h2>Visit the ice hole</h2>
        <p>
          Catch fish, dodge the boot. Optional play—the Library stays exactly
          where you left it.
        </p>
      </div>
      {!playing ? (
        <LemonButton
          ref={playRef}
          size="sm"
          variant="primary"
          onClick={() => setPlaying(true)}
        >
          Play Ice Fishing
        </LemonButton>
      ) : (
        <div className="werner-ice-hole__game">
          <div className="werner-ice-hole__game-head">
            <p>Pointer aims · click/↓ casts · ↑/W reels</p>
            <LemonButton size="sm" variant="secondary" onClick={exit}>
              Exit game
            </LemonButton>
          </div>
          <div className="werner-ice-hole__canvas-shell">
            <Suspense
              fallback={
                <p className="werner-ice-hole__loading">
                  Opening the ice hole…
                </p>
              }
            >
              <LazyWernerIceHoleGame />
            </Suspense>
          </div>
        </div>
      )}
    </aside>
  );
}
