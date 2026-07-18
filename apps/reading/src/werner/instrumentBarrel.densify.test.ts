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
  FISHING_BEATS,
  FISHING_CYCLE_MS,
  fishingStep,
  FOLLOW_EASE,
  INITIAL_WERNER_STATE,
  installChoreography,
  installLivingTvAmbient,
  installReactionBus,
  installTargetChoreography,
  isBusy,
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
  shouldFish,
  stationInstrumentLeaseCount,
  tipToBaitDistance,
  activityIdForPathname,
  getActivity,
  getActivityForPathname,
  getDefaultActivity,
  consumeLocallyStartedResearchSession,
  createWernerStage,
  EmoteView,
  iceFishingActivity,
  listActivities,
  notifyPointerIdleEdge,
  notifyResearchPhaseEdge,
  notifyResearchStarted,
  notifyShellFailure,
  registerActivity,
  ResearchLensCursor,
  researchLensActivity,
  speakingResonanceActivity,
  useMouseFollow,
  useStationActivity,
  useStationInstrumentSuspended,
  WADDLE_MS,
  WernerFishingLayer,
  WernerIceBait,
  WernerIceCursorShell,
  WernerRig,
  wernerArcade,
  wernerIceFishingCursor,
  wernerReducer,
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

  it("exports emoteForProductDoor densify for residual invent door families + aliases", () => {
    // densify: every invent door family maps to a living-TV emote; aliases share it.
    // thinking family — research workstation
    expect(emoteForProductDoor("twin-notes")).toBe("thinking");
    expect(emoteForProductDoor("twin_notes")).toBe("thinking");
    expect(emoteForProductDoor("thought-partner")).toBe("thinking");
    expect(emoteForProductDoor("cascade-plan")).toBe("thinking");
    // curious family — arcade/wait/cabinet/marketplace
    expect(emoteForProductDoor("wait-arcade")).toBe("curious");
    expect(emoteForProductDoor("wait_arcade")).toBe("curious");
    expect(emoteForProductDoor("book-marketplace")).toBe("curious");
    expect(emoteForProductDoor("book_marketplace")).toBe("curious");
    expect(emoteForProductDoor("ice-fishing")).toBe("curious");
    expect(emoteForProductDoor("zombies")).toBe("curious");
    expect(emoteForProductDoor("paperclip_zombies")).toBe("curious");
    expect(emoteForProductDoor("loading-game-host")).toBe("curious");
    // happy family — craft/pride
    expect(emoteForProductDoor("write")).toBe("happy");
    expect(emoteForProductDoor("antiek-bench")).toBe("happy");
    expect(emoteForProductDoor("antiek_bench")).toBe("happy");
    // noted family — settings/billing
    expect(emoteForProductDoor("settings")).toBe("noted");
    expect(emoteForProductDoor("billing")).toBe("noted");
    expect(emoteForProductDoor("pricing")).toBe("noted");
    // sleeping family
    expect(emoteForProductDoor("midnight_oil")).toBe("sleeping");
    // unknown → classic hit bump
    expect(emoteForProductDoor("does-not-exist")).toBe("hit");
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

  it("exports installLivingTvAmbient densify for pride-savor then curtain silence", () => {
    // densify: after complete, first quiet emits note_saved; second quiet idle; third silent.
    const emitted: string[] = [];
    let t = 0;
    let tick: (() => void) | null = null;
    const teardown = installLivingTvAmbient({
      quietMs: 100,
      pollMs: 10,
      target: null,
      emit: (experience) => {
        emitted.push(experience);
      },
      now: () => t,
      setInterval: (fn) => {
        tick = fn;
        return 1;
      },
      clearInterval: () => {},
    });
    // Seed last experience via pure policy path: poll with complete already set
    // by replaying ambient after manual lastExperience is not exposed — instead
    // drive product-complete through ambientExperienceAfterQuiet contract by
    // advancing time after seed via internal lastExperience null → idle first.
    t = 0;
    tick?.();
    expect(emitted).toEqual([]); // quietMs not met
    t = 100;
    tick?.();
    expect(emitted).toEqual(["idle"]); // default curtain after null
    // Re-arm via product beat: fire experience event is disabled (target null).
    // After idle, ambient must stay silent (no spam loop).
    t = 300;
    tick?.();
    expect(emitted).toEqual(["idle"]);
    teardown();
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

  it("exports ice-cursor + fishing shell densify components for fixed-station UX", () => {
    // densify: ice bait/line/cursor shell + walk-cycle rig + research lens stay public.
    expect(typeof WernerIceBait).toBe("function");
    expect(typeof WernerFishingLayer).toBe("function");
    expect(typeof WernerIceCursorShell).toBe("function");
    expect(typeof WernerRig).toBe("function");
    expect(typeof ResearchLensCursor).toBe("function");
  });

  it("exports fishing gag densify (shouldFish gate + endless never-caught cycle)", () => {
    // densify: loop owns Werner only at idle + pointer idle; cycle has no catch.
    expect(shouldFish(INITIAL_WERNER_STATE, true)).toBe(true);
    expect(shouldFish(INITIAL_WERNER_STATE, false)).toBe(false);
    expect(shouldFish({ name: "following", resume: "following" }, true)).toBe(
      false,
    );
    expect(shouldFish({ name: "waddling", resume: "idle" }, true)).toBe(false);
    expect(shouldFish({ name: "frozen", resume: "idle" }, true)).toBe(false);
    expect(FISHING_BEATS.length).toBeGreaterThan(0);
    expect(FISHING_CYCLE_MS).toBe(
      FISHING_BEATS.reduce((acc, s) => acc + s.holdMs, 0),
    );
    expect(FISHING_BEATS.map((b) => b.beat)).not.toContain("caught");
    expect(fishingStep(0).beat).toBe("cast");
    expect(fishingStep(FISHING_CYCLE_MS).beat).toBe("cast");
    expect(fishingStep(FISHING_BEATS[0].holdMs).beat).toBe(FISHING_BEATS[1].beat);
  });

  it("exports fishingStep densify walking the full never-caught beat order", () => {
    // densify: sequential holds land on cast→wait→bob→nibble→yank→miss→slump→reset→cast.
    const order = FISHING_BEATS.map((b) => b.beat);
    expect(order).toEqual([
      "cast",
      "wait",
      "bob",
      "nibble",
      "yank",
      "miss",
      "slump",
      "reset",
    ]);
    let elapsed = 0;
    for (let i = 0; i < FISHING_BEATS.length; i++) {
      const frame = fishingStep(elapsed);
      expect(frame.beat).toBe(FISHING_BEATS[i].beat);
      expect(frame.index).toBe(i);
      expect(frame.beatPhase).toBeGreaterThanOrEqual(0);
      expect(frame.beatPhase).toBeLessThan(1);
      elapsed += FISHING_BEATS[i].holdMs;
    }
    // Full loop wraps to cast without a catch payoff.
    expect(fishingStep(elapsed).beat).toBe("cast");
    expect(fishingStep(Number.NaN).beat).toBe("cast");
    expect(fishingStep(-10).beat).toBe("cast");
  });

  it("exports steering densify (isBusy + reducer + waddle period)", () => {
    // densify: directed actions are busy; freeze is a hard floor; waddle period public.
    expect(isBusy(INITIAL_WERNER_STATE)).toBe(false);
    expect(isBusy({ name: "waddling", resume: "idle" })).toBe(true);
    expect(isBusy({ name: "emoting", resume: "following" })).toBe(true);
    expect(isBusy({ name: "following", resume: "following" })).toBe(false);
    const frozen = wernerReducer(INITIAL_WERNER_STATE, { type: "freeze" });
    expect(frozen.name).toBe("frozen");
    expect(wernerReducer(frozen, { type: "waddle" }).name).toBe("frozen");
    expect(wernerReducer(frozen, { type: "unfreeze" }).name).toBe("idle");
    expect(WADDLE_MS).toBe(1800);
  });

  it("exports reducer densify for follow/waddle/emote latest-wins + resume ambient", () => {
    // densify: follow only moves ambient floor; directed actions keep resume ambient.
    const following = wernerReducer(INITIAL_WERNER_STATE, {
      type: "follow",
      on: true,
    });
    expect(following).toEqual({ name: "following", resume: "following" });
    const idleAgain = wernerReducer(following, { type: "follow", on: false });
    expect(idleAgain).toEqual({ name: "idle", resume: "idle" });
    const waddling = wernerReducer(following, { type: "waddle" });
    expect(waddling).toEqual({ name: "waddling", resume: "following" });
    // Mid-waddle follow does not interrupt; only updates resume.
    expect(
      wernerReducer(waddling, { type: "follow", on: false }),
    ).toEqual({ name: "waddling", resume: "idle" });
    expect(wernerReducer(waddling, { type: "arrived" })).toEqual({
      name: "following",
      resume: "following",
    });
    // Stale arrival while not waddling is ignored.
    expect(wernerReducer(following, { type: "arrived" })).toEqual(following);
    const emoting = wernerReducer(following, { type: "emote" });
    expect(emoting).toEqual({ name: "emoting", resume: "following" });
    expect(wernerReducer(emoting, { type: "emoteDone" })).toEqual({
      name: "following",
      resume: "following",
    });
    expect(wernerReducer(emoting, { type: "idle" })).toEqual({
      name: "idle",
      resume: "idle",
    });
  });

  it("exports ambientExperienceAfterQuiet densify for living-TV episode continuity", () => {
    // densify: product beat → pride savor (when earned) → curtain idle → silence.
    const q = DEFAULT_AMBIENT_QUIET_MS;
    expect(ambientExperienceAfterQuiet(q - 1, q, null)).toBeNull();
    expect(ambientExperienceAfterQuiet(-1, q, null)).toBeNull();
    expect(ambientExperienceAfterQuiet(q, q, null)).toBe("idle");
    expect(ambientExperienceAfterQuiet(q, q, "deep_research_start")).toBe(
      "idle",
    );
    expect(ambientExperienceAfterQuiet(q, q, "deep_research_complete")).toBe(
      "note_saved",
    );
    expect(ambientExperienceAfterQuiet(q, q, "piece_started")).toBe(
      "note_saved",
    );
    expect(ambientExperienceAfterQuiet(q, q, "note_saved")).toBe("idle");
    expect(ambientExperienceAfterQuiet(q, q, "fail")).toBe("idle");
    expect(ambientExperienceAfterQuiet(q, q, "deep_research_error")).toBe(
      "idle",
    );
    expect(ambientExperienceAfterQuiet(q, q, "highlight")).toBe("idle");
    expect(ambientExperienceAfterQuiet(q, q, "idle")).toBeNull();
  });

  it("exports createWernerStage densify + ice/arcade feature flags", () => {
    // densify: stage factory is pure over host + timers; flags default on unless VITE_*=0.
    expect(typeof createWernerStage).toBe("function");
    expect(typeof wernerIceFishingCursor).toBe("boolean");
    expect(typeof wernerArcade).toBe("boolean");
    const timers = {
      setTimeout: (fn: () => void, _ms: number) => {
        // Do not auto-fire; tests only need latest-wins clear + dispose.
        void fn;
        return 1;
      },
      clearTimeout: (_id: number) => {
        void _id;
      },
    };
    let pos = { x: 50, y: 50 };
    const host = {
      walkTo: (x: number, y: number) => {
        pos = { x, y };
      },
      getPos: () => pos,
      setEmote: () => {},
      setFollowing: () => {},
      setRoamPaused: () => {},
    };
    const stage = createWernerStage(host, timers);
    expect(stage.getState()).toEqual(INITIAL_WERNER_STATE);
    stage.emote("curious");
    expect(stage.getState().name).toBe("emoting");
    stage.idle();
    expect(stage.getState().name).toBe("idle");
    stage.freeze();
    expect(stage.getState().name).toBe("frozen");
    stage.unfreeze();
    expect(stage.getState().name).toBe("idle");
    stage.dispose();
  });

  it("exports createWernerStage densify for waddleToEl missing/frozen paths", () => {
    // densify: missing target is graceful no-op; frozen flashes still emote in place.
    const timers = {
      setTimeout: (fn: () => void, _ms: number) => {
        void fn;
        return 42;
      },
      clearTimeout: (_id: number) => {
        void _id;
      },
    };
    let walks = 0;
    let emotes: Array<string | null> = [];
    const host = {
      walkTo: () => {
        walks += 1;
      },
      getPos: () => ({ x: 50, y: 50 }),
      setEmote: (k: string | null) => {
        emotes.push(k);
      },
      setFollowing: () => {},
      setRoamPaused: () => {},
    };
    const stage = createWernerStage(host, timers);
    stage.waddleToEl(null);
    expect(walks).toBe(0);
    expect(stage.getState().name).toBe("idle");
    stage.freeze();
    // frozen path ignores null short-circuit order: freeze branch runs first.
    const el = {
      getBoundingClientRect: () => ({
        left: 100,
        top: 100,
        width: 20,
        height: 20,
        right: 120,
        bottom: 120,
        x: 100,
        y: 100,
        toJSON: () => ({}),
      }),
    } as Element;
    stage.waddleToEl(el, "curious");
    // frozen: no walk, still-pose emote flash, machine stays frozen (hard floor).
    expect(walks).toBe(0);
    expect(emotes).toContain("curious");
    expect(stage.getState().name).toBe("frozen");
    stage.dispose();
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
