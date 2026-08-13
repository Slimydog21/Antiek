/**
 * Knowledge-graph constellation (Processing-style seed sketch §12).
 *
 * Nodes + edges laid out by a seeded radial spiral. Same seed → same
 * graph topology and positions. Under reduced-motion the graph is static;
 * otherwise `params.t` gently phases a slow rotation (caller drives t).
 *
 * Pure Canvas2D. No p5.js. Token colours only (design/tokens).
 */

import { accent, sun, sunLight, surface } from "../../design/tokens";
import { coerceSeed, makeRng } from "./seed";
import type { SketchBaseParams, SketchRender } from "./types";

/** Salt mixed into the seed so this sketch's stream is distinct from peers. */
const SKETCH_SALT = 0xc0457e11;

export interface ConstellationParams extends SketchBaseParams {
  /** Number of nodes. Clamped to [4, 64]. Default 18. */
  nodeCount?: number;
  /** Edge density in [0, 1]. Default 0.28. */
  edgeDensity?: number;
}

export interface ConstellationNode {
  /** Normalised x in [0, 1]. */
  x: number;
  /** Normalised y in [0, 1]. */
  y: number;
  /** Radius scale in [0, 1]. */
  r: number;
  /** 0..1 importance — brighter nodes, thicker edges. */
  weight: number;
}

export interface ConstellationEdge {
  a: number;
  b: number;
  strength: number;
}

export interface ConstellationLayout {
  nodes: ConstellationNode[];
  edges: ConstellationEdge[];
}

/**
 * Pure layout generator — no canvas. Unit-testable determinism surface.
 * Positions are in [0,1]² so they scale to any canvas size.
 */
export function layoutConstellation(
  seed: string | number,
  nodeCount = 18,
  edgeDensity = 0.28,
): ConstellationLayout {
  const n = Math.max(4, Math.min(64, Math.floor(nodeCount)));
  const density = Math.max(0, Math.min(1, edgeDensity));
  const rng = makeRng(coerceSeed(seed) ^ SKETCH_SALT);

  const nodes: ConstellationNode[] = [];
  for (let i = 0; i < n; i++) {
    // Golden-angle spiral with jitter — reads as a knowledge-graph cloud,
    // not a perfect lattice (which would look mechanical).
    const t = (i + 0.5) / n;
    const angle = i * 2.399963229728653; // golden angle (radians)
    const radius = 0.12 + t * 0.38 + rng.range(-0.03, 0.03);
    const cx = 0.5 + Math.cos(angle) * radius + rng.range(-0.02, 0.02);
    const cy = 0.5 + Math.sin(angle) * radius + rng.range(-0.02, 0.02);
    nodes.push({
      x: Math.max(0.04, Math.min(0.96, cx)),
      y: Math.max(0.04, Math.min(0.96, cy)),
      r: rng.range(0.35, 1),
      weight: rng.range(0.25, 1),
    });
  }

  // Prefer short edges (local neighbourhood) — denser near the core.
  const edges: ConstellationEdge[] = [];
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const dx = nodes[i].x - nodes[j].x;
      const dy = nodes[i].y - nodes[j].y;
      const dist = Math.hypot(dx, dy);
      // Probabilistic accept: closer pairs + higher density → more edges.
      const p = density * (1 - Math.min(1, dist / 0.55));
      if (rng.next() < p) {
        edges.push({
          a: i,
          b: j,
          strength: (nodes[i].weight + nodes[j].weight) * 0.5 * (1 - dist),
        });
      }
    }
  }

  return { nodes, edges };
}

export const DEFAULT_CONSTELLATION_PARAMS: ConstellationParams = {
  seed: "antiek-constellation",
  nodeCount: 18,
  edgeDensity: 0.28,
  t: 0,
  reducedMotion: false,
  mode: "night",
};

/**
 * Pure render. Mutates only the canvas context.
 * When reducedMotion is true (or t is undefined), draws a frozen frame.
 */
export const renderConstellation: SketchRender<ConstellationParams> = (
  ctx,
  width,
  height,
  params,
) => {
  const {
    seed,
    nodeCount = 18,
    edgeDensity = 0.28,
    t = 0,
    reducedMotion = false,
    mode = "night",
  } = params;

  const layout = layoutConstellation(seed, nodeCount, edgeDensity);
  const palette = surface[mode];
  const bg = palette[2];
  const edgeColor = mode === "night" ? sunLight.base : sun.deep.day;
  const nodeColor = mode === "night" ? sun.base : sun.deep.day;
  const hubColor = mode === "night" ? accent.aurora.night : accent.aurora.day;
  const ink = palette[8];

  // Soft phase rotation under motion; frozen under reduced-motion.
  const phase = reducedMotion ? 0 : (t / 1000) * 0.08;
  const cosP = Math.cos(phase);
  const sinP = Math.sin(phase);

  ctx.save();
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  // Gentle radial vignette so the graph floats in the card.
  const g = ctx.createRadialGradient(
    width * 0.5,
    height * 0.5,
    Math.min(width, height) * 0.1,
    width * 0.5,
    height * 0.5,
    Math.min(width, height) * 0.65,
  );
  g.addColorStop(0, "rgba(0,0,0,0)");
  g.addColorStop(1, mode === "night" ? "rgba(0,0,0,0.35)" : "rgba(0,0,0,0.06)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, width, height);

  const project = (nx: number, ny: number): { x: number; y: number } => {
    // Rotate about centre in normalised space, then scale to canvas.
    const dx = nx - 0.5;
    const dy = ny - 0.5;
    const rx = dx * cosP - dy * sinP + 0.5;
    const ry = dx * sinP + dy * cosP + 0.5;
    return { x: rx * width, y: ry * height };
  };

  // Edges first.
  ctx.lineCap = "round";
  for (const e of layout.edges) {
    const a = project(layout.nodes[e.a].x, layout.nodes[e.a].y);
    const b = project(layout.nodes[e.b].x, layout.nodes[e.b].y);
    const alpha = 0.18 + e.strength * 0.55;
    ctx.strokeStyle = edgeColor;
    ctx.globalAlpha = Math.max(0.08, Math.min(0.85, alpha));
    ctx.lineWidth = 0.6 + e.strength * 1.8;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;

  // Nodes.
  const minDim = Math.min(width, height);
  for (let i = 0; i < layout.nodes.length; i++) {
    const node = layout.nodes[i];
    const p = project(node.x, node.y);
    const r = (1.6 + node.r * 3.4) * (minDim / 320);
    const isHub = node.weight > 0.78;
    ctx.fillStyle = isHub ? hubColor : nodeColor;
    ctx.globalAlpha = 0.55 + node.weight * 0.45;
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fill();
    // Soft halo on hubs.
    if (isHub) {
      ctx.globalAlpha = 0.18;
      ctx.beginPath();
      ctx.arc(p.x, p.y, r * 2.4, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.globalAlpha = 1;

  // Tiny provenance mark (seed fingerprint, bottom-right).
  const fingerprint = (coerceSeed(seed) >>> 0).toString(16).padStart(8, "0");
  ctx.fillStyle = ink;
  ctx.globalAlpha = 0.35;
  ctx.font = `${Math.max(8, minDim * 0.028)}px "JetBrains Mono", ui-monospace, monospace`;
  ctx.textAlign = "right";
  ctx.textBaseline = "bottom";
  ctx.fillText(fingerprint.slice(0, 8), width - 6, height - 4);
  ctx.globalAlpha = 1;
  ctx.restore();
};
