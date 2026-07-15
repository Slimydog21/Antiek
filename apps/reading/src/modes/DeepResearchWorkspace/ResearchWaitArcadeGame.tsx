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
}: {
  game: ArcadeGameKind;
  reducedMotion: boolean;
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
    <div ref={shellRef}>
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
