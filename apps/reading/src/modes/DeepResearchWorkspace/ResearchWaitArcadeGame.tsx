import { useEffect, useMemo, useRef } from "react";

import { ArcadeMount } from "../../arcade/engine/ArcadeMount";
import {
  createArcadeCartridge,
  type ArcadeGameKind,
} from "../../arcade/cartridgeFactory";
import { prefersDark } from "../../scene/mood";

/** Loaded only after explicit Play; keeps cartridge code out of the offer chunk. */
export default function ResearchWaitArcadeGame({
  game,
  reducedMotion,
}: {
  game: ArcadeGameKind;
  reducedMotion: boolean;
}) {
  // The cartridge scene follows the app's light/dark mode (D10) — the same
  // OS prefers-color-scheme signal Tailwind's media darkMode uses. Read at
  // cartridge construction; a mid-game OS theme flip applies on next mount.
  const cartridge = useMemo(
    () =>
      createArcadeCartridge(game, {
        reducedMotion,
        mode: prefersDark() ? "night" : "day",
      }),
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
