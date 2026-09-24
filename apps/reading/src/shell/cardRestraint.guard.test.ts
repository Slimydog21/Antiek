/**
 * cardRestraint.guard.test.ts — frames the visual gate sees stay neutral.
 *
 * Design spec §4: cards and fields are flat and bounded, and the sun is spent
 * on the dock key, the one primary action and the reading mark only. The
 * editor and notebook stories drew their frames with a 2.5px sun edge and an
 * 8px hard shadow (a sun shadow at night), so every lostpixel baseline of the
 * editors showed chrome the product does not ship (critique: "Stories should
 * use the product's wrappers, not the yellow shadow-z3 frame"). The notebook's
 * slash menu, a floating island, carried the same sun edge.
 *
 * These surfaces have no render harness of their own (a story frame is only
 * a wrapper; the slash menu opens on a typed "/"), so this pins the class
 * strings: a copy of the old frame recipe fails review.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const src = join(dirname(fileURLToPath(import.meta.url)), "..");

const FRAMES = [
  "modes/Notebook/SlashMenu.tsx",
  "modes/Notebook/Editor.stories.tsx",
  "modes/Notebook/Notebook.stories.tsx",
  "modes/Write/Editor/Editor.stories.tsx",
  "modes/Write/ContextWindow/ContextWindow.stories.tsx",
  "modes/Write/Brainstorm/IdeaDump.stories.tsx",
  "shell/ProjectTree.stories.tsx",
];

describe("frames around the editors and the slash menu", () => {
  it.each(FRAMES)("%s draws no sun edge", (file) => {
    const text = readFileSync(join(src, file), "utf8");
    expect(text).not.toMatch(/\bborder-sun\b/);
  });

  it.each(FRAMES.filter((f) => f.endsWith(".stories.tsx")))(
    "%s frames the story flat, as the product does",
    (file) => {
      const text = readFileSync(join(src, file), "utf8");
      expect(text).not.toMatch(/(^|\s)(dark:)?shadow-z\d/);
    },
  );
});
