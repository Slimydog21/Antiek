import type { WernerMood } from "../design/tokens";
import type { SceneArt } from "../scene/useSceneArt";
import { moodKey, type DayPart, type SceneMood, type Weather } from "../scene/mood";

export type ArtPresence = "live" | "fallback";

export interface WernerSceneCue {
  mood: WernerMood;
  sceneKey: string;
  artPresence: ArtPresence;
  reason: string;
  companionCopy: string;
}

export interface PoseGap {
  sceneKey: string;
  fallbackMood: WernerMood;
  wantedPose: string;
  note: string;
}

type CueCell = {
  mood: WernerMood;
  reason: string;
};

const LIVE_CUES: Record<DayPart, Record<Weather, CueCell>> = {
  dawn: {
    snow: {
      mood: "idle",
      reason: "First light through the snow; Werner stays calmly present.",
    },
    clear: {
      mood: "idle",
      reason: "Clear first light; Werner stays calmly present.",
    },
  },
  day: {
    snow: {
      mood: "idle",
      reason: "Daylight and snow are Werner's steady reading weather.",
    },
    clear: {
      mood: "idle",
      reason: "A clear day keeps Werner in the steady resting pose.",
    },
  },
  dusk: {
    snow: {
      mood: "thinking",
      reason: "Snow at dusk gets the quiet watching tilt.",
    },
    clear: {
      mood: "thinking",
      reason: "A clear dusk gets the quiet watching tilt.",
    },
  },
  night: {
    snow: {
      mood: "idle",
      reason: "Night snow is a settled state, not an empty state.",
    },
    clear: {
      mood: "idle",
      reason: "A clear night is settled; Werner stays present.",
    },
  },
};

const FALLBACK_CUES: Record<DayPart, Record<Weather, CueCell>> = {
  dawn: {
    snow: {
      mood: "idle",
      reason: "Procedural dawn snow is enough; Werner keeps company.",
    },
    clear: {
      mood: "idle",
      reason: "Procedural clear dawn is enough; Werner keeps company.",
    },
  },
  day: {
    snow: {
      mood: "idle",
      reason: "Procedural day snow is a designed reading state.",
    },
    clear: {
      mood: "idle",
      reason: "Procedural clear day is a designed reading state.",
    },
  },
  dusk: {
    snow: {
      mood: "thinking",
      reason: "Procedural dusk snow still earns the watching tilt.",
    },
    clear: {
      mood: "thinking",
      reason: "Procedural clear dusk still earns the watching tilt.",
    },
  },
  night: {
    snow: {
      mood: "idle",
      reason: "Procedural night snow is normal; Werner stays settled.",
    },
    clear: {
      mood: "idle",
      reason: "Procedural clear night is normal; Werner stays settled.",
    },
  },
};

// SPR-17/22 resolved dawn; SPR-29 resolved dusk; SPR-30 resolves nightfall.
// Keep the typed ledger rather than deleting the authority seam: future gaps
// must be explicit evidence records, not ad-hoc additions to product moods.
export const POSE_GAPS: readonly PoseGap[] = [];

const COMPANION_COPY: Record<ArtPresence, string> = {
  live: "Werner notices the scene and stays out of the text.",
  fallback: "No live art here; Werner stays with the procedural scene.",
};

function artPresenceFrom(sceneArt?: Pick<SceneArt, "isFallback"> | null): ArtPresence {
  return sceneArt?.isFallback ? "fallback" : "live";
}

export function wernerForScene(
  scene: SceneMood,
  sceneArt?: Pick<SceneArt, "isFallback"> | null,
): WernerSceneCue {
  const artPresence = artPresenceFrom(sceneArt);
  const cell = (artPresence === "fallback" ? FALLBACK_CUES : LIVE_CUES)[scene.dayPart][
    scene.weather
  ];

  return {
    mood: cell.mood,
    sceneKey: moodKey(scene),
    artPresence,
    reason: cell.reason,
    companionCopy: COMPANION_COPY[artPresence],
  };
}

export function wernerMoodForScene(scene: SceneMood): WernerMood {
  return wernerForScene(scene).mood;
}
