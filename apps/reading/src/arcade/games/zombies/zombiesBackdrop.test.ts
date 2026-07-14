import { describe, expect, it, vi } from "vitest";

import { loadZombiesBackdrop, type ZombiesBackdropRef } from "./zombiesBackdrop";

function fakeImage() {
  return {
    naturalWidth: 480,
    naturalHeight: 300,
    onload: null,
    onerror: null,
    src: "",
  } as unknown as HTMLImageElement;
}

describe("Paperclip Zombies authored backdrop loader", () => {
  it("keeps fallback authority until a valid bundled image loads", () => {
    const target: ZombiesBackdropRef = { current: null };
    const image = fakeImage();
    const onReady = vi.fn();
    const dispose = loadZombiesBackdrop(
      "/field.png",
      target,
      () => image,
      onReady,
    );
    expect(target.current).toBeNull();
    expect(onReady).not.toHaveBeenCalled();
    expect(image.src).toBe("/field.png");
    image.onload?.(new Event("load"));
    expect(target.current).toBe(image);
    expect(onReady).toHaveBeenCalledTimes(1);
    dispose();
    expect(target.current).toBeNull();
  });

  it("makes load and error callbacks inert after teardown", () => {
    const target: ZombiesBackdropRef = { current: null };
    const image = fakeImage();
    const dispose = loadZombiesBackdrop("/field.png", target, () => image);
    const lateLoad = image.onload;
    const lateError = image.onerror;
    dispose();
    lateLoad?.call(image, new Event("load"));
    lateError?.call(image, new Event("error"));
    expect(target.current).toBeNull();
    expect(image.onload).toBeNull();
    expect(image.onerror).toBeNull();
  });

  it("rejects an invalid zero-size decode", () => {
    const target: ZombiesBackdropRef = { current: null };
    const image = fakeImage();
    Object.defineProperty(image, "naturalWidth", { value: 0 });
    loadZombiesBackdrop("/field.png", target, () => image);
    image.onload?.(new Event("load"));
    expect(target.current).toBeNull();
  });
});
