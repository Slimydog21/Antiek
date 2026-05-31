/**
 * Ambient declaration for `pngjs`, scoped to the surface the AMS-v2 harness
 * uses (SPR-01). `pngjs` ships no bundled types and there is no @types/pngjs
 * installed (mirroring src/brand/pngjs.d.ts), so rather than add a dependency
 * we declare the tiny surface we touch: the constructor, the RGBA `data`
 * buffer, and the synchronous read/write codec. The package is already a
 * devDependency and present in node_modules.
 */
declare module "pngjs" {
  export interface PNGOptions {
    width: number;
    height: number;
  }
  export class PNG {
    constructor(options?: PNGOptions);
    width: number;
    height: number;
    /** RGBA bytes, length = width * height * 4. Writable. */
    data: Buffer;
    static sync: {
      read(buffer: Buffer): PNG;
      write(png: PNG): Buffer;
    };
  }
}
