import { useEffect, useMemo, useRef } from "react";

import { ArcadeMount } from "../../arcade/engine/ArcadeMount";
import {
  createArcadeCartridge,
  type ArcadeGameKind,
} from "../../arcade/cartridgeFactory";

/** Loaded only after explicit Play; keeps cartridge code out of the offer chunk. */
export default function ResearchWaitArcadeGame({
  game,
  reducedMotion,
  sceneArtSrc,
  paused = false,
}: {
  game: ArcadeGameKind;
  reducedMotion: boolean;
  sceneArtSrc: string;
  paused?: boolean;
}) {
  const cartridge = useMemo(
    () => createArcadeCartridge(game, { reducedMotion }),
    [game, reducedMotion],
  );
  const shellRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    shellRef.current?.querySelector<HTMLCanvasElement>("canvas")?.focus();
  }, []);

  return (
    <div ref={shellRef} className="research-wait-arcade__cabinet">
      <img
        className="research-wait-arcade__scene-art"
        src={sceneArtSrc}
        alt=""
        aria-hidden="true"
        decoding="async"
        draggable={false}
        style={{ pointerEvents: "none" }}
      />
      <ArcadeMount
        cartridge={cartridge}
        width={480}
        height={300}
        reducedMotion={reducedMotion}
        paused={paused}
        testId="research-wait-arcade-canvas"
      />
    </div>
  );
}
