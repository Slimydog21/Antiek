import { useEffect, useMemo, useRef, useState } from "react";

import { ArcadeMount } from "../../arcade/engine/ArcadeMount";
import backdropUrl from "../../arcade/games/fjord-skip/assets/werner_fjord_skip_archive_v1.webp";
import { createFjordSkipCartridge } from "../../arcade/games/fjord-skip";
import {
  loadFjordSkipBackdrop,
  type FjordSkipBackdropRef,
} from "../../arcade/games/fjord-skip/fjordSkipBackdrop";
import { usePrefersReducedMotion } from "../../workspace/usePrefersReducedMotion";

/**
 * Lazy boundary: neither cartridge nor authored image enters the
 * BrainstormStation offer chunk.
 */
export default function FjordSkipGame() {
  const reducedMotion = usePrefersReducedMotion();
  const backdropRef = useRef<FjordSkipBackdropRef>({ current: null });
  const shellRef = useRef<HTMLDivElement | null>(null);
  const [backdropReady, setBackdropReady] = useState(false);
  const cartridge = useMemo(
    () =>
      createFjordSkipCartridge({
        reducedMotion,
        backdrop: backdropRef.current,
      }),
    [reducedMotion],
  );
  const instructions = reducedMotion
    ? "Focus Fjord Skip. Press Enter to start. Left and Right aim, or point at a lane. Each click or Space press-and-release resolves one throw immediately; no automatic motion plays. Escape exits the game."
    : "Focus Fjord Skip. Press Enter to start. Left and Right aim, or point at a lane; hold Space or pointer to charge; release to throw. Enter retries. Escape exits the game.";

  useEffect(() => {
    shellRef.current?.querySelector<HTMLCanvasElement>("canvas")?.focus();
  }, []);

  useEffect(
    () =>
      loadFjordSkipBackdrop(backdropUrl, backdropRef.current, undefined, () =>
        setBackdropReady(true),
      ),
    [],
  );

  return (
    <div ref={shellRef} data-backdrop-ready={backdropReady}>
      <ArcadeMount
        cartridge={cartridge}
        width={960}
        height={600}
        reducedMotion={reducedMotion}
        redrawToken={backdropReady ? 1 : 0}
        testId="fjord-skip-canvas"
        instructions={instructions}
      />
    </div>
  );
}
