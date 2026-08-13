import { durationMs } from "../design/motion";
import type { WernerMood } from "../design/tokens";
import { moodKey, type SceneMood } from "../scene/mood";
import { wernerForScene, type WernerSceneCue } from "./wernerSceneMap";

export type WernerMomentId =
  | "nightfall"
  | "daybreak"
  | "dusk-settle"
  | "fallback-companion";

export type InterruptionBudget = "none";

export interface FrequencyCap {
  window: "per-transition" | "per-scene-state";
  max: 1;
}

export interface WernerMoment {
  id: WernerMomentId;
  pose: WernerMood;
  settlesTo: WernerMood;
  durationMs: number;
  reducedPose: WernerMood;
  interruptionBudget: InterruptionBudget;
  frequencyCap: FrequencyCap;
  copy: string;
}

const ONCE_PER_TRANSITION: FrequencyCap = { window: "per-transition", max: 1 };
const ONCE_PER_SCENE_STATE: FrequencyCap = { window: "per-scene-state", max: 1 };

export const WERNER_MOMENTS: readonly WernerMoment[] = [
  {
    id: "nightfall",
    pose: "thinking",
    settlesTo: "idle",
    durationMs: durationMs.slow,
    reducedPose: "idle",
    interruptionBudget: "none",
    frequencyCap: ONCE_PER_TRANSITION,
    copy: "The sky turns dark; the brain notices, then settles.",
  },
  {
    id: "daybreak",
    pose: "celebrate",
    settlesTo: "idle",
    durationMs: durationMs.slow,
    reducedPose: "idle",
    interruptionBudget: "none",
    frequencyCap: ONCE_PER_TRANSITION,
    copy: "The light returns; the brain gives it one small lift.",
  },
  {
    id: "dusk-settle",
    pose: "thinking",
    settlesTo: "thinking",
    durationMs: durationMs.base,
    reducedPose: "thinking",
    interruptionBudget: "none",
    frequencyCap: ONCE_PER_TRANSITION,
    copy: "The light starts to fade; the brain moves into the watching tilt.",
  },
  {
    id: "fallback-companion",
    pose: "idle",
    settlesTo: "idle",
    durationMs: durationMs.fast,
    reducedPose: "idle",
    interruptionBudget: "none",
    frequencyCap: ONCE_PER_SCENE_STATE,
    copy: "No live art here; the brain stays with the procedural scene.",
  },
];

const MOMENT_BY_ID: Record<WernerMomentId, WernerMoment> = Object.fromEntries(
  WERNER_MOMENTS.map((moment) => [moment.id, moment]),
) as Record<WernerMomentId, WernerMoment>;

function lightBand(part: SceneMood["dayPart"]): "day" | "night" | "edge" {
  if (part === "day") return "day";
  if (part === "night") return "night";
  return "edge";
}

function withSettle(moment: WernerMoment, scene: SceneMood): WernerMoment {
  return { ...moment, settlesTo: wernerForScene(scene).mood };
}

export function momentForTransition(
  prev: SceneMood | null,
  next: SceneMood,
): WernerMoment | null {
  if (!prev) return null;
  if (moodKey(prev) === moodKey(next)) return null;

  const from = lightBand(prev.dayPart);
  const to = lightBand(next.dayPart);

  if (from !== "night" && to === "night") {
    return withSettle(MOMENT_BY_ID.nightfall, next);
  }

  if (from === "night" && to === "day") {
    return withSettle(MOMENT_BY_ID.daybreak, next);
  }

  if (prev.dayPart !== "dusk" && next.dayPart === "dusk") {
    return withSettle(MOMENT_BY_ID["dusk-settle"], next);
  }

  return null;
}

export interface FallbackBeat {
  id: "fallback-companion";
  cue: WernerSceneCue;
  moment: WernerMoment;
  copy: string;
}

export function fallbackBeat(scene: SceneMood): FallbackBeat {
  const cue = wernerForScene(scene, { isFallback: true });
  const moment = {
    ...MOMENT_BY_ID["fallback-companion"],
    pose: cue.mood,
    settlesTo: cue.mood,
    reducedPose: cue.mood,
  };

  return {
    id: "fallback-companion",
    cue,
    moment,
    copy: cue.companionCopy,
  };
}
