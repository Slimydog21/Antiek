/**
 * notifySound.test.ts — the mute store (the audio itself is Web Audio and
 * not unit-tested; the localStorage contract is).
 */
import { beforeEach, describe, expect, it } from "vitest";

import { isSoundMuted, setSoundMuted } from "./notifySound";

describe("notifySound mute store", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("defaults to unmuted", () => {
    expect(isSoundMuted()).toBe(false);
  });

  it("setSoundMuted(true) persists and reads back", () => {
    setSoundMuted(true);
    expect(isSoundMuted()).toBe(true);
  });

  it("setSoundMuted(false) clears the flag", () => {
    setSoundMuted(true);
    setSoundMuted(false);
    expect(isSoundMuted()).toBe(false);
  });
});
