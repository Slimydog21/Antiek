import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  TWIN_WRITE_SEED_KEY_PREFIX,
  buildTwinWriteHref,
  loadTwinWriteSeed,
  storeTwinWriteSeed,
} from "./twinWriteSeed";

describe("twinWriteSeed (pp)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });
  afterEach(() => {
    window.sessionStorage.clear();
  });

  it("stores and loads twin write seed", () => {
    const key = storeTwinWriteSeed({
      plain_text: "[question] Why?\n\n[insight] Because.",
      html: "<article data-twin-draft=\"true\"><p>Why?</p></article>",
      title: "Twin draft · asset · 2 note(s)",
      asset_id: "asset-1",
      note_ids: ["q1", "i1"],
    });
    expect(key).toBeTruthy();
    expect(key!.startsWith(TWIN_WRITE_SEED_KEY_PREFIX)).toBe(true);
    const loaded = loadTwinWriteSeed(key!);
    expect(loaded?.plain_text).toMatch(/\[question\] Why\?/);
    expect(loaded?.view_format).toBe("html");
    expect(loaded?.source).toBe("twin_draft_selected");
    expect(loaded?.note_ids).toEqual(["q1", "i1"]);
  });

  it("rejects empty plain_text and foreign keys", () => {
    expect(
      storeTwinWriteSeed({
        plain_text: "  ",
        html: "<p>x</p>",
        title: "t",
        asset_id: "a",
        note_ids: [],
      }),
    ).toBeNull();
    expect(loadTwinWriteSeed("evil.key")).toBeNull();
    expect(loadTwinWriteSeed(`${TWIN_WRITE_SEED_KEY_PREFIX}missing`)).toBeNull();
  });

  it("builds write handoff href", () => {
    expect(buildTwinWriteHref("antiek.twin_write_seed.abc")).toBe(
      "/write?twin_seed=antiek.twin_write_seed.abc",
    );
    expect(buildTwinWriteHref("")).toBe("/write");
  });
});
