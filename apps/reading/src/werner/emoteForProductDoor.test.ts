import { describe, expect, it } from "vitest";

import { emoteForProductDoor } from "./choreography";

describe("emoteForProductDoor", () => {
  it("maps research to thinking", () => {
    expect(emoteForProductDoor("research")).toBe("thinking");
  });
  it("maps read and speak to curious", () => {
    expect(emoteForProductDoor("read")).toBe("curious");
    expect(emoteForProductDoor("speak")).toBe("curious");
  });
  it("maps write and home to happy", () => {
    expect(emoteForProductDoor("write")).toBe("happy");
    expect(emoteForProductDoor("home")).toBe("happy");
  });
  it("maps more to noted", () => {
    expect(emoteForProductDoor("more")).toBe("noted");
  });
  it("defaults unknown products to hit", () => {
    expect(emoteForProductDoor("settings")).toBe("hit");
    expect(emoteForProductDoor("")).toBe("hit");
  });
});
