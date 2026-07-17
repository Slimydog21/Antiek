import { describe, expect, it } from "vitest";

import { emoteForProductDoor } from "./choreography";

describe("emoteForProductDoor", () => {
  it("maps research-family doors to thinking", () => {
    expect(emoteForProductDoor("research")).toBe("thinking");
    expect(emoteForProductDoor("library")).toBe("thinking");
    expect(emoteForProductDoor("investigations")).toBe("thinking");
    expect(emoteForProductDoor("documents")).toBe("thinking");
    expect(emoteForProductDoor("notebooks")).toBe("thinking");
    expect(emoteForProductDoor("twin-notes")).toBe("thinking");
    expect(emoteForProductDoor("thought-partner")).toBe("thinking");
    expect(emoteForProductDoor("brainstorm")).toBe("thinking");
    expect(emoteForProductDoor("cascade-plan")).toBe("thinking");
  });
  it("maps read, speak, arcade, sources to curious", () => {
    expect(emoteForProductDoor("read")).toBe("curious");
    expect(emoteForProductDoor("speak")).toBe("curious");
    expect(emoteForProductDoor("arcade")).toBe("curious");
    expect(emoteForProductDoor("sources")).toBe("curious");
    expect(emoteForProductDoor("marketplace")).toBe("curious");
    expect(emoteForProductDoor("model-decision")).toBe("curious");
    expect(emoteForProductDoor("wait-arcade")).toBe("curious");
    expect(emoteForProductDoor("research-wait")).toBe("curious");
  });
  it("maps write, home, create to happy", () => {
    expect(emoteForProductDoor("write")).toBe("happy");
    expect(emoteForProductDoor("home")).toBe("happy");
    expect(emoteForProductDoor("create")).toBe("happy");
    expect(emoteForProductDoor("antiek-bench")).toBe("happy");
  });
  it("maps more/settings/billing/pricing to noted", () => {
    expect(emoteForProductDoor("more")).toBe("noted");
    expect(emoteForProductDoor("settings")).toBe("noted");
    expect(emoteForProductDoor("billing")).toBe("noted");
    expect(emoteForProductDoor("pricing")).toBe("noted");
  });
  it("maps midnight oil to sleeping", () => {
    expect(emoteForProductDoor("midnight-oil")).toBe("sleeping");
    expect(emoteForProductDoor("midnight_oil")).toBe("sleeping");
  });
  it("defaults unknown products to hit", () => {
    expect(emoteForProductDoor("unknown-door")).toBe("hit");
    expect(emoteForProductDoor("")).toBe("hit");
  });
});
