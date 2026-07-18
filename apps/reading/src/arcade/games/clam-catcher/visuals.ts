import visualKitUrl from "../../../brand/werner/arcade/clam-catcher-visual-kit-v1.webp";
import { accent, aliasFor, sun, surface } from "../../../design/tokens";
import type { GameContext } from "../../engine/types";
import {
  clamCatchStreakMultiplier,
  type ClamCatcherState,
  type FallingKind,
} from "./logic";

type AtlasImage = CanvasImageSource & { complete?: boolean };

export interface ClamCatcherVisualKit {
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
  common: { sx: 149, sy: 150, sw: 348, sh: 296 },
  pearl: { sx: 708, sy: 97, sw: 359, sh: 386 },
  jellyfish: { sx: 167, sy: 627, sw: 310, sh: 514 },
  bucket: { sx: 657, sy: 677, sw: 443, sh: 422 },
});

const ENTITY_SIZE: Record<FallingKind, { width: number; height: number }> = {
  // Every authored silhouette stays inside the unchanged radius hit circle.
  "common-clam": { width: 18, height: 15 },
  "pearl-clam": { width: 18, height: 19 },
  jellyfish: { width: 16, height: 26 },
};

/** One bounded project asset, created only after the user explicitly starts a game. */
export function createClamCatcherVisualKit(
  createImage: (() => HTMLImageElement) | null = typeof Image === "undefined"
    ? null
    : () => new Image(),
): ClamCatcherVisualKit {
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

const EMPTY_VISUAL_KIT: ClamCatcherVisualKit = Object.freeze({
  image: null,
  ready: false,
  load() {},
  dispose() {},
});

export function renderClamCatcher(
  c2d: CanvasRenderingContext2D,
  ctx: GameContext,
  state: ClamCatcherState,
  kit: ClamCatcherVisualKit,
): void {
  const day = aliasFor("day");
  c2d.clearRect(0, 0, ctx.width, ctx.height);

  // An archive observation chamber, not a generic aquarium gradient: three
  // flat water strata, a brass datum rail, and quiet shelf silhouettes.
  c2d.fillStyle = surface.day[6];
  c2d.fillRect(0, 0, ctx.width, ctx.height);
  c2d.fillStyle = surface.day[5];
  c2d.fillRect(0, Math.round(ctx.height * 0.34), ctx.width, ctx.height * 0.66);
  c2d.fillStyle = surface.day[4];
  c2d.fillRect(0, Math.round(ctx.height * 0.72), ctx.width, ctx.height * 0.28);
  c2d.fillStyle = day.border;
  for (let shelf = 0; shelf < 3; shelf += 1) {
    c2d.fillRect(20 + shelf * 44, 54 + shelf * 28, 28, 3);
  }
  c2d.fillStyle = sun.deep.day;
  c2d.fillRect(0, ctx.height - 22, ctx.width, 2);

  for (const entity of state.entities) {
    if (kit.ready && kit.image) {
      drawAtlasEntity(c2d, kit.image, entity.kind, entity.x, entity.y);
    } else {
      drawFallbackEntity(c2d, entity.kind, entity.x, entity.y, entity.radius);
    }
  }

  const bucketY = ctx.height - 34;
  if (kit.ready && kit.image) {
    drawAtlasCell(
      c2d,
      kit.image,
      ATLAS.bucket,
      state.bucketX - 29,
      bucketY,
      58,
      55,
    );
  } else {
    c2d.fillStyle = sun.base;
    c2d.fillRect(state.bucketX - 29, bucketY, 58, 14);
    c2d.fillStyle = day.text;
    c2d.fillRect(state.bucketX - 24, bucketY + 4, 48, 3);
  }

  drawHud(c2d, ctx, state, day.text);
}

function drawAtlasEntity(
  c2d: CanvasRenderingContext2D,
  image: CanvasImageSource,
  kind: FallingKind,
  x: number,
  y: number,
): void {
  const cell =
    kind === "jellyfish"
      ? ATLAS.jellyfish
      : kind === "pearl-clam"
        ? ATLAS.pearl
        : ATLAS.common;
  const size = ENTITY_SIZE[kind];
  const dx = x - size.width / 2;
  const dy = y - size.height / 2;
  drawAtlasCell(c2d, image, cell, dx, dy, size.width, size.height);
  // Pearl densify: sun rim marks rare clam (parity with ice golden rim).
  if (kind === "pearl-clam") {
    c2d.strokeStyle = sun.base;
    c2d.lineWidth = 1.5;
    c2d.strokeRect(dx + 0.5, dy + 0.5, size.width - 1, size.height - 1);
  }
}

function drawAtlasCell(
  c2d: CanvasRenderingContext2D,
  image: CanvasImageSource,
  cell: { sx: number; sy: number; sw: number; sh: number },
  dx: number,
  dy: number,
  dw: number,
  dh: number,
): void {
  c2d.drawImage(image, cell.sx, cell.sy, cell.sw, cell.sh, dx, dy, dw, dh);
}

function drawFallbackEntity(
  c2d: CanvasRenderingContext2D,
  kind: FallingKind,
  x: number,
  y: number,
  radius: number,
): void {
  c2d.fillStyle =
    kind === "jellyfish"
      ? accent.emperor.day
      : kind === "pearl-clam"
        ? sun.glow.day
        : accent.aurora.day;
  c2d.beginPath();
  c2d.arc(x, y, radius, Math.PI, 0);
  c2d.lineTo(x + radius, y + radius / 2);
  c2d.lineTo(x - radius, y + radius / 2);
  c2d.closePath();
  c2d.fill();
}

function drawHud(
  c2d: CanvasRenderingContext2D,
  ctx: GameContext,
  state: ClamCatcherState,
  textColor: string,
): void {
  c2d.fillStyle = textColor;
  c2d.font = "600 12px ui-monospace, SFMono-Regular, Menlo, monospace";
  c2d.fillText(`SCORE ${state.score}`, 10, 18);
  c2d.fillText(`LIVES ${state.lives}`, 10, 35);
  // Club Penguin catch-streak densify: show xN only while streak is live.
  if (state.streak > 0) {
    c2d.fillStyle = sun.base;
    c2d.fillText(
      `x${clamCatchStreakMultiplier(state.streak)}`,
      Math.max(96, ctx.width * 0.42),
      18,
    );
  }
  c2d.fillStyle = textColor;
  c2d.font = "12px system-ui, sans-serif";
  if (state.phase === "ready") {
    c2d.fillText(
      "Pointer or arrows to catch — Enter to start",
      10,
      ctx.height - 50,
    );
  } else if (state.phase === "gameover") {
    c2d.fillText("Shift over — Enter to retry", 10, ctx.height - 50);
    // Peak catch-streak brag densify (cabinet/wait craft).
    if (state.maxStreak > 0) {
      c2d.fillStyle = sun.base;
      c2d.font = "600 12px ui-monospace, SFMono-Regular, Menlo, monospace";
      c2d.fillText(
        `BEST x${clamCatchStreakMultiplier(state.maxStreak)}`,
        10,
        ctx.height - 32,
      );
    }
  }
}
