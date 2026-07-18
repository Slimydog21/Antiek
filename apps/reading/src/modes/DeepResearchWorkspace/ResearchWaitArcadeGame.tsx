import { useEffect, useMemo, useRef } from "react";

import { ArcadeMount } from "../../arcade/engine/ArcadeMount";
import {
  createArcadeCartridge,
  type ArcadeGameKind,
} from "../../arcade/cartridgeFactory";
// Host-layer living-TV inject (same path as ArcadeCabinet / LoadingGameHost).
// Arcade core stays free of reactionBus; beats still reach antiek:werner-experience.
import { emitLivingTvHostBeat } from "../../arcade/host/livingTvHostEmit";

/** Loaded only after explicit Play; keeps cartridge code out of the offer chunk. */
export default function ResearchWaitArcadeGame({
  game,
  reducedMotion,
  sceneArtSrc,
}: {
  game: ArcadeGameKind;
  reducedMotion: boolean;
  sceneArtSrc: string;
}) {
  const cartridge = useMemo(
    () =>
      createArcadeCartridge(game, {
        reducedMotion,
        onWernerBeat: emitLivingTvHostBeat,
      }),
    [game, reducedMotion],
  );
  const shellRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    shellRef.current?.querySelector<HTMLCanvasElement>("canvas")?.focus();
  }, []);

  return (
    <div ref={shellRef} className="research-wait-arcade__cabinet">
      <img
        className="research-wait-arcade__scene-art antiek-living-tv-invent"
        src={sceneArtSrc}
        alt=""
        aria-hidden="true"
        decoding="async"
        draggable={false}
        data-testid="research-wait-playing-living-tv-art"
        style={{ pointerEvents: "none" }}
      />
      <ArcadeMount
        cartridge={cartridge}
        width={480}
        height={300}
        reducedMotion={reducedMotion}
        testId="research-wait-arcade-canvas"
      />
    </div>
  );
}
