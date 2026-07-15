import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { EMOTE_DURATION_MS, EmoteView } from "../../../werner/emotes";
import {
  WernerCurious,
  WernerComposed,
  WernerDizzy,
  WernerHappy,
  WernerHit,
  WERNER_SEMANTIC_DURATION_MS,
} from ".";

const semantic = [
  ["curious", WernerCurious, "examines the evidence"],
  ["happy", WernerHappy, "marks the work verified"],
  ["composed", WernerComposed, "binds the research into one folio"],
  ["dizzy", WernerDizzy, "regains his bearings"],
  ["hit", WernerHit, "bumps the control"],
] as const;

afterEach(cleanup);

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return /\.[cm]?[jt]sx?$/.test(entry.name) ? [path] : [];
  });
}

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
      composed: 1500,
      dizzy: 1300,
      hit: 800,
    });
    expect(WERNER_SEMANTIC_DURATION_MS).toEqual({
      curious: EMOTE_DURATION_MS.curious,
      happy: EMOTE_DURATION_MS.happy,
      composed: EMOTE_DURATION_MS.composed,
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

  it("uses the authored head tilt only for the public curious/thinking semantic", () => {
    const curious = render(<WernerCurious size={64} reduced={false} />);
    const root = curious.container.firstElementChild;
    expect(root?.getAttribute("data-werner-mood")).toBe("thinking");
    expect(root?.getAttribute("data-duration-ms")).toBe("1200");
    expect(
      curious.container.querySelector(
        'img[data-werner-authored-pose="headTilt"]',
      ),
    ).toBeTruthy();
    expect(
      curious.container.querySelector("img")?.getAttribute("src"),
    ).toContain("werner_head_tilt");
    expect(
      curious.container.querySelector(".werner-semantic__evidence"),
    ).toBeTruthy();
    curious.unmount();

    for (const [Reaction, source] of [
      [WernerHappy, "werner_default"],
      [WernerComposed, "werner_default"],
      [WernerDizzy, "werner_lost"],
      [WernerHit, "werner_default"],
    ] as const) {
      const other = render(<Reaction size={64} reduced={false} />);
      expect(other.container.querySelector("img")?.getAttribute("src")).toContain(
        source,
      );
      expect(
        other.container.querySelector('[data-werner-authored-pose="headTilt"]'),
      ).toBeNull();
      other.unmount();
    }
  });

  it("keeps the head-tilt raster import exclusive to the private pose map", () => {
    expect(
      sourceFiles("src")
        .filter((path) => !/\.(?:test|stories)\.[cm]?[jt]sx?$/.test(path))
        .filter((path) =>
          readFileSync(path, "utf8").includes(
            "werner_head_tilt_v1_transparent.png",
          ),
        ),
    ).toEqual([join("src", "brand", "werner", "WernerAuthoredPose.tsx")]);
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
    expect(source).toContain("<WernerComposed");
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
    expect(mediaGuard).toContain(".werner-semantic__folio-cover");
    expect(mediaGuard).toContain(".werner-semantic__orbit");
    expect(css).not.toContain("infinite");
    expect(source).not.toMatch(
      /fetch\(|localStorage|sessionStorage|useNavigate|window\.|document\.|Date\.|Math\.random|requestAnimationFrame|setTimeout|setInterval/,
    );
    expect(
      [...source.matchAll(/from "([^"]+)"/g)].map((match) => match[1]),
    ).toEqual(["react", "../../Werner", "../WernerAuthoredPose"]);
  });
});
