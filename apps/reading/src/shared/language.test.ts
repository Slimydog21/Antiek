import { describe, expect, it } from "vitest";

import { BANNED_PATTERNS } from "./language";

function rule(id: string): RegExp {
  const found = BANNED_PATTERNS.find((pattern) => pattern.id === id);
  if (!found) throw new Error(`missing banned pattern: ${id}`);
  found.pattern.lastIndex = 0;
  return found.pattern;
}

describe("language banned patterns", () => {
  it("catches short and long raw investigation ids", () => {
    expect("Open inv-abc next".match(rule("inv-id"))).toEqual(["inv-abc"]);
    expect("Open inv-123abc456def next".match(rule("inv-id"))).toEqual([
      "inv-123abc456def",
    ]);
  });

  it("catches bracketed and bare chunk counts", () => {
    expect("[3 chunks]".match(rule("n-chunks"))).toEqual(["[3 chunks]"]);
    expect("Cited 5 chunks".match(rule("n-chunks"))).toEqual(["5 chunks"]);
    expect("Cited 1 chunk".match(rule("n-chunks"))).toBeNull();
  });

  it("catches bracketed and bare claim counts", () => {
    expect("[2 claims]".match(rule("n-claims"))).toEqual(["[2 claims]"]);
    expect("Found 4 claims".match(rule("n-claims"))).toEqual(["4 claims"]);
    expect("Found 1 claim".match(rule("n-claims"))).toBeNull();
  });

  it("catches short raw chunk ids", () => {
    expect("Preview chunk-9".match(rule("chunk-id"))).toEqual(["chunk-9"]);
    expect("Preview chunk-abcd".match(rule("chunk-id"))).toEqual(["chunk-abcd"]);
    expect("data-akb-chunk-id".match(rule("chunk-id"))).toBeNull();
  });
});
