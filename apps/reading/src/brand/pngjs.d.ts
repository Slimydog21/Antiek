/**
 * Minimal ambient declaration for `pngjs`, scoped to the synchronous PNG
 * decode that WernerLogoTransparency.test.ts uses (SPR-12 M4). `pngjs` has
 * no bundled types and there is no @types/pngjs installed; rather than add
 * a dependency just to satisfy the type-checker for a single test, we
 * declare the tiny surface we touch. The package is already present in
 * node_modules (a stable, widely-used pure-JS PNG codec).
 */
declare module "pngjs" {
  export class PNG {
    width: number;
    height: number;
    /** RGBA bytes, length = width * height * 4. */
    data: Buffer;
    static sync: {
      read(buffer: Buffer): PNG;
    };
  }
}
