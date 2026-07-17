import visualKitUrl from "../../../brand/werner/arcade/ice-fishing-visual-kit-v1.webp";
import { accent, aliasFor, sun, surface } from "../../../design/tokens";
import type { GameContext } from "../../engine/types";
import type { Fish, IceFishingState } from "./logic";

type AtlasImage = CanvasImageSource & { complete?: boolean };

export interface IceFishingVisualKit {
  readonly image: AtlasImage | null;
  readonly ready: boolean;
  load(): void;
  dispose(): void;
}

interface MutableVisualKit {
  image: HTMLImageElement | null;
  ready: boolean;
  load(): void;
  dispose(): void;
}

const ATLAS = Object.freeze({
  small: { sx: 62, sy: 228, sw: 486, sh: 196 },
  medium: { sx: 632, sy: 168, sw: 569, sh: 332 },
  hazard: { sx: 94, sy: 776, sw: 466, sh: 258 },
  hook: { sx: 824, sy: 793, sw: 183, sh: 258 },
});

/** One bounded project asset, created only after the user explicitly starts a game. */
export function createIceFishingVisualKit(
  createImage: (() => HTMLImageElement) | null = typeof Image === "undefined"
    ? null
    : () => new Image(),
): IceFishingVisualKit {
  if (!createImage) return EMPTY_VISUAL_KIT;

  const kit: MutableVisualKit = {
    image: null,
    ready: false,
    load() {
      kit.dispose();
      const image = createImage();
      kit.image = image;
      image.decoding = "async";
      image.onload = () => {
        if (kit.image === image) kit.ready = true;
      };
      image.onerror = () => {
        if (kit.image === image) kit.ready = false;
      };
      image.src = visualKitUrl;
    },
    dispose() {
      if (kit.image) {
        kit.image.onload = null;
        kit.image.onerror = null;
      }
      kit.image = null;
      kit.ready = false;
    },
  };
  return kit;
}

const EMPTY_VISUAL_KIT: IceFishingVisualKit = Object.freeze({
  image: null,
  ready: false,
  load() {},
  dispose() {},
});

export function renderIceFishing(
  c2d: CanvasRenderingContext2D,
  ctx: GameContext,
  state: IceFishingState,
  kit: IceFishingVisualKit,
): void {
  const day = aliasFor("day");
  c2d.clearRect(0, 0, ctx.width, ctx.height);
  c2d.fillStyle = surface.day[4];
  c2d.fillRect(0, 0, ctx.width, 48);
  c2d.fillStyle = surface.day[6];
  c2d.fillRect(0, 48, ctx.width, ctx.height - 48);
  c2d.fillStyle = surface.day[9];
  c2d.beginPath();
  c2d.ellipse(ctx.width / 2, 52, 40, 10, 0, 0, Math.PI * 2);
  c2d.fill();

  c2d.strokeStyle = sun.base;
  c2d.lineWidth = 2;
  c2d.beginPath();
  c2d.moveTo(state.hookX, 40);
  c2d.lineTo(state.hookX, state.hookY);
  c2d.stroke();
  if (kit.ready && kit.image) {
    drawAtlasFit(c2d, kit.image, ATLAS.hook, state.hookX - 5, state.hookY - 5, 10, 10);
  } else {
    c2d.fillStyle = sun.base;
    c2d.beginPath();
    c2d.arc(state.hookX, state.hookY, 5, 0, Math.PI * 2);
    c2d.fill();
  }

  for (const fish of state.fishes) {
    if (kit.ready && kit.image) drawAuthoredFish(c2d, kit.image, fish);
    else drawFallbackFish(c2d, fish);
  }

  c2d.fillStyle = day.text;
  c2d.font = "12px system-ui, sans-serif";
  c2d.fillText(`Score ${state.score}`, 8, 16);
  c2d.fillText(`Lives ${state.lives}`, 8, 32);
  // Club Penguin catch-streak densify: show xN only while streak is live.
  if (state.streak > 0) {
    c2d.fillStyle = sun.base;
    c2d.font = "600 12px ui-monospace, SFMono-Regular, Menlo, monospace";
    c2d.fillText(
      `x${Math.min(3, 1 + state.streak)}`,
      Math.max(96, ctx.width * 0.42),
      16,
    );
  }
  c2d.fillStyle = day.text;
  c2d.font = "12px system-ui, sans-serif";
  if (state.phase === "ready") {
    c2d.fillText("Click / Space to fish", 8, ctx.height - 12);
  } else if (state.phase === "gameover") {
    c2d.fillText("Game over — Enter to retry", 8, ctx.height - 12);
  }
}

function drawAuthoredFish(
  c2d: CanvasRenderingContext2D,
  image: CanvasImageSource,
  fish: Fish,
): void {
  const cell = ATLAS[fish.kind];
  if (fish.kind !== "hazard" && fish.vx < 0) {
    c2d.save();
    c2d.translate(fish.x + fish.w / 2, fish.y + fish.h / 2);
    c2d.scale(-1, 1);
    drawAtlasFit(c2d, image, cell, -fish.w / 2, -fish.h / 2, fish.w, fish.h);
    c2d.restore();
    return;
  }
  drawAtlasFit(c2d, image, cell, fish.x, fish.y, fish.w, fish.h);
}

function drawAtlasFit(
  c2d: CanvasRenderingContext2D,
  image: CanvasImageSource,
  cell: { sx: number; sy: number; sw: number; sh: number },
  x: number,
  y: number,
  width: number,
  height: number,
): void {
  const scale = Math.min(width / cell.sw, height / cell.sh);
  const drawWidth = cell.sw * scale;
  const drawHeight = cell.sh * scale;
  c2d.drawImage(
    image,
    cell.sx,
    cell.sy,
    cell.sw,
    cell.sh,
    x + (width - drawWidth) / 2,
    y + (height - drawHeight) / 2,
    drawWidth,
    drawHeight,
  );
}

function drawFallbackFish(c2d: CanvasRenderingContext2D, fish: Fish): void {
  c2d.fillStyle =
    fish.kind === "hazard"
      ? accent.emperor.day
      : fish.kind === "medium"
        ? sun.glow.day
        : accent.aurora.day;
  c2d.fillRect(fish.x, fish.y, fish.w, fish.h);
}
