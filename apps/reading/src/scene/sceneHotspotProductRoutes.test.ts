import { describe, expect, it } from "vitest";

import { productActionForSceneHotspot } from "./sceneHotspotProductRoutes";

describe("productActionForSceneHotspot", () => {
  it("maps igloo-ridge click to /arcade with highlight", () => {
    expect(productActionForSceneHotspot("igloo-ridge", "click")).toEqual({
      route: "/arcade",
      wernerExperience: "highlight",
    });
  });

  it("maps horizon-journey click to research door", () => {
    expect(productActionForSceneHotspot("horizon-journey", "click")).toEqual({
      route: "/",
      wernerExperience: "highlight",
    });
  });

  it("keeps peak-left ambient for honest shell-launch click proof", () => {
    // peak-left must remain ambient so shell-launch can prove scenery
    // activation without navigation side effects.
    expect(productActionForSceneHotspot("peak-left", "click")).toBeNull();
  });

  it("maps peak-right click to library", () => {
    expect(productActionForSceneHotspot("peak-right", "click")).toEqual({
      route: "/library",
      wernerExperience: "highlight",
    });
  });

  it("maps sky-aurora click to /home", () => {
    expect(productActionForSceneHotspot("sky-aurora", "click")).toEqual({
      route: "/home",
      wernerExperience: "highlight",
    });
  });

  it("never navigates on hover", () => {
    expect(productActionForSceneHotspot("igloo-ridge", "hover")).toBeNull();
  });
});
