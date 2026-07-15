import { useEffect, useMemo, useRef, useState } from "react";

import { ArcadeMount } from "../../arcade/engine/ArcadeMount";
import backdropUrl from "../../arcade/games/ice-fishing/assets/werner_ice_hole_alpine_archive_v1.webp";
import { createIceFishingCartridge } from "../../arcade/games/ice-fishing";
import {
  loadIceFishingBackdrop,
  type IceFishingBackdropRef,
} from "../../arcade/games/ice-fishing/iceFishingBackdrop";
import { usePrefersReducedMotion } from "../../workspace/usePrefersReducedMotion";

/** Lazy boundary: neither cartridge nor authored image enters the Library offer chunk. */
export default function WernerIceHoleGame() {
  const reducedMotion = usePrefersReducedMotion();
  const backdropRef = useRef<IceFishingBackdropRef>({ current: null });
  const shellRef = useRef<HTMLDivElement | null>(null);
  const [backdropReady, setBackdropReady] = useState(false);
  const cartridge = useMemo(
    () =>
      createIceFishingCartridge({
        reducedMotion,
        backdrop: backdropRef.current,
      }),
    [reducedMotion],
  );
  const instructions = reducedMotion
    ? "Focus Ice Fishing. Press Space or Enter to start. Each click or Arrow Down resolves one still fish-or-boot encounter; no automatic motion plays. Escape exits the game."
    : "Focus Ice Fishing. Press Space or Enter to start. Move the pointer to aim; click or Arrow Down drops the line; Arrow Up or W reels it in. Escape exits the game.";

  useEffect(() => {
    shellRef.current?.querySelector<HTMLCanvasElement>("canvas")?.focus();
  }, []);

  useEffect(
    () =>
      loadIceFishingBackdrop(backdropUrl, backdropRef.current, undefined, () =>
        setBackdropReady(true),
      ),
    [],
  );

  return (
    <div ref={shellRef} data-backdrop-ready={backdropReady}>
      <ArcadeMount
        cartridge={cartridge}
        width={480}
        height={300}
        reducedMotion={reducedMotion}
        redrawToken={backdropReady ? 1 : 0}
        testId="werner-ice-hole-canvas"
        instructions={instructions}
      />
    </div>
  );
}
