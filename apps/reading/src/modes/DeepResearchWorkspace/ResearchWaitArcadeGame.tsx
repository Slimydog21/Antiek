import { useEffect, useMemo, useRef } from "react";

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

  useEffect(() => {
    shellRef.current?.querySelector<HTMLCanvasElement>("canvas")?.focus();
  }, []);

  useEffect(
    () => loadZombiesBackdrop(backdropUrl, backdropRef.current),
    [],
  );

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
