import visualKitUrl from "../../../brand/werner/arcade/paperclip-zombies-visual-kit-v1.webp";
import {
  accent,
  rule,
  sun,
  sunLight,
  surface,
  type,
} from "../../../design/tokens";
import type { Zombie, ZombiesPhase, ZombiesState } from "./logic";

const HUD_HEIGHT = 20;
const STATUS_HEIGHT = 28;
const FORT_WIDTH = 28;

type AtlasImage = CanvasImageSource & { complete?: boolean };

export interface ZombiesVisualKit {
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
  hp1: { sx: 250, sy: 165, sw: 208, sh: 332 },
  hp2: { sx: 782, sy: 80, sw: 204, sh: 462 },
  hp3: { sx: 112, sy: 699, sw: 437, sh: 392 },
  fort: { sx: 720, sy: 706, sw: 348, sh: 432 },
});

/** One bounded local asset, instantiated only when the cartridge is initialized. */
export function createZombiesVisualKit(
  createImage: (() => HTMLImageElement) | null = typeof Image === "undefined"
    ? null
    : () => new Image(),
): ZombiesVisualKit {
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

const EMPTY_VISUAL_KIT: ZombiesVisualKit = Object.freeze({
  image: null,
  ready: false,
  load() {},
  dispose() {},
});

export const ZOMBIES_PHASE_COPY: Record<ZombiesPhase, string> = {
  ready: "OPEN THE NIGHT FILE · CLICK OR ENTER",
  playing: "ARCHIVE HOLDING · ESC EXITS",
  gameover: "FORT FALLEN · ENTER TO REFILE",
  exited: "SHIFT CLOSED · RESEARCH AWAITS",
};

export const ZOMBIES_COMPACT_PHASE_COPY: Record<ZombiesPhase, string> = {
  ready: "READY · ENTER",
  playing: "HOLD · ESC",
  gameover: "FALLEN · ENTER",
  exited: "SHIFT CLOSED",
};

export interface ZombiesVisualLayout {
  fieldTop: number;
  fieldBottom: number;
  fortRight: number;
  statusTop: number;
}

export function zombiesVisualLayout(
  width: number,
  height: number,
): ZombiesVisualLayout {
  return {
    fieldTop: HUD_HEIGHT,
    fieldBottom: Math.max(HUD_HEIGHT, height - STATUS_HEIGHT),
    fortRight: Math.min(FORT_WIDTH, width),
    statusTop: Math.max(HUD_HEIGHT, height - STATUS_HEIGHT),
  };
}

/** Pure canvas projection: no input, time, persistence, or lifecycle authority. */
export function drawZombiesScene(
  c2d: CanvasRenderingContext2D,
  state: ZombiesState,
  width: number,
  height: number,
  kit: ZombiesVisualKit = EMPTY_VISUAL_KIT,
): void {
  const layout = zombiesVisualLayout(width, height);
  drawField(c2d, width, height, layout);
  drawEvidenceTraces(c2d, state, width, layout);
  drawFort(c2d, state, layout, kit);
  drawHud(c2d, state, width);
  drawStatusPlate(c2d, state.phase, width, height, layout);
  // Targets render above chrome because their authoritative hitboxes may enter
  // the HUD/status bands; visual position must never drift from hit-testing.
  for (const zombie of state.zombies) drawPaperclip(c2d, zombie, kit);
}

function drawField(
  c2d: CanvasRenderingContext2D,
  width: number,
  height: number,
  layout: ZombiesVisualLayout,
): void {
  c2d.fillStyle = surface.night[2];
  c2d.fillRect(0, 0, width, height);

  c2d.fillStyle = surface.night[3];
  const fieldHeight = Math.max(0, layout.fieldBottom - layout.fieldTop);
  c2d.beginPath();
  c2d.moveTo(0, layout.fieldBottom);
  c2d.lineTo(width * 0.28, layout.fieldTop + fieldHeight * 0.2);
  c2d.lineTo(width * 0.48, layout.fieldTop + fieldHeight * 0.36);
  c2d.lineTo(width * 0.68, layout.fieldTop + fieldHeight * 0.14);
  c2d.lineTo(width, layout.fieldTop + fieldHeight * 0.4);
  c2d.lineTo(width, layout.fieldBottom);
  c2d.closePath();
  c2d.fill();

  c2d.strokeStyle = surface.night[5];
  c2d.lineWidth = 1;
  for (let y = layout.fieldTop + 22; y < layout.fieldBottom; y += 24) {
    c2d.beginPath();
    c2d.moveTo(layout.fortRight, y + 0.5);
    c2d.lineTo(width, y + 0.5);
    c2d.stroke();
  }
}

/** Signature: every live threat rides an evidence trace toward the archive. */
function drawEvidenceTraces(
  c2d: CanvasRenderingContext2D,
  state: ZombiesState,
  width: number,
  layout: ZombiesVisualLayout,
): void {
  c2d.strokeStyle =
    state.phase === "gameover" ? accent.emperor.night : sunLight.deep;
  c2d.lineWidth = 1;
  const traces =
    state.zombies.length > 0
      ? state.zombies
      : [{ x: width, y: layout.fieldTop + 62 }];
  for (const trace of traces.slice(0, 6)) {
    const y = Math.min(
      layout.fieldBottom - 8,
      Math.max(layout.fieldTop + 8, trace.y + 9),
    );
    c2d.beginPath();
    c2d.moveTo(layout.fortRight, y);
    c2d.lineTo(Math.max(layout.fortRight, trace.x - 12), y);
    c2d.lineTo(Math.max(layout.fortRight, trace.x - 8), y - 4);
    c2d.lineTo(Math.max(layout.fortRight, trace.x - 4), y + 4);
    c2d.lineTo(Math.max(layout.fortRight, trace.x), y);
    c2d.stroke();
  }
}

function drawFort(
  c2d: CanvasRenderingContext2D,
  state: ZombiesState,
  layout: ZombiesVisualLayout,
  kit: ZombiesVisualKit,
): void {
  const top = layout.fieldTop + 12;
  const bottom = layout.fieldBottom - 8;
  const fortHeight = Math.max(0, bottom - top);
  c2d.fillStyle = surface.night[5];
  c2d.fillRect(0, top, layout.fortRight, fortHeight);
  c2d.strokeStyle =
    state.phase === "gameover" ? accent.emperor.night : sun.base;
  c2d.lineWidth = 2;
  c2d.strokeRect(1, top + 1, layout.fortRight - 3, Math.max(0, fortHeight - 2));

  const diamondY = top + fortHeight / 2;
  if (kit.ready && kit.image) {
    drawAtlasFit(
      c2d,
      kit.image,
      ATLAS.fort,
      5,
      Math.max(top + 2, diamondY - 11),
      18,
      Math.min(22, Math.max(0, fortHeight - 4)),
    );
  } else {
    const diamondRadius = Math.min(7, Math.max(2, fortHeight * 0.2));
    c2d.fillStyle = sun.base;
    c2d.beginPath();
    c2d.moveTo(layout.fortRight / 2, diamondY - diamondRadius);
    c2d.lineTo(layout.fortRight / 2 + diamondRadius, diamondY);
    c2d.lineTo(layout.fortRight / 2, diamondY + diamondRadius);
    c2d.lineTo(layout.fortRight / 2 - diamondRadius, diamondY);
    c2d.closePath();
    c2d.fill();
  }

  c2d.strokeStyle = surface.night[7];
  c2d.lineWidth = 1;
  for (let y = top + 8; y < bottom - 12; y += 18) {
    c2d.strokeRect(7, y, layout.fortRight - 14, 11);
    c2d.beginPath();
    c2d.moveTo(layout.fortRight / 2 - 4, y + 5.5);
    c2d.lineTo(layout.fortRight / 2 + 4, y + 5.5);
    c2d.stroke();
  }
}

function drawPaperclip(
  c2d: CanvasRenderingContext2D,
  zombie: Zombie,
  kit: ZombiesVisualKit,
): void {
  const cx = zombie.x + zombie.w / 2;
  const cy = zombie.y + zombie.h / 2;
  if (kit.ready && kit.image) {
    const cell =
      zombie.hp === 1 ? ATLAS.hp1 : zombie.hp === 2 ? ATLAS.hp2 : ATLAS.hp3;
    drawAtlasFit(c2d, kit.image, cell, zombie.x, zombie.y, zombie.w, zombie.h);
    drawHealthPips(c2d, zombie, cx, cy);
  } else {
    drawFallbackPaperclip(c2d, zombie, cx, cy);
  }
}

function drawFallbackPaperclip(
  c2d: CanvasRenderingContext2D,
  zombie: Zombie,
  cx: number,
  cy: number,
): void {
  c2d.save();
  c2d.translate(cx, cy);
  c2d.strokeStyle = surface.night[8];
  c2d.lineWidth = 2.25;
  c2d.beginPath();
  c2d.ellipse(0, 0, zombie.w * 0.34, zombie.h * 0.38, 0, 0, Math.PI * 2);
  c2d.stroke();
  c2d.beginPath();
  c2d.ellipse(1, 0, zombie.w * 0.2, zombie.h * 0.34, 0, 0, Math.PI * 2);
  c2d.stroke();

  c2d.strokeStyle = accent.aurora.night;
  c2d.lineWidth = 1.5;
  c2d.beginPath();
  c2d.moveTo(-zombie.w * 0.3, -1);
  c2d.lineTo(-zombie.w * 0.42, 3);
  c2d.moveTo(zombie.w * 0.3, -1);
  c2d.lineTo(zombie.w * 0.42, 3);
  c2d.stroke();

  drawHealthPipsAtOrigin(c2d, zombie);
  c2d.restore();
}

function drawHealthPips(
  c2d: CanvasRenderingContext2D,
  zombie: Zombie,
  cx: number,
  cy: number,
): void {
  c2d.save();
  c2d.translate(cx, cy);
  drawHealthPipsAtOrigin(c2d, zombie);
  c2d.restore();
}

function drawHealthPipsAtOrigin(
  c2d: CanvasRenderingContext2D,
  zombie: Zombie,
): void {
  const pipWidth = Math.min(2, 14 / zombie.hp);
  const pipStart = zombie.hp === 1 ? -1 : -7;
  const pipStep = zombie.hp === 1 ? 0 : (14 - pipWidth) / (zombie.hp - 1);
  for (let hp = 0; hp < zombie.hp; hp += 1) {
    c2d.fillStyle = sun.base;
    c2d.fillRect(pipStart + hp * pipStep, zombie.h * 0.28, pipWidth, 2);
  }
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
  if (width <= 0 || height <= 0) return;
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

function drawHud(
  c2d: CanvasRenderingContext2D,
  state: ZombiesState,
  width: number,
): void {
  c2d.fillStyle = surface.night[4];
  c2d.fillRect(0, 0, width, HUD_HEIGHT);
  c2d.strokeStyle = rule.night;
  c2d.lineWidth = 1;
  c2d.beginPath();
  c2d.moveTo(0, HUD_HEIGHT - 0.5);
  c2d.lineTo(width, HUD_HEIGHT - 0.5);
  c2d.stroke();

  if (width < 240) {
    c2d.font = `600 6px ${type.mono}`;
    c2d.fillStyle = surface.night[9];
    c2d.fillText(`W${String(state.wave).padStart(2, "0")}`, 4, 13);
    c2d.fillText(`S${String(state.score).padStart(4, "0")}`, width * 0.3, 13);
    for (let life = 0; life < state.startingLives; life += 1) {
      c2d.fillStyle = life < state.lives ? sun.base : surface.night[6];
      c2d.fillRect(width - 34 + life * 10, 8, 6, 5);
    }
    return;
  }

  c2d.font = `600 10px ${type.mono}`;
  c2d.fillStyle = surface.night[7];
  c2d.fillText("NIGHT FILE", 10, 14);
  c2d.fillStyle = surface.night[9];
  c2d.fillText(`WAVE ${String(state.wave).padStart(2, "0")}`, width * 0.22, 14);
  c2d.fillText(
    `SCORE ${String(state.score).padStart(4, "0")}`,
    width * 0.4,
    14,
  );
  // BO1-style combo densify: show xN only while streak is live.
  if (state.combo > 0) {
    c2d.fillStyle = sun.base;
    c2d.fillText(`x${Math.min(4, 1 + state.combo)}`, width * 0.62, 14);
  }

  c2d.fillStyle = surface.night[7];
  c2d.font = `600 9px ${type.mono}`;
  c2d.fillText("FORT", width - 76, 14);
  for (let life = 0; life < state.startingLives; life += 1) {
    c2d.fillStyle = life < state.lives ? sun.base : surface.night[6];
    c2d.fillRect(width - 42 + life * 12, 8, 8, 6);
  }
}

function drawStatusPlate(
  c2d: CanvasRenderingContext2D,
  phase: ZombiesPhase,
  width: number,
  height: number,
  layout: ZombiesVisualLayout,
): void {
  c2d.fillStyle = surface.night[4];
  c2d.fillRect(0, layout.statusTop, width, height - layout.statusTop);
  c2d.fillStyle = phase === "gameover" ? accent.emperor.night : sun.base;
  c2d.fillRect(0, layout.statusTop, 4, height - layout.statusTop);
  c2d.fillStyle = surface.night[9];
  const compact = width < 240;
  c2d.font = `600 ${compact ? 6 : 10}px ${type.mono}`;
  c2d.fillText(
    compact ? ZOMBIES_COMPACT_PHASE_COPY[phase] : ZOMBIES_PHASE_COPY[phase],
    compact ? 7 : 12,
    layout.statusTop + 18,
  );
}
