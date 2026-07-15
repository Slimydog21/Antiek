import { describe, expect, it, vi } from "vitest";

import {
  loadIceFishingBackdrop,
  type IceFishingBackdropRef,
} from "./iceFishingBackdrop";

function fakeImage(width = 960, height = 600) {
  return {
    naturalWidth: width,
    naturalHeight: height,
    onload: null,
    onerror: null,
    src: "",
  } as unknown as HTMLImageElement;
}

describe("Ice Fishing authored backdrop loader", () => {
  it("keeps the procedural fallback authoritative until exact decode succeeds", () => {
    const target: IceFishingBackdropRef = { current: null };
    const image = fakeImage();
    const onReady = vi.fn();
    const dispose = loadIceFishingBackdrop(
      "/ice-hole.webp",
      target,
      () => image,
      onReady,
    );
    expect(target.current).toBeNull();
    expect(image.src).toBe("/ice-hole.webp");
    image.onload?.(new Event("load"));
    expect(target.current).toBe(image);
    expect(onReady).toHaveBeenCalledOnce();
    dispose();
    expect(target.current).toBeNull();
  });

  it.each([
    [0, 600],
    [480, 300],
    [960, 599],
    [1586, 992],
  ])("rejects a non-runtime %d x %d plate", (width, height) => {
    const target: IceFishingBackdropRef = { current: null };
    const image = fakeImage(width, height);
    const onReady = vi.fn();
    loadIceFishingBackdrop("/ice-hole.webp", target, () => image, onReady);
    image.onload?.(new Event("load"));
    expect(target.current).toBeNull();
    expect(onReady).not.toHaveBeenCalled();
  });

  it("makes late callbacks inert after teardown", () => {
    const target: IceFishingBackdropRef = { current: null };
    const image = fakeImage();
    const dispose = loadIceFishingBackdrop(
      "/ice-hole.webp",
      target,
      () => image,
    );
    const lateLoad = image.onload;
    dispose();
    lateLoad?.call(image, new Event("load"));
    expect(target.current).toBeNull();
    expect(image.onload).toBeNull();
    expect(image.onerror).toBeNull();
  });
});
