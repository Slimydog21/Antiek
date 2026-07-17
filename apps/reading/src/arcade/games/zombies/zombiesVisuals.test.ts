import { readFileSync } from "node:fs";

import { describe, expect, it, vi } from "vitest";

import { createZombiesState, startZombies, type ZombiesState } from "./logic";
import {
  createZombiesVisualKit,
  drawZombiesScene,
  type ZombiesVisualKit,
  zombiesVisualLayout,
} from "./zombiesVisuals";

function recordingContext() {
  const calls: Array<[string, ...unknown[]]> = [];
  const method = (name: string) =>
    vi.fn((...args: unknown[]) => calls.push([name, ...args]));
  const context = {
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 1,
    font: "",
    beginPath: method("beginPath"),
    closePath: method("closePath"),
    moveTo: method("moveTo"),
    lineTo: method("lineTo"),
    fill: method("fill"),
    stroke: method("stroke"),
    fillRect: method("fillRect"),
    strokeRect: method("strokeRect"),
    fillText: method("fillText"),
    ellipse: method("ellipse"),
    save: method("save"),
    restore: method("restore"),
    translate: method("translate"),
    rotate: method("rotate"),
    drawImage: method("drawImage"),
  } as unknown as CanvasRenderingContext2D;
  return { context, calls };
}

function scene(phase: ZombiesState["phase"]): ZombiesState {
  const base = startZombies(
    createZombiesState({ width: 480, height: 300, lives: 3 }),
  );
  return {
    ...base,
    phase,
    wave: 4,
    score: 137,
    lives: phase === "gameover" ? 0 : 2,
    zombies:
      phase === "playing"
        ? [{ id: 7, x: 310, y: 120, hp: 2, speed: 40, w: 18, h: 18 }]
        : [],
  };
}

describe("Paperclip Zombies field-station visuals", () => {
  it("loads fresh project-atlas images and ignores stale callbacks after disposal", () => {
    const first = { decoding: "auto", onload: null, onerror: null, src: "" };
    const second = { decoding: "auto", onload: null, onerror: null, src: "" };
    const createImage = vi
      .fn()
      .mockReturnValueOnce(first)
      .mockReturnValueOnce(second);
    const kit = createZombiesVisualKit(
      createImage as unknown as () => HTMLImageElement,
    );
    expect(createImage).not.toHaveBeenCalled();
    kit.load();
    const staleOnload = first.onload as unknown as () => void;
    expect(first.src).toMatch(/paperclip-zombies-visual-kit-v1\.webp$/);
    expect(first.decoding).toBe("async");
    kit.dispose();
    staleOnload();
    expect(kit.ready).toBe(false);
    expect(first.onload).toBeNull();
    expect(first.onerror).toBeNull();
    kit.load();
    expect(createImage).toHaveBeenCalledTimes(2);
    expect(kit.image).toBe(second);
  });

  it("aspect-fits each authored HP silhouette inside its authoritative rectangle", () => {
    const state = {
      ...scene("playing"),
      zombies: [
        { id: 1, x: 100, y: 80, hp: 1, speed: 0, w: 18, h: 18 },
        { id: 2, x: 140, y: 100, hp: 2, speed: 0, w: 18, h: 18 },
        { id: 3, x: 180, y: 120, hp: 3, speed: 0, w: 18, h: 18 },
      ],
    };
    const { context, calls } = recordingContext();
    const kit: ZombiesVisualKit = {
      image: {} as CanvasImageSource,
      ready: true,
      load() {},
      dispose() {},
    };
    drawZombiesScene(context, state, 480, 300, kit);
    const images = calls.filter(([name]) => name === "drawImage");
    expect(images.map((call) => call.slice(2, 6))).toEqual([
      [720, 706, 348, 432],
      [250, 165, 208, 332],
      [782, 80, 204, 462],
      [112, 699, 437, 392],
    ]);
    for (const [index, zombie] of state.zombies.entries()) {
      const [, , , , , , dx, dy, dw, dh] = images[index + 1] ?? [];
      expect(dx as number).toBeGreaterThanOrEqual(zombie.x);
      expect(dy as number).toBeGreaterThanOrEqual(zombie.y);
      expect((dx as number) + (dw as number)).toBeLessThanOrEqual(
        zombie.x + zombie.w,
      );
      expect((dy as number) + (dh as number)).toBeLessThanOrEqual(
        zombie.y + zombie.h,
      );
    }
    expect(calls).toContainEqual(["fillRect", -7, 5.040000000000001, 2, 2]);
  });

  it.each(["ready", "playing", "gameover", "exited"] as const)(
    "renders the exact %s phase plate",
    (phase) => {
      const { context, calls } = recordingContext();
      drawZombiesScene(context, scene(phase), 480, 300);
      expect(calls).toContainEqual([
        "fillText",
        {
          ready: "OPEN THE NIGHT FILE · CLICK OR ENTER",
          playing: "ARCHIVE HOLDING · ESC EXITS",
          gameover: "FORT FALLEN · ENTER TO REFILE",
          exited: "SHIFT CLOSED · RESEARCH AWAITS",
        }[phase],
        12,
        290,
      ]);
    },
  );

  it("draws the archival fort, evidence trace, paperclip loops, hp pips, and HUD", () => {
    const { context, calls } = recordingContext();
    drawZombiesScene(context, scene("playing"), 480, 300);
    expect(calls).toContainEqual(["strokeRect", 7, 40, 14, 11]);
    expect(calls).toContainEqual(["lineTo", 298, 129]);
    expect(calls.filter(([name]) => name === "ellipse")).toHaveLength(2);
    expect(calls).toContainEqual(["fillText", "WAVE 04", 480 * 0.22, 14]);
    expect(calls).toContainEqual([
      "fillText",
      "SCORE 0137",
      480 * 0.4,
      14,
    ]);
    expect(calls).toContainEqual(["fillRect", -7, 5.040000000000001, 2, 2]);
    expect(calls).toContainEqual(["fillRect", 5, 5.040000000000001, 2, 2]);
  });

  it("brags peak BO1 combo on gameover status plate", () => {
    const { context, calls } = recordingContext();
    const over = { ...scene("gameover"), maxCombo: 3, score: 40, lives: 0 };
    drawZombiesScene(context, over, 480, 300);
    // statusTop = height - STATUS_HEIGHT (28) → 272; brag sits at +34.
    expect(calls).toContainEqual(["fillText", "BEST x4", 12, 306]);
  });

  it("keeps all structural bands inside compact canvas bounds", () => {
    expect(zombiesVisualLayout(96, 80)).toEqual({
      fieldTop: 20,
      fieldBottom: 52,
      fortRight: 28,
      statusTop: 52,
    });
    expect(zombiesVisualLayout(480, 300)).toEqual({
      fieldTop: 20,
      fieldBottom: 272,
      fortRight: 28,
      statusTop: 272,
    });

    const { context, calls } = recordingContext();
    drawZombiesScene(context, scene("ready"), 96, 80);
    expect(calls).toContainEqual(["fillText", "W04", 4, 13]);
    expect(calls).toContainEqual(["fillText", "S0137", 28.799999999999997, 13]);
    expect(calls).toContainEqual(["fillText", "READY · ENTER", 7, 70]);
    const verticalCoordinates = calls
      .filter(([name]) => name === "moveTo" || name === "lineTo")
      .flatMap(([, , y]) => (typeof y === "number" ? [y] : []));
    expect(Math.min(...verticalCoordinates)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...verticalCoordinates)).toBeLessThanOrEqual(80);
  });

  it("draws spawn-edge targets after chrome without moving their hitboxes", () => {
    const state = {
      ...scene("playing"),
      zombies: [
        { id: 1, x: 300, y: 20, hp: 1, speed: 0, w: 18, h: 18 },
        { id: 2, x: 300, y: 270, hp: 1, speed: 0, w: 18, h: 18 },
      ],
    };
    const { context, calls } = recordingContext();
    drawZombiesScene(context, state, 480, 300);
    const statusIndex = calls.findIndex(
      ([name, text]) =>
        name === "fillText" && text === "ARCHIVE HOLDING · ESC EXITS",
    );
    const targets = calls
      .map((call, index) => ({ call, index }))
      .filter(({ call: [name] }) => name === "translate");
    expect(targets.map(({ call }) => call)).toEqual([
      ["translate", 309, 29],
      ["translate", 309, 279],
    ]);
    expect(targets.every(({ index }) => index > statusIndex)).toBe(true);
  });

  it("keeps compact edge targets wholly inside their authoritative rectangles", () => {
    const state = {
      ...scene("playing"),
      width: 96,
      height: 80,
      zombies: [
        { id: 1, x: 78, y: 20, hp: 1, speed: 0, w: 18, h: 18 },
        { id: 2, x: 78, y: 34, hp: 1, speed: 0, w: 18, h: 18 },
      ],
    };
    const { context, calls } = recordingContext();
    drawZombiesScene(context, state, 96, 80);
    expect(calls.filter(([name]) => name === "rotate")).toHaveLength(0);
    expect(calls.filter(([name]) => name === "translate")).toEqual([
      ["translate", 87, 29],
      ["translate", 87, 43],
    ]);
    expect(calls.filter(([name]) => name === "ellipse")).toEqual([
      ["ellipse", 0, 0, 6.12, 6.84, 0, 0, Math.PI * 2],
      ["ellipse", 1, 0, 3.6, 6.12, 0, 0, Math.PI * 2],
      ["ellipse", 0, 0, 6.12, 6.84, 0, 0, Math.PI * 2],
      ["ellipse", 1, 0, 3.6, 6.12, 0, 0, Math.PI * 2],
    ]);
    expect(calls).toContainEqual(["lineTo", -7.56, 3]);
    expect(calls).toContainEqual(["lineTo", 7.56, 3]);
    expect(calls).toContainEqual(["fillRect", -1, 5.040000000000001, 2, 2]);
  });

  it("compresses every reachable hp pip inside the authoritative hitbox", () => {
    const state = {
      ...scene("playing"),
      zombies: [{ id: 1, x: 78, y: 20, hp: 99, speed: 0, w: 18, h: 18 }],
    };
    const { context, calls } = recordingContext();
    drawZombiesScene(context, state, 96, 80);
    const pips = calls.filter(
      ([name, , y, width, height]) =>
        name === "fillRect" &&
        y === 5.040000000000001 &&
        typeof width === "number" &&
        width <= 2 &&
        height === 2,
    );
    expect(pips).toHaveLength(99);
    expect(pips[0]?.[1]).toBe(-7);
    const last = pips.at(-1);
    expect((last?.[1] as number) + (last?.[3] as number)).toBeCloseTo(7);
  });

  it("is deterministic and does not mutate authoritative game state", () => {
    const state = scene("playing");
    const before = structuredClone(state);
    const first = recordingContext();
    const second = recordingContext();
    drawZombiesScene(first.context, state, 480, 300);
    drawZombiesScene(second.context, state, 480, 300);
    expect(first.calls).toEqual(second.calls);
    expect(state).toEqual(before);
  });

  it("derives color and typography from tokens without raw visual literals", () => {
    const source = readFileSync(
      "src/arcade/games/zombies/zombiesVisuals.ts",
      "utf8",
    );
    expect(source).not.toMatch(/#[\da-f]{3,8}\b/i);
    expect(source).not.toContain("system-ui");
    expect(source).not.toMatch(
      /state\.elapsed|Date\.|performance\.|Math\.random|requestAnimationFrame|setTimeout|setInterval|createImageBitmap|fetch\(|localStorage|sessionStorage/,
    );
    expect(source).toContain("type.mono");
    expect(
      [...source.matchAll(/from "([^"]+)"/g)].map((match) => match[1]),
    ).toEqual([
      "../../../brand/werner/arcade/paperclip-zombies-visual-kit-v1.webp",
      "../../../design/tokens",
      "./logic",
    ]);
  });
});
