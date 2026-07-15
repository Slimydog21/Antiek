/**
 * Arcade engine contract (WERNER-ACT SPR-07 subset).
 *
 * Every mini-game implements `Cartridge`. The engine owns the loop, input
 * sampling, and canvas lifecycle; games own pure rules + presentation.
 */

/** Sampled input for one fixed-timestep frame. */
export interface InputState {
  /** Pointer position in canvas CSS pixels (null if never moved). */
  pointer: { x: number; y: number } | null;
  /** True while primary button is held. */
  pointerDown: boolean;
  /** Edge: pointer just pressed this frame. */
  pointerPressed: boolean;
  /** Edge: pointer just released this frame. */
  pointerReleased: boolean;
  /** Keys currently held (KeyboardEvent.key). */
  keysDown: ReadonlySet<string>;
  /** Keys pressed this frame. */
  keysPressed: ReadonlySet<string>;
  /** Keys released this frame. */
  keysReleased: ReadonlySet<string>;
}

export interface CartridgeMeta {
  title: string;
  /** Short blurb for cabinet / wait host. */
  blurb: string;
  /** Club-Penguin style tag for discovery UI. */
  style: "club-penguin" | "zombies-arcade" | "demo";
}

export interface GameContext {
  /** Logical canvas size in CSS pixels. */
  width: number;
  height: number;
  /** Seeded RNG — same seed + same inputs → same end state. */
  rng: () => number;
  /** Optional best-score seam (no-op until save sprint). */
  saveBestScore: (score: number) => void;
  /** Read last best score if any. */
  readBestScore: () => number;
}

/**
 * A game plug-in. Call order: init → (update/render)* → teardown.
 * `update` is pure-ish: mutate cartridge-private state only.
 */
export interface Cartridge {
  readonly id: string;
  readonly meta: CartridgeMeta;
  init(ctx: GameContext): void;
  update(dtSec: number, input: InputState, ctx: GameContext): void;
  render(ctx2d: CanvasRenderingContext2D, ctx: GameContext): void;
  teardown(): void;
  /** Optional snapshot for pure-logic tests / determinism harness. */
  getScore?(): number;
  isGameOver?(): boolean;
  /** Concise nonvisual equivalent of the current game state. */
  getAccessibleStatus?(): string;
}
