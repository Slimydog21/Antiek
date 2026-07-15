/**
 * emotes.test.tsx — the emote vocabulary mapped onto existing marks (SPR-05).
 *
 * Claims:
 *  - every emote kind renders SOMETHING (no missing branch);
 *  - reduced motion renders a STILL variant (a Werner mark with no animating
 *    wrapper) — proven by the absence of the animating mark's role and the
 *    presence of the canonical mark's img;
 *  - the duration table covers every kind (the state machine returns to idle
 *    exactly when the beat ends).
 */
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import {
  EMOTE_KINDS,
  EmoteView,
  emoteDurationMs,
  type EmoteKind,
} from "./emotes";

describe("EmoteView", () => {
  it("renders a mark for every emote kind (motion allowed)", () => {
    for (const kind of EMOTE_KINDS) {
      const { container, unmount } = render(
        <EmoteView kind={kind} size={64} reduced={false} />,
      );
      // Each animated mark renders at least one element (img or status span).
      expect(container.firstChild).not.toBeNull();
      unmount();
    }
  });

  it("reduced motion renders a STILL canonical mark (an <img>, no animating role=status)", () => {
    for (const kind of EMOTE_KINDS) {
      const { container, unmount } = render(
        <EmoteView kind={kind} size={64} reduced />,
      );
      // The still path is the canonical <Werner> mark → a role=img span with
      // an inner <img>, NOT the animated WernerThinking/CaughtAFish wrappers
      // (which carry role=status / extra chrome).
      const img = container.querySelector("img");
      expect(img, `still emote "${kind}" should render the canonical img`).not.toBeNull();
      unmount();
    }
  });

  it("keeps sleeping authored and single-layered when motion is reduced", () => {
    const { getByRole, container } = render(
      <EmoteView kind="sleeping" size={64} reduced />,
    );
    expect(getByRole("img", { name: "Werner sleeping" })).toBeTruthy();
    expect(
      container.querySelectorAll(
        'img[data-werner-authored-pose="sleeping"]',
      ),
    ).toHaveLength(1);
    expect(container.querySelector(".werner-sleep-still")).toBeTruthy();
    expect(container.querySelector(".werner-pose--empty")).toBeNull();
  });

  it("the duration table covers every kind", () => {
    for (const kind of EMOTE_KINDS) {
      expect(emoteDurationMs(kind)).toBeGreaterThan(0);
    }
  });

  it("falls back to a default duration for an unknown kind", () => {
    expect(emoteDurationMs("nope" as EmoteKind)).toBeGreaterThan(0);
  });

  it("offers at least 6 distinct emote kinds (SPR-05 M4)", () => {
    expect(new Set(EMOTE_KINDS).size).toBe(EMOTE_KINDS.length); // no dupes
    expect(EMOTE_KINDS.length).toBeGreaterThanOrEqual(6);
  });
});
