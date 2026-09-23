import { describe, expect, it } from "vitest";

import { entryScriptFromIndexHtml, resolveChunk } from "./bundle_budget";

// Shape of the real build: a 3 KB lazy `index-*.js` (AccountMemory/index.tsx)
// sorts before the entry.
const ASSETS = ["index-B2EeBPbh.js", "index-DnkfI94J.js", "lemon-BtnCMPug.js", "index-CPQ.css"];
const HTML =
  '<html><head><script type="module" crossorigin src="/assets/index-DnkfI94J.js"></script>' +
  '<link rel="modulepreload" crossorigin href="/assets/lemon-BtnCMPug.js"></head></html>';
const INDEX = { chunk: "index", maxBytes: 700_000, entry: true };
const LEMON = { chunk: "lemon", maxBytes: 60_000 };

describe("entryScriptFromIndexHtml", () => {
  it("returns the module script's basename", () => {
    expect(entryScriptFromIndexHtml(HTML)).toBe("index-DnkfI94J.js");
  });

  it("ignores classic scripts and modulepreload links", () => {
    const html =
      '<script src="/assets/legacy-1.js"></script>' +
      '<link rel="modulepreload" href="/assets/index-B2EeBPbh.js">' +
      '<script crossorigin type="module" src="/assets/index-DnkfI94J.js?v=1"></script>';
    expect(entryScriptFromIndexHtml(html)).toBe("index-DnkfI94J.js");
  });

  it("returns null when there is no module script", () => {
    expect(entryScriptFromIndexHtml("<html></html>")).toBeNull();
  });
});

describe("resolveChunk", () => {
  it("budgets the entry index.html loads, not the first or largest index-*.js", () => {
    expect(resolveChunk(INDEX, ASSETS, HTML)).toEqual({ file: "index-DnkfI94J.js" });
    // The entry listed last and the lazy chunk first must not change the answer.
    expect(resolveChunk(INDEX, [...ASSETS].reverse(), HTML)).toEqual({
      file: "index-DnkfI94J.js",
    });
    const lazyNamedEntry = HTML.replace("index-DnkfI94J.js", "index-B2EeBPbh.js");
    expect(resolveChunk(INDEX, ASSETS, lazyNamedEntry)).toEqual({ file: "index-B2EeBPbh.js" });
  });

  it("fails the entry budget when index.html is missing or names nothing", () => {
    expect(resolveChunk(INDEX, ASSETS, null)).toHaveProperty("error");
    expect(resolveChunk(INDEX, ASSETS, "<html></html>")).toHaveProperty("error");
  });

  it("fails the entry budget when index.html loads a file the prefix does not match", () => {
    const renamed = HTML.replace("index-DnkfI94J.js", "main-Z.js");
    expect(resolveChunk(INDEX, [...ASSETS, "main-Z.js"], renamed)).toHaveProperty("error");
  });

  it("resolves a uniquely named chunk by prefix", () => {
    expect(resolveChunk(LEMON, ASSETS, HTML)).toEqual({ file: "lemon-BtnCMPug.js" });
  });

  it("fails rather than guesses when a prefix matches several chunks", () => {
    const r = resolveChunk(LEMON, [...ASSETS, "lemon-Second.js"], HTML);
    expect(r).toHaveProperty("error");
    expect("error" in r && r.error).toContain("2 chunks match");
  });

  it("fails when nothing matches", () => {
    expect(resolveChunk(LEMON, ["index-DnkfI94J.js"], HTML)).toHaveProperty("error");
  });
});
