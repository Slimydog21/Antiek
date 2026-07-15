import { useEffect, useMemo, useRef, useState } from "react";

import { ArcadeMount } from "../../arcade/engine/ArcadeMount";
import backdropUrl from "../../arcade/games/zombies/assets/paperclip_zombies_night_archive_v1.jpg";
import { createZombiesCartridge } from "../../arcade/games/zombies";
import {
  loadZombiesBackdrop,
  type ZombiesBackdropRef,
} from "../../arcade/games/zombies/zombiesBackdrop";

/** Loaded only after explicit Play; keeps cartridge code out of the offer chunk. */
export default function ResearchWaitArcadeGame() {
  const backdropRef = useRef<ZombiesBackdropRef>({ current: null });
  const cartridge = useMemo(
    () => createZombiesCartridge({ backdrop: backdropRef.current }),
    [],
  );
  const shellRef = useRef<HTMLDivElement | null>(null);
  const [backdropReady, setBackdropReady] = useState(false);

  useEffect(() => {
    shellRef.current?.querySelector<HTMLCanvasElement>("canvas")?.focus();
  }, []);

  useEffect(
    () =>
      loadZombiesBackdrop(
        backdropUrl,
        backdropRef.current,
        undefined,
        () => setBackdropReady(true),
      ),
    [],
  );

  return (
    <div ref={shellRef} data-backdrop-ready={backdropReady}>
      <ArcadeMount
        cartridge={cartridge}
        width={480}
        height={300}
        redrawToken={backdropReady ? 1 : 0}
        testId="research-wait-arcade-canvas"
        instructions="Focus Paperclip Zombies. Press Space or Enter to start. Move the pointer to aim and click to fire. Press Q or Escape to exit."
      />
    </div>
  );
}
