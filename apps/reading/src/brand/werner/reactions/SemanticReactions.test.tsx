import { readFileSync } from "node:fs";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { EMOTE_DURATION_MS, EmoteView } from "../../../werner/emotes";
import {
  WernerCurious,
  WernerDizzy,
  WernerHappy,
  WernerHit,
  WERNER_SEMANTIC_DURATION_MS,
} from ".";

const semantic = [
  ["curious", WernerCurious, "examines the evidence"],
  ["happy", WernerHappy, "marks the work verified"],
  ["dizzy", WernerDizzy, "regains his bearings"],
  ["hit", WernerHit, "bumps the control"],
] as const;

afterEach(cleanup);

describe("Werner semantic reactions", () => {
  it.each(semantic)(
    "gives %s one accessible owner",
    (kind, Reaction, label) => {
      const { container } = render(<Reaction size={64} reduced={false} />);
      expect(screen.getByRole("img", { name: new RegExp(label) })).toBeTruthy();
      expect(screen.getAllByRole("img")).toHaveLength(1);
      expect(container.querySelector("img")?.getAttribute("src")).toBeTruthy();
      expect(
        container.firstElementChild?.getAttribute("data-werner-reaction"),
      ).toBe(kind);
    },
  );

  it("pins every one-shot duration to the unchanged stage table", () => {
    expect(WERNER_SEMANTIC_DURATION_MS).toEqual({
      curious: 1200,
      happy: 800,
      dizzy: 1300,
      hit: 800,
    });
    expect(WERNER_SEMANTIC_DURATION_MS).toEqual({
      curious: EMOTE_DURATION_MS.curious,
      happy: EMOTE_DURATION_MS.happy,
      dizzy: EMOTE_DURATION_MS.dizzy,
      hit: EMOTE_DURATION_MS.hit,
    });
  });

  it("keeps happy free of the fish-bearing celebrate raster", () => {
    const { container } = render(<WernerHappy size={64} reduced={false} />);
    const src = container.querySelector("img")?.getAttribute("src") ?? "";
    expect(src).toContain("werner_default");
    expect(src).not.toContain("caught_a_fish");
  });

  it.each(semantic)("renders a motionless but meaningful %s frame", (kind) => {
    const { container } = render(<EmoteView kind={kind} size={64} reduced />);
    expect(container.firstElementChild?.getAttribute("data-reduced")).toBe(
      "true",
    );
    expect(
      container.querySelector(`[data-werner-reaction="${kind}"]`),
    ).toBeTruthy();
    const mark = container.querySelector(".werner-semantic__mark");
    const prop = container.querySelector("svg");
    expect(mark).toBeTruthy();
    expect(prop).toBeTruthy();
    expect(getComputedStyle(mark as Element).animationName).toBe("none");
    expect(getComputedStyle(prop as Element).animationName).toBe("none");
  });

  it("uses four distinct semantic compositions instead of legacy aliases", () => {
    const source = readFileSync("src/werner/emotes.tsx", "utf8");
    expect(source).toContain("<WernerCurious");
    expect(source).toContain("<WernerHappy");
    expect(source).toContain("<WernerDizzy");
    expect(source).toContain("<WernerHit");
    expect(source).not.toMatch(/<WernerCaughtAFish|<WernerTobogganSpinner/);
  });

  it("keeps the reaction layer token-native, one-shot, and authority-free", () => {
    const css = readFileSync(
      "src/brand/werner/reactions/semantic-reactions.css",
      "utf8",
    );
    const source = readFileSync(
      "src/brand/werner/reactions/SemanticReactions.tsx",
      "utf8",
    );
    expect(css).not.toMatch(/#[\da-f]{3,8}\b/i);
    const mediaGuard = css.slice(
      css.indexOf("@media (prefers-reduced-motion: reduce)"),
    );
    expect(mediaGuard).toContain("animation: none !important");
    expect(mediaGuard).toContain(".werner-semantic__evidence");
    expect(mediaGuard).toContain(".werner-semantic__stamp");
    expect(mediaGuard).toContain(".werner-semantic__orbit");
    expect(css).not.toContain("infinite");
    expect(source).not.toMatch(
      /fetch\(|localStorage|sessionStorage|useNavigate|window\.|document\.|Date\.|Math\.random|requestAnimationFrame|setTimeout|setInterval/,
    );
    expect(
      [...source.matchAll(/from "([^"]+)"/g)].map((match) => match[1]),
    ).toEqual(["react", "../../Werner"]);
  });
});
