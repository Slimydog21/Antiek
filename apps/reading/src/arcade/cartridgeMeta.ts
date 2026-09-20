import type { ArcadeGameKind } from "./cartridgeFactory";
import type { CartridgeMeta } from "./engine/types";

/**
 * Single source of truth for cartridge discovery copy. The cartridges
 * report this meta through the engine contract and the wait-arcade chooser
 * reads the same entries, so chooser copy can never drift from what the
 * mounted game announces (previously duplicated in ARCADE_CHOICES).
 */
export const ARCADE_CARTRIDGE_META: Record<ArcadeGameKind, CartridgeMeta> = {
  zombies: {
    title: "Paperclip Zombies",
    blurb: "Defend the fort while deep research runs.",
    style: "zombies-arcade",
  },
  "ice-fishing": {
    title: "Ice Fishing",
    blurb: "Drop the line, catch fish, avoid the boot.",
    style: "club-penguin",
  },
};
