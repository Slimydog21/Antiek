/**
 * densify: instrument helpers (bait chrome + tip→bait tension + suspension +
 * productSelector + data-werner-target + reactionBus experience map) stay public
 * on the werner barrel so product shells share the fixed-station contract
 * (cursor is bait/instrument, not a chase pet).
 */
import { describe, expect, it } from "vitest";

import {
  acquireStationInstrumentSuspension,
  ambientExperienceAfterQuiet,
  baitChromeFromFollow,
  catenaryPath,
  centerLaggedTarget,
  DEFAULT_AMBIENT_QUIET_MS,
  DEFAULT_EMOTE_DURATION_MS,
  emitWernerExperience,
  emoteDurationMs,
  emoteForExperience,
  emoteForProductDoor,
  emoteFromWernerTargetAttr,
  EMOTE_DURATION_MS,
  EMOTE_KINDS,
  FOLLOW_EASE,
  installChoreography,
  installLivingTvAmbient,
  installReactionBus,
  installTargetChoreography,
  isProductExperience,
  isStationInstrumentSuspended,
  LAG_MS,
  POINTER_IDLE_MS,
  PRODUCT_EXPERIENCES,
  productSelector,
  rodBend,
  rodBendFromPoints,
  rodLength,
  rodTipFromMascotRect,
  ROD_BUTT_LOCAL,
  ROD_HALF_BEND_DIST,
  ROD_MAX_BEND,
  ROD_TIP_LOCAL,
  SAMPLE_INTERVAL_MS,
  stationInstrumentLeaseCount,
  tipToBaitDistance,
  activityIdForPathname,
  getActivity,
  getActivityForPathname,
  getDefaultActivity,
  consumeLocallyStartedResearchSession,
  EmoteView,
  iceFishingActivity,
  listActivities,
  notifyPointerIdleEdge,
  notifyResearchPhaseEdge,
  notifyResearchStarted,
  notifyShellFailure,
  registerActivity,
  researchLensActivity,
  speakingResonanceActivity,
  useMouseFollow,
  useStationActivity,
  useStationInstrumentSuspended,
  writingNibActivity,
  WERNER_EXPERIENCE_EVENT,
  WERNER_TARGET_ATTR,
} from "./index";

describe("werner instrument barrel densify", () => {
  it("exports baitChromeFromFollow for cursor-is-bait chrome", () => {
    expect(
      baitChromeFromFollow({ live: { x: 5, y: 9 }, tabHidden: false }),
    ).toEqual({ display: "block", left: "5px", top: "9px" });
  });

  it("exports tip→bait geometry shared with the fishing line densify", () => {
    const rod = { x: 0, y: 0 };
    const bait = { x: 30, y: 40 };
    expect(tipToBaitDistance(rod, bait)).toBe(50);
    expect(rodBendFromPoints(rod, bait)).toBeGreaterThan(0);
    expect(catenaryPath(rod, bait).endsWith(" 30 40")).toBe(true);
  });

  it("exports station instrument suspension for wait-arcade pointer densify", () => {
    expect(isStationInstrumentSuspended()).toBe(false);
    const release = acquireStationInstrumentSuspension("wait-arcade");
    expect(isStationInstrumentSuspended()).toBe(true);
    expect(stationInstrumentLeaseCount()).toBeGreaterThan(0);
    release();
    expect(isStationInstrumentSuspended()).toBe(false);
  });

  it("exports productSelector + emoteForProductDoor for living-TV door densify", () => {
    // Product shells stamp data-product-id; barrel densify keeps the selector
    // + emote map public so invent doors resolve without chasing a pet.
    expect(productSelector({ productId: "home-arcade", source: "click" })).toBe(
      '[data-product-id="home-arcade"]',
    );
    expect(emoteForProductDoor("home-arcade")).toBe("curious");
    expect(emoteForProductDoor("research")).toBe("thinking");
    expect(emoteForProductDoor("midnight-oil")).toBe("sleeping");
  });

  it("exports data-werner-target densify helpers for opt-in living-TV clicks", () => {
    expect(WERNER_TARGET_ATTR).toBe("data-werner-target");
    expect(emoteFromWernerTargetAttr("curious")).toBe("curious");
    expect(emoteFromWernerTargetAttr(null)).toBe("hit");
  });

  it("exports emoteForExperience densify for living-TV product reaction map", () => {
    // Host-beat inject densify: product experiences map to living-TV emotes
    // (arcade cores stay reactionBus-free; hosts inject).
    expect(emoteForExperience("highlight")).toBe("curious");
    expect(emoteForExperience("deep_research_start")).toBe("thinking");
    expect(emoteForExperience("deep_research_complete")).toBe("happy");
    expect(emoteForExperience("deep_research_error")).toBe("dizzy");
    expect(emoteForExperience("idle")).toBe("sleeping");
    expect(emoteForExperience("fail")).toBe("dizzy");
    expect(emoteForExperience("note_saved")).toBe("noted");
    expect(emoteForExperience("piece_started")).toBe("happy");
  });

  it("exports reactionBus allowlist densify (event + isProductExperience)", () => {
    // densify: host inject path stays on a closed allowlist; unknown beats ignore.
    expect(WERNER_EXPERIENCE_EVENT).toBe("antiek:werner-experience");
    expect(PRODUCT_EXPERIENCES).toContain("piece_started");
    expect(PRODUCT_EXPERIENCES.every(isProductExperience)).toBe(true);
    expect(isProductExperience("recording_started")).toBe(false);
    expect(isProductExperience("highlight")).toBe(true);
  });

  it("exports emitWernerExperience + installReactionBus densify for host inject", () => {
    // densify: hosts inject living-TV beats; arcade cores stay reactionBus-free.
    expect(typeof emitWernerExperience).toBe("function");
    expect(typeof installReactionBus).toBe("function");
    const emote = () => {};
    const teardown = installReactionBus({ emote });
    expect(typeof teardown).toBe("function");
    teardown();
  });

  it("exports living-TV ambient densify (quiet policy + installer)", () => {
    // densify: ambient episode continuity is pure policy + installLivingTvAmbient.
    expect(DEFAULT_AMBIENT_QUIET_MS).toBe(90_000);
    expect(
      ambientExperienceAfterQuiet(
        DEFAULT_AMBIENT_QUIET_MS,
        DEFAULT_AMBIENT_QUIET_MS,
        "deep_research_complete",
      ),
    ).toBe("note_saved");
    expect(
      ambientExperienceAfterQuiet(
        DEFAULT_AMBIENT_QUIET_MS,
        DEFAULT_AMBIENT_QUIET_MS,
        "idle",
      ),
    ).toBeNull();
    expect(typeof installLivingTvAmbient).toBe("function");
  });

  it("exports emote duration densify for living-TV stage beats", () => {
    // densify: every living-TV emote kind has a positive duration for stage beats.
    expect(EMOTE_KINDS.length).toBeGreaterThan(0);
    for (const kind of EMOTE_KINDS) {
      expect(emoteDurationMs(kind)).toBeGreaterThan(0);
    }
    // densify: invent door glances pin known holds (curious/thinking/sleeping).
    expect(emoteDurationMs("curious")).toBe(1200);
    expect(emoteDurationMs("thinking")).toBe(1400);
    expect(emoteDurationMs("sleeping")).toBe(2400);
  });

  it("exports EMOTE_DURATION_MS densify table aligned with emoteDurationMs", () => {
    // densify: table is exhaustive over EMOTE_KINDS; helper reads the same map.
    expect(Object.keys(EMOTE_DURATION_MS).sort()).toEqual(
      [...EMOTE_KINDS].sort(),
    );
    for (const kind of EMOTE_KINDS) {
      expect(emoteDurationMs(kind)).toBe(EMOTE_DURATION_MS[kind]);
    }
    expect(EMOTE_DURATION_MS.happy).toBe(800);
    expect(EMOTE_DURATION_MS.hit).toBe(800);
    expect(EMOTE_DURATION_MS.noted).toBe(1000);
    expect(EMOTE_DURATION_MS.dizzy).toBe(1300);
  });

  it("exports DEFAULT_EMOTE_DURATION_MS + catenaryPath densify for line geometry", () => {
    // densify: unknown emote kinds fall back to 1000ms; catenary short path is L.
    expect(DEFAULT_EMOTE_DURATION_MS).toBe(1000);
    const short = catenaryPath({ x: 0, y: 0 }, { x: 4, y: 0 });
    expect(short.startsWith("M 0 0")).toBe(true);
    expect(short).toContain(" L ");
    const long = catenaryPath({ x: 0, y: 0 }, { x: 100, y: 0 });
    expect(long.startsWith("M 0 0")).toBe(true);
    expect(long).toContain(" Q ");
    expect(long.endsWith(" 100 0")).toBe(true);
  });

  it("exports useMouseFollow + useStationInstrumentSuspended densify hooks", () => {
    // densify: hooks stay public for cursor-is-bait follow + wait-arcade suspend.
    expect(typeof useMouseFollow).toBe("function");
    expect(typeof useStationInstrumentSuspended).toBe("function");
  });

  it("exports station activity densify for path→instrument selection", () => {
    // densify: home of the penguin routes map to station instruments (not chase).
    // Knowledge work (home + research/read) uses research-lens; settings stays ice-fishing.
    expect(activityIdForPathname("/")).toBe("research-lens");
    expect(activityIdForPathname("/library")).toBe("research-lens");
    expect(activityIdForPathname("/settings")).toBe("ice-fishing");
    expect(activityIdForPathname("/write")).toBe("writing-nib");
    expect(activityIdForPathname("/speak")).toBe("speaking-resonance");
    const activities = listActivities();
    expect(activities.length).toBeGreaterThan(0);
    expect(getDefaultActivity().id).toBe("ice-fishing");
  });

  it("exports getActivity densify resolving registered station instruments", () => {
    // densify: registry resolves path policy ids to the same activity objects.
    expect(getActivity("ice-fishing")).toBe(iceFishingActivity);
    expect(getActivity("research-lens")).toBe(researchLensActivity);
    expect(getActivityForPathname("/library")).toBe(researchLensActivity);
    expect(getActivityForPathname("/settings")).toBe(iceFishingActivity);
    expect(getActivity("not-a-real-activity" as never)).toBeUndefined();
  });

  it("exports write/speak station instruments densify for path policy", () => {
    // densify: write/speak surfaces resolve registered nib + resonance instruments.
    expect(getActivity("writing-nib")).toBe(writingNibActivity);
    expect(getActivity("speaking-resonance")).toBe(speakingResonanceActivity);
    expect(getActivityForPathname("/write")).toBe(writingNibActivity);
    expect(getActivityForPathname("/speak")).toBe(speakingResonanceActivity);
    expect(writingNibActivity.id).toBe("writing-nib");
    expect(speakingResonanceActivity.id).toBe("speaking-resonance");
  });

  it("exports registerActivity + listActivities densify for full instrument roster", () => {
    // densify: station registry lists all four instruments; register is pure API.
    const ids = listActivities().map((a) => a.id).sort();
    expect(ids).toEqual(
      [
        "ice-fishing",
        "research-lens",
        "speaking-resonance",
        "writing-nib",
      ].sort(),
    );
    expect(typeof registerActivity).toBe("function");
    expect(typeof EmoteView).toBe("function");
    expect(typeof useStationActivity).toBe("function");
  });

  it("exports shell experience signal densify for living-TV host inject edges", () => {
    // densify: pointer idle / research phase edges are pure host inject policy.
    expect(notifyPointerIdleEdge(false, false)).toBe(false);
    expect(notifyPointerIdleEdge(false, true)).toBe(true);
    expect(notifyPointerIdleEdge(true, true)).toBe(false);
    expect(notifyPointerIdleEdge(false, true, false)).toBe(false);
    expect(notifyResearchPhaseEdge("idle", "running")).toBe(false);
    expect(notifyResearchPhaseEdge("running", "complete")).toBe(true);
    expect(notifyResearchPhaseEdge("running", "error")).toBe(true);
    expect(notifyResearchPhaseEdge("complete", "idle")).toBe(false);
    expect(typeof notifyResearchStarted).toBe("function");
    expect(typeof notifyShellFailure).toBe("function");
  });

  it("exports consumeLocallyStartedResearchSession densify (one-shot launch provenance)", () => {
    // densify: local launch is one-shot; historical reopen must not replay start.
    const sessionId = "barrel-densify-research-session";
    expect(consumeLocallyStartedResearchSession(sessionId)).toBe(false);
    notifyResearchStarted(sessionId);
    expect(consumeLocallyStartedResearchSession(sessionId)).toBe(true);
    expect(consumeLocallyStartedResearchSession(sessionId)).toBe(false);
  });

  it("exports mouse-follow densify for cursor-is-bait lag contract", () => {
    // densify: ice-cursor follow lags the pointer; centerLaggedTarget is pure.
    expect(LAG_MS).toBe(500);
    expect(FOLLOW_EASE).toBe(0.75);
    expect(SAMPLE_INTERVAL_MS).toBe(60);
    expect(POINTER_IDLE_MS).toBe(2000);
    expect(centerLaggedTarget({ x: 100, y: 200 }, 64)).toEqual({
      x: 68,
      y: 168,
    });
    expect(centerLaggedTarget(null, 64)).toBeNull();
  });

  it("exports choreography install densify for living-TV product + opt-in paths", () => {
    // densify: product-activate + data-werner-target installers stay public.
    expect(typeof installChoreography).toBe("function");
    expect(typeof installTargetChoreography).toBe("function");
    const stage = {
      waddleToEl: () => {},
      emote: () => {},
    } as never;
    const teardownA = installChoreography(stage, { target: null as never });
    const teardownB = installTargetChoreography(stage, {
      target: null as never,
    });
    expect(typeof teardownA).toBe("function");
    expect(typeof teardownB).toBe("function");
    teardownA();
    teardownB();
  });

  it("exports rodBend densify for instrument tension under tip→bait load", () => {
    // densify: rod flex is monotone in tip→bait distance; rest is straight.
    expect(rodBend(0)).toBe(0);
    expect(rodBend(60)).toBeCloseTo(3, 5); // half bend at half-bend distance
    expect(rodBend(100)).toBeGreaterThan(rodBend(50));
    expect(rodBend(1e9)).toBeLessThanOrEqual(6);
  });

  it("exports rodTipFromMascotRect densify for line attach at rod tip", () => {
    // densify: fishing line leaves the real rod tip in screen space (64 viewBox).
    const rect = {
      left: 100,
      top: 200,
      width: 64,
      height: 64,
      right: 164,
      bottom: 264,
      x: 100,
      y: 200,
      toJSON: () => ({}),
    } as DOMRect;
    const tip = rodTipFromMascotRect(rect, 64);
    // Default local tip is ROD_TIP_LOCAL {x:66,y:5} at scale 1.
    expect(tip).toEqual({ x: 166, y: 205 });
    const tipScaled = rodTipFromMascotRect(rect, 128);
    expect(tipScaled).toEqual({ x: 100 + 66 * 2, y: 200 + 5 * 2 });
  });

  it("exports rodLength densify for butt→tip rig contract", () => {
    // densify: rod length is fixed viewBox butt→tip (~36 units; MAX_BEND is ~1/6).
    const len = rodLength();
    expect(len).toBeCloseTo(Math.hypot(66 - 45, 5 - 34), 5);
    expect(len).toBeGreaterThan(30);
    expect(len).toBeLessThan(40);
  });

  it("exports rod bend constants densify for saturating tension curve", () => {
    // densify: HALF_BEND_DIST = 60 mid-cast; MAX_BEND = 6 asymptotic bow.
    expect(ROD_HALF_BEND_DIST).toBe(60);
    expect(ROD_MAX_BEND).toBe(6);
    expect(rodBend(ROD_HALF_BEND_DIST)).toBeCloseTo(ROD_MAX_BEND / 2, 5);
    expect(rodBend(1e9)).toBeLessThanOrEqual(ROD_MAX_BEND);
  });

  it("exports rod local anchors densify for butt→tip rig geometry", () => {
    // densify: rod tip/butt are fixed 64-viewBox locals the rig draws against.
    expect(ROD_TIP_LOCAL).toEqual({ x: 66, y: 5 });
    expect(ROD_BUTT_LOCAL).toEqual({ x: 45, y: 34 });
    expect(rodLength()).toBeCloseTo(
      Math.hypot(
        ROD_TIP_LOCAL.x - ROD_BUTT_LOCAL.x,
        ROD_TIP_LOCAL.y - ROD_BUTT_LOCAL.y,
      ),
      5,
    );
  });
});
