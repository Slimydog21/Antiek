/**
 * Lineup pitch — Processing-style generative field for the AI Role Lineup.
 *
 * The formation rendered as a code-drawn artefact: deterministic mowing
 * stripes, hand-jittered line markings, and the nine roles as a connected
 * team constellation (a passing network, not a random cloud). Under motion
 * the constellation breathes slowly (nodes pulse, edges shimmer); under
 * reduced-motion it is a frozen, identical frame. A substitution draws a
 * seeded one-shot burst at the swapped role's position.
 *
 * Pure Canvas2D. No p5.js. Token colours only (design/tokens). Same seed +
 * params + size → identical pixels.
 */

import { pitch, sun, sunLight } from "../../design/tokens";
import { FORMATION } from "../../api/settingsLineup";
import { coerceSeed, makeRng } from "./seed";
import type { SketchBaseParams, SketchRender } from "./types";

/** Salt mixed into the seed so this sketch's stream is distinct from peers. */
const SKETCH_SALT = 0x1a7e1c0d;

/** Team passing network — the nine roles as a connected formation graph. */
export const TEAM_EDGES: ReadonlyArray<readonly [string, string]> = [
  ["data_verification", "data_miner"],
  ["data_verification", "indexer"],
  ["data_verification", "data_refinement"],
  ["data_miner", "data_refinement"],
  ["data_miner", "orchestrator"],
  ["indexer", "critic"],
  ["indexer", "voice"],
  ["data_refinement", "writer"],
  ["data_refinement", "orchestrator"],
  ["orchestrator", "writer"],
  ["orchestrator", "media_creator"],
  ["critic", "writer"],
  ["critic", "media_creator"],
  ["voice", "media_creator"],
  ["voice", "critic"],
  ["writer", "media_creator"],
];

export interface LineupPitchParams extends SketchBaseParams {
  /** Formation role to highlight with a sun ring (selection). */
  highlightRole?: string | null;
  /** One-shot substitution burst: role that was swapped in. */
  pulseRole?: string | null;
  /** Deterministic burst seed (the model id that came on). */
  pulseSeed?: string | null;
  /** Wall-clock ms when the pulse began; fades over ~1.4 s of t. */
  pulseT?: number | null;
  /** Wall-clock ms at mount, so render can convert t → wall time purely. */
  mountWall?: number;
}

export interface PitchNode {
  roleId: string;
  /** Normalised x in [0, 1]. */
  x: number;
  /** Normalised y in [0, 1]. */
  y: number;
  weight: number;
  discovered: boolean;
}

export interface PitchLayout {
  nodes: PitchNode[];
  edges: Array<{ a: number; b: number }>;
}

const DISCOVERED_ROLES = new Set([
  "orchestrator",
  "critic",
  "media_creator",
  "voice",
  "indexer",
]);

/** Pure layout: fixed formation positions + the team graph. Deterministic. */
export function layoutLineupPitch(): PitchLayout {
  const rng = makeRng(coerceSeed("antiek-lineup-pitch") ^ SKETCH_SALT);
  const nodes = Object.keys(FORMATION).map((roleId) => {
    const pos = FORMATION[roleId];
    return {
      roleId,
      x: pos.x / 100,
      y: pos.y / 100,
      // Small deterministic per-role weight — brighter/stronger presences.
      weight: 0.55 + rng.next() * 0.4,
      discovered: DISCOVERED_ROLES.has(roleId),
    };
  });
  const index = new Map(nodes.map((n, i) => [n.roleId, i]));
  const edges = TEAM_EDGES.map(([a, b]) => ({
    a: index.get(a)!,
    b: index.get(b)!,
  }));
  return { nodes, edges };
}

export const DEFAULT_LINEUP_PITCH_PARAMS: LineupPitchParams = {
  seed: "antiek-lineup-pitch",
  t: 0,
  reducedMotion: false,
  mode: "night",
  highlightRole: null,
  pulseRole: null,
  pulseSeed: null,
  pulseT: null,
  mountWall: 0,
};

function roundRectPath(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
) {
  ctx.beginPath();
  ctx.rect(x, y, w, h);
}

/**
 * Pure render. Mutates only the canvas context. Deterministic given the
 * params; under reducedMotion (or t undefined) draws the frozen frame.
 */
export const renderLineupPitch: SketchRender<LineupPitchParams> = (
  ctx,
  width,
  height,
  params,
) => {
  const {
    t = 0,
    reducedMotion = false,
    mode = "night",
    highlightRole = null,
    pulseRole = null,
    pulseSeed = null,
    pulseT = null,
    mountWall = 0,
  } = params;

  const field = pitch[mode];
  const layout = layoutLineupPitch();
  const rng = makeRng(coerceSeed(params.seed) ^ SKETCH_SALT);
  const minDim = Math.min(width, height);
  const phase = reducedMotion ? 0 : t;

  ctx.save();

  // ── The field: base gradient + deterministic mowing stripes ───────────
  const grass = ctx.createLinearGradient(0, 0, 0, height);
  grass.addColorStop(0, field.base);
  grass.addColorStop(1, field.deep);
  ctx.fillStyle = grass;
  ctx.fillRect(0, 0, width, height);

  // Mowing stripes: vertical bands with seeded width jitter.
  const stripeCount = 9;
  const stripeBase = width / stripeCount;
  let stripeX = 0;
  for (let i = 0; i < stripeCount; i++) {
    const w = stripeBase * (0.82 + rng.next() * 0.36);
    if (i % 2 === 1) {
      ctx.fillStyle = field.mid;
      ctx.globalAlpha = 0.5;
      ctx.fillRect(stripeX, 0, w, height);
      ctx.globalAlpha = 1;
    }
    stripeX += w;
  }

  // ── Line markings: hand-jittered, translucent white ───────────────────
  const jitter = (): number => rng.range(-1.6, 1.6);
  const white = mode === "night" ? "rgba(255,255,255,0.28)" : "rgba(255,255,255,0.5)";
  ctx.strokeStyle = white;
  ctx.lineWidth = 1.4;

  // Outer boundary + halfway line.
  ctx.strokeRect(
    jitter(), jitter(),
    width + jitter(), height + jitter(),
  );
  ctx.beginPath();
  ctx.moveTo(width / 2 + jitter(), jitter());
  ctx.lineTo(width / 2 + jitter(), height + jitter());
  ctx.stroke();

  // Centre circle + spot.
  ctx.beginPath();
  ctx.arc(width / 2 + jitter(), height / 2 + jitter(), minDim * 0.11, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(width / 2 + jitter(), height / 2 + jitter(), 2, 0, Math.PI * 2);
  ctx.fillStyle = white;
  ctx.fill();

  // Penalty areas (two boxes, mirrored).
  const boxW = width * 0.32;
  const boxH = height * 0.16;
  roundRectPath(ctx, jitter(), jitter(), boxW + jitter(), boxH + jitter());
  ctx.stroke();
  roundRectPath(ctx, width - boxW + jitter(), jitter(), boxW + jitter(), boxH + jitter());
  ctx.stroke();

  // ── The team constellation ────────────────────────────────────────────
  const nodeColor = mode === "night" ? sun.base : sun.deep.day;
  const edgeColor = mode === "night" ? sunLight.base : sun.deep.day;
  const hubColor = mode === "night" ? sun.glow.night : sun.base;

  ctx.lineCap = "round";
  layout.edges.forEach((e, i) => {
    const a = layout.nodes[e.a];
    const b = layout.nodes[e.b];
    const shimmer = reducedMotion ? 0 : Math.sin(phase / 650 + i * 0.7) * 0.06;
    ctx.strokeStyle = edgeColor;
    ctx.globalAlpha = Math.max(0.1, Math.min(0.4, 0.2 + (a.weight + b.weight) * 0.12 + shimmer));
    ctx.lineWidth = 0.8 + (a.weight + b.weight) * 0.7;
    ctx.beginPath();
    ctx.moveTo(a.x * width, a.y * height);
    ctx.lineTo(b.x * width, b.y * height);
    ctx.stroke();
  });
  ctx.globalAlpha = 1;

  for (const node of layout.nodes) {
    const x = node.x * width;
    const y = node.y * height;
    const breathe = reducedMotion ? 0 : Math.sin(phase / 480 + node.weight * 6.28) * 0.9;
    const r = (1.6 + node.weight * 2.6 + breathe * 0.6) * (minDim / 320);
    const isHub = node.weight > 0.8;
    ctx.fillStyle = isHub ? hubColor : nodeColor;
    ctx.globalAlpha = 0.5 + node.weight * 0.45;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    if (isHub) {
      ctx.globalAlpha = 0.16;
      ctx.beginPath();
      ctx.arc(x, y, r * 2.3, 0, Math.PI * 2);
      ctx.fill();
    }
    // Discovered roles get a tiny sparkle cross — NEW SIGNING in the field.
    if (node.discovered) {
      ctx.globalAlpha = 0.75;
      ctx.strokeStyle = white;
      ctx.lineWidth = 0.8;
      const s = (minDim / 320) * 2.2;
      ctx.beginPath();
      ctx.moveTo(x - s, y - s);
      ctx.lineTo(x + s, y + s);
      ctx.moveTo(x + s, y - s);
      ctx.lineTo(x - s, y + s);
      ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;

  // ── Selection ring ────────────────────────────────────────────────────
  if (highlightRole) {
    const node = layout.nodes.find((n) => n.roleId === highlightRole);
    if (node) {
      const x = node.x * width;
      const y = node.y * height;
      const pulse = reducedMotion ? 0 : Math.sin(phase / 300) * 1.5;
      ctx.strokeStyle = nodeColor;
      ctx.lineWidth = 2;
      ctx.globalAlpha = 0.9;
      ctx.beginPath();
      ctx.arc(x, y, (minDim / 320) * (10 + pulse), 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
  }

  // ── One-shot substitution burst ───────────────────────────────────────
  if (pulseRole && pulseSeed && pulseT != null && mountWall > 0) {
    const node = layout.nodes.find((n) => n.roleId === pulseRole);
    if (node) {
      // Convert the frame's t into wall time purely, then age the burst.
      const wallNow = mountWall + t;
      const age = Math.max(0, wallNow - pulseT);
      const lifespan = 1400;
      if (age < lifespan) {
        const x = node.x * width;
        const y = node.y * height;
        const progress = age / lifespan;
        const burstRng = makeRng(coerceSeed(pulseSeed) ^ 0x5eed);
        const ringCount = 3;
        for (let ri = 0; ri < ringCount; ri++) {
          const ringR = (minDim / 320) * (6 + (progress + ri / ringCount) * 26);
          ctx.strokeStyle = hubColor;
          ctx.globalAlpha = Math.max(0, 0.55 * (1 - progress));
          ctx.lineWidth = 1.6 * (1 - progress) + 0.4;
          ctx.beginPath();
          ctx.arc(x, y, ringR, 0, Math.PI * 2);
          ctx.stroke();
        }
        // Sparks radiating outward, deterministic per model id.
        const sparkCount = 10;
        for (let si = 0; si < sparkCount; si++) {
          const angle = burstRng.range(0, Math.PI * 2);
          const dist = (minDim / 320) * (14 + progress * 30) * burstRng.range(0.6, 1.2);
          ctx.fillStyle = hubColor;
          ctx.globalAlpha = Math.max(0, 0.85 * (1 - progress));
          ctx.beginPath();
          ctx.arc(x + Math.cos(angle) * dist, y + Math.sin(angle) * dist, 1.6, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.globalAlpha = 1;
      }
    }
  }

  // ── Soft vignette so the cards float on the field ─────────────────────
  const vignette = ctx.createRadialGradient(
    width * 0.5, height * 0.5, minDim * 0.35,
    width * 0.5, height * 0.5, minDim * 0.75,
  );
  vignette.addColorStop(0, "rgba(0,0,0,0)");
  vignette.addColorStop(1, mode === "night" ? "rgba(0,0,0,0.4)" : "rgba(0,0,0,0.14)");
  ctx.fillStyle = vignette;
  ctx.fillRect(0, 0, width, height);

  ctx.restore();
};

export const lineupPitchSketch = {
  name: "lineup-pitch",
  label: "Lineup pitch",
  render: renderLineupPitch,
  defaultParams: DEFAULT_LINEUP_PITCH_PARAMS,
} as const;

