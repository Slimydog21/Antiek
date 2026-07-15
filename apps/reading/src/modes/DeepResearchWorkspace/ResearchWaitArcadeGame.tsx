import { useEffect, useMemo, useRef } from "react";

import { ArcadeMount } from "../../arcade/engine/ArcadeMount";
import { createZombiesCartridge } from "../../arcade/games/zombies";

/** Loaded only after explicit Play; keeps cartridge code out of the offer chunk. */
export default function ResearchWaitArcadeGame() {
  const cartridge = useMemo(() => createZombiesCartridge(), []);
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
        testId="research-wait-arcade-canvas"
      />
    </div>
  );
}
