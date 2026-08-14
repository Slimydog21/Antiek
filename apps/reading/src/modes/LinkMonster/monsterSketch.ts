/**
 * Link Monster — the p5.js (Processing) furnace-stage sketch.
 *
 * Art direction: docs/specs/link-monster-art-direction.md (Krea-
 * profiled, Weirdmageddon industrial-incinerator palette). This module
 * is deliberately self-contained: it knows nothing about React, talks
 * to the page through one handle, and draws everything with p5
 * primitives (shapes, noise, additive blending) — no image assets.
 *
 * The five-beat devour sequence (paste → fly → chew → ignite →
 * absorb) is driven by `handle.feed(url)`; `handle.absorb(digest)`
 * lands the API result as a constellation node + feed card.
 *
 * Reduced-motion users get a static scene: beats collapse to an
 * instant absorb (honest: the data is never gated on the animation).
 */

import p5 from "p5";

import type { LinkDigest, MonsterPlatform } from "../../api/linkMonster";

export type MonsterPhase =
  | "idle"
  | "validating"
  | "feeding"
  | "chewing"
  | "digesting"
  | "absorbed"
  | "leftover";

export interface MonsterSketchHandle {
  /** Play the 5-beat devour sequence for a URL pellet. */
  feed(url: string): void;
  /** Land a completed digest: spawn a constellation node + flash. */
  absorb(digest: LinkDigest): void;
  /** Land a failure: leftover puff + red flash. */
  leftover(reason: string): void;
  /** Reset to ambient (idle). */
  reset(): void;
}

// ── Palette — registered design tokens (src/design/tokens.ts), not raw
//    hex: the token-lint gate (scripts/lint_tokens.ts) fails on any new
//    hardcoded colour outside the token sources. Values are byte-identical
//    to the --lm-* block in tokens.css (art-direction profile §2).
import { linkMonster as _LM } from "../../design/tokens";

const C: Record<string, [number, number, number]> = {
  skyDeep: _hex(_LM.skyDeep),
  skyMid: _hex(_LM.skyMid),
  horizon: _hex(_LM.horizon),
  fur: _hex(_LM.fur),
  furShadow: _hex(_LM.furShadow),
  rim: _hex(_LM.rim),
  fireCore: _hex(_LM.fireCore),
  fireMid: _hex(_LM.fireMid),
  fireOuter: _hex(_LM.fireOuter),
  steel: _hex(_LM.steel),
  nickel: _hex(_LM.nickel),
  node: _hex(_LM.node),
  edge: _hex(_LM.edge),
  runeGlow: _hex(_LM.runeGlow),
  runeBase: _hex(_LM.runeBase),
  ember: _hex(_LM.ember),
  voidBlack: _hex(_LM.voidBlack),
  smoke: _hex(_LM.smoke),
  magenta: _hex(_LM.magenta),
  boneWhite: _hex(_LM.boneWhite),
};

function _hex(h: string): [number, number, number] {
  const v = parseInt(h.slice(1), 16);
  return [(v >> 16) & 0xff, (v >> 8) & 0xff, v & 0xff];
}

interface Pellet {
  active: boolean;
  text: string;
  x: number;
  y: number;
  t: number; // 0..1 along the flight curve
  phase: "fly" | "chew" | "digest";
  digestingT: number;
}

interface Ember {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  maxLife: number;
  size: number;
  color: [number, number, number];
}

interface GraphNode {
  id: string;
  x: number;
  y: number;
  r: number;
  pulse: number; // 0..1 spawn flash
  label: string | null;
}

interface Rune {
  seed: number;
  x: number;
  y: number;
  size: number;
  rot: number;
  glyph: number;
}

interface SmokePuff {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  life: number;
  maxLife: number;
}

export interface MonsterSketchOptions {
  /** Canvas is decorative-by-default; the digest data lives in DOM. */
  reducedMotion?: boolean;
  onPhaseChange?: (phase: MonsterPhase) => void;
}

export function createMonsterSketch(opts: MonsterSketchOptions = {}): {
  sketch: (p: p5) => void;
  handle: MonsterSketchHandle;
} {
  const reduced = opts.reducedMotion ?? false;

  // State owned by the sketch instance (safe to close over: one p5
  // instance per page mount, one handle per instance).
  let phase: MonsterPhase = "idle";
  let pellet: Pellet = { active: false, text: "", x: 0, y: 0, t: 0, phase: "fly", digestingT: 0 };
  let embers: Ember[] = [];
  let puffs: SmokePuff[] = [];
  let nodes: GraphNode[] = [];
  let edges: Array<[number, number, number]> = []; // node idx pairs + flash age
  let runes: Rune[] = [];
  let shake = 0;
  let mouthOpen = 0; // 0 closed .. 1 open
  let fireBoost = 0;
  let leftoverText: string | null = null;
  let leftoverT = 0;
  let absorbedFlash = 0;
  let streamT = 0;
  let seed = Math.floor(Math.random() * 1e9);
  let canvasW = 800;
  let canvasH = 600;

  function setPhase(p: MonsterPhase) {
    phase = p;
    opts.onPhaseChange?.(p);
  }

  function spawnEmbers(x: number, y: number, n: number, speed = 2.5) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2;
      const v = speed * (0.4 + Math.random());
      embers.push({
        x, y,
        vx: Math.cos(a) * v,
        vy: Math.sin(a) * v - 0.6,
        life: 0,
        maxLife: 50 + Math.random() * 60,
        size: 1.5 + Math.random() * 3,
        color: Math.random() < 0.6 ? C.ember : (Math.random() < 0.5 ? C.fireMid : C.fireCore),
      });
    }
  }

  function spawnSmoke(x: number, y: number) {
    puffs.push({
      x: x + (Math.random() - 0.5) * 6,
      y,
      vx: (Math.random() - 0.5) * 0.4,
      vy: -0.7 - Math.random() * 0.4,
      r: 5 + Math.random() * 6,
      life: 0,
      maxLife: 90 + Math.random() * 60,
    });
  }

  // ── The Monster (fur body + furnace mouth + chimney) ───────────────
  function drawMonster(p: p5, mx: number, my: number, w: number, h: number) {
    // Body: heavy furry blob (cerulean, shadowed), blacklight rim.
    p.push();
    p.noStroke();
    p.fill(...C.furShadow);
    p.ellipse(mx + 6, my + 10, w, h);
    p.fill(...C.fur);
    p.ellipse(mx, my, w, h);
    // Fur texture: short strokes along the silhouette.
    p.stroke(...C.furShadow);
    p.strokeWeight(1.4);
    p.noFill();
    for (let i = 0; i < 26; i++) {
      const a = Math.PI + (i / 26) * Math.PI; // lower half
      const rr = (w / 2) * (0.96 + 0.05 * Math.sin(i * 3.7 + p.frameCount * 0.02));
      const fx = mx + Math.cos(a) * rr;
      const fy = my + Math.sin(a) * rr * 0.9 + h * 0.12;
      p.line(fx, fy, fx + 3 * Math.cos(a + 0.5), fy + 3 * Math.sin(a + 0.5) + 2);
    }
    // Blacklight rim on the upper-left edge.
    p.stroke(...C.rim);
    p.strokeWeight(2);
    p.noFill();
    p.arc(mx, my, w - 8, h - 8, Math.PI * 0.95, Math.PI * 1.55);

    // Chimney (head) + smoke-stack ears.
    p.fill(...C.steel);
    p.rect(mx - 10, my - h * 0.62, 20, h * 0.28, 2);
    p.fill(...C.nickel);
    p.rect(mx - 10, my - h * 0.66, 20, 5, 2);
    for (const ex of [mx - w * 0.36, mx + w * 0.36]) {
      p.fill(...C.furShadow);
      p.rect(ex - 5, my - h * 0.5, 10, h * 0.24, 3);
      p.fill(...C.steel);
      p.rect(ex - 7, my - h * 0.56, 14, 8, 2);
      if (Math.random() < 0.08) spawnSmoke(ex, my - h * 0.56);
    }
    if (Math.random() < 0.1) spawnSmoke(mx, my - h * 0.66);

    // Eyes: white-ish, track the pellet when one is flying.
    const target = pellet.active && pellet.phase === "fly" ? pellet : null;
    for (const ex of [mx - w * 0.18, mx + w * 0.18]) {
      const exx = ex + (target ? Math.max(-5, Math.min(5, (target.x - ex) * 0.04)) : 0);
      const eyy = my - h * 0.14 + (target ? Math.max(-3, Math.min(3, (target.y - (my - h * 0.14)) * 0.04)) : 0);
      p.noStroke();
      p.fill(240, 238, 220);
      p.ellipse(exx, eyy, w * 0.13, h * 0.17);
      p.fill(...C.voidBlack);
      p.ellipse(exx, eyy + 1, w * 0.05, h * 0.08);
      p.fill(255, 220, 120);
      p.ellipse(exx + 2, eyy, w * 0.02, h * 0.03);
    }

    // Furnace mouth: dark opening + grate teeth + fire.
    const mouthY = my + h * 0.34;
    const mouthW = w * 0.52;
    const mouthH = h * 0.22 * (0.7 + mouthOpen * 0.6);
    p.noStroke();
    p.fill(...C.voidBlack);
    p.ellipse(mx, mouthY, mouthW, mouthH);

    // Fire behind the grate (layered noise blobs; boost on chew).
    const boost = fireBoost;
    p.blendMode(p.ADD);
    p.noStroke();
    for (let layer = 0; layer < 3; layer++) {
      const colors = [C.fireCore, C.fireMid, C.fireOuter];
      const r = mouthW * (0.16 + layer * 0.14) * (1 + boost * 0.5);
      const off = p.noise(p.frameCount * 0.03 + layer * 10 + seed) * 8;
      p.fill(colors[layer][0], colors[layer][1], colors[layer][2], 160 - layer * 35);
      p.ellipse(mx + Math.sin(p.frameCount * 0.05 + layer) * 3 + off, mouthY, r * 1.6, r);
    }
    p.blendMode(p.BLEND);

    // Grate teeth (steel bars with bevel highlights; animate with
    // mouthOpen + a chew oscillation).
    const chew = phase === "chewing" ? Math.sin(p.frameCount * 0.6) : 0;
    const toothW = mouthW / 9;
    for (let i = 0; i < 9; i++) {
      const tx = mx - mouthW / 2 + toothW * i + toothW / 2;
      const gap = mouthH * (0.25 + 0.75 * mouthOpen) + Math.max(0, chew) * 3;
      const th = mouthH * 0.55;
      p.fill(...C.steel);
      p.rect(tx - toothW / 2 + 1, mouthY - gap / 2 - th, toothW - 2, th, 2);
      p.rect(tx - toothW / 2 + 1, mouthY + gap / 2, toothW - 2, th, 2);
      p.fill(...C.nickel);
      p.rect(tx - 1, mouthY - gap / 2 - th, 2, th, 1);
      p.rect(tx - 1, mouthY + gap / 2, 2, th, 1);
    }
    p.pop();
  }

  // ── Weirdmageddon sky: gradient, sigils, eye, islands ──────────────
  function drawSky(p: p5, w: number, h: number) {
    p.noStroke();
    for (let y = 0; y < h; y += 4) {
      const t = y / h;
      const col =
        t < 0.55
          ? p.lerpColor(p.color(...C.skyDeep), p.color(...C.skyMid), t / 0.55)
          : p.lerpColor(p.color(...C.skyMid), p.color(...C.horizon), (t - 0.55) / 0.45);
      col.setAlpha(255);
      p.fill(col);
      p.rect(0, y, w, 4);
    }
    // Horizon glow.
    p.blendMode(p.ADD);
    p.fill(...C.horizon, 26);
    p.ellipse(w * 0.5, h, w * 1.4, h * 0.7);
    p.blendMode(p.BLEND);

    // Sigil circles (faint rotating mandalas).
    p.noFill();
    p.stroke(...C.magenta, 14);
    for (let i = 0; i < 3; i++) {
      const r = (0.16 + i * 0.12) * w;
      p.ellipse(w * 0.5, h * 0.28, r, r);
    }

    // All-seeing eye in a triangle (pupil tracks the mouse).
    const ex = w * 0.5;
    const ey = h * 0.24;
    const s = Math.min(w, h) * 0.05 + Math.sin(p.frameCount * 0.02) * 2;
    p.noFill();
    p.stroke(...C.magenta);
    p.strokeWeight(2);
    p.triangle(ex - s, ey + s * 0.9, ex + s, ey + s * 0.9, ex, ey - s * 1.15);
    p.stroke(...C.runeGlow, 160);
    p.fill(...C.runeGlow, 26);
    p.ellipse(ex, ey, s * 0.7, s * 0.7);
    p.noStroke();
    p.fill(...C.voidBlack);
    const px = ex + Math.max(-s * 0.16, Math.min(s * 0.16, (p.mouseX - ex) * 0.02));
    const py = ey + Math.max(-s * 0.16, Math.min(s * 0.16, (p.mouseY - ey) * 0.02));
    p.ellipse(px, py, s * 0.28, s * 0.28);
  }

  function drawIslands(p: p5, w: number, h: number) {
    for (let i = 0; i < 5; i++) {
      const sx = (i * 0.23 + 0.08) * w + Math.sin(p.frameCount * 0.004 + i * 7) * 6;
      const sy = (0.34 + (i % 3) * 0.12) * h + Math.sin(p.frameCount * 0.01 + i * 3) * 3;
      const sw = (0.08 + (i % 2) * 0.04) * w;
      p.noStroke();
      p.fill(...C.skyMid, 200);
      p.beginShape();
      p.vertex(sx - sw / 2, sy);
      p.vertex(sx - sw * 0.32, sy - sw * 0.12);
      p.vertex(sx + sw * 0.1, sy - sw * 0.08);
      p.vertex(sx + sw / 2, sy);
      p.vertex(sx + sw * 0.34, sy + sw * 0.2);
      p.vertex(sx - sw * 0.2, sy + sw * 0.24);
      p.endShape(p.CLOSE);
      // Blacklight rim on the island top.
      p.stroke(...C.rim, 120);
      p.strokeWeight(1);
      p.line(sx - sw / 2, sy, sx + sw / 2, sy);
    }
  }

  // ── Rune glyphs (calligraphic bezier strokes, shimmering) ──────────
  function drawRunes(p: p5) {
    p.noFill();
    p.strokeWeight(1.6);
    for (const rn of runes) {
      const osc = Math.sin(p.frameCount * 0.03 + rn.seed) * 0.15;
      p.push();
      p.translate(rn.x + Math.sin(p.frameCount * 0.005 + rn.seed) * 4, rn.y);
      p.rotate(rn.rot + osc);
      p.stroke(...C.runeGlow, 90 + 60 * Math.abs(Math.sin(p.frameCount * 0.02 + rn.seed)));
      p.beginShape();
      const glyphs: Array<Array<[number, number]>> = [
        [[-rn.size / 2, -rn.size / 2], [rn.size / 2, -rn.size / 2], [0, rn.size / 2], [-rn.size / 2, -rn.size / 2]],
        [[-rn.size / 2, 0], [rn.size / 2, 0], [0, -rn.size / 2], [0, rn.size / 2]],
        [[0, -rn.size / 2], [rn.size / 2, 0], [0, rn.size / 2], [-rn.size / 2, 0], [0, -rn.size / 2]],
        [[-rn.size / 2, -rn.size / 2], [rn.size / 2, rn.size / 2], [-rn.size / 2, rn.size / 2], [rn.size / 2, -rn.size / 2]],
        [[-rn.size / 2, rn.size / 2], [-rn.size / 2, -rn.size / 2], [rn.size / 2, -rn.size / 2], [rn.size / 2, 0]],
      ];
      const pts = glyphs[rn.glyph % glyphs.length];
      for (const [gx, gy] of pts) p.vertex(gx, gy);
      p.endShape();
      p.pop();
    }
  }

  // ── Knowledge graph constellation ──────────────────────────────────
  function drawGraph(p: p5, w: number, h: number) {
    const gx = w * 0.68;
    const gy = h * 0.3;
    p.blendMode(p.ADD);
    p.noFill();
    // Edges.
    for (const [a, b, flash] of edges) {
      const na = nodes[a];
      const nb = nodes[b];
      if (!na || !nb) continue;
      const f = Math.max(0, 1 - flash / 40);
      p.stroke(...C.edge, 60 + 195 * f);
      p.strokeWeight(0.8 + 2.2 * f);
      p.line(na.x, na.y, nb.x, nb.y);
    }
    // Nodes.
    for (const n of nodes) {
      const pulse = Math.max(0, 1 - n.pulse / 60);
      const rr = n.r * (1 + pulse * 0.6);
      p.noStroke();
      p.fill(...C.node, 40 + 80 * pulse);
      p.ellipse(n.x, n.y, rr * 3.2, rr * 3.2); // halo
      p.fill(...C.node);
      p.ellipse(n.x, n.y, rr, rr);
      p.fill(255);
      p.ellipse(n.x, n.y, rr * 0.35, rr * 0.35);
    }
    p.blendMode(p.BLEND);
    // Cluster marker.
    p.noFill();
    p.stroke(...C.magenta, 60);
    p.strokeWeight(1);
    p.ellipse(gx, gy, w * 0.3, h * 0.34);
  }

  function ensureConstellation(w: number, h: number) {
    if (nodes.length > 0) return;
    const gx = w * 0.68;
    const gy = h * 0.3;
    for (let i = 0; i < 9; i++) {
      const a = (i / 9) * Math.PI * 2 + seed * 0.001;
      const rr = Math.min(w, h) * (0.06 + (i % 3) * 0.035);
      nodes.push({
        id: `ambient-${i}`,
        x: gx + Math.cos(a) * rr,
        y: gy + Math.sin(a) * rr * 0.8,
        r: 2.2 + (i % 3),
        pulse: 0,
        label: null,
      });
    }
    // Ambient edges (a few spokes).
    for (let i = 1; i < nodes.length; i++) edges.push([0, i, 0]);
    // Runes.
    for (let i = 0; i < 6; i++) {
      runes.push({
        seed: Math.random() * 100,
        x: (0.08 + 0.18 * i) * w,
        y: (0.12 + (i % 2) * 0.62) * h,
        size: 10 + (i % 3) * 5,
        rot: (i * 0.5) % Math.PI,
        glyph: i,
      });
    }
  }

  // ── Beats ──────────────────────────────────────────────────────────
  function handleFeed(url: string) {
    pellet = {
      active: true,
      text: url,
      x: 0,
      y: 0,
      t: 0,
      phase: "fly",
      digestingT: 0,
    };
    mouthOpen = 0.4;
    setPhase("feeding");
  }

  function handleAbsorb(digest: LinkDigest) {
    const w = canvasW;
    const h = canvasH;
    const gx = w * 0.68 + (Math.random() - 0.5) * w * 0.1;
    const gy = h * 0.3 + (Math.random() - 0.5) * h * 0.08;
    nodes.push({
      id: digest.final_url || `${Date.now()}`,
      x: gx,
      y: gy,
      r: digest.outcome === "meal" ? 4.2 : 2.6,
      pulse: 1,
      label: digest.title,
    });
    // Connect to 1-2 nearest ambient nodes.
    const idx = nodes.length - 1;
    const scored = nodes
      .map((n, i) => ({ i, d: Math.hypot(n.x - gx, n.y - gy) }))
      .filter((s) => s.i !== idx)
      .sort((a, b) => a.d - b.d);
    for (const s of scored.slice(0, 2)) edges.push([idx, s.i, 40]);
    absorbedFlash = 40;
    spawnEmbers(gx, gy, 26, 3.2);
    streamT = 0;
    setPhase("absorbed");
    if (reduced) pellet.active = false;
  }

  function handleLeftover(reason: string) {
    leftoverText = reason;
    leftoverT = 60;
    pellet.active = false;
    setPhase("leftover");
    if (reduced) leftoverText = null;
  }

  function handleReset() {
    pellet.active = false;
    setPhase("idle");
  }

  // ── The sketch ─────────────────────────────────────────────────────
  const sketch = (p: p5) => {
    p.setup = () => {
      canvasW = p.windowWidth;
      canvasH = p.windowHeight;
      const canvas = p.createCanvas(canvasW, canvasH);
      canvas.style("display", "block");
      p.noStroke();
      ensureConstellation(p.width, p.height);
      if (reduced) p.noLoop();
    };

    p.windowResized = () => {
      canvasW = p.windowWidth;
      canvasH = p.windowHeight;
      p.resizeCanvas(canvasW, canvasH);
    };

    p.draw = () => {
      const w = p.width;
      const h = p.height;
      if (reduced) {
        drawSky(p, w, h);
        drawIslands(p, w, h);
        drawRunes(p);
        drawGraph(p, w, h);
        drawMonster(p, w * 0.32, h * 0.66, w * 0.2, h * 0.3);
        return;
      }
      p.background(...C.skyDeep);
      drawSky(p, w, h);
      drawIslands(p, w, h);
      drawRunes(p);

      // Monster center-left (mouth ~40% from left, 40-70% height).
      const mx = w * 0.32;
      const my = h * 0.62;
      const mw = w * 0.21;
      const mh = h * 0.32;

      // Beats.
      if (pellet.active && pellet.phase === "fly") {
        pellet.t = Math.min(1, pellet.t + 0.012);
        const t = pellet.t;
        const sx = w * 0.5;
        const sy = h - 40;
        const exx = mx;
        const eyy = my + mh * 0.3;
        // Bezier arc from the paste bar to the mouth.
        const bx = p.bezierPoint(sx, sx + (exx - sx) * 0.4, exx + (sx - exx) * 0.2, exx, t);
        const by = p.bezierPoint(sy, sy - h * 0.25, eyy - h * 0.12, eyy, t);
        pellet.x = bx;
        pellet.y = by;
        spawnEmbers(bx, by, 1, 1.4);
        if (t >= 1) {
          pellet.phase = "chew";
          setPhase("chewing");
          fireBoost = 1;
          shake = 12;
          spawnEmbers(mx, eyy, 30, 4);
        }
      } else if (pellet.active && pellet.phase === "chew") {
        mouthOpen = Math.max(0, mouthOpen - 0.05);
        fireBoost = Math.max(0, fireBoost - 0.02);
        shake = Math.max(0, shake - 0.4);
        if (Math.random() < 0.5) spawnEmbers(mx + (Math.random() - 0.5) * mw * 0.5, my + mh * 0.3, 2, 2.2);
        if (fireBoost <= 0.02) {
          pellet.phase = "digest";
          setPhase("digesting");
          streamT = 60;
        }
      } else if (pellet.active && pellet.phase === "digest") {
        // Digest ember stream toward the constellation.
        streamT -= 1;
        const gx = w * 0.68;
        const gy = h * 0.3;
        const srcX = mx;
        const srcY = my + mh * 0.3;
        for (let i = 0; i < 3; i++) {
          const t = Math.random();
          const bx = p.bezierPoint(srcX, srcX + 40, gx - 40, gx, t);
          const by = p.bezierPoint(srcY, srcY - h * 0.2, gy + h * 0.1, gy, t);
          spawnEmbers(bx, by, 1, 2.8);
        }
        if (streamT <= 0) pellet.active = false;
      }

      // Ambient ember/smoke decay.
      embers = embers.filter((e) => e.life < e.maxLife);
      p.blendMode(p.ADD);
      p.noStroke();
      for (const e of embers) {
        e.life += 1;
        e.x += e.vx;
        e.y += e.vy;
        e.vy *= 0.99;
        const fade = 1 - e.life / e.maxLife;
        p.fill(e.color[0], e.color[1], e.color[2], 200 * fade);
        p.ellipse(e.x, e.y, e.size * 2, e.size * 2);
      }
      p.blendMode(p.BLEND);
      puffs = puffs.filter((s) => s.life < s.maxLife);
      for (const s of puffs) {
        s.life += 1;
        s.x += s.vx + p.noise(s.life * 0.02 + s.x) * 0.3;
        s.y += s.vy;
        s.r += 0.08;
        p.noStroke();
        p.fill(...C.smoke, 90 * (1 - s.life / s.maxLife));
        p.ellipse(s.x, s.y, s.r * 2, s.r * 2);
      }

      // Leftover puff.
      if (leftoverText && leftoverT > 0) {
        leftoverT -= 1;
        spawnEmbers(mx, my + mh * 0.3, 2, 1.6);
        if (leftoverT <= 0) leftoverText = null;
      }

      // Node pulse decay + absorbed flash.
      for (const n of nodes) if (n.pulse > 0) n.pulse -= 0.6;
      for (const e of edges) if (e[2] > 0) e[2] -= 1;
      absorbedFlash = Math.max(0, absorbedFlash - 1);

      // Screen shake during the chew.
      p.push();
      if (shake > 0) p.translate((Math.random() - 0.5) * shake, (Math.random() - 0.5) * shake);

      drawGraph(p, w, h);
      drawMonster(p, mx, my, mw, mh);
      p.pop();

      // The pellet (the URL being eaten).
      if (pellet.active && pellet.phase === "fly") {
        p.push();
        p.noStroke();
        p.fill(...C.voidBlack, 220);
        p.rect(pellet.x - 40, pellet.y - 9, 80, 18, 4);
        p.stroke(...C.ember);
        p.strokeWeight(1);
        p.noFill();
        p.rect(pellet.x - 40, pellet.y - 9, 80, 18, 4);
        p.noStroke();
        p.fill(...C.ember);
        p.textAlign(p.CENTER, p.CENTER);
        p.textSize(9);
        p.textFont("Share Tech Mono, monospace");
        p.text(pellet.text.length > 34 ? pellet.text.slice(0, 33) + "…" : pellet.text, pellet.x, pellet.y);
        p.pop();
      }

      mouthOpen = p.lerp(mouthOpen, phase === "idle" || phase === "feeding" ? 0.35 : 0.15, 0.02);
    };
  };

  return {
    sketch,
    handle: {
      feed: handleFeed,
      absorb: handleAbsorb,
      leftover: handleLeftover,
      reset: handleReset,
    },
  };
}

/** Platform chip label/color hints for the DOM feed (not canvas). */
export const PLATFORM_META: Record<MonsterPlatform, { label: string; glyph: string }> = {
  youtube: { label: "YouTube", glyph: "▶" },
  x: { label: "X", glyph: "𝕏" },
  instagram: { label: "Instagram", glyph: "◉" },
  tiktok: { label: "TikTok", glyph: "♪" },
  substack: { label: "Substack", glyph: "✉" },
  generic: { label: "Web", glyph: "◎" },
};
