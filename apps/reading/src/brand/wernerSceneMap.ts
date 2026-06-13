/**
 * wernerSceneMap.ts — Werner's scene reactivity, as a pure function (ALC SPR-07 M1).
 *
 * Werner stands in the living scene (SPR-05 beautiful + SPR-06 alive) but until
 * now ignored the weather around him: the same idle pose at high noon and at
 * midnight in a blizzard. CHARACTER means he NOTICES where he is. This file is
 * the single source of truth for "given the scene's mood, which sanctioned
 * Werner pose fits the weather he's standing in" — nothing more.
 *
 * ─── HARD CONSTRAINTS (the SPR-07 firewall + restraint guard) ────────────────
 *
 *  1. PURE. `wernerForScene(mood)` is a total function SceneMood → WernerSceneCue.
 *     No Math.random, no Date.now, no DOM read, no clock. The same scene_key
 *     ALWAYS yields the same cue (byte-stable across re-renders — the
 *     determinism gate double-renders and diffs). Reactivity flows from the
 *     scene state alone; there is no hidden state to drift.
 *
 *  2. EXHAUSTIVE. There is a cue for EVERY one of the eight SceneMood states
 *     (4 dayParts × 2 weathers). The table is keyed on the SceneMood scene_key
 *     (`${dayPart}|${weather}`), the SAME key the scene art + procedural RNG
 *     seed on (mood.ts moodKey), so Werner and the sky can never disagree about
 *     what time it is. A switch with no default + the unit test's
 *     every-state-covered assertion are the two guards against a fall-through to
 *     undefined.
 *
 *  3. EXISTING POSES ONLY. The cue's `mood` is one of the FOUR sanctioned
 *     WernerMoods (idle | thinking | empty | celebrate). This file generates NO
 *     new art and adds NO fifth mood — Werner.tsx's dev runtime guard would
 *     throw, and the four-slot restraint is non-negotiable (brand/README.md,
 *     U-02). Where the pose set has no purpose-built pose for a scene state
 *     (there is no "asleep at night" pose wired into Werner.tsx, no "dawn"
 *     pose), the cue maps to the BEST-FITTING existing pose and the gap is
 *     RECORDED in POSE_GAPS below + the handoff — we never dress a generic idle
 *     pose up as a bespoke winter-dusk pose.
 *
 *  4. SUBTLE BY DESIGN. The default everywhere is `idle` — Werner is simply
 *     PRESENT in his weather, calm. The cue is a small lean, not a costume
 *     change: it is the scene-reactive INPUT the delight layer (wernerMoments)
 *     reads, and the resting mood Werner.tsx renders. A focused reader should
 *     feel the world is consistent, never be pulled to look at the penguin.
 *
 * This file maps state → POSE. It does NOT animate (SPR-06 owns motion) and does
 * NOT decide WHEN to fire a one-shot (wernerMoments owns transitions). It is the
 * quiet, total lookup the other two milestones build on.
 */
import type { SceneMood, DayPart, Weather } from "../scene/mood";
import { moodKey } from "../scene/mood";
import type { WernerMood } from "../design/tokens";

/**
 * The scene-reactive cue for a given scene mood: the resting Werner pose that
 * fits the weather, plus the scene_key it was derived from (so a consumer can
 * detect a TRANSITION without re-deriving the key) and a one-line rationale
 * (legible in tests + DevTools — why THIS pose for THIS weather).
 */
export interface WernerSceneCue {
  /** The sanctioned Werner mood (one of the four) that fits this scene. */
  mood: WernerMood;
  /** The SceneMood scene_key this cue was derived from (`${dayPart}|${weather}`). */
  sceneKey: string;
  /** Why this pose fits this weather — the §5-voice, taste-checkable reason. */
  reason: string;
}

/**
 * A recorded gap: a scene state for which the pose set has NO purpose-built
 * pose, so the cue falls back to the closest sanctioned mood. This is the
 * turnover artifact for a future operator Krea session — it names the state,
 * the pose we settled for, and the pose that would actually fit. Generating the
 * missing art is OUT OF SCOPE here (operator + Krea web app only).
 */
export interface PoseGap {
  /** The scene state (scene_key) that lacks a bespoke pose. */
  sceneKey: string;
  /** The sanctioned mood we mapped to instead. */
  fallbackMood: WernerMood;
  /** What a bespoke pose for this state would be (for the future art session). */
  wantedPose: string;
  /** Why the fallback is honest-but-imperfect. */
  note: string;
}

/**
 * The pose gaps, recorded honestly (rigor #1 — the pose set is what it is).
 *
 * The sanctioned set is FOUR character poses (idle, thinking-tilt, lost, caught-
 * a-fish). The scene has FOUR dayparts. There is no daypart-specific Werner art
 * — no "dawn-stretch," no "dusk-silhouette," no "asleep-under-the-aurora." A
 * `WernerSleeping` wrapper EXISTS (brand/werner/animated/WernerSleeping.tsx) but
 * it reuses the `empty` (lost) pose with a breathing animation — it is NOT a
 * distinct sleeping POSE, and `empty` is semantically "blank/first-run," not
 * "night." Using `empty` for "it's night" would mis-signal a system state. So
 * night maps to `idle` (Werner is calmly present in the dark), and the bespoke
 * "settled in for the night" pose is recorded as a gap, not faked.
 */
export const POSE_GAPS: readonly PoseGap[] = [
  {
    sceneKey: "dawn|snow",
    fallbackMood: "idle",
    wantedPose:
      "a waking / stretching pose — Werner just up as the light returns",
    note: "No dawn-specific pose exists; idle reads as 'present at first light', which is honest but generic. Dawn is also inert today (the app emits only day|*/night|*; SPR-06 phase-drift lights it).",
  },
  {
    sceneKey: "dawn|clear",
    fallbackMood: "idle",
    wantedPose: "the same waking pose under a clear dawn sky",
    note: "Same dawn gap; clear weather is also inert today (weather is fixed to snow in moodFromTheme).",
  },
  {
    sceneKey: "dusk|snow",
    fallbackMood: "thinking",
    wantedPose:
      "a 'watching the light go' pose — Werner gazing toward the dimming horizon",
    note: "No dusk pose exists; the thinking head-tilt is the closest 'contemplative' read in the set. A bespoke dusk-gaze pose would fit better. Dusk is inert today (SPR-06 phase-drift only).",
  },
  {
    sceneKey: "dusk|clear",
    fallbackMood: "thinking",
    wantedPose: "the same dusk-gaze pose under a clear dusk sky",
    note: "Same dusk gap; clear weather is inert today.",
  },
  {
    sceneKey: "night|snow",
    fallbackMood: "idle",
    wantedPose:
      "a 'settled in for the night' pose — Werner hunkered calmly against the cold under the aurora",
    note: "The WernerSleeping wrapper reuses the `empty`/lost pose, which is a SYSTEM-STATE pose (blank/first-run), not a night pose — mapping night to `empty` would mis-signal an empty surface. idle is the honest fallback; a true night/settled pose is the wanted art.",
  },
  {
    sceneKey: "night|clear",
    fallbackMood: "idle",
    wantedPose: "the same settled-for-night pose under clear stars",
    note: "Same night gap; clear weather is inert today.",
  },
];

/**
 * The cue table — a TOTAL map over every (dayPart, weather) pair. Written as an
 * explicit nested record (not a computed expression) so the exhaustiveness is
 * READABLE and the type system rejects a missing key at compile time:
 * `Record<DayPart, Record<Weather, ...>>` cannot be constructed with a hole.
 *
 * The design (subtle by design — rigor #2): Werner is `idle` almost everywhere
 * — present in his weather, not performing. The two non-idle resting cues are
 * dusk → `thinking` (a contemplative head-tilt as the light goes; the closest
 * existing pose to 'watching the day end') and they are RESTING moods, not
 * one-shots; the one-shot delight (e.g. a caught-a-fish flourish) is owned by
 * wernerMoments at TRANSITIONS, never baked into the resting cue here (a costume
 * change on every render would be exactly the noise the minimalist steelman
 * warns about).
 */
const CUE_TABLE: Record<
  DayPart,
  Record<Weather, { mood: WernerMood; reason: string }>
> = {
  dawn: {
    snow: {
      mood: "idle",
      reason:
        "First light through the snow — Werner is calmly present as the day begins (no dawn-specific pose; see POSE_GAPS).",
    },
    clear: {
      mood: "idle",
      reason:
        "A clear dawn — Werner present at first light (no dawn-specific pose; see POSE_GAPS).",
    },
  },
  day: {
    snow: {
      mood: "idle",
      reason:
        "Daytime in the drifting snow — Werner at home in his Antarctic weather, the steady resting state.",
    },
    clear: {
      mood: "idle",
      reason: "A clear day — Werner calmly present, the steady resting state.",
    },
  },
  dusk: {
    snow: {
      mood: "thinking",
      reason:
        "The light is going as the snow falls — the contemplative head-tilt is the closest pose to Werner watching the day end (no dusk pose; see POSE_GAPS).",
    },
    clear: {
      mood: "thinking",
      reason:
        "A clear dusk — the contemplative tilt reads as Werner watching the light fade (no dusk pose; see POSE_GAPS).",
    },
  },
  night: {
    snow: {
      mood: "idle",
      reason:
        "Night under the aurora, snow still falling — Werner settled and calmly present (no night pose; idle over `empty` so a blank-state pose isn't mis-signalled — see POSE_GAPS).",
    },
    clear: {
      mood: "idle",
      reason:
        "A clear, starlit night — Werner settled and calmly present (no night pose; see POSE_GAPS).",
    },
  },
};

/**
 * The pure scene-reactivity function: given the scene's mood, the resting Werner
 * cue that fits the weather. TOTAL (a cue for every SceneMood), DETERMINISTIC
 * (same scene_key ⇒ same cue, byte-stable), and SIDE-EFFECT-FREE (no clock, no
 * RNG, no DOM). This is the input the rest of M1/M2 reads.
 */
export function wernerForScene(mood: SceneMood): WernerSceneCue {
  const cell = CUE_TABLE[mood.dayPart][mood.weather];
  return {
    mood: cell.mood,
    sceneKey: moodKey(mood),
    reason: cell.reason,
  };
}

/** The resting Werner mood for a scene — the thin accessor Werner.tsx uses to
 *  become scene-aware without importing the whole cue shape. */
export function wernerMoodForScene(mood: SceneMood): WernerMood {
  return wernerForScene(mood).mood;
}
