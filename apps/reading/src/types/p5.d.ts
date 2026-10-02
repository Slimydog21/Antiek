/**
 * p5 2.3.3 advertises `types/p5.d.ts` in its package exports but does not
 * publish that file. The old DefinitelyTyped package described p5 1.x and
 * shadowed the advertised 2.x contract, so keep the contract local to the
 * API this app uses until upstream ships its missing declaration.
 */

declare module "p5" {
  export type P5BlendMode = object;

  export interface P5Color {
    setAlpha(alpha: number): void;
  }

  interface P5Element {
    style(property: string, value: string): void;
  }

  export default class P5 {
    setup: (() => void) | undefined;
    draw: (() => void) | undefined;
    windowResized: (() => void) | undefined;

    readonly ADD: P5BlendMode;
    readonly BLEND: P5BlendMode;
    readonly CENTER: unknown;
    readonly CLOSE: unknown;

    frameCount: number;
    height: number;
    mouseX: number;
    mouseY: number;
    width: number;
    windowHeight: number;
    windowWidth: number;

    arc(
      x: number,
      y: number,
      width: number,
      height: number,
      startAngle: number,
      stopAngle: number,
    ): void;
    background(...color: (number | P5Color)[]): void;
    beginShape(): void;
    bezierPoint(a: number, b: number, c: number, d: number, t: number): number;
    blendMode(mode: P5BlendMode): void;
    color(...color: number[]): P5Color;
    createCanvas(width: number, height: number): P5Element;
    ellipse(x: number, y: number, width: number, height?: number): void;
    endShape(mode?: unknown): void;
    fill(...color: (number | P5Color)[]): void;
    lerp(start: number, stop: number, amount: number): number;
    lerpColor(from: P5Color, to: P5Color, amount: number): P5Color;
    line(x1: number, y1: number, x2: number, y2: number): void;
    noFill(): void;
    noLoop(): void;
    noStroke(): void;
    noise(x: number, y?: number, z?: number): number;
    pop(): void;
    push(): void;
    rect(
      x: number,
      y: number,
      width: number,
      height: number,
      cornerRadius?: number,
    ): void;
    resizeCanvas(width: number, height: number): void;
    rotate(angle: number): void;
    stroke(...color: (number | P5Color)[]): void;
    strokeWeight(weight: number): void;
    text(content: string, x: number, y: number): void;
    textAlign(alignX: unknown, alignY?: unknown): void;
    textFont(font: string): void;
    textSize(size: number): void;
    translate(x: number, y: number): void;
    triangle(
      x1: number,
      y1: number,
      x2: number,
      y2: number,
      x3: number,
      y3: number,
    ): void;
    vertex(x: number, y: number): void;
    remove(): void;

    constructor(sketch: (instance: P5) => void, parentNode?: HTMLElement);
  }
}
