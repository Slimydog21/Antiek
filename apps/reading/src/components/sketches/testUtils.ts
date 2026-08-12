/**
 * Test helpers for Processing-style sketches.
 *
 * jsdom has no real Canvas2D bitmap, so we:
 *   1. Record draw-call sequences (zombiesVisuals pattern) for exact equality.
 *   2. Hash the call log into a stable string "pixel hash" so tests can assert
 *      same seed → same hash, param change → different hash — without node-canvas.
 */

import { vi } from "vitest";

export type DrawCall = [string, ...unknown[]];

export interface RecordingContext {
  context: CanvasRenderingContext2D;
  calls: DrawCall[];
  /** Stable hash of the call sequence (order + serialised args). */
  hash: () => string;
}

function serialise(value: unknown): string {
  if (value === null || value === undefined) return String(value);
  if (typeof value === "number") {
    // Round floats so IEEE dust does not flake hashes across engines.
    return Number.isInteger(value) ? String(value) : value.toFixed(6);
  }
  if (typeof value === "string" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return `[${value.map(serialise).join(",")}]`;
  if (typeof value === "object") {
    const entries = Object.keys(value as object)
      .sort()
      .map((k) => `${k}:${serialise((value as Record<string, unknown>)[k])}`);
    return `{${entries.join(",")}}`;
  }
  return String(value);
}

/** FNV-1a 32-bit over a string — stable across runs. */
export function hashString(s: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16).padStart(8, "0");
}

/**
 * Mock CanvasRenderingContext2D that records every draw call + style set.
 * createRadialGradient / createLinearGradient return stub gradient objects.
 */
export function recordingContext(): RecordingContext {
  const calls: DrawCall[] = [];
  const method = (name: string) =>
    vi.fn((...args: unknown[]) => {
      calls.push([name, ...args]);
    });

  const gradient = {
    addColorStop: vi.fn((offset: number, color: string) => {
      calls.push(["addColorStop", offset, color]);
    }),
  };

  // Style properties — record assignments as pseudo-calls for hash fidelity.
  const styleProps = [
    "fillStyle",
    "strokeStyle",
    "lineWidth",
    "lineCap",
    "lineJoin",
    "globalAlpha",
    "font",
    "textAlign",
    "textBaseline",
    "globalCompositeOperation",
  ] as const;

  const context: Record<string, unknown> = {
    beginPath: method("beginPath"),
    closePath: method("closePath"),
    moveTo: method("moveTo"),
    lineTo: method("lineTo"),
    quadraticCurveTo: method("quadraticCurveTo"),
    bezierCurveTo: method("bezierCurveTo"),
    arc: method("arc"),
    arcTo: method("arcTo"),
    ellipse: method("ellipse"),
    rect: method("rect"),
    fill: method("fill"),
    stroke: method("stroke"),
    fillRect: method("fillRect"),
    strokeRect: method("strokeRect"),
    clearRect: method("clearRect"),
    fillText: method("fillText"),
    strokeText: method("strokeText"),
    save: method("save"),
    restore: method("restore"),
    translate: method("translate"),
    rotate: method("rotate"),
    scale: method("scale"),
    setTransform: method("setTransform"),
    resetTransform: method("resetTransform"),
    clip: method("clip"),
    createRadialGradient: vi.fn((...args: unknown[]) => {
      calls.push(["createRadialGradient", ...args]);
      return gradient;
    }),
    createLinearGradient: vi.fn((...args: unknown[]) => {
      calls.push(["createLinearGradient", ...args]);
      return gradient;
    }),
    measureText: vi.fn((text: string) => {
      calls.push(["measureText", text]);
      return { width: String(text).length * 6 };
    }),
  };

  for (const prop of styleProps) {
    let current: unknown =
      prop === "globalAlpha"
        ? 1
        : prop === "lineWidth"
          ? 1
          : prop === "lineCap"
            ? "butt"
            : prop === "fillStyle" || prop === "strokeStyle"
              ? "#000000"
              : prop === "font"
                ? "10px sans-serif"
                : prop === "textAlign"
                  ? "start"
                  : prop === "textBaseline"
                    ? "alphabetic"
                    : prop === "globalCompositeOperation"
                      ? "source-over"
                      : "";
    Object.defineProperty(context, prop, {
      configurable: true,
      enumerable: true,
      get: () => current,
      set: (v: unknown) => {
        current = v;
        calls.push([`set:${prop}`, v]);
      },
    });
  }

  return {
    context: context as unknown as CanvasRenderingContext2D,
    calls,
    hash: () =>
      hashString(calls.map((c) => c.map(serialise).join("|")).join("\n")),
  };
}
