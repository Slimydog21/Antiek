import type { ArcadeGameKind } from "./cartridgeFactory";
import type { CartridgeMeta } from "./engine/types";

/**
 * Single source of truth for cartridge discovery copy. The cartridges
 * report this meta through the engine contract and the wait-arcade chooser
 * reads the same entries, so chooser copy can never drift from what the
 * mounted game announces (previously duplicated in ARCADE_CHOICES).
 *
 * `instructions` is the per-cartridge screen-reader copy ArcadeMount
 * announces — it names only that game's controls. "Escape exits" is the
 * host shell's promise (ResearchWaitArcade intercepts Escape in the capture
 * phase and restores focus), not the engine's.
 */
export const ARCADE_CARTRIDGE_META: Record<ArcadeGameKind, CartridgeMeta> = {
  zombies: {
    title: "Paperclip Zombies",
    blurb: "Defend the fort while deep research runs.",
    instructions:
      "Focus the game, then press Space or Enter to start. Aim with the " +
      "pointer and click, or press Space, to fire. Escape exits the game.",
    style: "defense",
  },
  "ice-fishing": {
    title: "Ice Fishing",
    blurb: "Drop the line, catch fish, avoid the boot.",
    instructions:
      "Focus the game, then press Space or Enter to start. Move the pointer " +
      "to aim, press Space or Arrow Down to drop the line, and Arrow Up to " +
      "reel. Escape exits the game.",
    style: "fishing",
  },
};
