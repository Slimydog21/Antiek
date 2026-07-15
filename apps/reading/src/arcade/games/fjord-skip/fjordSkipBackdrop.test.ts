import { describe, expect, it, vi } from "vitest";

import {
  loadFjordSkipBackdrop,
  type FjordSkipBackdropRef,
} from "./fjordSkipBackdrop";

function fakeImage(width = 960, height = 600) {
  return {
    naturalWidth: width,
    naturalHeight: height,
    onload: null,
    onerror: null,
    src: "",
  } as unknown as HTMLImageElement;
}

describe("Fjord Skip authored backdrop loader", () => {
  it("keeps the procedural fallback authoritative until exact 960 × 600 decode succeeds", () => {
    const target: FjordSkipBackdropRef = { current: null };
    const image = fakeImage();
    const onReady = vi.fn();
    const dispose = loadFjordSkipBackdrop(
      "/fjord.webp",
      target,
      () => image,
      onReady,
    );
    expect(target.current).toBeNull();
    expect(onReady).not.toHaveBeenCalled();
    expect(image.src).toBe("/fjord.webp");
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
  ])("rejects a non-runtime %d × %d plate", (width, height) => {
    const target: FjordSkipBackdropRef = { current: null };
    const image = fakeImage(width, height);
    const onReady = vi.fn();
    loadFjordSkipBackdrop("/fjord.webp", target, () => image, onReady);
    image.onload?.(new Event("load"));
    expect(target.current).toBeNull();
    expect(onReady).not.toHaveBeenCalled();
  });

  it("makes late callbacks inert after teardown", () => {
    const target: FjordSkipBackdropRef = { current: null };
    const image = fakeImage();
    const dispose = loadFjordSkipBackdrop("/fjord.webp", target, () => image);
    const lateLoad = image.onload;
    dispose();
    lateLoad?.call(image, new Event("load"));
    expect(target.current).toBeNull();
    expect(image.onload).toBeNull();
    expect(image.onerror).toBeNull();
  });

  it("makes late error callbacks inert after teardown", () => {
    const target: FjordSkipBackdropRef = { current: null };
    const image = fakeImage();
    const dispose = loadFjordSkipBackdrop("/fjord.webp", target, () => image);
    const lateError = image.onerror;
    dispose();
    lateError?.call(image, new Event("error"));
    expect(target.current).toBeNull();
    expect(image.onload).toBeNull();
    expect(image.onerror).toBeNull();
  });
});
